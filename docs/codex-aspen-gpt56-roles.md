# Codex 模型优先级与 Aspen 角色迁移记录

## 一、结论

**AWS 专属覆盖（2026-10-22）**：AWS 上的 Codex 主代理、全部角色子代理及递归子代理，只允许 `gpt-6-astra` + `ultra`，不可用或无法确认时停止受影响工作并报告，禁止换模型或降低推理强度。此要求覆盖本文下述非 AWS 角色映射、最低强度和 Aspen 安装示例；不得把 Aspen 的 Sol／Luna 配置复制到 AWS。普通模式、计划模式和旧会话续接均适用，详见 [`AGENTS.md`](../AGENTS.md) 第 26 条与 [AWS 落地记录](machine-aws-p4de.md)。

**非 AWS 现行规则（2026-11-20）**：Codex 主代理、所有子代理及递归子代理按 **GPT-6.2 → GPT-6.1 → GPT-6** 选择宿主实际支持且可调用的最高同角色型号。主代理沿用用户所选模型族。目前 Sol 依次检查 `gpt-6.2-sol`、`gpt-6.1-sol`、`gpt-6-sol`，Luna 只有 `gpt-6-luna`。当前代没有同角色型号或无法调用时继续检查下一代；全部候选均不可用时停止受影响工作并报告原始原因。禁止跨角色替代以及使用 GPT-5.6 或其他系列。子代理职责档位不得高于本次用户主请求，代际按同角色优先级独立判断。

2026-10-10 的规则曾将模型范围从 Aspen 的 GPT-5.6 改为 GPT-6／GPT-6.1，并禁止 GPT-5.6。用户当时的原话为「不允许使用任何GPT 5.6的模型，只允许使用GPT 6和GPT 6.1的模型。」「这个你可以直接改，对于 Markdown 的修改是可以直接改。」「你要更新一下这些 Markdown，就是说都要更新成GPT-6，GPT-6.1的系列。」

启动、派发和续接前核对模型实际绑定，显式指定合规型号。角色配置落盘与会话实际生效须分别核验。本文保留历史文件名，第三至第五节记录旧迁移示例与旧实测。

## 二、非 AWS 角色映射（现行选择规则）

| 角色 | 模型 | 推理强度 | 写入边界 | 用途 |
|---|---|---|---|---|
| 主代理 | 按用户所选模型族，Aspen 选 Sol 时首选 `gpt-6.2-sol` | 按主会话配置 | 继承当前会话 | 总体决策、整合、兜底 |
| `default` 子代理 | Sol，当前首选 `gpt-6.2-sol` | 默认 `medium`，允许更高 | 继承当前会话 | 通用子任务与整合 |
| `planner` | Sol，当前首选 `gpt-6.2-sol` | 默认 `medium`，允许更高 | `read-only` | 高歧义、多阶段计划与风险分析 |
| `reviewer` | Sol，当前首选 `gpt-6.2-sol` | 默认 `medium`，允许更高 | `read-only` | 正确性、安全性、回归与测试缺口审查 |
| `worker` | Sol，当前首选 `gpt-6.2-sol` | 默认 `medium`，允许更高 | 继承当前会话 | 边界清晰的代码或配置实现 |
| `tester` | Sol，当前首选 `gpt-6.2-sol` | 默认 `medium`，允许更高 | 继承当前会话 | 测试、复现、日志与失败归因，不修改源码 |
| `explorer` | `gpt-6-luna` | `high` | `read-only` | 快速代码路径、文件、依赖与事实检索 |

上表为选择规则。派发时以宿主实际支持的精确标识符为准，显式指定模型与推理强度。全历史 fork 无法覆盖时使用 `fork_turns="none"` 并提供自含委派说明。

Aspen 仓库内的 [角色配置](../codex/aspen/agents/)中，五个 Sol 角色仍绑定 `gpt-6.1-sol`，`explorer` 绑定 `gpt-6-luna`。`default`、`worker`、`explorer` 会覆盖同名内置角色，其余三个是自定义角色。并发、授权、写入隔离、验证和提交按 `AGENTS.md` 执行。

## 三、Aspen 全局配置（历史迁移示例）

以下是旧版 GPT-6／GPT-6.1 迁移为 `/home/hongzefu/.codex/config.toml` 拟定的值。当前型号按第一、二节选择。

```toml
model = "gpt-6.1-sol"
model_reasoning_effort = "high"
project_doc_max_bytes = 131072

[agents]
enabled = true
max_concurrent_threads_per_session = 32
default_subagent_model = "gpt-6-sol"
default_subagent_reasoning_effort = "medium"
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

## 四、旧版迁移的验收示例

以下检查对应第三节的旧版迁移示例：

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
assert config['agents']['max_concurrent_threads_per_session'] == 32
assert config['agents']['default_subagent_model'] == 'gpt-6-sol'
assert config['agents']['default_subagent_reasoning_effort'] == 'medium'

expected = {'default', 'planner', 'explorer', 'worker', 'reviewer', 'tester'}
seen = set()
for path in sorted((root / 'agents').glob('*.toml')):
    assert path.is_file() and not path.is_symlink(), path
    assert path.read_bytes() == (repo_agents / path.name).read_bytes(), path
    role = tomllib.loads(path.read_text())
    assert role['model'].startswith(('gpt-6-', 'gpt-6.1-')), (path, role['model'])
    assert role['name'] == path.stem, (path, role['name'])
    assert role['model_reasoning_effort'] == ('high' if 'luna' in role['model'] else 'medium'), path
    seen.add(role['name'])
assert seen == expected, (seen, expected)
print('ASPEN_GPT6_SERIES_ROLES=PASS')
PY
```

旧版验收方案要求新建任务，用 `/status` 核对当时预期的主代理 `gpt-6.1-sol/high`，再各启动一次角色并检查子任务详情里的实际模型与推理强度。现行规则的运行时验收按第一、二节核对所选型号与推理强度。旧实测中，用 `codex exec --ephemeral` 验收多代理报 `no rollout found for thread id`，临时主线程没有供子线程继承的 rollout。

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
