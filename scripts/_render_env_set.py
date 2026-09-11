"""Set BASE_RPC_URL -> drpc + WHALEFLOW_CHUNK_BLOCKS on Render (keys never printed)."""
import os
import time

import requests

key = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "..", "secrets", "render_api_key.txt")).read().strip()
h = {"Authorization": f"Bearer {key}", "Accept": "application/json",
     "Content-Type": "application/json"}
sid = "srv-d9maroe7bikc73adkaug"

for attempt in range(4):
    try:
        r1 = requests.put(
            f"https://api.render.com/v1/services/{sid}/env-vars/BASE_RPC_URL",
            headers=h, json={"value": "https://base.drpc.org"}, timeout=30)
        print("BASE_RPC_URL -> drpc:", r1.status_code)
        r2 = requests.post(
            f"https://api.render.com/v1/services/{sid}/env-vars",
            headers=h, json={"key": "WHALEFLOW_CHUNK_BLOCKS", "value": "250"},
            timeout=30)
        print("WHALEFLOW_CHUNK_BLOCKS=250:", r2.status_code)
        break
    except requests.exceptions.ConnectionError as exc:
        print(f"attempt {attempt}: connection error, retrying...")
        time.sleep(10)