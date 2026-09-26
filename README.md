# AgentMetaRules-hongzefu

hongzefu 名下所有仓库通用 agent 工作规则的**单一真源**。四个项目仓库各自维护的 `AGENTS.md` / `CLAUDE.md` / `greatlakes.md` 里，与具体项目无关的条目（语言、计划格式、uv、验证、tmux 长任务、集群提交、git commit、留档、存储边界、外部资产、GPU 判读、链路一致性、审计锚定、Codex 回退、受保护目录、证据纪律、服务型作业、源码真源、规则维护，以及 Claude Code 的 Workflow / Monitor / Skill / plan mode 机制）在这里合成三份正本；项目专属内容一律不收，只留占位符与各仓库实际取值对照表。

## 文件地图

| 路径 | 内容 |
|---|---|
| [`AGENTS.md`](AGENTS.md) | **正本 1**：通用规则第 0–26 条，末尾附录 A 占位符表、附录 B 四仓库实际取值、附录 C 规则来源 |
| [`CLAUDE.md`](CLAUDE.md) | **正本 2**：Claude Code 独有机制（`@AGENTS.md` 导入；Workflow 与 Agent 模型、Monitor、Skill、plan mode） |
| [`greatlakes.md`](greatlakes.md) | **正本 3**：GreatLakes Slurm 提交规约通用部分（认证 / 资源 / 路径 / venv / ControlMaster 流程 / Okta / sbatch 骨架 / job array / PENDING 读法 / 放行制度） |
| [`scripts/gl_submit.py`](scripts/gl_submit.py) | 通用提交器：两版合并，`GL_REPO` / `GL_SSH_ALIAS` / `GLUSER` / `GL_CONNECT_LOG` / `GL_PUSH_SENTINEL` 参数化，push 修法三条齐全，ControlPersist 口径 30d |
| [`skills/greatlakes-usage/`](skills/greatlakes-usage/) | 全局 skill `greatlakes-usage` 正本（`SKILL.md`、`check_usage.py`、`gl_master.py`、`gl_connect.py`），已修正 14d / 8h / paramiko 等过期口径，安装到 `~/.claude/skills/greatlakes-usage/` |
| [`templates/AGENTS.project.md`](templates/AGENTS.project.md) | 新项目 `AGENTS.md` 骨架：引用正本 sha + 判据表 + 占位符取值 + 显式覆盖项 + 规则来源与未采用清单 |
| [`templates/CLAUDE.project.md`](templates/CLAUDE.project.md) | 新项目 `CLAUDE.md` 骨架 |
| [`templates/job.sbatch`](templates/job.sbatch) | sbatch 骨架：`#SBATCH` 头 + 内嵌计算节点判定 fail-fast + `exec` 交棒 |
| [`templates/run_long_task.sh`](templates/run_long_task.sh) | detached tmux + 日志三件套 + `EXIT_CODE=` |
| [`templates/monitor_filter.sh`](templates/monitor_filter.sh) | Monitor 行缓冲过滤管道 |
| [`docs/sources.md`](docs/sources.md) | 溯源：每条规则来自哪个仓库的哪一节；日期沿革表 |
| [`docs/merge-decisions.md`](docs/merge-decisions.md) | 四仓库版本冲突的取舍（A–M）与口径统一清单 |
| [`docs/excluded.md`](docs/excluded.md) | 明确不收的项目专属内容（按仓库列） |
| [`docs/maniskill-multiprocess.md`](docs/maniskill-multiprocess.md) | ManiSkill / robomme 多进程与多 worker 生成的实测经验：`mplib` 墙钟预算导致的不可复现、跨架构不变量、夹爪元素与末段错位陷阱、官方比较器边界、吞吐、容差校验结论（2026-09-22） |
| [`docs/codex-app-ssh-multiagent.md`](docs/codex-app-ssh-multiagent.md) | Codex SSH App 新任务 16 个子代理实测及第 17 个容量拒绝记录（2026-09-26） |

## 来源锚定

「最新分支」= 各仓库最近一次提交所在分支，2026-09-18 查定。所有正文逐字取自这些 commit 的文件；冲突取舍与参数化见 `docs/`。

| 仓库 | 分支 | HEAD sha | 提交时间 (UTC) | 取用文件 |
|---|---|---|---|---|
| [robomme_policy_learning_MotionJEPA](https://github.com/hongzefu/robomme_policy_learning_MotionJEPA) | `v2-vail-eval-0917` | `5a746c6cc1cb16536d49b33466404fc0a1d19805` | 2026-09-18 16:45 | AGENTS.md、CLAUDE.md、greatlakes.md、scripts/training/gl_submit.py、external-assets-lock.md、env-b-aws-replication.md |
| [robomme_benchmark_MotionJEPA](https://github.com/hongzefu/robomme_benchmark_MotionJEPA) | `PolicyEvalThirdParty-v2-vail-eval-0917` | `b4e97f22fe007078e297205898c07c1acbc69165` | 2026-09-18 06:42 | AGENTS.md（强制规则节、全局执行规则、日志模板、6 条通用日志教训）、CLAUDE.md |
| [robomme-eval-GL](https://github.com/hongzefu/robomme-eval-GL) | `v2-vail-eval-0917` | `d4aeff7b64d364c49552383ae1b36334e7f6b4d3` | 2026-09-18 03:27 | AGENTS.md、CLAUDE.md、README.md、scripts/gl_smoke.sbatch |
| [MotionJEPA](https://github.com/hongzefu/MotionJEPA) | `v6.1.2-awsNoSlurm` | `4098a98fb5b81de7207a292366c204c5aca642b5` | 2026-09-14 21:50 | AGENTS.md、CLAUDE.md、greatlakes.md、scripts/train-script-hongzefu/gl_submit.py |
| 本机 `~/.claude/` | — | — | 2026-09-18 快照 | CLAUDE.md（全局）、greatlakes.md 副本、skills/greatlakes-usage/ |

## 接入新项目（三步）

1. 复制 [`templates/AGENTS.project.md`](templates/AGENTS.project.md) 与 [`templates/CLAUDE.project.md`](templates/CLAUDE.project.md) 到项目根目录，改名为 `AGENTS.md` / `CLAUDE.md`。
2. 填占位符：判据表两列、`<WORK_ROOT>` / `<STORE_ROOT>` / `<DOC_ROOT>` 等取值（对照 `AGENTS.md` 附录 A/B），并把需要偏离正本的条目写成**按条号的显式覆盖项**。
3. 在「规则来源」段写明引用的本仓库 commit sha，逐条列出未采用的条目及原因（正本第 25 条）。需要集群提交的项目，把 [`greatlakes.md`](greatlakes.md) 以引用或同步副本接入，并设 `GL_REPO` 指向集群侧仓库路径。

## 维护规则

- **改正本先改这里，再回流各项目仓库**；每次回流在项目 `AGENTS.md`「规则来源」段更新 sha。正本条目**只增不重编号**（第 25 条）。
- 项目里长出的新通用条目（带日期标注与实测出处）回收进正本时，逐字搬运、只改专有名词，并在 [`docs/sources.md`](docs/sources.md) 补一行来源。
- `~/.claude/greatlakes.md` 与 `~/.claude/skills/greatlakes-usage/` 应为本仓库对应文件的副本：`cp greatlakes.md ~/.claude/greatlakes.md`、`cp -r skills/greatlakes-usage ~/.claude/skills/`。本仓库建库时**未动** `~/.claude/` 下任何文件，是否同步由用户决定。
- 全局 `~/.claude/CLAUDE.md`（2026-09-01 版）与本仓库 `AGENTS.md` 内容同源；其「greatlakes 集群」一节写的提交器路径 `scripts/train-hongzefu/gl_submit.py` 在任何仓库里都不存在、权威源指向也已过期（见 [`docs/merge-decisions.md`](docs/merge-decisions.md) C、D 两项），建议改指本仓库；本仓库不提供全局 CLAUDE.md 的替换版（用户 2026-09-18 决定）。

## 本仓库自身的纪律

本仓库只有文档与少量脚本，按正本第 4 条的纯文档口径验证：`git diff --check`、相对链接可解析、正本内不残留项目专属路径、`bash -n` 模板、`py_compile` 脚本。commit subject 用 `docs:` / `fix:` 前缀，body 按第 11 条六项写。作者身份 `hongzefu <hongzefu@users.noreply.github.com>`（仅本仓库 `git config --local`）。
