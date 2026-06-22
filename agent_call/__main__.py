"""Unified CLI entry point for agent_call.

Usage::

    python -m agent_call --agent jiuwenclaw -q "your prompt"
    python -m agent_call --agent openclaw -q "your prompt" --thinking medium
    python -m agent_call --agent opencode -q "your prompt" --tee
    python -m agent_call --agent opencode -q "your prompt" --model deepseek-v4-flash
    python -m agent_call --agent hermes -q "your prompt" --output-dir ./logs

Or after pip install::

    agent-call --agent jiuwenclaw -q "your prompt"
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ._runner import AgentCall, _AGENT_CLASSES, _resolve_prompt_arg


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Unified agent call — run any supported AI agent from the CLI"
    )

    # ── Agent selection ───────────────────────────────────────────
    parser.add_argument(
        "-a", "--agent",
        choices=list(_AGENT_CLASSES.keys()),
        required=True,
        help="Agent to use",
    )

    # ── Prompt (mutually exclusive) ───────────────────────────────
    g = parser.add_mutually_exclusive_group(required=True)
    g.add_argument("-q", "--prompt", help="Prompt text (or path to .txt/.md file)")
    g.add_argument("-f", "--prompt-file", help="Read prompt from file")

    # ── Common options ────────────────────────────────────────────
    parser.add_argument(
        "-t", "--timeout",
        type=float,
        default=900.0,
        metavar="SEC",
        help="Subprocess timeout in seconds (default 900)",
    )
    parser.add_argument(
        "--cwd",
        type=Path,
        default=None,
        help="Working directory for the agent (default: workspace_dir)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        metavar="PATH",
        help="Output path. Ends with / = directory (auto-named file inside); "
        "otherwise = full file path.",
    )
    parser.add_argument(
        "--chat-id",
        default=None,
        help="Chat ID (default: auto-generated MMdd-HHmmss)",
    )
    parser.add_argument(
        "--tee",
        action="store_true",
        help="Stream agent output to terminal while writing to file",
    )
    parser.add_argument(
        "--workspace-dir",
        type=Path,
        default=None,
        help="Workspace root directory (default ./agent_call_workspace); "
        "for openclaw this is also the native workspace",
    )

    # ── Agent-specific options ────────────────────────────────────
    parser.add_argument(
        "--reset-workspace",
        action="store_true",
        default=True,
        help="Reset agent workspace before execution (default True; jiuwenclaw, openclaw)",
    )
    parser.add_argument(
        "--no-reset-workspace",
        action="store_false",
        dest="reset_workspace",
        help="Do not reset workspace",
    )
    parser.add_argument(
        "--command",
        default="jiuwenclaw-tui",
        metavar="CMD",
        help="jiuwenclaw TUI command (default: jiuwenclaw-tui)",
    )
    parser.add_argument(
        "--agent-name",
        default="agentcall",
        metavar="NAME",
        help="openclaw agent name (default: agentcall)",
    )
    parser.add_argument(
        "--thinking",
        choices=(
            "off", "minimal", "low", "medium", "high", "xhigh", "adaptive", "max",
        ),
        default="medium",
        help="openclaw thinking level (default: medium)",
    )
    parser.add_argument(
        "--local",
        action="store_true",
        default=True,
        help="openclaw: use --local (default True)",
    )
    parser.add_argument(
        "--no-local",
        action="store_false",
        dest="local",
        help="openclaw: do not use --local",
    )
    parser.add_argument(
        "--model",
        default=None,
        metavar="MODEL",
        help="opencode / simple: model name to use (e.g. deepseek-v4-flash)",
    )
    parser.add_argument(
        "--login-shell",
        action="store_true",
        help="hermes: use bash -lc instead of bash -c",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        metavar="DIR",
        help="hermes: output directory for temp and parsed files "
        "(default ./hermes_output_logs/)",
    )

    args = parser.parse_args()

    # ── Warn about irrelevant agent-specific flags ──────────────────
    _cli_warnings: list[str] = []
    if args.agent != "jiuwenclaw":
        if args.command != "jiuwenclaw-tui":
            _cli_warnings.append("--command 仅在 jiuwenclaw agent 时有效")
    if args.agent != "openclaw":
        if args.agent_name != "agentcall":
            _cli_warnings.append("--agent-name 仅在 openclaw agent 时有效")
        if args.thinking != "medium":
            _cli_warnings.append("--thinking 仅在 openclaw agent 时有效")
        if not args.local:  # --no-local was explicitly used
            _cli_warnings.append("--no-local 仅在 openclaw agent 时有效")
    if args.agent != "hermes":
        if args.login_shell:
            _cli_warnings.append("--login-shell 仅在 hermes agent 时有效")
    if args.agent not in ("opencode", "simple"):
        if args.model is not None:
            _cli_warnings.append("--model 仅在 opencode / simple agent 时有效")
    for w in _cli_warnings:
        print(f"Warning: {w}", file=sys.stderr)

    # ── Resolve prompt ────────────────────────────────────────────
    try:
        if args.prompt:
            prompt_text = _resolve_prompt_arg(args.prompt)
        else:
            prompt_text = Path(args.prompt_file).read_text(encoding="utf-8")
    except (OSError, UnicodeError) as e:
        print(f"Error reading prompt: {e}", file=sys.stderr)
        return 1

    # ── Build agent kwargs ────────────────────────────────────────
    agent_kwargs = {}
    if args.agent == "jiuwenclaw":
        agent_kwargs["command"] = args.command
    elif args.agent == "openclaw":
        agent_kwargs["agent_name"] = args.agent_name
        agent_kwargs["thinking"] = args.thinking
        agent_kwargs["local"] = args.local
    elif args.agent == "hermes":
        agent_kwargs["login_shell"] = args.login_shell

    if args.agent in ("opencode", "simple") and args.model is not None:
        agent_kwargs["model"] = args.model

    # ── Build run kwargs ──────────────────────────────────────────
    run_kwargs = {
        "timeout": args.timeout,
        "tee": args.tee,
        "reset_workspace": args.reset_workspace,
    }
    if args.cwd is not None:
        run_kwargs["cwd"] = args.cwd
    if args.output is not None:
        run_kwargs["output"] = args.output
    if args.chat_id is not None:
        run_kwargs["chat_id"] = args.chat_id

    # hermes uses its own output_dir logic; pass as base_dir in kwargs
    if args.agent == "hermes" and args.output_dir is not None:
        agent_kwargs["output_dir"] = args.output_dir

    # ── Execute ──────────────────────────────────────────────────
    try:
        result = AgentCall.run_once(
            agent=args.agent,
            prompt=prompt_text,
            workspace_dir=args.workspace_dir,
            **run_kwargs,
            **agent_kwargs,
        )
    except FileNotFoundError as e:
        fn = getattr(e, "filename", None)
        if fn == "bash" or (isinstance(fn, str) and fn.endswith("bash")):
            print("未找到 bash", file=sys.stderr)
            return 127
        if fn and ("hermes" in str(fn) or "openclaw" in str(fn) or "opencode" in str(fn)):
            print(f"未找到 {args.agent} 命令，请确认已安装并在 PATH 中", file=sys.stderr)
            return 127
        print(e, file=sys.stderr)
        return 1
    except Exception as e:
        print(e, file=sys.stderr)
        return 1

    # ── Report ───────────────────────────────────────────────────
    print(f"agent={args.agent}")
    print(f"chat_id={result.chat_id}")
    print(f"output={result.output_path}")
    print(f"returncode={result.returncode}")
    if result.returncode == 124:
        print("注意：子进程已超时，输出可能不完整", file=sys.stderr)
    if result.returncode == 127:
        print(
            "提示：127 通常表示子 shell 内未找到命令。"
            "当前使用 `bash -c`，PATH 继承自启动 Python 的进程；"
            f"若 `{args.agent}` 仅在 ~/.bashrc 中配置，请把 PATH 写入 "
            "~/.profile / ~/.bash_profile，"
            "或确认其为真实可执行文件而非仅 alias/函数。",
            file=sys.stderr,
        )
    return 0 if result.returncode == 0 else result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
