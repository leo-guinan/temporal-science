# Outreach Templates & Public Release Checklist

> **Tone Principle:** Peer-to-peer scientific candor. Lead with a concrete, falsifiable engineering/physics question and explicit known failure boundaries—never hype, never claim a solved theory, and explicitly welcome counterexamples.

---

## Template A — Invitation to First Independent External Critic / Replicator

**Subject:** Request for critique / 15-min replication challenge: predicting physical energy break-even of incremental reuse

Hi [Name],

I've followed your work on [specific area: incremental computation / compiler build graphs / hardware energy metering / systems performance]. I'm working on a research program (**Temporal Science**) studying when retaining and validating computational history saves physical energy versus strong incremental recomputation—and, more importantly, whether we can **predict that energy break-even boundary prospectively** before running a workload.

We've built a small, self-contained **Challenge Kit** (`challenge-kit-v1.tar.gz`, Python 3.10+ stdlib only, zero `pip` installs) implementing a blind preregistered 5-component energy model (`E_dispatch + E_validation + E_execution + E_memory + E_maintenance`). On an Apple M3 Max (AC power, `proc_pid_rusage` + `IOReport` whole-SoC), a disjoint 8-module micro-probe predicted full-lifecycle energy savings across a 71-module `_pytest` type-signature checker with strict-blind $R^2 = 0.987$ (CPU) and $R^2 = 0.945$ (Whole-SoC), while our own experiments also exposed clear failure regimes (e.g., fine `K=1` scalar Python reuse fails to beat strong incremental on whole-SoC, disk logging degrades energy by `-8%` to `-19%`, and zero-shot absolute Joules fail across algorithms).

The single most useful next step isn't another internal benchmark—it's testing whether the model **breaks or holds when someone else chooses the codebase and hardware** (especially Linux Intel/AMD RAPL or a wall-plug meter, or a real Git commit history).

Would you be open to running the 15-minute standalone challenge on a Python repo of your choice (or poking holes in the protocol itself)? Whether it confirms the model on new hardware, narrows its validity region, or falsifies it outright, we'd love to credit and publish the finding transparently alongside the Paper I preprint.

Attached / linked:
- Standalone Challenge Kit (`challenge-kit-v1.tar.gz`) + frozen protocol (`prospective-energy-protocol-v1.md`)
- Scoped Paper I Preprint (`manuscript.md`) + offline reproduction bundle (`paper-01-v0.1.0-portable.tar.gz`)

Best,  
[Your Name]

---

## Template B — Outreach to the 8 Prospective Founding-Network Researchers

**Subject:** Temporal Science prospectus & open composable research repository (feedback / critique welcome)

Hi [Name],

Your work on [specific foundational contribution] strongly shaped a research initiative I've been developing called **Temporal Science**, examining how accumulated, validated causal knowledge changes the computational and physical energy cost of reaching equivalent future outcomes—and where maintenance, verification, and volatility costs make memory a net liability.

Rather than sending a speculative manifesto, I waited until we had three concrete things you could actually inspect and stress-test:
1. **A scoped Paper I preprint + offline reproduction bundle** (`paper-01-v0.1.0-portable.tar.gz`, zero external paths) documenting both verified gains and explicit failure boundaries.
2. **An executable Composable Research Repository (CRR v0.2)** that enforces scientific composition rules in CI, tracks transitive impact across five papers, and keeps unverified release tiers (like `energy_focused_paper` and `independently_validated_release`) visibly blocked.
3. **A concise public Research Prospectus** (`prospectus.md`) and a standalone 15-minute **External Energy-Model Challenge Kit** (`challenge-kit-v1.tar.gz`).

We're preparing a field-building accelerator proposal structured around retrospective recognition of independent foundational work (7 founding seats + an 8th open seat reserved for an independent critic/replicator, governed by independent peer review and explicit conflict-of-interest disclosure).

I'd value any candid critique—especially on where our assumptions look weakest, what prior literature we missed in our novelty audit, or whether any piece of the five-paper architecture connects to open problems you care about. No commitment implied at all.

Best,  
[Your Name]

---

## Template C — Public Preprint & Artifact Release Checklist (arXiv / Zenodo / GitHub)

Before publishing publicly:
1. **GitHub Public Repository (`temporal-science`)**:
   - Confirm `python3 tools/research.py validate` → `PASS` (`16` claims, `5` papers).
   - Confirm `python3 tools/research.py test` → `100%` passing (`19/19` tests including Challenge Kit).
   - Confirm `python3 tools/research.py release paper-01 --tier scoped_preprint` → `PASS`, and `--tier energy_focused_paper` → `BLOCKED` (exit `2`).
   - Tag release `v0.1.0-scoped-preprint` and attach BOTH:
     - `papers/01-certified-reuse/release/paper-01-v0.1.0-portable.tar.gz`
     - `outreach/challenge-kit-v1.tar.gz`
2. **Zenodo Archival DOI**:
   - Upload `paper-01-v0.1.0-portable.tar.gz`, `outreach/challenge-kit-v1.tar.gz`, and `CITATION.cff` to obtain permanent citable DOIs.
3. **arXiv Scoped Preprint Submission (`cs.PF` / `cs.SE` / `cs.PL`)**:
   - Export `papers/01-certified-reuse/manuscript.md` to LaTeX/PDF preserving the verbatim **Scope & Evidence Notice** on page 1, the Zenodo DOIs for both archives, and all negative/failure-boundary tables.
