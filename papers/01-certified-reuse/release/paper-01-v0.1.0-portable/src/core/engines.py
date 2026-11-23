"""Benchmark execution engines for Experiments 1 & 2.

Implements four comparable systems running on identical deterministic workloads:
  1. FullRecomputeEngine: full topological recomputation on every update (Baseline A)
  2. ConventionalIncrementalEngine: optimal topological priority-queue incremental engine
     with value-equality early cutoff (Baseline B — strong hand-engineered baseline)
  3. LivingTraceContractEngine: trace-driven Trace-to-Contract compiler with formally
     certified LipschitzMarginCanary guards, regime caching, and KnowledgeLedger
  4. PeriodicCanaryEngine: periodically sampled monitor with explicit UNKNOWN states
     for quantifying probabilistic guard failure rates (Experiment 2)
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set, Tuple
import heapq
import time

from core.canary import CanaryState, PeriodicAuditCanary
from core.compiler import CompiledContractBundle, NodeTraceStats, TraceToContractCompiler
from core.contracts import KnowledgeLedger, LedgerEvent
from core.cost_ledger import CostCategory, CostLedger, EnergyModel, ResourceVector
from core.dependency_graph import DependencyGraph, OpType
from core.environment import UpdateEvent
from core.trace import TracePolicy, TraceStore


class BaseEngine:
    """Common interface for all benchmarked computational systems."""

    def __init__(
        self,
        name: str,
        algorithm_version: str,
        graph: DependencyGraph,
        energy_model: Optional[EnergyModel] = None,
    ) -> None:
        self.name = name
        self.algorithm_version = algorithm_version
        self.graph = graph
        self.energy_model = energy_model or EnergyModel()
        self.ledger = CostLedger(
            system_name=name,
            algorithm_version=algorithm_version,
            energy_model=self.energy_model,
        )
        self.values: List[float] = [0.0] * len(graph)
        self.current_inputs: Dict[int, float] = {}
        self.base_memory_bytes: int = len(graph) * 64

    def initialize(self, initial_inputs: Dict[int, float]) -> float:
        """Step 0: full initial evaluation on initial environmental state."""
        t0 = time.perf_counter()
        c0 = time.process_time()

        self.current_inputs = {nid: float(initial_inputs[nid]) for nid in self.graph.input_ids}
        for nid, val in self.current_inputs.items():
            self.values[nid] = val
        eval_ops = len(self.current_inputs)
        for node in self.graph.nodes:
            if node.op is not OpType.INPUT:
                self.values[node.node_id] = node.evaluate(self.values)
                eval_ops += 1

        elapsed = time.perf_counter() - t0
        cpu_elapsed = time.process_time() - c0
        mem_read = eval_ops * 32
        joules = self.energy_model.estimate_joules(cpu_time_s=cpu_elapsed, memory_bytes=mem_read)

        exec_cost = ResourceVector(
            steps=eval_ops,
            time_s=elapsed,
            joules=joules,
            memory_bytes=mem_read,
        )
        out = self.values[self.graph.output_id]
        self.ledger.record_step(
            timestep=0,
            total_nodes=len(self.graph),
            visited_nodes=len(self.graph),
            costs={CostCategory.EXECUTION: exec_cost},
            output_value=out,
            active_memory_bytes=self.base_memory_bytes,
        )
        return out

    def step(self, event: UpdateEvent) -> float:
        raise NotImplementedError

    def run(
        self, initial_inputs: Dict[int, float], events: Sequence[UpdateEvent]
    ) -> List[float]:
        outputs: List[float] = [self.initialize(initial_inputs)]
        for ev in events:
            outputs.append(self.step(ev))
        return outputs


class FullRecomputeEngine(BaseEngine):
    """Baseline A: recomputes the entire computational graph on every update."""

    def __init__(
        self,
        graph: DependencyGraph,
        energy_model: Optional[EnergyModel] = None,
    ) -> None:
        super().__init__(
            name="full_recomputation",
            algorithm_version="full_topo_v1",
            graph=graph,
            energy_model=energy_model,
        )

    def step(self, event: UpdateEvent) -> float:
        t0 = time.perf_counter()
        c0 = time.process_time()

        values = self.values
        for nid, val in event.delta.items():
            self.current_inputs[nid] = val
            values[nid] = val

        nodes = self.graph.nodes
        eval_ops = len(event.delta)
        for node in nodes:
            if node.op is not OpType.INPUT:
                values[node.node_id] = node.evaluate(values)
                eval_ops += 1

        elapsed = time.perf_counter() - t0
        cpu_elapsed = time.process_time() - c0
        mem_read = eval_ops * 32
        joules = self.energy_model.estimate_joules(cpu_time_s=cpu_elapsed, memory_bytes=mem_read)

        out = values[self.graph.output_id]
        self.ledger.record_step(
            timestep=event.timestep,
            total_nodes=len(self.graph),
            visited_nodes=len(self.graph),
            costs={
                CostCategory.EXECUTION: ResourceVector(
                    steps=eval_ops,
                    time_s=elapsed,
                    joules=joules,
                    memory_bytes=mem_read,
                )
            },
            output_value=out,
            active_memory_bytes=self.base_memory_bytes,
        )
        return out


class ConventionalIncrementalEngine(BaseEngine):
    """Baseline B: strong hand-engineered topological incremental engine with early cutoff.

    Uses a min-heap ordered by topological node_id so every affected node is evaluated at
    most once per update, and halts propagation immediately when a node's output is unchanged.
    """

    def __init__(
        self,
        graph: DependencyGraph,
        energy_model: Optional[EnergyModel] = None,
    ) -> None:
        super().__init__(
            name="conventional_incremental",
            algorithm_version="topo_heap_early_cutoff_v1",
            graph=graph,
            energy_model=energy_model,
        )

    def step(self, event: UpdateEvent) -> float:
        t0 = time.perf_counter()
        c0 = time.process_time()

        values = self.values
        nodes = self.graph.nodes
        heap: List[int] = []
        in_heap: Set[int] = set()
        visited = 0
        exec_ops = 0

        for nid, new_val in event.delta.items():
            old_val = values[nid]
            self.current_inputs[nid] = new_val
            visited += 1
            exec_ops += 1
            if new_val != old_val:
                values[nid] = new_val
                for child in nodes[nid].children:
                    if child not in in_heap:
                        in_heap.add(child)
                        heapq.heappush(heap, child)

        while heap:
            nid = heapq.heappop(heap)
            node = nodes[nid]
            old_val = values[nid]
            new_val = node.evaluate(values)
            visited += 1
            exec_ops += 1
            if new_val != old_val:
                values[nid] = new_val
                for child in node.children:
                    if child not in in_heap:
                        in_heap.add(child)
                        heapq.heappush(heap, child)

        elapsed = time.perf_counter() - t0
        cpu_elapsed = time.process_time() - c0
        mem_read = exec_ops * 40
        joules = self.energy_model.estimate_joules(cpu_time_s=cpu_elapsed, memory_bytes=mem_read)

        out = values[self.graph.output_id]
        self.ledger.record_step(
            timestep=event.timestep,
            total_nodes=len(self.graph),
            visited_nodes=visited,
            costs={
                CostCategory.EXECUTION: ResourceVector(
                    steps=max(1, exec_ops),
                    time_s=elapsed,
                    joules=joules,
                    memory_bytes=mem_read,
                )
            },
            output_value=out,
            active_memory_bytes=self.base_memory_bytes + len(self.graph) * 16,
        )
        return out


class LivingTraceContractEngine(BaseEngine):
    """System C: Trace-informed Living Computation engine with formally certified canaries.

    Lifecycle:
      1. Warmup (1..warmup_steps): executes incrementally while recording traces & node stats.
      2. Compilation (at t = warmup_steps): runs TraceToContractCompiler to compress invariant
         cones into ValidityContracts backed by LipschitzMarginCanary + regime caches.
      3. Contract-guided execution (t > warmup_steps): intercepts changes at contract boundaries;
         when a canary returns SAFE, skips the entire compressed sub-DAG and logs the avoidance
         (with assumptions and estimated energy savings) to the KnowledgeLedger.
      4. Optional adaptive retirement: under hostile high-entropy regimes, suspends net-negative
         contracts to prevent unbounded guard overhead.
    """

    def __init__(
        self,
        graph: DependencyGraph,
        energy_model: Optional[EnergyModel] = None,
        warmup_steps: int = 150,
        trace_policy: TracePolicy = TracePolicy.RECONSTRUCTIBLE_DELTA,
        trace_path: Optional[Path] = None,
        enable_regime_cache: bool = True,
        adaptive_retirement: bool = False,
        retire_min_checks: int = 50,
        retire_min_hit_rate: float = 0.25,
        name: str = "living_trace_contract",
    ) -> None:
        super().__init__(
            name=name,
            algorithm_version="trace_to_contract_lipschitz_v1",
            graph=graph,
            energy_model=energy_model,
        )
        self.warmup_steps = warmup_steps
        self.enable_regime_cache = enable_regime_cache
        self.adaptive_retirement = adaptive_retirement
        self.retire_min_checks = retire_min_checks
        self.retire_min_hit_rate = retire_min_hit_rate

        self.trace_store = TraceStore(
            policy=trace_policy,
            checkpoint_interval=500,
            persist_path=trace_path,
            energy_model=self.energy_model,
            keep_in_memory=True,
        )
        self.knowledge_ledger = KnowledgeLedger()
        self.node_stats: Dict[int, NodeTraceStats] = {
            n.node_id: NodeTraceStats() for n in graph.nodes
        }
        self.compiler = TraceToContractCompiler(
            graph=graph,
            energy_model=self.energy_model,
            enable_regime_cache=enable_regime_cache,
        )
        self.bundle: Optional[CompiledContractBundle] = None
        # Precomputed per-node non-internal children for fast routing after compilation
        self._normal_children: List[List[int]] = [list(n.children) for n in graph.nodes]
        # Track calibrated average joules per single node evaluation from warmup for avoidance accounting
        self._joules_per_node_eval: float = 5.0e-6

    def _rebuild_routing(self) -> None:
        """Rebuild fast child routing table respecting active contracts."""
        if self.bundle is None:
            self._normal_children = [list(n.children) for n in self.graph.nodes]
            return

        active_internals: Set[int] = set()
        for tid, canary in self.bundle.canaries_by_target.items():
            if canary.representation.contract.active:
                active_internals.update(self.bundle.target_to_internals[tid])

        self._normal_children = [
            [c for c in n.children if c not in active_internals]
            for n in self.graph.nodes
        ]

    def initialize(self, initial_inputs: Dict[int, float]) -> float:
        out = super().initialize(initial_inputs)
        # Record initial checkpoint trace honestly
        _, trace_cost = self.trace_store.record(
            timestep=0,
            algorithm_version=self.algorithm_version,
            input_delta=self.current_inputs,
            full_inputs=self.current_inputs,
            output_value=out,
            visited_count=len(self.graph),
        )
        self.ledger.totals_by_category[CostCategory.TRACE_RECORDING].add_inplace(trace_cost)
        self.ledger.records[-1].by_category[CostCategory.TRACE_RECORDING].add_inplace(trace_cost)
        return out

    def step(self, event: UpdateEvent) -> float:
        values = self.values
        nodes = self.graph.nodes
        t = event.timestep

        exec_cost = ResourceVector()
        guard_cost = ResourceVector()
        learn_cost = ResourceVector()
        reconfig_cost = ResourceVector()

        visited = 0
        exec_ops = 0
        guard_ops = 0
        contracts_hit = 0
        contracts_missed = 0
        canaries_safe = 0
        canaries_unsafe = 0
        nodes_avoided = 0
        avoided_ids: List[str] = []
        invalidated_ids: List[str] = []

        t_exec0 = time.perf_counter()
        c_exec0 = time.process_time()

        if self.bundle is None:
            # --- Phase 1: Warmup (conventional incremental + stats gathering) ---
            heap: List[int] = []
            in_heap: Set[int] = set()
            for nid, new_val in event.delta.items():
                old_val = values[nid]
                self.current_inputs[nid] = new_val
                visited += 1
                exec_ops += 1
                if new_val != old_val:
                    values[nid] = new_val
                    for child in nodes[nid].children:
                        if child not in in_heap:
                            in_heap.add(child)
                            heapq.heappush(heap, child)

            while heap:
                nid = heapq.heappop(heap)
                node = nodes[nid]
                old_val = values[nid]
                new_val = node.evaluate(values)
                visited += 1
                exec_ops += 1
                st = self.node_stats[nid]
                st.eval_count += 1
                if new_val != old_val:
                    st.change_count += 1
                    values[nid] = new_val
                    for child in node.children:
                        if child not in in_heap:
                            in_heap.add(child)
                            heapq.heappush(heap, child)
                else:
                    st.invariant_count += 1

            exec_elapsed = time.perf_counter() - t_exec0
            exec_cpu = time.process_time() - c_exec0
            mem_read = exec_ops * 40
            exec_cost = ResourceVector(
                steps=max(1, exec_ops),
                time_s=exec_elapsed,
                joules=self.energy_model.estimate_joules(exec_cpu, memory_bytes=mem_read),
                memory_bytes=mem_read,
            )

            # Compile contracts at the end of warmup
            if t == self.warmup_steps:
                # Calibrate empirical joules per node eval from warmup measurements
                warmup_exec = self.ledger.totals_by_category[CostCategory.EXECUTION]
                if warmup_exec.steps > 0:
                    self._joules_per_node_eval = warmup_exec.joules / warmup_exec.steps

                self.bundle, learn_cost = self.compiler.compile_from_stats(
                    timestep=t,
                    node_stats=self.node_stats,
                    current_values=values,
                    knowledge_ledger=self.knowledge_ledger,
                )
                self._rebuild_routing()
        else:
            # --- Phase 2: Contract-guided execution with sound Lipschitz-Margin canaries ---
            bundle = self.bundle
            b_to_targets = bundle.boundary_to_targets
            canaries = bundle.canaries_by_target
            normal_children = self._normal_children

            heap = []
            in_heap = set()
            dirty_boundaries: Dict[int, List[int]] = {}
            retired_any = False

            def propagate_from(src_id: int) -> None:
                for child in normal_children[src_id]:
                    if child not in in_heap:
                        in_heap.add(child)
                        heapq.heappush(heap, child)
                targets = b_to_targets.get(src_id)
                if targets:
                    for tid in targets:
                        if canaries[tid].representation.contract.active:
                            lst = dirty_boundaries.get(tid)
                            if lst is None:
                                dirty_boundaries[tid] = [src_id]
                            else:
                                lst.append(src_id)
                            if tid not in in_heap:
                                in_heap.add(tid)
                                heapq.heappush(heap, tid)

            for nid, new_val in event.delta.items():
                old_val = values[nid]
                self.current_inputs[nid] = new_val
                visited += 1
                exec_ops += 1
                if new_val != old_val:
                    values[nid] = new_val
                    propagate_from(nid)

            while heap:
                nid = heapq.heappop(heap)
                canary = canaries.get(nid)

                if canary is not None and canary.representation.contract.active and nid in dirty_boundaries:
                    contract = canary.representation.contract
                    res = canary.check(dirty_boundaries[nid], values, t)
                    guard_ops += res.guard_ops

                    if res.state is CanaryState.SAFE:
                        canaries_safe += 1
                        contracts_hit += 1
                        saved_nodes = contract.absorbed_node_count
                        nodes_avoided += saved_nodes
                        avoided_ids.append(contract.contract_id)
                        est_j = max(0.0, (saved_nodes - res.guard_ops) * self._joules_per_node_eval)
                        self.knowledge_ledger.record_avoidance(
                            timestep=t,
                            contract=contract,
                            reason=res.reason,
                            estimated_joules_saved=est_j,
                            details={
                                "changed_boundaries": dirty_boundaries[nid],
                                "guard_ops": res.guard_ops,
                                "used_regime_cache": res.used_regime_cache,
                            },
                        )
                        # If regime cache produced a different output from previous step, propagate!
                        assert res.cached_output is not None
                        if res.cached_output != values[nid]:
                            values[nid] = res.cached_output
                            propagate_from(nid)
                        continue

                    # Canary UNSAFE: recompute absorbed internal cone + target, then reanchor
                    canaries_unsafe += 1
                    contracts_missed += 1
                    invalidated_ids.append(contract.contract_id)
                    for internal_id in contract.internal_ids:
                        values[internal_id] = nodes[internal_id].evaluate(values)
                        visited += 1
                        exec_ops += 1

                    target_node = nodes[nid]
                    old_val = values[nid]
                    new_val = target_node.evaluate(values)
                    visited += 1
                    exec_ops += 1

                    reanchor_ops = canary.reanchor(
                        current_values=values,
                        pre_value=values[target_node.parents[0]],
                        output_value=new_val,
                    )
                    guard_ops += reanchor_ops

                    self.knowledge_ledger.record_invalidation(
                        timestep=t,
                        contract=contract,
                        reason=res.reason,
                        details={
                            "new_margin": round(canary.representation.ref_margin, 6),
                            "output_changed": new_val != old_val,
                        },
                    )

                    # Optional adaptive retirement if contract is chronically unprofitable
                    if (
                        self.adaptive_retirement
                        and canary.checks >= self.retire_min_checks
                        and (canary.safe_count / canary.checks) < self.retire_min_hit_rate
                    ):
                        contract.active = False
                        retired_any = True
                        self.knowledge_ledger.lifecycle_events.append(
                            LedgerEvent(
                                timestep=t,
                                event_type="retired",
                                contract_id=contract.contract_id,
                                target_node_name=contract.target_node_name,
                                reason=(
                                    f"Retired unprofitable contract: hit_rate="
                                    f"{canary.safe_count / canary.checks:.2%} < {self.retire_min_hit_rate:.0%}"
                                ),
                            )
                        )

                    if new_val != old_val:
                        values[nid] = new_val
                        propagate_from(nid)
                    continue

                # Standard incremental node evaluation
                node = nodes[nid]
                old_val = values[nid]
                new_val = node.evaluate(values)
                visited += 1
                exec_ops += 1
                if new_val != old_val:
                    values[nid] = new_val
                    propagate_from(nid)

            if retired_any:
                tr0 = time.perf_counter()
                cr0 = time.process_time()
                self._rebuild_routing()
                reconfig_cost = ResourceVector(
                    steps=len(self.graph),
                    time_s=time.perf_counter() - tr0,
                    joules=self.energy_model.estimate_joules(time.process_time() - cr0),
                )

            total_elapsed = time.perf_counter() - t_exec0
            total_cpu = time.process_time() - c_exec0
            # Attribute single-timer step time proportionally between execution and guarding
            # (eliminating inner-loop timer syscall observer effects while preserving total time exactly)
            denom = max(1, exec_ops + guard_ops)
            guard_frac = guard_ops / denom
            guard_time = total_elapsed * guard_frac
            guard_cpu = total_cpu * guard_frac
            exec_elapsed = total_elapsed - guard_time
            exec_cpu = total_cpu - guard_cpu

            exec_mem = exec_ops * 40
            guard_mem = guard_ops * 24
            exec_cost = ResourceVector(
                steps=exec_ops,
                time_s=exec_elapsed,
                joules=self.energy_model.estimate_joules(exec_cpu, memory_bytes=exec_mem),
                memory_bytes=exec_mem,
            )
            guard_cost = ResourceVector(
                steps=guard_ops,
                time_s=guard_time,
                joules=self.energy_model.estimate_joules(guard_cpu, memory_bytes=guard_mem),
                memory_bytes=guard_mem,
            )

        out = values[self.graph.output_id]

        # Honest trace recording cost on every step
        _, trace_cost = self.trace_store.record(
            timestep=t,
            algorithm_version=self.algorithm_version,
            input_delta=event.delta,
            full_inputs=self.current_inputs,
            output_value=out,
            visited_count=visited,
            avoided_contracts=avoided_ids,
            invalidated_contracts=invalidated_ids,
            is_warmup=(t <= self.warmup_steps),
        )

        active_mem = (
            self.base_memory_bytes
            + self.trace_store.total_bytes_written
            + (len(self.bundle.canaries_by_target) * 512 if self.bundle else 0)
        )

        self.ledger.record_step(
            timestep=t,
            total_nodes=len(self.graph),
            visited_nodes=visited,
            costs={
                CostCategory.EXECUTION: exec_cost,
                CostCategory.TRACE_RECORDING: trace_cost,
                CostCategory.LEARNING: learn_cost,
                CostCategory.GUARDING: guard_cost,
                CostCategory.RECONFIGURATION: reconfig_cost,
            },
            output_value=out,
            active_memory_bytes=active_mem,
            contracts_hit=contracts_hit,
            contracts_missed=contracts_missed,
            canaries_safe=canaries_safe,
            canaries_unsafe=canaries_unsafe,
            canaries_unknown=0,
            nodes_avoided_by_contracts=nodes_avoided,
        )
        return out

    def close(self) -> None:
        self.trace_store.close()


class PeriodicCanaryEngine(BaseEngine):
    """Experiment 2 comparison engine: periodically sampled monitors with UNKNOWN states.

    Reuses the same compiled subgraph structure as LivingTraceContractEngine, but replaces
    sound LipschitzMarginCanary with PeriodicAuditCanary(audit_period=P). Between audits,
    canaries report UNKNOWN and reuse stale values optimistically — quantifying the exact
    missed-invalidation rate vs monitoring savings.
    """

    def __init__(
        self,
        graph: DependencyGraph,
        energy_model: Optional[EnergyModel] = None,
        warmup_steps: int = 150,
        audit_period: int = 10,
    ) -> None:
        super().__init__(
            name=f"periodic_canary_p{audit_period}",
            algorithm_version=f"periodic_sampled_p{audit_period}_v1",
            graph=graph,
            energy_model=energy_model,
        )
        self.warmup_steps = warmup_steps
        self.audit_period = audit_period
        self.node_stats: Dict[int, NodeTraceStats] = {
            n.node_id: NodeTraceStats() for n in graph.nodes
        }
        self.compiler = TraceToContractCompiler(graph=graph, energy_model=self.energy_model)
        self.knowledge_ledger = KnowledgeLedger()
        self.periodic_canaries: Dict[int, PeriodicAuditCanary] = {}
        self.boundary_to_targets: Dict[int, List[int]] = {}
        self.target_to_internals: Dict[int, Tuple[int, ...]] = {}
        self._normal_children: List[List[int]] = [list(n.children) for n in graph.nodes]
        self._compiled: bool = False

    def step(self, event: UpdateEvent) -> float:
        values = self.values
        nodes = self.graph.nodes
        t = event.timestep
        visited = 0
        exec_ops = 0
        guard_ops = 0
        canaries_safe = 0
        canaries_unsafe = 0
        canaries_unknown = 0
        contracts_hit = 0
        contracts_missed = 0
        nodes_avoided = 0
        learn_cost = ResourceVector()

        t0 = time.perf_counter()
        c0 = time.process_time()

        if not self._compiled:
            heap: List[int] = []
            in_heap: Set[int] = set()
            for nid, new_val in event.delta.items():
                old_val = values[nid]
                self.current_inputs[nid] = new_val
                visited += 1
                exec_ops += 1
                if new_val != old_val:
                    values[nid] = new_val
                    for child in nodes[nid].children:
                        if child not in in_heap:
                            in_heap.add(child)
                            heapq.heappush(heap, child)
            while heap:
                nid = heapq.heappop(heap)
                old_val = values[nid]
                new_val = nodes[nid].evaluate(values)
                visited += 1
                exec_ops += 1
                st = self.node_stats[nid]
                st.eval_count += 1
                if new_val != old_val:
                    st.change_count += 1
                    values[nid] = new_val
                    for child in nodes[nid].children:
                        if child not in in_heap:
                            in_heap.add(child)
                            heapq.heappush(heap, child)
                else:
                    st.invariant_count += 1

            if t == self.warmup_steps:
                bundle, learn_cost = self.compiler.compile_from_stats(
                    timestep=t,
                    node_stats=self.node_stats,
                    current_values=values,
                    knowledge_ledger=self.knowledge_ledger,
                )
                self.boundary_to_targets = bundle.boundary_to_targets
                self.target_to_internals = bundle.target_to_internals
                active_internals: Set[int] = set()
                for tid, lip_canary in bundle.canaries_by_target.items():
                    pc = PeriodicAuditCanary(
                        canary_id=f"pcanary_{tid}",
                        representation=lip_canary.representation,
                        audit_period=self.audit_period,
                    )
                    pc.reanchor(
                        values,
                        values[nodes[tid].parents[0]],
                        values[tid],
                    )
                    self.periodic_canaries[tid] = pc
                    active_internals.update(bundle.target_to_internals[tid])
                self._normal_children = [
                    [c for c in n.children if c not in active_internals]
                    for n in nodes
                ]
                self._compiled = True
        else:
            heap = []
            in_heap = set()
            dirty_boundaries: Dict[int, List[int]] = {}
            normal_children = self._normal_children
            b_to_targets = self.boundary_to_targets

            def propagate_from(src_id: int) -> None:
                for child in normal_children[src_id]:
                    if child not in in_heap:
                        in_heap.add(child)
                        heapq.heappush(heap, child)
                targets = b_to_targets.get(src_id)
                if targets:
                    for tid in targets:
                        lst = dirty_boundaries.get(tid)
                        if lst is None:
                            dirty_boundaries[tid] = [src_id]
                        else:
                            lst.append(src_id)
                        if tid not in in_heap:
                            in_heap.add(tid)
                            heapq.heappush(heap, tid)

            for nid, new_val in event.delta.items():
                old_val = values[nid]
                self.current_inputs[nid] = new_val
                visited += 1
                exec_ops += 1
                if new_val != old_val:
                    values[nid] = new_val
                    propagate_from(nid)

            while heap:
                nid = heapq.heappop(heap)
                pc = self.periodic_canaries.get(nid)
                if pc is not None and nid in dirty_boundaries:
                    res = pc.check(dirty_boundaries[nid], values, t)
                    guard_ops += res.guard_ops

                    if res.state is CanaryState.SAFE:
                        canaries_safe += 1
                        contracts_hit += 1
                        nodes_avoided += pc.representation.contract.absorbed_node_count
                        continue
                    if res.state is CanaryState.UNKNOWN:
                        # Optimistic reuse between audits (explicitly tracked as UNKNOWN)
                        canaries_unknown += 1
                        contracts_hit += 1
                        nodes_avoided += pc.representation.contract.absorbed_node_count
                        continue

                    canaries_unsafe += 1
                    contracts_missed += 1
                    for internal_id in self.target_to_internals[nid]:
                        values[internal_id] = nodes[internal_id].evaluate(values)
                        visited += 1
                        exec_ops += 1
                    old_val = values[nid]
                    new_val = nodes[nid].evaluate(values)
                    visited += 1
                    exec_ops += 1
                    guard_ops += pc.reanchor(values, values[nodes[nid].parents[0]], new_val)
                    if new_val != old_val:
                        values[nid] = new_val
                        propagate_from(nid)
                    continue

                old_val = values[nid]
                new_val = nodes[nid].evaluate(values)
                visited += 1
                exec_ops += 1
                if new_val != old_val:
                    values[nid] = new_val
                    propagate_from(nid)

        tot_t = time.perf_counter() - t0
        tot_c = time.process_time() - c0
        denom = max(1, exec_ops + guard_ops)
        g_frac = guard_ops / denom
        guard_time = tot_t * g_frac
        guard_cpu = tot_c * g_frac
        exec_t = tot_t - guard_time
        exec_c = tot_c - guard_cpu

        out = values[self.graph.output_id]
        self.ledger.record_step(
            timestep=t,
            total_nodes=len(self.graph),
            visited_nodes=visited,
            costs={
                CostCategory.EXECUTION: ResourceVector(
                    steps=exec_ops,
                    time_s=exec_t,
                    joules=self.energy_model.estimate_joules(exec_c, memory_bytes=exec_ops * 40),
                    memory_bytes=exec_ops * 40,
                ),
                CostCategory.GUARDING: ResourceVector(
                    steps=guard_ops,
                    time_s=guard_time,
                    joules=self.energy_model.estimate_joules(guard_cpu, memory_bytes=guard_ops * 24),
                    memory_bytes=guard_ops * 24,
                ),
                CostCategory.LEARNING: learn_cost,
            },
            output_value=out,
            active_memory_bytes=self.base_memory_bytes,
            contracts_hit=contracts_hit,
            contracts_missed=contracts_missed,
            canaries_safe=canaries_safe,
            canaries_unsafe=canaries_unsafe,
            canaries_unknown=canaries_unknown,
            nodes_avoided_by_contracts=nodes_avoided,
        )
        return out
