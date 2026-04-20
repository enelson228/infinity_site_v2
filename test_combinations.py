import urllib.request
import json
import base64
import time
import os

RUNPOD_API_KEY = os.getenv("RUNPOD_API_KEY")
SD_ENDPOINT_ID = "xxz7c7fu66408y"
BASE_URL = f"https://api.runpod.ai/v2/{SD_ENDPOINT_ID}"

headers = {
    "Authorization": f"Bearer {RUNPOD_API_KEY}",
    "Content-Type": "application/json"
}

# Testing different combinations of settings
# 1. Balanced Quality (1024x1024, 30 steps, 7.5 guidance) - The Standard
# 2. High Detail (1024x1024, 60 steps, 9.0 guidance)
# 3. High Guidance (1024x1024, 30 steps, 15.0 guidance) - Sharp/Stylized
# 4. Cinematic Wide (1536x768, 40 steps, 8.5 guidance)
# 5. Max Stability (1280x1280, 50 steps, 10.0 guidance)

combinations = [
    {
        "name": "balanced",
        "input": {
            "prompt": "A futuristic cyborg knight in gleaming chrome armor, dramatic rim lighting, dark moody background, highly detailed",
            "num_inference_steps": 30,
            "width": 1024,
            "height": 1024,
            "guidance_scale": 7.5,
            "seed": 42
        }
    },
    {
        "name": "high_detail",
        "input": {
            "prompt": "A futuristic cyborg knight in gleaming chrome armor, dramatic rim lighting, dark moody background, highly detailed",
            "num_inference_steps": 60,
            "width": 1024,
            "height": 1024,
            "guidance_scale": 9.0,
            "seed": 42
        }
    },
    {
        "name": "high_guidance",
        "input": {
            "prompt": "A futuristic cyborg knight in gleaming chrome armor, dramatic rim lighting, dark moody background, highly detailed",
            "num_inference_steps": 30,
            "width": 1024,
            "height": 1024,
            "guidance_scale": 15.0,
            "seed": 42
        }
    },
    {
        "name": "cinematic_wide",
        "input": {
            "prompt": "A futuristic cyborg knight in gleaming chrome armor, dramatic rim lighting, dark moody background, highly detailed",
            "num_inference_steps": 40,
            "width": 1536,
            "height": 768,
            "guidance_scale": 8.5,
            "seed": 42
        }
    }
]

def run_gen(name, payload):
    print(f"\n--- Testing: {name} ---")
    req = urllib.request.Request(f"{BASE_URL}/run", data=json.dumps({"input": payload}).encode(), headers=headers, method="POST")
    with urllib.request.urlopen(req) as resp:
        job_id = json.loads(resp.read().decode())["id"]
    
    print(f"Job ID: {job_id}. Polling...")
    while True:
        time.sleep(4)
        status_req = urllib.request.Request(f"{BASE_URL}/status/{job_id}", headers=headers)
        with urllib.request.urlopen(status_req) as resp:
            data = json.loads(resp.read().decode())
            status = data.get("status")
            if status == "COMPLETED":
                output = data.get("output")
                b64 = None
                if isinstance(output, list): b64 = output[0].get("image")
                elif isinstance(output, dict): b64 = output.get("image") or output.get("images", [None])[0]
                
                if b64:
                    if b64.startswith("data:"): b64 = b64.split(",")[1]
                    img_data = base64.b64decode(b64 + '=' * (-len(b64) % 4))
                    fname = f"test_{name}.png"
                    with open(fname, "wb") as f: f.write(img_data)
                    print(f"Success! Saved as {fname}")
                return
            elif status in ["FAILED", "CANCELLED", "TIMED_OUT"]:
                print(f"Failed: {status}")
                return

for combo in combinations:
    run_gen(combo["name"], combo["input"])
