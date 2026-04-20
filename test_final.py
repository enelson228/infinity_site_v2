import os
import urllib.request, json, base64, time

RUNPOD_API_KEY = os.getenv("RUNPOD_API_KEY")
SD_ENDPOINT_ID = "xxz7c7fu66408y"
BASE_URL = f"https://api.runpod.ai/v2/{SD_ENDPOINT_ID}"
headers = {"Authorization": f"Bearer {RUNPOD_API_KEY}", "Content-Type": "application/json"}

payload = {
    "input": {
        "prompt": "Bioluminescent deep sea alien flora, vibrant neon colors, bioluminescence, 8k, extremely detailed, cinematic lighting, sharp focus",
        "num_inference_steps": 75,
        "width": 1024,
        "height": 1024,
        "guidance_scale": 11.5,
        "seed": 999
    }
}

print("Testing Optimal Quality (The Sweet Spot)...")
req = urllib.request.Request(f"{BASE_URL}/run", data=json.dumps(payload).encode(), headers=headers, method="POST")
with urllib.request.urlopen(req) as resp:
    job_id = json.loads(resp.read().decode())["id"]

while True:
    time.sleep(5)
    status_req = urllib.request.Request(f"{BASE_URL}/status/{job_id}", headers=headers)
    with urllib.request.urlopen(status_req) as resp:
        data = json.loads(resp.read().decode())
        status = data.get("status")
        print(f"Status: {status}")
        if status == "COMPLETED":
            output = data.get("output")
            b64 = output[0].get("image") if isinstance(output, list) else (output.get("image") or output.get("images", [None])[0])
            if b64:
                if b64.startswith("data:"): b64 = b64.split(",")[1]
                with open("test_sweet_spot.png", "wb") as f: f.write(base64.b64decode(b64 + '=' * (-len(b64) % 4)))
                print("Sweet spot test saved to test_sweet_spot.png")
            break
        elif status in ["FAILED", "CANCELLED", "TIMED_OUT"]: break
