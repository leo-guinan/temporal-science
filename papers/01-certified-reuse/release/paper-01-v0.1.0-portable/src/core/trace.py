"""Execution traces, append-only JSONL trace store, and deterministic replay.

Preserves the distinction between:
  - materialized traces (explicit snapshots of evaluated node states), and
  - reconstructible traces (compact input deltas + periodic checkpoints + op counts
    sufficient for deterministic replay without saturating storage/memory overhead).

Instrumentation overhead is measured and returned as a ResourceVector so trace
recording is never treated as free.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple
import json
import time

from core.cost_ledger import EnergyModel, ResourceVector
from core.dependency_graph import DependencyGraph


class TracePolicy(str, Enum):
    """Controls what gets materialized in the persistent execution trace."""

    SURPRISE_DRIVEN = "surprise_driven"  # warmup + checkpoints + invalidations only (lowest overhead)
    RECONSTRUCTIBLE_DELTA = "reconstructible_delta"  # input delta + checkpoints + summary every step
    OBSERVED_TRANSITIONS = "observed_transitions"  # evaluated nodes & outputs during warmup
    FULL_MATERIALIZED = "full_materialized"  # full state vector snapshot every step


@dataclass
class ExecutionTrace:
    """Persistent record of one computational step."""

    timestep: int
    algorithm_version: str
    input_delta: Dict[int, float]
    output_value: float
    visited_count: int
    timestamp_s: float
    policy: TracePolicy
    # Optional materialized fields depending on TracePolicy
    checkpoint_inputs: Optional[Dict[int, float]] = None
    node_transitions: Optional[Dict[int, float]] = None
    avoided_contracts: List[str] = field(default_factory=list)
    invalidated_contracts: List[str] = field(default_factory=list)
    step_cost: Optional[Dict[str, Any]] = None

    def to_json_line(self) -> str:
        payload: Dict[str, Any] = {
            "t": self.timestep,
            "alg": self.algorithm_version,
            "policy": self.policy.value,
            "ts": round(self.timestamp_s, 6),
            "in_delta": {str(k): v for k, v in self.input_delta.items()},
            "out": self.output_value,
            "visited": self.visited_count,
        }
        if self.checkpoint_inputs is not None:
            payload["ckpt_in"] = {str(k): v for k, v in self.checkpoint_inputs.items()}
        if self.node_transitions is not None:
            payload["transitions"] = {str(k): v for k, v in self.node_transitions.items()}
        if self.avoided_contracts:
            payload["avoided"] = self.avoided_contracts
        if self.invalidated_contracts:
            payload["invalidated"] = self.invalidated_contracts
        if self.step_cost is not None:
            payload["cost"] = self.step_cost
        return json.dumps(payload, separators=(",", ":"))

    @classmethod
    def from_json_line(cls, line: str) -> ExecutionTrace:
        data = json.loads(line)
        return cls(
            timestep=int(data["t"]),
            algorithm_version=str(data["alg"]),
            input_delta={int(k): float(v) for k, v in data["in_delta"].items()},
            output_value=float(data["out"]),
            visited_count=int(data["visited"]),
            timestamp_s=float(data["ts"]),
            policy=TracePolicy(data["policy"]),
            checkpoint_inputs=(
                {int(k): float(v) for k, v in data["ckpt_in"].items()}
                if "ckpt_in" in data
                else None
            ),
            node_transitions=(
                {int(k): float(v) for k, v in data["transitions"].items()}
                if "transitions" in data
                else None
            ),
            avoided_contracts=list(data.get("avoided", [])),
            invalidated_contracts=list(data.get("invalidated", [])),
            step_cost=data.get("cost"),
        )


class TraceStore:
    """Append-only JSONL trace store with honest recording cost accounting and replay."""

    def __init__(
        self,
        policy: TracePolicy = TracePolicy.RECONSTRUCTIBLE_DELTA,
        checkpoint_interval: int = 500,
        persist_path: Optional[Path] = None,
        energy_model: Optional[EnergyModel] = None,
        keep_in_memory: bool = True,
        flush_batch_size: int = 256,
    ) -> None:
        self.policy = policy
        self.checkpoint_interval = checkpoint_interval
        self.persist_path = persist_path
        self.energy_model = energy_model or EnergyModel()
        self.keep_in_memory = keep_in_memory
        self.flush_batch_size = max(1, flush_batch_size)
        self.traces: List[ExecutionTrace] = []
        self.total_bytes_written: int = 0
        self._file_handle = None
        self._write_buffer: List[str] = []

        if self.persist_path is not None:
            self.persist_path.parent.mkdir(parents=True, exist_ok=True)
            self._file_handle = self.persist_path.open("w", encoding="utf-8")

    def flush(self) -> int:
        """Flush buffered JSONL lines to disk and return bytes written."""
        if self._file_handle is None or not self._write_buffer:
            return 0
        chunk = "".join(self._write_buffer)
        self._file_handle.write(chunk)
        self._write_buffer.clear()
        return len(chunk.encode("utf-8"))

    def close(self) -> None:
        if self._file_handle is not None:
            self.flush()
            self._file_handle.close()
            self._file_handle = None

    def record(
        self,
        timestep: int,
        algorithm_version: str,
        input_delta: Dict[int, float],
        full_inputs: Dict[int, float],
        output_value: float,
        visited_count: int,
        node_transitions: Optional[Dict[int, float]] = None,
        avoided_contracts: Optional[List[str]] = None,
        invalidated_contracts: Optional[List[str]] = None,
        step_cost: Optional[Dict[str, Any]] = None,
        is_warmup: bool = False,
    ) -> Tuple[Optional[ExecutionTrace], ResourceVector]:
        """Record a trace entry and return the exact instrumentation ResourceVector."""
        # Fast-path for SURPRISE_DRIVEN policy: skip serialization on routine predicted steps
        if self.policy is TracePolicy.SURPRISE_DRIVEN:
            is_ckpt = timestep == 0 or (
                self.checkpoint_interval > 0 and timestep % self.checkpoint_interval == 0
            )
            has_surprise = bool(invalidated_contracts)
            if not (is_warmup or is_ckpt or has_surprise):
                # Still account honestly for the 1-op check decision
                return None, ResourceVector(steps=1, time_s=0.0, joules=0.0, memory_bytes=0)

        t0 = time.perf_counter()
        c0 = time.process_time()

        ckpt: Optional[Dict[int, float]] = None
        transitions_to_store: Optional[Dict[int, float]] = None

        if self.policy is TracePolicy.FULL_MATERIALIZED:
            ckpt = dict(full_inputs)
            transitions_to_store = dict(node_transitions) if node_transitions else None
            record_ops = len(full_inputs) + (len(transitions_to_store) if transitions_to_store else 0)
        elif self.policy is TracePolicy.OBSERVED_TRANSITIONS:
            if timestep == 0 or (self.checkpoint_interval > 0 and timestep % self.checkpoint_interval == 0):
                ckpt = dict(full_inputs)
            transitions_to_store = dict(node_transitions) if node_transitions else None
            record_ops = len(input_delta) + (len(transitions_to_store) if transitions_to_store else 0)
        else:  # RECONSTRUCTIBLE_DELTA or SURPRISE_DRIVEN (when triggered)
            if timestep == 0 or (self.checkpoint_interval > 0 and timestep % self.checkpoint_interval == 0):
                ckpt = dict(full_inputs)
            record_ops = len(input_delta) + (len(ckpt) if ckpt else 0) + 1

        trace = ExecutionTrace(
            timestep=timestep,
            algorithm_version=algorithm_version,
            input_delta=dict(input_delta),
            output_value=output_value,
            visited_count=visited_count,
            timestamp_s=t0,
            policy=self.policy,
            checkpoint_inputs=ckpt,
            node_transitions=transitions_to_store,
            avoided_contracts=list(avoided_contracts) if avoided_contracts else [],
            invalidated_contracts=list(invalidated_contracts) if invalidated_contracts else [],
            step_cost=step_cost,
        )

        bytes_serialized = 0
        if self._file_handle is not None:
            line = trace.to_json_line() + "\n"
            self._write_buffer.append(line)
            bytes_serialized = len(line.encode("utf-8"))
            self.total_bytes_written += bytes_serialized
            if len(self._write_buffer) >= self.flush_batch_size:
                self.flush()
        else:
            # Estimate memory footprint of the in-memory trace struct honestly
            bytes_serialized = (
                64
                + 24 * len(trace.input_delta)
                + (24 * len(ckpt) if ckpt else 0)
                + (24 * len(transitions_to_store) if transitions_to_store else 0)
            )
            self.total_bytes_written += bytes_serialized

        if self.keep_in_memory:
            self.traces.append(trace)

        elapsed = time.perf_counter() - t0
        cpu_elapsed = time.process_time() - c0
        joules = self.energy_model.estimate_joules(
            cpu_time_s=cpu_elapsed,
            memory_bytes=bytes_serialized,
            communication_bytes=bytes_serialized if self._file_handle is not None else 0,
        )
        cost = ResourceVector(
            steps=max(1, record_ops),
            time_s=elapsed,
            joules=joules,
            memory_bytes=bytes_serialized,
            communication_bytes=bytes_serialized if self._file_handle is not None else 0,
        )
        return trace, cost

    @staticmethod
    def iter_jsonl(path: Path) -> Iterator[ExecutionTrace]:
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    yield ExecutionTrace.from_json_line(line)

    @staticmethod
    def verify_deterministic_replay(
        graph: DependencyGraph,
        traces: List[ExecutionTrace],
        sample_timesteps: Optional[List[int]] = None,
        atol: float = 1e-12,
    ) -> Dict[str, Any]:
        """Reconstruct inputs from traces and verify deterministic output equivalence."""
        current_inputs: Dict[int, float] = {}
        checked = 0
        mismatches = 0
        sample_set = set(sample_timesteps) if sample_timesteps is not None else None

        for tr in traces:
            if tr.checkpoint_inputs is not None:
                current_inputs = dict(tr.checkpoint_inputs)
            else:
                current_inputs.update(tr.input_delta)

            if sample_set is None or tr.timestep in sample_set:
                vals = graph.evaluate_full(current_inputs)
                replayed = vals[graph.output_id]
                checked += 1
                if abs(replayed - tr.output_value) > atol:
                    mismatches += 1

        return {
            "checked": checked,
            "mismatches": mismatches,
            "replay_exact": mismatches == 0,
        }
