"""Compression engine providing real zlib and lzma compression with timing telemetry."""

from __future__ import annotations

import lzma
import time
import zlib
from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class CompressionResult:
    """Telemetry and output from a compression operation."""

    compressed_data: bytes
    compressed_size: int
    raw_size: int
    compression_time_ns: int
    compression_ratio: float  # compressed_size / raw_size (lower is better)
    space_saving: float       # 1.0 - (compressed_size / raw_size)


@dataclass(frozen=True)
class DecompressionResult:
    """Telemetry and output from a decompression operation."""

    decompressed_data: bytes
    decompression_time_ns: int


class CompressionEngine:
    """Handles page data compression and decompression using real CPU algorithms."""

    def __init__(self, algorithm: str = "zlib", level: int = 6) -> None:
        """Initialize compression engine.

        Args:
            algorithm: 'zlib' or 'lzma'.
            level: Compression level (0-9).
        """
        self.algorithm = algorithm.lower()
        self.level = level
        self._validate()

    def _validate(self) -> None:
        if self.algorithm not in ("zlib", "lzma"):
            raise ValueError(f"Unsupported algorithm '{self.algorithm}'. Must be 'zlib' or 'lzma'.")
        if not (0 <= self.level <= 9):
            raise ValueError(f"Compression level must be between 0 and 9, got {self.level}")

    def compress(self, data: bytes) -> CompressionResult:
        """Compress raw bytes and measure CPU duration.

        Args:
            data: Raw uncompressed bytes (typically 4096 bytes).

        Returns:
            CompressionResult containing compressed bytes, sizes, and elapsed nanoseconds.
        """
        start_ns = time.perf_counter_ns()
        if self.algorithm == "zlib":
            compressed = zlib.compress(data, level=self.level)
        elif self.algorithm == "lzma":
            compressed = lzma.compress(data, preset=self.level)
        else:
            raise ValueError(f"Unknown algorithm: {self.algorithm}")
        elapsed_ns = time.perf_counter_ns() - start_ns

        raw_size = len(data)
        comp_size = len(compressed)
        ratio = comp_size / raw_size if raw_size > 0 else 1.0
        saving = 1.0 - ratio

        return CompressionResult(
            compressed_data=compressed,
            compressed_size=comp_size,
            raw_size=raw_size,
            compression_time_ns=max(1, elapsed_ns),
            compression_ratio=ratio,
            space_saving=saving,
        )

    def decompress(self, compressed_data: bytes) -> DecompressionResult:
        """Decompress compressed bytes and measure CPU duration.

        Args:
            compressed_data: Compressed byte stream.

        Returns:
            DecompressionResult containing decompressed bytes and elapsed nanoseconds.
        """
        start_ns = time.perf_counter_ns()
        if self.algorithm == "zlib":
            decompressed = zlib.decompress(compressed_data)
        elif self.algorithm == "lzma":
            decompressed = lzma.decompress(compressed_data)
        else:
            raise ValueError(f"Unknown algorithm: {self.algorithm}")
        elapsed_ns = time.perf_counter_ns() - start_ns

        return DecompressionResult(
            decompressed_data=decompressed,
            decompression_time_ns=max(1, elapsed_ns),
        )
