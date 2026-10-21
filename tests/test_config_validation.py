"""Unit tests for configuration validation and serialization."""

import json
import pytest
from config import SimulationConfig


def test_default_config_valid():
    """Default simulation configuration should pass validation without error."""
    config = SimulationConfig()
    assert config.page_size == 4096
    assert config.dram_frames == 64
    assert config.compressed_pool_bytes == 64 * 4096
    assert config.virtual_address_space == 256
    assert config.compress_skip_threshold == 0.75
    assert config.compression_algorithm == "zlib"
    assert config.compression_level == 6


@pytest.mark.parametrize("frames", [0, -1, -64])
def test_invalid_dram_frames(frames):
    """dram_frames must be strictly positive."""
    with pytest.raises(ValueError, match="dram_frames must be positive"):
        SimulationConfig(dram_frames=frames)


@pytest.mark.parametrize("pool_bytes", [-1, -4096])
def test_invalid_pool_bytes(pool_bytes):
    """compressed_pool_bytes cannot be negative."""
    with pytest.raises(ValueError, match="compressed_pool_bytes cannot be negative"):
        SimulationConfig(compressed_pool_bytes=pool_bytes)


@pytest.mark.parametrize("threshold", [0.0, -0.1, 1.01, 2.5])
def test_invalid_compress_threshold(threshold):
    """compress_skip_threshold must be strictly within (0.0, 1.0]."""
    with pytest.raises(ValueError, match="compress_skip_threshold must be in range"):
        SimulationConfig(compress_skip_threshold=threshold)


@pytest.mark.parametrize("vas", [0, -10])
def test_invalid_virtual_address_space(vas):
    """virtual_address_space must be positive."""
    with pytest.raises(ValueError, match="virtual_address_space must be positive"):
        SimulationConfig(virtual_address_space=vas)


@pytest.mark.parametrize("latency_field", [
    "dram_latency_ns",
    "ssd_read_latency_ns",
    "ssd_write_latency_ns",
    "fixed_compress_latency_ns",
    "fixed_decompress_latency_ns",
])
def test_negative_latencies(latency_field):
    """Latencies cannot be negative."""
    kwargs = {latency_field: -5}
    with pytest.raises(ValueError, match="cannot be negative"):
        SimulationConfig(**kwargs)


def test_invalid_compression_algorithm():
    """Unsupported compression algorithm should raise ValueError."""
    with pytest.raises(ValueError, match="Unsupported compression algorithm"):
        SimulationConfig(compression_algorithm="bzip2")


@pytest.mark.parametrize("level", [-1, 10, 99])
def test_invalid_compression_level(level):
    """Compression level outside 0-9 should raise ValueError."""
    with pytest.raises(ValueError, match="compression_level must be between 0 and 9"):
        SimulationConfig(compression_level=level)


def test_config_json_roundtrip(tmp_path):
    """Config should serialize and deserialize identically via dict and JSON."""
    original = SimulationConfig(
        dram_frames=32,
        compressed_pool_bytes=16 * 4096,
        compress_skip_threshold=0.6,
        random_seed=123,
    )
    # Dict roundtrip
    as_dict = original.to_dict()
    from_dict = SimulationConfig.from_dict(as_dict)
    assert original == from_dict

    # JSON file roundtrip
    cfg_file = tmp_path / "config.json"
    original.to_json(cfg_file)
    from_json = SimulationConfig.from_json(cfg_file)
    assert original == from_json
