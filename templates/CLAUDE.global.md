# 全局指令（本机所有项目通用）

本文件是本机的全局 `CLAUDE.md`（`$CLAUDE_CONFIG_DIR/CLAUDE.md`，默认 `~/.claude/CLAUDE.md`），对本机**所有目录、所有会话**生效，包括没有接入 AgentMetaRules 正本的目录。通用部分是下方 `common-global` 标记块，由正本 [`CLAUDE.global.md`](https://github.com/hongzefu/AgentMetaRules-hongzefu/blob/main/CLAUDE.global.md) 经 `scripts/sync_rules.py apply --repo global-claude` 回流，块内勿手改；本机专属内容只写在标记外。不 `@` 导入正本。

## 本机专属

- <机器名称与环境判定结论，如「AWS p4de 单机，各项目的环境 B」「MacBook，无集群、无 GPU」>
- <持久化文件落点与缓存目录约定（`HF_HOME`、`UV_CACHE_DIR` 等）>
- <集群访问有无；无则写明不 ssh 试探、不调用 `greatlakes-usage` skill>
- <GitHub 凭据：用哪把 key、有没有 `gh`>
- <Claude Code 配置目录（`CLAUDE_CONFIG_DIR`）若非默认 `~/.claude`，写明>
- <正本 clone 路径；本机在 `sync-targets.json` `machines` 段登记的键>

<!-- AGENTMETARULES:BEGIN common-global -->
（由 sync_rules.py apply 填入，勿手改）
<!-- AGENTMETARULES:END common-global -->
