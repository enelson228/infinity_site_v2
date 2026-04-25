import base64
import io
import os
import random
from typing import Any


MODEL_ID = os.environ.get("MODEL_ID", "RunDiffusion/Juggernaut-XL")
MODEL_CACHE_DIR = os.environ.get("MODEL_CACHE_DIR", "/runpod-volume/huggingface")
MODEL_FILE = os.environ.get(
    "MODEL_FILE",
    f"https://huggingface.co/{MODEL_ID}/resolve/main/juggernautXL_version2.safetensors",
)
MODEL_CONFIG_REPO = os.environ.get(
    "MODEL_CONFIG_REPO",
    "stabilityai/stable-diffusion-xl-base-1.0",
)
ORIGINAL_CONFIG_FILE = os.environ.get(
    "ORIGINAL_CONFIG_FILE",
    "https://raw.githubusercontent.com/Stability-AI/generative-models/main/configs/inference/sd_xl_base.yaml",
)
DEFAULT_NEGATIVE_PROMPT = os.environ.get(
    "DEFAULT_NEGATIVE_PROMPT",
    "blurry, low quality, distorted, deformed, watermark, text",
)

_PIPELINE = None


def _clamp_int(value: Any, low: int, high: int, default: int) -> int:
    try:
        return max(low, min(high, int(value)))
    except (TypeError, ValueError):
        return default


def _clamp_float(value: Any, low: float, high: float, default: float) -> float:
    try:
        return max(low, min(high, float(value)))
    except (TypeError, ValueError):
        return default


def _load_pipeline():
    global _PIPELINE
    if _PIPELINE is not None:
        return _PIPELINE

    import torch
    from diffusers import StableDiffusionXLPipeline

    pipe = StableDiffusionXLPipeline.from_single_file(
        MODEL_FILE,
        config=MODEL_CONFIG_REPO,
        original_config=ORIGINAL_CONFIG_FILE,
        torch_dtype=torch.float16,
        use_safetensors=True,
        cache_dir=MODEL_CACHE_DIR,
        add_watermarker=False,
    )
    pipe.to("cuda")
    pipe.enable_attention_slicing()

    if os.environ.get("ENABLE_XFORMERS", "").lower() in ("1", "true", "yes"):
        pipe.enable_xformers_memory_efficient_attention()

    _PIPELINE = pipe
    return _PIPELINE


def _png_to_b64(image) -> str:
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def generate_image(input_data: dict[str, Any], pipeline=None) -> dict[str, Any]:
    prompt = str(input_data.get("prompt") or "").strip()
    if not prompt:
        raise ValueError("prompt is required")

    negative_prompt = str(
        input_data.get("negative_prompt") or DEFAULT_NEGATIVE_PROMPT
    ).strip()
    steps = _clamp_int(input_data.get("num_inference_steps"), 1, 60, 28)
    width = _clamp_int(input_data.get("width"), 512, 1536, 1024)
    height = _clamp_int(input_data.get("height"), 512, 1536, 1024)
    guidance = _clamp_float(input_data.get("guidance_scale"), 1.0, 15.0, 7.0)
    seed_raw = input_data.get("seed")
    seed = (
        random.randint(0, 2**32 - 1)
        if seed_raw in (None, "", -1, "-1")
        else _clamp_int(seed_raw, 0, 2**32 - 1, random.randint(0, 2**32 - 1))
    )

    pipe = pipeline or _load_pipeline()

    import torch

    generator = torch.Generator(device="cuda").manual_seed(seed)
    result = pipe(
        prompt=prompt,
        negative_prompt=negative_prompt,
        num_inference_steps=steps,
        width=width,
        height=height,
        guidance_scale=guidance,
        generator=generator,
    )

    return {
        "image": _png_to_b64(result.images[0]),
        "seed": seed,
        "model": "juggernaut-xl",
        "width": width,
        "height": height,
        "num_inference_steps": steps,
        "guidance_scale": guidance,
    }


def handler(event: dict[str, Any]) -> dict[str, Any]:
    try:
        return generate_image(event.get("input") or {})
    except Exception as exc:
        return {"error": str(exc)}


if __name__ == "__main__":
    import runpod

    runpod.serverless.start({"handler": handler})
