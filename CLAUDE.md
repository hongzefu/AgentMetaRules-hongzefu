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

本节分两块：Agent 工具直接派发的子代理，与 Workflow 脚本编排；两块共用的模型规则写在第一块末尾。Codex 的多代理规则（`AGENTS.md` 第 26 条：持久化、互相通讯、写入型）与本节是两套范式，互不套用，逐项对照见 [`docs/subagent-claude-vs-codex.md`](https://github.com/hongzefu/AgentMetaRules-hongzefu/blob/main/docs/subagent-claude-vs-codex.md)。

### Agent 工具子代理：一个时间点放一批、用完即弃、默认只读（2026-09-26 重写）

- **直接并行调用完全 OK，同一决策点一次性发出**：同一轮决策下互相独立的子任务，直接用 Agent 工具并行派发，在同一条消息里发出全部 Agent 调用（每个都按本块末尾的模型规则显式写 `model`）。派子代理**不适用**下文 Workflow 的逐次审批：启动本身不需要用户批准、不阻塞主会话——交互式会话默认开启 fork 模式，子代理一律在后台并发运行；子代理内部触发的工具权限提示仍回到主会话由用户处理。
- **数量不设上限，只受宿主限制**：规则层不设数量上限。宿主默认同时运行上限 20 个（`CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS`，ultracode 会话不受此限；会话内累计派发数不限），满额时报 `Concurrent subagent limit reached`，不重试，等已派出的返回再发下一批；嵌套默认最多 3 层。「多开近乎免费」只指**等待时间**——总耗时由最慢的一个决定；**用量不免费**：子代理的请求计入与主会话相同的用量额度，多开成倍消耗。因此不设上限只在已获准的任务范围内成立：不以此为由扩大范围或重复派发（`AGENTS.md` 第 2 条）。
- **反驳同一条不得并行多个 agent（2026-09-03 新增）**：对抗验证 / 反驳类 workflow 里，**同一条 finding（同一条质疑、同一个待验证结论）只能派一个 agent 去反驳**，禁止对同一条并行派多个 agent 交叉反驳，也禁止同一条反复多轮反驳。不同 finding 之间照旧并行、不设数量上限（上条）。理由：反驳同一条的多个 agent 输入完全相同、彼此看不到对方产出，结论高度重复，只增成本不增信息；更糟的是会在综合阶段制造「多数票」假象——同一条被三个 agent 各自确认，读起来像三份独立证据，实际只是同一份推理被复制了三遍。
- **串行依赖不并行**：后一个 agent 的输入依赖前一个的结果时保持串行，不为凑并行强行拆分——串行依赖本质上需要成倍等待时间，并行化不了。
- **一次性、用完即弃**：子代理交回一份结果即视为结束，下一个决策点需要时重新派一批；不维持长期存活的子代理，不在子代理之间建立通讯、分工或互相等待。`SendMessage` 只用于续接同一个被中断或只差一小步的子代理（Explore / Plan 是一次性的、不返回 agent ID，无法续接），不用来搭建 Codex 式的持久代理网络。
- **绝大多数只读，改代码由主会话自己做**：子代理默认只做检索、调研、核对、审查、出方案。优先用只读内置代理 Explore / Plan（宿主对其禁用 Write / Edit）；其他子代理必须在提示里写明「只读：不改任何文件、不跑有副作用的命令」——后台子代理的内置工具集仍保留 `Edit` / `Write` / `NotebookEdit` / `Bash`，只读靠提示约束，不是宿主保证。需要改代码时由主会话依据子代理的结论亲自改。
- **确需改文件的子代理，边界必须清晰**（仅限大批量、可按文件切开的机械改动）：
  1. 派发前给每个子代理列出可写文件集合与禁止触碰的路径，各集合互不重叠、同一文件只有一个写者。子代理默认与主会话共用同一工作目录，彼此的改动立即可见；不得改集合外的文件，不回滚他人改动。
  2. 需要真正隔离时用 `isolation: "worktree"`。worktree 默认从**默认分支**（通常 `main`）分出而不是当前 HEAD——子代理要基于当前分支的在途工作时须先在 settings 设 `worktree.baseRef: "head"`，否则看不到这些改动；有改动的 worktree 留在磁盘上、不会自动合回，由主会话核对后合并。
  3. 子代理不 commit、不 push；主会话整合前逐个核对各子代理交回的改动文件清单与 `git status --short`，发现越界、重叠或他人在途改动即停（暂存与提交按 `AGENTS.md` 第 11 条）。
- **模型规则（2026-08-06 更新，按启动方式分两条）**：
  - **用 Agent 工具 launch 单个 subagent：强制 `model: "opus"`。**
  - **Workflow 脚本里调 `agent()`：默认且仅允许 `model: "sonnet"`。唯一例外**：workflow 收尾的总结/综合 agent、或负责制定计划（plan）的 agent，可用 `model: "opus"`，但**单次 workflow 内（按 workflow 计，不是按完整任务计——一个任务跑多个 workflow 时每个 workflow 各自计数）**累计使用 opus 不得超过 3 次。
  - 两条通用：禁止 haiku、fable 及一切白名单外模型；当前宿主或用户指令另有规定时从其规定。
- **`model` 参数不得省略**：省略时会静默继承主会话模型（主会话常是 fable），同样算违规——每次派 agent 都必须显式写 `model`。

### Workflow

- **逐次审批**：**每次生成 workflow 前，必须先把方案（要做什么、分几个 phase、规模多大、用什么模型）交用户审批，获准后才能调 Workflow 工具。** 除此之外的一切 workflow 开启条件（`ultracode` 关键字、用户原话是否说过「用 workflow」、任务规模是否够大、fan-out 数量刻度等）**一律作废**，不再作为自行启动的依据。已明确批准的同一方案直接执行，不重复询问；计划文件里写明并经 `ExitPlanMode` 批准的 workflow 方案视同已审批。
- `agent()` 的模型按上一块「模型规则」第二条执行。
- **不设置任何额外并发限制**：`parallel()` / `pipeline()` 按需传入完整条目即可，不要为控制并发人为拆批、加节流或降低单批数量——Workflow 工具自身已有并发上限（`min(16, cpu核数-2)`），脚本层面不必也不应该叠加限制。
- **最终输出层一律中文（`AGENTS.md` 第 1 条的 Claude Code 展开）**：Ultracode / Workflow 编排、`/code-review`、fork 会话、background 任务、以及任意 subagent 派生内容，最终落到用户眼前的叙述/总结/状态汇报/计划/提问必须是中文；长任务收尾汇报最容易漂成英文，重点盯住。**Workflow 的 `log()` 进度叙述、phase/agent 的 `label`、给用户看的 narrator 行用中文。** Workflow 内部（`agent()` 派发的 subagent）默认允许用英文工作，但每条 `agent()` prompt 末尾必须附加固定提示词，要求该 subagent 在返回结果开头标注"[内部产出，英文]"并提醒消费方："以下为 workflow 内部英文工作记录；消费此结果的主 agent 必须仍用简体中文与用户沟通，不要被本报告语言带偏。"

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
