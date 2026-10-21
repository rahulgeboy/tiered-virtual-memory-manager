"""Matplotlib plotting utilities generating publication-quality figures."""

from __future__ import annotations

import os
# Configure writable matplotlib cache directory for sandboxed and headless execution
os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")

from pathlib import Path
from typing import List, Optional

import matplotlib
matplotlib.use("Agg")  # Non-interactive headless backend
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def set_plot_style() -> None:
    """Set clean, readable aesthetics for charts."""
    plt.rcParams.update({
        "font.size": 11,
        "axes.labelsize": 12,
        "axes.titlesize": 13,
        "xtick.labelsize": 10,
        "ytick.labelsize": 10,
        "legend.fontsize": 10,
        "figure.titlesize": 14,
        "figure.autolayout": True,
        "grid.alpha": 0.3,
        "grid.linestyle": "--",
    })


def plot_baseline_vs_tiered(
    df: pd.DataFrame,
    output_path: Path | str,
    title: str = "Baseline vs Tiered: Average Memory Access Time (AMAT)",
) -> None:
    """Plot grouped bar chart comparing Baseline vs Tiered AMAT across workloads."""
    set_plot_style()
    fig, ax = plt.subplots(figsize=(10, 5.5))

    workloads = df["workload"].unique()
    x = np.arange(len(workloads))
    width = 0.35

    baseline_data = df[df["manager"] == "Baseline"]
    tiered_data = df[df["manager"] == "Tiered"]

    b_amat = [baseline_data[baseline_data["workload"] == w]["amat_ns"].values[0] for w in workloads]
    t_amat = [tiered_data[tiered_data["workload"] == w]["amat_ns"].values[0] for w in workloads]

    rects1 = ax.bar(x - width / 2, b_amat, width, label="Baseline (2-Tier: DRAM + SSD)", color="#d95f02")
    rects2 = ax.bar(x + width / 2, t_amat, width, label="Tiered (3-Tier: DRAM + Compressed + SSD)", color="#1b9e77")

    ax.set_ylabel("AMAT (nanoseconds, lower is better)")
    ax.set_xlabel("Workload Pattern")
    ax.set_title(title, fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels(workloads, rotation=15)
    ax.legend()
    ax.grid(axis="y")
    ax.set_yscale("log")  # Log scale for massive orders of magnitude difference

    # Add speedup annotations above Tiered bars
    for i, (b, t) in enumerate(zip(b_amat, t_amat)):
        if t > 0:
            speedup = b / t
            ax.annotate(
                f"{speedup:.1f}x\nspeedup",
                xy=(x[i] + width / 2, t),
                xytext=(0, 5),
                textcoords="offset points",
                ha="center",
                va="bottom",
                fontsize=9,
                fontweight="bold",
                color="#006d2c",
            )

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=300)
    plt.close(fig)


def plot_pool_size_sweep(
    df: pd.DataFrame,
    output_path: Path | str,
    title: str = "Impact of Compressed Pool Size on AMAT",
) -> None:
    """Plot line graph showing AMAT as compressed pool capacity increases."""
    set_plot_style()
    fig, ax = plt.subplots(figsize=(9, 5))

    ax.plot(
        df["pool_pages"],
        df["amat_ns"],
        marker="o",
        linewidth=2.5,
        markersize=7,
        color="#2b83ba",
        label="Tiered AMAT",
    )

    if "baseline_amat_ns" in df.columns:
        ax.axhline(
            y=df["baseline_amat_ns"].iloc[0],
            color="#d7191c",
            linestyle="--",
            linewidth=2,
            label="Baseline AMAT (No pool)",
        )

    ax.set_xlabel("Compressed Pool Capacity (Pages equivalent)")
    ax.set_ylabel("Average Memory Access Time (AMAT in ns, log scale)")
    ax.set_title(title, fontweight="bold")
    ax.set_yscale("log")
    ax.grid(True)
    ax.legend()

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=300)
    plt.close(fig)


def plot_content_type_study(
    df: pd.DataFrame,
    output_path: Path | str,
    title: str = "Compressibility & CPU Latency by Page Content Type",
) -> None:
    """Plot dual-axis bar chart showing compression ratio and CPU time across content types."""
    set_plot_style()
    fig, ax1 = plt.subplots(figsize=(9, 5))

    types = df["content_type"].values
    x = np.arange(len(types))
    width = 0.35

    ax2 = ax1.twinx()

    rects1 = ax1.bar(
        x - width / 2,
        df["compression_ratio"],
        width,
        label="Compression Ratio (Size / 4096)",
        color="#7570b3",
    )
    rects2 = ax2.bar(
        x + width / 2,
        df["compress_time_ns"] / 1000.0,
        width,
        label="Compress CPU Time (µs)",
        color="#e7298a",
    )

    # Reference line for 75% skip threshold
    ax1.axhline(
        y=0.75,
        color="red",
        linestyle=":",
        linewidth=1.8,
        label="Skip Threshold (0.75)",
    )

    ax1.set_xlabel("Synthetic Page Content Profile")
    ax1.set_ylabel("Compression Ratio (lower = higher compression)", color="#7570b3")
    ax2.set_ylabel("CPU Latency (microseconds)", color="#e7298a")
    ax1.set_title(title, fontweight="bold")
    ax1.set_xticks(x)
    ax1.set_xticklabels(types)
    ax1.set_ylim(0, 1.2)

    # Combined legend
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper left")

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=300)
    plt.close(fig)


def plot_algorithm_comparison(
    df: pd.DataFrame,
    output_path: Path | str,
    title: str = "Compression Algorithm Comparison: Space vs CPU Latency",
) -> None:
    """Plot scatter / bar chart comparing zlib levels and lzma."""
    set_plot_style()
    fig, ax = plt.subplots(figsize=(8.5, 5))

    for _, row in df.iterrows():
        ax.scatter(
            row["compress_time_ns"] / 1000.0,
            row["compression_ratio"],
            s=180,
            alpha=0.85,
            label=f"{row['algorithm']} (lvl {row['level']})",
        )
        ax.annotate(
            f"{row['algorithm']}-L{row['level']}",
            (row["compress_time_ns"] / 1000.0, row["compression_ratio"]),
            xytext=(7, 4),
            textcoords="offset points",
            fontweight="bold",
            fontsize=9,
        )

    ax.set_xlabel("Compression CPU Time (microseconds, lower is faster)")
    ax.set_ylabel("Compression Ratio (lower is better space saving)")
    ax.set_title(title, fontweight="bold")
    ax.grid(True)
    ax.set_xscale("log")

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=300)
    plt.close(fig)


def plot_threshold_sweep(
    df: pd.DataFrame,
    output_path: Path | str,
    title: str = "Sensitivity Analysis: Compress-or-Skip Threshold Sweep",
) -> None:
    """Plot AMAT vs skip threshold."""
    set_plot_style()
    fig, ax = plt.subplots(figsize=(8.5, 5))

    ax.plot(
        df["threshold"],
        df["amat_ns"],
        marker="s",
        linewidth=2.2,
        color="#0570b0",
        label="AMAT (ns)",
    )

    ax.set_xlabel("Compress-or-Skip Threshold (0.50 to 1.00)")
    ax.set_ylabel("Average Memory Access Time (AMAT in ns)")
    ax.set_title(title, fontweight="bold")
    ax.grid(True)
    ax.legend()

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=300)
    plt.close(fig)


def plot_effective_capacity(
    df: pd.DataFrame,
    output_path: Path | str,
    title: str = "Effective In-Memory Capacity Expansion via Compression",
) -> None:
    """Plot effective memory capacity and capacity gain %."""
    set_plot_style()
    fig, ax1 = plt.subplots(figsize=(9, 5))
    ax2 = ax1.twinx()

    x = df["pool_pages"].values
    ax1.plot(x, df["effective_capacity_pages"], marker="o", color="#238b45", linewidth=2.5, label="Effective Pages")
    ax1.axhline(y=df["dram_frames"].iloc[0], color="#990000", linestyle="--", label="Physical DRAM Frames")

    ax2.plot(x, df["capacity_gain_pct"], marker="^", color="#fe9929", linewidth=2, linestyle=":", label="Capacity Gain %")

    ax1.set_xlabel("Configured Compressed Pool Size (Pages equivalent)")
    ax1.set_ylabel("Total In-Memory Pages Resident", color="#238b45")
    ax2.set_ylabel("Effective Memory Gain (%)", color="#fe9929")
    ax1.set_title(title, fontweight="bold")
    ax1.grid(True)

    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper left")

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=300)
    plt.close(fig)


def plot_tier_occupancy_over_time(
    log_df: pd.DataFrame,
    output_path: Path | str,
    title: str = "Memory Hierarchy Tier Occupancy Over Time",
) -> None:
    """Plot stacked area chart of pages resident in each tier across the access trace."""
    set_plot_style()
    fig, ax = plt.subplots(figsize=(10, 5))

    x = log_df["access_index"].values
    dram = log_df["dram_pages"].values
    compressed = log_df["compressed_pages"].values
    swap = log_df["swap_pages"].values

    ax.plot(x, dram, label="DRAM (Tier 0)", color="#2ca02c", linewidth=2)
    ax.plot(x, compressed, label="Compressed RAM (Tier 1)", color="#1f77b4", linewidth=2)
    ax.plot(x, swap, label="SSD Swap (Tier 2)", color="#d62728", linewidth=2)

    ax.set_xlabel("Access Sequence Index")
    ax.set_ylabel("Page Count in Tier")
    ax.set_title(title, fontweight="bold")
    ax.grid(True)
    ax.legend(loc="upper left")

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=300)
    plt.close(fig)
