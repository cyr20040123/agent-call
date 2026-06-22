# agent-call

Unified CLI and Python API for AI agent chat tools. Call any supported agent through a single interface — consistent parameters, consistent output format, no switching cost.

## Supported agents

| Agent | Key | Backend | Requires |
|-------|-----|---------|----------|
| **Dry** | `dry` | No-op (prints prompt) | nothing |
| **Simple** | `simple` | OpenAI-compatible HTTP API (`urllib`) | `simple_agent_config.ini` |
| **Jiuwenclaw** | `jiuwenclaw` | pexpect TUI automation | `jiuwenclaw-tui` on PATH |
| **Openclaw** | `openclaw` | `openclaw agent` subprocess | `openclaw` on PATH |
| **Opencode** | `opencode` | `opencode run` subprocess | `opencode` on PATH |
| **Hermes** | `hermes` | `hermes chat` subprocess + output parsing | `hermes` on PATH |

---

## Installation

```bash
pip install -e .
```

**Requirements:** Python ≥ 3.10.  The `pexpect` dependency is only needed for the `jiuwenclaw` agent.  Each agent also needs its own CLI tool installed and available on `PATH` (see table above).

---

## Quick start

### CLI

```bash
# Pick the agent with --agent / -a
agent-call --agent opencode -q "echo hello"
agent-call --agent jiuwenclaw -q "your prompt" --tee
agent-call --agent openclaw -q "your prompt" --thinking high
agent-call --agent hermes -q "your prompt" --login-shell

# Read prompt from file
agent-call --agent opencode -f ./prompt.txt

# Custom output directory (ends with / → auto-named file inside)
agent-call --agent jiuwenclaw -q "prompt" --output ./results/

# Full output file path
agent-call --agent opencode -q "prompt" --output ./results/my_output.txt
```

`python -m agent_call` works identically when `pip install` isn't available.

### Python API — one-shot call

```python
from agent_call import AgentCall

# Simplest usage: string prompt, auto-generated paths
result = AgentCall.run_once("opencode", prompt="echo hello")
print(result.complete_response)
print(result.returncode)     # 0 = success, 124 = timeout
print(result.output_path)    # Path to the output file
```

### Python API — context manager (persistent workspace)

```python
from pathlib import Path
from agent_call import AgentCall

with AgentCall("jiuwenclaw", workspace_dir=Path("./runs")) as ac:
    result = ac.run(
        prompt="Summarize today's meeting notes.",
        timeout=600,
        tee=True,              # stream output to terminal
    )
    print(f"Output: {result.output_path}")
    print(f"Chat ID: {result.chat_id}")
```

---

## Common parameters (all agents)

These are handled at the `AgentCall` / `run()` level and forwarded to the agent backend.

### `AgentCall` constructor

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `agent` | `str` | *(required)* | Agent key: `dry`, `simple`, `jiuwenclaw`, `openclaw`, `opencode`, `hermes` |
| `workspace_dir` | `Path \| None` | `./agent_call_workspace` | Root directory for output and workspace. For `openclaw`, this directory is also registered as the native openclaw workspace. |
| `**agent_kwargs` | — | — | Agent-specific kwargs forwarded to every `run()` call (see per-agent tables below). |

### `run()` / `run_once()` common kwargs

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `prompt` | `str \| None` | — | Prompt text. Mutually exclusive with `prompt_file`. |
| `prompt_file` | `str \| Path \| None` | — | Read prompt from this file. Mutually exclusive with `prompt`. |
| `chat_id` | `str \| None` | auto `MMdd-HHmmss` | Unique identifier for this chat run. |
| `timeout` | `float` | `900.0` | Subprocess timeout in seconds. Exceeding returns `returncode=124`. |
| `cwd` | `Path \| None` | `out_root` | Working directory for the agent subprocess. |
| `output` | `str \| Path \| None` | `{cwd}/{chat_id}_<agent>_output.txt` | Output path. Ends with `/` → directory (auto-named file inside); otherwise full file path. |
| `tee` | `bool` | `False` | If `True`, stream agent output to terminal while writing to file. |
| `reset_workspace` | `bool` | `True` | If `True`, reset agent workspace before execution (currently only effective for `jiuwenclaw`). |

### `AgentResult` (return type)

```python
@dataclass
class AgentResult:
    chat_id: str           # "MMdd-HHmmss" format
    output_path: Path      # path to the output file
    complete_response: str # full response text
    returncode: int        # 0 = success, 124 = timeout, 127 = command not found
    extra: dict            # agent-specific extra data
```

---

## Agent-specific parameters

Each agent supports a different set of keyword arguments. Passing an unsupported kwarg emits a Python `UserWarning` (or a CLI warning on stderr).  The parameter tables below show what each agent supports, the default values, and what each parameter actually does.

---

### `dry` — no-op agent

Does nothing.  Prints the prompt, cwd, and output path to stdout, writes the prompt text to the output file, and returns immediately with `returncode=0`.

**Purpose:** Testing pipeline setup, validating prompt construction, checking output path resolution — without actually calling any agent.

**Agent-specific parameters:** *none* (no `_supported_kwargs`)

```python
ac = AgentCall("dry")
result = ac.run(prompt="test prompt")  # prints [dry] info, writes prompt to output
```

---

### `simple` — direct OpenAI-compatible HTTP API

Sends a single, non-streaming chat completion request to any OpenAI-compatible endpoint.  No subprocess, no external CLI dependency.  Reads credentials from an INI config file.

**Agent-specific parameters:**

| Parameter | Constructor or `run()` | CLI flag | Type | Default | Description |
|-----------|----------------------|----------|------|---------|-------------|
| `config` | `run()` only | *(Python API only)* | `str` | `"simple_agent_config.ini"` | Path to the INI config file. Resolved relative to CWD if not absolute. |
| `model` | constructor or `run()` | `--model` | `str \| None` | `None` (use config value) | Override the model name. When set, this model is sent in the API request body instead of the config file's model. |

**Config file format** (`simple_agent_config.ini`):

```ini
[DEFAULT]
base-url = https://api.deepseek.com
api-key = sk-xxxxxxxxxxxxxxxxxxxxxxxx
model = deepseek-v4-flash
```

**How it works:**
1. Reads `base-url`, `api-key`, and `model` from the INI file.
2. POSTs JSON `{"model": "...", "messages": [...], "stream": false}` to `{base-url}/v1/chat/completions`.
3. Extracts `choices[0].message.content` from the response and writes it as the output.
4. On HTTP error, writes the error as JSON to the output file and returns `returncode=1`.

```python
# Use config defaults
AgentCall.run_once("simple", prompt="hello")

# Override model in constructor (applies to all run() calls)
with AgentCall("simple", model="deepseek-v4-pro") as ac:
    ac.run(prompt="first question")

# Override model per-call
ac.run(prompt="second question", model="gpt-4o")

# Custom config path per-call
ac.run(prompt="...", config="./prod.ini")
```

---

### `jiuwenclaw` — pexpect TUI automation

Spawns `jiuwenclaw-tui` via pexpect, waits for the TUI to initialize, sends the prompt keystroke-by-keystroke, polls for the "idle" / "done" signal, then sends `/exit`.  Includes ANSI-stripping and log post-processing.

**Agent-specific parameters:**

| Parameter | Constructor or `run()` | CLI flag | Type | Default | Description |
|-----------|----------------------|----------|------|---------|-------------|
| `command` | constructor or `run()` | `--command` | `str` | `"jiuwenclaw-tui"` | TUI command to spawn. Override for custom wrappers or aliases. Used to form the spawn command: `{command} --session {chat_id}`. |
| `reset_workspace` | `run()` only | `--reset-workspace` / `--no-reset-workspace` | `bool` | `False` (default in execute) | If `True`, sends `/workspace set <cwd>` via pexpect after TUI startup to reset the workspace to the current working directory. **Note:** the CLI defaults this to `True`, while the Python `execute()` default is `False`. |

**How it works:**
1. Spawns `{command} --session {chat_id}` in the given `cwd`.
2. Waits for the magic string `https://gitcode.com/openJiuwen/agent-core` (TUI ready signal, 30s timeout).
3. Presses Enter to confirm workspace.
4. If `reset_workspace=True`, sends `/workspace set <cwd>` and waits.
5. Sends the prompt text + Enter.
6. Polls every 5 seconds for 20 seconds of idle, checking for `esc to interrupt` (still running) or `Enter confirm` (needs confirmation → auto-confirms).
7. On detecting `mode:code.normal` or the separator line, sends `/exit`.
8. Post-processes the interaction log: strips ANSI codes and TUI boilerplate lines.

**Logging:** Writes a separate pexpect interaction log to `./jiuwenclaw_chat.log` in the current working directory.

```python
with AgentCall("jiuwenclaw", command="jiuwenclaw-tui") as ac:
    ac.run(prompt="do something", reset_workspace=True)
```

---

### `openclaw` — `openclaw agent` subprocess

Wraps the `openclaw agent` CLI via `bash -c`.  Requires workspace initialization — the constructor calls `openclaw agents add` to register the workspace directory.

**Agent-specific parameters:**

| Parameter | Constructor or `run()` | CLI flag | Type | Default | Description |
|-----------|----------------------|----------|------|---------|-------------|
| `agent_name` | constructor or `run()` | `--agent-name` | `str` | `"agentcall"` | Name of the openclaw agent to use. Must be registered via `openclaw agents add`. Passed as `--agent <name>` in the CLI command. |
| `thinking` | constructor or `run()` | `--thinking` | `str` | `"medium"` | Thinking/reasoning effort level. Controls how much the model "thinks" before responding. Must be one of: `off`, `minimal`, `low`, `medium`, `high`, `xhigh`, `adaptive`, `max`. Passed as `--thinking <level>`. |
| `local` | constructor or `run()` | `--local` / `--no-local` | `bool` | `True` | If `True`, appends `--local` to the `openclaw agent` command to use a local model. Set to `False` to use remote/cloud models. |

**Workspace initialization:**
- `openclaw` needs its workspace registered before use (`needs_init()` returns `True`).
- The constructor calls `init()`, which runs `openclaw agents add {agent_name} --workspace {workspace_dir}`.
- `workspace_dir` is used **directly** as the openclaw native workspace — openclaw can only read/write inside this directory.

**Generated command:**
```
openclaw agent --agent <agent_name> --session-id <chat_id> --thinking <level> --message <prompt> [--local]
```

```python
with AgentCall(
    "openclaw",
    workspace_dir="./runs",     # registered as openclaw native workspace
    agent_name="myagent",       # must be pre-registered
    thinking="xhigh",           # maximum thinking effort
    local=False,                # use cloud model
) as ac:
    result = ac.run(prompt="explain this codebase")
```

---

### `opencode` — `opencode run` subprocess

Wraps the `opencode run` CLI via `bash -c`.  The simplest subprocess-based agent.

**Agent-specific parameters:**

| Parameter | Constructor or `run()` | CLI flag | Type | Default | Description |
|-----------|----------------------|----------|------|---------|-------------|
| `model` | constructor or `run()` | `--model` | `str \| None` | `None` | Model name to pass via `--model`. When `None`, no `--model` flag is added and opencode uses its own default model. Setting it to a string adds `--model <value>` before the prompt. |

**Generated command:**
```
opencode run [--model <model>] <prompt>
```

**CLI example:**
```bash
agent-call --agent opencode -q "explain this code" --model deepseek-v4-flash
```

```python
# Use opencode's default model
AgentCall.run_once("opencode", prompt="echo hello")

# Override model
with AgentCall("opencode", model="deepseek-v4-flash") as ac:
    ac.run(prompt="explain this code")
    ac.run(prompt="now refactor it")
    ac.run(prompt="now write tests", model="gpt-4o")  # per-call override
```

---

### `hermes` — `hermes chat` subprocess with output parsing

Wraps `hermes chat -q <prompt>` via `bash -c` (or `bash -lc`).  After execution, the raw TUI output is **parsed** into structured sections.

**Agent-specific parameters:**

| Parameter | Constructor or `run()` | CLI flag | Type | Default | Description |
|-----------|----------------------|----------|------|---------|-------------|
| `login_shell` | `run()` only | `--login-shell` | `bool` | `False` | If `True`, uses `bash -lc` instead of `bash -c`. Needed when `hermes` is only available on PATH via `~/.bashrc` (which is only sourced in login shells). |
| `output_dir` | constructor only | `--output-dir` | `Path \| None` | `None` | Directory for temp and parsed output files. When `None`, uses the workspace-based default location. Sets `base_dir` for output path resolution. |

**Output parsing:**

The agent produces two output files:

| File | Pattern | Content |
|------|---------|---------|
| Raw output | `{chat_id}_hermes_output.txt` | Unprocessed TUI output from `hermes chat` |
| Parsed output | `{chat_id}_hermes_f_output.txt` | Structured output with sections |

The parsed output contains these sections:

```
=== model ===
<model name extracted from TUI>

=== query ===
<the prompt that was sent>

=== last_response ===
<the agent's last response — extracted from the final TUI box>

=== session_summary ===
Resume this session with: ...
```

**Parsing logic:**
1. **Model extraction:** Finds `· Nous Research` in the TUI output and reads the text between the preceding `│` and that marker.
2. **Query extraction:** Finds `Query: ` and reads until `Initializing...`.
3. **Last response extraction:** Finds the last occurrence of the `╭─ ⚕ Hermes ─` ... `╰────────` box boundaries and extracts the content between them.
4. **Session summary extraction:** Finds the last `Resume this session with:` line and includes everything from there to EOF.

```python
ac = AgentCall("hermes", output_dir=Path("./hermes_logs"))
ac.run(prompt="summarize meeting notes", login_shell=True)
# Raw output:   ./hermes_logs/MMdd-HHmmss_hermes_output.txt
# Parsed output: ./hermes_logs/MMdd-HHmmss_hermes_f_output.txt
```

---

## Parameter support matrix

Quick reference showing which agent-specific parameters each agent accepts.

| Parameter | dry | simple | jiuwenclaw | openclaw | opencode | hermes |
|-----------|:---:|:------:|:----------:|:--------:|:--------:|:-----:|
| `command` | — | — | ✓ | — | — | — |
| `agent_name` | — | — | — | ✓ | — | — |
| `thinking` | — | — | — | ✓ | — | — |
| `local` | — | — | — | ✓ | — | — |
| `model` | — | ✓ | — | — | ✓ | — |
| `config` | — | ✓ | — | — | — | — |
| `login_shell` | — | — | — | — | — | ✓ |
| `output_dir` | — | — | — | — | — | ✓ |
| `reset_workspace` | — | — | ✓ | — | — | — |

---

## CLI flags reference

### Required flags

| Flag | Description |
|------|-------------|
| `-a`, `--agent` | Agent key: `dry`, `simple`, `jiuwenclaw`, `openclaw`, `opencode`, `hermes` |
| `-q`, `--prompt` | Prompt text (or path to `.txt`/`.md` file). Mutually exclusive with `-f`. |
| `-f`, `--prompt-file` | Read prompt from file. Mutually exclusive with `-q`. |

### Common CLI flags (all agents)

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `-t`, `--timeout` | `float` | `900.0` | Subprocess timeout in seconds |
| `--cwd` | `Path` | *(workspace)* | Working directory for agent subprocess |
| `--output` | `str` | auto | Output path. Ends with `/` = directory; otherwise full file path |
| `--chat-id` | `str` | auto `MMdd-HHmmss` | Custom chat identifier |
| `--tee` | flag | off | Stream agent output to terminal while writing to file |
| `--workspace-dir` | `Path` | `./agent_call_workspace` | Workspace root directory |
| `--reset-workspace` | flag | on | Reset workspace before execution |
| `--no-reset-workspace` | flag | — | Do not reset workspace |

### Agent-specific CLI flags

| Flag | Applies to | Type | Default | Description |
|------|-----------|------|---------|-------------|
| `--command` | jiuwenclaw only | `str` | `jiuwenclaw-tui` | TUI command to spawn |
| `--agent-name` | openclaw only | `str` | `agentcall` | openclaw agent name |
| `--thinking` | openclaw only | `str` | `medium` | Thinking level: `off`, `minimal`, `low`, `medium`, `high`, `xhigh`, `adaptive`, `max` |
| `--model` | opencode / simple | `str` | *(none)* | Model name (e.g. `deepseek-v4-flash`) |
| `--local` / `--no-local` | openclaw only | flag | on | Use `--local` with openclaw |
| `--login-shell` | hermes only | flag | off | Use `bash -lc` instead of `bash -c` |
| `--output-dir` | hermes only | `Path` | *(workspace)* | Directory for temp/parsed output |

> Using an agent-specific flag with the wrong agent prints a warning to stderr but does not abort execution.

---

## Output file naming

Each agent defines its own output filename template. When `output` is specified as a directory (ends with `/`), the filename is generated from the template.  When `output` is a full file path, it's used as-is.

| Agent | Template | Notes |
|-------|----------|-------|
| `dry` | `{chat_id}_dry_output.txt` | |
| `simple` | `{chat_id}_simple_output.txt` | |
| `jiuwenclaw` | `{chat_id}_jiuwenclaw_output.txt` | Also writes `./jiuwenclaw_chat.log` |
| `openclaw` | `{chat_id}_openclaw_output.txt` | |
| `opencode` | `{chat_id}_opencode_output.txt` | |
| `hermes` | `{chat_id}_hermes_f_output.txt` | Also writes `{chat_id}_hermes_output.txt` (raw) |

---

## Return codes

| Code | Meaning |
|------|---------|
| `0` | Success — agent completed normally |
| `124` | Subprocess timeout — output may be truncated |
| `127` | Command not found — agent CLI not on PATH |
| other | Agent-specific non-zero exit code (e.g. `simple` returns `1` on HTTP error) |

---

## Error handling

- **Unsupported kwargs:** Python emits `UserWarning` when passing kwargs that the agent doesn't support.  CLI prints warnings to stderr for irrelevant agent-specific flags.
- **Timeout:** `subprocess.TimeoutExpired` → `returncode=124`.  Partial output is still captured and written.
- **Command not found:** `FileNotFoundError` → `returncode=127`.  The CLI prints guidance about `PATH` configuration (`~/.profile` vs `~/.bashrc`).
- **jiuwenclaw (pexpect):** `pexpect.TIMEOUT` or `pexpect.EOF` returns `None` from the interaction function → `returncode=124`.
- **simple (HTTP):** `URLError` or other exceptions → error written as JSON to output, `returncode=1`.
- **hermes:** If the raw TUI output is empty or unparseable, the parsed sections will be empty strings — the agent does not error.

---

## Configuration files

### `model_configs.json`

Per-model configuration for error pattern detection.  Currently supports `opencode`:

```json
{
    "opencode": {
        "error_patterns": [
            "Key limit exceeded",
            "No payment method",
            "Upstream idle timeout exceeded"
        ]
    }
}
```

### `simple_agent_config.ini`

Used only by the `simple` agent.  See the [simple agent section](#simple--direct-openai-compatible-http-api) for format and usage.

---

## Extending with a custom agent

Subclass `BaseAgent` and register it:

```python
from agent_call import BaseAgent, AgentResult

class MyAgent(BaseAgent):
    name = "myagent"
    output_filename_template = "{chat_id}_myagent_output.txt"
    _supported_kwargs = frozenset({"my_param"})

    def execute(self, prompt, *, cwd, output, chat_id, timeout, tee, **kwargs) -> AgentResult:
        my_param = kwargs.get("my_param", "default_value")
        # ... run your agent, write results to `output` ...
        output.write_text("response", encoding="utf-8")
        return AgentResult(
            chat_id=chat_id,
            output_path=output,
            complete_response="response",
            returncode=0,
        )
```

Then inject into `_AGENT_CLASSES` or subclass `AgentCall` to add it to the registry.
