"""Memory manager implementations: Baseline (2-tier), Tiered (3-tier with zswap/zram), and Adaptive Tiered."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass
from typing import Deque, Dict, List, Optional, Tuple, Union

from config import ContentType, EventType, SimulationConfig, Tier
from core.compressed_tier import CompressedTier
from core.compression import CompressionEngine
from core.cost_model import AccessCostBreakdown, LatencyCostModel
from core.dram_tier import DRAMTier
from core.page_table import PageTable, PageTableEntry
from core.swap_tier import SwapTier
from workloads.content_generator import PageContentGenerator


@dataclass(frozen=True)
class AccessRecord:
    """Detailed telemetry record for a single memory access."""

    access_index: int
    vpn: int
    is_write: bool
    event_type: EventType
    tier_before: Tier
    tier_after: Tier
    cost_ns: int
    dram_latency_ns: int
    decompress_latency_ns: int
    ssd_read_latency_ns: int
    eviction_compress_latency_ns: int
    eviction_ssd_write_latency_ns: int
    dram_pages: int
    compressed_pages: int
    swap_pages: int
    compressed_pool_bytes: int
    resident_dram_vpns: Tuple[int, ...] = ()
    resident_compressed_vpns: Tuple[int, ...] = ()
    resident_swap_vpns: Tuple[int, ...] = ()


class MemoryManager(ABC):
    """Abstract base class establishing a uniform interface for memory managers."""

    def __init__(
        self,
        config: SimulationConfig,
        content_profile: Optional[Union[Dict[int, ContentType], ContentType]] = None,
    ) -> None:
        """Initialize base memory manager components.

        Args:
            config: Simulation parameters and latencies.
            content_profile: Mapping of vpn -> ContentType, or a uniform ContentType.
        """
        self.config = config
        self.page_table = PageTable(virtual_address_space=config.virtual_address_space)
        self.dram = DRAMTier(max_frames=config.dram_frames, page_size=config.page_size)
        self.swap = SwapTier(page_size=config.page_size)
        self.cost_model = LatencyCostModel(config)
        self.compression_engine = CompressionEngine(
            algorithm=config.compression_algorithm, level=config.compression_level
        )
        self.content_gen = PageContentGenerator(page_size=config.page_size, seed=config.random_seed)

        # Setup content profile per VPN
        if content_profile is None:
            self.content_profile = PageContentGenerator.create_mixed_profile(
                config.virtual_address_space, seed=config.random_seed
            )
        elif isinstance(content_profile, ContentType):
            self.content_profile = {
                vpn: content_profile for vpn in range(config.virtual_address_space)
            }
        else:
            self.content_profile = dict(content_profile)

        # Simulation metrics & log
        self.access_log: List[AccessRecord] = []
        self.time_step: int = 0
        self.write_counter: int = 0

        # Aggregate counters
        self.dram_hits: int = 0
        self.minor_faults: int = 0
        self.major_faults: int = 0
        self.cold_faults: int = 0
        self.total_latency_ns: int = 0
        self.total_compress_time_ns: int = 0
        self.total_decompress_time_ns: int = 0
        self.total_uncompressed_bytes_compressed: int = 0
        self.total_compressed_bytes_produced: int = 0

    @abstractmethod
    def access(self, vpn: int, is_write: bool = False) -> AccessRecord:
        """Handle a virtual memory read or write access."""
        pass

    def run_trace(self, trace: List[Tuple[int, bool]]) -> List[AccessRecord]:
        """Execute a complete memory reference trace.

        Args:
            trace: List of (vpn, is_write) tuples.

        Returns:
            List of generated AccessRecord items.
        """
        records = []
        for vpn, is_write in trace:
            records.append(self.access(vpn, is_write))
        return records

    def assert_invariants(self) -> None:
        """Verify strict memory hierarchy consistency invariants.

        1. DRAM frame count <= config.dram_frames.
        2. Every VPN in [0, virtual_address_space) is in exactly ONE tier state.
        3. All physical structures are mutually exclusive (a page is not in DRAM and Swap simultaneously).
        """
        assert self.dram.frame_count <= self.config.dram_frames, (
            f"DRAM overflow: {self.dram.frame_count} > {self.config.dram_frames}"
        )

        for vpn in range(self.config.virtual_address_space):
            entry = self.page_table.get_entry(vpn)
            tier = entry.tier

            in_dram = self.dram.contains(vpn)
            in_swap = self.swap.contains(vpn)

            if tier == Tier.DRAM:
                assert in_dram, f"PTE says VPN {vpn} is in DRAM but not found in DRAMTier"
            elif tier == Tier.SWAP:
                assert in_swap, f"PTE says VPN {vpn} is in SWAP but not found in SwapTier"
            elif tier == Tier.UNMAPPED:
                assert not in_dram, f"VPN {vpn} marked UNMAPPED but present in DRAMTier"
                assert not in_swap, f"VPN {vpn} marked UNMAPPED but present in SwapTier"


class BaselineManager(MemoryManager):
    """Two-tier baseline memory manager: DRAM (LRU) + SSD Swap."""

    def access(self, vpn: int, is_write: bool = False) -> AccessRecord:
        """Process access in 2-tier baseline architecture."""
        self.time_step += 1
        entry = self.page_table.get_entry(vpn)
        tier_before = entry.tier

        dram_lat = self.cost_model.get_dram_hit_cost()
        ssd_read_lat = 0
        evict_ssd_write_lat = 0

        if tier_before == Tier.DRAM:
            # --- DRAM HIT ---
            self.dram_hits += 1
            event_type = EventType.HIT
            page_content = self.dram.read(vpn)
            if is_write:
                self.write_counter += 1
                page_content = self.content_gen.modify_page(page_content, self.write_counter)
                self.dram.write(vpn, page_content)

        elif tier_before == Tier.SWAP:
            # --- MAJOR FAULT ---
            self.major_faults += 1
            event_type = EventType.MAJOR_FAULT
            ssd_read_lat = self.cost_model.get_ssd_read_cost()
            page_content = self.swap.read(vpn)

            # Evict victim from DRAM if full
            if self.dram.is_full():
                evict_ssd_write_lat += self._evict_dram_victim()

            if is_write:
                self.write_counter += 1
                page_content = self.content_gen.modify_page(page_content, self.write_counter)
                entry.swap_clean = False
            else:
                # If page was just read from swap and not written to, swap copy is clean
                entry.swap_clean = True

            self.dram.put(vpn, page_content)
            entry.tier = Tier.DRAM

        elif tier_before == Tier.UNMAPPED:
            # --- COLD FAULT ---
            self.cold_faults += 1
            event_type = EventType.COLD_FAULT
            ctype = self.content_profile.get(vpn, ContentType.TEXT_LIKE)
            page_content = self.content_gen.generate_page(ctype, vpn=vpn)
            entry.content_type = ctype

            if self.dram.is_full():
                evict_ssd_write_lat += self._evict_dram_victim()

            if is_write:
                self.write_counter += 1
                page_content = self.content_gen.modify_page(page_content, self.write_counter)

            self.dram.put(vpn, page_content)
            entry.tier = Tier.DRAM

        else:
            raise RuntimeError(f"Unexpected tier {tier_before} in BaselineManager")

        entry.mark_access(time_step=self.time_step, is_write=is_write)
        tier_after = entry.tier

        total_cost = dram_lat + ssd_read_lat + evict_ssd_write_lat
        self.total_latency_ns += total_cost

        dram_vpns = tuple(self.dram.get_resident_vpns())
        swap_vpns = tuple(
            vpn
            for vpn in range(self.config.virtual_address_space)
            if self.page_table.get_entry(vpn).tier == Tier.SWAP
        )

        record = AccessRecord(
            access_index=self.time_step,
            vpn=vpn,
            is_write=is_write,
            event_type=event_type,
            tier_before=tier_before,
            tier_after=tier_after,
            cost_ns=total_cost,
            dram_latency_ns=dram_lat,
            decompress_latency_ns=0,
            ssd_read_latency_ns=ssd_read_lat,
            eviction_compress_latency_ns=0,
            eviction_ssd_write_latency_ns=evict_ssd_write_lat,
            dram_pages=len(dram_vpns),
            compressed_pages=0,
            swap_pages=len(swap_vpns),
            compressed_pool_bytes=0,
            resident_dram_vpns=dram_vpns,
            resident_compressed_vpns=(),
            resident_swap_vpns=swap_vpns,
        )
        self.access_log.append(record)
        return record

    def _evict_dram_victim(self) -> int:
        """Evict the LRU DRAM page directly to SSD swap.

        Returns:
            SSD write latency incurred (0 if clean and already on swap).
        """
        victim_vpn, victim_bytes = self.dram.evict_lru()
        victim_entry = self.page_table.get_entry(victim_vpn)

        if victim_entry.swap_clean and self.swap.contains(victim_vpn):
            # Page was unmodified since read from swap; skip redundant SSD write
            victim_entry.tier = Tier.SWAP
            return 0

        self.swap.write(victim_vpn, victim_bytes)
        victim_entry.swap_clean = True
        victim_entry.tier = Tier.SWAP
        return self.cost_model.get_ssd_write_cost()


class TieredManager(MemoryManager):
    """Three-tier memory manager: DRAM (Tier 0) + Compressed RAM (Tier 1) + SSD Swap (Tier 2)."""

    def __init__(
        self,
        config: SimulationConfig,
        content_profile: Optional[Union[Dict[int, ContentType], ContentType]] = None,
    ) -> None:
        """Initialize tiered manager with compressed RAM tier."""
        super().__init__(config, content_profile)
        self.compressed = CompressedTier(capacity_bytes=config.compressed_pool_bytes)

    def assert_invariants(self) -> None:
        """Verify 3-tier memory invariants including compressed pool byte limit."""
        super().assert_invariants()
        assert self.compressed.used_bytes <= self.compressed.capacity_bytes, (
            f"Compressed pool overflow: {self.compressed.used_bytes} > {self.compressed.capacity_bytes}"
        )
        for vpn in range(self.config.virtual_address_space):
            entry = self.page_table.get_entry(vpn)
            in_comp = self.compressed.contains(vpn)
            if entry.tier == Tier.COMPRESSED:
                assert in_comp, f"VPN {vpn} marked COMPRESSED but not in CompressedTier"
            else:
                assert not in_comp, f"VPN {vpn} marked {entry.tier} but present in CompressedTier"

    def access(self, vpn: int, is_write: bool = False) -> AccessRecord:
        """Handle 3-tier memory access: Hit -> Minor Fault -> Major Fault -> Cold Fault."""
        self.time_step += 1
        entry = self.page_table.get_entry(vpn)
        tier_before = entry.tier

        dram_lat = self.cost_model.get_dram_hit_cost()
        decomp_lat = 0
        ssd_read_lat = 0
        evict_comp_lat = 0
        evict_ssd_write_lat = 0

        if tier_before == Tier.DRAM:
            # --- DRAM HIT (Tier 0) ---
            self.dram_hits += 1
            event_type = EventType.HIT
            page_content = self.dram.read(vpn)
            if is_write:
                self.write_counter += 1
                page_content = self.content_gen.modify_page(page_content, self.write_counter)
                self.dram.write(vpn, page_content)

        elif tier_before == Tier.COMPRESSED:
            # --- MINOR FAULT (Tier 1 -> Tier 0) ---
            self.minor_faults += 1
            event_type = EventType.MINOR_FAULT

            # Decompress from compressed RAM
            comp_bytes = self.compressed.remove(vpn)
            decomp_res = self.compression_engine.decompress(comp_bytes)
            decomp_lat = self.cost_model.get_decompress_cost(decomp_res.decompression_time_ns)
            self.total_decompress_time_ns += decomp_lat

            page_content = decomp_res.decompressed_data

            # If DRAM is full, evict a DRAM victim to compressed tier or swap
            if self.dram.is_full():
                c_lat, w_lat = self._evict_dram_victim()
                evict_comp_lat += c_lat
                evict_ssd_write_lat += w_lat

            if is_write:
                self.write_counter += 1
                page_content = self.content_gen.modify_page(page_content, self.write_counter)
                entry.swap_clean = False

            self.dram.put(vpn, page_content)
            entry.tier = Tier.DRAM

        elif tier_before == Tier.SWAP:
            # --- MAJOR FAULT (Tier 2 -> Tier 0) ---
            self.major_faults += 1
            event_type = EventType.MAJOR_FAULT
            ssd_read_lat = self.cost_model.get_ssd_read_cost()
            page_content = self.swap.read(vpn)

            if self.dram.is_full():
                c_lat, w_lat = self._evict_dram_victim()
                evict_comp_lat += c_lat
                evict_ssd_write_lat += w_lat

            if is_write:
                self.write_counter += 1
                page_content = self.content_gen.modify_page(page_content, self.write_counter)
                entry.swap_clean = False
            else:
                entry.swap_clean = True

            self.dram.put(vpn, page_content)
            entry.tier = Tier.DRAM

        elif tier_before == Tier.UNMAPPED:
            # --- COLD FAULT (First touch) ---
            self.cold_faults += 1
            event_type = EventType.COLD_FAULT
            ctype = self.content_profile.get(vpn, ContentType.TEXT_LIKE)
            page_content = self.content_gen.generate_page(ctype, vpn=vpn)
            entry.content_type = ctype

            if self.dram.is_full():
                c_lat, w_lat = self._evict_dram_victim()
                evict_comp_lat += c_lat
                evict_ssd_write_lat += w_lat

            if is_write:
                self.write_counter += 1
                page_content = self.content_gen.modify_page(page_content, self.write_counter)

            self.dram.put(vpn, page_content)
            entry.tier = Tier.DRAM

        else:
            raise RuntimeError(f"Unexpected tier {tier_before} in TieredManager")

        entry.mark_access(time_step=self.time_step, is_write=is_write)
        tier_after = entry.tier

        total_cost = (
            dram_lat
            + decomp_lat
            + ssd_read_lat
            + evict_comp_lat
            + evict_ssd_write_lat
        )
        self.total_latency_ns += total_cost

        dram_vpns = tuple(self.dram.get_resident_vpns())
        comp_vpns = tuple(self.compressed.get_resident_vpns())
        swap_vpns = tuple(
            vpn
            for vpn in range(self.config.virtual_address_space)
            if self.page_table.get_entry(vpn).tier == Tier.SWAP
        )

        record = AccessRecord(
            access_index=self.time_step,
            vpn=vpn,
            is_write=is_write,
            event_type=event_type,
            tier_before=tier_before,
            tier_after=tier_after,
            cost_ns=total_cost,
            dram_latency_ns=dram_lat,
            decompress_latency_ns=decomp_lat,
            ssd_read_latency_ns=ssd_read_lat,
            eviction_compress_latency_ns=evict_comp_lat,
            eviction_ssd_write_latency_ns=evict_ssd_write_lat,
            dram_pages=len(dram_vpns),
            compressed_pages=len(comp_vpns),
            swap_pages=len(swap_vpns),
            compressed_pool_bytes=self.compressed.used_bytes,
            resident_dram_vpns=dram_vpns,
            resident_compressed_vpns=comp_vpns,
            resident_swap_vpns=swap_vpns,
        )
        self.access_log.append(record)
        return record

    def _evict_dram_victim(self) -> Tuple[int, int]:
        """Evict the LRU DRAM page through the compression pipeline.

        Eviction Policy:
        1. Compress victim content with real compression engine.
        2. Check compressibility threshold (compressed_size / PAGE_SIZE <= threshold).
        3. If compressible and pool has total capacity:
           - Demote LRU compressed pages to SSD until enough bytes are freed.
           - Insert into Compressed RAM pool.
        4. If incompressible (or compressed pool has zero capacity):
           - Bypass Tier 1 and write directly to SSD Swap.

        Returns:
            Tuple of (compression_latency_ns, ssd_write_latency_ns).
        """
        victim_vpn, victim_bytes = self.dram.evict_lru()
        victim_entry = self.page_table.get_entry(victim_vpn)

        # Real compression of victim page
        comp_res = self.compression_engine.compress(victim_bytes)
        compress_lat = self.cost_model.get_compress_cost(comp_res.compression_time_ns)
        self.total_compress_time_ns += compress_lat
        self.total_uncompressed_bytes_compressed += comp_res.raw_size
        self.total_compressed_bytes_produced += comp_res.compressed_size
        victim_entry.compressed_size = comp_res.compressed_size

        comp_ratio = comp_res.compression_ratio
        ssd_write_lat = 0

        # Check compress-or-skip criteria:
        # 1. Ratio <= compress_skip_threshold
        # 2. Total pool capacity >= compressed_size
        qualifies_for_compressed_tier = (
            comp_ratio <= self.config.compress_skip_threshold
            and self.compressed.has_total_capacity(comp_res.compressed_size)
        )

        if qualifies_for_compressed_tier:
            # Demote LRU compressed pages to SSD until pool has room
            while not self.compressed.can_fit(comp_res.compressed_size):
                demoted_vpn, demoted_comp_bytes = self.compressed.evict_lru()
                demoted_entry = self.page_table.get_entry(demoted_vpn)

                if demoted_entry.swap_clean and self.swap.contains(demoted_vpn):
                    # Clean copy already present on SSD
                    demoted_entry.tier = Tier.SWAP
                else:
                    # Decompress to write uncompressed 4KB page to swap
                    decomp_res = self.compression_engine.decompress(demoted_comp_bytes)
                    self.swap.write(demoted_vpn, decomp_res.decompressed_data)
                    demoted_entry.swap_clean = True
                    demoted_entry.tier = Tier.SWAP
                    ssd_write_lat += self.cost_model.get_ssd_write_cost()

            # Insert into compressed pool
            self.compressed.put(victim_vpn, comp_res.compressed_data)
            victim_entry.tier = Tier.COMPRESSED

        else:
            # Bypass compressed tier directly to SSD swap
            if victim_entry.swap_clean and self.swap.contains(victim_vpn):
                victim_entry.tier = Tier.SWAP
            else:
                self.swap.write(victim_vpn, victim_bytes)
                victim_entry.swap_clean = True
                victim_entry.tier = Tier.SWAP
                ssd_write_lat += self.cost_model.get_ssd_write_cost()

        return compress_lat, ssd_write_lat


class AdaptiveTieredManager(TieredManager):
    """Adaptive 3-tier memory manager that dynamically tunes compressed pool size.

    OS Concept:
    Linux memory management dynamically adjusts page cache versus zswap boundaries
    based on memory pressure metrics (PSI - Pressure Stall Information).
    If major faults (SSD I/O) increase, the system expands the compressed RAM pool
    to retain more working set in memory. If memory pressure subsides, the pool
    is pruned to return RAM frames for process execution.
    """

    def __init__(
        self,
        config: SimulationConfig,
        content_profile: Optional[Union[Dict[int, ContentType], ContentType]] = None,
        window_size: int = 100,
        high_watermark: float = 0.15,
        low_watermark: float = 0.02,
        min_pool_bytes: Optional[int] = None,
        max_pool_bytes: Optional[int] = None,
        step_bytes: Optional[int] = None,
    ) -> None:
        """Initialize adaptive tiered memory manager."""
        super().__init__(config, content_profile)
        self.window_size = window_size
        self.high_watermark = high_watermark
        self.low_watermark = low_watermark
        self.min_pool_bytes = min_pool_bytes if min_pool_bytes is not None else 8 * config.page_size
        self.max_pool_bytes = max_pool_bytes if max_pool_bytes is not None else 128 * config.page_size
        self.step_bytes = step_bytes if step_bytes is not None else 8 * config.page_size

        # Ring buffer tracking recent major fault occurrences (1 for major fault, 0 otherwise)
        self._recent_faults: Deque[int] = deque(maxlen=window_size)
        self.adaptation_events: List[Tuple[int, str, int]] = []  # (timestep, action, new_capacity)

    def access(self, vpn: int, is_write: bool = False) -> AccessRecord:
        """Process access with adaptive feedback tuning."""
        record = super().access(vpn, is_write)

        # Track major fault pressure in window
        is_major = 1 if record.event_type == EventType.MAJOR_FAULT else 0
        self._recent_faults.append(is_major)

        # Check adaptation conditions every 25 accesses once window has sufficient samples
        if self.time_step % 25 == 0 and len(self._recent_faults) >= min(25, self.window_size):
            self._adapt_pool_size()

        return record

    def _adapt_pool_size(self) -> None:
        """Dynamically expand or contract compressed pool capacity."""
        recent_major_rate = sum(self._recent_faults) / len(self._recent_faults)
        curr_capacity = self.compressed.capacity_bytes

        if recent_major_rate >= self.high_watermark and curr_capacity < self.max_pool_bytes:
            # Expand pool to mitigate SSD thrashing
            new_capacity = min(self.max_pool_bytes, curr_capacity + self.step_bytes)
            self.compressed.set_capacity(new_capacity)
            self.adaptation_events.append((self.time_step, "EXPAND", new_capacity))

        elif (
            recent_major_rate <= self.low_watermark
            and curr_capacity > self.min_pool_bytes
            and self.compressed.utilization < 0.60
        ):
            # Contract pool to release RAM
            new_capacity = max(self.min_pool_bytes, curr_capacity - self.step_bytes)
            evicted = self.compressed.set_capacity(new_capacity)
            # Demote any evicted pages to swap
            for demoted_vpn, demoted_comp_bytes in evicted:
                demoted_entry = self.page_table.get_entry(demoted_vpn)
                if not (demoted_entry.swap_clean and self.swap.contains(demoted_vpn)):
                    decomp = self.compression_engine.decompress(demoted_comp_bytes)
                    self.swap.write(demoted_vpn, decomp.decompressed_data)
                    demoted_entry.swap_clean = True
                demoted_entry.tier = Tier.SWAP

            self.adaptation_events.append((self.time_step, "CONTRACT", new_capacity))

