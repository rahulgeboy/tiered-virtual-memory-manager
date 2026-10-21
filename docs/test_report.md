# Test Report: Tiered Virtual Memory Manager Simulator

This document provides verification results for the automated unit tests and manual test cases.

---

## 1. Automated Test Suite Summary (`pytest`)

The automated test suite contains **58 unit and integration tests** verifying all core invariant assertions, compression integrity, and tier transitions.

```
============================= test session starts ==============================
platform darwin -- Python 3.12.3, pytest-9.1.1, pluggy-1.7.0
rootdir: /Users/rahul/Desktop/virtual_memory_paging_project
collected 58 items

tests/test_compression.py::test_roundtrip_integrity_zlib PASSED          [ 1%]
tests/test_compression.py::test_roundtrip_integrity_lzma PASSED          [ 3%]
tests/test_compression.py::test_compressibility_hierarchy PASSED         [ 5%]
tests/test_compression.py::test_zlib_levels[1] PASSED                    [ 6%]
tests/test_compression.py::test_zlib_levels[6] PASSED                    [ 8%]
tests/test_compression.py::test_zlib_levels[9] PASSED                    [10%]
tests/test_compression.py::test_invalid_algorithm PASSED                 [12%]
tests/test_config_validation.py::test_default_config_valid PASSED        [13%]
tests/test_config_validation.py::test_invalid_dram_frames[0] PASSED      [15%]
tests/test_config_validation.py::test_invalid_dram_frames[-1] PASSED     [17%]
tests/test_config_validation.py::test_invalid_dram_frames[-64] PASSED    [18%]
tests/test_config_validation.py::test_invalid_pool_bytes[-1] PASSED      [20%]
tests/test_config_validation.py::test_invalid_pool_bytes[-4096] PASSED   [22%]
tests/test_config_validation.py::test_invalid_compress_threshold[0.0] PASSED [24%]
tests/test_config_validation.py::test_invalid_compress_threshold[-0.1] PASSED [25%]
tests/test_config_validation.py::test_invalid_compress_threshold[1.01] PASSED [27%]
tests/test_config_validation.py::test_invalid_compress_threshold[2.5] PASSED [29%]
tests/test_config_validation.py::test_invalid_virtual_address_space[0] PASSED [31%]
tests/test_config_validation.py::test_invalid_virtual_address_space[-10] PASSED [32%]
tests/test_config_validation.py::test_negative_latencies[dram_latency_ns] PASSED [34%]
tests/test_config_validation.py::test_negative_latencies[ssd_read_latency_ns] PASSED [36%]
tests/test_config_validation.py::test_negative_latencies[ssd_write_latency_ns] PASSED [37%]
tests/test_config_validation.py::test_negative_latencies[fixed_compress_latency_ns] PASSED [39%]
tests/test_config_validation.py::test_negative_latencies[fixed_decompress_latency_ns] PASSED [41%]
tests/test_config_validation.py::test_invalid_compression_algorithm PASSED [43%]
tests/test_config_validation.py::test_invalid_compression_level[-1] PASSED [44%]
tests/test_config_validation.py::test_invalid_compression_level[10] PASSED [46%]
tests/test_config_validation.py::test_invalid_compression_level[99] PASSED [48%]
tests/test_config_validation.py::test_config_json_roundtrip PASSED       [50%]
tests/test_manager.py::test_baseline_manager_lifecycle PASSED            [51%]
tests/test_manager.py::test_tiered_manager_minor_fault PASSED            [53%]
tests/test_manager.py::test_compress_or_skip_incompressible PASSED       [55%]
tests/test_manager.py::test_compressed_pool_overflow_eviction_chain PASSED [56%]
tests/test_manager.py::test_data_integrity_roundtrip_after_swap_and_compression PASSED [58%]
tests/test_manager.py::test_clean_page_swap_write_skipped PASSED         [60%]
tests/test_manager.py::test_adaptive_tiered_manager_expansion PASSED     [62%]
tests/test_page_table.py::test_page_table_init PASSED                    [63%]
tests/test_page_table.py::test_invalid_vas_size PASSED                   [65%]
tests/test_page_table.py::test_vpn_bounds_check[-1] PASSED               [67%]
tests/test_page_table.py::test_vpn_bounds_check[64] PASSED               [68%]
tests/test_page_table.py::test_vpn_bounds_check[100] PASSED              [70%]
tests/test_page_table.py::test_pte_access_tracking PASSED                [72%]
tests/test_page_table.py::test_tier_counts PASSED                        [74%]
tests/test_tiers.py::test_dram_tier_lru PASSED                           [75%]
tests/test_tiers.py::test_dram_capacity_enforcement PASSED               [77%]
tests/test_tiers.py::test_compressed_tier_byte_capacity PASSED           [79%]
tests/test_tiers.py::test_compressed_tier_dynamic_resize PASSED          [81%]
tests/test_tiers.py::test_swap_tier PASSED                               [82%]
tests/test_workloads.py::test_content_generator_sizes_and_types PASSED   [84%]
tests/test_workloads.py::test_content_generator_reproducibility PASSED   [86%]
tests/test_workloads.py::test_content_mutation_on_write PASSED           [87%]
tests/test_workloads.py::test_mixed_profile_distribution PASSED          [89%]
tests/test_workloads.py::test_workload_patterns_length_and_bounds[SEQUENTIAL] PASSED [91%]
tests/test_workloads.py::test_workload_patterns_length_and_bounds[LOOPING] PASSED [93%]
tests/test_workloads.py::test_workload_patterns_length_and_bounds[ZIPF] PASSED [94%]
tests/test_workloads.py::test_workload_patterns_length_and_bounds[UNIFORM] PASSED [96%]
tests/test_workloads.py::test_workload_patterns_length_and_bounds[PHASE_SHIFTING] PASSED [98%]
tests/test_workloads.py::test_workload_reproducibility PASSED            [100%]

============================== 58 passed in 0.21s ==============================
```

---

## 2. Manual Test Cases (Verification Matrix)

### Test Case 1: First-Touch Cold Fault Allocation
- **Objective**: Verify that accessing an unmapped virtual page registers as `COLD_FAULT`, allocates 4096 bytes, and brings it into DRAM.
- **Inputs**: `SimulationConfig(dram_frames=4)`, access `vpn=0, is_write=False`.
- **Expected Output**: `record.event_type == COLD_FAULT`, `tier_before == UNMAPPED`, `tier_after == DRAM`, `dram.frame_count == 1`.
- **Actual Output**: Match. `COLD_FAULT` recorded, page 0 placed in DRAM.
- **Status**: **PASS**

### Test Case 2: DRAM Cache Hit and LRU Refresh
- **Objective**: Verify that accessing an already-resident page registers as `HIT`, charges 100 ns, and moves the page to the MRU position.
- **Inputs**: Pre-load pages 0, 1 into DRAM. Access page 0.
- **Expected Output**: `record.event_type == HIT`, cost = 100 ns, page 0 becomes newest item in DRAM `OrderedDict`.
- **Actual Output**: Match. Latency = 100 ns, head of OrderedDict becomes page 1.
- **Status**: **PASS**

### Test Case 3: Tier 1 Demotion on DRAM Eviction
- **Objective**: Verify that when DRAM is full, evicting a compressible page (`TEXT_LIKE`) compresses and inserts it into the `CompressedTier` rather than SSD swap.
- **Inputs**: `dram_frames=2, pool_bytes=16384`. Access pages 0, 1, then 2 (`TEXT_LIKE`).
- **Expected Output**: Page 0 evicted from DRAM into Compressed Tier. `PTE(0).tier == COMPRESSED`, `compressed.page_count == 1`.
- **Actual Output**: Match. Page 0 resident in compressed pool with compressed size ~880 bytes.
- **Status**: **PASS**

### Test Case 4: Minor Fault Promotion (Tier 1 -> Tier 0)
- **Objective**: Verify that accessing a page resident in Compressed RAM decompresses it into DRAM and deletes the compressed copy.
- **Inputs**: Page 0 resident in `COMPRESSED`. Access page 0.
- **Expected Output**: `record.event_type == MINOR_FAULT`, `PTE(0).tier == DRAM`, `compressed.contains(0) == False`, cost = DRAM latency + decompress latency.
- **Actual Output**: Match. `MINOR_FAULT` recorded, cost = 100 ns + ~8,500 ns, page removed from compressed pool.
- **Status**: **PASS**

### Test Case 5: Compress-or-Skip Incompressible Bypass
- **Objective**: Verify that high-entropy random pages with `compressed_size / 4096 > 0.75` bypass Tier 1 and go directly to SSD Swap.
- **Inputs**: `dram_frames=2, pool_bytes=16384, threshold=0.75, content=RANDOM`. Access pages 0, 1, then 2.
- **Expected Output**: Page 0 bypasses Compressed Tier. `PTE(0).tier == SWAP`, `compressed.page_count == 0`.
- **Actual Output**: Match. Page 0 placed on SSD swap, 0 bytes used in compressed pool.
- **Status**: **PASS**

### Test Case 6: Compressed Pool Byte Overflow Eviction
- **Objective**: Verify that when the compressed pool byte budget is exceeded, least-recently-used compressed pages are evicted to SSD swap.
- **Inputs**: `dram_frames=1, pool_bytes=80`. Access pages 0 through 5 (`ZERO` content, ~26 bytes each).
- **Expected Output**: At least 3 pages demoted to SSD swap because 80-byte budget cannot hold 5 compressed pages.
- **Actual Output**: Match. `swap.page_count == 3`, `compressed.used_bytes <= 80`.
- **Status**: **PASS**

### Test Case 7: Clean Page Swap-Write Suppression
- **Objective**: Verify that a clean page read from swap does not incur an SSD write latency when demoted back to swap.
- **Inputs**: Page 0 brought from swap via read (`is_write=False`), then evicted again without modification.
- **Expected Output**: `eviction_ssd_write_latency_ns == 0`, `swap_clean == True`.
- **Actual Output**: Match. SSD write skipped, 0 ns write latency charged.
- **Status**: **PASS**

### Test Case 8: Dirty Page Mutation & Recompression
- **Objective**: Verify that write accesses mark PTE dirty, invalidate `swap_clean`, and mutate content bytes so subsequent compression reflects modified data.
- **Inputs**: Page 0 in DRAM, execute write access `is_write=True`.
- **Expected Output**: `PTE(0).dirty == True`, `PTE(0).swap_clean == False`, raw bytes mutated.
- **Actual Output**: Match. Modified content verified, dirty bit set.
- **Status**: **PASS**

### Test Case 9: Configuration Validation Error Handling
- **Objective**: Verify that invalid configurations (negative frames, invalid algorithm, invalid threshold) fail fast with descriptive `ValueError`.
- **Inputs**: `SimulationConfig(dram_frames=-5)`, `SimulationConfig(compress_skip_threshold=1.5)`.
- **Expected Output**: `ValueError: dram_frames must be positive`, `ValueError: compress_skip_threshold must be in range (0.0, 1.0]`.
- **Actual Output**: Match. Clean descriptive `ValueError` raised without crash.
- **Status**: **PASS**

### Test Case 10: Full Round-Trip Page Content Integrity
- **Objective**: Verify that page contents remain 100% byte-identical after traversing DRAM -> Compressed RAM -> SSD Swap -> DRAM.
- **Inputs**: Write page 0 with known data buffer, evict through compression and swap, then fault back into DRAM.
- **Expected Output**: `dram.read(0) == original_bytes`.
- **Actual Output**: Match. Exact byte-for-byte equality confirmed.
- **Status**: **PASS**
