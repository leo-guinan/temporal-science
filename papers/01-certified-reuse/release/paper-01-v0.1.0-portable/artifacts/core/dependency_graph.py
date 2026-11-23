"""Computational dependency DAG, exact deterministic evaluation, and sensitivity analysis.

Supports building 1,000+ node layered computational graphs with deterministic semantics,
NetworkX graph export/analytics, causal ancestry queries, and mathematically sound
Lipschitz sensitivity propagation used by the Trace-to-Contract Compiler.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple
import math
import random

import networkx as nx


class OpType(str, Enum):
    INPUT = "input"
    LINEAR = "linear"
    SUM = "sum"
    MEAN = "mean"
    SCALE = "scale"
    ABS_DIFF = "abs_diff"
    RELU = "relu"
    CLAMP = "clamp"
    THRESHOLD = "threshold"
    MAX = "max"
    MIN = "min"


# Operators that are globally Lipschitz-continuous everywhere on R^k
LIPSCHITZ_CONTINUOUS_OPS: Set[OpType] = {
    OpType.INPUT,
    OpType.LINEAR,
    OpType.SUM,
    OpType.MEAN,
    OpType.SCALE,
    OpType.ABS_DIFF,
    OpType.RELU,
    OpType.CLAMP,
    OpType.MAX,
    OpType.MIN,
}

# Operators that possess flat / invariant validity regions (constant output over an open set)
SATURATING_OR_DISCRETE_OPS: Set[OpType] = {
    OpType.THRESHOLD,
    OpType.CLAMP,
    OpType.RELU,
}


@dataclass
class Node:
    """A single deterministic computational unit in a DependencyGraph."""

    node_id: int
    name: str
    op: OpType
    parents: Tuple[int, ...] = ()
    params: Dict[str, Any] = field(default_factory=dict)
    children: List[int] = field(default_factory=list)
    # Optional metadata for ground-truth analysis ONLY (never read by learners/compilers)
    ground_truth_group: Optional[str] = None

    def evaluate(self, values: Sequence[float]) -> float:
        """Evaluate this node given the current array of node values."""
        op = self.op
        p = self.parents
        if op is OpType.INPUT:
            return values[self.node_id]
        if op is OpType.LINEAR:
            weights: Tuple[float, ...] = self.params["weights"]
            acc = float(self.params.get("bias", 0.0))
            for pid, w in zip(p, weights):
                acc += w * values[pid]
            return acc
        if op is OpType.SUM:
            acc = 0.0
            for pid in p:
                acc += values[pid]
            return acc
        if op is OpType.MEAN:
            if not p:
                return 0.0
            acc = 0.0
            for pid in p:
                acc += values[pid]
            return acc / len(p)
        if op is OpType.SCALE:
            return self.params["scale"] * values[p[0]] + self.params.get("bias", 0.0)
        if op is OpType.ABS_DIFF:
            return abs(values[p[0]] - values[p[1]])
        if op is OpType.RELU:
            x = values[p[0]] - self.params.get("threshold", 0.0)
            return x if x > 0.0 else 0.0
        if op is OpType.CLAMP:
            x = values[p[0]]
            lo = self.params["lo"]
            hi = self.params["hi"]
            if x < lo:
                return lo
            if x > hi:
                return hi
            return x
        if op is OpType.THRESHOLD:
            x = values[p[0]]
            return 1.0 if x >= self.params["threshold"] else 0.0
        if op is OpType.MAX:
            return max(values[pid] for pid in p)
        if op is OpType.MIN:
            return min(values[pid] for pid in p)
        raise ValueError(f"Unsupported op: {op}")

    def parent_lipschitz_bounds(self) -> Optional[Tuple[float, ...]]:
        """Return exact global partial Lipschitz upper bounds wrt each parent, or None if discontinuous."""
        op = self.op
        if op is OpType.INPUT:
            return ()
        if op is OpType.LINEAR:
            return tuple(abs(float(w)) for w in self.params["weights"])
        if op is OpType.SUM:
            return tuple(1.0 for _ in self.parents)
        if op is OpType.MEAN:
            inv = 1.0 / len(self.parents) if self.parents else 0.0
            return tuple(inv for _ in self.parents)
        if op is OpType.SCALE:
            return (abs(float(self.params["scale"])),)
        if op is OpType.ABS_DIFF:
            return (1.0, 1.0)
        if op in (OpType.RELU, OpType.CLAMP):
            return (1.0,)
        if op in (OpType.MAX, OpType.MIN):
            return tuple(1.0 for _ in self.parents)
        return None


class DependencyGraph:
    """Directed acyclic graph of computational nodes in strict topological order (0..N-1)."""

    def __init__(self, name: str = "computation_dag") -> None:
        self.name = name
        self.nodes: List[Node] = []
        self.input_ids: List[int] = []
        self.output_id: int = -1

    def __len__(self) -> int:
        return len(self.nodes)

    def add_node(
        self,
        name: str,
        op: OpType,
        parents: Sequence[int] = (),
        params: Optional[Dict[str, Any]] = None,
        ground_truth_group: Optional[str] = None,
    ) -> int:
        node_id = len(self.nodes)
        parent_tuple = tuple(parents)
        for pid in parent_tuple:
            if pid < 0 or pid >= node_id:
                raise ValueError(
                    f"Graph must remain topologically ordered: parent {pid} >= node {node_id}"
                )
        node = Node(
            node_id=node_id,
            name=name,
            op=op,
            parents=parent_tuple,
            params=dict(params) if params else {},
            ground_truth_group=ground_truth_group,
        )
        self.nodes.append(node)
        for pid in parent_tuple:
            self.nodes[pid].children.append(node_id)
        if op is OpType.INPUT:
            self.input_ids.append(node_id)
        self.output_id = node_id
        return node_id

    def evaluate_full(self, input_values: Dict[int, float]) -> List[float]:
        """Reference full evaluation over all nodes in topological order."""
        vals = [0.0] * len(self.nodes)
        for nid in self.input_ids:
            vals[nid] = float(input_values[nid])
        for node in self.nodes:
            if node.op is not OpType.INPUT:
                vals[node.node_id] = node.evaluate(vals)
        return vals

    def to_networkx(self) -> nx.DiGraph:
        """Export to a NetworkX DiGraph for structural analysis and visualization."""
        g = nx.DiGraph(name=self.name)
        for node in self.nodes:
            g.add_node(node.node_id, name=node.name, op=node.op.value)
            for pid in node.parents:
                g.add_edge(pid, node.node_id)
        return g

    def graph_stats(self) -> Dict[str, Any]:
        g = self.to_networkx()
        in_degrees = [d for _, d in g.in_degree()]
        out_degrees = [d for _, d in g.out_degree()]
        return {
            "name": self.name,
            "num_nodes": len(self.nodes),
            "num_edges": g.number_of_edges(),
            "num_inputs": len(self.input_ids),
            "output_id": self.output_id,
            "dag_depth": nx.dag_longest_path_length(g),
            "mean_in_degree": round(sum(in_degrees) / len(in_degrees), 3),
            "mean_out_degree": round(sum(out_degrees) / len(out_degrees), 3),
            "max_out_degree": max(out_degrees),
            "is_dag": nx.is_directed_acyclic_graph(g),
        }

    def ancestors(self, node_id: int, max_depth: Optional[int] = None) -> Set[int]:
        """Return ancestors of node_id up to optional hop depth."""
        visited: Set[int] = set()
        frontier: List[Tuple[int, int]] = [(node_id, 0)]
        while frontier:
            cur, depth = frontier.pop()
            if max_depth is not None and depth >= max_depth:
                continue
            for pid in self.nodes[cur].parents:
                if pid not in visited:
                    visited.add(pid)
                    frontier.append((pid, depth + 1))
        return visited

    def descendants(self, node_id: int) -> Set[int]:
        """Return all downstream descendants of node_id."""
        visited: Set[int] = set()
        stack = list(self.nodes[node_id].children)
        while stack:
            cur = stack.pop()
            if cur not in visited:
                visited.add(cur)
                stack.extend(self.nodes[cur].children)
        return visited

    def extract_lipschitz_cone(
        self, target_node_id: int, max_internal_nodes: int = 64
    ) -> Optional[Tuple[Tuple[int, ...], Tuple[int, ...], Dict[int, float], int]]:
        """Extract a maximal continuous Lipschitz cone feeding a saturating/discrete target node.

        Given a target node v (THRESHOLD, CLAMP, or RELU) with single parent p:
        Walks backward from p through continuous operators whose outputs do NOT escape
        outside the cone (exclusive internal sub-DAG, so skipping internal nodes cannot
        leave any external consumer stale!).

        Returns:
            (boundary_ids, internal_ids_sorted, lipschitz_by_boundary, analysis_ops)
            or None if no nontrivial cone (>= 2 internal nodes) exists.
        """
        target = self.nodes[target_node_id]
        if target.op not in SATURATING_OR_DISCRETE_OPS or len(target.parents) != 1:
            return None

        pre_id = target.parents[0]
        analysis_ops = 1

        # Step 1: Collect candidate continuous ancestors of pre_id (exclusive ownership check)
        # A node u can be absorbed as an *internal* node of this compressed module if:
        #   - u is continuous (has exact global Lipschitz bounds), AND
        #   - u is not an INPUT node, AND
        #   - every child of u is already inside the cone (or is target_node_id).
        # Because nodes are topologically ordered, scanning backward from pre_id in reverse
        # topological order guarantees all children of u are processed before u!
        cone_members: Set[int] = {target_node_id}
        internal: Set[int] = set()
        queue: List[int] = [pre_id]
        seen: Set[int] = {pre_id}

        # Collect reachable ancestors up to a limit first, then prune in reverse topo order
        reachable: List[int] = []
        while queue and len(reachable) < max_internal_nodes * 2:
            curr = queue.pop()
            analysis_ops += 1
            node = self.nodes[curr]
            if node.op is OpType.INPUT or node.op not in LIPSCHITZ_CONTINUOUS_OPS:
                continue
            reachable.append(curr)
            for pid in node.parents:
                if pid not in seen:
                    seen.add(pid)
                    queue.append(pid)

        reachable.sort(reverse=True)
        for nid in reachable:
            analysis_ops += 1
            node = self.nodes[nid]
            # Exclusive ownership: all children must be inside cone_members
            if all(c in cone_members for c in node.children):
                internal.add(nid)
                cone_members.add(nid)
                if len(internal) >= max_internal_nodes:
                    break

        if len(internal) < 2 or pre_id not in internal:
            return None

        # Boundary consists of all parents of internal nodes that are outside `internal`
        boundary_set: Set[int] = set()
        for nid in internal:
            for pid in self.nodes[nid].parents:
                if pid not in internal:
                    boundary_set.add(pid)

        if not boundary_set:
            return None

        boundary_ids = tuple(sorted(boundary_set))
        internal_sorted = tuple(sorted(internal))

        # Step 2: Exact forward sensitivity propagation through `internal_sorted`
        # sens[nid][b] = upper bound on |d(val[nid]) / d(val[b])| across all R^|B|
        sens: Dict[int, Dict[int, float]] = {b: {b: 1.0} for b in boundary_ids}
        for nid in internal_sorted:
            node = self.nodes[nid]
            p_lips = node.parent_lipschitz_bounds()
            if p_lips is None:
                return None
            acc: Dict[int, float] = {}
            for pid, lip in zip(node.parents, p_lips):
                analysis_ops += 1
                if lip == 0.0:
                    continue
                for b_id, b_sens in sens[pid].items():
                    acc[b_id] = acc.get(b_id, 0.0) + lip * b_sens
            sens[nid] = acc

        pre_sens = sens[pre_id]
        lipschitz_by_boundary = {b: pre_sens.get(b, 0.0) for b in boundary_ids}
        return boundary_ids, internal_sorted, lipschitz_by_boundary, analysis_ops


def build_milestone_network(
    num_nodes: int = 1000,
    num_inputs: int = 120,
    seed: int = 42,
) -> DependencyGraph:
    """Build the deterministic 1,000-node computational DAG for the First Experimental Milestone.

    Architecture:
      - `num_inputs` environmental sensor inputs (default 120)
      - Multiple multi-stage processing subsystems (~22-25 nodes each), mixing:
          * linear feature projections, weighted averages, pairwise differences
          * intermediate nonlinearities (ReLU, max/min)
          * regime/safety/saturation decision gates (THRESHOLD, CLAMP, RELU)
        Each subsystem has localized sensor dependencies (some shared across neighboring
        subsystems to model realistic coupling).
      - A hierarchical aggregation tree combining all subsystem outputs into a single
        deterministic scalar root output.
      - Node count matches `num_nodes` exactly (default 1,000).
    """
    rng = random.Random(seed)
    g = DependencyGraph(name=f"living_milestone_dag_{num_nodes}n_s{seed}")

    # 1. Input layer
    inputs: List[int] = []
    for i in range(num_inputs):
        inputs.append(g.add_node(f"in_{i:03d}", OpType.INPUT, ground_truth_group="inputs"))

    # Reserve ~10% of remaining nodes for the top hierarchical aggregation tree
    remaining = num_nodes - num_inputs
    # Choose number of subsystems so each has ~21 nodes and leaves enough for aggregation
    target_sub_size = 22
    num_subsystems = max(4, (remaining - 60) // target_sub_size)
    # Build subsystems, leaving remaining budget for hierarchical aggregator
    subsystem_outputs: List[int] = []

    for s in range(num_subsystems):
        grp = f"sub_{s:02d}"
        # Each subsystem reads 4-5 inputs (contiguous local neighborhood + 1 shared coupling input)
        base = (s * 3) % num_inputs
        sub_inputs = [inputs[(base + k) % num_inputs] for k in range(4)]
        # Add slight coupling to another sensor for 1/3 of subsystems
        if s % 3 == 0:
            sub_inputs.append(inputs[(base + 17) % num_inputs])

        # Stage 1: 6 linear/scale feature extractors (6 nodes)
        stage1: List[int] = []
        for j in range(6):
            chosen = rng.sample(sub_inputs, k=min(3, len(sub_inputs)))
            raw_w = [rng.uniform(-0.8, 0.8) for _ in chosen]
            norm = sum(abs(w) for w in raw_w) or 1.0
            weights = tuple(round(w / norm, 4) for w in raw_w)
            bias = round(rng.uniform(-0.15, 0.15), 4)
            nid = g.add_node(
                f"{grp}_f1_{j}",
                OpType.LINEAR,
                parents=chosen,
                params={"weights": weights, "bias": bias},
                ground_truth_group=grp,
            )
            stage1.append(nid)

        # Stage 2: 5 derived feature nodes (ABS_DIFF, MEAN, SCALE, LINEAR) (5 nodes)
        stage2: List[int] = []
        stage2.append(
            g.add_node(
                f"{grp}_diff_0",
                OpType.ABS_DIFF,
                parents=(stage1[0], stage1[1]),
                ground_truth_group=grp,
            )
        )
        stage2.append(
            g.add_node(
                f"{grp}_diff_1",
                OpType.ABS_DIFF,
                parents=(stage1[2], stage1[3]),
                ground_truth_group=grp,
            )
        )
        stage2.append(
            g.add_node(
                f"{grp}_mean_0",
                OpType.MEAN,
                parents=(stage1[0], stage1[2], stage1[4]),
                ground_truth_group=grp,
            )
        )
        stage2.append(
            g.add_node(
                f"{grp}_mean_1",
                OpType.MEAN,
                parents=(stage1[1], stage1[3], stage1[5]),
                ground_truth_group=grp,
            )
        )
        stage2.append(
            g.add_node(
                f"{grp}_scale_0",
                OpType.SCALE,
                parents=(stage1[4],),
                params={"scale": round(rng.uniform(0.5, 1.2), 4), "bias": 0.05},
                ground_truth_group=grp,
            )
        )

        # Stage 3: 5 nonlinear/combining nodes (5 nodes)
        stage3: List[int] = []
        stage3.append(
            g.add_node(
                f"{grp}_max_0",
                OpType.MAX,
                parents=(stage2[0], stage2[1]),
                ground_truth_group=grp,
            )
        )
        stage3.append(
            g.add_node(
                f"{grp}_min_0",
                OpType.MIN,
                parents=(stage2[2], stage2[3]),
                ground_truth_group=grp,
            )
        )
        for j in range(3):
            p_sel = [stage2[j], stage2[(j + 1) % len(stage2)], stage2[(j + 2) % len(stage2)]]
            raw_w = [rng.uniform(-0.7, 0.7) for _ in p_sel]
            norm = sum(abs(w) for w in raw_w) or 1.0
            weights = tuple(round(w / norm, 4) for w in raw_w)
            stage3.append(
                g.add_node(
                    f"{grp}_mix_{j}",
                    OpType.LINEAR,
                    parents=p_sel,
                    params={"weights": weights, "bias": round(rng.uniform(-0.1, 0.1), 4)},
                    ground_truth_group=grp,
                )
            )

        # Stage 4: 4 pre-decision consolidation nodes (4 nodes)
        c0 = g.add_node(
            f"{grp}_cons_0",
            OpType.SUM,
            parents=(stage3[0], stage3[2]),
            ground_truth_group=grp,
        )
        c1 = g.add_node(
            f"{grp}_cons_1",
            OpType.MEAN,
            parents=(stage3[1], stage3[3], stage3[4]),
            ground_truth_group=grp,
        )
        c2 = g.add_node(
            f"{grp}_cons_2",
            OpType.ABS_DIFF,
            parents=(c0, c1),
            ground_truth_group=grp,
        )
        pre = g.add_node(
            f"{grp}_pre_decision",
            OpType.LINEAR,
            parents=(c0, c1, c2),
            params={"weights": (0.4, 0.35, 0.25), "bias": 0.0},
            ground_truth_group=grp,
        )

        # Stage 5: Subsystem output gate / regime detector (1 node -> 21 nodes per subsystem)
        # Mix of THRESHOLD (regime detector), CLAMP (saturated sensor), and RELU (activation alarm)
        # plus ~15% continuous pass-through subsystems so not every subsystem is contractible!
        mode = s % 6
        if mode in (0, 1, 2):
            # Threshold gate with nontrivial margin under nominal operating range
            thresh = round(rng.uniform(0.55, 0.85), 4)
            out_nid = g.add_node(
                f"{grp}_gate_thresh",
                OpType.THRESHOLD,
                parents=(pre,),
                params={"threshold": thresh},
                ground_truth_group=grp,
            )
        elif mode == 3:
            # Clamp with saturation bounds
            out_nid = g.add_node(
                f"{grp}_gate_clamp",
                OpType.CLAMP,
                parents=(pre,),
                params={"lo": -0.25, "hi": 0.35},
                ground_truth_group=grp,
            )
        elif mode == 4:
            # ReLU alarm activating only above threshold
            out_nid = g.add_node(
                f"{grp}_gate_relu",
                OpType.RELU,
                parents=(pre,),
                params={"threshold": round(rng.uniform(0.45, 0.70), 4)},
                ground_truth_group=grp,
            )
        else:
            # Pure continuous subsystem (tests that compiler does NOT falsely contract it)
            out_nid = g.add_node(
                f"{grp}_cont_out",
                OpType.SCALE,
                parents=(pre,),
                params={"scale": 0.5, "bias": 0.0},
                ground_truth_group=grp,
            )

        subsystem_outputs.append(out_nid)

    # 3. Hierarchical aggregation tree + exact padding to reach `num_nodes`
    # First, create an intermediate monitoring/feature layer over subsystem outputs
    # so we hit exactly `num_nodes` with meaningful, connected computation.
    current_layer = list(subsystem_outputs)

    # Calculate how many nodes are needed to reduce `current_layer` to 1 root with fan-in 2..3
    def min_tree_nodes(width: int) -> int:
        # binary tree reduction takes width - 1 nodes
        return max(1, width - 1)

    # Add enrichment/cross-subsystem aggregation layers while we have spare budget
    layer_idx = 0
    while len(g) + min_tree_nodes(len(current_layer)) < num_nodes:
        spare = num_nodes - len(g) - min_tree_nodes(len(current_layer))
        if spare <= 0:
            break
        # Add a pair-combining node over two existing current_layer nodes and replace or append
        if spare >= len(current_layer) and layer_idx < 3:
            next_layer: List[int] = []
            for i in range(len(current_layer)):
                p0 = current_layer[i]
                p1 = current_layer[(i + 1) % len(current_layer)]
                nid = g.add_node(
                    f"agg_l{layer_idx}_{i:02d}",
                    OpType.LINEAR,
                    parents=(p0, p1),
                    params={"weights": (0.6, 0.4), "bias": 0.0},
                    ground_truth_group="aggregator",
                )
                next_layer.append(nid)
            current_layer = next_layer
            layer_idx += 1
        else:
            # Consume remaining spare nodes one-by-one by chaining a scale/mean node
            idx = len(g) % len(current_layer)
            p0 = current_layer[idx]
            p1 = current_layer[(idx + 1) % len(current_layer)]
            nid = g.add_node(
                f"agg_pad_{len(g)}",
                OpType.MEAN,
                parents=(p0, p1),
                ground_truth_group="aggregator",
            )
            current_layer[idx] = nid

    # Final binary/ternary reduction to exact root node
    red_idx = 0
    while len(current_layer) > 1:
        next_layer = []
        i = 0
        while i < len(current_layer):
            if i + 1 < len(current_layer):
                # Check if we need fan-in 3 to land on exact num_nodes
                remaining_after_pair = len(current_layer) - 1
                nodes_left_budget = num_nodes - len(g)
                if (
                    i + 2 < len(current_layer)
                    and nodes_left_budget < remaining_after_pair
                ):
                    nid = g.add_node(
                        f"root_red_{red_idx}",
                        OpType.MEAN,
                        parents=(current_layer[i], current_layer[i + 1], current_layer[i + 2]),
                        ground_truth_group="aggregator",
                    )
                    next_layer.append(nid)
                    i += 3
                else:
                    nid = g.add_node(
                        f"root_red_{red_idx}",
                        OpType.MEAN,
                        parents=(current_layer[i], current_layer[i + 1]),
                        ground_truth_group="aggregator",
                    )
                    next_layer.append(nid)
                    i += 2
                red_idx += 1
            else:
                next_layer.append(current_layer[i])
                i += 1
        current_layer = next_layer

    # If still 1+ nodes short (edge case), wrap final output in identity scale
    while len(g) < num_nodes:
        prev = current_layer[0]
        prev = g.add_node(
            f"root_final_{len(g)}",
            OpType.SCALE,
            parents=(prev,),
            params={"scale": 1.0, "bias": 0.0},
            ground_truth_group="aggregator",
        )
        current_layer = [prev]

    g.output_id = current_layer[0]
    assert len(g) == num_nodes, f"Expected {num_nodes} nodes, built {len(g)}"
    return g
