"""Simple agent — direct OpenAI-compatible HTTP chat completion."""

from __future__ import annotations

import configparser
import json
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError

from ._base import AgentResult, BaseAgent

DEFAULT_CONFIG = "simple_agent_config.ini"
DEFAULT_MODEL = "deepseek-v4-flash"


def _read_config(config_path: str) -> tuple[str, str, str]:
    """Read base-url, api-key, model from a simple INI config file.

    Returns ``(base_url, api_key, model)``.
    """
    cp = configparser.ConfigParser()
    cp.read(config_path, encoding="utf-8")

    base_url = cp.get("DEFAULT", "base-url", fallback="https://api.deepseek.com")
    api_key = cp.get("DEFAULT", "api-key", fallback="")
    model = cp.get("DEFAULT", "model", fallback=DEFAULT_MODEL)

    # Strip trailing slash from base_url for clean /v1/... concatenation
    base_url = base_url.rstrip("/")
    return base_url, api_key, model


class SimpleAgent(BaseAgent):
    """Agent that sends a single OpenAI-compatible chat completion request.

    Configuration is read from ``simple_agent_config.ini`` in the current
    working directory (configurable via the *config* kwarg).

    Example config file::

        [DEFAULT]
        base-url = https://api.deepseek.com
        api-key = sk-xxxxxxxxxxxxxxxxxxxxxxxx
        model = deepseek-v4-flash
    """

    name = "simple"
    output_filename_template = "{chat_id}_simple_output.txt"
    _supported_kwargs = frozenset({"config", "model"})

    def execute(
        self,
        prompt: str,
        *,
        cwd: Path,
        output: Path,
        chat_id: str,
        timeout: float = 900.0,
        tee: bool = False,
        config: str = DEFAULT_CONFIG,
        model: str | None = None,
        **kwargs,
    ) -> AgentResult:
        output.parent.mkdir(parents=True, exist_ok=True)

        # Resolve config path relative to cwd if not absolute
        config_path = Path(config)
        if not config_path.is_absolute():
            config_path = Path.cwd() / config_path
        config_path = config_path.expanduser()

        if not config_path.exists():
            raise FileNotFoundError(
                f"Simple agent config not found: {config_path}\n"
                f"Create it with [DEFAULT] section containing base-url and api-key."
            )

        base_url, api_key, cfg_model = _read_config(str(config_path))
        if model is None:
            model = cfg_model

        # Build OpenAI-format request body
        body = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
        }
        body_bytes = json.dumps(body).encode("utf-8")

        url = f"{base_url}/v1/chat/completions"
        req = Request(
            url,
            data=body_bytes,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            method="POST",
        )

        if tee:
            print(f"[simple] POST {url}")
            print(f"[simple] model={model}")

        try:
            with urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8")
            rc = 0
        except URLError as e:
            raw = json.dumps({"error": str(e)})
            rc = 1
        except Exception as e:
            raw = json.dumps({"error": str(e)})
            rc = 1

        # Extract content from OpenAI response
        try:
            data = json.loads(raw)
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, json.JSONDecodeError):
            content = raw

        output.write_text(content, encoding="utf-8")

        return AgentResult(
            chat_id=chat_id,
            output_path=output,
            complete_response=content,
            returncode=rc,
        )
