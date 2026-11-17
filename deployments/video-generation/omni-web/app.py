"""LAN Gradio client for the local FastH3 Omni reference-generation API."""

from pathlib import Path
import os
import shutil
import time
import uuid

import gradio as gr
import requests


ROOT = Path(__file__).resolve().parent
UPLOADS = ROOT / "uploads"
OUTPUTS = ROOT / "outputs"
API = os.environ.get("VIDEO_API_URL", "http://127.0.0.1:8001").rstrip("/")
MODEL = os.environ.get("VIDEO_MODEL_NAME", "fasth3-omni")
TITLE = os.environ.get("VIDEO_MODEL_TITLE", "FastH3 Omni")
STEPS = int(os.environ.get("VIDEO_MODEL_STEPS", "8"))
JOB_TIMEOUT = int(os.environ.get("VIDEO_JOB_TIMEOUT", "7200"))
OUTPUT_2K = os.environ.get("VIDEO_OUTPUT_2K", "0") == "1"
SIZE_CHOICES = ([("2K 横屏 · 2560×1440", "2560x1440"), ("2K 竖屏 · 1440×2560", "1440x2560")]
                if OUTPUT_2K else [("480p 横屏 · 832×480", "832x480"), ("768p 横屏 · 1344×768", "1344x768"),
                                   ("768p 竖屏 · 768×1344", "768x1344"), ("正方形 · 768×768", "768x768")])
DEFAULT_SIZE = os.environ.get("VIDEO_DEFAULT_SIZE", SIZE_CHOICES[0][1])
if DEFAULT_SIZE not in {value for _, value in SIZE_CHOICES}:
    raise ValueError("VIDEO_DEFAULT_SIZE must be one of the configured video sizes")
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}
AUDIO_EXTENSIONS = {".wav", ".mp3", ".flac", ".m4a", ".ogg", ".aac"}


def session():
    client = requests.Session()
    client.trust_env = False
    return client


def health():
    try:
        with session() as client:
            result = client.get(f"{API}/health", timeout=3)
            result.raise_for_status()
        return "模型状态：已就绪，可以提交任务。"
    except requests.RequestException:
        return "模型状态：正在加载或服务未启动，请稍后刷新状态。"


def reference_labels(images, videos, audios):
    lines = []
    for tag, paths in (("Picture", images), ("Video", videos), ("Audio", audios)):
        for index, path in enumerate(paths or [], 1):
            name = Path(path).name.replace("`", "")
            lines.append(f"- `<{tag} {index}>`：{name}")
    return "提示词中可使用以下素材标记：\n\n" + "\n".join(lines) if lines else "上传素材后，这里会显示提示词中的引用标记。"


def stage_files(paths, kind, extensions, target):
    staged = []
    for index, source in enumerate(paths or [], 1):
        source = Path(source)
        if source.suffix.lower() not in extensions:
            raise gr.Error(f"不支持的{kind}文件格式：{source.suffix}")
        if not source.is_file():
            raise gr.Error(f"上传文件不存在：{source.name}")
        destination = target / f"{kind}-{index}{source.suffix.lower()}"
        shutil.copyfile(source, destination)
        staged.append(str(destination.resolve()))
    return staged


def request_json(response):
    if not response.ok:
        try:
            body = response.json()
            message = body.get("error", {}).get("message") or body.get("detail") or body
        except ValueError:
            message = response.text[:1200]
        raise gr.Error(f"生成服务返回 HTTP {response.status_code}：{message}")
    return response.json()


def generate(images, videos, audios, prompt, size, seconds, seed):
    images, videos, audios = images or [], videos or [], audios or []
    if not images and not videos:
        raise gr.Error("请至少上传一张参考图片或一个参考视频。")
    if len(images) > 9 or len(videos) > 3 or len(audios) > 3 or len(images) + len(videos) + len(audios) > 12:
        raise gr.Error("最多 9 张图片、3 个视频、3 段音频，素材总数不超过 12。")
    if not prompt or not prompt.strip():
        raise gr.Error("请填写生成要求。")
    if size not in {value for _, value in SIZE_CHOICES} or int(seconds) not in {5, 10, 15}:
        raise gr.Error("请选择界面提供的分辨率和时长。")
    started = time.monotonic()
    target = UPLOADS / uuid.uuid4().hex
    target.mkdir(parents=True)
    pictures = stage_files(images, "image", IMAGE_EXTENSIONS, target)
    clips = stage_files(videos, "video", VIDEO_EXTENSIONS, target)
    sounds = stage_files(audios, "audio", AUDIO_EXTENSIONS, target)
    body = {
        "model": MODEL, "task": "ref2va", "prompt": prompt.strip(),
        "num_inference_steps": STEPS,
        "size": size, "seconds": str(int(seconds)), "seed": int(seed),
    }
    if pictures:
        body["image_reference"] = [{"image_url": path} for path in pictures]
    if clips:
        body["video_reference"] = [{"video_url": path} for path in clips]
    if sounds:
        body["audio_reference"] = [{"audio_url": path} for path in sounds]
    with session() as client:
        try:
            job = request_json(client.post(f"{API}/v1/videos", json=body, timeout=90))
            job_id = job["id"]
            deadline = time.monotonic() + JOB_TIMEOUT
            while job["status"] != "completed":
                if job["status"] == "cancelled":
                    raise gr.Error(f"任务已取消：{job_id}")
                if job["status"] == "failed":
                    raise gr.Error(f"生成失败：{job.get('error')}")
                label = "排队中" if job["status"] == "queued" else "生成中"
                elapsed = int(time.monotonic() - started)
                stage = job.get("stage") or label
                yield None, None, f"{stage}，已等待 {elapsed} 秒。任务：{job_id}"
                if time.monotonic() > deadline:
                    raise gr.Error(f"等待超时，任务可能仍在运行。任务编号：{job_id}")
                time.sleep(3)
                job = request_json(client.get(f"{API}/v1/videos/{job_id}", timeout=30))
            output = OUTPUTS / f"{job_id}.mp4"
            with client.get(f"{API}/v1/videos/{job_id}/content", stream=True, timeout=180) as response:
                response.raise_for_status()
                with output.open("wb") as handle:
                    for chunk in response.iter_content(chunk_size=1024 * 1024):
                        handle.write(chunk)
            elapsed = round(time.monotonic() - started, 1)
            yield str(output), str(output), f"生成完成，用时 {elapsed} 秒。任务：{job_id}"
        except requests.RequestException as error:
            raise gr.Error(f"连接生成服务失败：{error}") from error


def create_ui():
    with gr.Blocks(title=f"{TITLE} 参考视频生成", theme=gr.themes.Soft()) as demo:
        gr.Markdown(f"# {TITLE}\n使用图片、视频和文字生成带同步音频的新视频。")
        state = gr.Markdown(health())
        refresh = gr.Button("刷新模型状态", size="sm")
        with gr.Row():
            with gr.Column(scale=1):
                images = gr.File(label="参考图片（最多 9 张）", file_count="multiple", file_types=["image"], type="filepath")
                videos = gr.File(label="参考视频（最多 3 个）", file_count="multiple", file_types=["video"], type="filepath")
                with gr.Accordion("参考音频（可选）", open=False):
                    audios = gr.File(label="参考音频（最多 3 段）", file_count="multiple", file_types=["audio"], type="filepath")
                labels = gr.Markdown(reference_labels(None, None, None))
                gr.Markdown("至少提供图片或视频之一；所有参考素材合计最多 12 个。")
            with gr.Column(scale=2):
                prompt = gr.Textbox(label="生成要求", lines=8, placeholder="例如：保持 <Picture 1> 中角色的外观，参考 <Video 1> 的动作，在雪地中向前奔跑。镜头平稳跟随，可听见踩雪声和风声。")
                with gr.Row():
                    size = gr.Dropdown(label="分辨率", choices=SIZE_CHOICES, value=DEFAULT_SIZE)
                    seconds = gr.Dropdown(label="视频时长（秒）", choices=[5, 10, 15], value=5)
                    seed = gr.Number(label="随机种子", value=1234, precision=0)
                gr.Markdown("24 FPS，自动生成同步音频。时长按模型帧数要求对齐；较大画幅、更多参考素材需要更长时间。")
                submit = gr.Button("生成视频", variant="primary")
                status = gr.Textbox(label="任务状态", value="等待提交", interactive=False)
                result = gr.Video(label="生成结果（含音频）")
                download = gr.File(label="下载 MP4", interactive=False)
        for component in (images, videos, audios):
            component.change(reference_labels, inputs=[images, videos, audios], outputs=labels, api_name=False)
        refresh.click(health, outputs=state, api_name="model_status")
        demo.load(health, outputs=state, api_name=False)
        timer = gr.Timer(value=15)
        timer.tick(health, outputs=state, api_name=False)
        submit.click(generate, inputs=[images, videos, audios, prompt, size, seconds, seed], outputs=[result, download, status], api_name="generate")
    return demo


if __name__ == "__main__":
    UPLOADS.mkdir(parents=True, exist_ok=True)
    OUTPUTS.mkdir(parents=True, exist_ok=True)
    create_ui().queue(default_concurrency_limit=1, max_size=12).launch(
        server_name="0.0.0.0", server_port=7860, share=False,
        allowed_paths=[str(OUTPUTS)], max_file_size="512mb", show_error=True,
    )
