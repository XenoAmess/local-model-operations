# Portions adapted from Diffusers MiniMax-H3, MiniMax Team/HuggingFace, Apache-2.0.
"""Bound activations while retaining dense attention over the complete H3 sequence.

No temporal diffusion windows, sparse attention, LoRA merging or precision change.
Projection/query chunks can change floating-point rounding and must be validated.
"""

import types


def _modulated(norm, states, scale, shift, indices):
    return norm(states) * (1.0 + scale.index_select(0, indices)) + shift.index_select(0, indices)


class FullSequenceAttention:
    def __init__(self, chunk=16384, flash_only=True):
        self.chunk, self.flash_only = chunk, flash_only

    def __call__(self, attn, hidden_states, rotary_emb=None, attention_mask=None):
        import torch
        import torch.nn.functional as F
        from contextlib import nullcontext
        from diffusers.models.transformers.transformer_minimax_h3 import _apply_rotary_emb
        if attention_mask is not None or attn.fused_projections:
            raise ValueError("Full-sequence IC requires unfused projections and unmasked dense attention")
        batch, length, _ = hidden_states.shape
        heads = attn.heads
        dim = attn.to_k.weight.shape[0] // heads
        # Allocate directly in head-major form: never duplicate full K/V just to
        # satisfy an attention kernel's layout. All keys remain visible to Q.
        keys = hidden_states.new_empty((batch, heads, length, dim))
        values = torch.empty_like(keys)
        for start in range(0, length, self.chunk):
            end = min(length, start + self.chunk)
            part = hidden_states[:, start:end]
            key = attn.norm_k(attn.to_k(part).unflatten(-1, (heads, dim)))
            if rotary_emb is not None:
                key = _apply_rotary_emb(key, *(x[start:end] for x in rotary_emb))
            keys[:, :, start:end].copy_(key.transpose(1, 2))
            values[:, :, start:end].copy_(attn.to_v(part).unflatten(-1, (heads, dim)).transpose(1, 2))
            del key, part
        output = torch.empty_like(hidden_states)
        for start in range(0, length, self.chunk):
            end = min(length, start + self.chunk)
            query = attn.norm_q(attn.to_q(hidden_states[:, start:end]).unflatten(-1, (heads, dim)))
            if rotary_emb is not None:
                query = _apply_rotary_emb(query, *(x[start:end] for x in rotary_emb))
            context = nullcontext()
            if self.flash_only and query.device.type == "cuda":
                from torch.nn.attention import SDPBackend, sdpa_kernel
                context = sdpa_kernel(SDPBackend.FLASH_ATTENTION)
            with context:
                attended = F.scaled_dot_product_attention(query.transpose(1, 2), keys, values,
                                                         dropout_p=0.0, is_causal=False)
            attended = attended.transpose(1, 2).flatten(2, 3).type_as(query)
            output[:, start:end].copy_(attn.to_out[1](attn.to_out[0](attended)))
            del query, attended
        del keys, values
        return output


def bounded_block(self, hidden_states, temb, adaln_indices, rotary_emb, attention_mask=None):
    import torch
    if torch.is_grad_enabled():
        raise RuntimeError("Bounded H3 block is inference-only")
    shift_a, scale_a, gate_a, shift_f, scale_f, gate_f = self.adaln_proj(temb)
    length = hidden_states.shape[1]
    normed = torch.empty_like(hidden_states)
    for start in range(0, length, self._full_chunk):
        end = min(length, start + self._full_chunk)
        normed[:, start:end].copy_(_modulated(self.norm1, hidden_states[:, start:end], scale_a, shift_a,
                                             adaln_indices[start:end]))
    attended = self.attn(normed, rotary_emb, attention_mask)
    del normed
    for start in range(0, length, self._full_chunk):
        end = min(length, start + self._full_chunk)
        # Keep the multiplication/addition order; reuse only dead storage.
        hidden_states[:, start:end].copy_(hidden_states[:, start:end] +
                                         gate_a.index_select(0, adaln_indices[start:end]) * attended[:, start:end])
    del attended
    for start in range(0, length, self._full_ff_chunk):
        end = min(length, start + self._full_ff_chunk)
        part = hidden_states[:, start:end]
        normed = _modulated(self.norm2, part, scale_f, shift_f, adaln_indices[start:end])
        feed = self.ff(normed)
        part.copy_(part + gate_f.index_select(0, adaln_indices[start:end]) * feed)
        del part, normed, feed
    return hidden_states


def bounded_forward(self, hidden_states, audio_hidden_states, encoder_hidden_states, timestep,
                    timestep_indices, token_tags, position_ids, video_indices, audio_indices,
                    text_indices, attention_kwargs=None, return_dict=True):
    import torch
    from diffusers.models.modeling_utils import get_parameter_dtype
    from diffusers.models.transformers.transformer_minimax_h3 import MiniMaxH3TransformerOutput
    if torch.is_grad_enabled() or attention_kwargs not in (None, {}):
        raise ValueError("Full-sequence IC is inference-only, with the pinned unmerged LoRA stack")
    self._full_step = getattr(self, "_full_step", 0) + 1
    length = position_ids.shape[0]
    if position_ids.shape != (length, 3) or token_tags.shape != (length,) or timestep_indices.shape != (length,):
        raise ValueError("Full-sequence packed layout mismatch")
    rotary = self.rope(position_ids)
    text = self.context_embedder(encoder_hidden_states.to(get_parameter_dtype(self.context_embedder)))
    text = self.token_refiner(text)
    packed = text.new_zeros((text.shape[0], length, text.shape[-1]))
    packed.index_copy_(1, text_indices, text)
    del text
    for source, projection, indices in ((hidden_states, self.proj_in, video_indices),
                                        (audio_hidden_states, self.audio_proj_in, audio_indices)):
        for start in range(0, source.shape[1], self._full_chunk):
            end = min(source.shape[1], start + self._full_chunk)
            projected = projection(source[:, start:end].to(get_parameter_dtype(projection)))
            packed.index_copy_(1, indices[start:end], projected.to(packed.dtype))
            del projected
    temb = self.time_embedder(self.time_proj(timestep).to(get_parameter_dtype(self.time_embedder)))
    adaln_indices = timestep_indices * 3 + token_tags
    for index, block in enumerate(self.transformer_blocks):
        packed = block(packed, temb, adaln_indices, rotary)
        if index % 5 == 4:
            from h3_full_sequence import progress
            total = getattr(self, "_full_total_steps", 3)
            progress(getattr(self, "_full_progress", None),
                     f"整段密集推理：第 {self._full_step}/{total} 步，第 {index+1}/{len(self.transformer_blocks)} 层",
                     15 + int(70 * ((self._full_step - 1) + (index+1) / len(self.transformer_blocks)) / total),
                     denoising_step=self._full_step, transformer_block=index+1, global_tokens=length)
            print(f"Full-sequence dense: block {index + 1}/50, {length} global tokens; "
                  f"GPU allocated {torch.cuda.memory_allocated() / 2**30:.2f} GiB, "
                  f"peak {torch.cuda.max_memory_allocated() / 2**30:.2f} GiB", flush=True)
    video_all = packed.new_empty((packed.shape[0], length, self.proj_out.out_features), dtype=get_parameter_dtype(self.proj_out))
    audio_all = packed.new_empty((packed.shape[0], length, self.audio_proj_out.out_features), dtype=get_parameter_dtype(self.audio_proj_out))
    for start in range(0, length, self._full_chunk):
        end = min(length, start + self._full_chunk)
        normalized = self.norm_out(packed[:, start:end], temb, timestep_indices[start:end])
        video_all[:, start:end].copy_(self.proj_out(normalized.to(get_parameter_dtype(self.proj_out))))
        audio_all[:, start:end].copy_(self.audio_proj_out(normalized.to(get_parameter_dtype(self.audio_proj_out))))
        del normalized
    video, audio = video_all.index_select(1, video_indices), audio_all.index_select(1, audio_indices)
    if not return_dict:
        return video, audio
    return MiniMaxH3TransformerOutput(sample=video, audio_sample=audio)


def install(model, chunk=16384, ff_chunk=2048, progress_path=None):
    if chunk < 1 or ff_chunk < 1:
        raise ValueError("Chunk sizes must be positive")
    model._full_chunk = chunk
    model._full_progress = progress_path
    model.forward = types.MethodType(bounded_forward, model)
    for block in model.transformer_blocks:
        block._full_chunk, block._full_ff_chunk = chunk, ff_chunk
        block.attn.set_processor(FullSequenceAttention(chunk))
        block.forward = types.MethodType(bounded_block, block)
    print(f"Full-sequence IC: dense global attention; query/projection chunks {chunk}, FFN {ff_chunk}; "
          "all K/V retained; no independent temporal windows", flush=True)
    return model
