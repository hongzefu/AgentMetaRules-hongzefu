# 溯源：每条规则来自哪里

源文件缩写：**policy** = robomme_policy_learning_MotionJEPA@`v2-eval-0917`（`5a746c6c`；原名 `v2-vail-eval-0917`，2026-09-26 复查：已改名，sha 不变）；**benchmark** = robomme_benchmark_MotionJEPA@`PolicyEvalThirdParty-v2-eval-0917`（`b4e97f22`；原名 `PolicyEvalThirdParty-v2-vail-eval-0917`，2026-09-26 复查：已改名，sha 不变）；**evalgl** = robomme-eval-GL@`v2-vail-eval-0917`（`d4aeff7b`）；**mjepa** = MotionJEPA@`v6.1.2-awsNoSlurm`（`4098a98f`；2026-09-26 复查：分支现 HEAD `bc1523a3`，取用文件未变）；**global** = 本机 `~/.claude/CLAUDE.md`（2026-09-01）；**skill** = 本机 `~/.claude/skills/greatlakes-usage/`。「主来源」是逐字底本，「并入」是只有该处才有的独有内容。

## 表一：规则 → 来源

| 正本条目 | 主来源（逐字底本） | 并入的独有内容 |
|---|---|---|
| 0 运行环境判定 | policy AGENTS「运行环境判定」 | evalgl AGENTS 判定命令骨架（`hostname`、`2>/dev/null`、micromamba 探测）；mjepa AGENTS「当前运行环境与存储边界」（硬件是带日期记录）；evalgl `gl_smoke.sbatch`（fail-fast 编码） |
| 1 语言 | benchmark AGENTS 规则 1 | global「语言」反例句；policy AGENTS 规则 1；mjepa AGENTS 规则 1（代理协作汇报） |
| 2 计划 | policy AGENTS 规则 2（含 2026-09-16 命名、改名引用维护） | mjepa AGENTS 规则 8（编号规则精确到条目边界；宿主指令优先）；benchmark AGENTS 规则 10（六个特征） |
| 3 uv | global「uv 依赖管理」 | policy AGENTS 规则 3（先确认 uv、禁裸 python、NFS copy）；mjepa AGENTS 规则 2（改 pyproject 后 `uv lock`）；benchmark AGENTS 规则 2（`uv venv`、pytest 由 uv 起）；evalgl AGENTS 规则 3(a)（`UV_CACHE_DIR` 显式、解释器钉死、`--frozen --no-sync`） |
| 4 改动后验证 | policy AGENTS 规则 4 | mjepa AGENTS 规则 4（`git diff --check` 核对原有要求、Playwright 临时环境、静态检查不能替代实跑）；benchmark AGENTS 规则 3（最小 smoke 前置）；evalgl AGENTS 规则 4 |
| 5 INTER_NEAREST | benchmark AGENTS 规则 6 | policy AGENTS 规则 5；mjepa AGENTS 规则 5 |
| 6 run_name | mjepa AGENTS 规则 6 | policy AGENTS 规则 6；env-b-aws-replication.md 十一节 3（计划外 run 名事后追认） |
| 7 长任务 tmux + 清理红线 | policy AGENTS 规则 7（红线全文含 2026-09-04 事故） | global「后台进程等待」（六判据、`tee` 三个坑、配套命令、括号技巧原理）；mjepa AGENTS 规则 7（`=` 精确匹配、强杀不写退出码、server 可能不存在）；benchmark AGENTS 规则 4；env-b 十节 1/5/7（事故原始记录、长命令先落脚本、避开忙卡） |
| 8 集群提交分叉 | policy AGENTS 规则 8 | evalgl AGENTS 规则 8（七条要点提醒）；mjepa AGENTS 规则 3（历史命令不代表授权） |
| 9 禁硬编码行号 | benchmark AGENTS 规则 5 | policy AGENTS 规则 9、19（审计行号）；mjepa AGENTS 规则 9 |
| 10 训练超参落点 | policy AGENTS 规则 10 | mjepa AGENTS 规则 10（项目覆盖白名单） |
| 11 git commit / push | global「git 提交」 | policy AGENTS 规则 11（push 纪律、gh 凭据、无 upstream 先问、禁 force）；mjepa AGENTS 规则 11（禁 `git clean -x/-X`、覆盖前核实 symlink、不继承推送授权→声明式例外）；benchmark AGENTS 规则 7（版本号递增语义）+ 全局执行规则（不得破坏性 git 清理）+ 日志 2026-09-09（`git apply --cached`） |
| 12 训练 / 评估留档 | mjepa AGENTS 规则 12 | policy AGENTS 规则 12、17；evalgl AGENTS 规则 13（三件套字段、tmux 会话清单）；env-b 十节 2（打包期间冻结 HEAD） |
| 13 数据集构建留档 | mjepa AGENTS 规则 15 | policy AGENTS 规则 12；2026-09-26 去重改写为同构第 12 条、只列差异 |
| 14 存储边界 | policy AGENTS 规则 13、14 | benchmark AGENTS 规则 8（本地快盘 + rsync）+ 全局执行规则（产物在仓库内、禁 symlink/bind mount 绕过）；evalgl AGENTS 规则 10、11（禁覆盖 HOME 理由、git 只在有凭据侧）；mjepa AGENTS「当前运行环境与存储边界」（单机红线、缓存逐项设）；benchmark 日志 2026-09-12（跨运行 glob 删除事故） |
| 15 原始数据与外部资产 | policy AGENTS 规则 15 | external-assets-lock.md 一、二、五、六节（三反模式、四设计点、异地复刻五步、边界三条）；evalgl AGENTS 规则 6(c)（第三方锁 40 位 sha）；env-b 一节口径 1、四节（token 只走 env、sha 前缀 + 字节数） |
| 16 GPU 利用率 | policy AGENTS 规则 16 | mjepa AGENTS 规则 17；2026-09-26 并入原第 14 条末项「吞吐基准记介质」 |
| 17 长调试留档 | policy AGENTS 规则 17 | mjepa AGENTS 规则 16（探索性标注）；2026-09-26 去掉对第 12 条的复述 |
| 18 链路一致性 | policy AGENTS 规则 18 | mjepa AGENTS 规则 18（不悄悄放宽阈值）；benchmark AGENTS 第三阶段第 5 条（一致性四分法）；env-b 二节、7.4 节（只换对照物、不改 gate） |
| 19 纯审计锚定 | policy AGENTS 规则 19 | mjepa AGENTS 规则 19（动态验证不描述为静态审计） |
| 20 Codex 回退 | policy AGENTS 规则 20 | mjepa AGENTS 规则 20；benchmark AGENTS 规则 9（沙箱故障不是代码错误、最小命令重试、删除不自动获授权） |
| 21 受保护目录 | benchmark AGENTS 规则 11 | benchmark 日志 2026-09-17（一次性授权原话） |
| 22 证据纪律与账本 | benchmark AGENTS 全局执行规则 + 「后续日志模板」 | env-b 一节、7.6 节、十一节（判定行内联、FAIL 只记现状）；evalgl README「验收」（不为挑成功回合重试）；evalgl README 60k 节（来源冲突保留并注明） |
| 23 服务型作业 | evalgl AGENTS 规则 14、15 | evalgl CLAUDE Monitor 第 7 条；evalgl `gl_smoke.sbatch`（`exec` 交棒、`--gpu_cmode=shared`、unset 诊断开关） |
| 24 源码唯一真源 | evalgl AGENTS 规则 5、6 | policy AGENTS「策略评估的工作副本与第三方分支机制」；benchmark 日志 2026-09-11（AST 钉死 scripts 不依赖 tests） |
| 25 规则维护元规则 | benchmark 日志 2026-09-09（拆分口径、编号取舍、脚本搬运） | evalgl AGENTS「规则来源」（逐条列未迁移）；mjepa AGENTS 前言（跨宿主中立）；2026-09-26 用户要求（标记块同步机制）：「每个仓库都要有一份agentsmd greatlake md等等 AgentMetaRules只负责每次同步的时候检查一下 平时只在仓库内交互 不要每次都读github太麻烦了」「是否可以只推这次修改的md 其他的都不动？精确按照文件来」，取舍见 [merge-decisions.md](merge-decisions.md) P |
| 26 仅 OpenAI Codex：完全按多代理流程工作——持久化子代理、尽可能多并发、写入边界清晰 | 2026-09-26 用户要求及澄清 | 用户四句原话：「尽可能积极调用使用multi agent来实现 但是分隔要保持清晰」「子agent要小于等于主要请求agent的规格」「codex强调修改文件要保持subagent之间的任务的的清晰 尽可能多并发 完全是multi agent的处理流程」「而codex一般是持久化的运行多agent 几个agent互相通讯 不会因为单个任务结束就关闭这个agent」；[OpenAI 官方 Subagents 文档](https://learn.chatgpt.com/docs/agent-configuration/subagents)；`rust-v0.157.0` 源码五个文件：[`codex-rs/prompts/src/multi_agent_instructions.rs`](https://github.com/openai/codex/blob/rust-v0.157.0/codex-rs/prompts/src/multi_agent_instructions.rs)、[`codex-rs/core/src/tools/handlers/multi_agents_spec.rs`](https://github.com/openai/codex/blob/rust-v0.157.0/codex-rs/core/src/tools/handlers/multi_agents_spec.rs)、[`codex-rs/core/src/agent/role.rs`](https://github.com/openai/codex/blob/rust-v0.157.0/codex-rs/core/src/agent/role.rs)、[`codex-rs/core/src/tools/spec_plan.rs`](https://github.com/openai/codex/blob/rust-v0.157.0/codex-rs/core/src/tools/spec_plan.rs)、[`codex-rs/core/src/agent/control/residency.rs`](https://github.com/openai/codex/blob/rust-v0.157.0/codex-rs/core/src/agent/control/residency.rs)；[SSH App 并发实测](codex-app-ssh-multiagent.md)；[两套子代理规则对照](subagent-claude-vs-codex.md) |
| CLAUDE.md 规则来源与优先级 | policy CLAUDE | evalgl CLAUDE（去版本号）；mjepa CLAUDE（跨宿主） |
| CLAUDE.md Workflow 与 Agent 模型（2026-09-26 重写为「Agent 工具子代理」「Workflow」两块） | policy CLAUDE | mjepa CLAUDE（范围不扩、中文 log/label）；benchmark CLAUDE §1（`agent()` 固定提示词）；2026-09-26 用户原话「claude subagent强调在一个时间点位置可以积极多调用 因为同时启动多个subagent基本是免费的 但是如果要修改文件要保持subagent之间的任务的的清晰」「对于claude而言 用户的直观感受是这样的直接调用 并行是完全ok的 一般在一个时间节点上同时放出一堆agent 然后用完即废弃 并且大部分情况不改代码」；Claude Code 官方文档 sub-agents / worktrees / agents 三页（链接见 [两套子代理规则对照](subagent-claude-vs-codex.md)） |
| CLAUDE.md Monitor | policy CLAUDE / evalgl CLAUDE | evalgl CLAUDE 5、7（job array 每片一个、静默空转）；global（括号技巧原理）；mjepa CLAUDE（Monitor 不可用时）；2026-09-26 去重：管道示例与 pgrep 括号技巧改为引用 AGENTS 第 7 条 |
| CLAUDE.md Skill 调用 | policy CLAUDE | evalgl CLAUDE（`ssh -O check` 豁免）；mjepa CLAUDE（不因历史文档提及就调用） |
| CLAUDE.md plan mode | policy CLAUDE | evalgl CLAUDE（只读阶段核实事实）；mjepa CLAUDE（计划文件属工具管理文件）；2026-09-26 去重改为引用 AGENTS 第 2 条 |
| greatlakes.md 全部硬规则节 | policy greatlakes.md（= mjepa 版严格超集，知识本体逐字同源） | skill SKILL.md（配额口径 20/960/80、物理 240 张、sandbox 与 timeout 说明）；evalgl `gl_smoke.sbatch`（fail-fast、`exec`）；policy greatlakes.md 放行记录节（`--dependency=afterany`、`--exclude`、配额 GPU 20 / CPU 80）；2026-09-26 占位 job 口径（用户原话「greatlakes都采用占用job的形式 而不是现在这样 在修改代码之前 启动工作的时候 尽可能早的占卡 如果是maniskill多worker cpu生成的 我记得这几个仓库有实测验证 其他情况下压低cpu mem保证快速排队 每次job都直接48小时 工作完成后kill 这样可以让排队和修改代码并行」），资源约束、算力使用规则与调试 slurm 脚本节随之改写 |
| scripts/gl_submit.py | policy `scripts/training/gl_submit.py`（含 push 修法 1、2 条） | mjepa `scripts/train-script-hongzefu/gl_submit.py`（对照）；greatlakes.md push 修法第 3 条（sentinel，本仓库新实现） |
| skills/greatlakes-usage/ | 本机 `~/.claude/skills/greatlakes-usage/` 四文件 | 修正见 merge-decisions.md 口径统一清单 |

## 表二：日期沿革（合并四仓库的日期标注，按时间排）

| 日期 | 事项 | 出处 | 落在本仓库 |
|---|---|---|---|
| 2026-06-17 | spgpu 强制至少 1 GPU：`--gpus-per-node=0` 报 `QOSMinGRES` | policy/mjepa greatlakes.md「已知坑」 | greatlakes.md「已知坑」；templates/hold_job.sbatch（原 templates/job.sbatch，2026-09-26 删除） |
| 2026-06-19 | Okta push「卡死」真根因（pexpect 模式表缺 `Press enter to continue`）；push 修法实测一次过 | policy/mjepa greatlakes.md | greatlakes.md「Okta 两条路」「push 修法」；scripts/gl_submit.py |
| 2026-07-13 | benchmark `/init` 建 AGENTS.md 账本与九字段日志模板 | benchmark 日志 | 第 22 条 |
| 2026-07-14 | benchmark 某目录全量英文化 → 规则 1「历史英文化遗留不回译」豁免 | benchmark 日志、规则 1 | 第 1 条豁免占位 |
| 2026-08-06 | nohup vs tmux 六判据实测（MotionJEPA 仓库） | global CLAUDE.md；benchmark 规则 4 | 第 7 条 |
| 2026-08-06 | 模型规则更新：Agent 工具→opus；workflow `agent()`→sonnet，opus ≤3 | global / policy / benchmark CLAUDE.md | CLAUDE.md |
| 2026-08-14 | GL 冒烟实测 job 57628076 与 v2 降配 57642560（4 CPU / 16G，排队 <1 分钟）；「48G 必需」推断作废；「现成的 slurm 脚本」节新增 | greatlakes.md | greatlakes.md「PENDING 读法」降配实例、「页缓存 vs 真实内存」；实测表本身排除 |
| 2026-08-14 | PENDING 碎片实测：余量 18 GPU / 768G / 72 CPU 但只 3 节点可调度 | greatlakes.md | greatlakes.md「PENDING 读法」 |
| 2026-08-14 | mjepa 默认精度翻转 bf16、臂格加权上线 | mjepa AGENTS | 排除（项目专属） |
| 2026-08-15 | mjepa 弃用 linear-probe 评估入口 | mjepa AGENTS | 排除 |
| 2026-08-16 | 分布式 Wan latent 抽取；job array 实测 57854615；全量 57856154/57856155；跨架构不逐位（max\|Δ\|≈1.2e-5） | greatlakes.md | greatlakes.md「job array」节；第 15 条边界；抽取流程排除 |
| 2026-08-18 | mjepa 规则 15 数据集构建留档定稿（随 v8-400ep） | mjepa AGENTS | 第 13 条 |
| 2026-08-18 | benchmark 从 MotionJEPA 移植通用约定 + 新增 CLAUDE.md 指针，明确未搬六项 | benchmark 日志 | 第 25 条；docs/merge-decisions.md |
| 2026-08-18 | v8-400ep 全量抽取二次放行（8×1GPU / 30h） | greatlakes.md | 排除（放行记录） |
| 2026-08-24 | 行缓冲两次实测踩坑（epoch 基准、冷缓存复测） | global；policy 规则 7 | 第 7 条；CLAUDE.md Monitor；templates/monitor_filter.sh |
| 2026-08-24 | GPU util 中位数假象：v1-e2e-b64 中位 100% 掩盖均值 69-70% | policy 规则 16 | 第 16 条 |
| 2026-08-26 | 同一进度点并行 spawn 不设上限 | global / policy CLAUDE.md | CLAUDE.md |
| 2026-08-27 | robomme framesamp 放行记录（`--dependency=afterany` 串行链、`--exclude` 冷节点、配额 GPU 22>20 / CPU 82>80） | policy greatlakes.md 放行记录 | greatlakes.md「job array」节技巧与配额口径；放行记录本身排除 |
| 2026-08-29 | 计划第一部分密度标杆定标 | policy 规则 2；mjepa 规则 8 | 第 2 条 |
| 2026-09-01 | 全局 `~/.claude/CLAUDE.md` 最后修改 | 本机 | docs/merge-decisions.md C、D |
| 2026-09-03 | 环境 A 口径：工作副本迁本机 `/data`，turbo 转只读归档 | policy 规则 13 | 第 14 条模式；附录 B |
| 2026-09-03 | 反驳同一条不得并行多个 agent | policy CLAUDE.md | CLAUDE.md |
| 2026-09-04 | 环境 B（AWS 单机）启用 | policy 判据表 | 第 0、8、14 条分叉 |
| 2026-09-04 | `tmux kill-server` 事故（误杀会话 0/7/19/20/claude-private 与在跑抽取） | policy 规则 7；env-b 十节 1 | 第 7 条红线 |
| 2026-09-04 | env-b 复刻教训：长命令先落脚本、多阶段打包期间不 commit、分片避开忙卡、`paths.sh` 前缀白名单、`refs/main` 补写 | env-b；external-assets-lock 五节 | 第 7、12、15 条 |
| 2026-09-08 | benchmark 账本规则与「只改一份文件」冲突的补记先例 | benchmark 日志 | 第 22 条 |
| 2026-09-09 | benchmark AGENTS/CLAUDE 按适用范围拆开；导入计划两部分为规则 10、插入不重编号；`git apply --cached` 精确暂存 | benchmark 日志 | 第 25、11 条 |
| 2026-09-10 | benchmark 规则 11 受保护目录逐个批准（用户原话） | benchmark 规则 11 | 第 21 条 |
| 2026-09-11 | benchmark AST 钉死 `scripts/` 不依赖 `tests/` | benchmark 日志 | 第 24 条 |
| 2026-09-12 | benchmark 跨运行 glob 删除事故（36 个 in-flight 文件被 unlink） | benchmark 日志 | 第 14 条 |
| 2026-09-12 | mjepa AWS 环境实测记录；从 robomme `v2-motionmem` `82c2ccef` 选择性迁移增量 | mjepa AGENTS | 附录 B；本表 |
| 2026-09-15 | 开发副本例外（`-temp` 副本、可写 symlink、独立 `.venv`） | policy 规则 14 | 第 14 条 |
| 2026-09-16 | 计划文件 `MMDD-<主题>-plan.md` 命名（美国东部时间） | policy 规则 2 | 第 2 条 |
| 2026-09-17 | uv 0.10.2 实测：`XDG_CACHE_HOME` 拖走 uv cache，须显式 `UV_CACHE_DIR` | evalgl 规则 3(a) | 第 3 条 |
| 2026-09-17 | benchmark「一口气全做完 不要再来问我了」一次性授权覆盖逐阶段批准 | benchmark 日志 | 第 21 条 |
| 2026-09-17 | evalgl 分支 `v2-vail-eval-0917`：vendoring、editable 校验、第三方分支机制 | evalgl AGENTS；policy「策略评估」节 | 第 24 条 |
| 2026-09-18 | 四仓库最新分支 HEAD 查定；本仓库建库 | 本仓库 | README「来源锚定」 |
| 2026-09-26 | Codex 多代理积极并行、委派说明、写入隔离、模型档位与宿主并发边界；SSH App 新任务 16 路并发及第 17 路拒绝实测 | 用户要求；OpenAI 官方 Subagents 文档；[验收记录](codex-app-ssh-multiagent.md) | 第 26 条 |
| 2026-09-26 | AGENTS 去重（在途改动只在第 11 条、授权不扩大只在第 2 条、判定行只在第 22 条、吞吐记介质并入第 16 条、第 13 条同构第 12 条只列差异、第 17 条去复述；CLAUDE.md Monitor / plan mode 改为引用）；两条子代理规则重写（CLAUDE.md「Agent 工具子代理：一个时间点放一批、用完即弃、默认只读」+「Workflow」，AGENTS 第 26 条「完全按多代理流程工作」）；第 25 条新增同步机制（三份正本加通用块标记、项目自带逐字副本、`sync_rules.py` / `land_rules_commit.py`、块内相对链接改绝对链接）；新增对照文档 | 用户原话（见表一第 25、26 条与 CLAUDE.md 行）；Claude Code / OpenAI 官方文档；`rust-v0.157.0` 源码 | AGENTS.md 第 2、11、13、16、17、22、25、26 条；CLAUDE.md；scripts/sync_rules.py、scripts/land_rules_commit.py、scripts/onboard/、sync-targets.json；templates/*.project.md；[subagent-claude-vs-codex.md](subagent-claude-vs-codex.md)；[merge-decisions.md](merge-decisions.md) P、Q |
| 2026-09-26 | greatlakes 占位 job 口径：任务确定上 GL 时开工先占卡（改代码之前就 sbatch，JobID 记入 `<日志目录>/hold-jobs-<任务名>.txt`，排队与改代码并行）；一切工作负载经 48 h 占位 job + `srun --overlap` 塞入；默认 1 CPU / 24 G；ManiSkill 多 worker 每 worker 1 CPU + 12 G；跑完按清单 `scancel` | 用户原话（见表一 greatlakes.md 行） | greatlakes.md「资源约束」「算力使用规则」「调试 slurm 脚本」；templates/hold_job.sbatch、templates/run_in_hold.sh、templates/greatlakes.project.md；[merge-decisions.md](merge-decisions.md) R |
