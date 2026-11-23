# Temporal Science — Immutable Release `v0.1.1-external-season-1`

**Release Tag:** `v0.1.1-external-season-1`  
**Date:** November 23, 2026  
**Status:** Public Scoped Preprint & External Replication Release (**External Research Season 1**)

---

## Important Distinction: Internal Verification vs. Independent Replication

> **Read This First:**  
> All automated test counts reported in this release (`47/47` local tests: `22` in `temporal-science` + `25` in the frozen read-only `living-computation` baseline) verify **internal software integrity, schema/composition checks, and local reproducibility on the development machine** (Apple M3 Max, macOS, Python 3.11.7). They **do not constitute independent external replication**, cross-architecture hardware confirmation (Intel/AMD RAPL), or AC wall-plug energy proof.

### Release Gate Status (Transparently Preserved)
| Paper I Release Tier | Status | Notes |
|---|---|---|
| `technical_report` | **PASS** | Formal proofs under stated premises + operation/modeled/hardware pilot results |
| `scoped_preprint` | **PASS** | Scoped to exact operation counts, `0`-false-SAFE soundness, and `modeled_proxy` energy, plus transparently scoped Apple M3 Max hardware extension (`exp_hw01`–`exp_hw04`) |
| `energy_focused_paper` | **BLOCKED** | Requires true AC wall-plug / discrete SSD-rail energy metering, cross-architecture (Intel/AMD RAPL) replication, and uncontrolled real Git commit studies |
| `independently_validated_release` | **BLOCKED** | Requires independent external replication by researchers outside the originating effort and external proof audit of open obligations `P5`/`P9` |

---

## Release Contents

1. **`paper-01-v0.1.0-portable.tar.gz`** — Self-contained offline reproduction archive for Paper I (*Certified Computational Reuse Under Environmental Change*), zero external relative paths; run `python3 reproduce.py` in any clean directory.
2. **`challenge-kit-v1.1.0.tar.gz`** — Standalone, zero-dependency external replication kit (`v1.1.0`, Python 3.10+ stdlib only) enabling any researcher to test or falsify the 5-component physical energy model on **their own Python repository**, including:
   - Real historical Git commit replay (`--git-history N`) and external JSON edit streams (`--edits-json FILE`).
   - Explicit telemetry scope classification (`process_attributed_cpu_pmu`, `package_rapl_hardware`, `wall_cpu_time_only`; `"is_wall_plug_energy": false`).
   - Linux RAPL domain discovery, exact `max_energy_range_uj` wraparound handling, and explicit `PermissionError` diagnostics.
3. **`raw-results-v0.1.1.tar.gz`** — Complete pinned JSON summaries, SHA-256 sealed preregistrations, methodological audits, and experiment reports across `exp_hw01`–`exp_hw05` and `exp_crr_breakeven`.
4. **`paper-01-manuscript.md`** — Updated scoped Paper I preprint manuscript (including Section 5.6 hardware & prospective validation extension).
5. **`prospectus.md`** — Public Temporal Science Research Prospectus & open falsification invitation.
6. **`prospective-energy-protocol-v1.md` & `.yaml`** — Frozen anti-leakage evaluation protocol (`TS-PROTO-HW-ENERGY-v1.0.0`, banning shared RNG seeds between preregistration and evaluation).
7. **`exp_hw04-methodological-audit.json` & `exp_hw04-report.md`** — Full independent audit disclosing `exp_hw04`'s shared static RNG seed schedule, reporting strictly blind unseen-schedule scores ($R^2 = 0.987$ CPU / $0.945$ Whole-SoC), and reporting calibration payback ($N^*_{\text{cal}} = 1\text{–}6$ runs).
8. **`CITATION.cff`** — Standard citation metadata.
9. **`SHA256SUMS.txt`** — Cryptographic checksums for verifying every file in this release (`shasum -a 256 -c SHA256SUMS.txt`).

---

## Explicit Negative Results & Failure Boundaries Preserved in This Release

We highlight where our hypotheses failed or narrowed so external reviewers can target them directly:
- **Fine scalar granularity (`K = 1`):** Unmodified scalar Python DAG reuse failed to achieve robust Whole-SoC energy savings against Strong Incremental (`-1.21 ± 21.34%` in `exp_hw02`, `-6.10 ± 23.20%` in `exp_hw03`).
- **Disk I/O inversion:** Synchronous disk JSONL trace logging significantly degraded process CPU (`-8.21%`) and Whole-SoC Memory+Fabric (`-19.02%`) energy even while abstract ops stayed `+15.7%`.
- **Zero-shot absolute Joule failure:** Cross-workload zero-shot prediction from `exp_hw03` failed on `_pytest` Whole-SoC absolute Joules ($R^2 = -0.545$), demonstrating why local primitive calibration is required for physical scale.
- **Router calibration payback boundary (`exp_hw05`):** Although the 5-term Temporal Energy Router achieved `87.5%` accuracy (`0.18 J` execution regret), its upfront `12.58 J` calibration energy did not pay back against `always_reuse` over `24` mixed tasks because in-memory reuse mistakes were tiny (`0.25 J` total downside vs `26.80 J` upside).
- **CRR infrastructure overhead (`exp_crr_breakeven`):** Unindexed `PyYAML` CRR v0.2 loses on pure machine metadata time/energy and disk storage (`3.6x` larger) across all tested scales ($V = 5..100$) when downstream tasks only run trivial unit checks.

---

## Quick Verification

```bash
# Verify every release artifact checksum
shasum -a 256 -c SHA256SUMS.txt

# Offline Paper I reproduction in a clean directory
tar -xzf paper-01-v0.1.0-portable.tar.gz && (cd paper-01-v0.1.0-portable && python3 reproduce.py)

# Run the standalone external Challenge Kit on any Python Git repository you choose
tar -xzf challenge-kit-v1.1.0.tar.gz && cd challenge-kit-v1.1.0
python3 challenge_runner.py --repo /path/to/your/git/repo --phase preregister --out ./run
python3 challenge_runner.py --repo /path/to/your/git/repo --phase evaluate --out ./run --git-history 20
```
