# Aspen Codex GPT-5.6 角色配置（2026-10-06）

## 一、结论

Aspen 的 Codex 模型统一限定为 GPT-5.6 家族。主代理固定使用 `gpt-5.6-sol/high`，子代理按职责在同一家族内分档：复杂规划和审查使用 `Sol`，常规实现和测试使用 `Terra`，只读探索使用 `Luna`。不得配置 GPT-5.5、GPT-6、Claude `opus` / `sonnet` 或其他模型；指定模型不可用时必须显式失败并报告，不得静默回退。

OpenAI 官方 GPT-5.6 指南将 `Sol` 定义为旗舰能力、`Terra` 定义为智能与成本平衡、`Luna` 定义为高吞吐效率档；Codex Subagents 文档确认全局默认值放在 `[agents]`，角色文件可分别设置 `model` 与 `model_reasoning_effort`。本机 2026-10-06 的 `/home/hongzefu/.codex/models_cache.json` 同时列出这三个精确 slug，`/home/hongzefu/.codex/config.toml` 的主模型已经是 `gpt-5.6-sol/high`。

官方依据：

- [OpenAI GPT-5.6 指南](https://developers.openai.com/api/docs/guides/latest-model#using-gpt-56)
- [OpenAI Codex Subagents 文档](https://learn.chatgpt.com/docs/agent-configuration/subagents)
- [OpenAI Codex 配置参考](https://learn.chatgpt.com/docs/config-file/config-reference)

## 二、角色映射

| 角色 | 模型 | 推理强度 | 写入边界 | 用途 |
|---|---|---|---|---|
| 主代理 / `default` | `gpt-5.6-sol` | `high` | 继承当前会话 | 总体决策、整合、兜底 |
| `planner` | `gpt-5.6-sol` | `xhigh` | `read-only` | 高歧义、多阶段计划与风险分析 |
| `reviewer` | `gpt-5.6-sol` | `high` | `read-only` | 正确性、安全性、回归与测试缺口审查 |
| `worker` | `gpt-5.6-terra` | `high` | 继承当前会话 | 边界清晰的代码或配置实现 |
| `tester` | `gpt-5.6-terra` | `high` | 继承当前会话 | 测试、复现、日志与失败归因，不修改源码 |
| `explorer` | `gpt-5.6-luna` | `high` | `read-only` | 快速代码路径、文件、依赖与事实检索 |

所有角色正本位于 [`../codex/aspen/agents/`](../codex/aspen/agents/)。`default`、`worker`、`explorer` 会覆盖同名内置角色；其余三个是自定义角色。角色只负责模型、推理强度与职责边界；并发、授权、写入隔离、验证和提交仍服从 `AGENTS.md`。

## 三、Aspen 全局配置

`/home/hongzefu/.codex/config.toml` 必须包含以下值；已有 `projects`、`plugins`、`features` 等表保持原样：

```toml
model = "gpt-5.6-sol"
model_reasoning_effort = "high"
project_doc_max_bytes = 131072

[agents]
enabled = true
max_concurrent_threads_per_session = 16
default_subagent_model = "gpt-5.6-terra"
default_subagent_reasoning_effort = "high"
```

全局规则与角色通过符号链接安装，正本只保留一份：

```bash
ln -s /data/hongzefu/AgentMetaRules-hongzefu/AGENTS.md /home/hongzefu/.codex/AGENTS.md
mkdir -p /home/hongzefu/.codex/agents
for role in default planner explorer worker reviewer tester; do
  ln -s "/data/hongzefu/AgentMetaRules-hongzefu/codex/aspen/agents/${role}.toml" \
    "/home/hongzefu/.codex/agents/${role}.toml"
done
```

安装前必须先逐个确认目标是缺失、普通文件还是符号链接；普通文件不得被无提示覆盖。更新正本后，已有符号链接无需复制。

## 四、验收

以下检查必须全部通过：

```bash
readlink -f /home/hongzefu/.codex/AGENTS.md
find /home/hongzefu/.codex/agents -maxdepth 1 -type l -printf '%f -> %l\n' | sort
uv run --no-project python - <<'PY'
import tomllib
from pathlib import Path

root = Path('/home/hongzefu/.codex')
config = tomllib.loads((root / 'config.toml').read_text())
assert config['model'] == 'gpt-5.6-sol'
assert config['model_reasoning_effort'] == 'high'
assert config['project_doc_max_bytes'] == 131072
assert config['agents']['max_concurrent_threads_per_session'] == 16
assert config['agents']['default_subagent_model'] == 'gpt-5.6-terra'
assert config['agents']['default_subagent_reasoning_effort'] == 'high'

expected = {'default', 'planner', 'explorer', 'worker', 'reviewer', 'tester'}
seen = set()
for path in sorted((root / 'agents').glob('*.toml')):
    role = tomllib.loads(path.read_text())
    assert role['model'].startswith('gpt-5.6-'), (path, role['model'])
    assert role['name'] == path.stem, (path, role['name'])
    seen.add(role['name'])
assert seen == expected, (seen, expected)
print('ASPEN_GPT56_ROLES=PASS')
PY
```

配置文件写入成功不代表已有 Codex 任务会热切换模型或并发上限。最终验收必须新建任务，用 `/status` 核对主代理为 `gpt-5.6-sol/high`，再各启动一次角色并检查子任务详情里的实际模型与推理强度；只有新任务实测才可写“运行时生效”。
