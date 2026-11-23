# Temporal Science — Field-Building Accelerator Supporting Brief

**Date:** November 22, 2026  
**Repository:** `temporal-science` (backed by frozen baseline `living-computation` v0.1–v0.3)  
**Companion Documents:** `synthesis/prospectus.md`, `papers/01-certified-reuse/manuscript.md`, `protocols/prospective-energy-protocol-v1.md`, `outreach/challenge-kit-v1/`

---

## 1. Executive Summary

**Temporal Science** investigates a concrete, measurable question at the intersection of computer science, systems engineering, control theory, and thermodynamics:

> **When does retaining, validating, and reusing a computational system's history reduce the physical energy required to achieve an equivalent future outcome—and can we predict that break-even boundary before running the computation?**

Rather than proposing a speculative paradigm from scratch, this application brings **three functioning assets already built, tested (`43/43` automated tests), and audited with explicit negative results**:

1. **A Falsifiable Scientific Proposition:** *Temporal Energy Advantage Under Validated Reuse*—that physical energy savings depend conditionally on the ratio between avoided computation and the complete costs of dispatching, validating, accessing, and maintaining reusable structure ($E_{\text{reuse}} = E_{\text{dispatch}} + E_{\text{validation}} + E_{\text{execution}} + E_{\text{memory}} + E_{\text{maintenance}}$).
2. **Reproducible Experimental Evidence—Including Where Our Hypothesis Fails:** Completed benchmarks spanning synthetic DAGs (`Living Computation` v0.1–v0.3), Apple M3 Max per-process PMU & whole-SoC energy studies (`exp_hw01`–`exp_hw04`), two independently sourced real-code workloads (`117` Python stdlib modules; `71` `_pytest` modules), and an empirical break-even study of our own research infrastructure (`exp_crr_breakeven`).
3. **Working Open Coordination Infrastructure:** A **Composable Research Repository (CRR v0.2)** that enforces scientific composition rules in CI, tracks transitive impact across five modular papers (`16` versioned claims), blocks premature release tiers honestly, and ships offline zero-external-path reproduction bundles alongside a standalone **External Challenge Kit (`challenge-kit-v1.tar.gz`)**.

---

## 2. Summary of Verified Evidence & Honest Failure Boundaries

| Domain | Verified Positive Result | Verified Failure / Negative Boundary |
|---|---|---|
| **Certified Reuse Soundness (Paper I)** | `0` false-SAFE errors across `40,004` DAG updates + `2,000+` fuzz probes; `+15.3%` ops vs strong incremental (`+93.6%` vs full). | Unsound periodic canaries (`P=5..50`) fail silently (`77.6%–98.4%` error); full trace logging loses `-167%` ops; high-entropy shock (`p > 0.12`) turns net negative. |
| **Apple M3 Max Physical Energy (`exp_hw01`–`exp_hw04`)** | Whole-SoC (`CPU+GPU+ANE+DRAM+DCS+AMCC`) savings on real code: `+18.7%–63.9%` on `117` stdlib modules (`+82.2%` vs full); `+21.2%–89.0%` on `71` `_pytest` modules (`+76.9%` vs full; `0` mismatches). | Unmodified fine scalar `K = 1` DAG vs strong incremental is **not robust** (`+1.2%` CPU Py3.12 battery; `-1.2% to -6.1%` Whole-SoC); synchronous disk logging degrades CPU (`-8.2%`) and DRAM/fabric (`-19.0%`) energy; zero-shot absolute Whole-SoC Joules fail (`R² = -0.545`). |
| **Prospective Energy Prediction (`exp_hw04` blind audit)** | 5-component primitive micro-probe (`8` modules; pays back in `N*_cal = 1–3` runs) predicts `_pytest` energy strictly blindly: **$R^2 = 0.987$** CPU (`2.08 pp` MAE) and **$R^2 = 0.945$** Whole-SoC (`1.48 pp` MAE). | Still single architecture (Apple M3 Max), SoC-internal telemetry (not AC wall-plug or discrete SSD rail), and experimentally mutated edits rather than uncontrolled Git commit histories. |
| **Research Infrastructure Break-Even (`exp_crr_breakeven`)** | CRR v0.2 catches **`100%` (`6/6`)** of injected scientific defects (vs `16.7%` conventional, `33.3%` modular) and `100%` transitive impact (vs `6%–36%` single-pass `grep`). | Unindexed `PyYAML` CRR **loses** on pure machine-only metadata time/energy (`-149 mJ` to `-2,367 mJ`/reuse) and disk storage (`3.6x` larger), and loses under high churn (`4x` edit-to-reuse) unless avoided upstream compute exceeds `~0.024·V` J. |

**Institutional Discipline:** Paper I's `scoped_preprint` tier passes, while `energy_focused_paper` and `independently_validated_release` remain formally **blocked** in CI until external cross-architecture RAPL/wall-plug metering and independent replications are completed.

---

## 3. Why Accelerator Funding Unlocks the Transition to a Distributed Field

The bottleneck is no longer solo prototype engineering—it is **independent external scrutiny and cross-lab replication**. Accelerator support turns a single researcher's verified infrastructure into an open, decentralized living research network:

- **Entry Point Requiring Zero Ideological Buy-In:** External researchers do not have to accept the full five-paper agenda. They can start with one self-contained question using `challenge-kit-v1.tar.gz` (*"Does the 5-term energy prediction model work on a workload and machine you choose?"*).
- **7 + 1 Founding Cohort & Retrospective Recognition Governance:** Seven founding seats + an eighth open seat reserved for an independent critic/replicator. Cohort selection and micro-grants are anchored to **retrospective recognition of verifiable, reproducible artifacts** (formal proof audits, cross-architecture RAPL/wall-plug replications, real Git-history tests, or decisive counterexamples), governed by documented independent peer review and mandatory public conflict-of-interest disclosure (`governance.md`).
- **Equal Archival Weight for Falsifications:** Failed replications and counterexamples are published directly inside the CRR claim graph with full attribution and trigger automated downstream impact reviews.

---

## 4. Proposed 12-Month Field-Building Milestones

1. **Months 1–3 (Public Release & First Independent Critique):** Publish Paper I (`scoped_preprint`) on arXiv/Zenodo alongside `paper-01-v0.1.0-portable.tar.gz` and `challenge-kit-v1.tar.gz`; fund/incentivize `2–3` independent cross-architecture (Linux Intel/AMD RAPL & external wattmeter) replications and falsification attempts.
2. **Months 4–6 (Real-History & Adaptive Routing Validation):** Test the frozen 5-term model on uncontrolled historical Git commit logs (Rust/TypeScript/Python) and benchmark a cost-aware **Temporal Energy Router** (`exp_hw05`) with full calibration-payback accounting.
3. **Months 7–9 (Multi-Lab Composable Paper II–III & CRR Indexing):** Address CRR v0.2's `PyYAML` scaling bottleneck (`V >= 100`) discovered in `exp_crr_breakeven` via a cached index, and onboard external contributors to co-author Paper II (Transferable Computation) and Paper III (Verifiable Work Not Done).
4. **Months 10–12 (IRB Human Workflow Study & Founding Cohort Review):** Execute a controlled human-subject study calibrating the empirical human break-even of CRR and Paper IV (Human Temporal Capital), and convene an independent external review panel for founding cohort allocations.
