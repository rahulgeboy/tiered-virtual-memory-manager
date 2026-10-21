# Design Notes & Operating System Theory: Tiered Virtual Memory Manager

This document provides deep technical explanations of the operating system algorithms, cost models, experimental findings, and trade-offs implemented in this project.

---

## 1. Operating System Concepts & Algorithms

### 1.1 Why In-Memory Page Compression (Linux zswap / zram)?
In traditional virtual memory architectures, physical DRAM is backed directly by a secondary storage device (HDD or SSD). When DRAM becomes full, the OS evicts victim pages to swap.
- **Physical DRAM Access**: ~100 nanoseconds.
- **Fast NVMe SSD Access**: ~100,000 nanoseconds (100 microseconds).
- **Latency Discrepancy**: A factor of **1,000x**.

When a working set marginally exceeds physical DRAM capacity, an operating system without compressed RAM falls into **thrashing**: the CPU spends the vast majority of its clock cycles idle, waiting for I/O transfers across the PCIe/SATA bus.

**Linux `zswap` and `zram` solve this dilemma:**
Modern multi-core CPUs can compress or decompress a 4096-byte memory page in roughly **8 to 12 microseconds** (8,000 - 12,000 ns). By inserting a compressed RAM pool between DRAM and SSD:
$$\text{Latency of Minor Fault (CPU Decompression)} \approx 10\,\mu\text{s} \ll \text{Latency of Major Fault (SSD Read)} \approx 100\,\mu\text{s}$$
Serving faults from compressed RAM is approximately **10x faster** than reading from an SSD!

### 1.2 OrderedDict for $O(1)$ LRU Management
Many naive memory simulators track LRU timestamps in a linear list or array, requiring an $O(N)$ scan on every single eviction to locate the minimum timestamp.
This simulator utilizes Python's `collections.OrderedDict`, implemented internally in C as a doubly linked list combined with a hash table:
- **Lookup / Hit**: $O(1)$ hash table lookup.
- **LRU Refresh**: `move_to_end(vpn)` splices the node to the tail in $O(1)$.
- **LRU Eviction**: `popitem(last=False)` pops the head node in $O(1)$.
This guarantees that simulations with hundreds of thousands of accesses execute in seconds without memory management overhead.

### 1.3 Byte-Capacity vs Fixed-Slot Pool Accounting
In standard DRAM, frames are uniformly fixed at 4096 bytes. However, compressed pages have variable lengths:
- Zero pages compress to **~26 bytes** (99.4% savings).
- English text pages compress to **~880 bytes** (78.5% savings).
- Structured binary records compress to **~1,300 bytes** (68.2% savings).

If the compressed pool were budgeted by a fixed page slot count, a zero page would consume the same budget as a poorly compressed page. To model real OS behavior (such as Linux `zbud` and `zsmalloc` allocators), `CompressedTier` measures capacity strictly in **BYTES**:
$$\text{Free Bytes} = \text{Capacity Bytes} - \sum_{p \in \text{Pool}} \text{len}(\text{compressed\_data}(p))$$
Evictions are triggered only when the byte size of an incoming compressed page exceeds available headroom.

### 1.4 Compress-or-Skip Policy
Compression is not a free lunch; it consumes CPU cycles. When high-entropy data (e.g. encrypted payloads, pre-compressed JPEG/MP4 media, or random bytes) is compressed with lossless algorithms like zlib:
1. The compressed output is often larger than 4096 bytes due to compression headers and symbol tables.
2. The page provides zero space savings.
3. Placing it in the compressed pool wastes RAM headroom and pushes out warm, compressible pages.

To protect the system, the manager enforces a **Compress-or-Skip Threshold**:
$$\text{If } \frac{\text{compressed\_size}}{\text{PAGE\_SIZE}} > 0.75 \implies \text{Bypass Tier 1 and send straight to SSD Swap}$$
This prevents compressed pool pollution and ensures only pages with meaningful space savings remain in memory.

### 1.5 Clean Page Swap-Write Bypass
When a page is paged in from SSD swap into DRAM for a **read-only** access, an identical copy already exists on the SSD swap partition. If the page is subsequently evicted back to swap without ever being written to (`PTE.dirty == False` and `PTE.swap_clean == True`), the OS **skips the physical write to SSD**. This eliminates redundant disk I/O, saves 100,000 ns of latency, and preserves SSD flash endurance.

---

## 2. Mathematical Cost Model & AMAT Derivation

Average Memory Access Time (AMAT) is the central metric evaluating virtual memory efficiency.

### 2.1 Theoretical AMAT Equation
Let:
- $t_{\text{DRAM}}$ = DRAM access latency (100 ns)
- $t_{\text{decomp}}$ = CPU decompression latency (~8,000 - 12,000 ns)
- $t_{\text{comp}}$ = CPU compression latency (~30,000 - 100,000 ns)
- $t_{\text{SSD\_read}}$ = SSD read latency (100,000 ns)
- $t_{\text{SSD\_write}}$ = SSD write latency (100,000 ns)
- $P_{\text{hit}}$ = Probability of a DRAM hit ($N_{\text{hit}} / N_{\text{total}}$)
- $P_{\text{minor}}$ = Probability of a minor fault ($N_{\text{minor}} / N_{\text{total}}$)
- $P_{\text{major}}$ = Probability of a major fault ($N_{\text{major}} / N_{\text{total}}$)
- $P_{\text{cold}}$ = Probability of a cold first-touch fault ($N_{\text{cold}} / N_{\text{total}}$)

In our model:
$$\text{AMAT} = \frac{\sum_{i=1}^{N} \text{cost}(i)}{N}$$
Where per-access cost is:
$$\text{cost}(i) = t_{\text{service}} + t_{\text{eviction\_overhead}}$$

1. **DRAM Hit**:
   $$\text{cost} = t_{\text{DRAM}} = 100\text{ ns}$$
2. **Minor Fault (Decompressed from Tier 1)**:
   $$\text{cost} = t_{\text{DRAM}} + t_{\text{decomp}} + [\text{eviction overhead if DRAM was full}]$$
3. **Major Fault (Read from Tier 2 SSD)**:
   $$\text{cost} = t_{\text{DRAM}} + t_{\text{SSD\_read}} + [\text{eviction overhead if DRAM was full}]$$
4. **Cold Fault (First Touch Allocation)**:
   $$\text{cost} = t_{\text{DRAM}} + [\text{eviction overhead if DRAM was full}]$$

---

## 3. In-Depth Analysis of Experimental Results

### 3.1 Why Tiered VM Wins on Skewed (Zipf) and Looping Workloads
In our benchmarks (**Experiment 1** & **Experiment 2**):
- On the **Zipf (Hot-Cold)** workload with compressible data:
  - Baseline experienced **137 major faults** (costing $137 \times 100,000\text{ ns} = 13,700,000\text{ ns}$).
  - Tiered experienced **0 major faults**; all 137 faults were absorbed as minor faults in Tier 1.
  - AMAT decreased from **21,700 ns** down to **18,387 ns** (up to **1.18x - 1.25x speedup**).
- On the **Phase-Shifting** workload with compressible data:
  - Tiered achieved a **1.16x speedup**, absorbing 234 faults in the warm compressed pool as working sets migrated.

### 3.2 Why Incompressible Random Workloads Show No Benefit
A crucial real-world finding observed in **Experiment 1**:
- For **Incompressible Random** data, Tiered AMAT was **higher** than Baseline:
  - Baseline AMAT: **115,033 ns**
  - Tiered AMAT: **208,404 ns** (Speedup = **0.55x**, i.e. 45% slowdown!)

**Operating System Explanation:**
When data is random and incompressible:
1. Every evicted DRAM page is sent to the compression engine.
2. The CPU expends ~98 µs attempting compression.
3. The compressor discovers the output is 4,107 bytes (larger than 4096 bytes).
4. The compress-or-skip threshold triggers, rejecting the page from Tier 1.
5. The page is then written to SSD swap anyway.
**Conclusion**: The system paid the full SSD write cost **plus** the useless CPU compression cost! This accurately reflects real-world Linux kernel behavior: running `zswap` on already-compressed databases or video streams wastes CPU without saving RAM.

### 3.3 The Pool Size "Sweet Spot" (Experiment 2)
As compressed pool capacity was swept from 0 to 128 pages:
- **0 Pages**: AMAT = 41,129 ns (no pool; CPU compression attempt overhead).
- **8 Pages**: AMAT = 31,114 ns (58 major faults still occur).
- **16 Pages**: AMAT = 26,214 ns (23 major faults).
- **32 Pages**: AMAT = **18,387 ns** (**Sweet Spot**; 0 major faults).
- **64 & 128 Pages**: AMAT plateaus at ~19,200 ns.
Once the compressed pool is large enough to contain the warm working set, further memory allocation yields diminishing returns. Allocating too much RAM to the pool robs physical memory from active applications.

---

## 4. Stretch Feature: Adaptive Tiered Management

The simulator includes `AdaptiveTieredManager`, which models Linux dynamic memory pressure balancing:
1. **Pressure Metric**: A sliding window of the last $W$ accesses ($W=25$) monitors the frequency of major faults:
   $$\text{Major Fault Rate} = \frac{\sum \text{Major Faults in Window}}{W}$$
2. **Expansion**: When $\text{Major Fault Rate} \ge 0.10$ (indicating SSD thrashing), the manager dynamically increases pool capacity by `step_bytes` (+16 KB), up to `max_pool_bytes`.
3. **Contraction**: When major faults drop to $\le 0.02$ and pool utilization is low, the manager contracts pool capacity to release RAM back to the host operating system. Any pages evicted during contraction are demoted cleanly to swap.

---

## 5. Assumptions, Limitations & Future Work

1. **Single-Threaded Model**:
   - *Current*: Decompression and compression are simulated sequentially on the accessing thread.
   - *Future Work*: Multi-threaded decompression pools (simulating Linux kernel crypto async API `acomp` with hardware offload such as Intel IAA).
2. **Linear Page Table**:
   - *Current*: Flat virtual address space.
   - *Future Work*: Multi-level hierarchical page tables (x86-64 4-level PML4 / 5-level paging) with TLB simulation and translation latency overhead.
3. **Machine Learning Compression Predictor**:
   - *Future Work*: Lightweight feature extraction (entropy sampling of the first 64 bytes) to predict compressibility in $O(1)$ without invoking the full zlib compressor.
