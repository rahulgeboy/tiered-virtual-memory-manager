"""Main Command-Line Interface (CLI) for Tiered Virtual Memory Manager Simulator."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from analysis.metrics import MetricsCalculator, SimulationMetrics
from config import ContentType, SimulationConfig, WorkloadPattern
from core.memory_manager import BaselineManager, MemoryManager, TieredManager
from workloads.access_patterns import WorkloadGenerator
from workloads.content_generator import PageContentGenerator


def format_table(rows: List[List[str]], headers: List[str]) -> str:
    """Format tabular data into a clean ASCII table."""
    col_widths = [len(h) for h in headers]
    for row in rows:
        for idx, val in enumerate(row):
            col_widths[idx] = max(col_widths[idx], len(str(val)))

    sep = "+-" + "-+-".join("-" * w for w in col_widths) + "-+"
    header_str = "| " + " | ".join(h.ljust(col_widths[i]) for i, h in enumerate(headers)) + " |"

    lines = [sep, header_str, sep]
    for row in rows:
        lines.append(
            "| " + " | ".join(str(val).ljust(col_widths[i]) for i, val in enumerate(row)) + " |"
        )
    lines.append(sep)
    return "\n".join(lines)


def print_simulation_report(
    metrics: SimulationMetrics,
    baseline_metrics: Optional[SimulationMetrics] = None,
) -> None:
    """Print an attractive summary report of simulation results."""
    print("\n" + "=" * 65)
    print(f"  VIRTUAL MEMORY SIMULATION RESULTS: {metrics.manager_name.upper()}")
    print("=" * 65)

    summary_rows = [
        ["Total Memory Accesses", f"{metrics.total_accesses:,}"],
        ["DRAM Hits (Tier 0)", f"{metrics.dram_hits:,} ({metrics.hit_ratio * 100:.2f}%)"],
        ["Minor Faults (Tier 1 Compressed)", f"{metrics.minor_faults:,} ({metrics.minor_fault_ratio * 100:.2f}%)"],
        ["Major Faults (Tier 2 SSD Swap)", f"{metrics.major_faults:,} ({metrics.major_fault_ratio * 100:.2f}%)"],
        ["Cold Faults (First-Touch Allocation)", f"{metrics.cold_faults:,} ({metrics.cold_fault_ratio * 100:.2f}%)"],
        ["Total Page Fault Ratio", f"{metrics.total_fault_ratio * 100:.2f}%"],
        ["Average Memory Access Time (AMAT)", f"{metrics.amat_ns:,.1f} ns"],
        ["Total Simulated Execution Latency", f"{metrics.total_simulated_time_ns / 1_000_000:,.3f} ms"],
        ["Effective In-Memory Capacity", f"{metrics.effective_capacity_pages} pages (+{metrics.effective_capacity_gain_pct:.1f}%)"],
        ["Compressed Pool Bytes In Use", f"{metrics.compressed_pool_bytes_used:,} bytes"],
        ["Average Space Saving", f"{metrics.avg_space_saving_pct:.2f}%"],
    ]

    if baseline_metrics is not None and baseline_metrics.amat_ns > 0:
        speedup = baseline_metrics.amat_ns / metrics.amat_ns
        summary_rows.append(["Speedup vs Baseline (AMAT)", f"{speedup:.2f}x faster"])

    print(format_table(summary_rows, ["Metric", "Observed Value"]))
    print()


def run_single_simulation(args: argparse.Namespace) -> None:
    """Execute a single virtual memory management simulation run."""
    try:
        # Load or construct config
        if args.config:
            cfg_path = Path(args.config)
            if not cfg_path.exists():
                print(f"Error: Config file '{args.config}' not found.", file=sys.stderr)
                sys.exit(1)
            config = SimulationConfig.from_json(cfg_path)
        else:
            pool_bytes = args.pool_pages * 4096
            config = SimulationConfig(
                page_size=4096,
                dram_frames=args.dram_frames,
                compressed_pool_bytes=pool_bytes,
                virtual_address_space=args.virtual_pages,
                compress_skip_threshold=args.threshold,
                compression_algorithm=args.algorithm,
                compression_level=args.compression_level,
                fixed_cost_mode=args.fixed_cost,
                random_seed=args.seed,
            )

        config.validate()

    except (ValueError, json.JSONDecodeError) as e:
        print(f"Configuration Error: {e}", file=sys.stderr)
        sys.exit(1)

    # Determine workload pattern
    pattern_map = {
        "sequential": WorkloadPattern.SEQUENTIAL,
        "looping": WorkloadPattern.LOOPING,
        "zipf": WorkloadPattern.ZIPF,
        "uniform": WorkloadPattern.UNIFORM,
        "phase_shifting": WorkloadPattern.PHASE_SHIFTING,
    }
    pattern = pattern_map.get(args.workload.lower())
    if pattern is None:
        print(f"Error: Invalid workload '{args.workload}'. Choose from {list(pattern_map.keys())}", file=sys.stderr)
        sys.exit(1)

    # Determine content profile
    content_map = {
        "text": ContentType.TEXT_LIKE,
        "zero": ContentType.ZERO,
        "structured": ContentType.STRUCTURED,
        "random": ContentType.RANDOM,
    }
    if args.content.lower() == "mixed":
        content_profile = None  # Mixed distribution
    else:
        ctype = content_map.get(args.content.lower())
        if ctype is None:
            print(f"Error: Invalid content type '{args.content}'. Choose from {list(content_map.keys()) + ['mixed']}", file=sys.stderr)
            sys.exit(1)
        content_profile = ctype

    if args.accesses <= 0:
        print(f"Error: --accesses must be positive, got {args.accesses}", file=sys.stderr)
        sys.exit(1)

    # Generate workload access trace
    wg = WorkloadGenerator(seed=config.random_seed)
    trace = wg.generate(
        pattern=pattern,
        num_accesses=args.accesses,
        virtual_address_space=config.virtual_address_space,
        write_ratio=args.write_ratio,
        dram_frames=config.dram_frames,
    )

    if not trace:
        print("Error: Workload access trace is empty.", file=sys.stderr)
        sys.exit(1)

    # If --compare is passed or system == "all", run both Baseline and Tiered
    if args.compare:
        print("\n--> Simulating Baseline (DRAM + SSD Swap)...")
        b_mgr = BaselineManager(config, content_profile=content_profile)
        b_mgr.run_trace(trace)
        b_mgr.assert_invariants()
        b_metrics = MetricsCalculator.compute(b_mgr, name="Baseline (2-Tier)")

        print("--> Simulating Tiered (DRAM + Compressed RAM + SSD Swap)...")
        t_mgr = TieredManager(config, content_profile=content_profile)
        t_mgr.run_trace(trace)
        t_mgr.assert_invariants()
        t_metrics = MetricsCalculator.compute(t_mgr, name="Tiered (3-Tier)")

        print_simulation_report(b_metrics)
        print_simulation_report(t_metrics, baseline_metrics=b_metrics)

        # Comparative summary
        speedup = b_metrics.amat_ns / t_metrics.amat_ns if t_metrics.amat_ns > 0 else 1.0
        print(f"Comparison Result: Tiered architecture provides a {speedup:.2f}x speedup over Baseline!")

        if args.export_csv:
            t_log = MetricsCalculator.log_to_dataframe(t_mgr.access_log)
            t_log.to_csv(args.export_csv, index=False)
            print(f"Exported Tiered access log to {args.export_csv}")

    else:
        system_lower = args.system.lower()
        if system_lower == "baseline":
            mgr: MemoryManager = BaselineManager(config, content_profile=content_profile)
        elif system_lower in ("tiered", "zswap"):
            mgr = TieredManager(config, content_profile=content_profile)
        else:
            print(f"Error: Unsupported system '{args.system}'. Use 'baseline' or 'tiered'.", file=sys.stderr)
            sys.exit(1)

        print(f"\n--> Running simulation with {args.accesses} accesses ({args.system.capitalize()})...")
        mgr.run_trace(trace)
        mgr.assert_invariants()
        metrics = MetricsCalculator.compute(mgr)
        print_simulation_report(metrics)

        if args.export_csv:
            log_df = MetricsCalculator.log_to_dataframe(mgr.access_log)
            log_df.to_csv(args.export_csv, index=False)
            print(f"Exported access log to {args.export_csv}")


def main() -> None:
    """CLI root command parser."""
    parser = argparse.ArgumentParser(
        description="Tiered Virtual Memory Manager Simulator (DRAM + Compressed RAM + SSD Swap)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    subparsers = parser.add_subparsers(dest="command", help="Operational mode")

    # Subcommand: simulate
    sim_parser = subparsers.add_parser("simulate", help="Run a single simulation or comparative test")
    sim_parser.add_argument(
        "--system",
        type=str,
        default="tiered",
        choices=["tiered", "baseline"],
        help="Memory hierarchy management system to simulate",
    )
    sim_parser.add_argument(
        "--compare",
        action="store_true",
        help="Simulate both Baseline and Tiered side-by-side on the exact same workload",
    )
    sim_parser.add_argument(
        "--workload",
        type=str,
        default="zipf",
        choices=["sequential", "looping", "zipf", "uniform", "phase_shifting"],
        help="Access pattern trace profile",
    )
    sim_parser.add_argument(
        "--content",
        type=str,
        default="mixed",
        choices=["mixed", "text", "zero", "structured", "random"],
        help="Page data compressibility profile",
    )
    sim_parser.add_argument(
        "--accesses",
        type=int,
        default=1000,
        help="Total memory references to execute",
    )
    sim_parser.add_argument(
        "--dram-frames",
        type=int,
        default=64,
        help="Number of physical frames available in DRAM (Tier 0)",
    )
    sim_parser.add_argument(
        "--pool-pages",
        type=int,
        default=64,
        help="Capacity of Compressed RAM pool (Tier 1) measured in 4KB page equivalents",
    )
    sim_parser.add_argument(
        "--virtual-pages",
        type=int,
        default=256,
        help="Size of virtual address space in pages",
    )
    sim_parser.add_argument(
        "--threshold",
        type=float,
        default=0.75,
        help="Compress-or-skip threshold ratio (0.0 < threshold <= 1.0)",
    )
    sim_parser.add_argument(
        "--algorithm",
        type=str,
        default="zlib",
        choices=["zlib", "lzma"],
        help="Compression algorithm engine",
    )
    sim_parser.add_argument(
        "--compression-level",
        type=int,
        default=6,
        help="Compression level (0-9)",
    )
    sim_parser.add_argument(
        "--write-ratio",
        type=float,
        default=0.20,
        help="Fraction of accesses that are write operations",
    )
    sim_parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for reproducible results",
    )
    sim_parser.add_argument(
        "--fixed-cost",
        action="store_true",
        help="Use deterministic fixed latency for compression/decompression",
    )
    sim_parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Optional path to custom JSON configuration file",
    )
    sim_parser.add_argument(
        "--export-csv",
        type=str,
        default=None,
        help="Optional file path to export access log CSV",
    )

    # Subcommand: experiments
    exp_parser = subparsers.add_parser(
        "experiments",
        help="Run full experimental evaluation suite (generates CSVs and PNG graphs in results/)",
    )
    exp_parser.add_argument(
        "--num-accesses",
        type=int,
        default=1500,
        help="Number of accesses per workload run",
    )
    exp_parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for reproducibility",
    )
    exp_parser.add_argument(
        "--output-dir",
        type=str,
        default="results",
        help="Output directory for CSVs and PNGs",
    )

    args = parser.parse_args()

    if args.command == "simulate":
        run_single_simulation(args)
    elif args.command == "experiments":
        import run_experiments
        results_path = Path(args.output_dir)
        results_path.mkdir(parents=True, exist_ok=True)
        run_experiments.run_experiment_1_baseline_vs_tiered(results_path, args.num_accesses, args.seed)
        run_experiments.run_experiment_2_pool_size_sweep(results_path, args.num_accesses, args.seed)
        run_experiments.run_experiment_3_content_types(results_path, args.seed)
        run_experiments.run_experiment_4_compression_algorithms(results_path, args.seed)
        run_experiments.run_experiment_5_skip_threshold_sweep(results_path, args.num_accesses, args.seed)
        run_experiments.run_experiment_6_effective_capacity(results_path, args.num_accesses, args.seed)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
