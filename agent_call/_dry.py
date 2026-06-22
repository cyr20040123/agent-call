"""Dry-run agent — prints the prompt and returns an empty result."""

from __future__ import annotations

from pathlib import Path

from ._base import AgentResult, BaseAgent


class DryAgent(BaseAgent):
    """No-op agent that prints the prompt and returns immediately.

    Useful for testing pipeline setup, validating prompt construction,
    or checking output path resolution without actually calling an agent.
    """

    name = "dry"
    output_filename_template = "{chat_id}_dry_output.txt"

    def execute(
        self,
        prompt: str,
        *,
        cwd: Path,
        output: Path,
        chat_id: str,
        timeout: float = 900.0,
        tee: bool = False,
        **kwargs,
    ) -> AgentResult:
        output.parent.mkdir(parents=True, exist_ok=True)

        output.write_text(prompt, encoding="utf-8")

        print(f"[dry] agent={self.name}  chat_id={chat_id}")
        print(f"[dry] cwd={cwd}")
        print(f"[dry] output={output}")
        print(f"[dry] --- prompt ---")
        print(prompt)

        return AgentResult(
            chat_id=chat_id,
            output_path=output,
            complete_response=prompt,
            returncode=0,
        )
