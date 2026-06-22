"""Hermes agent — wraps the ``hermes chat`` CLI tool."""

from __future__ import annotations

import shlex
import subprocess
from pathlib import Path
from typing import Optional

from ._base import AgentResult, BaseAgent

# ── Hermes TUI output parsing constants ──────────────────────────────
HERMES_BOX_TOP = "╭─ ⚕ Hermes ─"
HERMES_BOX_BOTTOM = "╰────────"
RESUME_PREFIX = "Resume this session with:"
NOUS_RESEARCH = "· Nous Research"
QUERY_MARK = "\nQuery: "
QUERY_MARK_ALT = "Query: "
INIT_MARK = "\nInitializing"

# ── Output section headers ───────────────────────────────────────────
OUTPUT_SECTION_MODEL = "=== model ==="
OUTPUT_SECTION_QUERY = "=== query ==="
OUTPUT_SECTION_LAST_RESPONSE = "=== last_response ==="
OUTPUT_SECTION_SESSION = "=== session_summary ==="


def _extract_model(text: str) -> str:
    i = text.find(NOUS_RESEARCH)
    if i == -1:
        return ""
    j = text.rfind("│", 0, i)
    if j == -1:
        return ""
    return text[j + 1 : i].strip()


def _extract_query(text: str) -> str:
    i = text.find(QUERY_MARK)
    if i == -1:
        i = text.find(QUERY_MARK_ALT)
        if i == -1:
            return ""
        start = i + len(QUERY_MARK_ALT)
    else:
        start = i + len(QUERY_MARK)
    j = text.find(INIT_MARK, start)
    if j == -1:
        return text[start:].strip()
    return text[start:j].strip()


def _extract_last_response(text: str) -> str:
    lines = text.splitlines()
    top_idxs = [i for i, ln in enumerate(lines) if HERMES_BOX_TOP in ln]
    bottom_idxs = [i for i, ln in enumerate(lines) if HERMES_BOX_BOTTOM in ln]
    if not top_idxs or not bottom_idxs:
        return ""
    start = top_idxs[-1]
    after = [i for i in bottom_idxs if i > start]
    if not after:
        return ""
    end = after[-1]
    return "\n".join(lines[start + 1 : end])


def _extract_session_summary(text: str) -> str:
    lines = text.splitlines()
    resume_idxs = [i for i, ln in enumerate(lines) if RESUME_PREFIX in ln]
    if not resume_idxs:
        return ""
    r = resume_idxs[-1]
    return "\n".join(lines[r:])


def _parse_hermes_raw_output(text: str) -> tuple[str, str, str, str]:
    return (
        _extract_model(text),
        _extract_query(text),
        _extract_last_response(text),
        _extract_session_summary(text),
    )


def _format_parsed_output(
    model: str, query: str, last_response: str, session_summary: str
) -> str:
    parts = [
        OUTPUT_SECTION_MODEL, model, "",
        OUTPUT_SECTION_QUERY, query, "",
        OUTPUT_SECTION_LAST_RESPONSE, last_response, "",
        OUTPUT_SECTION_SESSION, session_summary,
    ]
    return "\n".join(parts) + "\n"


class HermesAgent(BaseAgent):
    """Agent that runs ``hermes chat`` via subprocess and parses the TUI output."""

    name = "hermes"
    output_filename_template = "{chat_id}_hermes_f_output.txt"
    _supported_kwargs = frozenset({"login_shell"})

    def execute(
        self,
        prompt: str,
        *,
        cwd: Path,
        output: Path,
        chat_id: str,
        timeout: float = 600.0,
        tee: bool = False,
        login_shell: bool = False,
        **kwargs,
    ) -> AgentResult:
        """Run ``hermes chat`` and write parsed output.

        Parameters
        ----------
        login_shell :
            If True, use ``bash -lc`` instead of ``bash -c`` (for login-shell PATH).
        """
        # output is the *parsed* output path; temp goes alongside it
        temp_path = output.with_name(f"{chat_id}_hermes_output.txt")
        qtext = shlex.quote(prompt)
        qtmp = shlex.quote(str(temp_path))

        if tee:
            inner = (
                f"set -o pipefail; hermes chat -q {qtext} 2>&1 | tee {qtmp}"
            )
        else:
            inner = f"hermes chat -q {qtext} > {qtmp}"

        try:
            proc = subprocess.run(
                ["bash", "-lc" if login_shell else "-c", inner],
                cwd=str(cwd),
                timeout=timeout,
                text=True,
            )
            rc = proc.returncode
        except subprocess.TimeoutExpired:
            rc = 124

        raw = (
            temp_path.read_text(encoding="utf-8", errors="replace")
            if temp_path.exists()
            else ""
        )
        model, query, last_response, session_summary = _parse_hermes_raw_output(raw)
        output.write_text(
            _format_parsed_output(model, query, last_response, session_summary),
            encoding="utf-8",
        )

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
