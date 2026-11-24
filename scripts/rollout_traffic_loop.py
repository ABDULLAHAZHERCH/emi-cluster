import json
import time
import urllib.request
import urllib.error

URL = "http://emi.local/api/emi"
total = 0
failed = 0

print("Starting continuous request loop (Press Ctrl+C after rollout completes)...")
try:
    while True:
        total += 1
        payload = json.dumps({"P": 400000, "rate": 10.0, "n": 24}).encode("utf-8")
        req = urllib.request.Request(
            URL,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                print(f"[{total:03d}] OK ({resp.status}) | Pod: {data['servedBy']}")
        except (urllib.error.URLError, Exception) as exc:
            failed += 1
            print(f"[{total:03d}] FAILED: {exc}")
        time.sleep(0.3)
except KeyboardInterrupt:
    print(f"\nLoop stopped. Total requests: {total} | Failed requests: {failed}")
