"""Unit tests for storage tiers (DRAM, Compressed RAM, SSD Swap)."""

import pytest
from core.dram_tier import DRAMTier
from core.compressed_tier import CompressedTier
from core.swap_tier import SwapTier


def test_dram_tier_lru():
    """DRAM tier must enforce max_frames and pop true LRU victim."""
    dram = DRAMTier(max_frames=3, page_size=10)
    p0 = b"0" * 10
    p1 = b"1" * 10
    p2 = b"2" * 10
    p3 = b"3" * 10

    dram.put(0, p0)
    dram.put(1, p1)
    dram.put(2, p2)
    assert dram.is_full()
    assert dram.frame_count == 3

    # Accessing page 0 updates its LRU position (makes it most recent)
    dram.read(0)

    # Now LRU order is: 1 (oldest), 2, 0 (newest)
    victim_vpn, victim_bytes = dram.evict_lru()
    assert victim_vpn == 1
    assert victim_bytes == p1
    assert not dram.is_full()

    # Insert page 3
    dram.put(3, p3)
    assert dram.is_full()

    # Next LRU victim should be 2
    victim2_vpn, _ = dram.evict_lru()
    assert victim2_vpn == 2


def test_dram_capacity_enforcement():
    """Inserting into full DRAM without evicting must raise ValueError."""
    dram = DRAMTier(max_frames=2, page_size=10)
    dram.put(0, b"a" * 10)
    dram.put(1, b"b" * 10)

    with pytest.raises(ValueError, match="DRAM capacity.*exceeded"):
        dram.put(2, b"c" * 10)


def test_compressed_tier_byte_capacity():
    """Compressed pool must track capacity in bytes and reject overflows."""
    pool = CompressedTier(capacity_bytes=100)
    assert pool.capacity_bytes == 100
    assert pool.free_bytes == 100
    assert pool.used_bytes == 0

    c1 = b"x" * 40
    c2 = b"y" * 50
    c3 = b"z" * 20

    pool.put(1, c1)
    assert pool.used_bytes == 40
    assert pool.free_bytes == 60

    pool.put(2, c2)
    assert pool.used_bytes == 90
    assert pool.free_bytes == 10

    # c3 requires 20 bytes, only 10 available
    assert not pool.can_fit(len(c3))
    with pytest.raises(ValueError, match="Compressed pool overflow"):
        pool.put(3, c3)

    # Evict LRU (which is page 1, 40 bytes)
    victim_vpn, victim_data = pool.evict_lru()
    assert victim_vpn == 1
    assert victim_data == c1
    assert pool.used_bytes == 50
    assert pool.free_bytes == 50

    # Now c3 fits
    pool.put(3, c3)
    assert pool.used_bytes == 70


def test_compressed_tier_dynamic_resize():
    """Shrinking compressed pool capacity must evict LRU pages until it fits."""
    pool = CompressedTier(capacity_bytes=100)
    pool.put(1, b"a" * 30)
    pool.put(2, b"b" * 30)
    pool.put(3, b"c" * 30)
    assert pool.used_bytes == 90

    # Resize to 50 bytes -> should evict page 1 (30 bytes) and page 2 (30 bytes)
    evicted = pool.set_capacity(50)
    assert len(evicted) == 2
    assert [vpn for vpn, _ in evicted] == [1, 2]
    assert pool.used_bytes == 30
    assert pool.capacity_bytes == 50
    assert pool.contains(3)


def test_swap_tier():
    """SSD Swap should read and write pages correctly."""
    swap = SwapTier(page_size=10)
    data = b"swaptest!!"
    swap.write(42, data)
    assert swap.contains(42)
    assert swap.page_count == 1
    assert swap.read(42) == data
    assert swap.total_writes == 1
    assert swap.total_reads == 1
