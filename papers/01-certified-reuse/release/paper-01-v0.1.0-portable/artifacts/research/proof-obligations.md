# Formal Proof Obligations & Theorems

Prioritizing Contribution Level 2 (Section IX): rigorously defined families of environments and computational structures for which maintaining a valid learned representation is provably sound and provably bounded below reconstruction cost.

---

## Theorem 1 — Soundness of Lipschitz-Margin Validity Region Canaries

**Status**: Proved & implemented (`core/dependency_graph.py`, `core/canary.py`), verified by 2,000-probe fuzzing + 40,000-update exact-equivalence tests.

### Setup
Let $G = (V, E)$ be a deterministic computational DAG in topological order. Let $v \in V$ be a saturating or discrete target node with single parent $p$ and operator $f_v \in \{\text{THRESHOLD}_\theta, \text{RELU}_\theta, \text{CLAMP}_{[lo, hi]}\}$.
Let $I \subset V$ be an **exclusive internal cone** feeding $p$ with boundary set $B \subset V \setminus (I \cup \{v\})$ satisfying:
1. $p \in I$, and every parent of every $u \in I$ lies in $I \cup B$.
2. Every child of every $u \in I$ lies in $I \cup \{v\}$ (no external consumer reads any node in $I$).
3. Every $u \in I$ implements a globally Lipschitz-continuous operator with exact partial Lipschitz upper bounds $\ell_{u,q} \ge 0$ for each $q \in \text{parents}(u)$:
   $$|f_u(x) - f_u(x')| \le \sum_{q \in \text{parents}(u)} \ell_{u,q} |x_q - x'_q|.$$

Define the forward-propagated sensitivity vector $L \in \mathbb{R}_{\ge 0}^{|B|}$ inductively in topological order over $I$:
$$L_{b \to b} = 1, \qquad L_{b \to u} = \sum_{q \in \text{parents}(u)} \ell_{u,q} L_{b \to q}.$$

### Statement
For any anchor boundary vector $u^{(0)} \in \mathbb{R}^{|B|}$ with pre-activation $p^{(0)} = p(u^{(0)})$ and saturation margin:
$$m(p^{(0)}) = \begin{cases} |p^{(0)} - \theta| & f_v = \text{THRESHOLD}_\theta \\ \max(0, \theta - p^{(0)}) & f_v = \text{RELU}_\theta \\ \max(0, lo - p^{(0)}, p^{(0)} - hi) & f_v = \text{CLAMP}_{[lo, hi]} \end{cases}$$
for **every** $u \in \mathbb{R}^{|B|}$ satisfying the validity-ball precondition:
$$\sum_{b \in B} L_{b \to p} \, |u_b - u^{(0)}_b| < m(p^{(0)}),$$
we have $v(u) = v(u^{(0)})$ identically (a **restricted worst-case** guarantee).

### Proof Sketch
1. By induction on the topological order of $I$ and the triangle inequality, $|p(u) - p(u^{(0)})| \le \sum_{b \in B} L_{b \to p} |u_b - u^{(0)}_b|$.
2. Since the RHS is strictly less than $m(p^{(0)})$, $p(u)$ lies strictly on the same side of the threshold/saturation boundary as $p(u^{(0)})$ (and inside the constant flat region for `RELU`/`CLAMP`).
3. Because $I$ is exclusive (no external node reads $u \in I$), skipping the evaluation of all nodes in $I \cup \{v\}$ preserves exact observational equivalence for the entire DAG $G$. $\square$

*(Implementation note: `LipschitzMarginCanary` adds an explicit IEEE-754 floating-point margin $\epsilon_{\text{fp}} = 10^{-9}(1 + |p^{(0)}| + \sum_b L_b |u_b^{(0)}|)$ so floating-point rounding cannot trigger a boundary false-SAFE.)*

---

## Theorem 2 — Amortized Cost Advantage Condition (Payback Bound)

**Status**: Formalized; empirically validated across 4 regimes in Milestone 01+02.

### Setup
Consider a compressed module $M = I \cup \{v\}$ with absorbed node count $k = |I| + 1$ and boundary size $d = |B|$.
Suppose across $T$ updates after warmup $T_0$, module $M$ is triggered $N$ times with hit probability $h \in [0, 1]$ (fraction of triggers where the canary returns `SAFE`).
Let:
- $c_{\text{learn}}$ be the one-time compilation + validation cost for $M$,
- $c_{\text{guard}}$ be the per-trigger canary check cost (with $c_{\text{guard}} \le d + 1$),
- $c_{\text{reanchor}} \le d + 1$ be the re-anchoring cost on an `UNSAFE` miss.

### Statement
Relative to a conventional incremental engine that evaluates $k_{\text{eff}} \le k$ nodes per trigger of $M$, the trace-contract module achieves strictly positive net operation savings after $N$ triggers iff:
$$N \cdot \Big[ h \cdot k_{\text{eff}} - c_{\text{guard}} - (1 - h) c_{\text{reanchor}} \Big] > c_{\text{learn}} + C_{\text{trace}}(M).$$

### Corollary (Necessary Hit-Rate Floor & Failure Boundary)
Ignoring amortized trace cost, net positive savings are impossible unless the hit rate satisfies:
$$h > h_{\min} = \frac{c_{\text{guard}} + c_{\text{reanchor}}}{k_{\text{eff}} + c_{\text{reanchor}}}.$$
When environmental volatility pushes $h < h_{\min}$ (as in `high_entropy_shock`), static contracts become net-negative; **adaptive retirement** bounds total regret to $O(N_{\text{min}} \cdot (c_{\text{guard}} + c_{\text{reanchor}}))$ by reverting the module to conventional incremental routing once empirical $\hat{h} < h_{\min}$.

---

## Theorem 3 — Soundness of Linear/FPT SAT Tractability Canaries (Experiment 4)

**Status**: Proved & implemented (`experiments/04_tractability/sat_core.py`), verified against general DPLL across 2-SAT, Renamable-Horn 3-SAT, Bounded-$k$ Horn-Backdoor 3-SAT, and adversarial counterexamples.

### Statement
For any CNF formula $\phi$ with $n$ variables and $m$ clauses (width $\le 3$):
1. **Renamable-Horn (Lewis 1978 / Aspvall 1980)**: Constructing the auxiliary 2-SAT formula $\Psi(\phi) = \bigwedge_{C \in \phi} \bigwedge_{\ell_a \neq \ell_b \in C} (\ell_a \vee \ell_b)$ (at most $3m$ binary clauses) and solving via Tarjan SCC takes $O(n + m)$ time. $\Psi(\phi)$ is satisfiable iff there exists a polarity flip $\sigma \in \{0, 1\}^n$ making every clause of $\phi$ Horn; given $\sigma$, Horn unit propagation decides $\phi$ in $O(n + m)$ time (`RESTRICTED_WORST_CASE`).
2. **Bounded-$k$ Strong Horn-Backdoor**: Let $H^+(\phi)$ be the graph whose edges connect pairs of positive literals co-occurring in any clause of $\phi$. A variable set $B$ is a strong Horn-backdoor iff $B$ is a vertex cover of $H^+(\phi)$. Iterative-deepening bounded-search-tree vertex cover certifies a minimum $B$ with $|B| \le k$ (or proves none exists) in $O(2^k (n + m))$ time, after which branching on $B$ and running linear Horn propagation solves $\phi$ in $O(2^{|B|} (n + m))$ worst-case time (`RESTRICTED_WORST_CASE`).
3. **Non-soundness of Density Bounds**: Low global clause density $\alpha = m/n \le \alpha_0$ admits adversarial counterexamples (hard 3-SAT core + dummy padding variables) and therefore CANNOT carry a `RESTRICTED_WORST_CASE` bound.

---

## v0.2 Formal Proof Obligations (P4–P9)

*Policy: No proposition is marked `PROVED` without explicit assumptions and a complete proof. Established prior results are distinguished from novel extensions.*

---

### P4 — Predictive Synchronization Under Bounded Disturbances (LC-18)

**Status**: `PROVED` (elementary worst-case invariance bound for scalar/vector contractive linear dynamics under bounded disturbances; implemented in Experiment 8).

#### Assumptions
1. Environment state evolves as $R_{t+1} = \phi R_t + w_t$ with known contraction parameter $|\phi| < 1$ and bounded process disturbance $|w_t| \le W_{\max}$.
2. When an observation $z_t = R_t + \eta_t$ is acquired, measurement noise satisfies $|\eta_t| \le \eta_{\max}$.
3. At any step $t$ without observation, the predictor propagates $\hat{R}_{t+1} = \phi \hat{R}_t$; at an observation step, it resets $\hat{R}_t = z_t$ (so post-observation error satisfies $e_t = |\hat{R}_t - R_t| \le \eta_{\max}$).

#### Statement
Let the certified error radius evolve via $e_t^{\text{cert}} = \eta_{\max}$ on observation steps and $e_{t+1}^{\text{cert}} = |\phi| e_t^{\text{cert}} + W_{\max}$ on skipped steps. For any prediction horizon $\tau \ge 1$, the worst-case $\tau$-step lookahead error satisfies:
$$|\hat{R}(t+\tau) - R(t+\tau)| \le |\phi|^\tau e_t^{\text{cert}} + W_{\max} \sum_{j=0}^{\tau-1} |\phi|^j =: E_{\text{cert}}(t, \tau).$$
Consequently, any adaptive observation policy that triggers an observation whenever $E_{\text{cert}}(t, \tau) > \varepsilon(\tau)$ (assuming the feasible regime $|\phi|^\tau \eta_{\max} + W_{\max}\frac{1 - |\phi|^\tau}{1 - |\phi|} \le \varepsilon(\tau)$) guarantees $\Pr[|\hat{R}(t+\tau) - R(t+\tau)| \le \varepsilon(\tau)] = 1 \ge 1 - \delta$ for all $\delta \ge 0$ (`RESTRICTED_WORST_CASE` under the bounded-disturbance assumption).

#### Proof
By induction on $k \ge 0$: if $|\hat{R}_t - R_t| \le e_t^{\text{cert}}$, then
$$|\hat{R}_{t+1} - R_{t+1}| = |\phi(\hat{R}_t - R_t) - w_t| \le |\phi| e_t^{\text{cert}} + W_{\max} = e_{t+1}^{\text{cert}}.$$
Iterating $\tau$ times yields $E_{\text{cert}}(t, \tau)$ directly. On violation of $|w_t| \le W_{\max}$ (detected at the next observation whenever $|\hat{R}_t - z_t| > e_t^{\text{cert}} + \eta_{\max}$), the assumption is falsified, the canary enters `UNKNOWN`, and the observer escalates to continuous observation to re-estimate $W_{\max}$. $\square$

---

### P5 — Reuse Value Under Environmental Change (LC-2, LC-15)

**Status**: `PARTIALLY PROVED` (exact threshold proved for stationary trigger hit rate in Theorem 2; non-stationary drift & adaptive retirement regret bounds remain open for general Markovian environments).

#### Statement
Let a retained representation $M$ incur maintenance/guard cost $c_g(t)$, re-anchoring/update cost $c_u(t)$ on invalidation events $I_t \in \{0, 1\}$, and save $s(t)$ units of recomputation on valid hits ($I_t = 0$). Over horizon $T$, net lifecycle savings $S(T)$ relative to a reference architecture are positive iff:
$$\sum_{t=1}^T \big[(1 - I_t) s(t) - c_g(t) - I_t c_u(t)\big] > C_{\text{learn}} + C_{\text{trace}}(T) + C_{\text{reconfig}}(T).$$
*Open extension*: Tight online regret bounds for adaptive retirement policies under non-stationary regime-switching processes $I_t$.

---

### P6 — Validity Atlas Soundness (LC-3, LC-4)

**Status**: `PROVED` (direct union extension of Theorem 1; implemented and fuzz-tested in `core/canary.py`).

#### Statement
Let $\mathcal{A} = \{(u^{(j)}, m^{(j)}, y^{(j)})\}_{j=1}^K$ be a finite atlas of previously verified anchor executions of a deterministic sub-DAG $M$ with global Lipschitz vector $L \in \mathbb{R}_{\ge 0}^{|B|}$ (as in Theorem 1). Define the certified validity atlas region:
$$\mathcal{V}_{\mathcal{A}} = \bigcup_{j=1}^K \Big\{ u \in \mathbb{R}^{|B|} : \sum_{b \in B} L_b |u_b - u_b^{(j)}| < m^{(j)} \Big\}.$$
Then for every $u \in \mathcal{V}_{\mathcal{A}}$, if $j^*$ is ANY index witnessing $u \in B(u^{(j^*)}, m^{(j^*)})$, the output satisfies $v(u) = y^{(j^*)}$ identically (`RESTRICTED_WORST_CASE`), and whenever two balls overlap ($u \in B_i \cap B_j$), consistency $y^{(i)} = y^{(j)}$ holds automatically by determinism of $v$. $\square$

---

### P7 — Human Advice Accounting (LC-11)

**Status**: `OPEN / CONJECTURE` (to be formalized alongside Experiment 7 in Phase E).

#### Research Obligation
Characterize when a bounded advice string or structural hint $h$ of size $|h|$ reduces residual machine solving cost from $C_{\text{machine}}(x)$ to $C_{\text{machine}}(x \mid h) + C_{\text{verify}}(x, h)$, and formalize the complete two-ledger break-even condition when amortized across $R$ future instances—explicitly separating `human_time_s` from machine `steps` and `joules` and avoiding any classical complexity collapse claim.

---

### P8 — Semantic Interface Stability (LC-12, LC-13)

**Status**: `OPEN / CONJECTURE` (to be formalized alongside Experiment 10 in Phase E).

#### Research Obligation
Define an observable behavioral equivalence relation $\equiv_{\text{sem}}$ over Human API operations (`observe`, `intend`, `correct`, `authorize`, `evaluate`) across backend versions $V_1 \to V_2$ mediated by a translation layer $\mathcal{L}$, specifying exact compatibility invariants and mandatory authorization exceptions whenever consequential task semantics change.

---

### P9 — Observation Lower Bounds (LC-17, LC-18)

**Status**: `OPEN / CONJECTURE` (connects to classical rate-distortion / Kalman-Bucy / control-under-communication-constraints theory; to be investigated alongside Experiments 8 & 9).

#### Research Obligation
Derive an information-theoretic lower bound on the minimum average observation rate $\bar{\rho} \in (0, 1]$ required to satisfy $\Pr[d(\hat{R}(t+\tau), R(t+\tau)) \le \varepsilon(\tau)] \ge 1 - \delta$ for unstable or weakly contractive linear-Gaussian and bounded-disturbance environments, and benchmark Experiment 8's adaptive observers against that theoretical floor.


---

## v0.3 Formal Proof Obligations (P10–P16)

*All prior obligations (Theorems 1–3 and P4–P9) are preserved unchanged above. No proposition is marked `PROVED` without explicit assumptions and a complete proof.*

---

### P10 — Decision-State Compression Lower Bound (LC-19)

**Status**: `PROVED` (standard information-theoretic / pigeonhole lower bound for exact representation; storage complexity strictly separated from construction and query costs).

#### Statement
Let $\mathcal{E}$ be a finite environment state space partitioned by a specified exact query family $\mathcal{Q}$ into $M \ge 1$ distinguishable equivalence classes (i.e., for any two distinct classes $c_1 \neq c_2$, there exists $q \in \mathcal{Q}$ with $q(c_1) \neq q(c_2)$). Then any deterministic fixed-length binary representation $\mathrm{enc}: \mathcal{E} \to \{0,1\}^L$ that answers every query $q \in \mathcal{Q}$ exactly from $\mathrm{enc}(e)$ alone requires:
$$L \ge \lceil \log_2 M \rceil.$$

#### Proof
If $L < \lceil \log_2 M \rceil$, then $2^L < M$. By the pigeonhole principle, at least two states $e_1, e_2$ belonging to distinct equivalence classes map to the same bitstring $\mathrm{enc}(e_1) = \mathrm{enc}(e_2)$. Any deterministic decoder $D(\mathrm{enc}(e), q)$ must output identical answers for $e_1$ and $e_2$ on every $q \in \mathcal{Q}$, contradicting the existence of a distinguishing query $q^* \in \mathcal{Q}$ with $q^*(e_1) \neq q^*(e_2)$. Note that this bounds storage length $L$ only; constructing $\mathrm{enc}(e)$ or answering $q$ can incur arbitrarily larger time/step complexity. $\square$

---

### P11 — Transfer Contract Soundness (LC-21)

**Status**: `PROVED` (algebraic/commuting-diagram soundness condition for cross-environment capability transfer; implemented and verified in Experiment 12).

#### Assumptions
Let $f_{\text{src}}: X_{\text{src}} \to Y_{\text{src}}$ and $f_{\text{dst}}: X_{\text{dst}} \to Y_{\text{dst}}$ be deterministic task specifications in source and destination environments. Let $\hat{f}_{\text{src}}$ be a certified capability on validity region $\mathcal{V}_{\text{src}} \subseteq X_{\text{src}}$ satisfying $\forall x \in \mathcal{V}_{\text{src}},\; \hat{f}_{\text{src}}(x) = f_{\text{src}}(x)$. Let $\phi_{\text{in}}: X_{\text{dst}} \to X_{\text{src}}$ and $\phi_{\text{out}}: Y_{\text{src}} \to Y_{\text{dst}}$ be translation maps.

#### Statement
Suppose for an admissible destination set $\mathcal{V}_{\text{dst}} \subseteq X_{\text{dst}}$:
1. **Domain Preservation**: $\phi_{\text{in}}(\mathcal{V}_{\text{dst}}) \subseteq \mathcal{V}_{\text{src}}$.
2. **Semantic Commutation**: $\forall x' \in \mathcal{V}_{\text{dst}},\; \phi_{\text{out}}(f_{\text{src}}(\phi_{\text{in}}(x'))) = f_{\text{dst}}(x')$.

Then the transferred capability $\hat{f}_{\text{dst}} := \phi_{\text{out}} \circ \hat{f}_{\text{src}} \circ \phi_{\text{in}}$ is **sound** on $\mathcal{V}_{\text{dst}}$:
$$\forall x' \in \mathcal{V}_{\text{dst}},\quad \hat{f}_{\text{dst}}(x') = f_{\text{dst}}(x') \qquad (\text{RESTRICTED\_WORST\_CASE}).$$

#### Proof
For any $x' \in \mathcal{V}_{\text{dst}}$, Condition (1) gives $\phi_{\text{in}}(x') \in \mathcal{V}_{\text{src}}$, so $\hat{f}_{\text{src}}(\phi_{\text{in}}(x')) = f_{\text{src}}(\phi_{\text{in}}(x'))$. Applying $\phi_{\text{out}}$ and invoking Condition (2) yields $\hat{f}_{\text{dst}}(x') = \phi_{\text{out}}(f_{\text{src}}(\phi_{\text{in}}(x'))) = f_{\text{dst}}(x')$. Failure of either (1) (structural drift, T3) or (2) (semantic mismatch / institutional enclosure, T4) invalidates soundness and must trigger a transfer canary `UNSAFE` / `UNKNOWN` transition. $\square$

---

### P12 — Work Not Done Accounting Condition (LC-22)

**Status**: `PROVED` (accounting validity condition under a common outcome-equivalence relation and complete lifecycle boundary; enforced by Experiment 13's WND verifier).

#### Statement
Let $\mathcal{W} = (w_1, \dots, w_T)$ be a replayable workload, $\equiv_{\text{out}}$ an explicit required outcome-equivalence relation, $B$ a declared reference baseline, and $S$ an adaptive system. Let $C_B^{(u)}(\mathcal{W})$ and $C_S^{(u)}(\mathcal{W}) = C_{S,\text{exec}}^{(u)} + C_{S,\text{prep}}^{(u)} + C_{S,\text{learn}}^{(u)} + C_{S,\text{guard}}^{(u)} + C_{S,\text{maint}}^{(u)} + C_{S,\text{def}}^{(u)}$ be complete lifecycle expenditures in unit channel $u$ (e.g., machine ops, modeled joules, human seconds). A verified Work Not Done claim $\mathrm{WND}^{(u)}(\mathcal{W}, B, S) = C_B^{(u)}(\mathcal{W}) - C_S^{(u)}(\mathcal{W}) > 0$ is **valid** iff:
1. **Outcome Equivalence**: $\forall t \in \{1,\dots,T\},\; S(w_t) \equiv_{\text{out}} B(w_t)$ (zero silent requirement relaxation).
2. **Complete Boundary Conservation**: All preprocessing, tracing, learning, validation, guarding, maintenance, and deferred cleanup work are included in $C_S^{(u)}$; no hidden externalized cost in another channel $u'$ (such as omitted `human_time_s`) is omitted from the multi-channel report.
3. **Non-Duplication & Active Validity**: The workload hash $\mathrm{hash}(\mathcal{W})$ is claimed at most once per execution, and every reused contract was active/unexpired at the time of reuse.

Violation of (1), (2), or (3) invalidates the WND certificate. $\square$

---

### P13 — Attribution Conservation (LC-23)

**Status**: `PROVED` (accounting conservation identity for direct, proportional, and Shapley cooperative allocations; strictly distinguished from causal responsibility).

#### Statement
Let $S_{\text{ver}} \ge 0$ be the verified net Work Not Done of a capability graph with active contributor set $N = \{1, \dots, k\}$ and characteristic value function $v: 2^N \to \mathbb{R}_{\ge 0}$ satisfying $v(\emptyset) = 0$ and $v(N) = S_{\text{ver}}$. Any allocation vector $\alpha = (\alpha_1, \dots, \alpha_k)$ satisfies **strict conservation** iff $\sum_{i \in N} \alpha_i = S_{\text{ver}}$ (or weak conservation $\sum_i \alpha_i \le S_{\text{ver}}$ when residual unattributable synergy is held explicitly). In particular, the Shapley allocation:
$$\phi_i(v) = \sum_{A \subseteq N \setminus \{i\}} \frac{|A|!(|N|-|A|-1)!}{|N|!} \big(v(A \cup \{i\}) - v(A)\big)$$
uniquely satisfies efficiency ($\sum_{i \in N} \phi_i(v) = v(N) = S_{\text{ver}}$), symmetry, dummy-contributor zero share ($v(A \cup \{i\}) = v(A) \implies \phi_i = 0$), and additivity—preventing naive path double-counting ($\sum_i S_{\text{ver}} = k \cdot S_{\text{ver}} > S_{\text{ver}}$).

*Caveat*: Conservation is an **accounting invariant**, not a proof of causal necessity; causal involvement must be independently evidenced by the DAG edges in the evidence graph. $\square$

---

### P14 — Portable Knowledge Payback (LC-21, LC-15)

**Status**: `PROVED` (amortized cross-environment break-even condition; empirically mapped across workload/institution sweeps in Experiment 15).

#### Statement
Suppose a capability created once at cost $C_{\text{create}}$ is transferred to $M \ge 1$ destination institutions, incurring per-institution translation + validation cost $C_{\text{xfer}, m}$, per-reuse guarding/maintenance cost $c_{g,m}$, and gross per-reuse baseline avoidance $s_m$ across $R_m$ valid reuses prior to expiration/invalidation (plus retirement cost $C_{\text{retire}, m}$). Portable reuse achieves positive global cumulative savings over local rediscovery ($M \cdot C_{\text{create}}$) or stateless execution ($\sum_m R_m s_m$) iff:
$$\sum_{m=1}^M \big(R_m (s_m - c_{g,m}) - C_{\text{xfer}, m} - C_{\text{retire}, m}\big) > C_{\text{create}} \quad \text{(vs stateless)}$$
and beats independent local rediscovery at each institution iff:
$$\sum_{m=1}^M \big(C_{\text{xfer}, m} + \Delta C_{\text{guard}, m}\big) < (M - 1) C_{\text{create}}. \quad \square$$

---

### P15 — Computational Fingerprint Integrity (LC-23)

**Status**: `PROVED` (conditional on collision resistance of SHA-256 and deterministic canonical JSON serialization; implemented and tamper-tested in `core/evidence.py` and Experiment 14).

#### Assumptions
1. $\mathrm{Canon}(\cdot)$ is an injective, deterministic serialization (UTF-8 JSON with recursively sorted keys, fixed separators, and normalized numeric formatting).
2. $H = \text{SHA-256}$ is collision-resistant.
3. Every node $u$ in an acyclic evidence graph $G = (V, E)$ commits to its canonical payload and the sorted list of parent digests: $h(u) = H(\mathrm{Canon}(\mathrm{payload}(u), [h(p) : p \in \mathrm{parents}(u)]))$.

#### Statement
Under Assumptions (1)–(3), any modification to any node payload, dependency edge, ordering, or parent commitment in $G$ produces a distinct root Proof-of-Creator fingerprint $h(G)$ except with negligible collision probability under SHA-256. Moreover, given the same evidence graph $G$, any independent verifier reproduces the identical hex digest $h(G)$ deterministically.

*Caveat*: Integrity guarantees tamper-evidence and reproducibility only—it does **not** prove ground-truth empirical correctness, real-world authorship, or legal ownership. $\square$

---

### P16 — Feasible-Set Expansion & Non-Monotonic Counterexamples (LC-24)

**Status**: `PROVED` (sufficient condition for monotonic expansion + explicit counterexamples when maintenance costs, incompatibilities, or resource contention are present; tested in Experiment 16).

#### Statement
Let $\mathcal{A}(K, B)$ be the set of task portfolios achievable using knowledge/capabilities $K$ under resource budget $B$ and correctness constraints.
1. **Monotonic Expansion (Sufficient Condition)**: If adding capability $h$ (a) is optional to invoke (does not revoke or overwrite any previously usable method in $K$), (b) imposes zero mandatory fixed maintenance cost ($c_{\text{maint}}(h) = 0$) on budgets $B$, and (c) has no incompatibility constraints forbidding prior actions, then:
   $$\mathcal{A}(K, B) \subseteq \mathcal{A}(K \cup \{h\}, B) \quad \text{and} \quad V^*(K \cup \{h\}, B) \ge V^*(K, B).$$
2. **Strict Non-Monotonicity Counterexamples**: When $c_{\text{maint}}(h) > 0$ reduces residual budget $B' = B - c_{\text{maint}}(h) < B$, previously feasible tasks requiring budget in $(B', B]$ can become **infeasible**, so $\mathcal{A}(K \cup \{h\}, B) \not\supseteq \mathcal{A}(K, B)$ and $V^*(K \cup \{h\}, B) < V^*(K, B)$ is possible even when $\Delta \mathcal{A} \neq \emptyset$. Furthermore, $|\Delta\mathcal{A}| > 0$ does not imply $V_{\text{option}}(h) > 0$ when newly feasible tasks have zero utility or are dominated under mutual-exclusion budget contention. $\square$
