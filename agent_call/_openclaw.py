"""Openclaw agent — wraps the ``openclaw agent`` CLI."""

from __future__ import annotations

import shlex
import subprocess
from pathlib import Path
from typing import Optional

from ._base import AgentResult, BaseAgent

THINKING_LEVELS = (
    "off", "minimal", "low", "medium", "high", "xhigh", "adaptive", "max",
)


class OpenclawAgent(BaseAgent):
    """Agent that runs ``openclaw agent`` via subprocess."""

    name = "openclaw"
    output_filename_template = "{chat_id}_openclaw_output.txt"
    _supported_kwargs = frozenset({"agent_name", "thinking", "local"})

    # ── init (workspace setup) ───────────────────────────────────

    @staticmethod
    def needs_init() -> bool:
        return True

    def init(
        self,
        output_dir: Path,
        agent_name: str = "agentcall",
        **kwargs,
    ) -> Path:
        """Initialize openclaw workspace.

        *output_dir* is used directly as the openclaw native workspace —
        openclaw can only read/write inside this directory.
        """
        out_root = output_dir.expanduser().resolve()
        out_root.mkdir(parents=True, exist_ok=True)

        self._register_workspace(
            agent_name=agent_name,
            workspace_path=str(out_root),
            reset=False,
        )

        return out_root

    @staticmethod
    def _register_workspace(
        agent_name: str = "agentcall",
        workspace_path: str = "./agentcall_runs/openclaw/workspace",
        reset: bool = False,
    ) -> bool:
        """Register (and optionally reset) an openclaw agent workspace."""
        cmd_reset = f"openclaw agents delete {agent_name} --force"
        cmd = f"openclaw agents add {agent_name} --workspace {workspace_path}"
        try:
            if reset:
                subprocess.run(cmd_reset, shell=True, check=True)
            subprocess.run(cmd, shell=True, check=True)
            return True
        except subprocess.CalledProcessError:
            return False

    # ── execute ──────────────────────────────────────────────────

    def execute(
        self,
        prompt: str,
        *,
        cwd: Path,
        output: Path,
        chat_id: str,
        timeout: float | None = 600.0,
        tee: bool = False,
        agent_name: str | None = None,
        thinking: str = "medium",
        local: bool = True,
        **kwargs,
    ) -> AgentResult:
        if thinking not in THINKING_LEVELS:
            choices = ", ".join(THINKING_LEVELS)
            raise ValueError(f"thinking 必须是以下之一：{choices}")

        output.parent.mkdir(parents=True, exist_ok=True)

        if agent_name and agent_name.strip():
            qagent = f"--agent {shlex.quote(agent_name)}"
        else:
            qagent = ""

        qsid = shlex.quote(chat_id)
        qthinking = shlex.quote(thinking)
        qprompt_text = shlex.quote(prompt)
        qout = shlex.quote(str(output))

        cmd = (
            f"openclaw agent {qagent} --session-id {qsid} "
            f"--thinking {qthinking} --message {qprompt_text}"
        )
        if local:
            cmd = f"{cmd} --local"

        if tee:
            inner = f"set -o pipefail; {cmd} 2>&1 | tee {qout}"
        else:
            inner = f"{cmd} > {qout} 2>&1"

        kwargs_sp: dict = {
            "args": ["bash", "-c", inner],
            "cwd": str(cwd),
            "text": True,
        }
        if timeout is not None:
            kwargs_sp["timeout"] = timeout

        try:
            proc = subprocess.run(**kwargs_sp)
            rc = proc.returncode
        except subprocess.TimeoutExpired:
            rc = 124

        complete_response = (
            output.read_text(encoding="utf-8", errors="replace")
            if output.exists()
            else ""
        )
        return AgentResult(
            chat_id=chat_id,
            output_path=output,
            complete_response=complete_response,
            returncode=rc,
        )
