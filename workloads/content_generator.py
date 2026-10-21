"""Synthetic page content generator creating realistic 4096-byte memory buffers."""

from __future__ import annotations

import random
import struct
from typing import Dict, List, Optional

from config import ContentType


class PageContentGenerator:
    """Generates realistic 4096-byte page payloads exhibiting varied entropy and compressibility.

    OS Concept:
    Real operating system memory contains diverse data patterns:
    - Zero pages: freshly zero-initialized heaps/bss segments.
    - Text pages: string constants, code, configuration text with repetitive n-grams.
    - Structured data: tabular structures, object headers, pointers, integer arrays.
    - High-entropy/random: compressed media, encrypted buffers, cryptographic keys.
    Linux zswap/zram relies on this divergence: highly compressible pages remain in RAM,
    while incompressible pages bypass compression pools to avoid wasting CPU cycles.
    """

    ENGLISH_WORDS = [
        "operating", "system", "virtual", "memory", "paging", "demand", "translation",
        "hierarchy", "latency", "compression", "throughput", "buffer", "cache", "demotion",
        "promotion", "kernel", "allocation", "physical", "dram", "swap", "zram", "zswap",
        "algorithm", "replacement", "benchmark", "simulation", "process", "thread", "address"
    ]

    def __init__(self, page_size: int = 4096, seed: Optional[int] = 42) -> None:
        """Initialize content generator.

        Args:
            page_size: Size in bytes of each page (default 4096).
            seed: Seed for deterministic byte generation.
        """
        self.page_size = page_size
        self.seed = seed
        self._rng = random.Random(seed)

    def generate_page(self, content_type: ContentType, vpn: int = 0) -> bytes:
        """Generate a reproducible 4096-byte buffer for a given content profile.

        Args:
            content_type: ContentType enum value.
            vpn: Virtual page number for deterministic variations.

        Returns:
            bytes of length self.page_size.
        """
        # Per-vpn seeded RNG for perfect reproducibility regardless of call order
        vpn_rng = random.Random((self.seed or 0) * 10007 + vpn * 31 + hash(content_type))

        if content_type == ContentType.ZERO:
            return b"\x00" * self.page_size

        elif content_type == ContentType.TEXT_LIKE:
            words = []
            current_len = 0
            while current_len < self.page_size:
                word = vpn_rng.choice(self.ENGLISH_WORDS) + " "
                words.append(word)
                current_len += len(word)
            text_bytes = "".join(words).encode("utf-8")[: self.page_size]
            if len(text_bytes) < self.page_size:
                text_bytes = text_bytes.ljust(self.page_size, b" ")
            return text_bytes

        elif content_type == ContentType.STRUCTURED:
            # Emulate an array of C structs: struct { uint32 id; uint32 timestamp; uint32 flag; float val; }
            record_format = "<IIIId"
            record_size = struct.calcsize(record_format)
            records = []
            num_records = self.page_size // record_size
            for i in range(num_records):
                rec = struct.pack(
                    record_format,
                    vpn,
                    1600000000 + i * 10,
                    i % 8,
                    (vpn * 100 + i) % 256,
                    float(i * 1.5),
                )
                records.append(rec)
            raw = b"".join(records)
            return raw.ljust(self.page_size, b"\x00")

        elif content_type == ContentType.RANDOM:
            return bytes(vpn_rng.getrandbits(8) for _ in range(self.page_size))

        else:
            raise ValueError(f"Unknown ContentType: {content_type}")

    def modify_page(self, original: bytes, write_counter: int) -> bytes:
        """Mutate an existing page's contents to simulate a dirty page write.

        Modifies a slice of the page so that dirty page recompression produces
        realistic variations without turning structured data into pure random noise.

        Args:
            original: Existing 4096 bytes.
            write_counter: Monotonically increasing counter for mutation diversity.

        Returns:
            Mutated 4096-byte buffer.
        """
        buf = bytearray(original)
        mutation_seed = (self.seed or 0) + write_counter * 997
        rng = random.Random(mutation_seed)

        # Mutate 64 to 256 bytes at a pseudorandom offset
        offset = rng.randint(0, self.page_size - 256)
        mutation_len = rng.randint(64, 256)
        delta_bytes = bytes((b ^ (write_counter & 0xFF)) for b in rng.randbytes(mutation_len))
        buf[offset : offset + mutation_len] = delta_bytes

        return bytes(buf)

    @classmethod
    def create_mixed_profile(
        cls,
        virtual_address_space: int,
        weights: Optional[Dict[ContentType, float]] = None,
        seed: Optional[int] = 42,
    ) -> Dict[int, ContentType]:
        """Assign content types to virtual pages according to distribution weights.

        Default distribution:
        - 40% TEXT_LIKE
        - 20% ZERO
        - 20% STRUCTURED
        - 20% RANDOM

        Args:
            virtual_address_space: Total pages in address space.
            weights: Dictionary mapping ContentType to relative weight.
            seed: Seed for random assignment.

        Returns:
            Dict mapping vpn -> assigned ContentType.
        """
        if weights is None:
            weights = {
                ContentType.TEXT_LIKE: 0.40,
                ContentType.ZERO: 0.20,
                ContentType.STRUCTURED: 0.20,
                ContentType.RANDOM: 0.20,
            }

        types = list(weights.keys())
        prob = [weights[t] for t in types]
        total_weight = sum(prob)
        norm_prob = [p / total_weight for p in prob]

        rng = random.Random(seed)
        assignments = rng.choices(types, weights=norm_prob, k=virtual_address_space)
        return {vpn: assignments[vpn] for vpn in range(virtual_address_space)}
