# CLAUDE.md

本文件是 Claude Code 的入口：下一行 `@AGENTS.md` 导入本仓库通用规则与项目规则；标记块内是正本 `CLAUDE.md` 通用块（Claude Code 独有机制）的逐字副本，由 `sync_rules.py apply` 填入、不得手改；项目专属补充写在标记块之后。两份文件冲突时一律以 `AGENTS.md` 为准。

@AGENTS.md

<!-- AGENTMETARULES:BEGIN common-claude src=<正本 sha> blob=<块 blob> -->
（由 sync_rules.py apply 填入，勿手改）
<!-- AGENTMETARULES:END common-claude -->

## 项目专属补充

- **Monitor 过滤词表补充**：本仓库作业的缺陷特征行 / 完成行：`<字符串>`（「静默空转」类缺陷必须把特征行加进过滤器，不能只盯 `EXIT_CODE=`）。
- **Skill 调用**：本仓库当前环境 <有 / 无> 集群访问；<有集群访问时> 查 `<GL_ACCOUNT>` 占用先调 `greatlakes-usage`。
- **plan mode 只读核实清单**：本仓库的坑（<如 editable 指向、安装顺序、已知缺陷>）都是只读就能查清的，进入实施前先核实。
