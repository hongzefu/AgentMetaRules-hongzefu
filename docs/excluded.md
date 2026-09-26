# 明确不收的项目专属内容

判据：换一个仓库就不成立的内容不进正本。下面按仓库列出被排除的节，每项一句原因，避免误以为遗漏。项目值已参数化为占位符的条目不在此列（见 `AGENTS.md` 附录 A/B）。

**例外（有意保留、不视为项目值泄漏）**：带日期的实测出处与事故复盘里的项目名、工作负载名、run 名与 Slurm job 号——第 7 条「2026-08-06 在 MotionJEPA 仓库做 nohup vs tmux 六判据实测」「2026-08-24 MotionJEPA 仓库两次实测踩中」「一条在跑的 400 ep Wan 抽取」、第 12 条「MotionJEPA v7 前三个 run 都是先起跑后提交」、第 13 条「2026-08-18 随 MotionJEPA v8-400ep 建库定稿」、第 16 条「2026-08-24 v1-e2e-b64 中位 100% 掩盖了均值仅 69-70%」、第 21 条引号内的用户原话 `src/robomme`、`greatlakes.md` 的「MotionJEPA v7 双卡 bf16 的 4 CPU / 16G 降配实例」与 job 号 57854615 / 57856154 等——用于回溯证据来源，与保留 2026-08-14 PENDING 碎片实测数字同性质。规则本体不依赖这些值；具体数据集名、脚本文件名、CLI 参数名仍须参数化。

## robomme_policy_learning_MotionJEPA（`v2-eval-0917`；2026-09-26 复查已改名，sha 不变）

| 被排除内容 | 原因 |
|---|---|
| 判据表两列的具体值（`/data/hongzefu/...`、`/scratch/hongze/...`、2 × RTX 6000 Ada / 8 × A100） | 项目环境实例，改为附录 B 与判据表模板 |
| 「策略评估的工作副本与第三方分支机制」节 | 本轮评估任务的具体授权与分支名；机制抽到第 24 条 |
| 「项目 scope」节（MME-VLA、MotionJEPA motion token、四任务、commit `d951aef` 弃用清单） | 项目目标 |
| 规则 13/14 的具体路径、`v1-store/`、`-temp` 开发副本路径、678 GB 数据集 | 改为 `<WORK_ROOT>` / `<STORE_ROOT>` 等占位 |
| 规则 15 的 `Yinpei/robomme_data_h5`、`external-assets-lock.md` 第五节指引 | 项目数据源 |
| `greatlakes.md`「放行记录（robomme framesamp v2 计划，2026-08-27）」节 | 放行记录留在项目仓库；其中 `--dependency=afterany`、`--exclude`、配额口径已抽入正本 |
| `external-assets-lock.md` 二、三、四节（六条资产表、六处接入、MotionJEPA 权重上传） | 具体资产与代码接入点 |
| `env-b-aws-replication.md` 三、五、六、七、八、九、十一节与附录 | 具体判定行、sha、loss、GPU 分配、A100 实测数字 |

## robomme_benchmark_MotionJEPA（`PolicyEvalThirdParty-v2-eval-0917`；2026-09-26 复查已改名，sha 不变）

| 被排除内容 | 原因 |
|---|---|
| 「仓库目标」「全局执行规则」第 3–4 条（产物落点、`data/robomme_data_h5/`、`.gitignore` 处理）、「第一 / 二 / 三阶段」节 | RoboMME 数据生成恢复任务定义 |
| 「当前进度」表（53 行） | 实验进度 |
| 「追加式执行日志」120 条（只抽 6 条通用教训：2026-09-08 账本冲突补记、2026-09-09 拆分口径 / 编号取舍 / `git apply --cached`、2026-09-11 AST 钉死、2026-09-12 跨运行 glob 事故、2026-09-17 一次性授权措辞） | 执行记录 |
| 规则 1 的英文化遗留豁免清单（`tests/lightweight/test_no_patch_report_debug_environment.py`） | 改为豁免占位 |
| 规则 3 的测试路径（`tests/lightweight/`、`tests/dataset/`、`test_swap_variant_plan.py`） | 改为「项目须列出核心短测」 |
| 规则 6 括注的 `draw_variant_diagrams.py` | 项目脚本 |
| 规则 8 的 `132 MB/s` / `14 TB` 之外的具体目录（`artifacts/generated/`、`outputs/`） | 改为 `<STORE_ROOT>`；132 MB/s 作为 NFS 瓶颈实测数字保留 |
| 规则 11 的默认冻结项（`src/robomme/env_record_wrapper/RecordWrapper.py`、`RobommeRecordWrapper`、`NO RECORD`） | 改为「项目可列默认冻结项」 |
| 引言块的源仓库绝对路径、规则 10 的导入链接 | 溯源已在 `sources.md` |

## robomme-eval-GL（`v2-vail-eval-0917`）

| 被排除内容 | 原因 |
|---|---|
| 「仓库用途」「两份源码的职责」节 | RoboMME 两进程 WebSocket 评测拓扑 |
| 规则 3 的双环境具体名（服务端 `robomme_policy_learning`、客户端 `.envs/robomme-uv`、`scripts/setup_uv_client.sh`、历史 `.envs/robomme`） | 改为第 3 条通用表述 |
| 规则 5 的目录名与 `SOURCE_ORIGINS.json` / `scripts/bootstrap.sh` 文件名 | 改为第 24 条「来源清单文件」 |
| 规则 6(a) 的包名、校验脚本名与反例路径；6(b) 整条；6(c) 的 ManiSkill sha | 改为第 24 条 editable 校验、第 15 条锁 40 位 sha |
| 规则 8 末段「greatlakes.md 全文没有任何 eval 相关内容」 | 本仓库专属说明 |
| 规则 10 的 `eval.py --args.save_dir`、`serve_policy.py --policy.dir`、`compute_results.py` 软链例外 | 项目 CLI |
| 规则 14 的 16 任务 / 800 ep / `--args.only_tasks` / `XLA_PYTHON_CLIENT_MEM_FRACTION=0.7` / 健康检查文件路径 / SAPIEN 渲染后端 | 改为第 23 条模式 |
| 规则 15 的官方 `eval.py` 缺陷链定位 | 改为第 23 条「不依赖重试到出文件」 |
| README 的权重、任务清单、作业号 61331555、`srun --overlap --exact` 复用分配 | 项目实例 |
| CLAUDE.md Monitor 第 7 条的特征行字符串（`Error saving final results`、`Error evaluating episode`） | 改为 CLAUDE.md Monitor 第 7 条模式，项目 CLAUDE.md 填字符串 |

## MotionJEPA（`v6.1.2-awsNoSlurm`）

| 被排除内容 | 原因 |
|---|---|
| 「当前运行环境与存储边界」的具体值（`/scratch/hongze/MotionJEPA`、`/dev/md0`、8 × A100、2026-09-12） | 改为附录 B |
| 「项目概览」「环境」「原始数据来源（溯源）」「常用命令」「项目结构」「架构」及其七个子节 | 任务定义、数据集规格、模块路径、超参与实验结论 |
| 规则 4 的九个测试文件、`smoke_wan_local2gpu.sh`、`html_site.py` / `label_swap.py` 的 Playwright 测试、commit `333c29b` | 改为「项目须列出核心短测」；静态检查不能替代实跑的教训保留 |
| 规则 10 的 `wan-plan §7.3` 与 `tests/test_train_script_overrides.py` | 改为「项目自身的覆盖白名单」 |
| 规则 12 的归档文件名（`sig_loss_epoch1.csv`、`latent_eval_checkpoints.*`、`motion_usage_ep*.json`）、`configs/default.yaml`、v7 三个 run 名 | 改为通用归档描述；「先起跑后提交」教训保留 |
| 规则 13（数据路径核实：`/data/hongzefu/dataset-4env-v7`、rsync 命令） | 项目数据；「跨环境比较在当前环境重测」一句已入第 16 条 |
| 规则 14（评估指标绝对口径：四臂 / latent / VAE 底噪线 / motion_utilization） | 项目指标定义 |
| 规则 15 的 `KIND=full*`、G1–G10、`make_mask_stats.json`、十三节 / 五节体例、`dataset-v8-400ep-plan-v1.md §F` | 改为第 13 条通用表述 |
| 「规则迁移来源」的 commit sha 与链接 | 溯源已在 `sources.md` |
| `greatlakes.md`「现成的 slurm 脚本」表、两张 2026-08-14 冒烟实测表、「分布式 Wan latent 抽取」全节 | MotionJEPA 项目实测；其中降配档位、页缓存判读、job array / 依赖链 / 递补语义、跨架构不逐位、HF Hub 可达已抽入正本 |
| `greatlakes.md`「调试 slurm 脚本」的 `training.compile=false` / `§7.3 白名单` 一条 | 改为「只写项目覆盖白名单允许的键」 |

## 本机 `~/.claude/`

| 被排除内容 | 原因 |
|---|---|
| 全局 `CLAUDE.md` 的通用版（`global/CLAUDE.md`） | 用户 2026-09-18 决定不收；其内容已全部并入正本（2026-09-26 起全局 `~/.claude/CLAUDE.md` 改为 `@` 导入本仓库正本，不再需要单独的通用版） |
| `~/.claude/greatlakes.md` 副本 | 与 policy 版一致（旧一行），以本仓库正本替代 |
