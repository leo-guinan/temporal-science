# Proof of TS-001 (Theorem 1 — Lipschitz-Margin Validity Region Soundness)

## Setup
Let $G = (V, E)$ be a deterministic computational DAG in strict topological order ($p < u$ for every edge $(p, u) \in E$). Let $v \in V$ have single parent $p$ and operator $f_v \in \{\mathrm{THRESHOLD}_\theta, \mathrm{RELU}_\theta, \mathrm{CLAMP}_{[lo, hi]}\}$. Let $I \subset V$ be an exclusive internal cone with boundary $B \subset V \setminus (I \cup \{v\})$ such that:
1. $p \in I$, and every parent of every $u \in I$ lies in $I \cup B$.
2. Every child of every $u \in I$ lies in $I \cup \{v\}$ (no external consumer reads any node in $I$).
3. Every $u \in I$ implements a globally Lipschitz-continuous operator with exact partial Lipschitz upper bounds $\ell_{u,q} \ge 0$ satisfying $|f_u(x) - f_u(x')| \le \sum_{q \in \mathrm{parents}(u)} \ell_{u,q}|x_q - x'_q|$.

Define $L_{b \to b} = 1$ for $b \in B$ and, inductively in topological order on $I$:
$$L_{b \to u} = \sum_{q \in \mathrm{parents}(u)} \ell_{u,q} L_{b \to q}.$$

## Proof
1. **Induction on topological order of $I$**: Base case $u = b \in B$ holds trivially since $|x_b - x'_b| = 1 \cdot |x_b - x'_b|$. For any $u \in I$, assuming the bound holds for all parents $q \in \mathrm{parents}(u)$:
   $$|f_u(x) - f_u(x')| \le \sum_{q \in \mathrm{parents}(u)} \ell_{u,q} |x_q - x'_q| \le \sum_{q} \ell_{u,q} \sum_{b \in B} L_{b \to q} |u_b - u^{(0)}_b| = \sum_{b \in B} L_{b \to u} |u_b - u^{(0)}_b|.$$
   In particular, for $u = p$: $|p(u) - p(u^{(0)})| \le \sum_{b \in B} L_{b \to p} |u_b - u^{(0)}_b|$.
2. **Invariance at $v$**: By definition of saturation margin $m(p^{(0)})$, every value $z$ with $|z - p^{(0)}| < m(p^{(0)})$ lies strictly in the same constant flat region of $f_v$ as $p^{(0)}$. Hence $\sum_{b \in B} L_{b \to p}|u_b - u^{(0)}_b| < m(p^{(0)})$ implies $f_v(p(u)) = f_v(p(u^{(0)}))$.
3. **Observational equivalence on $G$**: Since no node in $V \setminus (I \cup \{v\})$ reads any node in $I$, skipping evaluation of $I \cup \{v\}$ preserves exact values for all external nodes in $G$. When the canary later fires `UNSAFE`, evaluating all $u \in I$ in topological order from current boundary values $B$ refreshes every internal state before evaluating $v$. $\square$

## Implementation & Numerical Caveat
`LipschitzMarginCanary` in `../living-computation/core/canary.py` adds an IEEE-754 safety margin $\epsilon_{\text{fp}} = 10^{-9}(1 + |p^{(0)}| + \sum_b L_b |u^{(0)}_b|)$ to prevent boundary rounding flips.
