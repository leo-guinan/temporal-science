# Temporal Science — External Research Season 1 Public Observation Ledger

> **Core rule:** Record public releases, independent replication attempts, counterexamples, upstream reviews, and preregistered scouting predictions **without claiming credit for independent research we did not cause**. Negative results and falsifications count as first-class contributions.

This ledger is intentionally a lightweight, version-controlled set of Markdown and JSON files—not software infrastructure. Entries are added only when real public artifacts, independent replication runs, upstream reviews, or pre-contact frozen scouting reports occur.

## Observation Streams

| Stream | File | What We Observe | Current Entries |
| :--- | :--- | :--- | :---: |
| **Public Releases** | [`releases.json`](releases.json) | Immutable release tags, GitHub release URLs, Zenodo archival DOIs, post-download SHA-256 verification | `1` (staged, pending public publish) |
| **Energy Challenge** | [`energy-challenge.json`](energy-challenge.json) | Independent replications, counterexamples, scope narrowings, and model prediction accuracy on third-party workloads and hardware | `0` (pending) |
| **External Contributions** | [`external-contributions.json`](external-contributions.json) | Upstream review, acceptance, criticism, and reuse of our work across external mathematical and research environments | `0` (pending) |
| **Unrestricted Research Grants** | [`unrestricted-grants.json`](unrestricted-grants.json) | Pre-contact frozen scouting reports (prior work recognized, question offered, predictions) and subsequent public research | `0 / 8` frozen |

## Public Challenge Invitation

The standalone Season 1 public challenge invitation is maintained in [`EXTERNAL_CHALLENGE_INVITATION.md`](EXTERNAL_CHALLENGE_INVITATION.md) and targets [`challenge-kit-v1.1.0.tar.gz`](../../release/v0.1.1-external-season-1/challenge-kit-v1.1.0.tar.gz) under frozen protocol `TS-PROTO-HW-ENERGY-v1.0.0`.

## Ledger Integrity Rules

1. **No retroactive editing of preregistered entries.** Corrections and clarifications are appended with dates rather than silently overwriting prior predictions or results.
2. **No silent version replacement.** Each published release gets a distinct versioned tag and filename (e.g., `challenge-kit-v1.1.0.tar.gz`, never silently overwriting `v1`).
3. **Explicit evidence boundaries.** Local software/artifact verification (`47/47` tests) is always separated from independent external replication (`pending`), and on-chip PMU/SoC/RAPL counters are never labeled as AC wall-plug energy.
4. **No credit-claiming.** When observing external researchers, upstream repositories, or unrestricted grant recipients, this ledger records public outcomes honestly without attributing independent researcher discoveries to Temporal Science.
