"""Shared utilities for agent_call package."""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Optional


def resolve_prompt(
    prompt: Optional[str] = None,
    prompt_file: Optional[str | Path] = None,
) -> str:
    """Resolve prompt text from direct string or file.

    Exactly one of *prompt* or *prompt_file* must be provided.
    """
    if prompt_file is not None:
        return Path(prompt_file).read_text(encoding="utf-8")
    if prompt is not None:
        return prompt
    raise ValueError("必须提供 prompt 文本或 prompt_file")


def make_chat_id(now: Optional[datetime] = None) -> str:
    """Generate a chat ID in ``MMdd-HHmmss`` format."""
    return (now or datetime.now()).strftime("%m%d-%H%M%S")


def replace_placeholders(template: str, **kwargs: str) -> str:
    """Replace all ``<key>`` placeholders in *template* with *kwargs* values.

    Example::

        >>> replace_placeholders("hello <name>, age <age>", name="Alice", age="30")
        'hello Alice, age 30'
    """
    result = template
    for key, value in kwargs.items():
        result = result.replace(f"<{key}>", str(value))
    return result


def resolve_output_path(
    output: str | Path | None,
    chat_id: str,
    *,
    filename_template: str = "{chat_id}_output.txt",
    base_dir: Optional[Path] = None,
) -> Path:
    """Resolve the output file path from an output spec and chat_id.

    Parameters
    ----------
    output :
        - ``None`` → write to ``{base_dir}/{filename_template}``
        - Ends with ``/`` or ``os.sep`` → treated as a directory; file named by
          *filename_template* inside it
        - Otherwise → treated as a complete file path
    chat_id :
        Used to format *filename_template* when *output* is a directory or None.
    filename_template :
        Template string for the filename. Must contain ``{chat_id}``.
        Default: ``"{chat_id}_output.txt"``.
    base_dir :
        Base directory for default output and relative path resolution.
        Default: ``Path.cwd()``.
    """
    base = Path(base_dir) if base_dir is not None else Path.cwd()
    named = filename_template.format(chat_id=chat_id)

    if output is None:
        return (base / named).resolve()

    s = str(output).strip()
    if s.endswith("/") or s.endswith(os.sep):
        dirpath = Path(s.rstrip("/" + os.sep)).expanduser()
        if not dirpath.is_absolute():
            dirpath = base / dirpath
        return (dirpath / named).resolve()

    p = Path(s).expanduser()
    if not p.is_absolute():
        p = base / p
    return p.resolve()
