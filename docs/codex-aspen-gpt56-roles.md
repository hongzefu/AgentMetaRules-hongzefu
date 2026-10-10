# Codex GPT-6／GPT-6.1 模型规则与 Aspen 角色迁移（2026-10-10）

## 一、结论

Codex 主代理、所有子代理及递归子代理仅允许使用 GPT-6 与 GPT-6.1 系列，禁止任何 GPT-5.6 模型及其它系列。此规则来自用户 2026-10-10 的明确指令，替代此前 Aspen 仅用 GPT-5.6 的约定；不是对模型性能或账号权限的推断。

用户原话：「不允许使用任何GPT 5.6的模型，只允许使用GPT 6和GPT 6.1的模型。」「这个你可以直接改，对于 Markdown 的修改是可以直接改。」「你要更新一下这些 Markdown，就是说都要更新成GPT-6，GPT-6.1的系列。」

本次更新 Markdown 规则与安装示例，不据此声称 `codex/aspen/agents/*.toml`、`~/.codex/agents/` 或 `~/.codex/config.toml` 已完成迁移。旧角色仍绑定 GPT-5.6 时禁止调用，须显式指定宿主提供的 GPT-6／GPT-6.1 型号；不支持显式选择时停止该项委派并报告。文档保留历史文件名以维持已有引用，第五节旧实测仅作历史证据。

## 二、角色映射（迁移目标，不代表已安装）

| 角色 | 模型 | 推理强度 | 写入边界 | 用途 |
|---|---|---|---|---|
| 主代理 / `default` | `gpt-6.1-sol` | `high` | 继承当前会话 | 总体决策、整合、兜底 |
| `planner` | `gpt-6.1-sol` | `xhigh` | `read-only` | 高歧义、多阶段计划与风险分析 |
| `reviewer` | `gpt-6.1-sol` | `high` | `read-only` | 正确性、安全性、回归与测试缺口审查 |
| `worker` | `gpt-6-sol` | `high` | 继承当前会话 | 边界清晰的代码或配置实现 |
| `tester` | `gpt-6-sol` | `high` | 继承当前会话 | 测试、复现、日志与失败归因，不修改源码 |
| `explorer` | `gpt-6-luna` | `high` | `read-only` | 快速代码路径、文件、依赖与事实检索 |

上表示例型号须以宿主实际可用列表核对，并遵守第 26 条的职责映射、显式选择和子代理不高于主请求模型档位的约束；无法比较档位时停止受影响派发并报告，不以继承模型绕过显式选择。指定型号不可用时报告，不得回退到 GPT-5.6。

所有角色配置位于 [`../codex/aspen/agents/`](../codex/aspen/agents/)。`default`、`worker`、`explorer` 会覆盖同名内置角色；其余三个是自定义角色。角色只负责模型、推理强度与职责边界；并发、授权、写入隔离、验证和提交仍服从 `AGENTS.md`。

## 三、Aspen 全局配置（后续配置迁移时使用）

`/home/hongzefu/.codex/config.toml` 必须包含以下值；已有 `projects`、`plugins`、`features` 等表保持原样：

```toml
model = "gpt-6.1-sol"
model_reasoning_effort = "high"
project_doc_max_bytes = 131072

[agents]
enabled = true
max_concurrent_threads_per_session = 16
default_subagent_model = "gpt-6-sol"
default_subagent_reasoning_effort = "high"
```

全局 `AGENTS.md` 通过符号链接指向正本；六个角色必须复制成 `~/.codex/agents/` 下的普通文件。2026-10-06 实测角色使用指向仓库外的符号链接时，运行时返回 `agent type is currently not available`，改为字节相同的普通文件后才成功注册：

```bash
ln -s /data/hongzefu/AgentMetaRules-hongzefu/AGENTS.md /home/hongzefu/.codex/AGENTS.md
mkdir -p /home/hongzefu/.codex/agents
for role in default planner explorer worker reviewer tester; do
  install -m 0644 "/data/hongzefu/AgentMetaRules-hongzefu/codex/aspen/agents/${role}.toml" \
    "/home/hongzefu/.codex/agents/${role}.toml"
done
```

安装前必须先逐个确认目标是缺失、普通文件还是符号链接；普通文件不得被无提示覆盖。更新正本后必须重新复制，并以逐文件 SHA-256 或字节比较确认安装副本与正本一致。

## 四、验收

以下检查必须全部通过：

```bash
readlink -f /home/hongzefu/.codex/AGENTS.md
find /home/hongzefu/.codex/agents -maxdepth 1 -type f -printf '%f\n' | sort
UV_CACHE_DIR="$HOME/.cache/uv" uv run --no-project python - <<'PY'
import tomllib
from pathlib import Path

root = Path('/home/hongzefu/.codex')
repo_agents = Path('/data/hongzefu/AgentMetaRules-hongzefu/codex/aspen/agents')
config = tomllib.loads((root / 'config.toml').read_text())
assert config['model'] == 'gpt-6.1-sol'
assert config['model_reasoning_effort'] == 'high'
assert config['project_doc_max_bytes'] == 131072
assert config['agents']['max_concurrent_threads_per_session'] == 16
assert config['agents']['default_subagent_model'] == 'gpt-6-sol'
assert config['agents']['default_subagent_reasoning_effort'] == 'high'

expected = {'default', 'planner', 'explorer', 'worker', 'reviewer', 'tester'}
seen = set()
for path in sorted((root / 'agents').glob('*.toml')):
    assert path.is_file() and not path.is_symlink(), path
    assert path.read_bytes() == (repo_agents / path.name).read_bytes(), path
    role = tomllib.loads(path.read_text())
    assert role['model'].startswith(('gpt-6-', 'gpt-6.1-')), (path, role['model'])
    assert role['name'] == path.stem, (path, role['name'])
    seen.add(role['name'])
assert seen == expected, (seen, expected)
print('ASPEN_GPT6_SERIES_ROLES=PASS')
PY
```

配置文件写入成功不代表已有 Codex 任务会热切换模型或并发上限。最终验收必须新建任务，用 `/status` 核对主代理为 `gpt-6.1-sol/high`，再各启动一次角色并检查子任务详情里的实际模型与推理强度；只有新任务实测才可写“运行时生效”。多代理验收不得使用 `codex exec --ephemeral`：临时主线程没有可供子线程继承的 rollout，本轮实测报 `no rollout found for thread id`。

## 五、2026-10-06 运行时验收记录（历史记录，已被新规则替代）

以下模型、任务 ID 与判定行保留当时的真实结果，不是现行可用性结论，也不授权重新调用 GPT-5.6。

Aspen 用户本地 CLI 从 `0.144.3` 升级到 `0.160.1` 后，以持久化、只读的 `codex exec --strict-config --json` 新建父任务 `01a11266-cf3e-70c2-92a9-b2356347bf80`，并行要求六个角色各自读取本仓库 `README.md` 第一行。逐个读取保存的 `session_meta` 与 `turn_context` 后得到：

| 角色 | 子任务 ID | 实际模型 | 实际推理强度 |
|---|---|---|---|
| `default` | `01a11267-06a4-7940-8a15-090a2ec65408` | `gpt-5.6-sol` | `high` |
| `planner` | `01a11267-0e30-7ce3-af2a-c8ded0fd692a` | `gpt-5.6-sol` | `xhigh` |
| `explorer` | `01a11267-1618-7243-a9d6-8cdeabeca27a` | `gpt-5.6-luna` | `high` |
| `worker` | `01a11267-1dd0-7ad3-bc8c-4f45ffb51d7f` | `gpt-5.6-terra` | `high` |
| `reviewer` | `01a11267-2633-7d71-bc9f-978e7246400e` | `gpt-5.6-sol` | `high` |
| `tester` | `01a11267-2e27-7fc0-b5bc-abfb8bec74bd` | `gpt-5.6-terra` | `high` |

父任务实际为 `gpt-5.6-sol/high`。六个子任务均返回 `# AgentMetaRules-hongzefu`，父任务最终输出 `ASPEN_ALL_ROLES_RUNTIME=PASS`；父子任务全部以 `read-only` 启动，本轮没有文件写入。判定脚本逐一核对角色、父任务 ID、实际模型和推理强度，输出 `ALL_ROLE_ROUTES=PASS count=6`。
