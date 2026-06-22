"""Jiuwenclaw agent — pexpect-based TUI automation for ``jiuwenclaw-tui``."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Optional

import pexpect

from ._base import AgentResult, BaseAgent

# ── Logging ──────────────────────────────────────────────────────────

_LOG_NAME = "jiuwenclaw_chat_log"


def _get_module_logger() -> logging.Logger:
    """Independent logger: does not propagate to root, avoiding interference."""
    log = logging.getLogger(_LOG_NAME)
    log.setLevel(logging.INFO)
    if not log.handlers:
        # Write log to current working directory (writable even when pip-installed)
        path = os.path.join(os.getcwd(), "jiuwenclaw_chat.log")
        fh = logging.FileHandler(path, encoding="utf-8")
        fh.setFormatter(
            logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
        )
        log.addHandler(fh)
        log.propagate = False
    return log


_m_logger = _get_module_logger()


# ── Tee helper ───────────────────────────────────────────────────────


class _Tee:
    """Write to multiple file objects simultaneously."""

    def __init__(self, *files):
        self.files = files

    def write(self, data):
        for f in self.files:
            f.write(data)
            f.flush()

    def flush(self):
        for f in self.files:
            f.flush()


# ── Log post-processing ──────────────────────────────────────────────


def _post_process_interaction_log(log_file_path: str | os.PathLike[str]) -> str:
    """Strip ANSI escape codes and TUI boilerplate from the interaction log."""
    with open(log_file_path, "r", encoding="utf-8") as file:
        log_content = file.read()

    remove_pattern = [
        "\x1b[38;2;255;255;255m",
        "\x1b[38;2;136;136;136m─",
        "\x1b[?2026l\x1b[4B\x1b[2G\x1b[?25l\x1b[?2026h\x1b[4A",
        "\x1b[?2026l\x1b[4B\x1b[2G\x1b[?25l\x1b[?2026h\x1b[2B",
        "\x1b[?25h\x1b[?2004l\x1b[>4;0m",
        "\x1b[?2026l\x1b[2A\x1b[2G\x1b[?25l",
        "\x1b[39m",
        "\x1b[0m",
        "\x1b]8;;\x07",
        "\x1b[2K",
    ]
    for pattern in remove_pattern:
        log_content = log_content.replace(pattern, "")

    line_pattern_to_remove = [
        "esc to interrupt",
        "JIUWEN CLAW",
        " | mode:",
        " | Mode:",
    ]
    lines = log_content.split("\n")
    new_lines = []
    n_lines_to_remove = 0
    for line in lines:
        if any(pattern in line for pattern in line_pattern_to_remove):
            n_lines_to_remove += 1
            continue
        new_lines.append(line)

    log_content = "\n".join(new_lines)
    for _ in range(3):
        log_content = log_content.replace("\n\n", "\n")

    with open(log_file_path, "w", encoding="utf-8") as file:
        file.write(log_content)
    return log_content


def _just_wait(child, sec: float) -> None:
    """Wait using pexpect timeout (interruptible, unlike time.sleep)."""
    child.expect(pexpect.TIMEOUT, timeout=sec)


# ── Core interaction ─────────────────────────────────────────────────


def _interact_with_jiuwenclaw(
    input_string: str,
    *,
    interaction_log_file: str | os.PathLike[str] = "jiuwenclaw_interaction.log",
    cwd: str | os.PathLike[str] | None = None,
    timeout: float = 600,
    tee: bool = True,
    session_id: str | None = None,
    command: str = "jiuwenclaw-tui",
    reset_workspace: bool = False,
) -> Optional[str]:
    """Low-level pexpect automation of ``jiuwenclaw-tui``.

    Returns the captured output before exit, or None on timeout/EOF.
    """
    cwd_path = Path(cwd).expanduser().resolve() if cwd is not None else None
    cmd = f"{command} --session {session_id}" if session_id else command

    child = pexpect.spawn(
        cmd,
        cwd=str(cwd_path) if cwd_path is not None else None,
        encoding="utf-8",
        timeout=timeout,
    )
    child.linesep = "\r\n"

    log_path = Path(interaction_log_file).expanduser()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_file = open(log_path, "w", encoding="utf-8")
    child.logfile = _Tee(sys.stdout, log_file) if tee else log_file

    try:
        _m_logger.info(
            "\n==================================================\n"
            "请求内容：%s\n"
            "==================================================",
            input_string,
        )
        _m_logger.info("等待工具启动完成")
        child.expect("https://gitcode.com/openJiuwen/agent-core", timeout=30)

        _m_logger.info("等待2秒后按回车（确认workspace）")
        _just_wait(child, 2)
        child.sendline("")

        if reset_workspace:
            _m_logger.info("检测到重置工作目录指令")
            assert cwd_path is not None, "重置工作目录需要提供 cwd 参数"
            child.sendline(f"/workspace set {cwd_path}")
            _just_wait(child, 3)
            child.sendline("")

        _m_logger.info("等待2秒后发送请求")
        _just_wait(child, 2)
        child.sendline(input_string)
        child.sendline("")

        WAIT_INTERVAL = 5
        NO_RESPONSE_TIME = 20
        for _ in range(int(timeout / WAIT_INTERVAL)):
            _just_wait(child, WAIT_INTERVAL)
            idx = child.expect(
                ["esc to interrupt", "Enter confirm", pexpect.TIMEOUT],
                timeout=NO_RESPONSE_TIME,
            )
            if idx == 2:
                _m_logger.info("循环等待超时退出，一定时间内无刷新")
                break
            if idx == 0:
                _m_logger.info("运行中，等待%ds", WAIT_INTERVAL)
                while idx == 0:
                    idx = child.expect(
                        ["esc to interrupt", "Enter confirm", pexpect.TIMEOUT],
                        timeout=2,
                    )
            if idx == 1:
                _m_logger.info("检测到提示确认信号")
                _just_wait(child, 1)
                child.sendline("")
                _just_wait(child, 1)
                child.sendline("")
                continue

        idx = child.expect(
            [
                "mode:code.normal",
                "────────────────────────────────────────",
                pexpect.TIMEOUT,
            ],
            timeout=20,
        )
        _m_logger.info("捕捉到结束信号[%d]", idx)

        _m_logger.info("发送退出命令")
        child.sendline("/exit")
        idx = child.expect([pexpect.TIMEOUT, pexpect.EOF], timeout=10)
        if idx == 0:
            _m_logger.info("超时退出")
        elif idx == 1:
            _m_logger.info("EOF退出")
        return child.before

    except pexpect.TIMEOUT:
        _m_logger.error("错误：等待超时，工具可能没有按预期响应")
        return None
    except pexpect.EOF:
        _m_logger.error("工具意外退出")
        return child.before
    finally:
        child.close()
        log_file.close()
        _post_process_interaction_log(log_path)


# ── Agent class ──────────────────────────────────────────────────────


class JiuwenclawAgent(BaseAgent):
    """Agent that automates ``jiuwenclaw-tui`` via pexpect."""

    name = "jiuwenclaw"
    output_filename_template = "{chat_id}_jiuwenclaw_output.txt"
    _supported_kwargs = frozenset({"command", "reset_workspace"})

    def execute(
        self,
        prompt: str,
        *,
        cwd: Path,
        output: Path,
        chat_id: str,
        timeout: float = 600.0,
        tee: bool = False,
        command: str = "jiuwenclaw-tui",
        reset_workspace: bool = False,
        **kwargs,
    ) -> AgentResult:
        output.parent.mkdir(parents=True, exist_ok=True)

        result = _interact_with_jiuwenclaw(
            prompt,
            interaction_log_file=output,
            cwd=cwd,
            timeout=timeout,
            tee=tee,
            session_id=chat_id,
            command=command,
            reset_workspace=reset_workspace,
        )

        complete_response = (
            output.read_text(encoding="utf-8", errors="replace")
            if output.exists()
            else (result or "")
        )
        returncode = 0 if result is not None else 124

        return AgentResult(
            chat_id=chat_id,
            output_path=output,
            complete_response=complete_response,
            returncode=returncode,
        )
