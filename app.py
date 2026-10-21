"""Interactive Streamlit Dashboard for Tiered Virtual Memory Manager Simulator."""

from __future__ import annotations

import os
# Configure headless matplotlib cache
os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")

import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import streamlit as st

from analysis.metrics import MetricsCalculator, SimulationMetrics
from config import ContentType, EventType, SimulationConfig, Tier, WorkloadPattern
from core.memory_manager import AccessRecord, BaselineManager, MemoryManager, TieredManager
from workloads.access_patterns import WorkloadGenerator
from workloads.content_generator import PageContentGenerator

# Page configuration
st.set_page_config(
    page_title="Tiered VM Manager Simulator",
    page_icon="💾",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom Styling
st.markdown(
    """
    <style>
    .main-title { font-size: 2.2rem; font-weight: 800; color: #3b82f6; margin-bottom: 0.2rem; }
    .sub-title { font-size: 1.05rem; color: #94a3b8; margin-bottom: 1.2rem; }
    .tier-box {
        border-radius: 8px;
        padding: 14px 16px;
        margin-bottom: 10px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.2);
    }
    .dram-card {
        background: linear-gradient(135deg, #064e3b 0%, #047857 100%) !important;
        border-left: 6px solid #10b981 !important;
    }
    .comp-card {
        background: linear-gradient(135deg, #1e3a8a 0%, #2563eb 100%) !important;
        border-left: 6px solid #3b82f6 !important;
    }
    .swap-card {
        background: linear-gradient(135deg, #7f1d1d 0%, #dc2626 100%) !important;
        border-left: 6px solid #ef4444 !important;
    }
    .tier-box h4 {
        color: #ffffff !important;
        font-weight: 700 !important;
        margin: 0 0 4px 0 !important;
        font-size: 16px !important;
    }
    .tier-box p {
        margin: 0 !important;
        font-size: 12.5px !important;
        font-weight: 500 !important;
    }
    .dram-card p { color: #a7f3d0 !important; }
    .comp-card p { color: #bfdbfe !important; }
    .swap-card p { color: #fecaca !important; }

    .badge-hit { background-color: #10b981; color: white; padding: 5px 10px; border-radius: 5px; font-weight: bold; font-size: 14px; }
    .badge-minor { background-color: #f59e0b; color: white; padding: 5px 10px; border-radius: 5px; font-weight: bold; font-size: 14px; }
    .badge-major { background-color: #ef4444; color: white; padding: 5px 10px; border-radius: 5px; font-weight: bold; font-size: 14px; }
    .badge-cold { background-color: #6366f1; color: white; padding: 5px 10px; border-radius: 5px; font-weight: bold; font-size: 14px; }

    .cell-grid {
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
        min-height: 80px;
        max-height: 250px;
        overflow-y: auto;
        padding: 10px;
        background: #0f172a;
        border: 1px solid #334155;
        border-radius: 8px;
    }
    .page-cell {
        min-width: 68px;
        height: 56px;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        border-radius: 6px;
        padding: 4px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.3);
        transition: transform 0.1s ease;
    }
    .dram-cell {
        background: linear-gradient(180deg, #10b981 0%, #059669 100%) !important;
        border: 1.5px solid #34d399 !important;
    }
    .comp-cell {
        background: linear-gradient(180deg, #3b82f6 0%, #2563eb 100%) !important;
        border: 1.5px solid #60a5fa !important;
    }
    .swap-cell {
        background: linear-gradient(180deg, #ef4444 0%, #dc2626 100%) !important;
        border: 1.5px solid #f87171 !important;
    }
    .cell-vpn {
        font-size: 13.5px !important;
        font-weight: 800 !important;
        color: #ffffff !important;
        line-height: 1.1 !important;
        letter-spacing: 0.5px;
    }
    .cell-sub {
        font-size: 10px !important;
        font-weight: 600 !important;
        color: rgba(255, 255, 255, 0.9) !important;
        margin-top: 2px !important;
    }
    .cell-active-tag {
        font-size: 9px !important;
        font-weight: 900 !important;
        background: #fbbf24 !important;
        color: #78350f !important;
        padding: 1px 4px !important;
        border-radius: 3px !important;
        margin-top: 2px !important;
    }
    .active-inspector-box {
        background: #1e293b;
        border: 2px solid #3b82f6;
        border-radius: 8px;
        padding: 12px 18px;
        margin-bottom: 14px;
        display: flex;
        align-items: center;
        justify-content: space-between;
        color: #f8fafc;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_data
def run_simulation_cached(
    system_type: str,
    workload_str: str,
    content_str: str,
    accesses: int,
    dram_frames: int,
    pool_pages: int,
    vas: int,
    threshold: float,
    algorithm: str,
    compression_level: int,
    seed: int,
    fixed_cost: bool,
) -> Tuple[List[Dict], Dict]:
    """Execute simulation run and return serialized records and metrics."""
    config = SimulationConfig(
        page_size=4096,
        dram_frames=dram_frames,
        compressed_pool_bytes=pool_pages * 4096,
        virtual_address_space=vas,
        compress_skip_threshold=threshold,
        compression_algorithm=algorithm,
        compression_level=compression_level,
        fixed_cost_mode=fixed_cost,
        random_seed=seed,
    )

    pattern_map = {
        "Sequential": WorkloadPattern.SEQUENTIAL,
        "Looping": WorkloadPattern.LOOPING,
        "Zipf (Hot-Cold)": WorkloadPattern.ZIPF,
        "Uniform Random": WorkloadPattern.UNIFORM,
        "Phase-Shifting": WorkloadPattern.PHASE_SHIFTING,
    }
    pattern = pattern_map[workload_str]

    content_map = {
        "Text-Like": ContentType.TEXT_LIKE,
        "Zero": ContentType.ZERO,
        "Structured": ContentType.STRUCTURED,
        "Random (Incompressible)": ContentType.RANDOM,
    }
    content_profile = None if content_str == "Mixed Profile" else content_map[content_str]

    wg = WorkloadGenerator(seed=seed)
    trace = wg.generate(
        pattern=pattern,
        num_accesses=accesses,
        virtual_address_space=vas,
        write_ratio=0.20,
        dram_frames=dram_frames,
    )

    if system_type == "Tiered (3-Tier)":
        mgr = TieredManager(config, content_profile=content_profile)
    else:
        mgr = BaselineManager(config, content_profile=content_profile)

    mgr.run_trace(trace)
    metrics = MetricsCalculator.compute(mgr, name=system_type)

    log_data = []
    for r in mgr.access_log:
        log_data.append({
            "access_index": r.access_index,
            "vpn": r.vpn,
            "is_write": r.is_write,
            "event_type": r.event_type.value,
            "tier_before": r.tier_before.value,
            "tier_after": r.tier_after.value,
            "cost_ns": r.cost_ns,
            "dram_latency_ns": r.dram_latency_ns,
            "decompress_latency_ns": r.decompress_latency_ns,
            "ssd_read_latency_ns": r.ssd_read_latency_ns,
            "eviction_compress_latency_ns": r.eviction_compress_latency_ns,
            "eviction_ssd_write_latency_ns": r.eviction_ssd_write_latency_ns,
            "dram_pages": r.dram_pages,
            "compressed_pages": r.compressed_pages,
            "swap_pages": r.swap_pages,
            "compressed_pool_bytes": r.compressed_pool_bytes,
        })

    return log_data, metrics.to_dict()


# ---------------- SIDEBAR CONTROLS ----------------
with st.sidebar:
    st.header("⚙️ Simulation Config")

    system_mode = st.selectbox(
        "Memory System",
        ["Tiered (3-Tier)", "Baseline (2-Tier)"],
        index=0,
        help="Tiered adds in-memory compressed RAM (zswap) between DRAM and SSD.",
    )

    workload_choice = st.selectbox(
        "Workload Pattern",
        ["Zipf (Hot-Cold)", "Looping", "Sequential", "Phase-Shifting", "Uniform Random"],
        index=0,
    )

    content_choice = st.selectbox(
        "Page Content Profile",
        ["Text-Like", "Mixed Profile", "Zero", "Structured", "Random (Incompressible)"],
        index=0,
    )

    accesses_count = st.slider("Total Accesses", min_value=100, max_value=2000, value=600, step=100)

    col_sb1, col_sb2 = st.columns(2)
    with col_sb1:
        dram_frames_val = st.number_input("DRAM Frames", min_value=4, max_value=256, value=32, step=4)
    with col_sb2:
        pool_pages_val = st.number_input("Pool (Pages Equiv)", min_value=0, max_value=256, value=48, step=8)

    vas_val = st.number_input("Virtual Address Space (Pages)", min_value=16, max_value=512, value=128, step=16)
    threshold_val = st.slider("Skip Threshold", min_value=0.5, max_value=1.0, value=0.75, step=0.05)

    with st.expander("Advanced Settings"):
        algo_choice = st.selectbox("Compression Engine", ["zlib", "lzma"], index=0)
        level_val = st.slider("Compression Level", min_value=1, max_value=9, value=6)
        seed_val = st.number_input("Random Seed", value=42)
        fixed_cost_chk = st.checkbox("Deterministic Fixed Cost Mode", value=False)

# Header
st.markdown("<div class='main-title'>Tiered Virtual Memory Manager Simulator</div>", unsafe_allow_html=True)
st.markdown(
    "<div class='sub-title'>In-Memory Page Compression Hierarchy: DRAM (Tier 0) ⇄ Compressed RAM (Tier 1) ⇄ SSD Swap (Tier 2)</div>",
    unsafe_allow_html=True,
)

# Run current simulation
records, metrics_dict = run_simulation_cached(
    system_type=system_mode,
    workload_str=workload_choice,
    content_str=content_choice,
    accesses=accesses_count,
    dram_frames=dram_frames_val,
    pool_pages=pool_pages_val,
    vas=vas_val,
    threshold=threshold_val,
    algorithm=algo_choice,
    compression_level=level_val,
    seed=seed_val,
    fixed_cost=fixed_cost_chk,
)
metrics = SimulationMetrics(**metrics_dict)
df_log = pd.DataFrame(records)

# Navigation Tabs
tab_live, tab_compare, tab_experiments = st.tabs([
    "🖥️ Live Tier Visualizer",
    "⚖️ Baseline vs Tiered Compare",
    "📊 Benchmark Experiments",
])

# ---------------- TAB 1: LIVE VISUALIZER ----------------
with tab_live:
    # State for step playback
    if "current_step" not in st.session_state:
        st.session_state.current_step = min(50, len(records) - 1)

    # Playback Controls Toolbar
    ctrl_col1, ctrl_col2, ctrl_col3, ctrl_col4, ctrl_col5 = st.columns([1, 1, 1, 1, 5])
    with ctrl_col1:
        if st.button("⏪ Start"):
            st.session_state.current_step = 0
    with ctrl_col2:
        if st.button("◀ Step"):
            st.session_state.current_step = max(0, st.session_state.current_step - 1)
    with ctrl_col3:
        if st.button("Step ▶"):
            st.session_state.current_step = min(len(records) - 1, st.session_state.current_step + 1)
    with ctrl_col4:
        if st.button("End ⏩"):
            st.session_state.current_step = len(records) - 1
    with ctrl_col5:
        step_idx = st.slider(
            "Access Playhead",
            min_value=0,
            max_value=len(records) - 1,
            value=st.session_state.current_step,
            key="slider_step",
            on_change=lambda: st.session_state.update(current_step=st.session_state.slider_step),
        )

    curr_rec = records[st.session_state.current_step]

    # Current Access HUD Callout
    hud_c1, hud_c2, hud_c3, hud_c4 = st.columns([2, 2, 2, 3])
    with hud_c1:
        st.metric("Access #", f"{curr_rec['access_index']} / {len(records)}")
    with hud_c2:
        st.metric("Target VPN", f"Page {curr_rec['vpn']} ({'WRITE' if curr_rec['is_write'] else 'READ'})")
    with hud_c3:
        evt = curr_rec["event_type"]
        color_class = {
            "HIT": "badge-hit",
            "MINOR_FAULT": "badge-minor",
            "MAJOR_FAULT": "badge-major",
            "COLD_FAULT": "badge-cold",
        }.get(evt, "badge-hit")
        st.markdown(f"**Event Type**<br><span class='{color_class}'>{evt}</span>", unsafe_allow_html=True)
    with hud_c4:
        st.metric(
            "Latency Incurred",
            f"{curr_rec['cost_ns']:,} ns",
            delta=f"{curr_rec['tier_before']} ➔ {curr_rec['tier_after']}",
        )

    st.markdown("---")

    # Reconstruct tier contents at current step
    # We replay up to current step
    dram_pages_current = set()
    comp_pages_current = set()
    swap_pages_current = set()

    # Replay events up to current_step to get accurate set of pages in each tier
    for i in range(st.session_state.current_step + 1):
        r = records[i]
        p = r["vpn"]
        dram_pages_current.discard(p)
        comp_pages_current.discard(p)
        swap_pages_current.discard(p)

        if r["tier_after"] == "DRAM":
            dram_pages_current.add(p)
        elif r["tier_after"] == "COMPRESSED":
            comp_pages_current.add(p)
        elif r["tier_after"] == "SWAP":
            swap_pages_current.add(p)

    # Active Page Focus Inspector Banner
    is_write_label = "WRITE" if curr_rec["is_write"] else "READ"
    st.markdown(
        f"""
        <div class='active-inspector-box'>
            <div>
                <span style='font-size: 11px; color: #94a3b8; text-transform: uppercase; font-weight: 700;'>🎯 Active Targeted Page</span><br>
                <strong style='font-size: 21px; color: #60a5fa;'>Virtual Page {curr_rec['vpn']} (VPN {curr_rec['vpn']})</strong>
                <span style='background: #3b82f6; color: white; padding: 2px 8px; border-radius: 4px; font-size: 12px; font-weight: bold; margin-left: 8px;'>{is_write_label}</span>
            </div>
            <div>
                <span style='font-size: 11px; color: #94a3b8; font-weight: 700;'>TIER TRANSITION</span><br>
                <span style='font-size: 15px; font-weight: bold; color: #f8fafc;'>{curr_rec['tier_before']} ➔ {curr_rec['tier_after']}</span>
            </div>
            <div>
                <span style='font-size: 11px; color: #94a3b8; font-weight: 700;'>PAGE FAULT STATUS</span><br>
                <span class='{color_class}'>{evt}</span>
            </div>
            <div>
                <span style='font-size: 11px; color: #94a3b8; font-weight: 700;'>SERVICE LATENCY</span><br>
                <strong style='font-size: 19px; color: #fbbf24;'>{curr_rec['cost_ns']:,} ns</strong>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # 3-Tier Physical Grid Layout
    col_t0, col_t1, col_t2 = st.columns(3)

    with col_t0:
        st.markdown(
            f"""
            <div class='tier-box dram-card'>
                <h4>🟢 Tier 0: DRAM Frames ({len(dram_pages_current)} / {dram_frames_val})</h4>
                <p>Fast physical memory (100 ns latency)</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        cells_html = "<div class='cell-grid'>"
        for p in sorted(list(dram_pages_current)):
            is_active = (p == curr_rec["vpn"])
            highlight = "border: 3px solid #fbbf24 !important; box-shadow: 0 0 14px #fbbf24; transform: scale(1.1); z-index: 10;" if is_active else ""
            badge = "<span class='cell-active-tag'>ACTIVE</span>" if is_active else "<span class='cell-sub'>4 KB</span>"
            cells_html += f"<div class='page-cell dram-cell' style='{highlight}' title='Virtual Page {p} resident in DRAM Frame'><span class='cell-vpn'>VPN {p}</span>{badge}</div>"
        if not dram_pages_current:
            cells_html += "<span style='color: #94a3b8; font-size: 13px; font-style: italic; padding: 8px;'>No resident frames in DRAM</span>"
        cells_html += "</div>"
        st.markdown(cells_html, unsafe_allow_html=True)

    with col_t1:
        pool_bytes_now = curr_rec["compressed_pool_bytes"]
        max_bytes = pool_pages_val * 4096
        pct_used = (pool_bytes_now / max_bytes * 100.0) if max_bytes > 0 else 0
        st.markdown(
            f"""
            <div class='tier-box comp-card'>
                <h4>🔵 Tier 1: Compressed RAM ({len(comp_pages_current)} pages)</h4>
                <p>zswap pool: {pool_bytes_now:,} / {max_bytes:,} B ({pct_used:.1f}%)</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        cells_html = "<div class='cell-grid'>"
        for p in sorted(list(comp_pages_current)):
            is_active = (p == curr_rec["vpn"])
            highlight = "border: 3px solid #fbbf24 !important; box-shadow: 0 0 14px #fbbf24; transform: scale(1.1); z-index: 10;" if is_active else ""
            badge = "<span class='cell-active-tag'>ACTIVE</span>" if is_active else "<span class='cell-sub'>zswap</span>"
            cells_html += f"<div class='page-cell comp-cell' style='{highlight}' title='Virtual Page {p} compressed in Tier 1 RAM'><span class='cell-vpn'>VPN {p}</span>{badge}</div>"
        if not comp_pages_current:
            cells_html += "<span style='color: #94a3b8; font-size: 13px; font-style: italic; padding: 8px;'>Compressed pool is empty</span>"
        cells_html += "</div>"
        st.markdown(cells_html, unsafe_allow_html=True)

    with col_t2:
        st.markdown(
            f"""
            <div class='tier-box swap-card'>
                <h4>🔴 Tier 2: SSD Swap ({len(swap_pages_current)} pages)</h4>
                <p>High latency backing store (100,000 ns)</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        cells_html = "<div class='cell-grid'>"
        for p in sorted(list(swap_pages_current)):
            is_active = (p == curr_rec["vpn"])
            highlight = "border: 3px solid #fbbf24 !important; box-shadow: 0 0 14px #fbbf24; transform: scale(1.1); z-index: 10;" if is_active else ""
            badge = "<span class='cell-active-tag'>ACTIVE</span>" if is_active else "<span class='cell-sub'>SSD</span>"
            cells_html += f"<div class='page-cell swap-cell' style='{highlight}' title='Virtual Page {p} swapped out to SSD'><span class='cell-vpn'>VPN {p}</span>{badge}</div>"
        if not swap_pages_current:
            cells_html += "<span style='color: #94a3b8; font-size: 13px; font-style: italic; padding: 8px;'>No swapped pages on SSD</span>"
        cells_html += "</div>"
        st.markdown(cells_html, unsafe_allow_html=True)

    st.markdown("---")

    # Dynamic Running Charts
    st.subheader("📈 Real-Time Simulation Trajectory")
    df_sub = df_log.iloc[: st.session_state.current_step + 1].copy()
    df_sub["cumulative_amat"] = df_sub["cost_ns"].expanding().mean()

    ch_col1, ch_col2 = st.columns(2)
    with ch_col1:
        fig_amat, ax_a = plt.subplots(figsize=(6, 3))
        ax_a.plot(df_sub["access_index"], df_sub["cumulative_amat"], color="#1e3a8a", linewidth=2)
        ax_a.set_title("Cumulative AMAT (ns)")
        ax_a.set_xlabel("Access #")
        ax_a.set_ylabel("Nanoseconds")
        ax_a.grid(True, linestyle="--", alpha=0.4)
        st.pyplot(fig_amat)
        plt.close(fig_amat)

    with ch_col2:
        fig_occ, ax_o = plt.subplots(figsize=(6, 3))
        ax_o.plot(df_sub["access_index"], df_sub["dram_pages"], label="DRAM", color="#10b981", linewidth=2)
        ax_o.plot(df_sub["access_index"], df_sub["compressed_pages"], label="Compressed", color="#3b82f6", linewidth=2)
        ax_o.plot(df_sub["access_index"], df_sub["swap_pages"], label="Swap", color="#ef4444", linewidth=2)
        ax_o.set_title("Tier Occupancy Count")
        ax_o.set_xlabel("Access #")
        ax_o.set_ylabel("Pages")
        ax_o.legend(loc="upper left", fontsize=8)
        ax_o.grid(True, linestyle="--", alpha=0.4)
        st.pyplot(fig_occ)
        plt.close(fig_occ)

    # Event history table
    st.subheader("📜 Recent Access Telemetry Log")
    start_history = max(0, st.session_state.current_step - 9)
    recent_slice = df_log.iloc[start_history : st.session_state.current_step + 1]
    st.dataframe(
        recent_slice[[
            "access_index", "vpn", "is_write", "event_type", "tier_before", "tier_after", "cost_ns"
        ]],
        use_container_width=True,
    )


# ---------------- TAB 2: SYSTEM COMPARISON ----------------
with tab_compare:
    st.subheader("⚖️ Direct Side-by-Side Architectural Comparison")
    st.markdown(
        "Runs both **Baseline (2-Tier)** and **Tiered (3-Tier)** on the exact same access trace and content profile."
    )

    if st.button("🚀 Run Comparative Benchmark", type="primary"):
        with st.spinner("Executing side-by-side benchmark..."):
            _, b_dict = run_simulation_cached(
                system_type="Baseline (2-Tier)",
                workload_str=workload_choice,
                content_str=content_choice,
                accesses=accesses_count,
                dram_frames=dram_frames_val,
                pool_pages=pool_pages_val,
                vas=vas_val,
                threshold=threshold_val,
                algorithm=algo_choice,
                compression_level=level_val,
                seed=seed_val,
                fixed_cost=fixed_cost_chk,
            )
            _, t_dict = run_simulation_cached(
                system_type="Tiered (3-Tier)",
                workload_str=workload_choice,
                content_str=content_choice,
                accesses=accesses_count,
                dram_frames=dram_frames_val,
                pool_pages=pool_pages_val,
                vas=vas_val,
                threshold=threshold_val,
                algorithm=algo_choice,
                compression_level=level_val,
                seed=seed_val,
                fixed_cost=fixed_cost_chk,
            )

        b_m = SimulationMetrics(**b_dict)
        t_m = SimulationMetrics(**t_dict)
        speedup = b_m.amat_ns / t_m.amat_ns if t_m.amat_ns > 0 else 1.0

        # Highlights
        st.success(
            f"🎯 **Tiered System achieves {speedup:.2f}x speedup!** "
            f"AMAT reduced from **{b_m.amat_ns:,.1f} ns** to **{t_m.amat_ns:,.1f} ns**."
        )

        cmp_c1, cmp_c2, cmp_c3 = st.columns(3)
        with cmp_c1:
            st.metric("Baseline AMAT", f"{b_m.amat_ns:,.1f} ns")
            st.metric("Baseline Major Faults", f"{b_m.major_faults:,}")
            st.metric("Baseline In-Memory Capacity", f"{b_m.effective_capacity_pages} pages")
        with cmp_c2:
            st.metric("Tiered AMAT", f"{t_m.amat_ns:,.1f} ns", delta=f"{-(1.0 - 1/speedup)*100:.1f}% latency")
            st.metric("Tiered Major Faults", f"{t_m.major_faults:,}", delta=f"{t_m.major_faults - b_m.major_faults}")
            st.metric(
                "Tiered In-Memory Capacity",
                f"{t_m.effective_capacity_pages} pages",
                delta=f"+{t_m.effective_capacity_gain_pct:.1f}%",
            )
        with cmp_c3:
            st.metric("Speedup Factor", f"{speedup:.2f}x")
            st.metric("Minor Faults Served via RAM", f"{t_m.minor_faults:,}")
            st.metric("Average Compression Space Saving", f"{t_m.avg_space_saving_pct:.1f}%")

        # Visual Comparison Bar Charts
        fig_cmp, (ax_amat, ax_faults) = plt.subplots(1, 2, figsize=(10, 4))

        # AMAT bar
        ax_amat.bar(["Baseline", "Tiered"], [b_m.amat_ns, t_m.amat_ns], color=["#ef4444", "#10b981"], width=0.4)
        ax_amat.set_ylabel("AMAT (ns, lower is better)")
        ax_amat.set_title("Average Memory Access Time")
        ax_amat.grid(axis="y", linestyle="--", alpha=0.5)

        # Faults Breakdown stacked bar
        fault_cats = ["Hits", "Minor (Comp)", "Major (SSD)", "Cold"]
        b_vals = [b_m.dram_hits, b_m.minor_faults, b_m.major_faults, b_m.cold_faults]
        t_vals = [t_m.dram_hits, t_m.minor_faults, t_m.major_faults, t_m.cold_faults]

        x_b = np.arange(2)
        width = 0.35
        ax_faults.bar(["Baseline", "Tiered"], [b_m.major_faults, t_m.major_faults], label="Major (SSD)", color="#ef4444")
        ax_faults.bar(["Baseline", "Tiered"], [b_m.minor_faults, t_m.minor_faults], bottom=[b_m.major_faults, t_m.major_faults], label="Minor (Compressed)", color="#3b82f6")
        ax_faults.set_ylabel("Fault Count")
        ax_faults.set_title("Page Fault Distribution")
        ax_faults.legend()
        ax_faults.grid(axis="y", linestyle="--", alpha=0.5)

        st.pyplot(fig_cmp)
        plt.close(fig_cmp)


# ---------------- TAB 3: BENCHMARK EXPERIMENTS ----------------
with tab_experiments:
    st.subheader("📊 Experimental Results Gallery")
    st.markdown("Precomputed experimental data across workloads, pool sweeps, and compression algorithms.")

    res_dir = Path("results")
    if not (res_dir / "exp1_baseline_vs_tiered_text.png").exists():
        st.warning("Experiment figures not found. Click below to run the full benchmark suite.")
        if st.button("Run Full Experiments Now"):
            import run_experiments
            with st.spinner("Executing all 6 experiments..."):
                run_experiments.main()
            st.experimental_rerun()

    exp_select = st.selectbox(
        "Choose Experiment Study",
        [
            "Experiment 1: Baseline vs Tiered across Workloads",
            "Experiment 2: Compressed Pool Size Sweep",
            "Experiment 3: Content-Type Compressibility Study",
            "Experiment 4: Compression Algorithm Comparison",
            "Experiment 5: Compress-or-Skip Threshold Sweep",
            "Experiment 6: Effective Capacity Expansion",
        ],
    )

    if exp_select.startswith("Experiment 1"):
        img_p = res_dir / "exp1_baseline_vs_tiered_text.png"
        csv_p = res_dir / "exp1_baseline_vs_tiered.csv"
        if img_p.exists():
            st.image(str(img_p), caption="Exp 1: Baseline vs Tiered AMAT (Compressible Text)")
        if csv_p.exists():
            st.dataframe(pd.read_csv(csv_p))

    elif exp_select.startswith("Experiment 2"):
        img_p = res_dir / "exp2_pool_size_sweep.png"
        csv_p = res_dir / "exp2_pool_size_sweep.csv"
        if img_p.exists():
            st.image(str(img_p), caption="Exp 2: AMAT vs Compressed Pool Size (Finding the sweet spot)")
        if csv_p.exists():
            st.dataframe(pd.read_csv(csv_p))

    elif exp_select.startswith("Experiment 3"):
        img_p = res_dir / "exp3_content_types.png"
        csv_p = res_dir / "exp3_content_types.csv"
        if img_p.exists():
            st.image(str(img_p), caption="Exp 3: Compressibility & CPU Duration by Page Content Type")
        if csv_p.exists():
            st.dataframe(pd.read_csv(csv_p))

    elif exp_select.startswith("Experiment 4"):
        img_p = res_dir / "exp4_algorithms.png"
        csv_p = res_dir / "exp4_algorithms.csv"
        if img_p.exists():
            st.image(str(img_p), caption="Exp 4: Algorithm Trade-offs (zlib vs lzma)")
        if csv_p.exists():
            st.dataframe(pd.read_csv(csv_p))

    elif exp_select.startswith("Experiment 5"):
        img_p = res_dir / "exp5_threshold_sweep.png"
        csv_p = res_dir / "exp5_threshold_sweep.csv"
        if img_p.exists():
            st.image(str(img_p), caption="Exp 5: Compress-or-Skip Threshold Sensitivity")
        if csv_p.exists():
            st.dataframe(pd.read_csv(csv_p))

    elif exp_select.startswith("Experiment 6"):
        img_p = res_dir / "exp6_effective_capacity.png"
        csv_p = res_dir / "exp6_effective_capacity.csv"
        if img_p.exists():
            st.image(str(img_p), caption="Exp 6: Effective Memory Capacity Expansion")
        if csv_p.exists():
            st.dataframe(pd.read_csv(csv_p))
