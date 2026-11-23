# Historical Avoidance Ledger — Milestone 01+02

> Audit trail of which computations were avoided, why they could safely be avoided, which environmental assumptions supported each decision, when assumptions failed, and how much work and modeled energy were saved.

## 1. Experimental Context
- **Graph**: `living_milestone_dag_1000n_s42` (1000 nodes, 2167 edges, 120 inputs, depth 25)
- **Workload**: `localized_regime_drift`, 10,000 controlled updates (seed 2026)
- **Energy accounting**: `modeled_proxy` (measured CPU time + memory/IO traffic model; not hardware RAPL)
- **Output correctness vs Full Recomputation**: 0 mismatches across 10001 steps (100.0% exact)

## 2. Net Lifecycle Accounting (All Overhead Included)

| Comparison | Step Savings | Time Savings | Modeled Energy Savings | Payback $T^*$ (ops) | $R_{\text{avoid}}$ (gross / net ops) |
|---|---:|---:|---:|---:|---:|
| Living (every-step JSONL trace) vs Full | 8,251,647 (93.54%) | 3.5053 s (89.69%) | 12.207284 J (89.63%) | t=1 | 53.93x / 52.93x |
| Living (every-step JSONL trace) vs Incremental | 94,249 (14.20%) | -0.0377 s (-10.32%) | -0.132139 J (-10.32%) | t=427 | 1.60x / 0.60x |
| Living (surprise-driven trace) vs Incremental | 101,678 (15.32%) | -0.0241 s (-6.61%) | -0.084548 J (-6.60%) | t=408 | 1.68x / 0.68x |

## 3. Learned Validity Contracts & Per-Contract Savings

- **Contracts learned from traces**: 31
- **Total contract avoidance events**: 14,469
- **Total node evaluations avoided by contracts**: 303,849
- **Total canary invalidations (assumption breaks)**: 7,478
- **Estimated gross modeled energy saved by contracts**: 0.559220 J

| Contract ID | Target Node | Guarantee | Boundary Inputs | Absorbed Nodes | Hits (SAFE) | Invalidations (UNSAFE) | Nodes Avoided | Est. Energy Saved (J) |
|---|---|---|---:|---:|---:|---:|---:|---:|
| `vc_011_sub_00_gate_thresh` | `sub_00_gate_thresh` | `restricted_worst_case` | 5 | 21 | 796 | 36 | 16,716 | 0.030753 |
| `vc_019_sub_18_gate_thresh` | `sub_18_gate_thresh` | `restricted_worst_case` | 5 | 21 | 723 | 49 | 15,183 | 0.027898 |
| `vc_006_sub_06_gate_thresh` | `sub_06_gate_thresh` | `restricted_worst_case` | 5 | 21 | 704 | 66 | 14,784 | 0.027185 |
| `vc_001_sub_12_gate_thresh` | `sub_12_gate_thresh` | `restricted_worst_case` | 5 | 21 | 691 | 119 | 14,511 | 0.026770 |
| `vc_002_sub_36_gate_thresh` | `sub_36_gate_thresh` | `restricted_worst_case` | 5 | 21 | 673 | 114 | 14,133 | 0.026064 |
| `vc_017_sub_31_gate_thresh` | `sub_31_gate_thresh` | `restricted_worst_case` | 4 | 21 | 634 | 44 | 13,314 | 0.024377 |
| `vc_003_sub_30_gate_thresh` | `sub_30_gate_thresh` | `restricted_worst_case` | 5 | 21 | 633 | 152 | 13,293 | 0.024520 |
| `vc_020_sub_01_gate_thresh` | `sub_01_gate_thresh` | `restricted_worst_case` | 4 | 21 | 626 | 42 | 13,146 | 0.024189 |
| `vc_009_sub_34_gate_relu` | `sub_34_gate_relu` | `restricted_worst_case` | 4 | 21 | 596 | 69 | 12,516 | 0.023013 |
| `vc_004_sub_24_gate_thresh` | `sub_24_gate_thresh` | `restricted_worst_case` | 5 | 21 | 592 | 182 | 12,432 | 0.022947 |
| `vc_024_sub_20_gate_thresh` | `sub_20_gate_thresh` | `restricted_worst_case` | 4 | 21 | 591 | 62 | 12,411 | 0.022761 |
| `vc_010_sub_14_gate_thresh` | `sub_14_gate_thresh` | `restricted_worst_case` | 4 | 21 | 579 | 71 | 12,159 | 0.022469 |
| `vc_014_sub_19_gate_thresh` | `sub_19_gate_thresh` | `restricted_worst_case` | 4 | 21 | 569 | 63 | 11,949 | 0.022070 |
| `vc_008_sub_07_gate_thresh` | `sub_07_gate_thresh` | `restricted_worst_case` | 4 | 21 | 562 | 48 | 11,802 | 0.021741 |
| `vc_013_sub_26_gate_thresh` | `sub_26_gate_thresh` | `restricted_worst_case` | 4 | 21 | 559 | 79 | 11,739 | 0.021604 |
| `vc_031_sub_25_gate_thresh` | `sub_25_gate_thresh` | `restricted_worst_case` | 4 | 21 | 556 | 68 | 11,676 | 0.021455 |
| `vc_005_sub_13_gate_thresh` | `sub_13_gate_thresh` | `restricted_worst_case` | 4 | 21 | 555 | 55 | 11,655 | 0.021471 |
| `vc_015_sub_08_gate_thresh` | `sub_08_gate_thresh` | `restricted_worst_case` | 4 | 21 | 551 | 70 | 11,571 | 0.021344 |
| `vc_026_sub_02_gate_thresh` | `sub_02_gate_thresh` | `restricted_worst_case` | 4 | 21 | 545 | 72 | 11,445 | 0.020923 |
| `vc_023_sub_04_gate_relu` | `sub_04_gate_relu` | `restricted_worst_case` | 4 | 21 | 540 | 116 | 11,340 | 0.020898 |
| ... | *(11 additional contracts in `avoidance_ledger.json`)* | | | | | | | |

## 4. Sample Avoidance Provenance Entries

Each entry records the exact timestep, bypassed subgraph, mathematical precondition that held, and supporting assumptions:

### Step `t=151` — `vc_004_sub_24_gate_thresh` (avoided 21 node evaluations)
- **Why safe**: Lipschitz validity ball holds: drift=0.021121 < margin=0.247836 (remaining=0.226714)
- **Guard ops spent**: 2 | **Changed boundary IDs**: `[89]`
- **Estimated modeled energy saved**: `0.000038856 J`
- **Supporting environmental & structural assumptions**:
  - Sub-DAG internal nodes (20 nodes) remain structurally immutable
  - Every internal operator in cone is globally Lipschitz-continuous (L[in_072]=1.190, L[in_073]=0.603, L[in_074]=1.122, L[in_075]=0.459, L[in_089]=1.332)
  - Target node `sub_24_gate_thresh` (threshold) stays inside its flat/saturated validity ball: drift + eps_fp < margin
  - Deterministic pure evaluation (no hidden side effects or unobserved external inputs)

### Step `t=152` — `vc_004_sub_24_gate_thresh` (avoided 21 node evaluations)
- **Why safe**: Lipschitz validity ball holds: drift=0.113683 < margin=0.247836 (remaining=0.134153)
- **Guard ops spent**: 2 | **Changed boundary IDs**: `[72]`
- **Estimated modeled energy saved**: `0.000038856 J`
- **Supporting environmental & structural assumptions**:
  - Sub-DAG internal nodes (20 nodes) remain structurally immutable
  - Every internal operator in cone is globally Lipschitz-continuous (L[in_072]=1.190, L[in_073]=0.603, L[in_074]=1.122, L[in_075]=0.459, L[in_089]=1.332)
  - Target node `sub_24_gate_thresh` (threshold) stays inside its flat/saturated validity ball: drift + eps_fp < margin
  - Deterministic pure evaluation (no hidden side effects or unobserved external inputs)

### Step `t=152` — `vc_007_sub_28_gate_relu` (avoided 21 node evaluations)
- **Why safe**: Lipschitz validity ball holds: drift=0.044174 < margin=0.408029 (remaining=0.363854)
- **Guard ops spent**: 2 | **Changed boundary IDs**: `[85]`
- **Estimated modeled energy saved**: `0.000038856 J`
- **Supporting environmental & structural assumptions**:
  - Sub-DAG internal nodes (20 nodes) remain structurally immutable
  - Every internal operator in cone is globally Lipschitz-continuous (L[in_084]=0.818, L[in_085]=0.921, L[in_086]=1.462, L[in_087]=1.095)
  - Target node `sub_28_gate_relu` (relu) stays inside its flat/saturated validity ball: drift + eps_fp < margin
  - Deterministic pure evaluation (no hidden side effects or unobserved external inputs)

### Step `t=153` — `vc_011_sub_00_gate_thresh` (avoided 21 node evaluations)
- **Why safe**: Lipschitz validity ball holds: drift=0.020148 < margin=0.659632 (remaining=0.639484)
- **Guard ops spent**: 2 | **Changed boundary IDs**: `[2]`
- **Estimated modeled energy saved**: `0.000038856 J`
- **Supporting environmental & structural assumptions**:
  - Sub-DAG internal nodes (20 nodes) remain structurally immutable
  - Every internal operator in cone is globally Lipschitz-continuous (L[in_000]=1.517, L[in_001]=0.596, L[in_002]=1.912, L[in_003]=0.066, L[in_017]=0.550)
  - Target node `sub_00_gate_thresh` (threshold) stays inside its flat/saturated validity ball: drift + eps_fp < margin
  - Deterministic pure evaluation (no hidden side effects or unobserved external inputs)

### Step `t=153` — `vc_004_sub_24_gate_thresh` (avoided 21 node evaluations)
- **Why safe**: Lipschitz validity ball holds: drift=0.115673 < margin=0.247836 (remaining=0.132162)
- **Guard ops spent**: 2 | **Changed boundary IDs**: `[75]`
- **Estimated modeled energy saved**: `0.000038856 J`
- **Supporting environmental & structural assumptions**:
  - Sub-DAG internal nodes (20 nodes) remain structurally immutable
  - Every internal operator in cone is globally Lipschitz-continuous (L[in_072]=1.190, L[in_073]=0.603, L[in_074]=1.122, L[in_075]=0.459, L[in_089]=1.332)
  - Target node `sub_24_gate_thresh` (threshold) stays inside its flat/saturated validity ball: drift + eps_fp < margin
  - Deterministic pure evaluation (no hidden side effects or unobserved external inputs)

### Step `t=153` — `vc_031_sub_25_gate_thresh` (avoided 21 node evaluations)
- **Why safe**: Lipschitz validity ball holds: drift=0.002110 < margin=0.795730 (remaining=0.793620)
- **Guard ops spent**: 2 | **Changed boundary IDs**: `[75]`
- **Estimated modeled energy saved**: `0.000038856 J`
- **Supporting environmental & structural assumptions**:
  - Sub-DAG internal nodes (20 nodes) remain structurally immutable
  - Every internal operator in cone is globally Lipschitz-continuous (L[in_075]=0.486, L[in_076]=1.263, L[in_077]=0.648, L[in_078]=2.075)
  - Target node `sub_25_gate_thresh` (threshold) stays inside its flat/saturated validity ball: drift + eps_fp < margin
  - Deterministic pure evaluation (no hidden side effects or unobserved external inputs)

### Step `t=154` — `vc_008_sub_07_gate_thresh` (avoided 21 node evaluations)
- **Why safe**: Lipschitz validity ball holds: drift=0.046619 < margin=0.635741 (remaining=0.589122)
- **Guard ops spent**: 2 | **Changed boundary IDs**: `[22]`
- **Estimated modeled energy saved**: `0.000038856 J`
- **Supporting environmental & structural assumptions**:
  - Sub-DAG internal nodes (20 nodes) remain structurally immutable
  - Every internal operator in cone is globally Lipschitz-continuous (L[in_021]=0.541, L[in_022]=0.722, L[in_023]=2.248, L[in_024]=1.018)
  - Target node `sub_07_gate_thresh` (threshold) stays inside its flat/saturated validity ball: drift + eps_fp < margin
  - Deterministic pure evaluation (no hidden side effects or unobserved external inputs)

### Step `t=154` — `vc_004_sub_24_gate_thresh` (avoided 21 node evaluations)
- **Why safe**: Lipschitz validity ball holds: drift=0.067994 < margin=0.247836 (remaining=0.179842)
- **Guard ops spent**: 2 | **Changed boundary IDs**: `[72]`
- **Estimated modeled energy saved**: `0.000038856 J`
- **Supporting environmental & structural assumptions**:
  - Sub-DAG internal nodes (20 nodes) remain structurally immutable
  - Every internal operator in cone is globally Lipschitz-continuous (L[in_072]=1.190, L[in_073]=0.603, L[in_074]=1.122, L[in_075]=0.459, L[in_089]=1.332)
  - Target node `sub_24_gate_thresh` (threshold) stays inside its flat/saturated validity ball: drift + eps_fp < margin
  - Deterministic pure evaluation (no hidden side effects or unobserved external inputs)

### Step `t=154` — `vc_007_sub_28_gate_relu` (avoided 21 node evaluations)
- **Why safe**: Lipschitz validity ball holds: drift=0.102679 < margin=0.408029 (remaining=0.305350)
- **Guard ops spent**: 2 | **Changed boundary IDs**: `[87]`
- **Estimated modeled energy saved**: `0.000038856 J`
- **Supporting environmental & structural assumptions**:
  - Sub-DAG internal nodes (20 nodes) remain structurally immutable
  - Every internal operator in cone is globally Lipschitz-continuous (L[in_084]=0.818, L[in_085]=0.921, L[in_086]=1.462, L[in_087]=1.095)
  - Target node `sub_28_gate_relu` (relu) stays inside its flat/saturated validity ball: drift + eps_fp < margin
  - Deterministic pure evaluation (no hidden side effects or unobserved external inputs)

### Step `t=155` — `vc_017_sub_31_gate_thresh` (avoided 21 node evaluations)
- **Why safe**: Lipschitz validity ball holds: drift=0.242258 < margin=0.685833 (remaining=0.443576)
- **Guard ops spent**: 2 | **Changed boundary IDs**: `[94]`
- **Estimated modeled energy saved**: `0.000038856 J`
- **Supporting environmental & structural assumptions**:
  - Sub-DAG internal nodes (20 nodes) remain structurally immutable
  - Every internal operator in cone is globally Lipschitz-continuous (L[in_093]=0.949, L[in_094]=1.141, L[in_095]=1.568, L[in_096]=0.882)
  - Target node `sub_31_gate_thresh` (threshold) stays inside its flat/saturated validity ball: drift + eps_fp < margin
  - Deterministic pure evaluation (no hidden side effects or unobserved external inputs)

### Step `t=156` — `vc_006_sub_06_gate_thresh` (avoided 21 node evaluations)
- **Why safe**: Lipschitz validity ball holds: drift=0.007261 < margin=0.668616 (remaining=0.661354)
- **Guard ops spent**: 2 | **Changed boundary IDs**: `[20]`
- **Estimated modeled energy saved**: `0.000038856 J`
- **Supporting environmental & structural assumptions**:
  - Sub-DAG internal nodes (20 nodes) remain structurally immutable
  - Every internal operator in cone is globally Lipschitz-continuous (L[in_018]=0.669, L[in_019]=0.869, L[in_020]=0.747, L[in_021]=1.467, L[in_035]=0.839)
  - Target node `sub_06_gate_thresh` (threshold) stays inside its flat/saturated validity ball: drift + eps_fp < margin
  - Deterministic pure evaluation (no hidden side effects or unobserved external inputs)

### Step `t=156` — `vc_014_sub_19_gate_thresh` (avoided 21 node evaluations)
- **Why safe**: Lipschitz validity ball holds: drift=0.019215 < margin=0.707941 (remaining=0.688726)
- **Guard ops spent**: 2 | **Changed boundary IDs**: `[60]`
- **Estimated modeled energy saved**: `0.000038856 J`
- **Supporting environmental & structural assumptions**:
  - Sub-DAG internal nodes (20 nodes) remain structurally immutable
  - Every internal operator in cone is globally Lipschitz-continuous (L[in_057]=1.347, L[in_058]=1.344, L[in_059]=1.124, L[in_060]=0.600)
  - Target node `sub_19_gate_thresh` (threshold) stays inside its flat/saturated validity ball: drift + eps_fp < margin
  - Deterministic pure evaluation (no hidden side effects or unobserved external inputs)
