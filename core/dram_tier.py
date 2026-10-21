"""DRAM Tier (Tier 0) representing fast physical memory with LRU replacement."""

from __future__ import annotations

from collections import OrderedDict
from typing import Dict, List, Optional, Tuple


class DRAMTier:
    """Simulates physical RAM frames using an O(1) OrderedDict for LRU ordering.

    OS Concept:
    Physical memory is organized into fixed-size frames. When all frames are
    occupied and a new page must be brought in, the operating system selects
    a victim page using a page replacement algorithm. Least Recently Used (LRU)
    evicts the page that has not been accessed for the longest time, exploiting
    temporal locality.
    """

    def __init__(self, max_frames: int, page_size: int = 4096) -> None:
        """Initialize DRAM tier.

        Args:
            max_frames: Maximum number of physical frames available in DRAM.
            page_size: Size of each frame in bytes.
        """
        if max_frames <= 0:
            raise ValueError(f"max_frames must be positive, got {max_frames}")
        self.max_frames = max_frames
        self.page_size = page_size
        # Maps vpn -> raw uncompressed page bytes (4096 bytes)
        # OrderedDict maintains access order: oldest at beginning, most recent at end.
        self._frames: OrderedDict[int, bytes] = OrderedDict()

    @property
    def frame_count(self) -> int:
        """Number of occupied DRAM frames."""
        return len(self._frames)

    def is_full(self) -> bool:
        """True if all DRAM frames are occupied."""
        return len(self._frames) >= self.max_frames

    def contains(self, vpn: int) -> bool:
        """Check if page is resident in DRAM."""
        return vpn in self._frames

    def read(self, vpn: int) -> bytes:
        """Access a resident page in DRAM and update LRU order.

        Args:
            vpn: Virtual page number.

        Returns:
            The raw page bytes.

        Raises:
            KeyError: If vpn is not in DRAM.
        """
        if vpn not in self._frames:
            raise KeyError(f"VPN {vpn} not present in DRAM")
        self._frames.move_to_end(vpn)
        return self._frames[vpn]

    def write(self, vpn: int, content: bytes) -> None:
        """Write new content to a resident DRAM page and update LRU order.

        Args:
            vpn: Virtual page number.
            content: New page bytes.

        Raises:
            KeyError: If vpn is not in DRAM.
            ValueError: If content length does not match page_size.
        """
        if vpn not in self._frames:
            raise KeyError(f"VPN {vpn} not present in DRAM")
        if len(content) != self.page_size:
            raise ValueError(
                f"Page content size {len(content)} does not match page_size {self.page_size}"
            )
        self._frames[vpn] = content
        self._frames.move_to_end(vpn)

    def put(self, vpn: int, content: bytes) -> None:
        """Insert or update a page in DRAM.

        Note: If DRAM is full and vpn is new, caller must call evict_lru() first.

        Args:
            vpn: Virtual page number.
            content: Raw uncompressed page bytes.

        Raises:
            ValueError: If DRAM is already at capacity and adding a new VPN.
        """
        if vpn not in self._frames and self.is_full():
            raise ValueError(
                f"DRAM capacity ({self.max_frames} frames) exceeded. Eviction required first."
            )
        if len(content) != self.page_size:
            raise ValueError(
                f"Page content size {len(content)} does not match page_size {self.page_size}"
            )
        self._frames[vpn] = content
        self._frames.move_to_end(vpn)

    def evict_lru(self) -> Tuple[int, bytes]:
        """Evict the least recently used page from DRAM.

        Returns:
            Tuple of (victim_vpn, victim_bytes).

        Raises:
            KeyError: If DRAM is empty.
        """
        if not self._frames:
            raise KeyError("Cannot evict from empty DRAM")
        # popitem(last=False) pops the oldest item in O(1)
        return self._frames.popitem(last=False)

    def remove(self, vpn: int) -> bytes:
        """Explicitly remove a page from DRAM without LRU ordering.

        Args:
            vpn: Virtual page number.

        Returns:
            The raw page bytes.
        """
        return self._frames.pop(vpn)

    def get_resident_vpns(self) -> List[int]:
        """Return list of resident VPNs from least to most recently used."""
        return list(self._frames.keys())
