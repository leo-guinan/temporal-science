# Paper IV — Human Computational Capital: Stable Interfaces and Intergenerational Knowledge Transfer

**Module ID**: `paper-04` | **Version**: `0.1.0` | **Exported Contract**: `TS-HUMAN-CAPITAL`  
**Imports**: `TS-BASE-001`, `TS-005`  
**Status**: Simulation & engineering-model stage ONLY; **blocked for empirical behavioral publication pending real human-subject studies (§8) and P7/P8 formalization**.

## 1. Central Claim
Actionable human expertise can function as reusable computational capital (`TS-008`) when validated, preserved in a Contribution-to-Savings Ledger, and mediated by a compatibility-checked **Human API** (`observe`, `intend`, `correct`, `authorize`, `evaluate`), provided validation and adaptation costs stay below avoided rediscovery and retraining.

## 2. Verified Simulation Evidence (Explicitly Labeled Simulated)
- **Exp 7 (Simulated Human Capital, 60 planted Horn-backdoor SAT tasks)**:
  - Caching validated structural hints cuts simulated human prompting **20x** (`720.0s → 36.0s`, 57 reuses) while cutting machine ops `-77.7%` vs DPLL (`344k → 76.7k`).
  - Human API semantic translation survives a `v1 → v2` backend variable permutation (`t=20`), cutting simulated human time a further **-33.3%** (`24.0s`, 2 prompts, 58 reuses) at `+351` translation ops; faulty hints (50% error test) are 100% caught by the $O(m)$ validator.
- **Exp 10 (Simulated Human API Stability, 200 workflow tasks across `V1..V5`)**:
  - `human_api_adaptive` cuts total simulated human time **-42.0%** vs stateless UI churn (`644.0s` vs `1,110.5s`), eliminates avoidable relearning (`492.5s → 0.0s`), and surfaces the consequential `V3→V4` semantic shift via explicit `authorize` confirmation (`0` silent semantic failures).
  - **Counterexample A (`naive_silent_wrapper`)**: conceals `V3→V4` shift, causing `37` silent semantic failures.
  - **Counterexample B (Legacy Adapter Debt)**: above `6–8` divergent paradigm layers, legacy wrapping (`115.2s + 96k ops`) costs more than clean conceptual retraining (`65.0s`).
- **Exp 5 (Human Renegotiation Trade-off)**: Machine savings (`+88%`) can hide `204s` of simulated human renegotiation unless tracked in separate ledgers.

## 3. Explicit Non-Claims & Required Next Work
Simulated human times are NOT measured human cognitive energy or psychological harm. Requires IRB-approved user studies measuring actual task time, error recovery, and conceptual understanding before empirical behavioral claims.
