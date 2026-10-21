"""Compressed RAM Tier (Tier 1) simulating in-memory compressed page cache (zswap/zram)."""

from __future__ import annotations

from collections import OrderedDict
from typing import Dict, List, Optional, Tuple


class CompressedTier:
    """Simulates a compressed memory pool bounded strictly by BYTE capacity.

    OS Concept:
    Linux zswap and zram store evicted pages in a reserved region of RAM,
    compressed using algorithms like lz4, zlib, or zstd. Because pages have
    variable compressibility, the capacity limit is enforced in BYTES rather
    than a fixed count of page slots.
    LRU order is maintained so that cold compressed pages can be demoted to SSD swap
    when the compressed pool becomes full.
    """

    def __init__(self, capacity_bytes: int) -> None:
        """Initialize compressed tier pool.

        Args:
            capacity_bytes: Maximum pool capacity in compressed bytes.
        """
        if capacity_bytes < 0:
            raise ValueError(f"capacity_bytes cannot be negative, got {capacity_bytes}")
        self.capacity_bytes = capacity_bytes
        self.used_bytes = 0
        # Maps vpn -> compressed bytes. OrderedDict preserves LRU order.
        self._pool: OrderedDict[int, bytes] = OrderedDict()

    @property
    def page_count(self) -> int:
        """Number of pages currently stored in the compressed pool."""
        return len(self._pool)

    @property
    def free_bytes(self) -> int:
        """Available byte headroom in the compressed pool."""
        return max(0, self.capacity_bytes - self.used_bytes)

    @property
    def utilization(self) -> float:
        """Fraction of byte capacity currently used (0.0 to 1.0)."""
        if self.capacity_bytes == 0:
            return 1.0
        return self.used_bytes / self.capacity_bytes

    def contains(self, vpn: int) -> bool:
        """Check if a page is stored in the compressed tier."""
        return vpn in self._pool

    def get_compressed_size(self, vpn: int) -> int:
        """Return the compressed size of a stored page."""
        if vpn not in self._pool:
            raise KeyError(f"VPN {vpn} not in compressed pool")
        return len(self._pool[vpn])

    def can_fit(self, size_bytes: int) -> bool:
        """Check if the given compressed size can fit in remaining headroom."""
        return self.free_bytes >= size_bytes

    def has_total_capacity(self, size_bytes: int) -> bool:
        """Check if the size could ever fit in the total pool capacity."""
        return self.capacity_bytes >= size_bytes

    def put(self, vpn: int, compressed_data: bytes) -> None:
        """Store compressed page bytes into the pool.

        Caller is responsible for demoting LRU pages first if can_fit() is False.

        Args:
            vpn: Virtual page number.
            compressed_data: Compressed page bytes.

        Raises:
            ValueError: If compressed bytes exceed available pool headroom.
        """
        new_size = len(compressed_data)
        old_size = len(self._pool[vpn]) if vpn in self._pool else 0
        net_increase = new_size - old_size

        if net_increase > self.free_bytes:
            raise ValueError(
                f"Compressed pool overflow: requires {net_increase} bytes, "
                f"but only {self.free_bytes} bytes free out of {self.capacity_bytes} bytes."
            )

        self._pool[vpn] = compressed_data
        self._pool.move_to_end(vpn)
        self.used_bytes += net_increase

    def remove(self, vpn: int) -> bytes:
        """Remove a compressed page from the pool (e.g. upon promotion to DRAM).

        Args:
            vpn: Virtual page number.

        Returns:
            The compressed bytes that were stored.

        Raises:
            KeyError: If vpn is not in the pool.
        """
        if vpn not in self._pool:
            raise KeyError(f"VPN {vpn} not present in compressed pool")
        data = self._pool.pop(vpn)
        self.used_bytes -= len(data)
        return data

    def evict_lru(self) -> Tuple[int, bytes]:
        """Evict the least recently used compressed page for demotion to SSD.

        Returns:
            Tuple of (victim_vpn, victim_compressed_bytes).

        Raises:
            KeyError: If the pool is empty.
        """
        if not self._pool:
            raise KeyError("Cannot evict from empty compressed pool")
        victim_vpn, victim_data = self._pool.popitem(last=False)
        self.used_bytes -= len(victim_data)
        return victim_vpn, victim_data

    def set_capacity(self, new_capacity_bytes: int) -> List[Tuple[int, bytes]]:
        """Resize the compressed pool capacity dynamically.

        If the new capacity is lower than current usage, evicts LRU pages
        until current usage <= new_capacity_bytes.

        Args:
            new_capacity_bytes: New maximum capacity in bytes.

        Returns:
            List of evicted (vpn, compressed_bytes) that must be demoted to SSD.
        """
        if new_capacity_bytes < 0:
            raise ValueError(f"capacity_bytes cannot be negative, got {new_capacity_bytes}")
        self.capacity_bytes = new_capacity_bytes
        evicted = []
        while self.used_bytes > self.capacity_bytes and self._pool:
            evicted.append(self.evict_lru())
        return evicted

    def get_resident_vpns(self) -> List[int]:
        """Return list of resident VPNs from least to most recently used."""
        return list(self._pool.keys())
