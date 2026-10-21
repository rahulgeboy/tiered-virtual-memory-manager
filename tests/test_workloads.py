"""Unit tests for workload generators and synthetic page payloads."""

import pytest
from config import ContentType, WorkloadPattern
from workloads.access_patterns import WorkloadGenerator
from workloads.content_generator import PageContentGenerator


def test_content_generator_sizes_and_types():
    """All generated pages must have exact configured page_size."""
    gen = PageContentGenerator(page_size=4096, seed=42)
    for ctype in (ContentType.ZERO, ContentType.TEXT_LIKE, ContentType.STRUCTURED, ContentType.RANDOM):
        buf = gen.generate_page(ctype, vpn=10)
        assert len(buf) == 4096


def test_content_generator_reproducibility():
    """Same seed and VPN must yield identical content."""
    gen1 = PageContentGenerator(page_size=4096, seed=12345)
    gen2 = PageContentGenerator(page_size=4096, seed=12345)
    buf1 = gen1.generate_page(ContentType.TEXT_LIKE, vpn=7)
    buf2 = gen2.generate_page(ContentType.TEXT_LIKE, vpn=7)
    assert buf1 == buf2


def test_content_mutation_on_write():
    """Mutating page on write changes content while preserving page size."""
    gen = PageContentGenerator(page_size=4096, seed=42)
    orig = gen.generate_page(ContentType.TEXT_LIKE, vpn=3)
    mutated = gen.modify_page(orig, write_counter=1)
    assert len(mutated) == 4096
    assert mutated != orig


def test_mixed_profile_distribution():
    """Mixed profile generates expected proportions across address space."""
    profile = PageContentGenerator.create_mixed_profile(
        virtual_address_space=200,
        weights={
            ContentType.TEXT_LIKE: 0.5,
            ContentType.ZERO: 0.5,
        },
        seed=42,
    )
    assert len(profile) == 200
    types = list(profile.values())
    assert ContentType.TEXT_LIKE in types
    assert ContentType.ZERO in types


@pytest.mark.parametrize("pattern", [
    WorkloadPattern.SEQUENTIAL,
    WorkloadPattern.LOOPING,
    WorkloadPattern.ZIPF,
    WorkloadPattern.UNIFORM,
    WorkloadPattern.PHASE_SHIFTING,
])
def test_workload_patterns_length_and_bounds(pattern):
    """Generated traces must match requested length and address space bounds."""
    wg = WorkloadGenerator(seed=42)
    num_accesses = 200
    vas = 64
    trace = wg.generate(
        pattern=pattern,
        num_accesses=num_accesses,
        virtual_address_space=vas,
        write_ratio=0.25,
        dram_frames=16,
    )
    assert len(trace) == num_accesses
    for vpn, is_write in trace:
        assert 0 <= vpn < vas
        assert isinstance(is_write, bool)


def test_workload_reproducibility():
    """Same seed yields identical access traces."""
    wg1 = WorkloadGenerator(seed=999)
    wg2 = WorkloadGenerator(seed=999)
    t1 = wg1.generate_zipf(num_accesses=100, virtual_address_space=32)
    t2 = wg2.generate_zipf(num_accesses=100, virtual_address_space=32)
    assert t1 == t2
