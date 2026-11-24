import json
import urllib.request
from collections import Counter

URL = "http://emi.local/api/emi"
TOTAL_REQUESTS = 30
counts = Counter()

for i in range(1, TOTAL_REQUESTS + 1):
    payload = json.dumps({"P": 100000 + i * 1000, "rate": 10.5, "n": 12}).encode("utf-8")
    req = urllib.request.Request(
        URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        body = json.loads(resp.read().decode("utf-8"))
        pod = body["servedBy"]
        counts[pod] += 1
        print(f"Request {i:02d} -> HTTP {resp.status} | Pod: {pod}")

print("\n--- Summary Table ---")
print(f"{'Pod Name':<35} | {'Requests Served':<15}")
print("-" * 53)
for pod, count in sorted(counts.items()):
    print(f"{pod:<35} | {count:<15}")
print("-" * 53)
print(f"{'Total':<35} | {sum(counts.values()):<15}")
