# Paper II — Transferable Computation: Validity-Preserving Knowledge Across Environments

**Module ID**: `paper-02` | **Version**: `0.1.0` | **Exported Contract**: `TS-TRANSFER-CERTIFICATE`  
**Imports**: `TS-BASE-001`, `TS-001`, `TS-CERTIFIED-REUSE`

## 1. Central Claim
Validated capabilities can transfer across institutions with differing schemas, encodings, or partial drift using explicit **Transfer Certificates** (`TS-005`) and **Tractability-Preserving Environment Policies** (`TS-006`), beating destination rediscovery while catching semantic divergence and institutional enclosure via grounded external reality probes.

## 2. Verified Evidence Mapping (Living Computation v0.1–v0.3)
- **Exp 12 (`T1–T4` Transfer Benchmark)**:
  - `T1_syntactic` & `T2_semantic`: `human_api_transfer` retains `12/12` modules with `0.0000` MAE, `0.0%` false-SAFE, saving **-90.8%** (T1) and **-79.9%** (T2) ops vs full rediscovery (`0.0s` human time). Blind reuse suffers `62.3%–100.0%` false-SAFE.
  - `T3_structural_drift`: retains `8/12` unaffected modules and selectively relearns 4 (**-87.0%** ops vs full rediscovery, `0.0106` MAE).
  - `T4_institutional_enclosure`: catches divergence via external reality probe (`0.0%` false-SAFE vs `70.9%` blind reuse) despite 100% internal schema consistency.
- **Exp 4 & Exp 5 (SAT Environment Synthesis)**:
  - Certified `2-SAT` (`7.40x`), `Renamable-Horn` (`1.81x`), and `Bounded-k3 Horn-Backdoor` (`1.41x`) at $n=60$; naive low-density heuristic falsified by padded hard core (`density=2.18`).
  - Upstream enforcement saves **-76.3%** machine ops vs DPLL (`0` silently dropped clauses) with explicit `104s` simulated human ledger; 2D phase diagram maps failure boundaries at high mandatory irreducibility (`p_hard=1.0`) and high negotiable churn (`204s` human burden), mitigated `-67.3%` by adaptive policy retirement.

## 3. Formal Contributions & Limitations
- **Proved**: P11 (Transfer Contract Soundness), Theorem 3 (Lewis–Aspvall & FPT Backdoor soundness).
- **Non-Claims**: Does not prove universal portability or automatic translation discovery; requires external reality probing to prevent institutional enclosure.
