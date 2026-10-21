"""Workload access trace generators modeling realistic OS memory reference patterns."""

from __future__ import annotations

import random
from typing import List, Optional, Tuple

import numpy as np

from config import WorkloadPattern


class WorkloadGenerator:
    """Generates synthetic memory reference traces (vpn, is_write).

    OS Concept:
    Memory access patterns dramatically influence paging algorithm performance:
    - Sequential Scan: Streaming through a large dataset (e.g. file copying, video playback).
    - Looping: Iterating through an array slightly larger than physical memory;
      classic pathological case for LRU where hit rate collapses to 0%.
    - Zipfian / Hot-Cold: Demonstrates 80/20 temporal locality common in web servers,
      databases, and cached index lookups.
    - Uniform Random: Maximum entropy, no temporal or spatial locality.
    - Phase-Shifting: Multi-stage computation (e.g. compiler phases, batch jobs)
      where working set changes abruptly.
    """

    def __init__(self, seed: Optional[int] = 42) -> None:
        """Initialize workload generator with seed."""
        self.seed = seed

    def _determine_write(self, rng: random.Random, write_ratio: float) -> bool:
        """Probabilistically decide if an access is a write."""
        return rng.random() < write_ratio

    def generate_sequential(
        self,
        num_accesses: int,
        virtual_address_space: int,
        write_ratio: float = 0.2,
    ) -> List[Tuple[int, bool]]:
        """Generate a sequential linear scan through the address space."""
        if num_accesses <= 0 or virtual_address_space <= 0:
            raise ValueError("num_accesses and virtual_address_space must be positive")
        rng = random.Random(self.seed)
        trace = []
        for i in range(num_accesses):
            vpn = i % virtual_address_space
            trace.append((vpn, self._determine_write(rng, write_ratio)))
        return trace

    def generate_looping(
        self,
        num_accesses: int,
        working_set_size: int,
        write_ratio: float = 0.2,
    ) -> List[Tuple[int, bool]]:
        """Generate a repeated loop over a working set slightly larger than DRAM.

        Classic LRU pathology: if working set exceeds physical frames by even 1,
        every access evicts the page needed in the near future.
        """
        if num_accesses <= 0 or working_set_size <= 0:
            raise ValueError("num_accesses and working_set_size must be positive")
        rng = random.Random(self.seed)
        trace = []
        for i in range(num_accesses):
            vpn = i % working_set_size
            trace.append((vpn, self._determine_write(rng, write_ratio)))
        return trace

    def generate_zipf(
        self,
        num_accesses: int,
        virtual_address_space: int,
        write_ratio: float = 0.2,
        alpha: float = 1.2,
    ) -> List[Tuple[int, bool]]:
        """Generate power-law / Zipfian distributed accesses exhibiting high skew (hot-cold)."""
        if num_accesses <= 0 or virtual_address_space <= 0:
            raise ValueError("num_accesses and virtual_address_space must be positive")
        np_rng = np.random.default_rng(self.seed)
        py_rng = random.Random(self.seed)

        # Compute Zipf probabilities for ranks 1..N
        ranks = np.arange(1, virtual_address_space + 1, dtype=np.float64)
        weights = 1.0 / np.power(ranks, alpha)
        probabilities = weights / np.sum(weights)

        # Draw pages according to Zipf distribution
        vpns = np_rng.choice(virtual_address_space, size=num_accesses, p=probabilities)

        trace = []
        for vpn in vpns:
            trace.append((int(vpn), self._determine_write(py_rng, write_ratio)))
        return trace

    def generate_uniform(
        self,
        num_accesses: int,
        virtual_address_space: int,
        write_ratio: float = 0.2,
    ) -> List[Tuple[int, bool]]:
        """Generate uniformly distributed random memory accesses."""
        if num_accesses <= 0 or virtual_address_space <= 0:
            raise ValueError("num_accesses and virtual_address_space must be positive")
        rng = random.Random(self.seed)
        trace = []
        for _ in range(num_accesses):
            vpn = rng.randint(0, virtual_address_space - 1)
            trace.append((vpn, self._determine_write(rng, write_ratio)))
        return trace

    def generate_phase_shifting(
        self,
        num_accesses: int,
        virtual_address_space: int,
        phase_length: int = 200,
        hot_set_size: int = 16,
        write_ratio: float = 0.2,
    ) -> List[Tuple[int, bool]]:
        """Generate a trace where the active working set migrates after every phase_length accesses."""
        if num_accesses <= 0 or virtual_address_space <= 0:
            raise ValueError("num_accesses and virtual_address_space must be positive")
        rng = random.Random(self.seed)
        trace = []

        num_phases = max(1, (num_accesses + phase_length - 1) // phase_length)
        phase_offset = 0

        for i in range(num_accesses):
            if i > 0 and i % phase_length == 0:
                # Shift active window
                phase_offset = (phase_offset + hot_set_size) % max(
                    1, virtual_address_space - hot_set_size
                )

            # 85% of accesses stay within current phase hot window, 15% anywhere in address space
            if rng.random() < 0.85:
                vpn = (phase_offset + rng.randint(0, min(hot_set_size - 1, virtual_address_space - 1))) % virtual_address_space
            else:
                vpn = rng.randint(0, virtual_address_space - 1)

            trace.append((vpn, self._determine_write(rng, write_ratio)))

        return trace

    def generate(
        self,
        pattern: WorkloadPattern,
        num_accesses: int,
        virtual_address_space: int,
        write_ratio: float = 0.2,
        dram_frames: int = 64,
    ) -> List[Tuple[int, bool]]:
        """Convenience dispatcher to generate a workload by pattern enum."""
        if pattern == WorkloadPattern.SEQUENTIAL:
            return self.generate_sequential(num_accesses, virtual_address_space, write_ratio)
        elif pattern == WorkloadPattern.LOOPING:
            # Looping working set slightly exceeds DRAM frames (e.g. 1.2x)
            working_set = min(virtual_address_space, max(dram_frames + 4, int(dram_frames * 1.2)))
            return self.generate_looping(num_accesses, working_set, write_ratio)
        elif pattern == WorkloadPattern.ZIPF:
            return self.generate_zipf(num_accesses, virtual_address_space, write_ratio)
        elif pattern == WorkloadPattern.UNIFORM:
            return self.generate_uniform(num_accesses, virtual_address_space, write_ratio)
        elif pattern == WorkloadPattern.PHASE_SHIFTING:
            phase_len = max(50, num_accesses // 10)
            hot_size = max(4, dram_frames // 2)
            return self.generate_phase_shifting(
                num_accesses, virtual_address_space, phase_len, hot_size, write_ratio
            )
        else:
            raise ValueError(f"Unknown workload pattern: {pattern}")
