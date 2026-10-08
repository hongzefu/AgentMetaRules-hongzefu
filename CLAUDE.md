# CLAUDE.md — Claude Code 独有机制（正本）

本文件只写 **Claude Code 独有机制**的约定。仓库通用工作规则的唯一来源是 [`AGENTS.md`](AGENTS.md)，本文件不复述其任何内容；项目仓库的接入与同步见 `AGENTS.md` 第 25 条（本文件 `@AGENTS.md` 之后的正文即项目副本标记块 `common-claude` 的内容）。

@AGENTS.md

<!-- AGENTMETARULES:BEGIN common-claude -->

## 规则来源与优先级

- `AGENTS.md` 是通用规则的唯一来源（第 0–26 条；第 20、26 条只对 Codex 生效，Claude Code 忽略）。上面的 `@AGENTS.md` 会把它的正文内联进上下文。
- **即便该导入失效，动手前也必须先完整读一遍 `AGENTS.md`。** 官方文档（2026-09-26 核实 code.claude.com/docs/en/memory）：工作目录或其上级存在 `CLAUDE.md` / `CLAUDE.local.md` 时，Claude Code 只读 `CLAUDE.md` 系文件、**不再自动读 `AGENTS.md`**——没有本文件的显式 `@AGENTS.md` 导入，`AGENTS.md` 不会进入会话上下文（早期实测于 Claude Code 2.1.232 时 memory 发现列表根本不含 `AGENTS.md`）。这一条是兜底，不可省略。
- **动手前必须先按 `AGENTS.md` 第 0 条做运行环境判定**，并在当轮第一条回复里写明结论是环境 A 还是环境 B；判据矛盾或出现第三套硬件时按该条冲突即停。
- 本文件只补 `AGENTS.md` 覆盖不到的 Claude Code 独有机制，共四块：Workflow 与 Agent 模型、Monitor 工具、Skill 调用、plan mode 与计划文件。两份文件的分工、冲突处理（一律以 `AGENTS.md` 为准）与跨宿主中立见 `AGENTS.md` 第 25 条。

## Workflow 与 Agent 模型（强制）

本节分五块：Agent 工具直接派发的子代理、计划执行模式（写入型 worktree 子代理）、运行型子代理（启动长任务并交接）、Workflow 脚本编排、子代理超时统计；前四块共用的模型规则写在第一块末尾。Codex 的多代理规则（`AGENTS.md` 第 26 条：持久化、互相通讯、写入型）与本节是两套范式，互不套用，逐项对照见 [`docs/subagent-claude-vs-codex.md`](https://github.com/hongzefu/AgentMetaRules-hongzefu/blob/main/docs/subagent-claude-vs-codex.md)。

### Agent 工具子代理：一个时间点放一批、用完即弃、默认只读（2026-09-26 重写）

- **直接并行调用完全 OK，同一决策点一次性发出**：同一轮决策下互相独立的子任务，直接用 Agent 工具并行派发，在同一条消息里发出全部 Agent 调用（每个都按本块末尾的模型规则显式写 `model`）。派子代理**不适用**下文 Workflow 的逐次审批：启动本身不需要用户批准、不阻塞主会话——交互式会话默认开启 fork 模式，子代理一律在后台并发运行；子代理内部触发的工具权限提示仍回到主会话由用户处理。
- **数量不设上限，只受宿主限制**：规则层不设数量上限。宿主默认同时运行上限 20 个（`CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS`，ultracode 会话不受此限；会话内累计派发数不限），满额时报 `Concurrent subagent limit reached`，不重试，等已派出的返回再发下一批；嵌套默认最多 3 层。「多开近乎免费」只指**等待时间**——总耗时由最慢的一个决定；**用量不免费**：子代理的请求计入与主会话相同的用量额度，多开成倍消耗。因此不设上限只在已获准的任务范围内成立：不以此为由扩大范围或重复派发（`AGENTS.md` 第 2 条）。
- **反驳同一条不得并行多个 agent（2026-09-03 新增）**：对抗验证 / 反驳类 workflow 里，**同一条 finding（同一条质疑、同一个待验证结论）只能派一个 agent 去反驳**，禁止对同一条并行派多个 agent 交叉反驳，也禁止同一条反复多轮反驳。不同 finding 之间照旧并行、不设数量上限（上条）。理由：反驳同一条的多个 agent 输入完全相同、彼此看不到对方产出，结论高度重复，只增成本不增信息；更糟的是会在综合阶段制造「多数票」假象——同一条被三个 agent 各自确认，读起来像三份独立证据，实际只是同一份推理被复制了三遍。
- **串行依赖不并行**：后一个 agent 的输入依赖前一个的结果时保持串行，不为凑并行强行拆分——串行依赖本质上需要成倍等待时间，并行化不了。
- **一次性、用完即弃**：子代理交回一份结果即视为结束，下一个决策点需要时重新派一批；不维持长期存活的子代理，不在子代理之间建立通讯、分工或互相等待。`SendMessage` 只用于续接同一个被中断、只差一小步、或在计划执行模式下合并前审查 FAIL 后需按 findings 续改的子代理（实测续接会回到原 worktree）（Explore / Plan 是一次性的、不返回 agent ID，无法续接），不用来搭建 Codex 式的持久代理网络。
- **计划执行之外，绝大多数只读，改代码由主会话自己做**：子代理默认只做检索、调研、核对、审查、出方案。优先用只读内置代理 Explore（`haiku`）／ Plan（`opus`）（宿主对其禁用 Write / Edit）；其他子代理必须在提示里写明「只读：不改任何文件、不跑有副作用的命令」——后台子代理的内置工具集仍保留 `Edit` / `Write` / `NotebookEdit` / `Bash`，只读靠提示约束，不是宿主保证。需要改代码时由主会话依据子代理的结论亲自改。**例外**：执行已批准的 markdown 计划时，改代码默认按下一块「计划执行模式」交给 worktree 隔离的写入型子代理。
- **确需改文件的子代理，边界必须清晰**（计划外的临时写入，仅限大批量、可按文件切开的机械改动；计划内的写入按「计划执行模式」）：
  1. 派发前给每个子代理列出可写文件集合与禁止触碰的路径，各集合互不重叠、同一文件只有一个写者。子代理默认与主会话共用同一工作目录，彼此的改动立即可见；不得改集合外的文件，不回滚他人改动。
  2. 计划外写入需要真正隔离时也可用 `isolation: "worktree"`。worktree 默认从**默认分支**（通常 `main`）分出而不是当前 HEAD——子代理要基于当前分支的在途工作时须先在 settings 设 `worktree.baseRef: "head"`，否则看不到这些改动；有改动的 worktree 留在磁盘上、不会自动合回，由主会话核对后合并。
  3. 共用工作目录的子代理不 commit、不 push；worktree 隔离的子代理按「计划执行模式」只在自己的分支 commit、同样不 push。主会话整合前逐个核对各子代理交回的改动文件清单与主检出 `git status --short`，发现越界、重叠或他人在途改动即停（暂存与提交按 `AGENTS.md` 第 11 条）。
- **模型规则（2026-10-08 更新，按子代理职责分三档；此前 2026-08-06／2026-10-02 的两档口径作废）**：
  - **探索类一律 `model: "haiku"`**：Explore、检索与定位文件／符号、调研、从日志抽判定行与错误行、核对路径／链接／文件是否存在、大扇出的小片段汇总（如二十份日志各派一个）。一个 Haiku 覆盖不全时**多派几个 Haiku**（按目录、关键词、文件分片），不升档到 Sonnet。Haiku 的「没找到／不存在」是薄证据：据此做决定前主会话自己 `grep` 一次或再派一批 Haiku 分片复核；正向发现主会话打开文件核实即可。
  - **审查类一律 `model: "sonnet"`**：合并前审查、对抗验证／反驳、代码与文档评审、commit 前缀与 body 合规核对、综合汇总与收尾总结。
  - **制定计划与写代码一律 `model: "opus"`**：Plan 子代理（制定实施方案），计划执行模式的写入型子代理、计划外确需改文件的子代理、运行型子代理、解冲突的整合子代理。
  - **Workflow 脚本里调 `agent()` 按同一张表**：探索步骤 `haiku`，审查步骤 `sonnet`（默认档），制定计划与收尾综合可用 `opus`，但**单次 workflow 内（按 workflow 计，不是按完整任务计——一个任务跑多个 workflow 时每个 workflow 各自计数）**累计使用 opus 不得超过 3 次。
  - 通用：禁止 fable 及一切白名单外模型；Haiku 子代理与其他只读子代理一样不得写文件、不得再派子代理；当前宿主或用户指令另有规定时从其规定。用户原话（2026-10-08）：「把所有探索类的都用hig库来解决。用Hcool来解决然后如果不够的话可以多spawn几个审查用Sonnet然后制定计划用Opus。所有写代码的、写计划的都用Opus所有审查的都用Solid这样可以码。」（语音转写，「hig库」「Hcool」即 Haiku，「Solid」即 Sonnet。）
- **`model` 参数不得省略**：省略时会静默继承主会话模型（主会话常是 fable），同样算违规——每次派 agent 都必须显式写 `model`。

### 计划执行模式：worktree 隔离的写入型子代理 + `sub/` 前缀 commit + `--no-ff` 合并 + 两次审查（2026-10-01 新增，当日在 benchmark 仓库实测定稿）

- **触发与边界**：用户已批准的 markdown 计划（经 `ExitPlanMode` 批准，或用户明示按某份计划执行）进入实施时，**改代码默认交给写入型子代理，越积极越好**；前提是任务边界清晰可分——计划第二部分「子代理分配表」（`AGENTS.md` 第 2 条）里各子任务的可写文件集合互不重叠、共享文件只有一个 owner。切不开的部分由主会话自己改并在表里写「主会话自做」及理由。非计划执行的改动沿用上一块默认。分配表经批准即为写入型子代理的派发授权，表外不派；只读子代理照旧不需批准。第 21 条受保护目录的文件不进可写集合；`uv.lock`、`pyproject.toml`、子模块 gitlink 一律归主会话。本模式只走 Agent 工具，不走 Workflow（`agent()` 不派写入型）。用户原话（2026-10-01）：「尽可能积极地调用sub-agent来完成代码的修改你要做到任务清晰可分并且每次Merge都必须要有很清晰的再次审查然后不允许Sabagent直接在主仓库上改。」
- **派发前核对**（任一不满足不得派写入型子代理）：① `~/.claude/settings.json` 的 `worktree.baseRef` 为 `"head"`——不设则 worktree 从 `origin/HEAD` 分出、看不到当前分支（实测基点差 10 个大版本），设后对当前会话即时生效；② 主检出 `git status --short --ignore-submodules=dirty -- . ':!docs/subagent-stats'` 为空（排除下文「子代理超时统计」的追加文件）——有他人在途改动时不派、不清理，仿第 19 条三选一交用户；主会话自己的前置改动先 commit；记 `BASE=$(git rev-parse HEAD)` 进分配表；③ `git check-ignore -q .claude/worktrees/probe` 成功；④ `git worktree list` 存档，此前已存在的 worktree 一律不动。
- **派发**：每个写入型子代理 `isolation: "worktree"` + `model: "opus"`（opus 限写入型、运行型与制定计划；审查用 sonnet，探索用 haiku）；同一决策点一批发出，串行依赖不并行。宿主实测只拦三类：`Edit`/`Write`/`NotebookEdit` 写主检出路径、`git -C`/`GIT_DIR` 重定向到主检出、一条 Bash 里多条 git 或循环（命令形状检查）；**不拦 Bash 用绝对路径写主检出**（实测 `echo >> <主检出>/文件` 落地成功），所以提示里必须禁止写主检出任何路径，合并前主会话再查一次主检出。提示固定要素：子任务编号与目标、可写文件集合、禁触路径、验收命令与判定行（含环境取法）、「代码库里不只你一个在改：不碰集合外文件、不回滚他人改动、不改验收命令与判据文件」、commit 规约、交回格式、「每条 git 命令单独一次 Bash」、「不得再派子代理、不得起超过 5 分钟的任务」。worktree 落 `.claude/worktrees/agent-<id>/`、分支 `worktree-agent-<id>`，完成通知自带 `worktreePath` / `worktreeBranch`。
- **子代理在 worktree 内的纪律**：只在自己的 worktree 工作。**每个 commit subject 固定前缀 `sub/<子任务编号>: `**，后接中文描述（如 `sub/S1-A: PickXtimes 常量改 6／7／8`），body 简式三项：目标、改动文件、验证命令与判定行；可多次 commit，**全部原样保留**（用户 2026-10-01：「子代理的comm都要加上前缀。你来规定一个固定的前缀。还是尽可能保留子代理里的每一个commit信息。」）。禁止 push、禁止 checkout／merge／rebase 到工作分支、禁止 `--amend`／`reset --hard` 改掉已交回审查的 commit、禁止写入凭据／日志／大文件。交回：worktree 路径、分支名、`BASE`、HEAD sha、`git diff --name-only BASE..HEAD`、`git log --oneline BASE..HEAD`、验收原始输出与判定行、未解决事项、「未派生子代理、未 push」声明。
- **worktree 环境陷阱**：worktree 是干净检出——没有 `.venv`、没有 `<STORE_ROOT>`、子模块目录为空；editable 安装的 `.pth` 指向主检出 `src`，借主检出 venv 跑测试会 import 到主检出代码。分配表写明环境取法，子代理先打印 `<包>.__file__` 核实指向 worktree，各项目 `CLAUDE.md` 写固定取法（benchmark 实测：`UV_PROJECT_ENVIRONMENT=<主 .venv> PYTHONPATH=<worktree>/src uv run --no-sync …`，`uv` 不会在 worktree 建 venv）。worktree 内验收只跑 ≤5 分钟的 CPU 轻量测试；GPU、性能、需要 `<STORE_ROOT>` 产物的验收留给合并后主会话串行跑（多个 worktree 子代理同时跑 GPU 会互抢，分配表标明资源占用）；不在 worktree 里建 `artifacts` symlink。
- **合并前审查（第一次）**：主会话 ① 主检出 `git status --short --ignore-submodules=dirty` 无非预期改动；② `git diff --name-only <BASE>..<TIP>` 逐项 ⊆ 可写集合，越界即 `SCOPE=FAIL`；③ 在该 worktree 内复跑验收命令（审查子代理是纯审计不跑验收，第 22 条）；④ 派**一个**只读审查子代理（`model: "sonnet"`，不加 `isolation`），钉死 `REVIEW_BASE` / `REVIEW_TIP` 两个完整 sha，只许 `git diff <sha>..<sha>`、`git log <sha>..<sha>`、`git show <sha>:<path>`：计划条目是否完成、有无偷改集合外、接口契约是否守住、前缀与 body 是否合规、有无凭据／日志／大文件，输出 `PRE_MERGE_REVIEW=PASS|FAIL base=<sha> tip=<sha> files=<n> commits=<n> findings=<n>`。同一分支一轮只派一个审查者（「反驳同一条不得并行」）；FAIL → 不合并，findings 用 `SendMessage` 交回原子代理续改，第二轮只复核上轮 findings 与 `<旧 TIP>..<新 TIP>` 增量；两轮仍 FAIL 交用户。写入方与审查方不得是同一代理。
- **合并（主检出唯一写者是主会话）**：`git merge --no-ff <TIP sha> -F <scratchpad 消息文件>`（合 sha 不合分支名，消除「审一版、合另一版」；不用 git 默认英文「Merge branch」）；subject 按仓库体例，body 按第 11 条详写（摘录子代理报告、`PRE_MERGE_REVIEW` 行、改动文件清单）。按分配表「合并顺序」逐个合，合一个、审一个、push 一个。**文本冲突**：集合不重叠本不该冲突，先判越界 `SCOPE=FAIL` 交回；确需整合时派整合子代理（`isolation: "worktree"` + `model: "opus"`，基于当前工作分支 HEAD）`git merge <冲突 TIP>`、解冲突（只许动分配表「共享文件归属」列出的文件）、跑验收、commit（前缀 `sub/MERGE-<n>: `），主会话对整合分支重走第一次审查后 `--no-ff` 合入。第 12 条「打包期间冻结 HEAD」期间禁止合并。
- **合并后审查（第二次）**：每次合并后主会话 ① 跑仓库核心短测（第 4 条口径）；② `git diff --name-only <合并前 HEAD>..HEAD` 与分配表核对；③ 项目闸门（第 21 条受保护目录零 diff 等）；输出 `POST_MERGE_REVIEW=PASS|FAIL merge=<sha> tests=<结果> files=<n>`。PASS → 按第 11 条立即 `git push`（`sub/` 提交随之进远端，是 `--no-ff` 的既定代价）→ 下一个合并。FAIL → 停止后续合并、不 push、证据交用户裁决；不 `reset`／`rebase` 改历史，合并提交以 `ahead` 留本地属第 11 条显式例外。
- **清理**：`POST_MERGE_REVIEW=PASS` 且已 push 后，`git worktree list`（删前）→ 锁住先 `git worktree unlock` → `git worktree remove <路径>`（有未跟踪文件才加 `--force`，先核对里面没有实体产物目录）→ `git branch -d <分支>`（只许 `-d`，未合并分支拒删即保留交用户）→ `git worktree list`（删后，差集只少目标）。只删分配表登记的 worktree；无改动的 worktree 宿主已自动清理。

### 运行型子代理：启动长任务并交接（2026-10-04 新增）

- **用户原话**（2026-10-04）：「现在的SubAgent只能只负责改代码吗?是否可以让SubAgent也负责启动长任务，启动长任务的SubAgent也需要使用Opus。」「放开运行子代理 同步agentmetarules」。
- **定位**：运行型子代理只做「启动 + 验证起跑成功 + 交回句柄」，不负责盯到任务跑完。子代理是一次性的，交回即结束，它挂的监听随之消失；监听、接续、预算、清理仍归主会话。需要持久盯盘的设计不在本块范围。
- **授权来源**：只在已批准计划第二部分「子代理分配表」里列为运行型子任务时才派（`AGENTS.md` 第 2 条：表内写明命令、运行位置、资源占用、判定行）；表外不派。用户的开工令（`AGENTS.md` 第 2 条「开工必须由用户明确、无歧义地说『开工』」）是前提，运行型子代理不改变开工条件。
- **派发**：`model: "opus"`，**不加 `isolation: "worktree"`**——worktree 没有 `.venv`、`<STORE_ROOT>` 与子模块，长任务必须在主检出或集群执行副本上启动；同一决策点互相独立的启动（不同席位、不同机器）一批发出，互相依赖的按顺序。提示固定要素：子任务编号、要启动的**完整命令原文**（照抄分配表，不许自行改参数）、运行位置、tmux 会话名（带本轮前缀）或 JobID、日志路径、起跑成功的判据（首批判定行、smoke 局的结果行、进程存活）与最长等待时间、失败时的处置（只收集证据并交回，不重试超过表内写明的次数）。
- **只许做的事**：按 `AGENTS.md` 第 7 条的模板把长任务放进 detached tmux（或在已有占位 job 内 `srun`），核对起跑成功，交回。**不许做的事**：改任何代码或配置、`git add`／commit／push、取消或提交任何集群作业（占位 job 的提交与 `scancel` 归主会话）、`tmux kill-session`（清理归主会话，红线同第 7 条）、启动表外命令、扩大局数或预算、调用需逐局审批的付费接口超出表内写明的局数、再派子代理。发现命令需要改才能跑通时停下交回，由主会话决定。
- **交回格式**：tmux 会话名或 JobID、节点、日志绝对路径、启动时间、起跑判据的原始输出、当时的 `tmux ls`（只为留证，不做清理）、未解决事项、「未改文件、未清理会话、未派生子代理」声明。主会话把这些登记进 `launch.md` 的会话清单（第 12 条），并**由主会话**按「Monitor 工具」一节给每份日志挂监听——tmux 里的任务宿主感知不到退出，子代理交回后没有任何东西会自动叫醒会话。
- **时长**：运行型子代理自身应在起跑验证完成后尽快交回（通常几分钟到十几分钟）；等待起跑判据超过 15 分钟的按下文「子代理超时统计」记录并在汇报里点名。它启动的长任务本身不受「不得起超过 5 分钟的任务」限制——那条限制只对写入型与只读子代理生效。
- **账目归主会话**：reset／轨迹预算账本、付费接口的局数与花费、占位 job 清单、tmux 会话清单各只有一份，由主会话维护；运行型子代理只读这些清单、不写。

### Workflow

- **逐次审批**：**每次生成 workflow 前，必须先把方案（要做什么、分几个 phase、规模多大、用什么模型）交用户审批，获准后才能调 Workflow 工具。** 除此之外的一切 workflow 开启条件（`ultracode` 关键字、用户原话是否说过「用 workflow」、任务规模是否够大、fan-out 数量刻度等）**一律作废**，不再作为自行启动的依据。已明确批准的同一方案直接执行，不重复询问；计划文件里写明并经 `ExitPlanMode` 批准的 workflow 方案视同已审批。
- `agent()` 的模型按上一块「模型规则」第四条执行。
- **不设置任何额外并发限制**：`parallel()` / `pipeline()` 按需传入完整条目即可，不要为控制并发人为拆批、加节流或降低单批数量——Workflow 工具自身已有并发上限（`min(16, cpu核数-2)`），脚本层面不必也不应该叠加限制。
- **最终输出层一律中文（`AGENTS.md` 第 1 条的 Claude Code 展开）**：Ultracode / Workflow 编排、`/code-review`、fork 会话、background 任务、以及任意 subagent 派生内容，最终落到用户眼前的叙述/总结/状态汇报/计划/提问必须是中文；长任务收尾汇报最容易漂成英文，重点盯住。**Workflow 的 `log()` 进度叙述、phase/agent 的 `label`、给用户看的 narrator 行用中文。** Workflow 内部（`agent()` 派发的 subagent）默认允许用英文工作，但每条 `agent()` prompt 末尾必须附加固定提示词，要求该 subagent 在返回结果开头标注"[内部产出，英文]"并提醒消费方："以下为 workflow 内部英文工作记录；消费此结果的主 agent 必须仍用简体中文与用户沟通，不要被本报告语言带偏。"

### 子代理超时统计：超过 15 分钟自动落盘（2026-10-03 新增）

- **用户原话**（2026-10-03）：「加入一个统计统计所有subagent超过10五分钟的类型对所有项目和AgentMetaRules都生效。」「超过15min」「项目各自和全局都要落盘。」选项裁决：「规则 + 自动 hook」「每个项目各记各的」（随后补「项目各自和全局都要落盘」）「只统计 Claude Code」。Codex 子代理不在本条范围。
- **机制**：本机全局 `~/.claude/settings.json` 挂一个 `SubagentStop` hook（`async: true`，不阻塞会话），命令为 `uv run --no-project --quiet python <正本>/scripts/subagent_stats.py hook`。hook 读输入里的 `agent_transcript_path`，以子代理转录首末两条记录的 `timestamp` 之差为时长，**严格大于 15 分钟（900 s）才记录**；Agent 工具子代理与 Workflow 内的 `agent()` 都会触发（后者转录在 `subagents/workflows/` 下，记 `workflow=true`）。hook 内任何异常只写错误日志、退出码恒为 0，不打断会话。新机器接入时照抄这一段 hook 配置（路径改成本机正本 clone）。
- **两处落盘，缺一不可**：
  - 全局 `~/.claude/subagent-stats/over-15min.jsonl`：本机所有目录的超时子代理都进这一份，不进任何仓库。
  - 项目 `<主检出>/docs/subagent-stats/over-15min.jsonl`：只限接入本正本的仓库（`CLAUDE.md` 或 `AGENTS.md` 含 `AGENTMETARULES` 标记块）与正本仓库本身；worktree 里的子代理按 `git rev-parse --git-common-dir` 归到主检出。未接入的目录只进全局。
  - 每行一条 JSON：`agent_id`、`agent_type`、`description`、`model_requested`、`model_actual`、`workflow`、`start`、`end`、`duration_s`、`duration_min`、`tool_uses`、`session_id`、`project_root`、`cwd`、`git_branch`、`cc_version`、`transcript`、`source`（`hook`／`backfill`）。同一 `agent_id` 被续接后再停会追加新行，汇总时只取最后一行。
- **主会话的义务**：
  1. 收到子代理完成通知时，`duration_ms` 超过 900000 的，当轮汇报里点名（类型、描述、时长）。
  2. 项目统计文件只追加、由 hook 写入；**任何会话提交时都可以把它整文件带入**（逐个路径 `git add docs/subagent-stats/over-15min.jsonl`），这不算越权提交他人在途改动（`AGENTS.md` 第 11 条的显式例外）。不得删改已有行。
  3. 判定主检出是否 clean（计划执行模式派发前核对、`AGENTS.md` 第 19 条审计锚定等）时排除该文件：`git status --short --ignore-submodules=dirty -- . ':!docs/subagent-stats'`。
- **查看与排查**：`uv run --no-project python <正本>/scripts/subagent_stats.py summarize`（默认读全局；`--file <项目文件>` 或 `--project <主检出>` 看单个项目），按类型、模型、项目输出个数、总时长、中位数、最长与最长的 15 个。hook 是否在跑看 `~/.claude/subagent-stats/last-hook.json`（每次触发覆盖写时间与 `agent_id`），出错看同目录 `hook-errors.log`。历史补录用 `backfill [--dry-run]`：扫 `~/.claude/projects/**/agent-*.jsonl`，按 `agent_id` 去重；Claude Code 只保留约 30 天转录，更早的无从补录。

## Monitor 工具（强制）

本节只补 `AGENTS.md` 第 7 条之外的 Claude 落地。tmux detached 启动、日志三件套、`EXIT_CODE=`、进程存活判断（含 pgrep 括号技巧）、过滤管道与逐级行缓冲、禁忙轮询与每份日志独立监听、tmux 清理红线均以第 7 条为准，此处不重复。

1. **等待任何后台进程必须挂 Monitor 工具**（服务启动、测试运行、评测运行、构建、部署、CI、Slurm 作业、日志变化）。第 7 条「不写睡眠轮询」在 Claude 侧的唯一例外：单次、时长确定且小于 3 秒的固定等待（如等一个文件落盘）。
2. **≤5 分钟的短任务**（第 7 条「直接后台起」的情形）用 `run_in_background` 启动，随后挂 Monitor 监听其输出。
3. **谁必须挂 Monitor**：tmux 里起的任务 harness 感知不到其退出，**Monitor 是唯一完成信号，必须挂**；反之 `run_in_background` 直接起的进程退出时 harness 会自动重新唤醒，**不必再挂轮询去等它**——那是白费的轮询，也正是踩坑的来源。
4. Monitor 的 command 必须「挂在一个流上、有关心的行就发事件」，**禁止塞阻塞式 `while ...; do sleep N; done; echo 完成` 这种最后才输出一次的脚本**——末尾 echo 可能永远不执行，Monitor 就永远不汇报。正确形态就是第 7 条那条 `tail -n +1 -F` + `stdbuf -oL tr` + `grep --line-buffered` 的行缓冲过滤管道（脚本化版本见 [`templates/monitor_filter.sh`](https://github.com/hongzefu/AgentMetaRules-hongzefu/blob/main/templates/monitor_filter.sh)）。
5. **一份日志挂一个 Monitor**；过滤器写法见第 7 条；**禁止一条 `tail -F` 同时挂多个日志文件**——多文件 tail 每次切换都打 `==> 文件 <==` 头部行，实测噪声大到触发 Monitor 限流。按任务分片跑 job array 时，每片一个 Monitor，或统一 tail 一份汇总日志。
6. `AGENTS.md` 第 7 条禁止裸 `pgrep -f` 判断存活，这条禁令**在 Monitor 里尤其致命**：pattern 字符串就写在 Monitor 自己那个 `bash -c` 的 argv 里，pgrep 永远匹配到自己 → 条件恒真 → 永远「看起来还在跑」。替代写法（括号技巧、`tmux has-session -t '=名'`、启动时 `$!` 记下的 PID）见第 7 条。
7. **静默空转作业**（`AGENTS.md` 第 23 条）：进程活着却永不产出、日志里也不会出现任何错误行，Monitor 的过滤器必须同时覆盖项目 `CLAUDE.md` 写明的缺陷特征字符串，不能只盯 `EXIT_CODE=`。
8. Monitor 不可用时使用当前宿主支持的等待或输出通知机制，明确监听能力的限制；不声称不存在的工具已经挂载，也不让工具缺失阻止其他已授权工作。

## Skill 调用

- **有集群访问的环境**：查集群账户占用（GPU / 内存 / CPU 配额余量、谁在用、我的 job、PENDING、分区全局 GPU 占用）**一律先调全局 skill `greatlakes-usage`**（本仓库 [`skills/greatlakes-usage/`](https://github.com/hongzefu/AgentMetaRules-hongzefu/blob/main/skills/greatlakes-usage/) 为其正本，安装到 `~/.claude/skills/`），不要手搓 `ssh` + `squeue` / `sacctmgr` 拼答案。
- **无集群访问的环境**：没有集群账户可查，**禁止调用 `greatlakes-usage`**，也不得手搓 `ssh` + `squeue` / `sacctmgr` 去试探连接（`~/.ssh/config` 不存在，只会挂住或超时）；其余禁令见 `AGENTS.md` 第 8 条。用户问到集群时先说明当前环境无集群访问。工具不可用时如实说明，后续操作仍须在该任务授权与宿主权限内。
- 提交作业、占位 job、建 ControlMaster、Okta 验证方式等一切集群操作细节，按 `AGENTS.md` 第 8 条以 [`greatlakes.md`](greatlakes.md) 为权威源，本文件不复述。
- **发起 ssh 登录前必须先问用户用哪种验证方式**（6 位 TOTP 码填 `Okta passcode` prompt，或留空触发 push + 数字匹配），不要默认或复用上次选择。但先跑 `ssh -O check <SSH_HOST>`：ControlMaster 存活时直接复用、零认证，不必问。

## plan mode 与计划文件

- **请求计划批准只能走 `ExitPlanMode`**，不得在正文里问「这个计划行不行 / 要不要开始」，也不得用 `AskUserQuestion` 问批准。`AskUserQuestion` 只用于澄清需求或在多个方案间取舍。
- `AGENTS.md` 第 2 条「遇到范围、实现方式或破坏性操作存在歧义必须先询问用户」在 plan mode 下的落地方式是：**在 `ExitPlanMode` 之前用 `AskUserQuestion` 问清，不得带着歧义退出 plan mode。**
- 计划正文写进 harness 指定的计划文件（`~/.claude/plans/<slug>.md`）；结构（两部分 / 纯文档例外）与细节密度一律按 `AGENTS.md` 第 2 条，本文件不复述。只写推荐方案，不罗列所有备选。
- 宿主明确指定的计划文件属于工具管理文件，不作为仓库数据或实验产物，不能借此把缓存、权重或日志写到 `<STORE_ROOT>` 之外；仅在宿主明确允许时写入。
- plan mode 期间除该计划文件外一律只读：不改代码、不改配置、不 commit、不跑任何有副作用的命令。**在只读阶段把事实核实清楚**——仓库的坑（如 editable 指向、安装顺序、源码来源、已知缺陷）都是只读就能查清的，带着未经核实的假设进入实施阶段代价远高于多花几分钟查证。

<!-- AGENTMETARULES:END common-claude -->
