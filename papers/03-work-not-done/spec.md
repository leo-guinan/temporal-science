# Paper III — Verifiable Work Not Done: Efficient Certificates of Computational Avoidance

**Module ID**: `paper-03` | **Version**: `0.1.0` | **Exported Contract**: `TS-WORK-NOT-DONE`  
**Imports**: `TS-BASE-001`, `TS-CERTIFIED-REUSE`, `TS-TRANSFER-CERTIFICATE`

## 1. Central Claim
Outcome-equivalent resource reductions can be independently certified against credible baselines via tiered **Work Not Done Certificates** (`TS-007`) that reject fabricated, shifted, and duplicated claims and verify orders of magnitude more cheaply than full replay when backed by mathematically bounded contracts.

## 2. Verified Evidence Mapping (Living Computation v0.3)
- **Exp 13 (`wnd_verifier.py`)**:
  - **3/3** positive claims accepted across distinct non-equivalent tiers (`REPLAY_MEASURED`, `MATHEMATICALLY_BOUNDED`, `STATISTICALLY_ESTIMATED`).
  - **8/8** adversarial claims rejected (`INFLATED_BASELINE`, `INCORRECT_OUTPUTS`, `HIDDEN_HUMAN_EFFORT`, `UNCHARGED_PREPROCESSING`, `DEFERRED_COMPUTATION`, `DUPLICATED_CLAIM`, `WEAKENED_REQUIREMENTS`, `EXPIRED_OR_INVALID_CONTRACT`).
  - **Verification Economics**: Full independent replay costs `433,145` ops (`9.3x` saved work) and cached-baseline replay costs `193,416` ops (`4.2x`), whereas mathematically bounded certificate verification costs **`612` ops** (`75.7x` cheaper than `46,313` net WND).
- **Exp 15 (Longitudinal Portable Payback, P14)**:
  - Cross-institution reuse scales `+21.2%` ($M=1$) → `+59.3%` ($M=16$), paying back `4.4x` faster than local persistence (`t=24` vs `t=106`); high churn (`>= 0.06`) flips static capital into `-95.4%` liability, bounded to `-7.1%` by adaptive retirement.

## 3. Formal Contributions & Remaining Gaps
- **Proved**: P12 (WND Accounting Condition), P14 (Portable Knowledge Payback).
- **Gaps**: Compositional WND rules for shared baselines and physically metered hardware energy certificates (separate from operation counts & modeled proxy joules).
