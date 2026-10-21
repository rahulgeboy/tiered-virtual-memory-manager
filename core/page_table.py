"""Page table implementation and page table entries (PTE) tracking memory tier states."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from config import ContentType, Tier


@dataclass
class PageTableEntry:
    """Represents an entry in the virtual page table.

    OS Concept:
    Each process has a page table where each entry (PTE) maps a virtual page
    number (VPN) to its current physical state. In our 3-tier hierarchy, the
    tier indicates whether the page is resident in fast physical memory (DRAM),
    stored in the compressed in-memory pool (Tier 1), paged out to SSD swap
    (Tier 2), or not yet allocated (UNMAPPED).
    """

    vpn: int
    tier: Tier = Tier.UNMAPPED
    dirty: bool = False
    last_access_time: int = 0
    access_count: int = 0
    compressed_size: int = 0
    content_type: Optional[ContentType] = None
    # Indicates whether swap holds an exact, unmodified copy of page content
    # (used to avoid redundant SSD writes on demotion if page has not been written to)
    swap_clean: bool = False

    def mark_access(self, time_step: int, is_write: bool = False) -> None:
        """Update access statistics and dirty bit."""
        self.last_access_time = time_step
        self.access_count += 1
        if is_write:
            self.dirty = True
            self.swap_clean = False  # Modifying content invalidates swap copy


class PageTable:
    """Manages the virtual address space page table entries."""

    def __init__(self, virtual_address_space: int) -> None:
        """Initialize page table with unmapped pages.

        Args:
            virtual_address_space: Total number of virtual pages.
        """
        if virtual_address_space <= 0:
            raise ValueError(
                f"virtual_address_space must be positive, got {virtual_address_space}"
            )
        self.virtual_address_space = virtual_address_space
        self.entries: Dict[int, PageTableEntry] = {
            vpn: PageTableEntry(vpn=vpn) for vpn in range(virtual_address_space)
        }

    def validate_vpn(self, vpn: int) -> None:
        """Verify that a VPN is within the valid virtual address space bounds.

        Args:
            vpn: Virtual page number to validate.

        Raises:
            ValueError: If vpn is out of bounds.
        """
        if not (0 <= vpn < self.virtual_address_space):
            raise ValueError(
                f"Virtual page number {vpn} out of bounds for address space [0, {self.virtual_address_space - 1}]"
            )

    def get_entry(self, vpn: int) -> PageTableEntry:
        """Retrieve the PTE for a given VPN after bounds check.

        Args:
            vpn: Virtual page number.

        Returns:
            The corresponding PageTableEntry.
        """
        self.validate_vpn(vpn)
        return self.entries[vpn]

    def get_tier_counts(self) -> Dict[Tier, int]:
        """Return the count of pages in each tier."""
        counts = {tier: 0 for tier in Tier}
        for entry in self.entries.values():
            counts[entry.tier] += 1
        return counts

    def get_all_entries(self) -> List[PageTableEntry]:
        """Return a list of all PTEs sorted by VPN."""
        return [self.entries[i] for i in range(self.virtual_address_space)]
