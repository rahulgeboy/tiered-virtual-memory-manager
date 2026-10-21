"""Metrics calculation and evaluation for memory manager simulations."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional

import pandas as pd

from core.memory_manager import AccessRecord, MemoryManager


@dataclass(frozen=True)
class SimulationMetrics:
    """Summary metrics evaluating virtual memory hierarchy performance."""

    manager_name: str
    total_accesses: int
    dram_hits: int
    minor_faults: int
    major_faults: int
    cold_faults: int
    hit_ratio: float
    minor_fault_ratio: float
    major_fault_ratio: float
    cold_fault_ratio: float
    total_fault_ratio: float
    amat_ns: float
    total_simulated_time_ns: int
    avg_compression_ratio: float
    avg_space_saving_pct: float
    total_compress_time_ns: int
    total_decompress_time_ns: int
    final_dram_pages: int
    final_compressed_pages: int
    final_swap_pages: int
    compressed_pool_bytes_used: int
    effective_capacity_pages: int
    effective_capacity_gain_pct: float
    speedup_vs_baseline: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert metrics to dictionary."""
        return asdict(self)


class MetricsCalculator:
    """Computes comprehensive metrics from simulation runs and access logs."""

    @staticmethod
    def compute(manager: MemoryManager, name: Optional[str] = None) -> SimulationMetrics:
        """Calculate simulation metrics from an executed MemoryManager instance.

        Args:
            manager: Executed MemoryManager instance.
            name: Optional human-readable manager name.

        Returns:
            SimulationMetrics instance.
        """
        total = max(1, manager.time_step)
        hits = manager.dram_hits
        minor = manager.minor_faults
        major = manager.major_faults
        cold = manager.cold_faults
        total_faults = minor + major + cold

        hit_ratio = hits / total
        minor_ratio = minor / total
        major_ratio = major / total
        cold_ratio = cold / total
        fault_ratio = total_faults / total

        amat = manager.total_latency_ns / total

        raw_bytes = manager.total_uncompressed_bytes_compressed
        comp_bytes = manager.total_compressed_bytes_produced
        if raw_bytes > 0:
            avg_comp_ratio = comp_bytes / raw_bytes
            avg_space_saving = (1.0 - avg_comp_ratio) * 100.0
        else:
            avg_comp_ratio = 1.0
            avg_space_saving = 0.0

        dram_pages = manager.dram.frame_count
        compressed_pages = getattr(manager, "compressed", None).page_count if hasattr(manager, "compressed") else 0
        swap_pages = manager.swap.page_count
        pool_bytes = getattr(manager, "compressed", None).used_bytes if hasattr(manager, "compressed") else 0

        # In-memory capacity includes physical DRAM frames + pages in compressed pool
        effective_capacity = dram_pages + compressed_pages
        baseline_frames = manager.config.dram_frames
        capacity_gain_pct = (
            ((effective_capacity - baseline_frames) / baseline_frames * 100.0)
            if baseline_frames > 0
            else 0.0
        )

        manager_title = name or manager.__class__.__name__

        return SimulationMetrics(
            manager_name=manager_title,
            total_accesses=manager.time_step,
            dram_hits=hits,
            minor_faults=minor,
            major_faults=major,
            cold_faults=cold,
            hit_ratio=hit_ratio,
            minor_fault_ratio=minor_ratio,
            major_fault_ratio=major_ratio,
            cold_fault_ratio=cold_ratio,
            total_fault_ratio=fault_ratio,
            amat_ns=amat,
            total_simulated_time_ns=manager.total_latency_ns,
            avg_compression_ratio=avg_comp_ratio,
            avg_space_saving_pct=avg_space_saving,
            total_compress_time_ns=manager.total_compress_time_ns,
            total_decompress_time_ns=manager.total_decompress_time_ns,
            final_dram_pages=dram_pages,
            final_compressed_pages=compressed_pages,
            final_swap_pages=swap_pages,
            compressed_pool_bytes_used=pool_bytes,
            effective_capacity_pages=effective_capacity,
            effective_capacity_gain_pct=capacity_gain_pct,
            speedup_vs_baseline=1.0,
        )

    @staticmethod
    def compare(baseline_metrics: SimulationMetrics, tiered_metrics: SimulationMetrics) -> SimulationMetrics:
        """Compute relative speedup of tiered over baseline."""
        if tiered_metrics.amat_ns > 0:
            speedup = baseline_metrics.amat_ns / tiered_metrics.amat_ns
        else:
            speedup = 1.0

        # Create updated metrics object with speedup
        d = tiered_metrics.to_dict()
        d["speedup_vs_baseline"] = speedup
        return SimulationMetrics(**d)

    @staticmethod
    def to_dataframe(metrics_list: List[SimulationMetrics]) -> pd.DataFrame:
        """Convert a list of SimulationMetrics into a pandas DataFrame."""
        return pd.DataFrame([m.to_dict() for m in metrics_list])

    @staticmethod
    def log_to_dataframe(access_log: List[AccessRecord]) -> pd.DataFrame:
        """Convert a manager's access log into a pandas DataFrame for analysis."""
        data = []
        for r in access_log:
            data.append({
                "access_index": r.access_index,
                "vpn": r.vpn,
                "is_write": r.is_write,
                "event_type": r.event_type.value,
                "tier_before": r.tier_before.value,
                "tier_after": r.tier_after.value,
                "cost_ns": r.cost_ns,
                "dram_latency_ns": r.dram_latency_ns,
                "decompress_latency_ns": r.decompress_latency_ns,
                "ssd_read_latency_ns": r.ssd_read_latency_ns,
                "eviction_compress_latency_ns": r.eviction_compress_latency_ns,
                "eviction_ssd_write_latency_ns": r.eviction_ssd_write_latency_ns,
                "dram_pages": r.dram_pages,
                "compressed_pages": r.compressed_pages,
                "swap_pages": r.swap_pages,
                "compressed_pool_bytes": r.compressed_pool_bytes,
            })
        return pd.DataFrame(data)
