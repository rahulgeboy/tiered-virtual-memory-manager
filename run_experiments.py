"""Automated experimental evaluation runner across tiered VM configurations."""

from __future__ import annotations

import os
# Configure headless matplotlib
os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")

import argparse
import sys
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd

from analysis.metrics import MetricsCalculator, SimulationMetrics
from analysis.plots import (
    plot_algorithm_comparison,
    plot_baseline_vs_tiered,
    plot_content_type_study,
    plot_effective_capacity,
    plot_pool_size_sweep,
    plot_threshold_sweep,
    plot_tier_occupancy_over_time,
)
from config import ContentType, SimulationConfig, WorkloadPattern
from core.compression import CompressionEngine
from core.memory_manager import BaselineManager, TieredManager
from workloads.access_patterns import WorkloadGenerator
from workloads.content_generator import PageContentGenerator


def ensure_results_dir(base_dir: Path) -> Path:
    """Ensure output results directory exists."""
    results_dir = base_dir / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    return results_dir


def run_experiment_1_baseline_vs_tiered(
    results_dir: Path,
    num_accesses: int = 1500,
    seed: int = 42,
) -> pd.DataFrame:
    """Experiment 1: Baseline vs Tiered across all workloads and content profiles."""
    print("Running Experiment 1: Baseline vs Tiered across Workloads & Content Profiles...")
    wg = WorkloadGenerator(seed=seed)
    config = SimulationConfig(
        page_size=4096,
        dram_frames=64,
        compressed_pool_bytes=64 * 4096,
        virtual_address_space=256,
        random_seed=seed,
    )

    workloads = [
        WorkloadPattern.SEQUENTIAL,
        WorkloadPattern.LOOPING,
        WorkloadPattern.ZIPF,
        WorkloadPattern.UNIFORM,
        WorkloadPattern.PHASE_SHIFTING,
    ]

    records = []

    for pattern in workloads:
        trace = wg.generate(
            pattern=pattern,
            num_accesses=num_accesses,
            virtual_address_space=config.virtual_address_space,
            write_ratio=0.20,
            dram_frames=config.dram_frames,
        )

        for content_name, profile in [
            ("Text-Like", ContentType.TEXT_LIKE),
            ("Mixed", None),
            ("Incompressible-Random", ContentType.RANDOM),
        ]:
            # Run Baseline (2-tier)
            b_mgr = BaselineManager(config, content_profile=profile)
            b_mgr.run_trace(trace)
            b_metrics = MetricsCalculator.compute(b_mgr, name="Baseline")

            # Run Tiered (3-tier)
            t_mgr = TieredManager(config, content_profile=profile)
            t_mgr.run_trace(trace)
            t_metrics = MetricsCalculator.compute(t_mgr, name="Tiered")
            t_compared = MetricsCalculator.compare(b_metrics, t_metrics)

            records.append({
                "workload": pattern.value,
                "content_profile": content_name,
                "manager": "Baseline",
                "amat_ns": b_metrics.amat_ns,
                "dram_hits": b_metrics.dram_hits,
                "minor_faults": b_metrics.minor_faults,
                "major_faults": b_metrics.major_faults,
                "cold_faults": b_metrics.cold_faults,
                "hit_ratio": b_metrics.hit_ratio,
                "speedup": 1.0,
            })
            records.append({
                "workload": pattern.value,
                "content_profile": content_name,
                "manager": "Tiered",
                "amat_ns": t_metrics.amat_ns,
                "dram_hits": t_metrics.dram_hits,
                "minor_faults": t_metrics.minor_faults,
                "major_faults": t_metrics.major_faults,
                "cold_faults": t_metrics.cold_faults,
                "hit_ratio": t_metrics.hit_ratio,
                "speedup": t_compared.speedup_vs_baseline,
            })

    df = pd.DataFrame(records)
    csv_path = results_dir / "exp1_baseline_vs_tiered.csv"
    df.to_csv(csv_path, index=False)

    # Plot for Text-Like and Mixed profiles
    df_text = df[df["content_profile"] == "Text-Like"]
    plot_baseline_vs_tiered(
        df_text,
        results_dir / "exp1_baseline_vs_tiered_text.png",
        title="Baseline vs Tiered AMAT (Compressible Text Data)",
    )

    df_mixed = df[df["content_profile"] == "Mixed"]
    plot_baseline_vs_tiered(
        df_mixed,
        results_dir / "exp1_baseline_vs_tiered_mixed.png",
        title="Baseline vs Tiered AMAT (Realistic Mixed Data)",
    )
    print(f"  Exp 1 completed. Saved to {csv_path}")
    return df


def run_experiment_2_pool_size_sweep(
    results_dir: Path,
    num_accesses: int = 1500,
    seed: int = 42,
) -> pd.DataFrame:
    """Experiment 2: Compressed-pool-size sweep (0, 8, 16, 32, 64, 128 pages equivalent)."""
    print("Running Experiment 2: Compressed Pool Size Sweep...")
    wg = WorkloadGenerator(seed=seed)
    trace = wg.generate(
        pattern=WorkloadPattern.ZIPF,
        num_accesses=num_accesses,
        virtual_address_space=256,
        write_ratio=0.20,
        dram_frames=64,
    )

    pool_pages_list = [0, 8, 16, 32, 64, 128]
    records = []

    # Baseline AMAT for reference
    base_cfg = SimulationConfig(page_size=4096, dram_frames=64, virtual_address_space=256, random_seed=seed)
    b_mgr = BaselineManager(base_cfg, content_profile=ContentType.TEXT_LIKE)
    b_mgr.run_trace(trace)
    b_amat = MetricsCalculator.compute(b_mgr).amat_ns

    for pages in pool_pages_list:
        cfg = SimulationConfig(
            page_size=4096,
            dram_frames=64,
            compressed_pool_bytes=pages * 4096,
            virtual_address_space=256,
            random_seed=seed,
        )
        t_mgr = TieredManager(cfg, content_profile=ContentType.TEXT_LIKE)
        t_mgr.run_trace(trace)
        t_metrics = MetricsCalculator.compute(t_mgr)

        records.append({
            "pool_pages": pages,
            "pool_bytes": pages * 4096,
            "amat_ns": t_metrics.amat_ns,
            "baseline_amat_ns": b_amat,
            "dram_hits": t_metrics.dram_hits,
            "minor_faults": t_metrics.minor_faults,
            "major_faults": t_metrics.major_faults,
            "speedup": b_amat / t_metrics.amat_ns if t_metrics.amat_ns > 0 else 1.0,
            "final_compressed_pages": t_metrics.final_compressed_pages,
            "pool_bytes_used": t_metrics.compressed_pool_bytes_used,
        })

    df = pd.DataFrame(records)
    csv_path = results_dir / "exp2_pool_size_sweep.csv"
    df.to_csv(csv_path, index=False)
    plot_pool_size_sweep(
        df,
        results_dir / "exp2_pool_size_sweep.png",
        title="Impact of Compressed Pool Size on AMAT (Zipf Workload)",
    )
    print(f"  Exp 2 completed. Saved to {csv_path}")
    return df


def run_experiment_3_content_types(results_dir: Path, seed: int = 42) -> pd.DataFrame:
    """Experiment 3: Compressibility and CPU duration per synthetic content type."""
    print("Running Experiment 3: Content-Type Compressibility & CPU Study...")
    gen = PageContentGenerator(page_size=4096, seed=seed)
    engine = CompressionEngine(algorithm="zlib", level=6)

    types = [
        ContentType.ZERO,
        ContentType.TEXT_LIKE,
        ContentType.STRUCTURED,
        ContentType.RANDOM,
    ]

    records = []
    for ctype in types:
        ratios = []
        comp_times = []
        decomp_times = []

        # Sample across 30 distinct virtual pages to compute robust averages
        for vpn in range(30):
            page_bytes = gen.generate_page(ctype, vpn=vpn)
            comp_res = engine.compress(page_bytes)
            decomp_res = engine.decompress(comp_res.compressed_data)

            ratios.append(comp_res.compression_ratio)
            comp_times.append(comp_res.compression_time_ns)
            decomp_times.append(decomp_res.decompression_time_ns)

        records.append({
            "content_type": ctype.value,
            "compression_ratio": float(pd.Series(ratios).mean()),
            "space_saving_pct": (1.0 - float(pd.Series(ratios).mean())) * 100.0,
            "compress_time_ns": float(pd.Series(comp_times).mean()),
            "decompress_time_ns": float(pd.Series(decomp_times).mean()),
        })

    df = pd.DataFrame(records)
    csv_path = results_dir / "exp3_content_types.csv"
    df.to_csv(csv_path, index=False)
    plot_content_type_study(
        df,
        results_dir / "exp3_content_types.png",
        title="Page Compressibility & CPU Latency by Data Type",
    )
    print(f"  Exp 3 completed. Saved to {csv_path}")
    return df


def run_experiment_4_compression_algorithms(results_dir: Path, seed: int = 42) -> pd.DataFrame:
    """Experiment 4: Compression algorithms comparison (zlib levels 1/6/9 vs lzma)."""
    print("Running Experiment 4: Compression Algorithm Comparison...")
    gen = PageContentGenerator(page_size=4096, seed=seed)
    # Use realistic mixed text-like payload
    test_pages = [gen.generate_page(ContentType.TEXT_LIKE, vpn=i) for i in range(20)]

    configs = [
        ("zlib", 1),
        ("zlib", 6),
        ("zlib", 9),
        ("lzma", 1),
        ("lzma", 6),
    ]

    records = []
    for algo, lvl in configs:
        engine = CompressionEngine(algorithm=algo, level=lvl)
        ratios = []
        comp_times = []
        decomp_times = []

        for p in test_pages:
            res = engine.compress(p)
            decomp = engine.decompress(res.compressed_data)
            ratios.append(res.compression_ratio)
            comp_times.append(res.compression_time_ns)
            decomp_times.append(decomp.decompression_time_ns)

        records.append({
            "algorithm": algo,
            "level": lvl,
            "compression_ratio": float(pd.Series(ratios).mean()),
            "space_saving_pct": (1.0 - float(pd.Series(ratios).mean())) * 100.0,
            "compress_time_ns": float(pd.Series(comp_times).mean()),
            "decompress_time_ns": float(pd.Series(decomp_times).mean()),
        })

    df = pd.DataFrame(records)
    csv_path = results_dir / "exp4_algorithms.csv"
    df.to_csv(csv_path, index=False)
    plot_algorithm_comparison(
        df,
        results_dir / "exp4_algorithms.png",
        title="Algorithm Comparison: Ratio vs CPU Latency",
    )
    print(f"  Exp 4 completed. Saved to {csv_path}")
    return df


def run_experiment_5_skip_threshold_sweep(
    results_dir: Path,
    num_accesses: int = 1500,
    seed: int = 42,
) -> pd.DataFrame:
    """Experiment 5: Compress-or-skip threshold sensitivity sweep (0.50 to 1.00)."""
    print("Running Experiment 5: Compress-or-Skip Threshold Sweep...")
    wg = WorkloadGenerator(seed=seed)
    trace = wg.generate(
        pattern=WorkloadPattern.ZIPF,
        num_accesses=num_accesses,
        virtual_address_space=256,
        write_ratio=0.20,
        dram_frames=64,
    )

    thresholds = [0.50, 0.60, 0.70, 0.75, 0.80, 0.90, 1.00]
    records = []

    for th in thresholds:
        cfg = SimulationConfig(
            page_size=4096,
            dram_frames=64,
            compressed_pool_bytes=64 * 4096,
            virtual_address_space=256,
            compress_skip_threshold=th,
            random_seed=seed,
        )
        mgr = TieredManager(cfg, content_profile=None)  # Mixed profile
        mgr.run_trace(trace)
        metrics = MetricsCalculator.compute(mgr)

        records.append({
            "threshold": th,
            "amat_ns": metrics.amat_ns,
            "dram_hits": metrics.dram_hits,
            "minor_faults": metrics.minor_faults,
            "major_faults": metrics.major_faults,
            "final_compressed_pages": metrics.final_compressed_pages,
            "compressed_pool_bytes_used": metrics.compressed_pool_bytes_used,
        })

    df = pd.DataFrame(records)
    csv_path = results_dir / "exp5_threshold_sweep.csv"
    df.to_csv(csv_path, index=False)
    plot_threshold_sweep(
        df,
        results_dir / "exp5_threshold_sweep.png",
        title="Compress-or-Skip Threshold Sensitivity (Mixed Profile)",
    )
    print(f"  Exp 5 completed. Saved to {csv_path}")
    return df


def run_experiment_6_effective_capacity(
    results_dir: Path,
    num_accesses: int = 1500,
    seed: int = 42,
) -> pd.DataFrame:
    """Experiment 6: Effective memory capacity expansion vs DRAM_FRAMES alone."""
    print("Running Experiment 6: Effective Memory Capacity Expansion...")
    wg = WorkloadGenerator(seed=seed)
    # Sequential scan across address space to populate memory hierarchy
    trace = wg.generate_sequential(
        num_accesses=num_accesses,
        virtual_address_space=256,
        write_ratio=0.10,
    )

    pool_pages_list = [0, 16, 32, 64, 96, 128]
    records = []

    for pool_p in pool_pages_list:
        cfg = SimulationConfig(
            page_size=4096,
            dram_frames=64,
            compressed_pool_bytes=pool_p * 4096,
            virtual_address_space=256,
            random_seed=seed,
        )
        mgr = TieredManager(cfg, content_profile=ContentType.TEXT_LIKE)
        mgr.run_trace(trace)
        metrics = MetricsCalculator.compute(mgr)

        records.append({
            "pool_pages": pool_p,
            "dram_frames": 64,
            "effective_capacity_pages": metrics.effective_capacity_pages,
            "capacity_gain_pct": metrics.effective_capacity_gain_pct,
            "final_compressed_pages": metrics.final_compressed_pages,
            "pool_bytes_used": metrics.compressed_pool_bytes_used,
            "swap_pages": metrics.final_swap_pages,
        })

    df = pd.DataFrame(records)
    csv_path = results_dir / "exp6_effective_capacity.csv"
    df.to_csv(csv_path, index=False)
    plot_effective_capacity(
        df,
        results_dir / "exp6_effective_capacity.png",
        title="Effective In-Memory Capacity Expansion (Text Profile)",
    )

    # Also generate a sample tier occupancy over time plot from the last manager run
    log_df = MetricsCalculator.log_to_dataframe(mgr.access_log)
    plot_tier_occupancy_over_time(
        log_df,
        results_dir / "sample_tier_occupancy_over_time.png",
        title="Tier Occupancy Dynamic Trajectory (Sequential Trace)",
    )

    print(f"  Exp 6 completed. Saved to {csv_path}")
    return df


def main() -> None:
    """CLI entry point for running all experimental suites."""
    parser = argparse.ArgumentParser(
        description="Run comprehensive virtual memory manager benchmark experiments."
    )
    parser.add_argument(
        "--num-accesses",
        type=int,
        default=1500,
        help="Number of memory accesses per workload run (default: 1500)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for deterministic workloads and data (default: 42)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="results",
        help="Directory to save generated CSVs and PNG graphs (default: results)",
    )
    args = parser.parse_args()

    results_dir = Path(args.output_dir)
    results_dir.mkdir(parents=True, exist_ok=True)

    print(f"===========================================================")
    print(f"Starting OS Virtual Memory Benchmark Suite")
    print(f"Results Directory: {results_dir.resolve()}")
    print(f"Accesses per run:  {args.num_accesses}")
    print(f"Reproducible Seed: {args.seed}")
    print(f"===========================================================\n")

    run_experiment_1_baseline_vs_tiered(results_dir, num_accesses=args.num_accesses, seed=args.seed)
    run_experiment_2_pool_size_sweep(results_dir, num_accesses=args.num_accesses, seed=args.seed)
    run_experiment_3_content_types(results_dir, seed=args.seed)
    run_experiment_4_compression_algorithms(results_dir, seed=args.seed)
    run_experiment_5_skip_threshold_sweep(results_dir, num_accesses=args.num_accesses, seed=args.seed)
    run_experiment_6_effective_capacity(results_dir, num_accesses=args.num_accesses, seed=args.seed)

    print(f"\n===========================================================")
    print(f"All 6 experiments completed successfully!")
    print(f"Generated CSV data and PNG figures are in: {results_dir.resolve()}")
    print(f"===========================================================")


if __name__ == "__main__":
    main()
