# Paper V — Proof of Creator: Causal Provenance, Verified Savings, and Computational Optionality

**Module ID**: `paper-05` | **Version**: `0.1.0` | **Exported Contract**: `TS-PROOF-OF-CREATOR`  
**Imports**: `TS-BASE-001`, `TS-WORK-NOT-DONE`, `TS-HUMAN-CAPITAL`

## 1. Central Claim
Authenticated contribution histories, validated capability/transfer contracts, and tiered Work Not Done certificates compose into a tamper-evident **Proof of Creator** fingerprint (`TS-009`) supporting conservative cooperative attribution (P13) alongside a strictly separated **Computational Optionality Ledger** (`TS-010`, P16).

## 2. Verified Evidence Mapping (Living Computation v0.2–v0.3)
- **Exp 14 (Proof of Creator Verifier, 5 Scenarios)**:
  - Deterministic canonical SHA-256 fingerprint reproduction + **4/4** tamper/forgery/misattribution/replay attacks detected (100%).
  - **Shapley P13 conservation**: `{'alice': 130k, 'bob': 130k, 'carol': 80k, 'eve': 0}` (`sum = 340k` exact; dummy gets `0`) vs `1,020k` naive path double-counting (3x inflation) and `-580k` leave-one-out synergy gap.
  - Drift invalidation halts post-drift attribution (`0`) while preserving historical credit (`80k`); independent rediscovery keeps separate root lineages (`0` misattribution).
- **Exp 16 (Computational Optionality)**:
  - Exact constrained 0-1 portfolio optimizer shows multi-contributor portable capabilities expanding `|A|` `3 → 9` and `V*` `49.0 → 283.0` (`V_opt = +234.0 [176, 292]`), strictly separated from realized WND.
  - Pre-demand expiration (`0.0 → 0.9`) drops realized ratio `0.96 → 0.10`; 4 counterexamples verify zero-utility task inflation, mutex contention, **P16 maintenance crowding-out (`V_opt = -70.0 < 0`)**, and obsolescence before demand.
- **Exp 11 (Knowledge Asymmetry & Leakage Audit)**:
  - Standard SHA-256 sweep cleanly separates Shannon entropy (`14→0` bits), guessing prob, search ops (`4522x→1x`), and modeled energy (`1574x`), while syntactic Horn-backdoors leak 100% in round 0 (`13.69→0.00` bits)—confirming cryptographic primitives are required for hiding.
- **End-to-End 10-Step Held-Out Chain (`v03_chain_bundle.json`, seeds `9999` & `42424`)**: Connects Creation (`192k` ops) → Transfer (`0%` false-SAFE, T4 caught) → Verified WND (`+383,580` net ops, duplicate rejected) → Shapley P13 → PoC Fingerprint (tamper detected) → Separate Optionality (`+6` tasks, `V_opt=+234`).

## 3. Explicit Non-Claims
A Proof of Creator fingerprint does NOT establish legal ownership, human identity, economic entitlement, or scientific truth. Attribution policies are explicitly separated from the causal evidence graph.
