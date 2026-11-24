import csv
import os
import random
import re
import resource
import subprocess
import threading
import time
from datetime import datetime, timezone
import psutil

RESULTS_DIR = "results"
SESSLOG_PATH = os.path.join(RESULTS_DIR, "workload_sesslog.txt")
SUMMARY_CSV = os.path.join(RESULTS_DIR, "fixed_summary.csv")

REPLICAS_LIST = [1, 2, 3]
RATES_LIST = [10, 25, 50, 100, 200]
DURATION_SEC = 60


def ensure_workload_file(num_entries=200):
    """Generate 200 randomized POST /api/emi session entries (httperf limit is 1000)."""
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


def scale_deployment(replicas):
    print(f"\n[CLUSTER] Scaling emi-web to {replicas} replica(s)...")
    subprocess.run(
        ["kubectl", "scale", "deployment", "emi-web", f"--replicas={replicas}", "-n", "emi"],
        check=True,
    )
    subprocess.run(
        ["kubectl", "rollout", "status", "deployment/emi-web", "-n", "emi"],
        check=True,
    )
    while True:
        out = subprocess.check_output(
            ["kubectl", "get", "pods", "-n", "emi", "-l", "app=emi-web", "--no-headers"],
            text=True,
        ).strip()
        lines = [line for line in out.splitlines() if line.strip()]
        ready_lines = [line for line in lines if "1/1" in line and "Running" in line]
        if len(lines) == replicas and len(ready_lines) == replicas:
            break
        time.sleep(2)
    time.sleep(5)


def profile_host_cpu(stop_event, csv_path):
    start = time.time()
    psutil.cpu_percent(interval=None)
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp", "elapsed_sec", "host_cpu_percent"])
        while not stop_event.is_set():
            cpu = psutil.cpu_percent(interval=1.0)
            now = datetime.now(timezone.utc).isoformat()
            elapsed = round(time.time() - start, 2)
            writer.writerow([now, elapsed, cpu])
            f.flush()


def profile_pod_metrics(stop_event, csv_path):
    start = time.time()
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "timestamp",
            "elapsed_sec",
            "pod_name",
            "cpu_millicores",
            "cpu_percent_of_100m_request",
            "memory_mi",
        ])
        while not stop_event.is_set():
            now = datetime.now(timezone.utc).isoformat()
            elapsed = round(time.time() - start, 2)
            try:
                out = subprocess.check_output(
                    ["kubectl", "top", "pods", "-n", "emi", "--no-headers"],
                    text=True,
                    stderr=subprocess.DEVNULL,
                )
                for line in out.strip().splitlines():
                    parts = line.split()
                    if len(parts) >= 3:
                        pod = parts[0]
                        cpu_m = int(parts[1].replace("m", ""))
                        mem_mi = int(parts[2].replace("Mi", ""))
                        cpu_pct = round((cpu_m / 100.0) * 100.0, 2) if pod.startswith("emi-web") else ""
                        writer.writerow([now, elapsed, pod, cpu_m, cpu_pct, mem_mi])
                f.flush()
            except subprocess.CalledProcessError:
                pass
            stop_event.wait(15.0)


def parse_httperf_output(raw_text):
    rate_match = re.search(r"Request rate:\s+([\d.]+)\s+req/s", raw_text)
    resp_match = re.search(r"Reply time \[ms\]:\s+response\s+([\d.]+)", raw_text)
    err_match = re.search(r"Errors:\s+total\s+(\d+)", raw_text)
    s2xx_match = re.search(r"2xx=(\d+)", raw_text)
    s4xx_match = re.search(r"4xx=(\d+)", raw_text)
    s5xx_match = re.search(r"5xx=(\d+)", raw_text)

    actual_rate = float(rate_match.group(1)) if rate_match else 0.0
    avg_resp_ms = float(resp_match.group(1)) if resp_match else 0.0
    net_errors = int(err_match.group(1)) if err_match else 0
    ok_2xx = int(s2xx_match.group(1)) if s2xx_match else 0
    err_4xx = int(s4xx_match.group(1)) if s4xx_match else 0
    err_5xx = int(s5xx_match.group(1)) if s5xx_match else 0

    total_errors = net_errors + err_4xx + err_5xx
    return actual_rate, avg_resp_ms, ok_2xx, total_errors


def main():
    ensure_workload_file(num_entries=200)
    cap_nofile_for_httperf()

    with open(SUMMARY_CSV, "w", newline="", encoding="utf-8") as sf:
        summary_writer = csv.writer(sf)
        summary_writer.writerow([
            "replicas",
            "target_rate",
            "actual_rate",
            "avg_response_ms",
            "ok_2xx",
            "error_count",
        ])

        for replicas in REPLICAS_LIST:
            scale_deployment(replicas)

            for rate in RATES_LIST:
                num_sessions = rate * DURATION_SEC
                tag = f"r{replicas}_rate{rate}"
                host_csv = os.path.join(RESULTS_DIR, f"host_cpu_{tag}.csv")
                pod_csv = os.path.join(RESULTS_DIR, f"pod_metrics_{tag}.csv")
                raw_txt = os.path.join(RESULTS_DIR, f"httperf_{tag}.txt")

                print(f"[RUN] Replicas={replicas} | Target Rate={rate} req/s | Duration={DURATION_SEC}s")
                stop_event = threading.Event()
                t_host = threading.Thread(target=profile_host_cpu, args=(stop_event, host_csv), daemon=True)
                t_pods = threading.Thread(target=profile_pod_metrics, args=(stop_event, pod_csv), daemon=True)
                t_host.start()
                t_pods.start()

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
                stop_event.set()
                t_host.join(timeout=3)
                t_pods.join(timeout=3)

                combined_output = proc.stdout + "\n" + proc.stderr
                with open(raw_txt, "w", encoding="utf-8") as rf:
                    rf.write(combined_output)

                if proc.returncode != 0:
                    raise RuntimeError(f"httperf failed for {tag} (exit {proc.returncode}):\n{combined_output}")

                actual_rate, avg_resp_ms, ok_2xx, total_errors = parse_httperf_output(combined_output)
                summary_writer.writerow([replicas, rate, actual_rate, avg_resp_ms, ok_2xx, total_errors])
                sf.flush()
                print(
                    f"      -> Actual Rate: {actual_rate} req/s | Avg Response: {avg_resp_ms} ms | "
                    f"2xx: {ok_2xx} | Errors: {total_errors}"
                )
                time.sleep(10)


if __name__ == "__main__":
    main()
