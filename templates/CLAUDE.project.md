# CLAUDE.md

本文件只写 **Claude Code 独有机制**的约定。仓库通用工作规则的唯一来源是 `AGENTS.md`，本文件不复述其任何内容。

@AGENTS.md

## 规则来源与优先级

- `AGENTS.md` 是本仓库通用规则的唯一来源（通用条目引用 [`AgentMetaRules-hongzefu`](https://github.com/hongzefu/AgentMetaRules-hongzefu) 正本 @ `<正本 sha>`）。上面的 `@AGENTS.md` 会把它的正文内联进上下文。
- **即便该导入失效，动手前也必须先完整读一遍 `AGENTS.md`。** 实测 Claude Code 的 memory 发现列表只含 `CLAUDE.md` / `CLAUDE.local.md` / `.claude/rules`，**不含 `AGENTS.md`**——没有本文件的显式导入时，`AGENTS.md` 不会进入会话上下文。这一条是兜底，不可省略。
- **动手前必须先做运行环境判定**：执行 `AGENTS.md`「运行环境判定」一节的判定命令，并在当轮第一条回复里写明结论是 **环境 A：<名称>** 还是 **环境 B：<名称>**。判据互相矛盾、或出现第三套硬件时，把原始输出交用户裁决，不得自行挑一套往下走。
- **两份文件冲突时一律以 `AGENTS.md` 为准**，本文件仅在 `AGENTS.md` 未规定处生效。

## Claude Code 独有机制

Workflow 与 Agent 模型、Monitor 工具、Skill 调用、plan mode 与计划文件四块，全部以 `AgentMetaRules-hongzefu` 的 [`CLAUDE.md`](https://github.com/hongzefu/AgentMetaRules-hongzefu/blob/main/CLAUDE.md) 正本 @ `<正本 sha>` 为准，本文件只写项目专属补充：

- **Monitor 过滤词表补充**：本仓库作业的缺陷特征行 / 完成行：`<字符串>`（正本 Monitor 第 7 条）。
- **Skill 调用**：本仓库当前环境 <有 / 无> 集群访问；<有集群访问时> 查 `<GL_ACCOUNT>` 占用先调 `greatlakes-usage`。
- **plan mode 只读核实清单**：本仓库的坑（<如 editable 指向、安装顺序、已知缺陷>）都是只读就能查清的，进入实施前先核实。
