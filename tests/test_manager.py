"""Unit and integration tests for BaselineManager and TieredManager."""

import pytest
from config import ContentType, EventType, SimulationConfig, Tier
from core.memory_manager import AdaptiveTieredManager, BaselineManager, TieredManager


def test_baseline_manager_lifecycle():
    """Verify Cold Fault -> Hit -> Eviction -> Major Fault cycle in Baseline."""
    config = SimulationConfig(
        page_size=4096,
        dram_frames=2,
        compressed_pool_bytes=0,
        virtual_address_space=4,
    )
    mgr = BaselineManager(config, content_profile=ContentType.TEXT_LIKE)

    # 1. Access VPN 0: Cold fault
    rec0 = mgr.access(vpn=0, is_write=False)
    assert rec0.event_type == EventType.COLD_FAULT
    assert rec0.tier_before == Tier.UNMAPPED
    assert rec0.tier_after == Tier.DRAM
    assert mgr.dram.frame_count == 1
    mgr.assert_invariants()

    # 2. Access VPN 0 again: Hit
    rec0_hit = mgr.access(vpn=0, is_write=False)
    assert rec0_hit.event_type == EventType.HIT
    assert rec0_hit.tier_before == Tier.DRAM
    assert rec0_hit.tier_after == Tier.DRAM
    mgr.assert_invariants()

    # 3. Access VPN 1: Cold fault (DRAM now full: [0, 1])
    rec1 = mgr.access(vpn=1, is_write=False)
    assert rec1.event_type == EventType.COLD_FAULT
    assert mgr.dram.frame_count == 2
    mgr.assert_invariants()

    # 4. Access VPN 2: Cold fault causing eviction of LRU page (VPN 0) to SWAP
    rec2 = mgr.access(vpn=2, is_write=False)
    assert rec2.event_type == EventType.COLD_FAULT
    assert mgr.dram.frame_count == 2
    assert mgr.page_table.get_entry(0).tier == Tier.SWAP
    assert mgr.page_table.get_entry(1).tier == Tier.DRAM
    assert mgr.page_table.get_entry(2).tier == Tier.DRAM
    mgr.assert_invariants()

    # 5. Access VPN 0: Major fault from SWAP (causes eviction of VPN 1 to SWAP)
    rec0_swap = mgr.access(vpn=0, is_write=False)
    assert rec0_swap.event_type == EventType.MAJOR_FAULT
    assert rec0_swap.tier_before == Tier.SWAP
    assert rec0_swap.tier_after == Tier.DRAM
    assert mgr.page_table.get_entry(1).tier == Tier.SWAP
    assert mgr.page_table.get_entry(0).tier == Tier.DRAM
    mgr.assert_invariants()


def test_tiered_manager_minor_fault():
    """Verify promotion from compressed pool to DRAM triggers MINOR_FAULT."""
    config = SimulationConfig(
        page_size=4096,
        dram_frames=2,
        compressed_pool_bytes=16 * 4096,
        virtual_address_space=4,
        compress_skip_threshold=0.75,
    )
    # Using TEXT_LIKE so it easily compresses below 0.75 threshold
    mgr = TieredManager(config, content_profile=ContentType.TEXT_LIKE)

    # Fill DRAM with pages 0 and 1
    mgr.access(0)
    mgr.access(1)
    assert mgr.dram.frame_count == 2
    assert mgr.compressed.page_count == 0

    # Access page 2: evicts LRU page 0 into Compressed tier
    rec2 = mgr.access(2)
    assert rec2.event_type == EventType.COLD_FAULT
    assert mgr.page_table.get_entry(0).tier == Tier.COMPRESSED
    assert mgr.compressed.contains(0)
    assert mgr.compressed.page_count == 1
    assert mgr.compressed.used_bytes > 0
    mgr.assert_invariants()

    # Access page 0: Minor fault! Promotes from Compressed tier back to DRAM
    rec0 = mgr.access(0)
    assert rec0.event_type == EventType.MINOR_FAULT
    assert rec0.tier_before == Tier.COMPRESSED
    assert rec0.tier_after == Tier.DRAM
    assert not mgr.compressed.contains(0)
    # Page 1 should now be evicted to Compressed tier
    assert mgr.page_table.get_entry(1).tier == Tier.COMPRESSED
    mgr.assert_invariants()


def test_compress_or_skip_incompressible():
    """High-entropy RANDOM pages should bypass Compressed tier and go directly to SWAP."""
    config = SimulationConfig(
        page_size=4096,
        dram_frames=2,
        compressed_pool_bytes=16 * 4096,
        virtual_address_space=4,
        compress_skip_threshold=0.75,  # Random bytes have ratio >= 1.0 > 0.75
    )
    mgr = TieredManager(config, content_profile=ContentType.RANDOM)

    mgr.access(0)
    mgr.access(1)
    # Access page 2: LRU page 0 is evicted. Because it's RANDOM, it skips Tier 1 and goes to SWAP!
    mgr.access(2)
    assert mgr.page_table.get_entry(0).tier == Tier.SWAP
    assert mgr.compressed.page_count == 0
    assert mgr.compressed.used_bytes == 0
    mgr.assert_invariants()


def test_compressed_pool_overflow_eviction_chain():
    """When compressed pool byte capacity is exhausted, demote LRU compressed pages to SSD."""
    # Pool can hold roughly 2 compressed zero pages (~50 bytes each)
    config = SimulationConfig(
        page_size=4096,
        dram_frames=1,
        compressed_pool_bytes=80,  # Tight pool capacity
        virtual_address_space=6,
        compress_skip_threshold=0.75,
    )
    mgr = TieredManager(config, content_profile=ContentType.ZERO)

    # Access page 0 (in DRAM)
    mgr.access(0)
    assert mgr.page_table.get_entry(0).tier == Tier.DRAM

    # Access page 1 -> page 0 demoted to Compressed RAM
    mgr.access(1)
    assert mgr.page_table.get_entry(0).tier == Tier.COMPRESSED
    assert mgr.page_table.get_entry(1).tier == Tier.DRAM
    mgr.assert_invariants()

    # Access page 2, 3, 4, 5
    for p in range(2, 6):
        mgr.access(p)
        mgr.assert_invariants()

    # Verify that pages have reached SWAP because pool byte capacity was bounded
    assert mgr.swap.page_count > 0
    assert mgr.compressed.used_bytes <= config.compressed_pool_bytes
    mgr.assert_invariants()


def test_data_integrity_roundtrip_after_swap_and_compression():
    """Verify that page content remains 100% byte-accurate through DRAM->Compressed->Swap->DRAM."""
    config = SimulationConfig(
        page_size=4096,
        dram_frames=1,
        compressed_pool_bytes=100,  # Small pool so demotion to swap occurs quickly
        virtual_address_space=4,
    )
    mgr = TieredManager(config, content_profile=ContentType.TEXT_LIKE)

    # Touch page 0 and record its content
    mgr.access(0)
    original_p0 = bytes(mgr.dram.read(0))

    # Push page 0 to Compressed, then to Swap by accessing pages 1, 2, 3
    mgr.access(1)
    mgr.access(2)
    mgr.access(3)

    assert mgr.page_table.get_entry(0).tier == Tier.SWAP

    # Touch page 0 again (Major fault from swap)
    mgr.access(0)
    retrieved_p0 = mgr.dram.read(0)

    assert retrieved_p0 == original_p0


def test_clean_page_swap_write_skipped():
    """Clean pages already on swap should not incur additional SSD write latency upon demotion."""
    config = SimulationConfig(
        page_size=4096,
        dram_frames=1,
        virtual_address_space=3,
        ssd_write_latency_ns=100_000,
    )
    mgr = BaselineManager(config, content_profile=ContentType.TEXT_LIKE)

    # Page 0 cold fault -> DRAM
    mgr.access(0, is_write=False)
    # Page 1 cold fault -> Page 0 evicted to SWAP (incurs 100,000 ns SSD write)
    rec1 = mgr.access(1, is_write=False)
    assert rec1.eviction_ssd_write_latency_ns == 100_000

    # Read page 0 from SWAP (major fault, NOT written to -> swap_clean remains True)
    rec0 = mgr.access(0, is_write=False)
    assert mgr.page_table.get_entry(0).swap_clean is True

    # Evict page 0 again by accessing page 2 without modifying page 0
    # Redundant SSD write should be skipped!
    rec2 = mgr.access(2, is_write=False)
    assert rec2.eviction_ssd_write_latency_ns == 0
    assert mgr.page_table.get_entry(0).tier == Tier.SWAP


def test_adaptive_tiered_manager_expansion():
    """Adaptive manager should expand pool capacity when major fault threshold is exceeded."""
    config = SimulationConfig(
        page_size=4096,
        dram_frames=2,
        compressed_pool_bytes=1000,  # Very tight initial capacity (~1 page)
        virtual_address_space=20,
    )
    adaptive_mgr = AdaptiveTieredManager(
        config=config,
        content_profile=ContentType.TEXT_LIKE,
        window_size=20,
        high_watermark=0.10,
        min_pool_bytes=1000,
        max_pool_bytes=32000,
        step_bytes=2000,
    )

    initial_cap = adaptive_mgr.compressed.capacity_bytes

    # Access 10 pages in loops: 2 fit in DRAM, ~1-2 in compressed pool, rest pushed to swap.
    # Subsequent iterations cause repeated major faults from swap!
    for step in range(120):
        adaptive_mgr.access(step % 10)
        adaptive_mgr.assert_invariants()

    # With sustained major faults from swap, capacity must expand beyond initial_cap
    assert adaptive_mgr.compressed.capacity_bytes > initial_cap
    assert any(action == "EXPAND" for _, action, _ in adaptive_mgr.adaptation_events)

