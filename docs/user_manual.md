# User Manual: Tiered Virtual Memory Manager Simulator

A complete guide for running, configuring, and analyzing simulations using the CLI, experimental testbed, and interactive Streamlit dashboard.

---

## 1. System Requirements & Setup

### Requirements
- **Python**: 3.10, 3.11, or 3.12+
- **OS**: Windows, macOS, or Linux (cross-platform, runs completely in user space without administrator/root privileges)
- **Dependencies**: `numpy`, `pandas`, `matplotlib`, `streamlit`, `pytest`

### Setup Instructions
```bash
# 1. Create a virtual environment
python3 -m venv .venv

# 2. Activate the virtual environment
# On macOS / Linux:
source .venv/bin/activate
# On Windows:
# .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt
```

---

## 2. Running Simulations via the Command Line (`main.py`)

The simulator provides an intuitive CLI with built-in `--help` documentation and subcommands.

### 2.1 View Help
```bash
python main.py --help
python main.py simulate --help
python main.py experiments --help
```

### 2.2 Run a Single Simulation
```bash
# Run a 3-tier simulation on a Zipf workload with mixed compressible data
python main.py simulate --system tiered --workload zipf --content mixed --accesses 1000
```

### 2.3 Run a Comparative Benchmark (Baseline vs Tiered)
To compare both architectures side-by-side on the exact same access trace:
```bash
python main.py simulate --compare --workload zipf --content text --accesses 1000
```
**Sample Output:**
```
=================================================================
  VIRTUAL MEMORY SIMULATION RESULTS: BASELINE (2-TIER)
=================================================================
+--------------------------------------+------------------+
| Metric                               | Observed Value   |
+--------------------------------------+------------------+
| Total Memory Accesses                | 1,000            |
| DRAM Hits (Tier 0)                   | 793 (79.30%)     |
| Minor Faults (Tier 1 Compressed)     | 0 (0.00%)        |
| Major Faults (Tier 2 SSD Swap)       | 56 (5.60%)       |
| Average Memory Access Time (AMAT)    | 18,200.0 ns      |
+--------------------------------------+------------------+

=================================================================
  VIRTUAL MEMORY SIMULATION RESULTS: TIERED (3-TIER)
=================================================================
+--------------------------------------+---------------------+
| Metric                               | Observed Value      |
+--------------------------------------+---------------------+
| Total Memory Accesses                | 1,000               |
| DRAM Hits (Tier 0)                   | 793 (79.30%)        |
| Minor Faults (Tier 1 Compressed)     | 56 (5.60%)          |
| Major Faults (Tier 2 SSD Swap)       | 0 (0.00%)           |
| Average Memory Access Time (AMAT)    | 14,522.3 ns         |
| Effective In-Memory Capacity         | 151 pages (+135.9%) |
| Average Space Saving                 | 76.10%              |
| Speedup vs Baseline (AMAT)           | 1.25x faster        |
+--------------------------------------+---------------------+
```

### 2.4 CLI Configuration Options
| Parameter | Default | Description |
|---|---|---|
| `--system` | `tiered` | Choose `tiered` (3-tier) or `baseline` (2-tier) |
| `--compare` | `False` | Run both systems side-by-side |
| `--workload` | `zipf` | Access trace: `sequential`, `looping`, `zipf`, `uniform`, `phase_shifting` |
| `--content` | `mixed` | Page data: `mixed`, `text`, `zero`, `structured`, `random` |
| `--accesses` | `1000` | Total number of virtual page references |
| `--dram-frames` | `64` | Physical frames available in DRAM (Tier 0) |
| `--pool-pages` | `64` | Compressed RAM pool capacity (Tier 1) in 4KB page equivalents |
| `--virtual-pages` | `256` | Size of process virtual address space in pages |
| `--threshold` | `0.75` | Skip threshold ratio ($0 < \text{threshold} \le 1.0$) |
| `--algorithm` | `zlib` | Compression engine: `zlib` or `lzma` |
| `--compression-level` | `6` | Compression level (0-9) |
| `--fixed-cost` | `False` | Deterministic latency mode (compress=3,000ns, decompress=2,000ns) |
| `--export-csv` | `None` | Save step-by-step access log to CSV file |
| `--config` | `None` | Load parameters from a custom JSON config file |

---

## 3. Running the Automated Experiments (`run_experiments.py`)

To generate all 6 benchmark datasets and publication-quality graphs:
```bash
python run_experiments.py
```
This executes all benchmarks and stores files into `results/`:
- `results/exp1_baseline_vs_tiered.csv` & `exp1_baseline_vs_tiered_text.png`: AMAT & speedup across workloads.
- `results/exp2_pool_size_sweep.csv` & `exp2_pool_size_sweep.png`: Finding the pool capacity sweet spot.
- `results/exp3_content_types.csv` & `exp3_content_types.png`: Real compressibility & CPU latency by data type.
- `results/exp4_algorithms.csv` & `exp4_algorithms.png`: Compression algorithms comparison (zlib levels 1/6/9 vs lzma).
- `results/exp5_threshold_sweep.csv` & `exp5_threshold_sweep.png`: Compress-or-skip threshold sensitivity.
- `results/exp6_effective_capacity.csv` & `exp6_effective_capacity.png`: In-memory page expansion %.

---

## 4. Running the Streamlit Interactive Dashboard (`app.py`)

Launch the web GUI:
```bash
streamlit run app.py
```
Open `http://localhost:8501` in your browser.

### Features in the Dashboard:
1. **Interactive Sidebar**: Adjust workload patterns, page content, DRAM frames, pool size, and compression algorithms in real time.
2. **Live Visualizer Tab**:
   - Visual grid of memory frames (DRAM in Green, Compressed RAM in Blue, SSD Swap in Red).
   - Play/pause/step controls (`⏮`, `◀`, `▶`, `⏩`) with playhead slider to inspect any step.
   - Live telemetry: current event type (Hit, Minor Fault, Major Fault, Cold Fault), VPN, and latency incurred.
   - Dynamic real-time charts showing AMAT and tier occupancy over time.
3. **Compare Tab**: Side-by-side bar charts and speedup calculations on identical workloads.
4. **Benchmarks Tab**: Interactive viewer of all generated experimental graphs and CSV tables.
5. **Architecture & Viva Prep Tab**: Embedded OS concepts and viva cheat sheet.

---

## 5. Running the Test Suite (`pytest`)

Execute the complete test suite:
```bash
pytest -v
```
All 58 automated unit and integration tests will execute and verify data integrity, LRU behavior, and tier invariants.
