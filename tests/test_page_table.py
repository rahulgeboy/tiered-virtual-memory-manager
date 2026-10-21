"""Unit tests for PageTable and PageTableEntry."""

import pytest
from config import ContentType, Tier
from core.page_table import PageTable, PageTableEntry


def test_page_table_init():
    """PageTable should initialize all pages as UNMAPPED and clean."""
    pt = PageTable(virtual_address_space=64)
    assert len(pt.entries) == 64
    for vpn in range(64):
        entry = pt.get_entry(vpn)
        assert entry.vpn == vpn
        assert entry.tier == Tier.UNMAPPED
        assert entry.dirty is False
        assert entry.access_count == 0
        assert entry.last_access_time == 0
        assert entry.swap_clean is False


def test_invalid_vas_size():
    """Non-positive virtual address space must raise ValueError."""
    with pytest.raises(ValueError):
        PageTable(virtual_address_space=0)
    with pytest.raises(ValueError):
        PageTable(virtual_address_space=-5)


@pytest.mark.parametrize("invalid_vpn", [-1, 64, 100])
def test_vpn_bounds_check(invalid_vpn):
    """Accessing out-of-bounds VPN must raise ValueError."""
    pt = PageTable(virtual_address_space=64)
    with pytest.raises(ValueError, match="out of bounds"):
        pt.validate_vpn(invalid_vpn)
    with pytest.raises(ValueError, match="out of bounds"):
        pt.get_entry(invalid_vpn)


def test_pte_access_tracking():
    """mark_access should correctly increment counters and set dirty bit."""
    entry = PageTableEntry(vpn=10)
    assert entry.access_count == 0
    assert entry.dirty is False

    # Read access at timestep 1
    entry.mark_access(time_step=1, is_write=False)
    assert entry.access_count == 1
    assert entry.last_access_time == 1
    assert entry.dirty is False

    # Simulate page was swapped and clean
    entry.swap_clean = True

    # Write access at timestep 5
    entry.mark_access(time_step=5, is_write=True)
    assert entry.access_count == 2
    assert entry.last_access_time == 5
    assert entry.dirty is True
    # Writing invalidates the clean swap copy
    assert entry.swap_clean is False


def test_tier_counts():
    """PageTable should report accurate tier counts."""
    pt = PageTable(virtual_address_space=10)
    pt.get_entry(0).tier = Tier.DRAM
    pt.get_entry(1).tier = Tier.DRAM
    pt.get_entry(2).tier = Tier.COMPRESSED
    pt.get_entry(3).tier = Tier.SWAP

    counts = pt.get_tier_counts()
    assert counts[Tier.DRAM] == 2
    assert counts[Tier.COMPRESSED] == 1
    assert counts[Tier.SWAP] == 1
    assert counts[Tier.UNMAPPED] == 6
