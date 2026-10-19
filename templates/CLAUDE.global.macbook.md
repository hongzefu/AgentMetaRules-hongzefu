# 全局指令（本机器所有项目通用）

本文件是 MacBook 的全局 `~/.claude/CLAUDE.md`，适用于该机器上的**所有项目和会话**。其中的规则优先级高于默认行为，必须严格遵守。通用部分（语言、子代理派发政策、跨会话沟通、uv、detached tmux、Monitor、git 提交纪律、开工与提交后的同步检查）是下方 `common-global` 标记块，由正本 [`CLAUDE.global.md`](https://github.com/hongzefu/AgentMetaRules-hongzefu/blob/main/CLAUDE.global.md) 经 `scripts/sync_rules.py apply --repo global-claude` 回流（本机需先 clone 正本并在 `sync-targets.json` 的 `machines` 段登记），块内勿手改；本机专属内容只写在标记外。不 `@` 导入正本。

## 运行环境（本机专属）

- 本机为 MacBook（macOS / zsh），单机环境，无集群、无 GPU 服务器访问；不要 ssh 试探集群、不调用集群相关 skill（`greatlakes-usage`）。
- `tmux` 需 `brew install tmux`；未安装时先提示用户安装，不擅自改用 nohup。
- 持久化文件落点、缓存目录与 GitHub 凭据按本机实际填写。
- 全局 `~/.claude/settings.json` 挂 `SessionStart`／`PostToolUse` 两个 hook（正本 `CLAUDE.md`「hook 配置」），兜底脚本路径填本机正本 clone 的 `scripts/repo_guard.py`。

<!-- AGENTMETARULES:BEGIN common-global -->
（由 sync_rules.py apply 填入，勿手改）
<!-- AGENTMETARULES:END common-global -->
