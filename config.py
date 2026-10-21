"""Configuration module for Tiered Virtual Memory Manager simulation.

Defines the simulation parameters, tier types, access event types, and validation logic.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict


class Tier(str, Enum):
    """Memory hierarchy tiers."""
    DRAM = "DRAM"
    COMPRESSED = "COMPRESSED"
    SWAP = "SWAP"
    UNMAPPED = "UNMAPPED"


class EventType(str, Enum):
    """Memory access classification."""
    HIT = "HIT"                  # Found in DRAM
    MINOR_FAULT = "MINOR_FAULT"  # Found in Compressed RAM, decompressed into DRAM
    MAJOR_FAULT = "MAJOR_FAULT"  # Found on SSD Swap, read into DRAM
    COLD_FAULT = "COLD_FAULT"    # First touch, freshly allocated into DRAM


class ContentType(str, Enum):
    """Page data compressibility profiles."""
    TEXT_LIKE = "TEXT_LIKE"      # Repeated English words (compresses well)
    ZERO = "ZERO"                # Zero-filled (compresses extremely well)
    STRUCTURED = "STRUCTURED"    # Repeated records/counters (compresses moderately)
    RANDOM = "RANDOM"            # High-entropy random bytes (incompressible)


class WorkloadPattern(str, Enum):
    """Access pattern profiles."""
    SEQUENTIAL = "SEQUENTIAL"
    LOOPING = "LOOPING"
    ZIPF = "ZIPF"
    UNIFORM = "UNIFORM"
    PHASE_SHIFTING = "PHASE_SHIFTING"


@dataclass
class SimulationConfig:
    """Configuration parameters for memory manager simulation runs."""

    page_size: int = 4096
    dram_frames: int = 64
    compressed_pool_bytes: int = 64 * 4096  # Measured in BYTES, not page count
    virtual_address_space: int = 256        # Total virtual pages in address space

    # Latency model parameters (in nanoseconds)
    dram_latency_ns: int = 100
    ssd_read_latency_ns: int = 100_000
    ssd_write_latency_ns: int = 100_000

    # Fixed cost mode vs real measured timing via time.perf_counter_ns()
    fixed_cost_mode: bool = False
    fixed_compress_latency_ns: int = 3_000
    fixed_decompress_latency_ns: int = 2_000

    # Compression policy
    # If (compressed_size / page_size) > compress_skip_threshold, bypass Tier 1 to SSD
    compress_skip_threshold: float = 0.75
    compression_algorithm: str = "zlib"  # "zlib" or "lzma"
    compression_level: int = 6           # 1, 6, 9 for zlib; 0-9 for lzma

    # Reproducibility
    random_seed: int = 42

    def __post_init__(self) -> None:
        """Validate all parameters after initialization."""
        self.validate()

    def validate(self) -> None:
        """Enforce parameter constraints and fail fast with informative errors.

        Raises:
            ValueError: If any parameter is invalid.
        """
        if self.page_size <= 0:
            raise ValueError(f"page_size must be positive, got {self.page_size}")
        if self.dram_frames <= 0:
            raise ValueError(f"dram_frames must be positive, got {self.dram_frames}")
        if self.compressed_pool_bytes < 0:
            raise ValueError(
                f"compressed_pool_bytes cannot be negative, got {self.compressed_pool_bytes}"
            )
        if self.virtual_address_space <= 0:
            raise ValueError(
                f"virtual_address_space must be positive, got {self.virtual_address_space}"
            )
        if not (0.0 < self.compress_skip_threshold <= 1.0):
            raise ValueError(
                f"compress_skip_threshold must be in range (0.0, 1.0], got {self.compress_skip_threshold}"
            )
        if self.dram_latency_ns < 0:
            raise ValueError(f"dram_latency_ns cannot be negative, got {self.dram_latency_ns}")
        if self.ssd_read_latency_ns < 0:
            raise ValueError(
                f"ssd_read_latency_ns cannot be negative, got {self.ssd_read_latency_ns}"
            )
        if self.ssd_write_latency_ns < 0:
            raise ValueError(
                f"ssd_write_latency_ns cannot be negative, got {self.ssd_write_latency_ns}"
            )
        if self.fixed_compress_latency_ns < 0:
            raise ValueError(
                f"fixed_compress_latency_ns cannot be negative, got {self.fixed_compress_latency_ns}"
            )
        if self.fixed_decompress_latency_ns < 0:
            raise ValueError(
                f"fixed_decompress_latency_ns cannot be negative, got {self.fixed_decompress_latency_ns}"
            )

        valid_algorithms = {"zlib", "lzma"}
        if self.compression_algorithm.lower() not in valid_algorithms:
            raise ValueError(
                f"Unsupported compression algorithm '{self.compression_algorithm}'. "
                f"Must be one of {valid_algorithms}"
            )

        if self.compression_algorithm.lower() == "zlib":
            if self.compression_level not in range(0, 10):
                raise ValueError(
                    f"zlib compression_level must be between 0 and 9, got {self.compression_level}"
                )
        elif self.compression_algorithm.lower() == "lzma":
            if self.compression_level not in range(0, 10):
                raise ValueError(
                    f"lzma compression_level must be between 0 and 9, got {self.compression_level}"
                )

    def to_dict(self) -> Dict[str, Any]:
        """Convert config to dictionary representation."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> SimulationConfig:
        """Create config from dictionary representation."""
        return cls(**data)

    def to_json(self, path: Path | str | None = None) -> str:
        """Export config to JSON string or file."""
        serialized = json.dumps(self.to_dict(), indent=2)
        if path:
            Path(path).write_text(serialized, encoding="utf-8")
        return serialized

    @classmethod
    def from_json(cls, path_or_json: Path | str) -> SimulationConfig:
        """Load config from JSON string or JSON file."""
        p = Path(path_or_json)
        if p.exists() and p.is_file():
            data = json.loads(p.read_text(encoding="utf-8"))
        else:
            data = json.loads(str(path_or_json))
        return cls.from_dict(data)
