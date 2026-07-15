"""
Swarm agent execution — run a prompt across multiple opencode models.

Provides :class:`SwarmRunner` for executing the same prompt with *n_swarm_models*
different models (from the yaml config), with automatic failover via model cycling
and support for both sequential and concurrent execution modes.
"""

from __future__ import annotations

import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable

from ._runner import AgentCall
from ._base import AgentResult
from ._common import replace_placeholders


# ---------------------------------------------------------------------------
# SwarmRunner
# ---------------------------------------------------------------------------


class SwarmRunner:
    """Execute a prompt across multiple opencode models with failure handling.

    Parameters
    ----------
    config:
        Parsed ``rl_global_config.yaml`` dictionary.  Reads keys:
        ``data_swarm.n_swarm_models``, ``data_swarm.opencode_swarm_models``,
        ``data_swarm.swarm_execution``.
    cwd:
        Working directory for each agent subprocess.
    timeout:
        Per-agent timeout in seconds (default 180).
    """

    def __init__(self, config: dict[str, Any], cwd: Path, timeout: float = 180) -> None:
        data_swarm = config.get("data_swarm", {})
        self.n_models: int = data_swarm.get("n_swarm_models", 1)
        self.model_pool: list[str] = list(data_swarm.get("opencode_swarm_models", []))
        self.mode: str = data_swarm.get("swarm_execution", "sequential")
        self.cwd = Path(cwd)
        self.timeout = timeout

        if self.n_models < 1:
            raise ValueError("data_swarm.n_swarm_models must be >= 1")
        if not self.model_pool:
            raise ValueError("data_swarm.opencode_swarm_models is empty")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, prompt: str, file_check: Callable[[str], bool] | None = None,
            n_override: int | None = None) -> list[AgentResult]:
        """Run *prompt* with ``n_swarm_models``, handling failures with model cycling.

        The *prompt* may contain a ``<model_name>`` placeholder which is
        replaced per-model with the short name (portion after the last ``/``).

        If *file_check* is provided, it is called after each agent call with
        the full model name.  If it returns ``False``, the model is treated
        as failed (triggering failover), even if the agent returned exit 0.

        *n_override* temporarily overrides ``n_swarm_models`` for this call
        (e.g. when retrying only the missing slots).
        """
        n = n_override if n_override is not None else self.n_models
        models = self._select_models(n)
        if self.mode in ("concurrent", "parallel"):
            results, succeeded = self._run_concurrent(prompt, models, file_check)
        else:
            results, succeeded = self._run_sequential(prompt, models, file_check)
        if succeeded:
            print(
                f"[swarm] {len(succeeded)}/{n} models succeeded: "
                f"{', '.join(succeeded)}",
                file=sys.stderr,
            )
        else:
            print(
                f"[swarm] 0/{n} models succeeded.",
                file=sys.stderr,
            )
        return results

    # ------------------------------------------------------------------
    # Model selection
    # ------------------------------------------------------------------

    def _select_models(self, n: int | None = None) -> list[str]:
        """Select *n* models from the pool, cycling if needed (default: ``n_swarm_models``)."""
        if n is None:
            n = self.n_models
        selected: list[str] = []
        for i in range(n):
            selected.append(self.model_pool[i % len(self.model_pool)])
        return selected

    @staticmethod
    def _short_name(model: str) -> str:
        """Return the portion of *model* after the last ``/``, or *model* itself."""
        return model.rsplit("/", 1)[-1]

    # ------------------------------------------------------------------
    # Execution modes
    # ------------------------------------------------------------------

    def _run_sequential(
        self, prompt: str, models: list[str], file_check: Callable[[str], bool] | None
    ) -> tuple[list[AgentResult], list[str]]:
        """Run models one at a time.  On failure, cycle to the next unused model.

        Returns ``(results, succeeded_models)``.
        """
        used: set[str] = set()
        results: list[AgentResult] = []
        succeeded: list[str] = []

        for i, model in enumerate(models):
            current = model
            failed_this_slot: set[str] = set()
            while True:
                try:
                    resolved = prompt.replace("<model_name>", self._short_name(current))
                    result = self._call_agent(resolved, current)
                    # Check output file if callback provided
                    if file_check is not None and not file_check(current):
                        failed_this_slot.add(current)
                        raise RuntimeError(f"Output file missing for model {current}")
                    results.append(result)
                    used.add(current)
                    succeeded.append(current)
                    break
                except Exception as exc:
                    print(
                        f"[swarm] Model {current} failed: {exc}",
                        file=sys.stderr,
                    )
                    failed_this_slot.add(current)
                    nxt = self._pick_next(current, used, exclude=failed_this_slot)
                    if nxt is None:
                        print(
                            f"[swarm] No more models available, skipping slot {i}",
                            file=sys.stderr,
                        )
                        break
                    current = nxt

        return results, succeeded

    def _run_concurrent(
        self, prompt: str, models: list[str], file_check: Callable[[str], bool] | None
    ) -> tuple[list[AgentResult], list[str]]:
        """Run all models concurrently.  Each slot has independent failover.

        Returns ``(results, succeeded_models)``.
        """
        results: list[AgentResult] = []
        succeeded: list[str] = []
        lock = threading.Lock()
        used: set[str] = set()

        def _run_one(model: str) -> tuple[AgentResult | None, str | None]:
            current = model
            failed_this_slot: set[str] = set()
            while True:
                try:
                    resolved = prompt.replace("<model_name>", self._short_name(current))
                    result = self._call_agent(resolved, current)
                    # Check output file if callback provided
                    if file_check is not None and not file_check(current):
                        failed_this_slot.add(current)
                        raise RuntimeError(f"Output file missing for model {current}")
                    with lock:
                        used.add(current)
                    return result, current
                except Exception as exc:
                    print(
                        f"[swarm] Model {current} failed: {exc}",
                        file=sys.stderr,
                    )
                    failed_this_slot.add(current)
                    with lock:
                        nxt = self._pick_next(current, used, exclude=failed_this_slot)
                    if nxt is None:
                        print(
                            "[swarm] No more models available for a concurrent slot",
                            file=sys.stderr,
                        )
                        return None, None
                    current = nxt

        with ThreadPoolExecutor(max_workers=len(models)) as executor:
            futures = {executor.submit(_run_one, m): m for m in models}
            for future in as_completed(futures):
                r, model_name = future.result()
                if r is not None:
                    results.append(r)
                    if model_name is not None:
                        succeeded.append(model_name)

        return results, succeeded

    # ------------------------------------------------------------------
    # Failover logic
    # ------------------------------------------------------------------

    def _pick_next(self, current: str, used: set[str], exclude: set[str] | None = None) -> str | None:
        """Pick the next model from the pool after *current*.

        Preference order:
        1. First unused model not in *exclude*.
        2. Next in pool (cyclically) after *current* (skipping *exclude*).
        3. First in pool (fallback).

        Returns ``None`` when all pool models are in *exclude*.
        """
        # Prefer unused, excluding failed-for-this-slot
        for m in self.model_pool:
            if m not in used and (exclude is None or m not in exclude):
                return m
        # No unused non-excluded — try any non-excluded model
        if exclude is not None:
            remaining = [m for m in self.model_pool if m not in exclude]
            if not remaining:
                return None
            try:
                idx = self.model_pool.index(current)
                for m in self.model_pool[idx + 1:] + self.model_pool[:idx]:
                    if m in remaining:
                        return m
            except ValueError:
                return remaining[0]
        # No exclude — original cycling behavior
        try:
            idx = self.model_pool.index(current)
            return self.model_pool[(idx + 1) % len(self.model_pool)]
        except ValueError:
            return self.model_pool[0] if self.model_pool else None

    # ------------------------------------------------------------------
    # Low-level agent call
    # ------------------------------------------------------------------

    def _call_agent(self, prompt: str, model: str) -> AgentResult:
        """Execute a single agent call."""
        return AgentCall.run_once(
            "opencode",
            prompt=prompt,
            model=model,
            cwd=self.cwd,
            workspace_dir=self.cwd,
            timeout=self.timeout,
        )
