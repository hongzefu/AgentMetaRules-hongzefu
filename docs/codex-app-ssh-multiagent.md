# Codex SSH App 多代理并发验收（2026-09-26）

本记录验证 Codex SSH App 的新任务能否实际并行运行 16 个子代理，以及第 17 个是否会受宿主容量限制。配置为：

```toml
[agents]
max_concurrent_threads_per_session = 16
```

未设置 `default_subagent_model`，以保留默认继承行为；本次显式选择 `gpt-6-luna` 仅是实验选项。任务由同一 SSH App daemon 通过正式 `thread/start` 接口创建（App 的 `create_thread` 工具未暴露），并由 `codex_app list_threads` 确认。Codex 版本为 `0.157.0`，验收任务 ID 为 `01a0def6-52e3-7fa2-b191-b984a663bf93`。

| 判定 | 实测 | 结论 |
|---|---|---|
| `CONCURRENT_16` | 18:26:08.039Z 原始返回显示主代理及 probe01–probe16 均为 running | PASS |
| `MODELS_16` | 独立读取 16 个直接子代理会话，均为 `gpt-6-luna/low`；主线程为 `gpt-6-astra` | PASS |
| `LIMIT_17` | 18:26:12.249Z 创建 probe17 返回 `agent thread limit reached` | PASS |
| `CLEANUP` | 16 次中断均返回先前状态 running；最终 16 个探针均 interrupted，无子代理运行 | PASS，count=16 |

以上证据证明该新任务实际达到 16 路并发，并在第 17 路受限；不代表其他会话容量相同。旧任务树的 `AgentExecutionLimiter` 通过 `OnceLock/get_or_init` 初始化，正式配置热重载只更新配置，不替换既有 limiter，因此旧任务原有的 4 槽限制不承诺即时扩容。早先测试中，`0`、`-1` 和字符串 `unlimited` 被拒；`1000000` 仅解析接受，不能据此声称无限并发。`default_subagent_model` 的字符串可解析也不证明模型实际路由。

本次任务暴露的是 V2 多代理工具集（`spawn_agent` / `followup_task` / `send_message` / `wait_agent` / `interrupt_agent` / `list_agents`），没有 V1 的 `close_agent`；空闲子代理在容量不足时由宿主按 [`residency.rs`](https://github.com/openai/codex/blob/rust-v0.157.0/codex-rs/core/src/agent/control/residency.rs) 的 `is_unloadable` 规则自动卸载。

复验步骤：应用配置后创建新的 SSH App 任务；同时启动 16 个子代理并以 `list_agents` 确认同一时刻状态；核对各自 `session_meta` 的父任务身份及 `turn_context.model`、`effort`；再创建第 17 个并确认容量错误。配置解析不能替代真实并发验收。App `wait_threads` 正常完成，用时 207770 毫秒，未出现错误。原始结构化证据位于 `/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/codex-multiagent/20260926/acceptance.json`；取证后停止探针，`CLEANUP=PASS count=16`。

在原工作副本复核原始记录：

```bash
cd /data/hongzefu/robomme_benchmark_MotionJEPANewTask
command -v uv
uv run --no-sync python artifacts/codex-multiagent/20260926/verify_acceptance.py
```

该命令只读原始父子任务记录，核对同时运行快照、16 个模型与父任务身份、第 17 个拒绝及 16 次中断，四项均输出 `PASS`。`acceptance.json` 的 SHA-256 为 `256cde26fa084e6ef9dd15367068015b3879067b522c4447b1a2fa53f17edc91`；同目录 `cleanup.json` 为 `75144e524e57c751950271b2c0cdc092e0cf6f3b30e8fb0d181784aba4ae68db`。

参考：[OpenAI Subagents 文档](https://learn.chatgpt.com/docs/agent-configuration/subagents)；源码固定标签 [`rust-v0.157.0` 的 `AgentExecutionLimiter`](https://github.com/openai/codex/blob/rust-v0.157.0/codex-rs/core/src/agent/control/execution.rs)。
