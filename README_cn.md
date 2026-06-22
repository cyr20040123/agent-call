# agent-call

AI Agent 对话工具的统一 CLI 和 Python API。通过单一接口调用所有支持的 Agent —— 统一的参数、统一的输出格式，无需切换心智模型。

## 支持的 Agent

| Agent | 标识符 | 后端 | 依赖 |
|-------|--------|------|------|
| **Dry** | `dry` | 空操作（仅打印 prompt） | 无 |
| **Simple** | `simple` | OpenAI 兼容 HTTP API（`urllib`） | `simple_agent_config.ini` 配置文件 |
| **Jiuwenclaw** | `jiuwenclaw` | pexpect TUI 自动化 | `jiuwenclaw-tui` 在 PATH 中 |
| **Openclaw** | `openclaw` | `openclaw agent` 子进程 | `openclaw` 在 PATH 中 |
| **Opencode** | `opencode` | `opencode run` 子进程 | `opencode` 在 PATH 中 |
| **Hermes** | `hermes` | `hermes chat` 子进程 + 输出解析 | `hermes` 在 PATH 中 |

---

## 安装

```bash
pip install -e .
```

**环境要求：** Python ≥ 3.10。`pexpect` 依赖仅 `jiuwenclaw` agent 需要。各 agent 还需要对应的 CLI 工具已安装并在 PATH 中（见上表）。

---

## 快速开始

### CLI 命令行

```bash
# 通过 --agent / -a 选择 agent
agent-call --agent opencode -q "echo hello"
agent-call --agent jiuwenclaw -q "你的提示词" --tee
agent-call --agent openclaw -q "你的提示词" --thinking high
agent-call --agent hermes -q "你的提示词" --login-shell

# 从文件读取 prompt
agent-call --agent opencode -f ./prompt.txt

# 自定义输出目录（以 / 结尾 → 目录内自动命名）
agent-call --agent jiuwenclaw -q "prompt" --output ./results/

# 完整输出文件路径
agent-call --agent opencode -q "prompt" --output ./results/my_output.txt
```

未 pip install 时，`python -m agent_call` 效果相同。

### Python API — 单次调用

```python
from agent_call import AgentCall

# 最简用法：字符串 prompt，自动生成路径
result = AgentCall.run_once("opencode", prompt="echo hello")
print(result.complete_response)   # 完整响应文本
print(result.returncode)          # 0 = 成功, 124 = 超时
print(result.output_path)         # 输出文件路径
```

### Python API — 上下文管理器（持久化工作区）

```python
from pathlib import Path
from agent_call import AgentCall

with AgentCall("jiuwenclaw", workspace_dir=Path("./runs")) as ac:
    result = ac.run(
        prompt="把今天的会议纪要总结为要点。",
        timeout=600,
        tee=True,              # 同步输出到终端
    )
    print(f"输出文件: {result.output_path}")
    print(f"对话 ID: {result.chat_id}")
```

---

## 通用参数（所有 agent 共用）

以下参数在 `AgentCall` / `run()` 层面处理，然后转发给 agent 后端。

### `AgentCall` 构造参数

| 参数 | 类型 | 默认值 | 说明 |
|-----------|------|---------|-------------|
| `agent` | `str` | *(必填)* | Agent 标识符：`dry`、`simple`、`jiuwenclaw`、`openclaw`、`opencode`、`hermes` |
| `workspace_dir` | `Path \| None` | `./agent_call_workspace` | 输出和工作区的根目录。对于 `openclaw`，此目录同时注册为 openclaw 的原生工作区。 |
| `**agent_kwargs` | — | — | Agent 专用参数，会转发给每次 `run()` 调用（详见下文各 agent 参数表）。 |

### `run()` / `run_once()` 通用参数

| 参数 | 类型 | 默认值 | 说明 |
|-----------|------|---------|-------------|
| `prompt` | `str \| None` | — | 提示词文本。与 `prompt_file` 互斥。 |
| `prompt_file` | `str \| Path \| None` | — | 从文件读取 prompt。与 `prompt` 互斥。 |
| `chat_id` | `str \| None` | 自动生成 `MMdd-HHmmss` | 本次对话的唯一标识符。 |
| `timeout` | `float` | `900.0` | 子进程超时时间（秒）。超时返回 `returncode=124`。 |
| `cwd` | `Path \| None` | `out_root` | Agent 子进程的工作目录。 |
| `output` | `str \| Path \| None` | `{cwd}/{chat_id}_<agent>_output.txt` | 输出路径。以 `/` 结尾 → 目录（内部自动命名）；否则为完整文件路径。 |
| `tee` | `bool` | `False` | 若为 `True`，在写入文件的同时将 agent 输出流式打印到终端。 |
| `reset_workspace` | `bool` | `True` | 若为 `True`，执行前重置 agent 工作区（目前仅 `jiuwenclaw` 生效）。 |

### `AgentResult`（返回值类型）

```python
@dataclass
class AgentResult:
    chat_id: str           # "MMdd-HHmmss" 格式
    output_path: Path      # 输出文件路径
    complete_response: str # 完整响应文本
    returncode: int        # 0 = 成功, 124 = 超时, 127 = 命令未找到
    extra: dict            # agent 专用附加数据
```

---

## Agent 专用参数

每个 agent 支持的参数各不相同。传入不支持的参数会触发 Python `UserWarning`（CLI 模式下则向 stderr 打印警告）。下表中详列每个 agent 支持的参数、默认值及其具体作用。

---

### `dry` — 空操作 agent

不做任何实际调用。将 prompt、cwd 和 output 路径打印到 stdout，把 prompt 文本写入输出文件，然后立即返回 `returncode=0`。

**用途：** 测试 pipeline 配置、验证 prompt 构造、检查输出路径解析 —— 无需实际调用任何 agent。

**Agent 专用参数：** *无*（未定义 `_supported_kwargs`）

```python
ac = AgentCall("dry")
result = ac.run(prompt="测试提示词")  # 打印 [dry] 信息，将 prompt 写入输出文件
```

---

### `simple` — 直接调用 OpenAI 兼容 HTTP API

向任意 OpenAI 兼容接口发送单次非流式 chat completion 请求。无子进程，无外部 CLI 依赖。从 INI 配置文件读取认证信息。

**Agent 专用参数：**

| 参数 | 传入位置 | CLI flag | 类型 | 默认值 | 说明 |
|-----------|----------------------|----------|------|---------|-------------|
| `config` | 仅 `run()` | *(仅 Python API)* | `str` | `"simple_agent_config.ini"` | INI 配置文件路径。若非绝对路径，则相对于当前工作目录解析。 |
| `model` | 构造函数或 `run()` | `--model` | `str \| None` | `None`（使用配置文件中的值） | 覆盖模型名称。设置后，API 请求体中使用此模型名而非配置文件中的模型名。 |

**配置文件格式** (`simple_agent_config.ini`)：

```ini
[DEFAULT]
base-url = https://api.deepseek.com
api-key = sk-xxxxxxxxxxxxxxxxxxxxxxxx
model = deepseek-v4-flash
```

**工作流程：**
1. 从 INI 文件读取 `base-url`、`api-key` 和 `model`。
2. 向 `{base-url}/v1/chat/completions` 发送 POST 请求，body 为 `{"model": "...", "messages": [...], "stream": false}`。
3. 从响应中提取 `choices[0].message.content` 并写入输出文件。
4. HTTP 出错时，将错误信息以 JSON 格式写入输出文件，`returncode=1`。

```python
# 使用配置文件中的默认值
AgentCall.run_once("simple", prompt="你好")

# 在构造函数中覆盖 model（对所有 run() 调用生效）
with AgentCall("simple", model="deepseek-v4-pro") as ac:
    ac.run(prompt="第一个问题")

# 单次调用覆盖 model
ac.run(prompt="第二个问题", model="gpt-4o")

# 单次调用使用自定义配置文件
ac.run(prompt="...", config="./prod.ini")
```

---

### `jiuwenclaw` — pexpect TUI 自动化

通过 pexpect 启动 `jiuwenclaw-tui`，等待 TUI 初始化完成，以按键方式发送 prompt，轮询等待"空闲/完成"信号，然后发送 `/exit` 退出。输出会经过 ANSI 转义码剥离和日志后处理。

**Agent 专用参数：**

| 参数 | 传入位置 | CLI flag | 类型 | 默认值 | 说明 |
|-----------|----------------------|----------|------|---------|-------------|
| `command` | 构造函数或 `run()` | `--command` | `str` | `"jiuwenclaw-tui"` | 要启动的 TUI 命令。用于自定义包装器或别名。生成的实际命令为：`{command} --session {chat_id}`。 |
| `reset_workspace` | 仅 `run()` | `--reset-workspace` / `--no-reset-workspace` | `bool` | `False`（execute 中的默认值） | 若为 `True`，TUI 启动后通过 pexpect 发送 `/workspace set <cwd>` 将工作区重置到当前工作目录。**注意：** CLI 中默认为 `True`，Python API 的 `execute()` 中默认为 `False`。 |

**工作流程：**
1. 在指定 `cwd` 下启动 `{command} --session {chat_id}`。
2. 等待魔数串 `https://gitcode.com/openJiuwen/agent-core`（TUI 就绪信号，30 秒超时）。
3. 按 Enter 确认工作区。
4. 如果 `reset_workspace=True`，发送 `/workspace set <cwd>` 并等待。
5. 发送 prompt 文本 + Enter。
6. 每 5 秒轮询一次，20 秒无响应判定为空闲，同时检测 `esc to interrupt`（仍在运行）或 `Enter confirm`（需确认 → 自动确认）。
7. 检测到 `mode:code.normal` 或分隔线后，发送 `/exit` 退出。
8. 后处理交互日志：剥离 ANSI 转义码和 TUI 框架行。

**日志：** 在当前工作目录下额外写入 pexpect 交互日志 `./jiuwenclaw_chat.log`。

```python
with AgentCall("jiuwenclaw", command="jiuwenclaw-tui") as ac:
    ac.run(prompt="做某事", reset_workspace=True)
```

---

### `openclaw` — `openclaw agent` 子进程

通过 `bash -c` 包装 `openclaw agent` CLI。需要工作区初始化 —— 构造函数会调用 `openclaw agents add` 注册工作区目录。

**Agent 专用参数：**

| 参数 | 传入位置 | CLI flag | 类型 | 默认值 | 说明 |
|-----------|----------------------|----------|------|---------|-------------|
| `agent_name` | 构造函数或 `run()` | `--agent-name` | `str` | `"agentcall"` | 要使用的 openclaw agent 名称。必须已通过 `openclaw agents add` 注册。在 CLI 命令中以 `--agent <name>` 传入。 |
| `thinking` | 构造函数或 `run()` | `--thinking` | `str` | `"medium"` | 思考/推理力度级别，控制模型在回答前的"思考"程度。可选值：`off`、`minimal`、`low`、`medium`、`high`、`xhigh`、`adaptive`、`max`。以 `--thinking <level>` 传入命令。 |
| `local` | 构造函数或 `run()` | `--local` / `--no-local` | `bool` | `True` | 若为 `True`，在 `openclaw agent` 命令后追加 `--local` 以使用本地模型。设为 `False` 则使用远程/云端模型。 |

**工作区初始化：**
- `openclaw` 使用前需要注册工作区（`needs_init()` 返回 `True`）。
- 构造函数调用 `init()`，执行 `openclaw agents add {agent_name} --workspace {workspace_dir}`。
- `workspace_dir` **直接**作为 openclaw 原生工作区使用 —— openclaw 只能在此目录内读写。

**生成的命令：**
```
openclaw agent --agent <agent_name> --session-id <chat_id> --thinking <level> --message <prompt> [--local]
```

```python
with AgentCall(
    "openclaw",
    workspace_dir="./runs",     # 注册为 openclaw 原生工作区
    agent_name="myagent",       # 需预先注册
    thinking="xhigh",           # 最高思考力度
    local=False,                # 使用云端模型
) as ac:
    result = ac.run(prompt="解释这个代码库")
```

---

### `opencode` — `opencode run` 子进程

通过 `bash -c` 包装 `opencode run` CLI。最简单的基于子进程的 agent。

**Agent 专用参数：**

| 参数 | 传入位置 | CLI flag | 类型 | 默认值 | 说明 |
|-----------|----------------------|----------|------|---------|-------------|
| `model` | 构造函数或 `run()` | `--model` | `str \| None` | `None` | 通过 `--model` 传入的模型名称。为 `None` 时不添加 `--model` flag，opencode 使用其自带默认模型。设置为字符串时，在 prompt 前添加 `--model <value>`。 |

**生成的命令：**
```
opencode run [--model <model>] <prompt>
```

**CLI 示例：**
```bash
agent-call --agent opencode -q "解释这段代码" --model deepseek-v4-flash
```

```python
# 使用 opencode 默认模型
AgentCall.run_once("opencode", prompt="echo hello")

# 覆盖模型
with AgentCall("opencode", model="deepseek-v4-flash") as ac:
    ac.run(prompt="解释这段代码")
    ac.run(prompt="现在重构它")
    ac.run(prompt="现在写测试", model="gpt-4o")  # 单次调用覆盖
```

---

### `hermes` — `hermes chat` 子进程 + 输出解析

通过 `bash -c`（或 `bash -lc`）包装 `hermes chat -q <prompt>`。执行完成后，将原始 TUI 输出**解析**为结构化章节。

**Agent 专用参数：**

| 参数 | 传入位置 | CLI flag | 类型 | 默认值 | 说明 |
|-----------|----------------------|----------|------|---------|-------------|
| `login_shell` | 仅 `run()` | `--login-shell` | `bool` | `False` | 若为 `True`，使用 `bash -lc` 替代 `bash -c`。当 `hermes` 仅通过 `~/.bashrc` 配置 PATH（仅 login shell 会 source 该文件）时需要启用。 |
| `output_dir` | 仅构造函数 | `--output-dir` | `Path \| None` | `None` | 临时文件和解析后输出文件的存放目录。为 `None` 时使用基于工作区的默认位置。会影响输出路径的 `base_dir` 解析。 |

**输出解析：**

该 agent 会产生两个输出文件：

| 文件 | 文件名模式 | 内容 |
|------|---------|---------|
| 原始输出 | `{chat_id}_hermes_output.txt` | `hermes chat` 的未处理 TUI 输出 |
| 解析后输出 | `{chat_id}_hermes_f_output.txt` | 结构化的分析结果 |

解析后的输出包含以下章节：

```
=== model ===
<从 TUI 中提取的模型名称>

=== query ===
<发送的 prompt 内容>

=== last_response ===
<agent 的最后一次响应 —— 从最后一个 TUI 框体中提取>

=== session_summary ===
Resume this session with: ...
```

**解析逻辑：**
1. **模型提取：** 在 TUI 输出中定位 `· Nous Research`，读取其前一个 `│` 与该标记之间的文本。
2. **查询提取：** 定位 `Query: `，读取直到 `Initializing...` 之间的内容。
3. **最后响应提取：** 定位最后一个 `╭─ ⚕ Hermes ─` ... `╰────────` 框体边界，提取其中的内容。
4. **会话摘要提取：** 定位最后一行 `Resume this session with:`，包含该行之后的所有内容。

```python
ac = AgentCall("hermes", output_dir=Path("./hermes_logs"))
ac.run(prompt="总结会议纪要", login_shell=True)
# 原始输出:   ./hermes_logs/MMdd-HHmmss_hermes_output.txt
# 解析后输出: ./hermes_logs/MMdd-HHmmss_hermes_f_output.txt
```

---

## 参数支持矩阵

快速查看每个 agent 支持哪些专用参数。

| 参数 | dry | simple | jiuwenclaw | openclaw | opencode | hermes |
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

## CLI 命令行参考

### 必选参数

| Flag | 说明 |
|------|-------------|
| `-a`, `--agent` | Agent 标识符：`dry`、`simple`、`jiuwenclaw`、`openclaw`、`opencode`、`hermes` |
| `-q`, `--prompt` | 提示词文本（或 `.txt`/`.md` 文件路径）。与 `-f` 互斥。 |
| `-f`, `--prompt-file` | 从文件读取 prompt。与 `-q` 互斥。 |

### 通用 CLI 参数（所有 agent）

| Flag | 类型 | 默认值 | 说明 |
|------|------|---------|-------------|
| `-t`, `--timeout` | `float` | `900.0` | 子进程超时时间（秒） |
| `--cwd` | `Path` | *(工作区)* | Agent 子进程的工作目录 |
| `--output` | `str` | 自动 | 输出路径。以 `/` 结尾 = 目录；否则为完整文件路径 |
| `--chat-id` | `str` | 自动 `MMdd-HHmmss` | 自定义对话标识符 |
| `--tee` | flag | 关闭 | 同步将 agent 输出流式打印到终端 |
| `--workspace-dir` | `Path` | `./agent_call_workspace` | 工作区根目录 |
| `--reset-workspace` | flag | 开启 | 执行前重置工作区 |
| `--no-reset-workspace` | flag | — | 不重置工作区 |

### Agent 专用 CLI 参数

| Flag | 适用 Agent | 类型 | 默认值 | 说明 |
|------|-----------|------|---------|-------------|
| `--command` | 仅 jiuwenclaw | `str` | `jiuwenclaw-tui` | 要启动的 TUI 命令 |
| `--agent-name` | 仅 openclaw | `str` | `agentcall` | openclaw agent 名称 |
| `--thinking` | 仅 openclaw | `str` | `medium` | 思考级别：`off`、`minimal`、`low`、`medium`、`high`、`xhigh`、`adaptive`、`max` |
| `--model` | opencode / simple | `str` | *(无)* | 模型名称（如 `deepseek-v4-flash`） |
| `--local` / `--no-local` | 仅 openclaw | flag | 开启 | openclaw 是否使用 `--local` |
| `--login-shell` | 仅 hermes | flag | 关闭 | 使用 `bash -lc` 替代 `bash -c` |
| `--output-dir` | 仅 hermes | `Path` | *(工作区)* | 临时/解析后输出文件目录 |

> 对不匹配的 agent 使用专用 flag 会向 stderr 打印警告，但不会中止执行。

---

## 输出文件命名

每个 agent 有自己的输出文件名模板。当 `output` 指定为目录（以 `/` 结尾）时，文件名从模板生成。当 `output` 为完整文件路径时，直接使用。

| Agent | 模板 | 备注 |
|-------|----------|-------|
| `dry` | `{chat_id}_dry_output.txt` | |
| `simple` | `{chat_id}_simple_output.txt` | |
| `jiuwenclaw` | `{chat_id}_jiuwenclaw_output.txt` | 同时写入 `./jiuwenclaw_chat.log` |
| `openclaw` | `{chat_id}_openclaw_output.txt` | |
| `opencode` | `{chat_id}_opencode_output.txt` | |
| `hermes` | `{chat_id}_hermes_f_output.txt` | 同时写入 `{chat_id}_hermes_output.txt`（原始输出） |

---

## 返回码

| 返回码 | 含义 |
|------|---------|
| `0` | 成功 —— agent 正常完成 |
| `124` | 子进程超时 —— 输出可能被截断 |
| `127` | 命令未找到 —— agent CLI 不在 PATH 中 |
| 其他 | Agent 特定的非零退出码（如 `simple` 在 HTTP 错误时返回 `1`） |

---

## 错误处理

- **不支持的参数：** Python 中传入 agent 不支持的 kwarg 会触发 `UserWarning`。CLI 中对不匹配的 agent 使用专用 flag 会向 stderr 打印警告。
- **超时：** `subprocess.TimeoutExpired` → `returncode=124`。部分输出仍会被捕获并写入文件。
- **命令未找到：** `FileNotFoundError` → `returncode=127`。CLI 会打印关于 `PATH` 配置（`~/.profile` 与 `~/.bashrc` 的区别）的指引。
- **jiuwenclaw（pexpect）：** `pexpect.TIMEOUT` 或 `pexpect.EOF` 时交互函数返回 `None` → `returncode=124`。
- **simple（HTTP）：** `URLError` 或其他异常 → 错误以 JSON 格式写入输出文件，`returncode=1`。
- **hermes：** 如果原始 TUI 输出为空或无法解析，解析后的章节内容为空字符串 —— agent 不会报错。

---

## 配置文件

### `model_configs.json`

按模型配置错误检测规则。目前支持 `opencode`：

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

仅 `simple` agent 使用。格式和用法见 [simple agent 章节](#simple--直接调用-openai-兼容-http-api)。

---

## 自定义 Agent 扩展

继承 `BaseAgent` 并注册即可：

```python
from agent_call import BaseAgent, AgentResult

class MyAgent(BaseAgent):
    name = "myagent"
    output_filename_template = "{chat_id}_myagent_output.txt"
    _supported_kwargs = frozenset({"my_param"})

    def execute(self, prompt, *, cwd, output, chat_id, timeout, tee, **kwargs) -> AgentResult:
        my_param = kwargs.get("my_param", "默认值")
        # ... 运行你的 agent，将结果写入 output ...
        output.write_text("响应内容", encoding="utf-8")
        return AgentResult(
            chat_id=chat_id,
            output_path=output,
            complete_response="响应内容",
            returncode=0,
        )
```

然后注入到 `_AGENT_CLASSES` 或子类化 `AgentCall` 将其加入注册表。
