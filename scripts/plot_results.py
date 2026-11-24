import os
import pandas as pd
import matplotlib.pyplot as plt

RESULTS_DIR = "results"


def plot_graph_1():
    df = pd.read_csv(os.path.join(RESULTS_DIR, "fixed_summary.csv"))
    plt.figure(figsize=(8, 5))

    for replicas in sorted(df["replicas"].unique()):
        sub = df[df["replicas"] == replicas].sort_values("target_rate")
        plt.plot(
            sub["target_rate"],
            sub["avg_response_ms"],
            marker="o",
            linewidth=2,
            label=f"{replicas} Web Replica{'s' if replicas > 1 else ''}",
        )

    plt.title("Average Response Time vs. Request Rate (Fixed Replicas)", fontsize=12, fontweight="bold")
    plt.xlabel("Target Request Rate (req/s)")
    plt.ylabel("Average Response Time (ms)")
    plt.xticks([10, 25, 50, 100, 200])
    plt.grid(True, linestyle="--", alpha=0.5)
    plt.legend()
    plt.tight_layout()
    out_path = os.path.join(RESULTS_DIR, "graph1_response_time_vs_rate.png")
    plt.savefig(out_path, dpi=300)
    plt.close()
    print(f"Saved {out_path}")


def plot_graph_2():
    df = pd.read_csv(os.path.join(RESULTS_DIR, "pod_metrics_r3_rate100.csv"))
    web_df = df[df["pod_name"].str.startswith("emi-web")].copy()
    web_df["cpu_percent_of_100m_request"] = pd.to_numeric(web_df["cpu_percent_of_100m_request"])

    plt.figure(figsize=(8, 5))
    for pod_name in sorted(web_df["pod_name"].unique()):
        sub = web_df[web_df["pod_name"] == pod_name].sort_values("elapsed_sec")
        plt.plot(
            sub["elapsed_sec"],
            sub["cpu_percent_of_100m_request"],
            marker="s",
            linewidth=2,
            label=pod_name,
        )

    plt.axhline(100, color="gray", linestyle=":", label="100% of CPU Request (100m)")
    plt.title("Per-Pod CPU Utilization Over Time (3 Replicas @ 100 req/s)", fontsize=12, fontweight="bold")
    plt.xlabel("Time (seconds)")
    plt.ylabel("CPU Utilization (% of 100m Request)")
    plt.grid(True, linestyle="--", alpha=0.5)
    plt.legend()
    plt.tight_layout()
    out_path = os.path.join(RESULTS_DIR, "graph2_pod_cpu_r3_rate100.png")
    plt.savefig(out_path, dpi=300)
    plt.close()
    print(f"Saved {out_path}")


def plot_graph_3():
    df = pd.read_csv(os.path.join(RESULTS_DIR, "hpa_timeline.csv"))
    df["elapsed_min"] = df["elapsed_sec"] / 60.0

    fig, axes = plt.subplots(3, 1, figsize=(9, 8), sharex=True)

    # Panel 1: Request Rate
    axes[0].step(df["elapsed_min"], df["target_rate"], where="post", color="#1f77b4", linewidth=2)
    axes[0].set_ylabel("Request Rate\n(req/s)")
    axes[0].set_title("HPA Autoscaling Behavior Over 10 Minutes", fontsize=12, fontweight="bold")
    axes[0].grid(True, linestyle="--", alpha=0.5)

    # Panel 2: Average CPU Utilization
    axes[1].plot(df["elapsed_min"], df["avg_cpu_percent"], marker="o", markersize=4, color="#ff7f0e", linewidth=2)
    axes[1].axhline(50, color="red", linestyle="--", linewidth=1.2, label="HPA Target (50% CPU)")
    axes[1].set_ylabel("Avg CPU\nUtilization (%)")
    axes[1].legend(loc="upper right")
    axes[1].grid(True, linestyle="--", alpha=0.5)

    # Panel 3: Number of Web Replicas
    axes[2].step(df["elapsed_min"], df["current_replicas"], where="post", color="#2ca02c", linewidth=2)
    axes[2].set_ylabel("Web Replicas")
    axes[2].set_xlabel("Time (minutes)")
    axes[2].set_yticks([1, 2, 3, 4, 5])
    axes[2].set_xlim(0, 10)
    axes[2].grid(True, linestyle="--", alpha=0.5)

    plt.tight_layout()
    out_path = os.path.join(RESULTS_DIR, "graph3_hpa_autoscaling.png")
    plt.savefig(out_path, dpi=300)
    plt.close()
    print(f"Saved {out_path}")


if __name__ == "__main__":
    plot_graph_1()
    plot_graph_2()
    plot_graph_3()
