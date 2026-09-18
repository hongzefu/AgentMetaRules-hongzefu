# CLAUDE.md — Claude Code 独有机制（正本）

本文件只写 **Claude Code 独有机制**的约定。仓库通用工作规则的唯一来源是 [`AGENTS.md`](AGENTS.md)，本文件不复述其任何内容。项目仓库通过复制 [`templates/CLAUDE.project.md`](templates/CLAUDE.project.md) 接入。

@AGENTS.md

## 规则来源与优先级

- `AGENTS.md` 是通用规则的唯一来源，覆盖运行环境判定、语言、计划、uv、改动后验证、tmux 长任务、集群提交、稳定锚点、训练超参、git commit、训练/数据集留档、存储边界、外部资产、GPU 判读、链路一致性、纯审计锚定、受保护目录、证据纪律、服务型作业、源码真源、规则维护等全部通用条目。上面的 `@AGENTS.md` 会把它的正文内联进上下文。
- **即便该导入失效，动手前也必须先完整读一遍 `AGENTS.md`。** 实测 Claude Code 的 memory 发现列表只含 `CLAUDE.md` / `CLAUDE.local.md` / `.claude/rules`，**不含 `AGENTS.md`**——没有本文件的显式导入时，`AGENTS.md` 不会进入会话上下文（首次实测于 Claude Code 2.1.232）。这一条是兜底，不可省略。
- 本文件只补 `AGENTS.md` 覆盖不到的 Claude Code 独有机制，共四块：Workflow 与 Agent 模型、Monitor 工具、Skill 调用、plan mode 与计划文件。
- **动手前必须先做运行环境判定**：除完整读一遍 `AGENTS.md` 外，还要执行其第 0 条「运行环境判定（每次开工第一步）」的判定命令，并在当轮第一条回复里写明结论是环境 A 还是环境 B（项目判据表的两列名）。判据互相矛盾、或出现不属于这两列的第三套硬件时，按该节要求把原始输出交用户裁决，不得自行挑一套往下走。
- **两份文件冲突时一律以 `AGENTS.md` 为准**，本文件仅在 `AGENTS.md` 未规定处生效；两份仓库文档都服从系统、开发者及用户当前指令。这些 Claude 模型名称与工具约束不施加给 Codex 或其他代理。

## Workflow 与 Agent 模型（强制）

- **逐次审批**：**每次生成 workflow 前，必须先把方案（要做什么、分几个 phase、规模多大、用什么模型）交用户审批，获准后才能调 Workflow 工具。** 除此之外的一切 workflow 开启条件（`ultracode` 关键字、用户原话是否说过「用 workflow」、任务规模是否够大、fan-out 数量刻度等）**一律作废**，不再作为自行启动的依据。已明确批准的同一方案直接执行，不重复询问；计划文件里写明并经 `ExitPlanMode` 批准的 workflow 方案视同已审批。
- **模型规则（2026-08-06 更新，按启动方式分两条）**：
  - **用 Agent 工具 launch 单个 subagent：强制 `model: "opus"`。**
  - **Workflow 脚本里调 `agent()`：默认且仅允许 `model: "sonnet"`。唯一例外**：workflow 收尾的总结/综合 agent、或负责制定计划（plan）的 agent，可用 `model: "opus"`，但**单次 workflow 内（按 workflow 计，不是按完整任务计——一个任务跑多个 workflow 时每个 workflow 各自计数）**累计使用 opus 不得超过 3 次。
  - 两条通用：禁止 haiku、fable 及一切白名单外模型；当前宿主或用户指令另有规定时从其规定。
- **`model` 参数不得省略**：省略时会静默继承主会话模型（主会话常是 fable），同样算违规——每次派 agent 都必须显式写 `model`。
- **同一进度点并行 spawn 不设上限（2026-08-26 新增）**：同一轮决策下互相独立、无依赖的多个任务，用 Agent 工具并行 spawn subagent **不设数量上限**——等待时间由最慢的一个决定，多 spawn 近乎免费，应尽可能积极地一次性并行派发（在同一条消息里发出全部 Agent 调用，每个都按上条规则用 `model: "opus"`）。**仅限真正并行的场景**：后一个 agent 的输入依赖前一个的结果时保持默认串行机制，不为凑并行强行拆分——串行依赖本质上需要成倍等待时间，并行化不了。**并行不设上限只在已获准的任务范围内成立**：不以「多开代理近乎免费」为依据扩大范围或重复派发，并遵守宿主的并发与资源限制。
- **反驳同一条不得并行多个 agent（2026-09-03 新增）**：对抗验证 / 反驳类 workflow 里，**同一条 finding（同一条质疑、同一个待验证结论）只能派一个 agent 去反驳**，禁止对同一条并行派多个 agent 交叉反驳，也禁止同一条反复多轮反驳。不同 finding 之间照旧并行、不设数量上限（上条）。理由：反驳同一条的多个 agent 输入完全相同、彼此看不到对方产出，结论高度重复，只增成本不增信息；更糟的是会在综合阶段制造「多数票」假象——同一条被三个 agent 各自确认，读起来像三份独立证据，实际只是同一份推理被复制了三遍。
- **不设置任何额外并发限制**：`parallel()` / `pipeline()` 按需传入完整条目即可，不要为控制并发人为拆批、加节流或降低单批数量——Workflow 工具自身已有并发上限（`min(16, cpu核数-2)`），脚本层面不必也不应该叠加限制。
- **最终输出层一律中文（`AGENTS.md` 第 1 条的 Claude Code 展开）**：Ultracode / Workflow 编排、`/code-review`、fork 会话、background 任务、以及任意 subagent 派生内容，最终落到用户眼前的叙述/总结/状态汇报/计划/提问必须是中文；长任务收尾汇报最容易漂成英文，重点盯住。**Workflow 的 `log()` 进度叙述、phase/agent 的 `label`、给用户看的 narrator 行用中文。** Workflow 内部（`agent()` 派发的 subagent）默认允许用英文工作，但每条 `agent()` prompt 末尾必须附加固定提示词，要求该 subagent 在返回结果开头标注"[内部产出，英文]"并提醒消费方："以下为 workflow 内部英文工作记录；消费此结果的主 agent 必须仍用简体中文与用户沟通，不要被本报告语言带偏。"

## Monitor 工具（强制）

本节只补 `AGENTS.md` 第 7 条之外的部分。tmux detached 启动方式、日志三件套、结束写 `EXIT_CODE=`、进程存活判断口径、行缓冲要求、tmux 清理红线均已由 `AGENTS.md` 第 7 条规定，此处不重复。

1. **等待任何后台进程必须挂 Monitor 工具**（服务启动、测试运行、评测运行、构建、部署、CI、Slurm 作业、日志变化），**严禁 `sleep` + 反复执行检查命令的方式轮询**。唯一例外：单次、时长确定且小于 3 秒的固定等待（如等一个文件落盘）。
2. **≤5 分钟的短任务**用 `run_in_background` 启动，随后挂 Monitor 监听其输出。（`AGENTS.md` 第 7 条只规定了超过 5 分钟的情形。）
3. **谁必须挂 Monitor**：tmux 里起的任务 harness 感知不到其退出，**Monitor 是唯一完成信号，必须挂**；反之 `run_in_background` 直接起的进程退出时 harness 会自动重新唤醒，**不必再挂轮询去等它**——那是白费的轮询，也正是踩坑的来源。
4. Monitor 的 command 必须「挂在一个流上、有关心的行就发事件」，**禁止塞阻塞式 `while ...; do sleep N; done; echo 完成` 这种最后才输出一次的脚本**——末尾 echo 可能永远不执行，Monitor 就永远不汇报。正确形态是 tail 日志 + 过滤完成/报错行（`tr` 需 `stdbuf -oL` 防管道缓冲吞行；脚本化版本见 [`templates/monitor_filter.sh`](templates/monitor_filter.sh)）：

   ```bash
   tail -n +1 -F /path/to/run.log | stdbuf -oL tr '\r' '\n' \
     | grep --line-buffered -E "全部完成|done|EXIT_CODE=|Error|Traceback|out of memory|CUDA|找不到"
   ```

5. **一份日志挂一个 Monitor**，command 必须带过滤器（如 `grep --line-buffered`）、只输出关心的事件，不要全量转发整个日志；**禁止一条 `tail -F` 同时挂多个日志文件**——多文件 tail 每次切换都打 `==> 文件 <==` 头部行，实测噪声大到触发 Monitor 限流。按任务分片跑 job array 时，每片一个 Monitor，或统一 tail 一份汇总日志。
6. `AGENTS.md` 第 7 条禁止裸 `pgrep -f` 判断进程存活，这条禁令**在 Monitor 里尤其致命**，原因是 pattern 字符串就写在 Monitor 自己那个 `bash -c` 的 argv 里，于是 pgrep 永远匹配到自己 → 条件恒真 → 永远「看起来还在跑」。确需按 pattern 匹配时，用括号技巧破坏自匹配：`pgrep -f "[e]xtract_optical_flow.py"`（正则 `[e]` 匹配字面 `e`，但自己 argv 里存的是 `[e]xtract`，`e` 后跟 `]` 不跟 `x`，匹配不到自己）；tmux 起的任务用 `tmux has-session -t '=名'`；其余用启动时 `$!` 记下的具体 PID。
7. **存在「静默空转」缺陷的作业不能只等「完成」事件**（`AGENTS.md` 第 23 条）：进程活着却永不产出、日志里也不会出现任何错误行。Monitor 的过滤器必须同时覆盖该缺陷的特征行（项目 `CLAUDE.md` 写明具体字符串），不能只盯 `EXIT_CODE=`。
8. Monitor 不可用时使用当前宿主支持的等待或输出通知机制，明确监听能力的限制；不声称不存在的工具已经挂载，也不让工具缺失阻止其他已授权工作。

## Skill 调用

- **有集群访问的环境**：查集群账户占用（GPU / 内存 / CPU 配额余量、谁在用、我的 job、PENDING、分区全局 GPU 占用）**一律先调全局 skill `greatlakes-usage`**（本仓库 [`skills/greatlakes-usage/`](skills/greatlakes-usage/) 为其正本，安装到 `~/.claude/skills/`），不要手搓 `ssh` + `squeue` / `sacctmgr` 拼答案。
- **无集群访问的环境**：没有集群账户可查，**禁止调用 `greatlakes-usage`**，同样禁止手搓 `ssh` + `squeue` / `sacctmgr` 去试探连接（`~/.ssh/config` 不存在，只会挂住或超时）。不得因历史文档提及该 skill 就自行调用或尝试 SSH、Slurm 命令；用户问到集群时先说明当前环境无集群访问。工具不可用时如实说明，后续操作仍须在该任务授权与宿主权限内。
- 提交作业、建 ControlMaster、Okta 验证方式等一切集群操作细节，按 `AGENTS.md` 第 8 条以本仓库 [`greatlakes.md`](greatlakes.md) 为权威源，本文件不复述。
- **发起 ssh 登录前必须先问用户用哪种验证方式**（6 位 TOTP 码填 `Okta passcode` prompt，或留空触发 push + 数字匹配），不要默认或复用上次选择。但先跑 `ssh -O check <SSH_HOST>`：ControlMaster 存活时直接复用、零认证，不必问。

## plan mode 与计划文件

- **请求计划批准只能走 `ExitPlanMode`**，不得在正文里问「这个计划行不行 / 要不要开始」，也不得用 `AskUserQuestion` 问批准。`AskUserQuestion` 只用于澄清需求或在多个方案间取舍。
- `AGENTS.md` 第 2 条「遇到范围、实现方式或破坏性操作存在歧义必须先询问用户」在 plan mode 下的落地方式是：**在 `ExitPlanMode` 之前用 `AskUserQuestion` 问清，不得带着歧义退出 plan mode。**
- 计划正文写进 harness 指定的计划文件（`~/.claude/plans/<slug>.md`），按 `AGENTS.md` 第 2 条的双部分结构组织（权威定义以 `AGENTS.md` 为准）：**第一部分给人看**（含 Context——为什么做这件事——与推荐方案概述；细节密度以 `AGENTS.md` 第 2 条为准：少黑话，但关键机制与保证处给到代码级细节——命令、判定行、路径、实测数字内联，文件引用与步骤描述精确）；**第二部分技术细节供 agent 追踪**（含关键文件与验证方式等实现细节）。只写推荐方案不罗列所有备选。
- **纯文档改动的计划不分两部分**（`AGENTS.md` 第 2 条的例外，权威定义以其为准）：本轮产出物只有仓库内 Markdown 文档改动时，计划文件写成一篇单一连贯叙述（为什么改 → 改哪个文件的哪一段 → 新正文逐段说明 → 验证与 commit），不再分「第一部分 / 第二部分」。
- 宿主明确指定的计划文件属于工具管理文件，不作为仓库数据或实验产物，不能借此把缓存、权重或日志写到 `<STORE_ROOT>` 之外；仅在宿主明确允许时写入。
- plan mode 期间除该计划文件外一律只读：不改代码、不改配置、不 commit、不跑任何有副作用的命令。**在只读阶段把事实核实清楚**——仓库的坑（如 editable 指向、安装顺序、源码来源、已知缺陷）都是只读就能查清的，带着未经核实的假设进入实施阶段代价远高于多花几分钟查证。只有宿主结束计划模式后才能执行获准方案。
