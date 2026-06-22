"""AgentCall — unified facade for all supported agents."""

from __future__ import annotations

import warnings
from pathlib import Path
from typing import Any, Optional, Type

from ._base import AgentResult, BaseAgent
from ._common import make_chat_id, resolve_output_path, resolve_prompt
from ._dry import DryAgent
from ._hermes import HermesAgent
from ._jiuwenclaw import JiuwenclawAgent
from ._openclaw import OpenclawAgent
from ._opencode import OpencodeAgent
from ._simple import SimpleAgent

# ── Agent registry ───────────────────────────────────────────────────

_AGENT_CLASSES: dict[str, Type[BaseAgent]] = {
    "dry": DryAgent,
    "simple": SimpleAgent,
    "jiuwenclaw": JiuwenclawAgent,
    "openclaw": OpenclawAgent,
    "opencode": OpencodeAgent,
    "hermes": HermesAgent,
}


def get_available_agents() -> list[str]:
    """Return the list of supported agent names."""
    return list(_AGENT_CLASSES.keys())


def _resolve_prompt_arg(prompt_arg: str) -> str:
    """If *prompt_arg* points to an existing .txt/.md file, read it; else return as-is."""
    p = Path(prompt_arg)
    if p.exists() and p.suffix in (".txt", ".md"):
        return p.read_text(encoding="utf-8")
    return prompt_arg


# ── AgentCall ────────────────────────────────────────────────────────


class AgentCall:
    """Unified interface for calling various AI agents.

    Supports context-manager protocol for setup/teardown::

        with AgentCall(agent="jiuwenclaw", workspace_dir=Path("./runs")) as ac:
            result = ac.run(prompt="do something")
            print(result.complete_response)

    For one-shot calls::

        result = AgentCall.run_once(agent="opencode", prompt="echo hello")
    """

    def __init__(
        self,
        agent: str,
        *,
        workspace_dir: Optional[Path] = None,
        **agent_kwargs,
    ):
        """Create an AgentCall instance.

        Parameters
        ----------
        agent :
            Agent name: ``"jiuwenclaw"`` / ``"openclaw"`` / ``"opencode"`` / ``"hermes"``.
        workspace_dir :
            Root directory for agent output and workspace. Default: ``./agent_call_workspace``.
            For openclaw, this directory is registered as the native workspace.
        **agent_kwargs :
            Agent-specific keyword arguments forwarded to ``run()``
            (e.g. ``agent_name="agentcall"``, ``thinking="medium"`` for openclaw).
        """
        agent_cls = _AGENT_CLASSES.get(agent)
        if agent_cls is None:
            raise ValueError(
                f"Unknown agent: {agent!r}. Available: {get_available_agents()}"
            )

        self._agent_name = agent
        self._agent_instance = agent_cls()
        self._agent_kwargs = agent_kwargs

        # Warn about kwargs not supported by this agent
        unsupported = set(agent_kwargs) - set(self._agent_instance._supported_kwargs)
        if unsupported:
            for kw in sorted(unsupported):
                warnings.warn(
                    f"kwarg {kw!r} is not supported by agent {agent!r} "
                    f"(only effective for: {sorted(self._agent_instance._supported_kwargs)})",
                    stacklevel=2,
                )
        self._workspace_dir = (
            workspace_dir.expanduser().resolve()
            if workspace_dir is not None
            else Path.cwd() / "agent_call_workspace"
        )

        # Initialize agent workspace
        if self._agent_instance.needs_init():
            agent_name = agent_kwargs.get("agent_name", "agentcall")
            self._out_root = self._agent_instance.init(
                output_dir=self._workspace_dir,
                agent_name=agent_name,
            )
        else:
            self._out_root = self._workspace_dir
            self._out_root.mkdir(parents=True, exist_ok=True)

    # ── properties ────────────────────────────────────────────────

    @property
    def agent_name(self) -> str:
        """The agent identifier string."""
        return self._agent_name

    @property
    def out_root(self) -> Path:
        """Resolved output root directory."""
        return self._out_root

    @property
    def workspace_dir(self) -> Path:
        """Workspace directory."""
        return self._workspace_dir

    # ── run ───────────────────────────────────────────────────────

    def run(
        self,
        prompt: Optional[str] = None,
        *,
        prompt_file: Optional[str | Path] = None,
        chat_id: Optional[str] = None,
        timeout: float = 900.0,
        cwd: Optional[Path] = None,
        output: str | Path | None = None,
        tee: bool = False,
        reset_workspace: bool = True,
        **kwargs,
    ) -> AgentResult:
        """Execute one agent call.

        Parameters
        ----------
        prompt :
            Prompt text. Mutually exclusive with *prompt_file*.
        prompt_file :
            Read prompt from this file. Mutually exclusive with *prompt*.
        chat_id :
            Chat identifier (default: auto-generated ``MMdd-HHmmss``).
        timeout :
            Subprocess timeout in seconds (default 900).
        cwd :
            Working directory for the agent. Default: *out_root*.
        output :
            Output path spec. Directory (ends with ``/``) or full file path.
            Default: ``{cwd}/{chat_id}_<agent>_output.txt``.
        tee :
            If True, also stream agent output to the terminal.
        reset_workspace :
            If True (default), reset the agent workspace before execution.
        **kwargs :
            Additional agent-specific arguments (overrides constructor kwargs).

        Returns
        -------
        AgentResult
        """
        # Merge constructor kwargs with per-call kwargs (call wins)
        merged_kwargs: dict[str, Any] = {**self._agent_kwargs, **kwargs}

        # Warn about per-call kwargs not supported by this agent
        unsupported = set(kwargs) - set(self._agent_instance._supported_kwargs)
        if unsupported:
            for kw in sorted(unsupported):
                warnings.warn(
                    f"kwarg {kw!r} is not supported by agent {self._agent_name!r} "
                    f"(only effective for: {sorted(self._agent_instance._supported_kwargs)})",
                    stacklevel=2,
                )

        # Resolve prompt
        text = resolve_prompt(prompt, prompt_file)

        # Resolve chat_id
        cid = chat_id or make_chat_id()

        # Resolve cwd
        if cwd is None:
            cwd = self._out_root
        cwd = Path(cwd).expanduser().resolve()
        cwd.mkdir(parents=True, exist_ok=True)

        # Resolve output path (relative to cwd, uses agent's own filename template)
        out_path = resolve_output_path(
            output, cid,
            filename_template=self._agent_instance.output_filename_template,
            base_dir=cwd,
        )

        # Execute
        return self._agent_instance.execute(
            text,
            cwd=cwd,
            output=out_path,
            chat_id=cid,
            timeout=timeout,
            tee=tee,
            reset_workspace=reset_workspace,
            **merged_kwargs,
        )

    # ── convenience ───────────────────────────────────────────────

    @classmethod
    def run_once(
        cls,
        agent: str,
        prompt: Optional[str] = None,
        *,
        prompt_file: Optional[str | Path] = None,
        workspace_dir: Optional[Path] = None,
        **kwargs,
    ) -> AgentResult:
        """One-shot agent call.

        Parameters are the same as ``AgentCall(agent, ...).run(prompt, ...)``.
        """
        instance = cls(
            agent=agent,
            workspace_dir=workspace_dir,
        )
        return instance.run(prompt=prompt, prompt_file=prompt_file, **kwargs)

    # ── context manager ───────────────────────────────────────────

    def __enter__(self) -> "AgentCall":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        return None

    def __repr__(self) -> str:
        return (
            f"AgentCall(agent={self._agent_name!r}, "
            f"workspace_dir={self._workspace_dir!r})"
        )
