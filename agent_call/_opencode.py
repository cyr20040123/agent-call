"""Opencode agent — wraps the ``opencode run`` CLI."""

from __future__ import annotations

import shlex
import subprocess
from pathlib import Path

from ._base import AgentResult, BaseAgent


class OpencodeAgent(BaseAgent):
    """Agent that runs ``opencode run`` via subprocess."""

    name = "opencode"
    output_filename_template = "{chat_id}_opencode_output.txt"
    _supported_kwargs = frozenset({"model"})

    def execute(
        self,
        prompt: str,
        *,
        cwd: Path,
        output: Path,
        chat_id: str,
        timeout: float | None = None,
        tee: bool = False,
        model: str | None = None,
        **kwargs,
    ) -> AgentResult:
        output.parent.mkdir(parents=True, exist_ok=True)

        qtext = shlex.quote(prompt)
        qout = shlex.quote(str(output))

        model_flag = f"--model {shlex.quote(model)} " if model else ""

        if tee:
            inner = f"set -o pipefail; opencode run {model_flag}{qtext} 2>&1 | tee {qout}"
        else:
            inner = f"opencode run {model_flag}{qtext} > {qout} 2>&1"

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
