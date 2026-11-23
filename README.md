# Temporal Science Research Initiative (CRR v0.2)

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.24467291.svg)](https://doi.org/10.5281/zenodo.24467291)
**Latest Release:** [`v0.1.1-external-season-1`](https://github.com/leo-guinan/temporal-science/releases/tag/v0.1.1-external-season-1) · **External Challenge:** [`ledger/season-1/EXTERNAL_CHALLENGE_INVITATION.md`](ledger/season-1/EXTERNAL_CHALLENGE_INVITATION.md) · **Observation Ledger:** [`ledger/season-1/`](ledger/season-1/)

**Foundational Research Program, Five-Paper Publication Architecture, and Composable Research Repository**

> *How does a computational system's history change the energy required to reach an equivalent future state?*

This repository organizes the **Temporal Science Research Initiative** as an executable **Composable Research Repository (CRR v0.2)** referencing the preserved, read-only experimental codebase at `../living-computation` (v0.1–v0.3, 25/25 automated tests verified).

## Structure

```text
temporal-science/
├── initiative.yaml                    # Initiative charter & pinned reference to ../living-computation
├── governance.md                      # Scientific boundaries, claim composition & energy/human rules
├── glossary.md                        # Unified notation reconciling Temporal Science & LC-1..LC-24
├── CITATION.cff                       # Interoperable citation metadata
├── schemas/claim-schema.json          # CRR claim contract JSON schema
├── research/
│   ├── foundations/                   # Temporal Science state-transition & transition-energy note
│   ├── literature/                    # 5-field prior-work & novelty audit
│   └── claims/                        # 16 versioned composable claim contracts (TS-BASE-001..TS-PROOF-OF-CREATOR)
├── papers/
│   ├── 01-certified-reuse/            # Paper I  (exports TS-CERTIFIED-REUSE; includes scoped preprint manuscript.md & portable .tar.gz)
│   ├── 02-transferable-computation/   # Paper II (exports TS-TRANSFER-CERTIFICATE)
│   ├── 03-work-not-done/              # Paper III (exports TS-WORK-NOT-DONE)
│   ├── 04-human-capital/              # Paper IV  (exports TS-HUMAN-CAPITAL)
│   └── 05-proof-of-creator/           # Paper V   (exports TS-PROOF-OF-CREATOR)
├── synthesis/
│   ├── prospectus.md                  # Public Temporal Science Research Prospectus & external challenge invitation
│   └── open-questions.md              # Persistent open research & proof obligation backlog
├── reports/
│   ├── initiative-audit.md            # Phase 0 traceability matrix & missing evidence report
│   └── readiness-report.md            # Paper-by-paper & claim-by-claim publication readiness plan
├── tools/research.py                  # CRR v0.2 CLI (validate, impact, build, verify-build, bundle, release, test)
└── tests/
    ├── test_crr.py                    # Structural, impact-query, build, verify-build & tiered release-gate tests
    └── test_adversarial_composition.py # Adversarial scientific-validity & artifact-tampering test suite
```

## Quickstart (CRR v0.2 CLI)

```bash
# 1. Validate all 16 claim manifests, scientific composition rules (S1-S5), version pins, acyclicity, and artifact links
python3 tools/research.py validate

# 2. Query transitive downstream impact of changing or invalidating Paper I's TS-001 (11 downstream claims across all 5 papers)
python3 tools/research.py impact TS-001

# 3. Build reproducible Paper I artifact package and verify every pinned SHA-256 digest live
python3 tools/research.py build paper-01
python3 tools/research.py verify-build paper-01

# 4. Evaluate tiered publication release gates:
#    - scoped_preprint passes for Paper I (operation counts + modeled_proxy energy only)
#    - energy_focused_paper & independently_validated_release block transparently until unmet obligations are satisfied
python3 tools/research.py release paper-01 --tier scoped_preprint
python3 tools/research.py release paper-01 --tier energy_focused_paper

# 5. Build a completely self-contained portable reproduction bundle (zero external relative paths)
python3 tools/research.py bundle paper-01

# 6. Run all CRR, adversarial scientific-composition, and executable claim tests
python3 tools/research.py test
```

## Standalone Clean-Environment Reproduction (Paper I)

An independent researcher can verify Paper I offline in any fresh directory without checking out `living-computation`:

```bash
tar -xzf papers/01-certified-reuse/release/paper-01-v0.1.0-portable.tar.gz -C /tmp/repro
cd /tmp/repro/paper-01-v0.1.0-portable
python3 reproduce.py
```
