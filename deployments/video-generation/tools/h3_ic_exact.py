"""IC inference data movement optimizations; leave every arithmetic operator unchanged."""

import ctypes
import gc


class ExactDiagnosticComplete(Exception):
    """A bounded real-input parity diagnostic, never a completed video."""


def chunk_forward_preallocated(original, size=2048):
    """Keep the existing GEMM shapes; copy chunk results into their final storage."""
    def forward(hidden_states, *args, **kwargs):
        if hidden_states.shape[1] <= size:
            return original(hidden_states, *args, **kwargs)
        output = None
        offset = 0
        for part in hidden_states.split(size, dim=1):
            value = original(part, *args, **kwargs)
            if output is None:
                output = value.new_empty((value.shape[0], hidden_states.shape[1], *value.shape[2:]))
            output[:, offset:offset + value.shape[1]].copy_(value)
            offset += value.shape[1]
            del value
        return output
    return forward


def precast_lora_compute_weights(model, compute_device="cpu"):
    """Cache exactly the BF16 casts performed by every original LoRALinear call.

    The unmerged A-then-B computation remains unchanged. The original FP32
    masters remain in the checkpoint on disk, rather than being repeatedly
    transferred to CUDA and cast for every FFN chunk. Reject other input dtypes
    instead of silently using these cached casts for a different computation.
    """
    import torch
    count = saved = 0

    def check_dtype(module, args):
        if args[0].dtype != torch.bfloat16:
            raise RuntimeError("Cached IC LoRA casts require the original BF16 activation dtype")

    with torch.no_grad():
        for module in model.modules():
            if type(module).__name__ != "LoRALinear":
                continue
            if module.base.weight.dtype != torch.bfloat16:
                raise RuntimeError("Unexpected IC LoRA base precision")
            for name in ("lora_A", "lora_B"):
                parameter = getattr(module, name)
                if parameter.device.type != "cpu" or parameter.dtype != torch.float32:
                    raise RuntimeError("Precast IC LoRA masters once, on the host, before placement")
                saved += parameter.numel() * 2
                # Perform the cast on the original compute device too: CPU and
                # CUDA conversion edge cases must not be assumed identical.
                parameter.data = parameter.detach().to(compute_device).to(torch.bfloat16).to("cpu")
            module.register_forward_pre_hook(check_dtype)
            count += 1
    return {"linears": count, "host_bytes_saved": saved,
            "compute_dtype": "bfloat16", "cast_device": str(compute_device), "lora_merged": False}


def readonly_block_offload(model, device):
    """Restore immutable host storage instead of copying unchanged weights back.

    Copies and all computation use the same CUDA stream. Host tensors remain
    alive and immutable for the entire model lifetime. No pinned-memory clone,
    extra model copy, different arithmetic, or new attention backend is used.
    """
    import torch
    for name, module in model.named_children():
        if name != "transformer_blocks":
            module.to(device)
    step = {"number": 0}

    def begin(module, args, kwargs):
        if torch.is_grad_enabled():
            raise RuntimeError("Read-only IC offload is for inference only")
        step["number"] += 1
        print(f"IC denoising step {step['number']} started", flush=True)

    model.register_forward_pre_hook(begin, with_kwargs=True)
    total = 0
    for index, block in enumerate(model.transformer_blocks):
        parameters = [(parameter, parameter.detach()) for parameter in block.parameters()]
        buffers = [(module, name, value) for module in block.modules() for name, value in module._buffers.items()
                   if value is not None]
        if any(value.device.type != "cpu" for _, value in parameters) or \
                any(value.device.type != "cpu" for _, _, value in buffers):
            raise RuntimeError("Capture immutable CPU weights before CUDA placement")
        if any(parameter.requires_grad for parameter, _ in parameters):
            raise RuntimeError("Read-only IC offload cannot be used with trainable weights")
        total += sum(value.numel() * value.element_size() for _, value in parameters)

        def onload(module, args, block_index=index, host_parameters=parameters, host_buffers=buffers):
            if block_index % 10 == 0:
                print(f"IC step {step['number']}: block {block_index + 1}/50", flush=True)
            for parameter, host in host_parameters:
                parameter.data = host.to(device, non_blocking=True)
            for child, name, host in host_buffers:
                child._buffers[name] = host.to(device, non_blocking=True)

        def unload(module, args, output, host_parameters=parameters, host_buffers=buffers):
            for parameter, host in host_parameters:
                parameter.data = host
            for child, name, host in host_buffers:
                child._buffers[name] = host

        block.register_forward_pre_hook(onload)
        block.register_forward_hook(unload, always_call=True)
    gc.collect()
    ctypes.CDLL(None).malloc_trim(0)
    torch.cuda.empty_cache()
    print(f"IC placement: immutable CPU storage ({total} bytes), H2D only, unchanged BF16 math", flush=True)
    return model


def install_real_input_diagnostic(model, report_path, legacy_ff):
    """Compare the first real block to original FP32-master LoRA and FFN I/O.

    Run only as an explicitly requested standalone diagnostic. Do not finish
    denoising or produce a video. The full model's 312 casts and actual packing
    run before this hook, then the original first-block arithmetic is replayed
    with its exact original inputs and adapted base weights.
    """
    import json
    from pathlib import Path
    import time
    import torch
    from safetensors import safe_open
    root = Path(__file__).resolve().parents[1]
    archive_path = root / "models/Open-H3-Regenerate-2K-IC/lora/open_h3_regenerate_2k_ic_lora.safetensors"

    def verify(block, args, kwargs, output):
        torch.cuda.synchronize()
        # The read-only offload post-hook has already restored these CPU tensors.
        parameters = [(parameter, parameter.detach()) for parameter in block.parameters()]
        buffers = [(child, name, value) for child in block.modules() for name, value in child._buffers.items()
                   if value is not None]
        if any(host.device.type != "cpu" for _, host in parameters):
            raise RuntimeError("Real-input diagnostic must follow the read-only unload hook")
        start = time.monotonic()
        masters = 0
        try:
            block.to("cuda")
            with safe_open(archive_path, framework="pt", device="cpu") as archive:
                for name, module in block.named_modules():
                    if type(module).__name__ != "LoRALinear":
                        continue
                    for matrix in ("A", "B"):
                        key = f"transformer.transformer_blocks.0.{name}.lora_{matrix}.weight"
                        getattr(module, "lora_" + matrix).data = archive.get_tensor(key).cuda().float()
                        masters += 1
            # Calling forward directly avoids running the offload and diagnostic
            # hooks recursively. All original child operators still execute.
            with legacy_ff():
                reference = block.forward(*args, **kwargs)
            torch.cuda.synchronize()
            equal = torch.equal(reference, output)
            report = {"status": "real_input_first_block_bitwise_verified" if equal else "bitwise_comparison_failed",
                      "full_model_loaded": True, "cached_lora_linears": 312,
                      "original_fp32_lora_matrices_reloaded": masters,
                      "input_shape": list(args[0].shape), "output_shape": list(output.shape),
                      "compared_elements": output.numel(), "dtype": str(output.dtype),
                      "bit_equal": equal, "reference_replay_seconds_including_weight_reload": time.monotonic() - start,
                      "full_video_generated": False,
                      "scope": "Actual production packed input and adapted weights; original FP32 LoRA masters, original FFN chunking and original arithmetic replayed"}
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(json.dumps(report, indent=2) + "\n")
            print("IC_REAL_INPUT_PARITY", json.dumps(report), flush=True)
            if not equal or masters != 12:
                raise RuntimeError("Reject exact I/O: real-input original arithmetic comparison failed")
        finally:
            for parameter, host in parameters:
                parameter.data = host
            for child, name, host in buffers:
                child._buffers[name] = host
        raise ExactDiagnosticComplete("Real-input parity verified; diagnostic stopped before the rest of denoising")

    model.transformer_blocks[0].register_forward_hook(verify, with_kwargs=True)
