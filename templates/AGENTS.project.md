# AGENTS.md

本文件规定 agent 在本仓库中的工作方式。所有仓库任务都必须先遵守本文件，再结合用户当前明确指令确定本轮范围。

**通用规则引用**：本仓库的通用工作规则以 [`AgentMetaRules-hongzefu`](https://github.com/hongzefu/AgentMetaRules-hongzefu) 的 `AGENTS.md` 为正本，引用 commit `<正本 sha>`（回流时更新）。本文件只写：① 项目专属的判据表与占位符取值；② 对正本条目的**显式覆盖项**（按正本条号引用）；③ 项目 scope 与规则来源。优先级：系统 / 开发者 / 用户当前指令 > 本文件明确写出的覆盖项 > 正本；本文件未覆盖处以正本为准。

## 运行环境判定（每次开工第一步）

按正本第 0 条执行。判定命令（只读，可整段贴）：

```bash
echo "repo=$(git rev-parse --show-toplevel 2>/dev/null)"
hostname
for p in <SHARED_ROOT> <LOCAL_ROOT> <SINGLE_NODE_ROOT> ~/.ssh/config; do
  printf '%s: %s\n' "$p" "$([ -e "$p" ] && echo 存在 || echo 不存在)"
done
nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | sort | uniq -c
command -v micromamba >/dev/null && echo "micromamba: 有" || echo "micromamba: 无"
```

判据表（同一行的两列互斥；口径日期写在列名里）：

| 判据 | 环境 A：<名称>（<口径日期>） | 环境 B：<名称>（<口径日期>） |
|---|---|---|
| 主机名（`hostname` 前缀） | | |
| 仓库根 | `<WORK_ROOT>` | |
| 共享存储路径 | | |
| 本机盘路径 | | |
| `~/.ssh/config`（集群 ControlMaster） | | |
| GPU | | |
| Slurm / 集群提交 | | |
| 原始数据 | | |
| 可做的事 | | |

**冲突即停**（正本第 0 条）。环境 B 的红线（如有）：一切持久化只落 `<SINGLE_NODE_ROOT>`；不连集群、不提交 Slurm；不访问不存在的共享存储（含 symlink 穿透与新建外链）。

## 占位符取值

| 占位符 | 本仓库取值 |
|---|---|
| `<WORK_ROOT>` | |
| `<ARCHIVE_ROOT>` | （无则写「无」） |
| `<STORE_ROOT>` | |
| `<DOC_ROOT>` | |
| `<FAST_LOCAL_CACHE_ROOT>` | |
| `<PY_INTERPRETER>` | |
| `<GL_REPO>` / `<GL_SUBMIT>` / `<GL_ACCOUNT>` / `<GL_PARTITION>` / `<SSH_HOST>` | |
| `<PROTECTED_DIRS>` | |
| `<COMMIT_SUBJECT_STYLE>` | （照抄本仓库 `git log` 现行体例） |
| `<PLAN_EXEMPLAR>` | |

## 对正本的覆盖项（按条号；未列出的条目按正本执行）

- **覆盖第 4 条（改动后验证）**：核心短测命令：`<命令>`；条件测试：`<命令>`；最小 smoke 的维度组合：`<…>`。
- **覆盖第 12 / 13 条（留档）**：`<DOC_ROOT>` 的具体子目录与章节体例（如与正本不同）。
- **覆盖第 21 条（受保护目录）**：`<PROTECTED_DIRS>` = `<目录>`；默认冻结项：`<文件>`，验证命令 `git diff --quiet HEAD -- <文件>`。
- **覆盖第 11 条（push）**：<若本仓库不继承自动推送授权，在此明确声明；否则删除本行>。
- <其它覆盖项，每条注明正本条号与理由>

## 项目 scope（未来工作，不代表当前实施授权）

- <仓库总体目标>
- <当前分支用途>
- <明确弃用、勿从历史翻出的内容>

## 规则来源

通用规则引用自 `AgentMetaRules-hongzefu` 的 `AGENTS.md` @ `<正本 sha>`。**未采用的条目及原因**：
- 第 <N> 条：<原因，如「本仓库只做评测、没有训练链路」>。
- …

Claude Code 独有机制（Workflow 与 Agent 模型、Monitor 工具、Skill 调用、plan mode）不写在本文件，见同目录 `CLAUDE.md`。两份文件冲突时**一律以本文件为准**。
