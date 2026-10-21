# System Architecture: Tiered Virtual Memory Manager

This document provides architectural diagrams and control-flow models for the Tiered Virtual Memory Manager with Page Compression (simulating Linux `zswap`/`zram`).

---

## 1. High-Level Memory Hierarchy Architecture

```mermaid
graph TD
    subgraph CPU["CPU & Virtual Memory Subsystem"]
        VA["Virtual Address (VPN + Offset)"]
        PT["Page Table (VPN -> PTE)"]
        VA --> PT
    end

    subgraph MemoryHierarchy["Three-Tier Memory Hierarchy"]
        direction TB
        subgraph Tier0["Tier 0: Physical DRAM (Fastest)"]
            DRAM["Uncompressed DRAM Frames (64 Frames)<br/>Latency: 100 ns<br/>Managed via O(1) LRU OrderedDict"]
        end

        subgraph Tier1["Tier 1: Compressed RAM Pool (Warm Cache)"]
            ZSWAP["In-Memory Compressed Pool (zswap)<br/>Capacity: Bounded strictly by BYTES<br/>Latency: Decompress ~8-12 µs<br/>Algorithm: zlib / lzma"]
        end

        subgraph Tier2["Tier 2: SSD Swap Device (Backing Store)"]
            SSD["Simulated SSD Disk Swap<br/>Capacity: Unlimited<br/>Latency: 100,000 ns (100 µs)<br/>Persists raw 4KB pages"]
        end
    end

    PT -->|"DRAM Hit (Tier 0)"| DRAM
    PT -->|"Minor Fault (Tier 1)"| ZSWAP
    PT -->|"Major Fault (Tier 2)"| SSD
    PT -->|"Cold Fault (First Touch)"| DRAM

    DRAM -->|"Demotion (Eviction + zlib Compress)"| ZSWAP
    DRAM -->|"Incompressible Bypass (ratio > 0.75)"| SSD
    ZSWAP -->|"Pool Overflow Demotion"| SSD
    ZSWAP -->|"Promotion (Decompress)"| DRAM
    SSD -->|"Promotion (SSD Read)"| DRAM
```

---

## 2. Page Access & Fault Handling Flowchart

Every virtual memory reference follows this decision and service sequence:

```mermaid
flowchart TD
    Start(["Memory Access: (VPN, is_write)"]) --> CheckPT["Lookup Page Table Entry (PTE)"]

    CheckPT --> WhatTier{"Current PTE.tier?"}

    %% DRAM HIT
    WhatTier -->|"DRAM"| Hit["DRAM HIT (Tier 0)<br/>- Read/Write raw 4KB bytes<br/>- Move VPN to LRU tail<br/>- Charge DRAM Latency (100 ns)"]
    Hit --> WriteCheck{"is_write?"}
    WriteCheck -->|"Yes"| MarkDirty["Mark PTE.dirty = True<br/>Mutate page content"]
    WriteCheck -->|"No"| Done(["Access Complete"])
    MarkDirty --> Done

    %% MINOR FAULT
    WhatTier -->|"COMPRESSED"| Minor["MINOR FAULT (Tier 1)<br/>- Decompress page bytes via zlib/lzma<br/>- Charge DRAM + Decompress Latency (~8-12 µs)"]
    Minor --> NeedDramEvict1{"DRAM Full?"}
    NeedDramEvict1 -->|"Yes"| EvictChain1["Run DRAM Eviction Pipeline"]
    NeedDramEvict1 -->|"No"| PromoteComp["Remove from Compressed Pool<br/>Insert uncompressed into DRAM<br/>PTE.tier = DRAM"]
    EvictChain1 --> PromoteComp
    PromoteComp --> WriteCheck

    %% MAJOR FAULT
    WhatTier -->|"SWAP"| Major["MAJOR FAULT (Tier 2)<br/>- Read 4KB page from SSD swap<br/>- Charge DRAM + SSD Read Latency (100,100 ns)"]
    Major --> NeedDramEvict2{"DRAM Full?"}
    NeedDramEvict2 -->|"Yes"| EvictChain2["Run DRAM Eviction Pipeline"]
    NeedDramEvict2 -->|"No"| PromoteSwap["Insert 4KB page into DRAM<br/>PTE.tier = DRAM<br/>If read-only: PTE.swap_clean = True"]
    EvictChain2 --> PromoteSwap
    PromoteSwap --> WriteCheck

    %% COLD FAULT
    WhatTier -->|"UNMAPPED"| Cold["COLD FAULT (First Touch)<br/>- Allocate fresh 4KB content<br/>- Charge DRAM Latency (100 ns)"]
    Cold --> NeedDramEvict3{"DRAM Full?"}
    NeedDramEvict3 -->|"Yes"| EvictChain3["Run DRAM Eviction Pipeline"]
    NeedDramEvict3 -->|"No"| InsertCold["Insert 4KB page into DRAM<br/>PTE.tier = DRAM<br/>Assign ContentType"]
    EvictChain3 --> InsertCold
    InsertCold --> WriteCheck
```

---

## 3. DRAM Eviction & Demotion Pipeline

When physical DRAM frames are full and a new page must be brought into DRAM, the eviction pipeline executes:

```mermaid
flowchart TD
    StartEvict(["DRAM Eviction Triggered"]) --> SelectVictim["Select LRU Victim from DRAM<br/>(pop oldest from OrderedDict)"]
    SelectVictim --> CompressVictim["Compress victim with real zlib Engine<br/>Measure CPU duration & compressed size"]
    CompressVictim --> CheckSkip{"compressed_size / 4096 <= 0.75<br/>AND<br/>pool_capacity >= compressed_size?"}

    %% Compressible Path
    CheckSkip -->|"Yes (Compressible)"| CheckPool{"Can compressed pool fit bytes?<br/>(free_bytes >= compressed_size)"}
    CheckPool -->|"No (Pool Full)"| DemotePoolLRU["Demote LRU page from Compressed Pool<br/>- Pop oldest compressed page<br/>- If swap_clean and on SSD: skip SSD write<br/>- Else: decompress & write to SSD (+100 µs)<br/>- PTE.tier = SWAP"]
    DemotePoolLRU --> CheckPool
    CheckPool -->|"Yes (Space Available)"| StoreComp["Store compressed bytes in Pool<br/>PTE.tier = COMPRESSED<br/>PTE.compressed_size = comp_size"]
    StoreComp --> EndEvict(["Eviction Complete"])

    %% Incompressible Path
    CheckSkip -->|"No (Skip Threshold Exceeded)"| BypassSSD["Bypass Tier 1 (Straight to SSD)<br/>- If swap_clean: skip SSD write<br/>- Else: write 4KB page to SSD (+100 µs)<br/>- PTE.tier = SWAP"]
    BypassSSD --> EndEvict
```

---

## 4. Page Lifecycle State Transition Diagram

```mermaid
stateDiagram-v2
    [*] --> UNMAPPED: Process Address Space Allocated
    UNMAPPED --> DRAM: First-Touch Access (Cold Fault)

    DRAM --> DRAM: Subsequent Access (DRAM Hit, LRU refresh)

    DRAM --> COMPRESSED: Evicted from DRAM (ratio <= 0.75 & pool has room)
    DRAM --> SWAP: Evicted from DRAM (incompressible: ratio > 0.75)

    COMPRESSED --> DRAM: Access requested (Minor Fault, decompression)
    COMPRESSED --> SWAP: Pool capacity overflow (LRU demotion to SSD)

    SWAP --> DRAM: Access requested (Major Fault, SSD read)
```
