# Temporal Science — Research Prospectus

**Version:** 1.0 · **Date:** November 22, 2026  
**Repository:** `temporal-science` (backed by frozen baseline `living-computation` v0.1–v0.3)  
**Audience:** External researchers, scientific reviewers, and field-building accelerator evaluators

---

## 1. The Question

Classical computer science mostly measures the cost of a computation as if the machine starts from scratch every time. Yet almost every real system—a build pipeline, a sensor network, a control loop, a scientific workflow, or a human organization—solves streams of related problems over an environment that changes unevenly over time.

**Temporal Science** studies a simple, measurable question:

> **How does a system's accumulated history change the computational and energetic cost of reaching an equivalent future outcome—once every cost of observing, storing, verifying, maintaining, and retiring that history is counted honestly?**

Our working hypothesis is **conditional, not universal**: validated causal knowledge can substantially reduce future work when environments exhibit local or recurring structure, and can *increase* total cost when maintenance, verification, or environmental volatility outweigh reuse. Mapping both the gains and the exact failure boundaries is the core empirical program.

---

## 2. Why This Matters Now

Modern computing systems spend enormous energy recomputing nearly identical subproblems, over-sampling stable environments, and re-discovering capabilities across organizational boundaries. At the same time, informal caching, unverified learned heuristics, and ad-hoc AI shortcuts silently break when underlying conditions drift.

Temporal Science sits at the intersection of incremental computation, control theory, formal verification, and resource accounting. Rather than proposing a speculative new physical law or claiming breakthroughs on worst-case complexity (we make **no claims** regarding `P = NP`), the initiative builds:

1. **Formal validity contracts and cheap boundary checks ("canaries")** that distinguish `SAFE` reuse from `UNSAFE` drift and `UNKNOWN` ambiguity.
2. **Complete lifecycle accounting** that charges every overhead—compilation, storage, I/O, communication, verification, and fallback—to the same ledger.
3. **Verifiable counterfactual accounting ("Work Not Done")** and tamper-evident provenance so avoided work can be audited without being fabricated or double-counted.

---

## 3. Preliminary Evidence—and Where the Hypothesis Breaks

Across three experimental cycles (`living-computation` v0.1–v0.3, 16 experiments and 25 automated tests), we tested both the upside and the failure limits of the framework on deterministically seeded benchmarks. All energy figures below are **`modeled_proxy` energy** (computed from explicit fixed operation/memory/I/O weights), **not** physically metered hardware joules.

### What works so far (under stated assumptions)
- **Certified DAG reuse (Paper I):** On a `1,000`-node computational DAG over `40,004` updates across four regimes, exact boundary canaries achieved **`0` output mismatches** and **`0` false-SAFE errors** across `2,000+` fuzz probes. Under localized regime drift, surprise-driven contract compilation cut total operations by **93.63%** vs. full recomputation and **15.32%** vs. a strong dirty-propagation incremental baseline (payback in `408` steps).
- **Adaptive observation & bounded sync (Paper I):** Canary-probed sensor selection cut modeled energy by **75.95%** across `60` sensors while recovering from mid-run relevance drift (`131` steps), where static learned selection failed permanently (`2,533` safety violations). Under a bounded `1.85x` dynamical shift, interval-certified predictive synchronization maintained **`0.00%` violations** while cutting modeled energy `14.8%` and flagging the shift in `5` steps via `UNKNOWN`.
- **Cross-environment transfer & enclosure detection (Paper II):** Explicit translation maps and external reality probes transferred modular capabilities across schema and semantic shifts with **`0%` false-SAFE errors** (`-87.0%` ops under partial drift) and caught "institutional enclosure" (100% internally consistent, externally wrong) where internal checks failed blindly.
- **Anti-fraud Work Not Done & Provenance (Papers III & V):** A tiered verifier rejected **8/8** fabricated, cost-shifted, or duplicated avoidance claims. While brute-force replay verification cost `4.2x–9.3x` more than the avoided work, contract-bounded verification cost `612` ops (`75.7x` cheaper than `46.3k` net avoided ops). Content-addressed evidence graphs with Shapley accounting strictly conserved attribution (`sum = verified savings`) where naive path attribution inflated credit `3x`.

### Verified failure boundaries (equally important)
- **Operation counts $\ne$ energy:** Switching trace logging from in-memory to synchronous disk JSONL kept operation savings positive (`+15.32%`) while flipping modeled energy **negative** (`-6.60%` to `-10.32%`).
- **Volatility crossover:** Above shock rate $p \approx 0.10\text{–}0.12$, static contract reuse turns negative (`-5.08%` to `-47.67%`); adaptive retirement bounds loss to `-5.48%` but cannot create savings from pure noise.
- **Simpler baselines win in stationary regimes:** On stationary linear-Gaussian dynamics, simple periodic polling (`P = 3`, `1.15 J`) beat adaptive Kalman sampling (`2.53 J`), and worst-case interval bounds degraded to `100%` observation under unbounded Gaussian noise.
- **Full trace logging fails completely:** Naive full trace materialization increased total cost by `+167%` and never reached payback.
- **Syntactic structure is not cryptographic security:** Reused Horn-backdoor structure leaked `100%` of secret variables on round `0`, proving real cryptography is required for hiding.
- **Human-capital experiments are simulation-only:** All human-attention and cognitive-load findings (Paper IV) currently come from modeled agents, not real human participants.

---

## 4. The Five-Paper Composable Architecture

Rather than publishing one monolithic paper or five loosely linked essays, Temporal Science is structured as five independent papers that import and export explicit versioned research contracts:

| Paper | Title | Exported Contract | Current Highest Passing Gate | What Blocks Higher Release Tiers |
|---|---|---|---|---|
| **Paper I** | Certified Computational Reuse Under Environmental Change | `TS-CERTIFIED-REUSE` | **`scoped_preprint`** *(ops + modeled proxy energy; manuscript & portable bundle ready)* | Hardware energy metering (`energy_focused_paper`); external non-synthetic replication (`independently_validated_release`) |
| **Paper II** | Transferable Computation Across Shifting Environments | `TS-TRANSFER-CERTIFICATE` | `technical_report` | Non-synthetic cross-institution benchmarks; P8/P11 external audit |
| **Paper III** | Verifiable Work Not Done and Compounding Computational Capital | `TS-WORK-NOT-DONE` | `technical_report` | Hardware metering; compositional multi-claim baseline rules |
| **Paper IV** | Human Temporal Capital: Attention, Cognitive Load, and Sustainable Reuse | `TS-HUMAN-CAPITAL` | `technical_report` | **Real human-subject studies** (IRB-approved); currently simulation-only |
| **Paper V** | Proof of Creator: Causal Provenance, Attribution, and Computational Optionality | `TS-PROOF-OF-CREATOR` | `technical_report` | Cryptographic adversarial audit; real-world pilot beyond synthetic chains |

---

## 5. Infrastructure: Composable Research Repositories (CRR)

A distinguishing feature of this initiative is that its publication discipline is enforced in code (`temporal-science/tools/research.py`):

- **Executable claim manifests:** 16 claims (`TS-BASE-001`, `TS-001`–`TS-010`, and 5 exported paper contracts) declare explicit assumptions, guarantee tiers, energy-evidence tiers, and invalidation conditions.
- **Automated dependency & impact analysis:** Running `research impact TS-001` immediately traces **11 downstream claims across all five papers** so that if a foundational assumption is narrowed or falsified, every dependent claim is flagged for review.
- **Scientific composition rules (not just syntax checks):** Automated validation rejects formally proved theorems that silently depend on unproved or partially supported claims, blocks energy-tier inflation (`physically_measured_energy` without hardware metering), blocks scope misuse (extrapolating `simulated` human agents to `real_human` claims), blocks guarantee inflation, and detects 1-byte artifact tampering via SHA-256 verification.
- **Tiered, honest release gates:** Every paper is evaluated against four explicit tiers (`technical_report`, `scoped_preprint`, `energy_focused_paper`, `independently_validated_release`) so ready preprints can ship under tight scope while unmet scientific obligations remain visibly blocked.
- **Zero-external-path portable bundles:** Each release compiles into a self-contained `.tar.gz` archive with an offline `reproduce.py` script that verifies checksums and re-runs core proofs and benchmarks in a clean directory.

---

## 6. Governance and Founding Cohort Model (7 + 1 Open Seat)

Building a credible new research area requires open governance and external scrutiny from day one.

- **Founding Cohort Structure (7 + 1):** The initiative plans a founding cohort of seven core researchers plus an **eighth open seat** reserved specifically for an independent external critic or replicator.
- **Retrospective Recognition & Conflict-of-Interest Policy:** Founding-cohort membership is designed around **retrospective recognition of verifiable foundational contributions**—evaluated against documented criteria (formal proofs, reproducible empirical benchmarks, independent replication, or decisive counterexamples)—rather than arbitrary self-appointment. Any affiliation, funding, prior collaboration, or financial relationship among reviewers, editors, and cohort candidates must be disclosed publicly in `governance.md`, and selection decisions require independent external review rather than unilateral approval by the initiative's originator.
- **Open Falsification Policy:** Counterexamples, negative results, and failed replications carry equal archival weight to positive results and are recorded directly in the affected claim manifests.

---

## 7. An Explicit Invitation: Come Challenge Paper I

The single highest-value next step for Temporal Science is **not** another supportive essay—it is an **independent external attempt to break, narrow, or rigorously test Paper I**.

We invite a first external researcher (in systems, incremental computation, computer architecture, or control theory) to download the self-contained Paper I bundle (`paper-01-v0.1.0-portable.tar.gz`) and pursue any of four concrete challenges:

1. **Hardware Energy Audit:** Instrument the Paper I DAG and observation workloads with Intel RAPL, Apple `powermetrics`, or wall-socket metering to test whether cache and memory-hierarchy effects preserve or overturn our `modeled_proxy` energy findings.
2. **Real-World Workload Stress Test:** Replace our `1,000`-node synthetic DAG with a real compiler dependency graph, build graph, or streaming analytics pipeline and measure whether certified reuse still beats a tuned incremental baseline.
3. **Formal Soundness Attack:** Audit `TS-001` (`research/claims/TS-001/proof.md`) and `TS-003` (`P4`) for hidden assumptions, edge cases, or counterexamples.
4. **Baseline Strengthening:** Propose a stronger stateless, incremental, or periodic baseline that narrows the region where certified reuse pays back.

Whether that independent investigation confirms Paper I on real hardware, sharpens its boundaries, or falsifies a core claim, the result will be published transparently alongside the repository and directly advances the field.

---

**Contact & Artifacts:**  
- Paper I Scoped Preprint: `papers/01-certified-reuse/manuscript.md`  
- Portable Reproduction Archive: `papers/01-certified-reuse/release/paper-01-v0.1.0-portable.tar.gz`  
- Novelty & Literature Audit: `research/literature/novelty-audit.md`  
- Open Questions & Falsification Agenda: `synthesis/open-questions.md`  
- Governance & Standards: `governance.md`
