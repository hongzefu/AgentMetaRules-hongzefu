# 冲突与取舍

四个仓库同一条规则存在不同版本时，按「更新的日期 > 更完整的表述 > 与实配一致」三条取舍；每处取舍并列两边原文。源文件缩写同 [`sources.md`](sources.md)。

## A. commit 后是否必须 push

- global「git 提交」：`**每次 git commit 完成后必须立即 git push 同步到远端**，不得让已提交的 commit 滞留本地；本轮结束时 git status -sb 首行不得残留 ahead 计数。该同步已获用户长期授权，无需逐次确认。`
- policy AGENTS 规则 11：同上，另含具体远端 URL 与 gh 凭据配置。
- mjepa AGENTS 规则 11：`本仓库不继承源仓库的自动推送长期授权。只在当前任务已有推送授权时同步对应分支，不擅自修改 upstream 或凭据。`
- benchmark AGENTS 规则 7：无 push 条款；日志实际口径「提交但不推送」。

**取舍**：正本第 11 条写「默认 commit 后立即 push（该同步已获用户长期授权）」，并加**声明式例外**：项目 AGENTS.md 明确声明不继承、分支无 upstream、第三方 fork、无凭据一侧 → 先问用户。mjepa 的 AWS 分支与 benchmark 的第三方 fork 都落在例外分支里，不需要改它们的语义。

## B. 并行 spawn 是否设上限

- global / policy CLAUDE：`用 Agent 工具并行 spawn subagent **不设数量上限**——等待时间由最慢的一个决定，**多 spawn 近乎免费**，应尽可能积极地一次性并行派发`
- mjepa CLAUDE：`获准任务中真正独立的子任务可并行……不以「多开代理近乎免费」为依据扩大范围或重复派发。`

**取舍**：两者不矛盾——一个说范围内的并发度，一个说范围本身。正本 CLAUDE.md 合并为「已定范围内并行不设上限；不以此为由扩大范围或重复派发，并遵守宿主并发与资源限制」。

## C. `greatlakes.md` 权威源指向

- global「greatlakes 集群」：`**权威源是 MotionJEPA 仓库根目录 greatlakes.md（被 git 跟踪，以它为准）**。~/.claude/greatlakes.md 只是它的副本`
- evalgl AGENTS 规则 8：权威源指 `/data/hongzefu/robomme_policy_learning_MotionJEPA/greatlakes.md`（跨仓库绝对路径，环境 B 下不存在）。
- 实测：`~/.claude/greatlakes.md` 内容与 **policy** 版一致（含 robomme 放行记录节），与 MotionJEPA 版不一致；且比 policy 版旧一行（放行记录引用的计划文件名 `v2-framesamp-restructure-plan.md` 在 policy 已改为 `0827-framesamp-restructure-plan.md`）。policy 版与 mjepa 版的 GreatLakes 知识本体逐字同源，只差提交器路径 5 行与放行记录节。

**取舍**：权威源改为本仓库 `greatlakes.md`；项目仓库以「引用 + 副本同步」接入；保留 policy 规则 8「文件不存在时先问 account/partition/上限/路径，不得复制其他仓库配置」兜底。全局 CLAUDE.md 的指向已过期，建议改指本仓库（本仓库不动 `~/.claude/`）。

## D. 提交器路径

- global：`scripts/train-hongzefu/gl_submit.py`（两个仓库里都不存在）
- mjepa：`scripts/train-script-hongzefu/gl_submit.py`
- policy：`scripts/training/gl_submit.py`

**取舍**：正本放 `scripts/gl_submit.py`，文档用 `<GL_SUBMIT>` 占位，仓库路径由 `GL_REPO` 环境变量传入（两版原来把 `REPO` 硬编码在脚本里）。

## E. Monitor 示例是否带 `stdbuf -oL`

- policy CLAUDE Monitor 第 4 条示例：`tail -n +1 -F /path/to/run.log | tr '\r' '\n' \`（裸 `tr`）
- policy AGENTS 规则 7：`tr 写成 stdbuf -oL tr、awk 加 fflush()、sed 加 -u，只给 grep --line-buffered 不够（2026-08-24 epoch 基准与冷缓存复测两次实测踩中）`
- global / evalgl / mjepa：示例均为 `stdbuf -oL tr`

**取舍**：policy CLAUDE 的示例判为陈旧残留（与其自身 AGENTS 第 7 条矛盾），正本统一 `stdbuf -oL tr`。

## F. Codex 回退是否允许 `perl -0pi`

- benchmark AGENTS 规则 9 第 3 条：`只有不改变语义的纯机械替换才可回退到 perl -0pi，且匹配文本、目标文件和预期替换次数必须预先核验。`
- policy AGENTS 规则 20：`**禁止整文件覆盖**：本例外只允许补丁式修改，禁止改用 cat >、sed -i、perl -pi、脚本重写或其他整文件覆盖方式规避 apply_patch。`

**取舍**：以 policy 为准（更新、有 `patch --dry-run --batch --fuzz=0` 三步硬闸与应用后核对）；benchmark 版是 2026-08-18 从 MotionJEPA 搬来的早期版。补入 benchmark 独有的「删除操作不会因沙箱故障自动获得授权」「沙箱故障不是代码错误、最小命令重试」。

## G. commit subject 体例

- policy / mjepa：`commitV<大版本>.<小版本>: <中文描述>`，文档/修补/撤销用 `docs:` / `fix:` / `revert:`
- benchmark：`<大版本>.<小版本>[.<修订>] <中文描述>`（如 `2.9.2 变体简图出图验证与账本补记`）；日志 2026-08-18 明确记录「保留本仓库现行体例，不引入 MotionJEPA 的 commitV6.2:」
- global：`沿用该仓库既有的 message 风格（前缀习惯、编号体例照抄现有 git log）`

**取舍**：正本采 global 的元规则，两种具体体例作为实例附注，项目在 `<COMMIT_SUBJECT_STYLE>` 声明；benchmark 的版本号递增语义（大版本只在跨机制更新时递增、小版本每次 commit 递增、从 `git log` 最近一次接续）三家一致，并入正本。

## H. `UV_CACHE_DIR` 落点

- evalgl AGENTS 3(a)：`**UV_CACHE_DIR 必须显式设回 $HOME/.cache/uv**，不能靠「不设」……一旦设了 XDG_CACHE_HOME 指向 eval-store/cache/xdg，uv cache 会被一起拖到 NFS`
- policy AGENTS 规则 14：`改为逐项显式设置 UV_CACHE_DIR / XDG_CACHE_HOME / WANDB_* / HF_HOME 等缓存类环境变量指向 v1-store/cache/`
- env-b：`一切持久化只落 /scratch/hongze/（含 UV_CACHE_DIR=/scratch/hongze/.cache/uv）`

**取舍**：共同内核是「`UV_CACHE_DIR` 必须显式设定、不能靠默认或 XDG 继承」；落点因场景而异——工作副本在 NFS 时压回本机 `$HOME/.cache/uv`，单机环境指到工作盘。正本第 3 条写内核 + `<FAST_LOCAL_CACHE_ROOT>` 占位并说明两种场景。

## I. submodule + gitlink 与 vendoring

- policy AGENTS「策略评估的工作副本与第三方分支机制」：`保持官方 RoboMME/robomme_benchmark 来源与主仓库锁定的 gitlink……从原锁定提交建立 PolicyEvalThirdParty-<主仓库任务分支>`
- evalgl AGENTS 规则 5：`是普通源码目录，不能包含独立 .git、.gitmodules 或 gitlink。所有源码改动统一在顶层提交和推送，不再维护原 fork 的评测专用分支。`

**取舍**：同一批源码的两条治理路线，evalgl（2026-09-17/18）是后来演进的结果。正本第 24 条只抽通用内核：唯一真源、锁定版本、禁以 fork 最新 HEAD 替换、修改第三方须走专用分支再回主仓库；机制（submodule / vendoring）留项目二选一。

## J. 工作副本落在哪块盘

- policy 规则 13 环境 A：工作副本在本机 `/data`，turbo 只读归档；「策略评估」节：评估任务经用户授权用 turbo 副本（例外）。
- evalgl 规则 11：`**单一工作副本落在 /nfs/turbo/…/robomme-eval-GL，本机 /data 盘不落任何文件。**`
- policy 规则 13 环境 A：`本机 /data/hongzefu 的全局原始 H5 照旧永久保留`（与 evalgl「/data 不落任何文件」对同一块盘口径相反）

**取舍**：位置参数化为 `<WORK_ROOT>` / `<ARCHIVE_ROOT>`，并在第 14 条区分「工作副本落点」与「原始数据永久保留区」两个概念（evalgl 的表述把二者混为一谈）。附录 B 逐仓库列实际取值。

## K. ControlPersist 有效期

- `~/.ssh/config` 实配：`ControlPersist 30d`
- policy / mjepa greatlakes.md：30d
- skill `SKILL.md` / `gl_master.py`：14d；`gl_connect.py` 末行：「现在起 8 小时内」
- policy / mjepa `gl_submit.py` docstring 与两处 print：8h

**取舍**：统一 30d（与实配一致），skill 四文件与提交器一并改。

## L. Monitor grep 过滤词表

- global / policy：`全部完成|done|EXIT_CODE=|Error|Traceback|out of memory|找不到`
- evalgl / mjepa CLAUDE：`全部完成|EXIT_CODE=|Error|Traceback|out of memory|CUDA`
- benchmark CLAUDE：`全部完成|EXIT_CODE=|Error|Traceback|out of memory|找不到`

**取舍**：取并集 `全部完成|done|EXIT_CODE=|Error|Traceback|out of memory|CUDA|找不到`，模板脚本第二个参数可覆盖。

## M. 计划密度标杆文件名

- mjepa 规则 8：`v3-destructive-restructure-plan.md`
- policy 规则 2：`0829-destructive-restructure-plan.md`（2026-09-16 `MMDD-` 命名后的现名）
- benchmark 规则 10：`motion-memory-plan.md`（远端链接）+ 六个特征

**取舍**：正本用 `0829-destructive-restructure-plan.md` 并注明所在仓库；benchmark 六个特征保留为通用写法；项目可在 `<PLAN_EXEMPLAR>` 指定自己的标杆。

## N. 留档体例：三件套 vs 十二节 README

- mjepa AGENTS 规则 12：run 目录下单一 `README.md`，十二节体例（①一句话结论 … ⑫归档文件清单），两段式写入。
- evalgl AGENTS 规则 13：`launch.md` / `result.md` / `records/` 三件套，字段级展开。

**取舍**（2026-09-18 审计发现两套并列未说明关系后补）：正本第 12 条写明对应关系——`launch.md` 承载①–⑥节、`result.md` 承载①与⑦–⑪节、`records/` 对应⑫；项目沿用单文件体例时可把十二节合写进 run 目录 `README.md`，不再另建三件套；上级 `<DOC_ROOT>/README.md` 始终只是总索引。第 17 条同步注明两种体例。

## O. `--qos` 禁令的范围

- evalgl AGENTS 规则 8 要点提醒：`**不要写 --qos**`
- policy / mjepa greatlakes.md「资源约束」：`实测 --qos=interactive 在 chaijy2/spgpu 下报 Invalid qos specification，不要再用 —— 默认不指定 qos 即可；……正确的 qos 名待用 sacctmgr show assoc user=hongzefu format=qos（或 sacctmgr show qos）查清`

**取舍**：evalgl 的摘要句把针对 `--qos=interactive` 的实测禁令放大成了对整个参数的绝对禁止，与 greatlakes.md「正确 qos 名待查清」矛盾。正本第 8 条按 greatlakes.md 原文写「不要写 `--qos=interactive`，默认不指定 qos，确需指定时先 `sacctmgr` 查清」。

## 口径统一清单（不算冲突、但各处不一致的细节）

| 项 | 统一为 | 改动落点 |
|---|---|---|
| ControlPersist | 30d | greatlakes.md、scripts/gl_submit.py、skills/greatlakes-usage/{SKILL.md,gl_master.py,gl_connect.py,check_usage.py} |
| Monitor 示例 | `stdbuf -oL tr` | CLAUDE.md、AGENTS.md 第 7 条、templates/monitor_filter.sh |
| grep 词表 | 并集（见 L） | 同上 |
| 提交器路径 | `<GL_SUBMIT>` / `scripts/gl_submit.py` | greatlakes.md、SKILL.md |
| `check_usage.py` 头部用法 | `uv run --no-project --with pexpect`（原写 `--with paramiko`，与实际走 `gl_master` + 系统 ssh 不符） | skills/greatlakes-usage/check_usage.py |
| `check_usage.py` 常量 | `USER` / `ACCOUNT` 改为 `GLUSER` / `GL_ACCOUNT` 环境变量取值，默认值不变 | 同上 |
| `gl_submit.py` 仓库路径 | `GL_REPO` 环境变量（原硬编码 `REPO` 常量） | scripts/gl_submit.py |
| `gl_submit.py` push 修法第 3 条 | 新增 `GL_PUSH_SENTINEL` 握手（两版原都缺；⚠ 未实测） | scripts/gl_submit.py |
| 标杆文件名 | `0829-destructive-restructure-plan.md` | AGENTS.md 第 2 条 |
| Claude Code 版本号 | 正文去版本号，脚注保留「首次实测于 2.1.232」 | CLAUDE.md |
| tmux 精确匹配 | `-t '=名'` | AGENTS.md 第 7 条、templates |
| sbatch 判定的 `! command -v` 形态 | 统一为 `|| { echo …; exit 2; }`，退出码一致 | templates/job.sbatch |
| greatlakes.md 标题 | 「greatlakes Slurm 提交规约（通用正本）」（原两份都写「（MotionJEPA）」，policy 版属残留） | greatlakes.md |
| greatlakes.md `--output` 路径 | `<GL_REPO>/<STORE_ROOT>/logs/%x-%j.log`（原写 `…/MotionJEPA/output/logs/`，policy 版属残留） | greatlakes.md |
| run 覆盖参数写法 | 「覆盖 / 强制类参数（如 `overwrite=true`）」，泛化表述 + 举例；greatlakes.md 原 `overwrite=True` 统一小写 | AGENTS.md 第 6 条、greatlakes.md「调试 slurm 脚本」 |
| 调试脚本的覆盖白名单守卫 | 「项目若有覆盖项守卫测试会双重判违规」（原写 MotionJEPA 的 `test_train_script_overrides.py`） | greatlakes.md「调试 slurm 脚本」 |
| 判据表模板 | 首行加「主机名（`hostname` 前缀）」（判定命令已打印 `hostname`、sbatch 也以它为首条 fail-fast，表里原无行位） | AGENTS.md 第 0 条、templates/AGENTS.project.md |
