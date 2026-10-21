"""Cost and latency modeling for tiered virtual memory operations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from config import EventType, SimulationConfig


@dataclass(frozen=True)
class AccessCostBreakdown:
    """Detailed latency breakdown for an individual page access."""

    event_type: EventType
    dram_latency_ns: int
    decompress_latency_ns: int = 0
    ssd_read_latency_ns: int = 0
    eviction_compress_latency_ns: int = 0
    eviction_ssd_write_latency_ns: int = 0

    @property
    def total_cost_ns(self) -> int:
        """Total latency incurred during this access including any eviction work."""
        return (
            self.dram_latency_ns
            + self.decompress_latency_ns
            + self.ssd_read_latency_ns
            + self.eviction_compress_latency_ns
            + self.eviction_ssd_write_latency_ns
        )

    @property
    def direct_cost_ns(self) -> int:
        """Direct access latency without eviction overhead."""
        return self.dram_latency_ns + self.decompress_latency_ns + self.ssd_read_latency_ns


class LatencyCostModel:
    """Calculates operational latencies according to the simulation configuration."""

    def __init__(self, config: SimulationConfig) -> None:
        """Initialize latency model with simulation config."""
        self.config = config

    def get_dram_hit_cost(self) -> int:
        """Latency of reading/writing a page already resident in DRAM."""
        return self.config.dram_latency_ns

    def get_decompress_cost(self, measured_ns: int) -> int:
        """Decompression latency (either fixed or measured)."""
        if self.config.fixed_cost_mode:
            return self.config.fixed_decompress_latency_ns
        return max(1, measured_ns)

    def get_compress_cost(self, measured_ns: int) -> int:
        """Compression latency (either fixed or measured)."""
        if self.config.fixed_cost_mode:
            return self.config.fixed_compress_latency_ns
        return max(1, measured_ns)

    def get_ssd_read_cost(self) -> int:
        """Latency of transferring a 4KB page from SSD swap to DRAM."""
        return self.config.ssd_read_latency_ns

    def get_ssd_write_cost(self) -> int:
        """Latency of writing a 4KB page to SSD swap."""
        return self.config.ssd_write_latency_ns
