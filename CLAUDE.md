# CLAUDE.md — Claude Code 独有机制（正本）

本文件只写 **Claude Code 独有机制**的约定。仓库通用工作规则的唯一来源是 [`AGENTS.md`](AGENTS.md)，本文件不复述其任何内容；项目仓库的接入与同步见 `AGENTS.md` 第 25 条（本文件 `@AGENTS.md` 之后的正文即项目副本标记块 `common-claude` 的内容）。

@AGENTS.md

<!-- AGENTMETARULES:BEGIN common-claude -->

## 规则来源与优先级

- `AGENTS.md` 是通用规则的唯一来源（第 0–26 条；仅第 20 条只对 Codex 生效，Claude Code 忽略；第 26 条统一两宿主子代理职责，宿主专节各自执行）。上面的 `@AGENTS.md` 会把它的正文内联进上下文。
- **即便该导入失效，动手前也必须先完整读一遍 `AGENTS.md`。** 官方文档（2026-09-26 核实 code.claude.com/docs/en/memory）：工作目录或其上级存在 `CLAUDE.md` / `CLAUDE.local.md` 时，Claude Code 只读 `CLAUDE.md` 系文件、**不再自动读 `AGENTS.md`**——没有本文件的显式 `@AGENTS.md` 导入，`AGENTS.md` 不会进入会话上下文（早期实测于 Claude Code 2.1.232 时 memory 发现列表根本不含 `AGENTS.md`）。这一条是兜底，不可省略。
- **动手前必须先按 `AGENTS.md` 第 0 条做运行环境判定**，并在当轮第一条回复里写明结论是环境 A 还是环境 B；判据矛盾或出现第三套硬件时按该条冲突即停。
- 本文件只补 `AGENTS.md` 覆盖不到的 Claude Code 独有机制，共四块：Workflow 与 Agent 模型、Monitor 工具、Skill 调用、plan mode 与计划文件。两份文件的分工、冲突处理（一律以 `AGENTS.md` 为准）与跨宿主中立见 `AGENTS.md` 第 25 条。

## Workflow 与 Agent 模型（强制）

本节分五块：Agent 工具的按批生命周期、独立 worktree 修改与整合操作、运行型起跑交接、Workflow 脚本编排、子代理超时统计。职责、显式模型、建议派发表与运行／修代码边界统一引用 `AGENTS.md` 第 26 条；本节保留 Claude Code 的 Harness 操作和一次性、按批交回生命周期，不将 Codex 的持久代理网络套过来。官方材料和带日期历史实测见 [`docs/subagent-claude-vs-codex.md`](https://github.com/hongzefu/AgentMetaRules-hongzefu/blob/main/docs/subagent-claude-vs-codex.md)。

### Agent 工具子代理：同一决策点按批派发、一次性交回（2026-10-10 统一职责）

- **共同政策来源**：模型与角色一律按 `AGENTS.md` 第 26 条显式选择：探索 `haiku` 只读自主按需派，规划／修改文件／解冲突／运行 `opus`，审查 `sonnet`。覆盖不全多派 Haiku，不升档探索；大角色不降档。没有计划分工先形成明确委派，有计划尽量跟随；调整在已授权范围内说明原因与实际归属，不反复请示，不扩大实施、资源、费用或保护代码授权。
- **直接并行调用、同一决策点一次性发出**：独立任务用 Agent 工具在同一条消息里发出全部调用，显式写 `model`。直接 Agent 派发不适用下文 Workflow 的逐次审批；后台调用不阻塞主会话，子代理内工具权限提示仍按宿主权限处理。
- **数量按当前宿主容量**：规则不叠加人为数量限制；`CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS` 要求 64，配置与历史实测见下文 Workflow「并发上限必须设为 64」。满额报 `Concurrent subagent limit reached` 时等已派批次返回，不忙重试；嵌套等真实工具约束按当前宿主。多开只缩短等待时间，用量仍计入主会话额度，不重复派发、不扩大授权。
- **同一 finding 不重复并发反驳**：同一质疑只派一个审查代理，不对同一条并行复制或反复多轮反驳；不同 finding 可以并发。重复输入不是独立证据，不能靠多数票凑结论。
- **串行依赖不并行**：后一个代理依赖前一个交付时顺序执行。
- **一次性、按批交回**：一份结果交回即结束，下一决策点需要时新派一批，不维持长期代理网络。`SendMessage` 仅用于同一被中断、只差一步或合并前审查失败需续改的代理；是否返回可续接 id 按宿主实际能力，Explore／Plan 的历史一次性限制不冒充所有版本事实。
- **只读与写入明确分工**：探索／检索代理的委派必须写「只读，不改文件、不跑有副作用的命令」，优先用 Explore（`haiku`）；规划可用 Plan（`opus`）。后台代理内仍可能有 `Edit`／`Write`／`NotebookEdit`／`Bash`，只读提示不是权限沙箱。修改文件统一走下一块的独立 worktree 流程，含计划外已授权修改；删除原「计划外由主会话亲自改」和「可共用主目录写机械改动」分支。
- **模型不可用即停并报告**：按第 26 条核实职责档位、主请求上限与实际参数，不继承模型绕过，不静默换档；Workflow 的 `agent()` 也按同一角色政策执行，不再设人工最多 3 次 opus 限制。

### 计划执行模式：worktree 隔离的写入型子代理 + `sub/` 前缀 commit + `--no-ff` 合并 + 两次审查（2026-10-01 新增，当日在 benchmark 仓库实测定稿）

- **触发与边界**：用户已授权的代码／文件修改尽可能拆给独立 worktree 子代理，任务可写集合不重叠、共享文件单一 owner；切不开的关键路径由主会话自做并说明理由。计划分工尽量跟随，调整和无计划分工按 `AGENTS.md` 第 26 条先明确委派，不再以「表外不派」限制已授权拆分。受保护目录仍按第 21 条逐项批准；`uv.lock`、`pyproject.toml`、子模块 gitlink 由主代理明确单一归属，可按职责委派独立 worktree 修改；依赖与第三方修改仍须满足第 3、21、24 条和已授权范围。本流程用 Agent 工具，不走 Workflow（`agent()` 不派写入型）。2026-10-01 用户原话：「尽可能积极地调用sub-agent来完成代码的修改你要做到任务清晰可分并且每次Merge都必须要有很清晰的再次审查然后不允许Sabagent直接在主仓库上改。」
- **派发前核对**（任一不满足不得派写入型子代理）：① `~/.claude/settings.json` 的 `worktree.baseRef` 为 `"head"`（全局与仓库项目级 `.claude/settings.json` 都设，见 Workflow 一节「并发上限必须设为 64」的两处落地与新机器询问）——不设则 worktree 从 `origin/HEAD` 分出、看不到当前分支（实测基点差 10 个大版本），设后对当前会话即时生效；② 记录主检出 `git status --short --ignore-submodules=dirty -- . ':!docs/subagent-stats'`（排除下文「子代理超时统计」的追加文件），固定已提交的 `BASE=$(git rev-parse HEAD)` 进委派；不触碰或携带无关在途改动，无关 dirty 不阻断独立 worktree 派发。只有任务依赖未提交内容、写集／整合将冲突或基线不明时，暂停受影响派发并交回主会话核实；需要纳入的主会话前置改动先按第 11 条提交，纯审计另按第 19 条锚定；③ `git check-ignore -q .claude/worktrees/probe` 成功；④ `git worktree list` 存档，此前已存在的 worktree 一律不动。
- **派发**：每个写入型子代理 `isolation: "worktree"` + `model: "opus"`（opus 限写入型、运行型与制定计划；审查用 sonnet，探索用 haiku）；同一决策点一批发出，串行依赖不并行。宿主实测只拦三类：`Edit`/`Write`/`NotebookEdit` 写主检出路径、`git -C`/`GIT_DIR` 重定向到主检出、一条 Bash 里多条 git 或循环（命令形状检查）；**不拦 Bash 用绝对路径写主检出**（实测 `echo >> <主检出>/文件` 落地成功），所以提示里必须禁止写主检出任何路径，合并前主会话再查一次主检出。提示固定要素：子任务编号与目标、可写文件集合、禁触路径、验收命令与判定行（含环境取法）、「代码库里不只你一个在改：不碰集合外文件、不回滚他人改动、不改验收命令与判据文件」、commit 规约、交回格式、「每条 git 命令单独一次 Bash」、「递归派发遵守主代理明确职责与下级写集、禁触、依赖、交付和验收，核实宿主实际嵌套能力；未划清下级边界不得递归派发；不得起超过 5 分钟的任务」。worktree 落 `.claude/worktrees/agent-<id>/`、分支 `worktree-agent-<id>`，完成通知自带 `worktreePath` / `worktreeBranch`。
- **子代理在 worktree 内的纪律**：只在自己的 worktree 工作。**每个 commit subject 固定前缀 `sub/<子任务编号>: `**，后接中文描述（如 `sub/S1-A: PickXtimes 常量改 6／7／8`），body 简式三项：目标、改动文件、验证命令与判定行；可多次 commit，**全部原样保留**（用户 2026-10-01：「子代理的comm都要加上前缀。你来规定一个固定的前缀。还是尽可能保留子代理里的每一个commit信息。」）。禁止 push、禁止 checkout／merge／rebase 到工作分支、禁止 `--amend`／`reset --hard` 改掉已交回审查的 commit、禁止写入凭据／日志／大文件。交回：worktree 路径、分支名、`BASE`、HEAD sha、`git diff --name-only BASE..HEAD`、`git log --oneline BASE..HEAD`、验收原始输出与判定行、未解决事项、如实声明有无经明确划界且宿主支持的下级代理及其职责／文件归属，以及「未 push」。
- **worktree 环境陷阱**：worktree 是干净检出——没有 `.venv`、没有 `<STORE_ROOT>`、子模块目录为空；editable 安装的 `.pth` 指向主检出 `src`，借主检出 venv 跑测试会 import 到主检出代码。分配表写明环境取法，子代理先打印 `<包>.__file__` 核实指向 worktree，各项目 `CLAUDE.md` 写固定取法（benchmark 实测：`UV_PROJECT_ENVIRONMENT=<主 .venv> PYTHONPATH=<worktree>/src uv run --no-sync …`，`uv` 不会在 worktree 建 venv）。worktree 内验收只跑 ≤5 分钟的 CPU 轻量测试；GPU、性能、需要 `<STORE_ROOT>` 产物的验收留给合并后主会话串行跑（多个 worktree 子代理同时跑 GPU 会互抢，分配表标明资源占用）；不在 worktree 里建 `artifacts` symlink。
- **合并前审查（第一次）**：主会话 ① 主检出 `git status --short --ignore-submodules=dirty` 无非预期改动；② `git diff --name-only <BASE>..<TIP>` 逐项 ⊆ 可写集合，越界即 `SCOPE=FAIL`；③ 在该 worktree 内复跑验收命令（审查子代理是纯审计不跑验收，第 22 条）；④ 派**一个**只读审查子代理（`model: "sonnet"`，不加 `isolation`），钉死 `REVIEW_BASE` / `REVIEW_TIP` 两个完整 sha，只许 `git diff <sha>..<sha>`、`git log <sha>..<sha>`、`git show <sha>:<path>`：计划条目是否完成、有无偷改集合外、接口契约是否守住、前缀与 body 是否合规、有无凭据／日志／大文件，输出 `PRE_MERGE_REVIEW=PASS|FAIL base=<sha> tip=<sha> files=<n> commits=<n> findings=<n>`。同一分支一轮只派一个审查者（「反驳同一条不得并行」）；FAIL → 不合并，findings 用 `SendMessage` 交回原子代理续改，第二轮只复核上轮 findings 与 `<旧 TIP>..<新 TIP>` 增量；两轮仍 FAIL 交用户。写入方与审查方不得是同一代理。
- **合并（主检出唯一写者是主会话）**：`git merge --no-ff <TIP sha> -F <scratchpad 消息文件>`（合 sha 不合分支名，消除「审一版、合另一版」；不用 git 默认英文「Merge branch」）；subject 按仓库体例，body 按第 11 条详写（摘录子代理报告、`PRE_MERGE_REVIEW` 行、改动文件清单）。按分配表「合并顺序」逐个合，合一个、审一个、push 一个。**文本冲突**：集合不重叠本不该冲突，先判越界 `SCOPE=FAIL` 交回；确需整合时派整合子代理（`isolation: "worktree"` + `model: "opus"`，基于当前工作分支 HEAD）`git merge <冲突 TIP>`、解冲突（只许动分配表「共享文件归属」列出的文件）、跑验收、commit（前缀 `sub/MERGE-<n>: `），主会话对整合分支重走第一次审查后 `--no-ff` 合入。第 12 条「打包期间冻结 HEAD」期间禁止合并。
- **合并后审查（第二次）**：每次合并后主会话 ① 跑仓库核心短测（第 4 条口径）；② `git diff --name-only <合并前 HEAD>..HEAD` 与分配表核对；③ 项目闸门（第 21 条受保护目录零 diff 等）；输出 `POST_MERGE_REVIEW=PASS|FAIL merge=<sha> tests=<结果> files=<n>`。PASS → 按第 11 条立即 `git push`（`sub/` 提交随之进远端，是 `--no-ff` 的既定代价）→ 下一个合并。FAIL → 停止后续合并、不 push、证据交用户裁决；不 `reset`／`rebase` 改历史，合并提交以 `ahead` 留本地属第 11 条显式例外。
- **清理**：`POST_MERGE_REVIEW=PASS` 且已 push 后，`git worktree list`（删前）→ 锁住先 `git worktree unlock` → `git worktree remove <路径>`（有未跟踪文件才加 `--force`，先核对里面没有实体产物目录）→ `git branch -d <分支>`（只许 `-d`，未合并分支拒删即保留交用户）→ `git worktree list`（删后，差集只少目标）。只删分配表登记的 worktree；无改动的 worktree 宿主已自动清理。

### 运行型子代理：按授权启动、验证起跑并交接（2026-10-10 统一边界）

- **用户原话与共同政策**：2026-10-04：「现在的SubAgent只能只负责改代码吗?是否可以让SubAgent也负责启动长任务，启动长任务的SubAgent也需要使用Opus。」「放开运行子代理 同步agentmetarules」。现行职责、提交 job 权限与运行／修复分工以 `AGENTS.md` 第 26 条为准。
- **定位与生命周期**：Claude 运行代理只做启动、验证起跑、交回句柄，按批交回即结束。持续监听、接续、预算与清理由主会话承担；子代理结束会带走自己的监听，不能声称后台 tmux 自动唤醒主会话。
- **授权与委派**：满足第 2 条开工与现有授权边界；有计划尽量按分配表，无分工先写明确运行委派。委派给出完整命令、确定代码版本、运行位置、资源／费用／reset／轨迹预算、tmux 名或已有 JobID／新 job 规格、日志和输出路径、起跑判据、最长等待、失败处置和重试上限。无需重复申请已批准范围，不能自行扩大。
- **派发操作**：显式 `model: "opus"`，运行时不加 `isolation: "worktree"`——在已指定且有环境／产物的主检出或集群执行副本启动，不把运行权当源代码写入权。独立启动同一决策点按批派，存在依赖则顺序执行。第 7 条 detached tmux 和第 8 条集群规范照旧。
- **可执行操作**：按明确授权提交新 job，**立即交回 JobID**，或在已有占位 job 内按确定版本与命令用 `srun` 启动工作负载。提交回执或状态不明先查已有作业，禁止重复提交；不能自行取消 job 或清理 tmux，会话／作业清单和唯一资源清理归主会话。
- **禁止操作与修复交接**：不得改代码、配置、启动脚本、依赖或参数，不作运行时补丁，不 `git add`／commit／push，不自行转代码代理或再派修复代理。需要修代码时收集证据交主会话；主会话另派独立 worktree 修复代理，审查、验证、整合后再交确定版本和命令续跑。不得启动委派外命令、超出重试／预算／费用上限。
- **如实交回**：JobID／tmux 名、节点、启动时间、日志绝对路径、起跑判据原始输出、`tmux ls` 留证、实际尝试和预算消耗、产物／程序账本写入、未解决事项。正常程序产生日志、结果和授权账本更新允许写入指定路径；不再要求虚假的「未改文件」声明。主会话立即登记 `launch.md` 的句柄清单并按 Monitor 节给每份日志挂监听。
- **时长与账目**：起跑验证完成尽快交回；自身超过 15 分钟按下文超时统计记录。被启动的长任务按第 7／12 条执行；写入型／只读子代理不得起超过 5 分钟任务的既有操作约束不套到运行代理。主会话统一掌握唯一预算、费用和句柄账本，运行代理不另建账本；授权程序的正常账本更新如实登记。

### Workflow

- **逐次审批**：**每次生成 workflow 前，必须先把方案（要做什么、分几个 phase、规模多大、用什么模型）交用户审批，获准后才能调 Workflow 工具。** 除此之外的一切 workflow 开启条件（`ultracode` 关键字、用户原话是否说过「用 workflow」、任务规模是否够大、fan-out 数量刻度等）**一律作废**，不再作为自行启动的依据。已明确批准的同一方案直接执行，不重复询问；计划文件里写明并经 `ExitPlanMode` 批准的 workflow 方案视同已审批。
- `agent()` 的显式模型按 `AGENTS.md` 第 26 条职责执行，不设人工 opus 次数上限；本节真实工具限制与逐次审批保留。
- **不设置任何额外并发限制**：`parallel()` / `pipeline()` 按需传入完整条目即可，不要为控制并发人为拆批、加节流或降低单批数量——Workflow 工具自身已有并发上限（按下条设为 64），脚本层面不必也不应该叠加限制。
- **并发上限必须设为 64（2026-10-08 新增）**：宿主默认 Workflow 并发闸门为 `Math.min(16, Math.max(2, CPU核数-2))`、Agent 工具子代理同时运行上限为 20，一律改为 64。两处落地、缺一不可：① 每台机器的全局 `~/.claude/settings.json` 的 `env` 段；② 每个接入本正本的仓库（含正本本身）提交一份项目级 `.claude/settings.json`，内容只有这一段 `env` 加 `worktree.baseRef: "head"`（计划执行模式派写入型子代理的前提，2026-10-08 用户要求一并设为全局），换机器、新 clone 也自动生效。写法：

  ```json
  { "env": { "CLAUDE_CODE_WORKFLOW_MAX_CONCURRENT_AGENTS": "64", "CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS": "64" }, "worktree": { "baseRef": "head" } }
  ```

  **新机器上先问是否写进全局（2026-10-08 新增）**：项目级 `.claude/settings.json` 只在该仓库里生效。每次会话开工时（与 `AGENTS.md` 第 0 条运行环境判定同一步），只读检查本机 `~/.claude/settings.json` 的 `env` 是否已含这两个变量且都为 `"64"`、`worktree.baseRef` 是否为 `"head"`；任一缺失或不符，说明这是一台新机器或未接入的机器，**必须在当轮第一条回复里问用户要不要把这两个变量与 `worktree.baseRef: "head"` 写进本机全局 `~/.claude/settings.json`**（写进全局后，本机所有目录、包括未接入正本的目录都生效）。用户同意才写，只合并进 `env` 段与 `worktree.baseRef`，不动其他键，写后读回确认仍是合法 JSON；用户拒绝则本会话不再问。检查命令：`jq -r '.env.CLAUDE_CODE_WORKFLOW_MAX_CONCURRENT_AGENTS, .env.CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS, .worktree.baseRef' ~/.claude/settings.json`（应依次为 `64`、`64`、`head`）。用户原话（2026-10-08）：「这个settingsJson能够最好的话就放到就是只要只要这个仓库一个新的机器上开始了你要问用户需不需要把它放到全局里面」「worktree.baseRef，之后派写入型子代理前需要设成 "head"。这个也要设置为全局。」。

  只对之后新开的会话生效。核实：开 `--debug-file` 的会话跑一次 workflow，日志应出现 `workflow: concurrent agent gate = 64 (CLAUDE_CODE_WORKFLOW_MAX_CONCURRENT_AGENTS)`。Claude Code 2.1.283 源码实测：`CLAUDE_CODE_WORKFLOW_MAX_CONCURRENT_AGENTS` 校验范围 1～256；单个 workflow 累计 `agent()` 调用上限 1000，不可改。2026-10-08 在 sled-vail（32 核）用无头会话跑 60 个 haiku `agent()` 各等 30 秒，按转录首末时间戳算 `PEAK_CONCURRENCY=60`，60 个在 1.3 s 内全部起跑、总墙钟 47.9 s。无头会话（`claude -p`）跑 workflow 须显式 `--allowedTools "Workflow"`，否则权限模式降回 `default`、Workflow 被直接拒。设高上限不改变用量计费：并发越高额度消耗越快，也不扩大授权范围（`AGENTS.md` 第 2 条）。用户原话（2026-10-08）：「claude workflow强制并行最多16个 按照cpu count这个能破除吗」「设成 64 写进 settings.json」「SUBAGENTS 也调到 64」「同意你需要更改这个AgentMetaRoth和每个仓库的这个设置就是每次都要设置成这样」。
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
  3. 记录主检出状态（修改代理派发前核对）或按 `AGENTS.md` 第 19 条判定审计 clean 状态时排除该文件：`git status --short --ignore-submodules=dirty -- . ':!docs/subagent-stats'`。
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
- 计划正文写进 harness 指定的计划文件（`~/.claude/plans/<slug>.md`）；结构（两部分 / 纯文档例外）与细节密度一律按 `AGENTS.md` 第 2 条，本文件不复述。只写推荐方案，不罗列所有备选。用户要求落在仓库根目录的计划交付物按 `AGENTS.md` 第 2 条写成单文件 HTML（不再写 `.md`），图由 `opus` 画图子代理按图并行出内联 SVG。
- 宿主明确指定的计划文件属于工具管理文件，不作为仓库数据或实验产物，不能借此把缓存、权重或日志写到 `<STORE_ROOT>` 之外；仅在宿主明确允许时写入。
- plan mode 期间除该计划文件外一律只读：不改代码、不改配置、不 commit、不跑任何有副作用的命令。**在只读阶段把事实核实清楚**——仓库的坑（如 editable 指向、安装顺序、源码来源、已知缺陷）都是只读就能查清的，带着未经核实的假设进入实施阶段代价远高于多花几分钟查证。

<!-- AGENTMETARULES:END common-claude -->
