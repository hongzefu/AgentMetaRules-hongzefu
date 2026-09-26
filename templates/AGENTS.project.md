# AGENTS.md

本文件规定 agent 在本仓库中的工作方式。所有仓库任务都必须先遵守本文件，再结合用户当前明确指令确定本轮范围。

**本文件构成**（自上而下）：

1. **头部**（本段）与「0. 运行环境判定」判据表——项目专属，手写；
2. **`common-agents` 标记块**——通用规则正本 `AGENTS.md` 通用块（「强制规则（最高优先级）」到「附录 A」表末）的**逐字副本**，由同步脚本填入，**不得手改**；BEGIN 行的 `src=` / `blob=` 记录副本来自正本哪个 commit、块内容的 blob id；
3. **项目专属内容**——标记块之后的项目专属规则（P1…Pn）、对正本的覆盖项、占位符取值、项目 scope、规则来源与未采用清单，手写。

**正本**：本机 `/data/hongzefu/AgentMetaRules-hongzefu`，GitHub [`hongzefu/AgentMetaRules-hongzefu`](https://github.com/hongzefu/AgentMetaRules-hongzefu)。平时只读本文件，不必去读正本；只在同步时（有正本检出的机器上）比对副本：

```bash
uv run --no-project python /data/hongzefu/AgentMetaRules-hongzefu/scripts/sync_rules.py check --repo <name>
```

`<name>` 是本仓库在正本 `sync-targets.json` 里的登记名。末行 `SYNC_SUMMARY=PASS` 即副本与正本一致；`FAIL` 时由正本侧 `apply` 回流，不在本仓库手改标记块。需要偏离通用规则时，写进下方「对正本的覆盖项」。

**优先级**：系统 / 开发者 / 用户当前指令 > 本文件标记块外明确写出的覆盖项与项目专属规则 > 标记块内的通用规则。覆盖项未涉及处以标记块为准；标记块未规定处以项目专属内容为准。项目目标、历史计划和示例命令不代表本轮实施授权。

## 0. 运行环境判定（每次开工第一步）

**每次会话开工前、执行任何带路径的命令之前，必须先跑一次判定，并把结论（环境 A 还是环境 B）写进当轮第一条回复**；判定未完成前不得执行任何带写入的命令。判定命令（只读，可整段贴）：

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

**冲突即停**：判定输出与上表任一行不符，或两套判据互相矛盾，一律停下来把原始输出交用户裁决，不得自行挑一套往下走，也不得按「多数判据像 A」推断；不属于任一列的第三套硬件同理。环境 B 的红线（如有）：一切持久化只落 `<SINGLE_NODE_ROOT>`；不连集群、不提交 Slurm；不访问不存在的共享存储（含 symlink 穿透与新建外链）。集群作业里把本表编码成逐行 `|| { echo …; exit 2; }` 的 fail-fast（骨架见正本 [`templates/run_in_hold.sh`](https://github.com/hongzefu/AgentMetaRules-hongzefu/blob/main/templates/run_in_hold.sh)）。

<!-- AGENTMETARULES:BEGIN common-agents src=<正本 sha> blob=<块 blob> -->
（由 sync_rules.py apply 填入，勿手改）
<!-- AGENTMETARULES:END common-agents -->

## 项目专属规则（P1…Pn）

编号用 `P1`、`P2`…，与标记块内的通用条号区分；只增不重编号。每条写明日期、用户原话或实测出处。

- **P1. <规则标题>**（<日期>，<出处>）：<正文>。

## 对正本的覆盖项（按条号；未列出的条目按标记块执行）

- **覆盖第 4 条（改动后验证）**：核心短测命令：`<命令>`；条件测试：`<命令>`；最小 smoke 的维度组合：`<…>`。
- **覆盖第 12 / 13 条（留档）**：`<DOC_ROOT>` 的具体子目录与章节体例（如与正本不同）。
- **覆盖第 21 条（受保护目录）**：`<PROTECTED_DIRS>` = `<目录>`；默认冻结项：`<文件>`，验证命令 `git diff --quiet HEAD -- <文件>`。
- **覆盖第 11 条（push）**：<若本仓库不继承自动推送授权，在此明确声明；否则删除本行>。
- <其它覆盖项，每条注明正本条号与理由>

## 占位符取值

| 占位符 | 本仓库取值 |
|---|---|
| `<WORK_ROOT>` | |
| `<ARCHIVE_ROOT>` | （无则写「无」） |
| `<STORE_ROOT>` | |
| `<DOC_ROOT>` | |
| `<FAST_LOCAL_CACHE_ROOT>` | |
| `<PY_INTERPRETER>` | |
| `<SHARED_ROOT>` / `<LOCAL_ROOT>` / `<SINGLE_NODE_ROOT>` | |
| `<GL_REPO>` / `<GL_SUBMIT>` / `<GL_ACCOUNT>` / `<GL_PARTITION>` / `<SSH_HOST>` | |
| `<PROTECTED_DIRS>` | |
| `<COMMIT_SUBJECT_STYLE>` | （照抄本仓库 `git log` 现行体例） |
| `<PLAN_EXEMPLAR>` | （写现名、注明所在仓库，并核实链接可达） |

## 项目 scope（未来工作，不代表当前实施授权）

- <仓库总体目标>
- <当前分支用途>
- <明确弃用、勿从历史翻出的内容>

## 规则来源与未采用清单

通用规则副本来自正本哪个 commit、块内容的 blob id，见上方 BEGIN 标记行的 `src=` / `blob=`（由 `sync_rules.py apply` 写入，回流时自动更新），不在此另写 sha。**未采用的通用条目及原因**：

- 第 <N> 条：<原因，如「本仓库只做评测、没有训练链路」>。
- …

Claude Code 独有机制见同目录 `CLAUDE.md`，集群提交规约见同目录 `greatlakes.md`（不上集群的项目写明「无」）；与本文件冲突时**一律以本文件为准**。
