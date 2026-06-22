"""Base classes for agent implementations."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class AgentResult:
    """Result from a single agent execution."""

    chat_id: str
    """Unique identifier for this chat run (MMdd-HHmmss format)."""

    output_path: Path
    """Path to the output file containing the agent's response."""

    complete_response: str
    """Full text of the agent's response (read from *output_path*)."""

    returncode: int
    """Exit code from the underlying subprocess. 0 = success, 124 = timeout."""

    # Agent-specific extra fields (e.g. session_id for openclaw)
    extra: dict = field(default_factory=dict)


class BaseAgent(ABC):
    """Abstract base for all agent implementations.

    Subclasses must set ``name`` and implement ``execute()``.
    They may override ``init()`` and ``needs_init()`` for workspace setup.
    """

    #: Human-readable agent identifier ("jiuwenclaw", "openclaw", etc.)
    name: str = "base"

    #: Output filename template used by the runner.
    #: Must contain ``{chat_id}``.  Override in subclasses as needed.
    output_filename_template: str = "{chat_id}_output.txt"

    #: Set of keyword argument names this agent accepts in ``execute()``.
    #: Used to warn when irrelevant kwargs are passed via the API or CLI.
    _supported_kwargs: frozenset[str] = frozenset()

    @abstractmethod
    def execute(
        self,
        prompt: str,
        *,
        cwd: Path,
        output: Path,
        chat_id: str,
        timeout: float,
        tee: bool,
        **kwargs,
    ) -> AgentResult:
        """Execute the agent with the given prompt.

        Parameters
        ----------
        prompt :
            The prompt text to send to the agent.
        cwd :
            Working directory for the agent subprocess.
        output :
            Full output file path (already resolved).
        chat_id :
            Chat identifier string.
        timeout :
            Subprocess timeout in seconds.
        tee :
            If True, also print agent output to the terminal.
        **kwargs :
            Agent-specific keyword arguments.

        Returns
        -------
        AgentResult
        """
        ...

    def init(
        self,
        output_dir: Path,
        **kwargs,
    ) -> Path:
        """Initialize agent workspace, returning the resolved output root.

        The default implementation creates *output_dir* and returns its
        resolved absolute path. Override for agents that need special
        workspace setup (e.g. openclaw).

        Parameters
        ----------
        output_dir :
            User-requested output directory, also used as the agent's
            workspace root when applicable (openclaw).
        **kwargs :
            Additional agent-specific init parameters.
        """
        out_root = output_dir.expanduser().resolve()
        out_root.mkdir(parents=True, exist_ok=True)
        return out_root

    @staticmethod
    def needs_init() -> bool:
        """Return True if this agent needs explicit ``init()`` before use."""
        return False
