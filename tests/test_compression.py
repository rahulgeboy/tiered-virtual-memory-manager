"""Unit tests for compression engine (zlib, lzma, ratio calculation, round-trip integrity)."""

import pytest
from core.compression import CompressionEngine
from workloads.content_generator import PageContentGenerator
from config import ContentType


def test_roundtrip_integrity_zlib():
    """Compressed data decompressed via zlib must exactly match original bytes."""
    gen = PageContentGenerator(page_size=4096, seed=42)
    engine = CompressionEngine(algorithm="zlib", level=6)

    for ctype in (ContentType.ZERO, ContentType.TEXT_LIKE, ContentType.STRUCTURED, ContentType.RANDOM):
        original = gen.generate_page(ctype, vpn=1)
        res = engine.compress(original)
        decomp = engine.decompress(res.compressed_data)
        assert decomp.decompressed_data == original
        assert res.compression_time_ns > 0
        assert decomp.decompression_time_ns > 0


def test_roundtrip_integrity_lzma():
    """Compressed data decompressed via lzma must exactly match original bytes."""
    gen = PageContentGenerator(page_size=4096, seed=42)
    engine = CompressionEngine(algorithm="lzma", level=3)

    data = gen.generate_page(ContentType.TEXT_LIKE, vpn=5)
    res = engine.compress(data)
    decomp = engine.decompress(res.compressed_data)
    assert decomp.decompressed_data == data


def test_compressibility_hierarchy():
    """ZERO should compress better than TEXT_LIKE, which compresses better than RANDOM."""
    gen = PageContentGenerator(page_size=4096, seed=42)
    engine = CompressionEngine(algorithm="zlib", level=6)

    zero_res = engine.compress(gen.generate_page(ContentType.ZERO))
    text_res = engine.compress(gen.generate_page(ContentType.TEXT_LIKE))
    rand_res = engine.compress(gen.generate_page(ContentType.RANDOM))

    assert zero_res.compression_ratio < 0.05  # >95% savings
    assert text_res.compression_ratio < 0.35  # >65% savings
    assert rand_res.compression_ratio >= 0.99  # Incompressible or expands


@pytest.mark.parametrize("level", [1, 6, 9])
def test_zlib_levels(level):
    """Zlib compression levels 1, 6, and 9 should all function properly."""
    engine = CompressionEngine(algorithm="zlib", level=level)
    data = b"Operating systems virtual memory lab test string " * 80
    res = engine.compress(data)
    decomp = engine.decompress(res.compressed_data)
    assert decomp.decompressed_data == data


def test_invalid_algorithm():
    """Unsupported algorithm raises ValueError."""
    with pytest.raises(ValueError):
        CompressionEngine(algorithm="snappy")
