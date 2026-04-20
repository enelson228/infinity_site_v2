import os
import urllib.request, json
RUNPOD_API_KEY = os.getenv("RUNPOD_API_KEY")
SD_ENDPOINT_ID = "xxz7c7fu66408y"
job_id = "112e3b2d-c77a-4fe4-82a8-1ebea1c07b6b-u2"
url = f"https://api.runpod.ai/v2/{SD_ENDPOINT_ID}/status/{job_id}"
req = urllib.request.Request(url, headers={"Authorization": f"Bearer {RUNPOD_API_KEY}"})
with urllib.request.urlopen(req) as resp:
    data = json.loads(resp.read().decode())
    print(json.dumps(data.get("output"), indent=2))
