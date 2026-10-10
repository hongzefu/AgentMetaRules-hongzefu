# AgentMetaRules-hongzefu

hongzefu 名下所有仓库通用 agent 工作规则的**单一真源**。与具体项目无关的条目——`AGENTS.md` 第 0–26 条（第 20 条仅 Codex；第 26 条统一两宿主子代理职责并保留 Harness 生命周期差异）、`CLAUDE.md`（Claude Code 的 Agent 子代理与 Workflow、Monitor、Skill、plan mode）与 `greatlakes.md`（占位 job 口径的集群规约）——在这里合成三份正本；项目专属内容一律不收，只留占位符与各仓库实际取值对照表。

各项目仓库自带三份正本通用块的**逐字副本**（用 `AGENTMETARULES` 标记圈出，标记外写项目专属内容），平时只在项目仓库内读写规则；本仓库只在每次同步时用 [`scripts/sync_rules.py`](scripts/sync_rules.py) 检查漂移并回流。用户 2026-09-26 原话：「每个仓库都要有一份agentsmd greatlake md等等 AgentMetaRules只负责每次同步的时候检查一下 平时只在仓库内交互 不要每次都读github太麻烦了」。

## 文件地图

| 路径 | 内容 |
|---|---|
| [`AGENTS.md`](AGENTS.md) | **正本 1**：通用规则第 0–26 条，末尾附录 A 占位符表、附录 B 四仓库实际取值、附录 C 规则来源。通用块 = 「强制规则（最高优先级）」到附录 A 表末，标记名 `common-agents`（第 0 条与附录 B/C 在块外） |
| [`CLAUDE.md`](CLAUDE.md) | **正本 2**：Claude Code 独有操作（`@AGENTS.md` 导入；Agent 一次性按批交回、独立 worktree 修改与起跑交接、Workflow 逐次审批、Monitor、Skill、plan mode）；模型、角色与授权统一引用 `AGENTS.md` 第 26 条。通用块 = `@AGENTS.md` 行之后到文末，标记名 `common-claude` |
| [`greatlakes.md`](greatlakes.md) | **正本 3**：GreatLakes Slurm 提交规约通用部分（认证 / 占位 job 与资源约束 / 路径 / venv / ControlMaster 流程 / Okta / 占位 job 与运行器骨架 / job array / PENDING 读法 / 放行制度 / 算力使用规则）。通用块 = H1 标题之后到文末，标记名 `common-greatlakes` |
| [`sync-targets.json`](sync-targets.json) | 同步目标清单：正本（canon）与三个项目仓库 benchmark（`robomme_benchmark_MotionJEPANewTask` @ `newtaskRelease-v5`）、policy（`robomme_policy_learning_MotionJEPA` @ `v2-motionmem`）、mjepa（NFS 上的 `MotionJEPA` @ `v6.1.2-awsNoSlurm`）、newtask-v3（sled-aspen 本机 `robomme_benchmark_newtask-v3-MotionJepa1006` @ `newtask-v3-MotionJepa1006`，只接 `AGENTS.md` / `CLAUDE.md` 两份，无集群访问不接 `greatlakes.md`；2026-10-06 接入）的路径与分支 |
| [`scripts/sync_rules.py`](scripts/sync_rules.py) | 标记块同步器：`check`（只读比对，末行 `SYNC_SUMMARY=PASS\|FAIL`）、`apply`（只替换标记块并写入 `src=` / `blob=`）、`transform`（对任意版本的文件内容做同一变换）、`blocks`（列出正本通用块）、`lint`（正本标记自检） |
| [`scripts/land_rules_commit.py`](scripts/land_rules_commit.py) | 把规则同步落到带在途工作的仓库：远端侧用 git plumbing 生成只含规则文件的提交，本地侧做合并提交，不暂存、不覆盖在途改动 |
| [`scripts/rehearse_land.sh`](scripts/rehearse_land.sh) | `land_rules_commit.py` 的落地演练脚本（先演练、再真落地） |
| [`scripts/onboard/`](scripts/onboard/) | 首次接入夹具：每个仓库一份 `<repo>.json` 与 head/tail 夹具，按稳定锚点切出标记块位置；写法见目录内 README |
| [`scripts/gl_submit.py`](scripts/gl_submit.py) | 通用提交器：两版合并，`GL_REPO` / `GL_SSH_ALIAS` / `GLUSER` / `GL_CONNECT_LOG` / `GL_PUSH_SENTINEL` 参数化，push 修法三条齐全，ControlPersist 口径 30d |
| [`skills/greatlakes-usage/`](skills/greatlakes-usage/) | 全局 skill `greatlakes-usage` 正本（`SKILL.md`、`check_usage.py`、`gl_master.py`、`gl_connect.py`），已修正 14d / 8h / paramiko 等过期口径，安装到 `~/.claude/skills/greatlakes-usage/` |
| [`templates/AGENTS.project.md`](templates/AGENTS.project.md) | 新项目 `AGENTS.md` 骨架：头部构成说明 + 第 0 条判据表 + `common-agents` 空标记块 + 项目专属规则 + 按条号覆盖项 + 占位符取值 + 项目 scope + 规则来源与未采用清单 |
| [`templates/CLAUDE.project.md`](templates/CLAUDE.project.md) | 新项目 `CLAUDE.md` 骨架：`@AGENTS.md` + `common-claude` 空标记块 + 项目专属补充 |
| [`templates/greatlakes.project.md`](templates/greatlakes.project.md) | 新项目 `greatlakes.md` 骨架：`common-greatlakes` 空标记块 + 项目专属（放行记录 / 现成脚本 / 实测表） |
| [`templates/hold_job.sbatch`](templates/hold_job.sbatch) | 48 h 占位 job 骨架：1 GPU、`--gpu_cmode=shared`、默认 1 CPU / 24G、正文 `sleep infinity`；头注写 ManiSkill 多 worker 变体、JobID 清单与按清单 `scancel` |
| [`templates/run_in_hold.sh`](templates/run_in_hold.sh) | 经 `srun --jobid --overlap --exact` 塞进占位 job 的运行器骨架：计算节点判定 fail-fast + 日志三件套 + `trap cleanup EXIT` + `EXIT_CODE=` |
| [`templates/run_long_task.sh`](templates/run_long_task.sh) | detached tmux + 日志三件套 + `EXIT_CODE=` |
| [`templates/monitor_filter.sh`](templates/monitor_filter.sh) | Monitor 行缓冲过滤管道 |
| [`templates/CLAUDE.global.macbook.md`](templates/CLAUDE.global.macbook.md) | MacBook 单机全局 `~/.claude/CLAUDE.md` 版本：中文沟通 + 从第 3、7 条与 Monitor 节摘出的 uv / tmux / Monitor 本机规则（自包含、不 `@` 导入，符合下文 2026-09-27 约定）；本机需 `brew install tmux` |
| [`docs/sources.md`](docs/sources.md) | 溯源：每条规则来自哪个仓库的哪一节；日期沿革表 |
| [`docs/merge-decisions.md`](docs/merge-decisions.md) | 四仓库版本冲突与机制取舍（A–R）与口径统一清单 |
| [`docs/excluded.md`](docs/excluded.md) | 明确不收的项目专属内容（按仓库列） |
| [`docs/maniskill-multiprocess.md`](docs/maniskill-multiprocess.md) | ManiSkill / robomme 多进程与多 worker 生成的实测经验：`mplib` 墙钟预算导致的不可复现、跨架构不变量、夹爪元素与末段错位陷阱、官方比较器边界、吞吐、容差校验结论（2026-09-22） |
| [`docs/codex-app-ssh-multiagent.md`](docs/codex-app-ssh-multiagent.md) | Codex SSH App 新任务 16 个子代理实测及第 17 个容量拒绝记录；V2 多代理工具集与空闲代理自动卸载（2026-09-26） |
| [`docs/codex-aspen-gpt56-roles.md`](docs/codex-aspen-gpt56-roles.md) | Codex 仅允许 GPT-6、GPT-6.1 系列的现行规则与角色映射；历史文件名和旧验收单独保留（2026-10-10 更新） |
| [`docs/codex-ssh-update.md`](docs/codex-ssh-update.md) | Codex SSH App 更新、常驻后端切换及桌面模型菜单验证记录（2026-10-01） |
| [`docs/subagent-claude-vs-codex.md`](docs/subagent-claude-vs-codex.md) | Claude Code 与 Codex 统一角色政策、各自 Harness 生命周期及带日期官方依据／历史实测对照（2026-10-10 规则修订，非新实测） |
| [`codex/aspen/agents/`](codex/aspen/agents/) | Aspen 六角色配置文件；其中旧 GPT-5.6 绑定已被第 26 条禁止，完成 GPT-6／GPT-6.1 配置迁移与运行时核验前不得加载使用 |

## 来源锚定

「最新分支」= 各仓库最近一次提交所在分支，2026-09-18 查定。所有正文逐字取自这些 commit 的文件；冲突取舍与参数化见 `docs/`。

| 仓库 | 分支（现名） | 取文 sha | 提交时间 (UTC) | 取用文件 |
|---|---|---|---|---|
| [robomme_policy_learning_MotionJEPA](https://github.com/hongzefu/robomme_policy_learning_MotionJEPA) | `v2-eval-0917` | `5a746c6cc1cb16536d49b33466404fc0a1d19805` | 2026-09-18 16:45 | AGENTS.md、CLAUDE.md、greatlakes.md、scripts/training/gl_submit.py、external-assets-lock.md、env-b-aws-replication.md |
| [robomme_benchmark_MotionJEPA](https://github.com/hongzefu/robomme_benchmark_MotionJEPA) | `PolicyEvalThirdParty-v2-eval-0917` | `b4e97f22fe007078e297205898c07c1acbc69165` | 2026-09-18 06:42 | AGENTS.md（强制规则节、全局执行规则、日志模板、6 条通用日志教训）、CLAUDE.md |
| [robomme-eval-GL](https://github.com/hongzefu/robomme-eval-GL) | `v2-vail-eval-0917` | `d4aeff7b64d364c49552383ae1b36334e7f6b4d3` | 2026-09-18 03:27 | AGENTS.md、CLAUDE.md、README.md、scripts/gl_smoke.sbatch |
| [MotionJEPA](https://github.com/hongzefu/MotionJEPA) | `v6.1.2-awsNoSlurm` | `4098a98fb5b81de7207a292366c204c5aca642b5` | 2026-09-14 21:50 | AGENTS.md、CLAUDE.md、greatlakes.md、scripts/train-script-hongzefu/gl_submit.py |
| 本机 `~/.claude/` | — | — | 2026-09-18 快照 | CLAUDE.md（全局）、greatlakes.md 副本、skills/greatlakes-usage/ |

**2026-09-26 复查注记**（取文 sha 不变，只更新分支现状）：

- policy 分支 `v2-vail-eval-0917` 已改名 `v2-eval-0917`，benchmark 分支 `PolicyEvalThirdParty-v2-vail-eval-0917` 已改名 `PolicyEvalThirdParty-v2-eval-0917`；改名不改 sha（仍是 `5a746c6c` / `b4e97f22`），上表已写现名。
- robomme-eval-GL 的 `v2-vail-eval-0917` **未改名**（仍 `d4aeff7b`），但其工作副本 `/nfs/turbo/coe-chaijy-unreplicated/hongzefu/robomme-eval-GL` 已于 2026-09-18 清空归档，清理记录在同级目录 `robomme-eval-GL-cleanup-20260918T032848Z/`；回查原文以 GitHub 上该 sha 为准。
- MotionJEPA `v6.1.2-awsNoSlurm` 分支现 HEAD `bc1523a3`；取文 sha `4098a98f` 仍是其祖先，上表取用文件在两者之间未变。
- policy 另有分支 `v2-eval-0918-motion`（`ba52d79a`）改过 `AGENTS.md`，其增量**尚未回收**进正本。

## 接入新项目（三步）

1. 复制三份 [`templates/AGENTS.project.md`](templates/AGENTS.project.md)、[`templates/CLAUDE.project.md`](templates/CLAUDE.project.md)、[`templates/greatlakes.project.md`](templates/greatlakes.project.md) 到项目根目录，改名为 `AGENTS.md` / `CLAUDE.md` / `greatlakes.md`（不上集群的项目可不要 `greatlakes.md`，并在「规则来源」段写明）。填第 0 条判据表与占位符取值（对照正本 `AGENTS.md` 附录 A/B）；需要偏离正本的条目写进标记外的「对正本的覆盖项（按条号）」，标记块内一字不改。
2. 在 [`sync-targets.json`](sync-targets.json) 登记该仓库（名称、路径、分支），并写 `scripts/onboard/<repo>.json` 夹具（按稳定锚点指明三份文件的标记块位置，写法见 [`scripts/onboard/`](scripts/onboard/) 内 README）。
3. 在本仓库根目录运行 `uv run --no-project python scripts/sync_rules.py apply --repo <name> --onboard scripts/onboard`，把三份通用块填进标记对（BEGIN 行写入 `src=<正本 sha> blob=<块 blob>`）；再跑 `uv run --no-project python scripts/sync_rules.py check --repo <name>`，末行 `SYNC_SUMMARY=PASS` 后按项目自己的第 11 条口径提交（只逐个 `git add` 这三份规则文件）。

## 维护规则

- **改正本先改这里，再回流各项目仓库**，顺序固定：
  1. 在本仓库改正本，`git commit` + `git push`；
  2. `uv run --no-project python scripts/sync_rules.py check --repo <name>` 逐个目标只读比对，报出哪些仓库的标记块漂移；
  3. `apply --repo <name>` 回流——只替换标记块、写入新的 `src=` / `blob=`，标记外的项目内容不动；目标仓库有在途工作时改用 [`scripts/land_rules_commit.py`](scripts/land_rules_commit.py)（远端侧 plumbing 提交 + 本地侧合并提交）。回流只提交这次改到的规则文件，其他文件都不动（用户 2026-09-26 原话：「是否可以只推这次修改的md 其他的都不动？精确按照文件来」）；
  4. 回流 commit 即更新项目「规则来源」段的 sha（BEGIN 行的 `src=`），不再另写「引用 commit」。
- 正本条目**只增不重编号**（第 25 条）；项目里长出的新通用条目（带日期标注与实测出处）回收进正本时，逐字搬运、只改专有名词，并在 [`docs/sources.md`](docs/sources.md) 补一行来源。
- `~/.claude/greatlakes.md` 与 `~/.claude/skills/greatlakes-usage/` 是本仓库对应文件的副本，正本更新后重新同步：`cp greatlakes.md ~/.claude/greatlakes.md`、`cp -r skills/greatlakes-usage ~/.claude/skills/`。
- 全局 `~/.claude/CLAUDE.md` **不再** `@` 导入本仓库（2026-09-27 撤掉；2026-09-26 曾改为两行 `@` 导入，2026-09-18 曾决定不提供全局替换版）。原因：正本与项目标记块是同一份内容，双份注入使每个会话启动即多占约 30k token（MotionJEPA 实测启动注入 139k 字 → 78k 字）。会话里生效的只有项目仓库内的标记块副本；未接入的目录先按第 25 条用 `sync_rules.py` 接入。全局文件只保留「本机专属」一节。**不得再把 `@` 导入加回全局文件。**旧版（2026-09-01）「greatlakes 集群」一节的过期提交器路径与权威源指向随之失效（见 [`docs/merge-decisions.md`](docs/merge-decisions.md) C、D 两项）。
- Codex 侧：`~/.codex/AGENTS.md` 指向本仓库 `AGENTS.md`；`~/.codex/config.toml` 设 `project_doc_max_bytes = 131072`——Codex 默认只读 `AGENTS.md` 前 32 KiB，正本与各项目副本都已超过，不调大会静默丢掉后半截规则（见 [`docs/merge-decisions.md`](docs/merge-decisions.md) P）。
- Aspen Codex 角色：本仓库 `codex/aspen/agents/*.toml` 是正本，安装时逐个复制为 `~/.codex/agents/*.toml` 普通文件；`~/.codex/config.toml` 的主模型与 `[agents]` 默认值按 [`docs/codex-aspen-gpt56-roles.md`](docs/codex-aspen-gpt56-roles.md) 固定。2026-10-06 实测仓库外符号链接不会注册为可用角色，因此正本更新后必须重新复制并运行逐文件哈希与运行时验收。

## MotionJEPA NFS 检出接续步骤

用户 2026-09-26 决定 MotionJEPA 本轮**只推远端**：规则同步提交只落到 GitHub 上的 `v6.1.2-awsNoSlurm`，NFS 检出 `/nfs/turbo/coe-chaijy-unreplicated/hongzefu/MotionJEPA` 的工作区本轮不动。下次在该检出里工作时按以下顺序接续，**禁止 rebase**：

1. 先按其第 11 条 commit 在途改动（逐个 `git add` 本轮文件）；
2. `git fetch origin`；
3. `git merge origin/v6.1.2-awsNoSlurm`（`git merge` 本身不 rebase；`--no-rebase` 是 `git pull` 的参数，`git merge` 不认，写上会报 `unknown option`）；
4. 三份规则文件若冲突：逐个 `git checkout --ours -- AGENTS.md`（`CLAUDE.md`、`greatlakes.md` 同理）保留本地版，再在本仓库根目录跑 `uv run --no-project python scripts/sync_rules.py apply --repo mjepa --onboard scripts/onboard` 重新填入标记块；
5. `git add AGENTS.md CLAUDE.md greatlakes.md`，`git commit` 完成 merge；
6. `uv run --no-project python scripts/sync_rules.py check --repo mjepa` 末行 `SYNC_SUMMARY=PASS` 后 `git push`。

## 本仓库自身的纪律

本仓库只有文档与少量脚本，按正本第 4 条的纯文档口径验证，提交前逐项跑：

- `git diff --check`；
- 相对链接可解析、正本内不残留项目专属路径；
- `uv run --no-project python scripts/sync_rules.py lint`（正本标记自检）；
- `uv run --no-project python scripts/sync_rules.py check`（各目标仓库副本比对，末行看 `SYNC_SUMMARY=`）；
- `uv run --no-project python -m py_compile scripts/*.py`；
- `bash -n templates/*.sh templates/*.sbatch`。

commit subject 用 `docs:` / `fix:` 前缀，body 按第 11 条六项写。作者身份 `hongzefu <hongzefu@users.noreply.github.com>`（仅本仓库 `git config --local`）。
