"""SSD Swap Tier (Tier 2) simulating backing disk storage."""

from __future__ import annotations

from typing import Dict, List, Optional


class SwapTier:
    """Simulates SSD disk swap space with unlimited capacity.

    OS Concept:
    Swap space acts as the lowest tier of the virtual memory hierarchy.
    Transferring pages between RAM and SSD involves high latency (typically
    100 microseconds / 100,000 ns vs 100 ns for DRAM).
    Operating systems track whether a page is 'dirty' (modified in memory)
    or 'clean' (matching the disk copy). If an uncompressed or unmodified page
    already exists on swap and has not been written to, redundant write I/O can
    be eliminated on demotion.
    """

    def __init__(self, page_size: int = 4096) -> None:
        """Initialize SSD swap tier.

        Args:
            page_size: Size of a swapped page in bytes.
        """
        self.page_size = page_size
        # Maps vpn -> raw 4096 page bytes stored on SSD
        self._storage: Dict[int, bytes] = {}
        self.total_reads: int = 0
        self.total_writes: int = 0

    @property
    def page_count(self) -> int:
        """Total pages currently stored on swap."""
        return len(self._storage)

    def contains(self, vpn: int) -> bool:
        """Check if page resides on swap."""
        return vpn in self._storage

    def read(self, vpn: int) -> bytes:
        """Read page content from SSD swap into DRAM.

        Args:
            vpn: Virtual page number.

        Returns:
            The raw 4096 page bytes.

        Raises:
            KeyError: If page is not on swap.
        """
        if vpn not in self._storage:
            raise KeyError(f"VPN {vpn} not present on SSD swap")
        self.total_reads += 1
        return self._storage[vpn]

    def write(self, vpn: int, content: bytes) -> None:
        """Write page content to SSD swap.

        Args:
            vpn: Virtual page number.
            content: Raw 4096 page bytes.

        Raises:
            ValueError: If content length does not match page_size.
        """
        if len(content) != self.page_size:
            raise ValueError(
                f"Page content size {len(content)} does not match page_size {self.page_size}"
            )
        self._storage[vpn] = content
        self.total_writes += 1

    def remove(self, vpn: int) -> Optional[bytes]:
        """Remove page from swap (e.g. if discarded or overwritten).

        Args:
            vpn: Virtual page number.

        Returns:
            The removed bytes, or None if not present.
        """
        return self._storage.pop(vpn, None)

    def get_swapped_vpns(self) -> List[int]:
        """Return list of all VPNs currently residing on swap."""
        return list(self._storage.keys())
