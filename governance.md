# Temporal Science — Scientific Governance & Claim Composition Policy

Version 0.1.0 · November 22, 2026

## 1. Scientific Boundaries (Prohibited Overclaims)

No manuscript, claim contract, or automated summary in this initiative may claim without new independent evidence:
1. A resolution of $\mathrm{P}$ vs $\mathrm{NP}$, or that formal languages change complexity class over physical time.
2. A new physical or thermodynamic law derived solely from operation-count or proxy-energy benchmarks.
3. That representation compression necessarily reduces physical energy consumption.
4. That knowledge transfer or persistent memory is universally beneficial across all churn regimes.
5. That cryptographic digests or authenticated provenance establish empirical truth, legal authorship, or economic ownership.
6. That simulated-human experiments measure actual human psychology, cognition, or behavior.
7. That automated CI checks or passing unit tests constitute formal proof verification or independent scientific peer review.
8. That every source of avoided work admits unique causal attribution.

## 2. Claim Composition Rules

A downstream claim may depend on an upstream claim only when:
1. The upstream claim carries a stable identifier and pinned semantic version.
2. All imported assumptions are surfaced explicitly in the downstream specification.
3. The downstream workload/model satisfies those assumptions.
4. The imported guarantee tier is preserved (never silently upgrading `empirical` or `simulated` evidence into `formally_proved_under_assumptions` or `physically_measured`).
5. The upstream claim is neither `invalidated` nor `contradicted` for the downstream scope.
6. Translation, validation, monitoring, and retirement costs are accounted for in separate unit channels.

When an upstream claim changes version or status, downstream dependents are **flagged for review** via `research impact <CLAIM_ID>`—not automatically declared false.

## 3. Energy & Human-Subject Reporting Rules

- **Three distinct savings claim types**: (1) operation avoidance, (2) modeled energy avoidance (`modeled_proxy`), and (3) physically measured energy reduction (requires metered hardware telemetry). Never conflate them.
- **Human-subject claims**: All synthetic agent results must carry explicit `simulated` tags. Empirical claims about human learning, retraining, or organizational behavior require informed-consent human-subject data or properly cited prior empirical literature.
- **Preservation of historical artifacts**: Reference results in `../living-computation/results/` are strictly immutable. New experiments or replications must write to new versioned directories.
