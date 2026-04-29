# Forge SDXL RunPod Worker

Queue-based RunPod Serverless worker for the Forge page. It accepts the same input shape that `blueprints/forge.py` sends today and returns a base64 PNG that the existing gallery code can save.

## Build

```bash
docker build -t <registry>/juggernaut-xl-runpod:latest .
docker push <registry>/juggernaut-xl-runpod:latest
```

This repo also includes a manual GitHub Actions workflow that publishes:

```text
ghcr.io/enelson228/infinity-site-v2-juggernaut-xl:latest
```

## RunPod Endpoint

Create a queue-based Serverless endpoint with:

- Worker image: `ghcr.io/enelson228/infinity-site-v2-juggernaut-xl:latest`
- GPU: `L4/A5000/A6000/A40/3090/4090 24GB` first. RTX 5090 requires the CUDA 12.8+ worker image in this directory.
- Active workers: `0`
- Max workers: `1`
- GPUs per worker: `1`
- Idle timeout: `5s`
- Execution timeout: `300-600s`
- FlashBoot: enabled

Set the endpoint ID in the app environment as `FORGE_ENDPOINT_ID` for Juggernaut XL or `CYBERREALISTIC_PONY_ENDPOINT_ID` for CyberRealistic Pony. Keep `RUNPOD_API_KEY` configured for the Flask app.

## Worker Environment

- `MODEL_ID`: defaults to `RunDiffusion/Juggernaut-XL`
- `MODEL_FILE`: defaults to the repo's `juggernautXL_version2.safetensors` single-file checkpoint using a direct `/resolve/main/` Hugging Face URL
- `MODEL_SLUG`: response model label returned to Forge, defaults to `juggernaut-xl`
- `ORIGINAL_CONFIG_FILE`: defaults to Stability AI's `sd_xl_base.yaml`
- `MODEL_CACHE_DIR`: defaults to `/runpod-volume/huggingface`
- `DEFAULT_NEGATIVE_PROMPT`: optional fallback negative prompt
- `ENABLE_XFORMERS`: optional `true` if the image includes a compatible xFormers build

Using a network volume for `/runpod-volume/huggingface` reduces repeated model downloads after the first cold start, but it adds storage cost. For lowest monthly cost, start without a volume and add one only if cold starts are too slow.

To reuse the same image for CyberRealistic Pony, create a second RunPod template with:

- `MODEL_SLUG=cyberrealistic-pony`
- `MODEL_ID=cyberdelia/CyberRealisticPony`
- `MODEL_FILE=https://huggingface.co/cyberdelia/CyberRealisticPony/resolve/main/CyberRealisticPony_V17.0_FP16.safetensors`
- `ENABLE_XFORMERS=false`

## Smoke Payload

```json
{
  "input": {
    "prompt": "cinematic photo of a futuristic mountain observatory at sunrise",
    "negative_prompt": "blurry, low quality, watermark, text",
    "num_inference_steps": 28,
    "width": 1024,
    "height": 1024,
    "guidance_scale": 7,
    "seed": -1,
    "model": "juggernaut-xl"
  }
}
```

## Cost Guardrails

This worker is intended for private Forge use. Keep Flex workers with `active_workers=0` so no GPU compute accrues while idle, and keep `max_workers=1` so runaway concurrent jobs cannot multiply cost.
