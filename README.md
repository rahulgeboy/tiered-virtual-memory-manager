# Tiered Virtual Memory Manager with Page Compression

A Python-based operating systems simulation demonstrating in-memory page compression hierarchies (**DRAM + Compressed RAM + SSD Swap**), inspired by Linux `zswap` and `zram`.

---

## 📌 Project Overview
In standard operating systems, when physical memory (RAM) is full, victim pages are evicted to an SSD or disk swap partition. However, reading a page from an SSD incurs a massive latency penalty (**~100,000 ns**) compared to reading from RAM (**~100 ns**)—a **1,000x slowdown** that causes disk thrashing.

This simulator models a **three-tier memory hierarchy**:
- **Tier 0 (Fast DRAM)**: Fast physical frames holding hot (recently accessed) uncompressed pages (100 ns latency).
- **Tier 1 (Compressed RAM Pool / zswap)**: Warm pages compressed using real CPU algorithms (`zlib` / `lzma`) and held in RAM. Faults from this tier (minor faults) take only **~8 to 12 µs** (CPU decompression) instead of 100 µs on disk.
- **Tier 2 (SSD Swap)**: Cold pages stored on simulated disk swap for cold eviction (100,000 ns latency).

The simulator measures **real compression ratios and CPU nanoseconds** using standard library compression engines on synthetic 4096-byte memory payloads, enforcing a **compress-or-skip** policy that bypasses Tier 1 when pages are incompressible.

---

## 🚀 Quickstart & Installation

### 1. Prerequisites
- Python 3.10+ (tested on Python 3.12)
- macOS, Linux, or Windows (100% user space, no admin/root rights required)

### 2. Setup Virtual Environment
```bash
python3 -m venv .venv
source .venv/bin/activate       # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

---

## 💻 How to Run

### 1. Run via CLI (`main.py`)
Run a side-by-side comparison between the Baseline (DRAM + SSD) and Tiered (DRAM + Compressed RAM + SSD) systems on a Zipf workload:
```bash
python main.py simulate --compare --workload zipf --content text --accesses 1000
```

Run a single simulation with custom options:
```bash
python main.py simulate --system tiered --workload looping --content mixed --accesses 1200 --dram-frames 64 --pool-pages 64
```

View all options:
```bash
python main.py --help
python main.py simulate --help
```

### 2. Run the Benchmark Experiment Suite (`run_experiments.py`)
Generate all 6 research benchmark datasets and publication-quality figures:
```bash
python run_experiments.py
```
This automatically produces CSV tables and high-resolution PNG plots in `results/`:
- `exp1_baseline_vs_tiered.csv` & `exp1_baseline_vs_tiered_text.png`
- `exp2_pool_size_sweep.csv` & `exp2_pool_size_sweep.png`
- `exp3_content_types.csv` & `exp3_content_types.png`
- `exp4_algorithms.csv` & `exp4_algorithms.png`
- `exp5_threshold_sweep.csv` & `exp5_threshold_sweep.png`
- `exp6_effective_capacity.csv` & `exp6_effective_capacity.png`
- `sample_tier_occupancy_over_time.png`

### 3. Launch the Interactive Dashboard (`app.py`)
Launch the Streamlit web dashboard:
```bash
streamlit run app.py
```
Visit `http://localhost:8501` to use:
- **Live Tier Visualizer**: Visual animated grid of DRAM frames, Compressed pool bytes, and SSD Swap.
- **Playback Controls**: Step forward, step back, and scrub playhead with live latency and fault callouts.
- **Compare Tab**: Direct side-by-side bar chart comparison and speedup multiplier.
- **Benchmark Gallery**: Interactive viewer for all experiment graphs.
- **Viva Prep**: Embedded OS architecture and cheat sheet.

### 4. Run the Test Suite (`pytest`)
Run all 58 automated unit tests with comprehensive assertions and invariants:
```bash
pytest -v
```

---

## 📸 Sample Visualizations & Screenshots

When running `app.py` or `run_experiments.py`, visual artifacts are placed in `results/`:
- **Tier Grid Visualizer**: Displays 3 color-coded sections:
  - 🟢 **Tier 0 DRAM** (Green cells): Shows resident pages and active LRU state.
  - 🔵 **Tier 1 Compressed RAM** (Blue cells): Shows compressed in-memory pool with byte usage progress.
  - 🔴 **Tier 2 SSD Swap** (Red cells): Shows swapped pages.
- **AMAT vs Pool Size Plot** (`results/exp2_pool_size_sweep.png`): Demonstrates the "sweet spot" where AMAT drops precipitously as pool capacity reaches 32 pages, and plateaus thereafter.
- **Content-Type Compressibility Plot** (`results/exp3_content_types.png`): Shows the contrast between Zero pages (99.4% savings), Text pages (78.5% savings), and Random pages (incompressible, expanding slightly).

---

## 📚 Glossary of Operating System Terms

- **Page**: A fixed-length contiguous block of virtual memory (typically 4096 bytes / 4KB).
- **Page Table**: An operating system kernel data structure mapping virtual page numbers (VPN) to physical memory locations or backing store tiers.
- **Page Table Entry (PTE)**: A single record in the page table containing flags (resident tier, dirty bit, access timestamps, access count).
- **Page Fault**: An interrupt raised by hardware (MMU) when an accessed page is not resident in physical DRAM frames.
- **Minor Fault (Soft Fault)**: A page fault where the page resides in system RAM (in the compressed pool). Handled without disk I/O via fast CPU decompression (~8-12 µs).
- **Major Fault (Hard Fault)**: A page fault where the page must be read from disk / SSD swap storage, requiring expensive secondary storage I/O (~100 µs).
- **Demotion**: Moving an evicted victim page from a faster, higher tier to a slower, lower tier (DRAM -> Compressed RAM -> SSD Swap).
- **Promotion**: Moving an accessed page from a slower tier back to physical DRAM.
- **LRU (Least Recently Used)**: A page replacement policy that evicts the page that has not been referenced for the longest period of time.
- **Compression Ratio**: Ratio of compressed size to uncompressed size ($\text{compressed\_size} / \text{raw\_size}$). Lower values indicate superior space savings.
- **AMAT (Average Memory Access Time)**: The weighted average latency incurred per memory access across hits and faults.
- **Workload**: The sequence and temporal distribution of memory references generated by running software processes.

---

## 🎓 University Lab Viva Q&A (16 Comprehensive Questions)

### Q1: What is demand paging and why is it used?
**Answer**: Demand paging is a memory management technique where pages are brought into physical DRAM only when an active instruction attempts to access them. It maximizes physical RAM utilization by never pre-allocating memory for unused program segments or arrays.

### Q2: What is the difference between a Minor Fault and a Major Fault?
**Answer**: A **Minor Fault** (soft fault) occurs when the desired page is already present in system RAM (such as in an in-memory compressed cache like zswap or page cache), so it is serviced quickly by CPU decompression without disk I/O. A **Major Fault** (hard fault) requires reading the page from physical secondary storage (SSD/HDD), which is roughly 10x to 1,000x slower.

### Q3: What is Linux zswap and how does it differ from Linux zram?
**Answer**:
- **zswap** is a compressed writeback cache that sits in front of a real swap device (SSD/HDD). Evicted pages are compressed and cached in RAM; if the zswap pool fills up, the oldest compressed pages are written back to the physical swap partition.
- **zram** creates a standalone compressed block device in RAM without requiring any underlying physical disk.

### Q4: Why is the compressed pool capacity measured in BYTES rather than a page count?
**Answer**: In physical DRAM, every frame is strictly 4096 bytes. However, compressed pages have variable lengths depending on their entropy (e.g., 26 bytes for zero pages vs 880 bytes for text). Measuring capacity in bytes reflects real physical memory consumption and prevents internal fragmentation.

### Q5: What is the "Compress-or-Skip" policy, and why is it vital?
**Answer**: When high-entropy data (such as encrypted files, compressed archives, or random data) is compressed, the output often exceeds 4096 bytes. The compress-or-skip policy checks if $\text{compressed\_size} / \text{PAGE\_SIZE} > 0.75$. If so, it bypasses the compressed pool and writes straight to SSD swap, preventing pool pollution and preserving RAM for compressible pages.

### Q6: Why did the Tiered system show NO benefit (or slight slowdown) on random incompressible data?
**Answer**: For incompressible data, every eviction causes the CPU to spend ~98 µs attempting compression. Once rejected by the skip threshold, the page is still written to SSD swap. Thus, the system incurred the full SSD latency **plus** wasted CPU compression cycles.

### Q7: What is the clean-page swap-write bypass optimization?
**Answer**: If a page was brought into DRAM from swap for a read-only access and never modified (`PTE.dirty == False`), an identical copy already exists on SSD swap. When that page is evicted, the OS suppresses the redundant physical disk write, saving 100 µs of I/O latency and flash wear.

### Q8: How does temporal locality impact the hit ratio under LRU?
**Answer**: Temporal locality states that memory locations accessed recently are likely to be accessed again in the near future. LRU keeps recently referenced pages at the tail of its access queue, ensuring the hot working set remains in fast physical memory.

### Q9: Why is a simple Looping workload a pathological worst-case for pure LRU?
**Answer**: If an application loops over $N$ pages and DRAM holds only $N-1$ frames, every single access targets the page that was evicted at the beginning of the previous loop. Consequently, the cache hit rate drops to **0%**.

### Q10: How does a three-tier system mitigate the LRU looping pathology?
**Answer**: Because compressed pages consume significantly less space, the in-memory capacity expands from 64 pages to over 150+ pages. If the loop size is 76 pages, it fits entirely within DRAM + Compressed RAM, turning 100% of would-be SSD major faults into fast in-memory minor faults.

### Q11: How is $O(1)$ LRU replacement implemented in this simulator?
**Answer**: The simulator uses Python's `collections.OrderedDict`, an internal doubly linked list with a hash table. Cache lookups, `move_to_end()` promotions, and `popitem(last=False)` victim evictions all execute in $O(1)$ time.

### Q12: What is AMAT and how is it calculated in a 3-tier hierarchy?
**Answer**: Average Memory Access Time is:
$$\text{AMAT} = t_{\text{DRAM}} + P_{\text{minor}} \cdot t_{\text{decomp}} + P_{\text{major}} \cdot t_{\text{SSD\_read}} + P_{\text{evict}} \cdot (t_{\text{comp}} + t_{\text{SSD\_write}})$$
It quantifies the effective latency experienced per memory reference.

### Q13: What happens when the compressed pool byte capacity overflows?
**Answer**: The least-recently-used compressed pages are evicted from the pool: they are decompressed (or written out) to SSD swap, freeing byte headroom for the incoming newly compressed page.

### Q14: How does Adaptive Pool Sizing (`AdaptiveTieredManager`) work?
**Answer**: It measures the sliding-window rate of major faults. If major faults exceed a high watermark ($\ge 10\%$), it dynamically expands pool capacity to mitigate SSD thrashing. If major faults subside and pool utilization is low, it contracts the pool to return RAM to the operating system.

### Q15: What is the space saving formula and how does it relate to compression ratio?
**Answer**:
$$\text{Compression Ratio} = \frac{\text{Compressed Size}}{\text{Raw Size}}, \quad \text{Space Saving \%} = (1 - \text{Compression Ratio}) \times 100$$
A ratio of 0.20 corresponds to an 80% memory space saving.

### Q16: Why is lossless compression (like zlib/DEFLATE) mandatory for virtual memory paging?
**Answer**: Operating system memory contains executable machine code, pointers, and critical data structures. Any bit distortion (lossy compression) would corrupt instructions, cause kernel panics, or crash applications. Lossless algorithms guarantee 100% byte-for-byte round-trip fidelity.

---

## 📁 Repository Directory Structure
```
tiered_vm/
├── README.md                      # Project manual, installation, glossary & viva prep
├── requirements.txt              # Standard library + minimal dependencies
├── config.py                     # SimulationConfig dataclass & parameter validation
├── main.py                       # CLI entry point (simulate, experiments, compare)
├── app.py                        # Streamlit animated 3-tier visualizer dashboard
├── run_experiments.py            # Automated benchmark runner across 6 experiments
├── core/
│   ├── __init__.py
│   ├── page_table.py             # PageTable & PageTableEntry (PTE) state tracking
│   ├── dram_tier.py              # Tier 0: LRU OrderedDict physical frames
│   ├── compressed_tier.py        # Tier 1: Byte-capacity bounded compressed pool
│   ├── swap_tier.py              # Tier 2: SSD Swap device with dirty-write bypass
│   ├── cost_model.py             # AMAT and latency accounting model
│   ├── compression.py            # Real zlib & lzma compression engines with telemetry
│   └── memory_manager.py         # MemoryManager ABC, Baseline, Tiered, AdaptiveTiered
├── workloads/
│   ├── __init__.py
│   ├── content_generator.py      # Realistic 4KB page content (Zero, Text, Struct, Random)
│   └── access_patterns.py        # Trace generators (Sequential, Looping, Zipf, Uniform, Phase)
├── analysis/
│   ├── __init__.py
│   ├── metrics.py                # SimulationMetrics and Pandas aggregation
│   └── plots.py                  # Matplotlib publication figures
├── tests/
│   ├── __init__.py
│   ├── test_config_validation.py # Config validation error tests
│   ├── test_page_table.py        # Page table bounds & state tracking tests
│   ├── test_compression.py       # Round-trip integrity & timing tests
│   ├── test_tiers.py             # DRAM, Compressed, and Swap storage tier tests
│   ├── test_workloads.py         # Content & workload pattern generators tests
│   └── test_manager.py           # Eviction chains, fault logic, & invariant tests
├── docs/
│   ├── architecture.md           # System design & Mermaid flowcharts
│   ├── design_notes.md           # Algorithmic notes, AMAT derivation & findings
│   ├── user_manual.md            # Detailed operations & CLI reference
│   └── test_report.md            # Automated pytest summary + 10 manual test cases
└── results/                      # Output CSVs and high-resolution PNG plots
```
