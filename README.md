# Tiered Virtual Memory Manager with Page Compression

A Python-based operating systems simulation demonstrating in-memory page compression hierarchies (**DRAM + Compressed RAM + SSD Swap**), inspired by Linux `zswap` and `zram`.

---

# Project Overview
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
