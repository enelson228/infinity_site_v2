import os
import urllib.request
import json
import base64
import time
import sys

RUNPOD_API_KEY = os.getenv("RUNPOD_API_KEY")
SD_ENDPOINT_ID = "xxz7c7fu66408y"
BASE_URL = f"https://api.runpod.ai/v2/{SD_ENDPOINT_ID}"

headers = {
    "Authorization": f"Bearer {RUNPOD_API_KEY}",
    "Content-Type": "application/json"
}

# Maximize settings: High steps, high resolution
payload = {
    "input": {
        "prompt": "A spectacular hyper-detailed futuristic cyber city, neon lights, 8k resolution, masterpiece",
        "negative_prompt": "blurry, low quality, deformed",
        "num_inference_steps": 100,
        "width": 1536,
        "height": 1536,
        "guidance_scale": 20.0
    }
}

print("Starting generation experiment with maximized settings...")
print(f"Prompt: {payload['input']['prompt']}")
print(f"Steps: {payload['input']['num_inference_steps']}")
print(f"Resolution: {payload['input']['width']}x{payload['input']['height']}")
print(f"Guidance: {payload['input']['guidance_scale']}")

req = urllib.request.Request(
    f"{BASE_URL}/run",
    data=json.dumps(payload).encode(),
    headers=headers,
    method="POST"
)

try:
    with urllib.request.urlopen(req) as response:
        result = json.loads(response.read().decode())
        job_id = result.get("id")
        print(f"Job submitted! Job ID: {job_id}")
except Exception as e:
    print(f"Failed to submit job: {e}")
    sys.exit(1)

print("Polling for status...")
while True:
    status_req = urllib.request.Request(
        f"{BASE_URL}/status/{job_id}",
        headers=headers
    )
    try:
        with urllib.request.urlopen(status_req) as resp:
            status_data = json.loads(resp.read().decode())
            status = status_data.get("status")
            print(f"Status: {status}")
            
            if status == "COMPLETED":
                output = status_data.get("output")
                b64_image = None
                if isinstance(output, list) and output:
                    b64_image = output[0].get("image") or output[0].get("images", [None])[0]
                elif isinstance(output, dict):
                    b64_image = output.get("image") or (output.get("images") or [None])[0]
                
                if isinstance(b64_image, str) and b64_image.startswith("data:"):
                    b64_image = b64_image.split(",", 1)[1]
                    
                if b64_image:
                    image_bytes = base64.b64decode(b64_image + '=' * (-len(b64_image) % 4))
                    filename = "experiment_max_settings.png"
                    with open(filename, "wb") as f:
                        f.write(image_bytes)
                    print(f"Experiment successful! Image saved to {filename}")
                else:
                    print("No image found in output.")
                break
            elif status in ["FAILED", "CANCELLED", "TIMED_OUT"]:
                print(f"Job failed with status: {status}")
                if "error" in status_data:
                    print(f"Error: {status_data['error']}")
                break
                
    except Exception as e:
        print(f"Error polling status: {e}")
        
    time.sleep(5)
