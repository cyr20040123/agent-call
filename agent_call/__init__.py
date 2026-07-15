"""agent_call — Unified CLI and Python API for AI agent chat tools.

Supported agents: jiuwenclaw, openclaw, opencode, hermes.

Quick start::

    from agent_call import AgentCall

    # One-shot call
    result = AgentCall.run_once("opencode", prompt="echo hello")
    print(result.complete_response)

    # With workspace setup (context manager)
    with AgentCall("jiuwenclaw", workspace_dir="./runs") as ac:
        result = ac.run(prompt="summarize meeting notes")
"""

from ._base import AgentResult, BaseAgent
from ._dry import DryAgent
from ._hermes import HermesAgent
from ._simple import SimpleAgent
from ._jiuwenclaw import JiuwenclawAgent
from ._openclaw import OpenclawAgent
from ._opencode import OpencodeAgent
from ._common import replace_placeholders
from ._runner import AgentCall, get_available_agents
from .swarm_runner import SwarmRunner

__all__ = [
    "AgentCall",
    "AgentResult",
    "BaseAgent",
    "get_available_agents",
    # Agent classes (for advanced/subclassing use)
    "DryAgent",
    "SimpleAgent",
    "HermesAgent",
    "JiuwenclawAgent",
    "OpenclawAgent",
    "OpencodeAgent",
    # Swarm runner
    "SwarmRunner",
    "replace_placeholders",
]
