## 通用规则（AgentMetaRules 正本副本）

下方标记块 `common-agents` 是 [AgentMetaRules-hongzefu](https://github.com/hongzefu/AgentMetaRules-hongzefu) 正本 `AGENTS.md`「强制规则」第 1–26 条与附录 A 的逐字副本（标记行 `src=` 记正本 commit、`blob=` 记块内容 blob id，**块内禁止手改**；同步核对命令 `uv run --no-project python /data/hongzefu/AgentMetaRules-hongzefu/scripts/sync_rules.py check --repo policy`）。上方「运行环境判定」是正本第 0 条的本仓库实例（判据表两列：环境 A = sled-vail 本机 + turbo 归档 + GreatLakes；环境 B = AWS 单机）。优先级：系统 / 开发者 / 用户当前指令 > 标记块外明确写出的覆盖项 > 标记块内的正本条目。平时只读本文件，不需要去读 GitHub 上的正本；正本改动经同步脚本回流。标记块之后是本仓库的覆盖项、占位符取值、项目 scope 与规则来源。

