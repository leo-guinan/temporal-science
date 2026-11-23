# Scientific Readiness Assessment & Prioritized Publication Plan

**Date:** November 22, 2026  
**CRR Validation Status:** All 16 claims and 5 paper modules structurally validated; all referenced Living Computation artifacts verified on disk.

---

## 1. Paper-by-Paper Publication Readiness

| Paper | Exported Contract | Preprint Ready (Scoped)? | Final Release Ready? | Strongest Verified Result | Primary Blocking Work Required |
|---|---|---|---|---|---|
| **Paper I** — Certified Computational Reuse | `TS-CERTIFIED-REUSE` | **YES** *(ops & modeled J only)* | **NO** | `+15.32%` ops vs strong topological incremental (`40,004` exact steps, `0` false-SAFE); P4 `0.00%` shift viol; Exp 9 `6.08x` Jump/Jitter | 1) Hardware-metered physical energy benchmark (§19); 2) Larger non-synthetic DAG replication; 3) P5/P9 proofs |
| **Paper II** — Transferable Computation | `TS-TRANSFER-CERTIFICATE` | **YES** *(synthetic institutions)* | **NO** | `-90.8%` (T1), `-79.9%` (T2), `-87.0%` (T3, 8/12 retained), `0%` false-SAFE; catches T4 enclosure; Exp 5 `-76.3%` SAT ops with `0` dropped clauses | 1) Independent non-synthetic destination benchmark; 2) External review of semantic equivalence mappings |
| **Paper III** — Verifiable Work Not Done | `TS-WORK-NOT-DONE` | **YES** *(ops & modeled J)* | **NO** | `3/3` claim tiers accepted, `8/8` adversarial attacks rejected; proves `612`-op math-bound verify beats `433k`-op full replay by `708x` | 1) Compositional multi-claim WND theorem for shared baselines; 2) Hardware-metered energy certificate tier |
| **Paper IV** — Human Computational Capital | `TS-HUMAN-CAPITAL` | **NO** *(simulation-only technical note OK, NOT behavioral paper)* | **NO** | `20x` simulated human prompt reduction via reusable hints; `-42%` simulated human time & `0` silent semantic failures via Human API | 1) **IRB-approved human-subject study** measuring real task time & comprehension (§8); 2) Formal P7 & P8 proofs |
| **Paper V** — Proof of Creator | `TS-PROOF-OF-CREATOR` | **YES** *(prototype protocol & simulation)* | **NO** | End-to-end 10-step held-out chain (`+383k` net WND, Shapley P13 conserved, `4/4` tamper detection, separate `V_opt=+234`, CE3 `V_opt=-70`) | 1) Depends on Paper III & IV gates clearing; 2) Multi-party independent verification trial |

---

## 2. Claim-Level Readiness Breakdown

- **Publishable Now (under explicit assumptions & scoped caveats)**:
  - `TS-BASE-001`, `TS-001`, `TS-002` *(operation-count claims)*, `TS-003` *(bounded disturbance)*, `TS-004` *(simulation)*, `TS-005` *(synthetic T1–T4)*, `TS-006` *(certified SAT subfamilies)*, `TS-007` *(non-overlapping single-claim WND)*, `TS-009` *(integrity & Shapley conservation)*, `TS-010` *(constrained optionality + P16 non-monotonicity)*.
- **Requires Additional Work Before Final Claims**:
  - `TS-CERTIFIED-REUSE` & `TS-WORK-NOT-DONE`: require **hardware-metered physical joules** before claiming physical transition-energy advantage $\widehat{TA}_E$.
  - `TS-008` & `TS-HUMAN-CAPITAL`: strictly restricted to synthetic engineering claims until **real human-subject data** and P7/P8 proofs are completed.

---

## 3. Prioritized Publication & Execution Sequence

1. **Priority 1 — Physical Energy Measurement Harness (§19, unlocks Paper I & Paper III)**:
   - Port Milestone 01+02's 1,000-node DAG runner (or a tight C/Rust kernel) onto a hardware-metered host (Linux Intel/AMD RAPL or macOS `powermetrics` outside sandbox) with fixed frequency governor, idle-baseline subtraction, and 20-trial uncertainty intervals.
2. **Priority 2 — Release Paper I (`paper-01`) Preprint & Independent Audit**:
   - Use `python3 tools/research.py build paper-01` to freeze the RO-Crate + SHA-256 manifest + evidence appendix; complete P5 online retirement regret analysis.
3. **Priority 3 — Advance Paper II (`paper-02`) & Paper III (`paper-03`) in Parallel**:
   - Add one non-synthetic destination dataset to Exp 12 (Paper II) and prove compositional non-overlapping WND rules (Paper III).
4. **Priority 4 — Human-Subject Protocol for Paper IV (`paper-04`)**:
   - Design an IRB-ready controlled workflow study comparing stateless UI churn vs. Human API semantic translation on real participants, and complete P7/P8 proofs.
5. **Priority 5 — Assemble Paper V (`paper-05`) & Temporal Science Overview**:
   - Pin released versions of `TS-CERTIFIED-REUSE`, `TS-TRANSFER-CERTIFICATE`, `TS-WORK-NOT-DONE`, and `TS-HUMAN-CAPITAL`, then publish Paper V and the field overview linking all five contracts.
