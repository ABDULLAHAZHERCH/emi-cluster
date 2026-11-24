import csv
import json
import os
import random
import resource
import subprocess
import threading
import time
from datetime import datetime, timezone

RESULTS_DIR = "results"
SESSLOG_PATH = os.path.join(RESULTS_DIR, "workload_sesslog.txt")
HPA_CSV = os.path.join(RESULTS_DIR, "hpa_timeline.csv")
HPA_RAW_LOG = os.path.join(RESULTS_DIR, "hpa_raw.log")

PHASES = [
    ("Phase 1 (Warmup)", 10, 120),
    ("Phase 2 (Spike)", 100, 300),
    ("Phase 3 (Cooldown)", 10, 180),
]

current_target_rate = 10


def ensure_workload_file(num_entries=200):
    """Generate up to 200 randomized POST /api/emi session entries (httperf limit is 1000)."""
    os.makedirs(RESULTS_DIR, exist_ok=True)
    with open(SESSLOG_PATH, "w", encoding="utf-8") as f:
        for _ in range(num_entries):
            p = random.randint(50000, 2000000)
            rate = round(random.uniform(5.0, 18.0), 2)
            n = random.randint(12, 120)
            f.write(f'/api/emi method=POST contents="P={p}&rate={rate}&n={n}"\n\n')


def cap_nofile_for_httperf():
    """Keep soft open-file limit <= 1024 to prevent select() FD_SETSIZE overflow in httperf."""
    soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    if soft > 1024:
        resource.setrlimit(resource.RLIMIT_NOFILE, (1024, hard))


def poll_hpa(stop_event):
    """Record HPA status and replica count every 15 seconds."""
    start = time.time()
    with open(HPA_CSV, "w", newline="", encoding="utf-8") as cf, open(
        HPA_RAW_LOG, "w", encoding="utf-8"
    ) as lf:
        writer = csv.writer(cf)
        writer.writerow([
            "timestamp",
            "elapsed_sec",
            "target_rate",
            "avg_cpu_percent",
            "current_replicas",
            "desired_replicas",
        ])
        while not stop_event.is_set():
            now = datetime.now(timezone.utc).isoformat()
            elapsed = round(time.time() - start, 2)
            try:
                raw_table = subprocess.check_output(
                    ["kubectl", "get", "hpa", "emi-web", "-n", "emi"],
                    text=True,
                ).strip()
                lf.write(f"[{now}] (t={elapsed}s, rate={current_target_rate})\n{raw_table}\n\n")
                lf.flush()

                raw_json = subprocess.check_output(
                    ["kubectl", "get", "hpa", "emi-web", "-n", "emi", "-o", "json"],
                    text=True,
                )
                hpa_obj = json.loads(raw_json)
                status = hpa_obj.get("status", {})
                cur_rep = status.get("currentReplicas", 1)
                des_rep = status.get("desiredReplicas", 1)

                cpu_pct = 0
                for metric in status.get("currentMetrics", []):
                    if metric.get("type") == "Resource" and metric["resource"]["name"] == "cpu":
                        cpu_pct = metric["resource"]["current"].get("averageUtilization", 0)

                writer.writerow([now, elapsed, current_target_rate, cpu_pct, cur_rep, des_rep])
                cf.flush()
                print(
                    f"[HPA t={elapsed:5.1f}s] Rate={current_target_rate:3d} req/s | "
                    f"CPU={cpu_pct}% | Replicas={cur_rep} (desired={des_rep})"
                )
            except Exception as exc:
                print(f"[HPA WARN] {exc}")

            stop_event.wait(15.0)


def main():
    global current_target_rate
    ensure_workload_file(num_entries=200)
    cap_nofile_for_httperf()

    stop_event = threading.Event()
    poller = threading.Thread(target=poll_hpa, args=(stop_event,), daemon=True)
    poller.start()

    try:
        for idx, (label, rate, duration) in enumerate(PHASES, start=1):
            current_target_rate = rate
            num_sessions = rate * duration
            print(f"\n=== {label}: {rate} req/s for {duration}s ===")
            cmd = [
                "httperf",
                "--server", "emi.local",
                "--port", "80",
                r"--add-header=Content-Type: application/x-www-form-urlencoded\n",
                f"--wsesslog={num_sessions},0,{SESSLOG_PATH}",
                f"--rate={rate}",
                "--timeout=5",
            ]
            proc = subprocess.run(cmd, capture_output=True, text=True)
            combined = proc.stdout + "\n" + proc.stderr
            with open(os.path.join(RESULTS_DIR, f"httperf_hpa_phase{idx}.txt"), "w", encoding="utf-8") as pf:
                pf.write(combined)

            if proc.returncode != 0:
                raise RuntimeError(f"httperf failed in {label} (exit {proc.returncode}):\n{combined}")
    finally:
        stop_event.set()
        poller.join(timeout=5)

    print("\n10-minute autoscaling experiment completed. Data saved to results/hpa_timeline.csv.")


if __name__ == "__main__":
    main()
