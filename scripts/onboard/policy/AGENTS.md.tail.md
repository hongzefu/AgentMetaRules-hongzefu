
## 对正本的覆盖项（按正本条号；未列出的条目按正本执行）

- **覆盖第 2 条（计划密度标杆）**：`<PLAN_EXEMPLAR>` = 本仓库 `0829-destructive-restructure-plan.md` 第一部分「两条核心保证的原理」一节的分层写法；历史名称与现名的对应见 [计划文件命名迁移表](docs/README.md#计划文件命名迁移表)。
- **覆盖第 4 条（核心短测）**：本仓库尚未固化「任何机器都能跑」的核心短测命令清单；按第 4 条选覆盖改动的最小真实子集（`uv run python -m pytest <定向测试> -q`），纯文档改动至少 `git diff --check`。补齐清单后写回本条。
- **覆盖第 8 条（集群提交按环境分叉）**：环境 A 向 GreatLakes 提交前遵守本仓库 `greatlakes.md`（正本副本 + 项目放行记录）；环境 B 无 `~/.ssh/config`、无 ControlMaster，禁止提交任何 Slurm 作业、禁止 ssh 集群、禁止运行 `scripts/training/gl_submit.py`，训练、建库、评估一律在本机 8×A100 上跑，集群留档只作只读存档。
- **覆盖第 11 条（commit 体例与 push）**：`<COMMIT_SUBJECT_STYLE>` = 功能性改动 `commitV<大版本>.<小版本>: <中文描述>`，文档、修补、撤销用 `docs:`、`fix:`、`revert:`；commit 后立即 push 到 `origin`（`https://github.com/hongzefu/robomme_policy_learning_MotionJEPA.git`），凭据走 gh CLI；当前分支没有 upstream 时先问用户，不得自行 `git push -u`。
- **覆盖第 14 条（工作副本与存储边界，按环境分叉；本仓库原规则 13、14 原文）**：
  - 工作副本位置与存储边界按环境分叉：
    - **环境 A**：**仓库工作副本位于本机 `/data/hongzefu/robomme_policy_learning_MotionJEPA`（2026-09-03 起，`v2-motionmem` 分支）；NFS turbo `/nfs/turbo/coe-chaijy-unreplicated/hongzefu/robomme_policy_learning_MotionJEPA` 那份保留为只读归档。** 一切代码改动、命令运行与新产物都落本机工作副本；不得在 turbo 归档上改代码或写入新产物。turbo 归档保存历史 run 产物与旧基线（`v1-prod-*` run、`4task-gl` / `4task-gl-framesamp` 数据集、`openpi-assets` 权重、`train-assets` 等），本机副本以**只读 symlink 逐项引用**它们、不复制第二份（引用清单与写保护纪律见第 14 条与 `0901-motion-memory-plan.md` 红线 17）。本机 `/data/hongzefu` 的全局原始 H5 照旧永久保留；本机 GPU 承担一致性验证的对照产物、资源档位实测和功能性 smoke run。吞吐基准必须记录**底层存储介质**（本机 NVMe / turbo NFS）与 batch size、worker 数、warmup 和稳定态统计；两种介质的数字不得混比，跨介质对照必须在同一介质上重测。集群侧看不到本机 `/data`，从本机工作副本提交 Slurm 作业不可用（`scripts/training/gl_submit.py` 的 `REPO` 仍指 turbo）。
    - **环境 B（当前）**：**仓库主工作副本位于 `/scratch/hongze/robomme_policy_learning_MotionJEPA`（本地 NVMe RAID `/dev/md0`，6.9 T）。长训练期间主副本锁死只读、开发转到 `-temp` 开发副本的机制见第 14 条环境 B 段的例外条款。**所有持久化文件只能落 `/scratch/hongze/` 下**——原始数据、派生库、索引、缓存、模型权重、tokenizer、checkpoint、日志、run 产物、下载物，一个不例外；不得写 `$HOME`、`/` 或任何其他盘，只有真正的临时文件才用 scratchpad 或 `/tmp`。`/data/hongzefu` 与 `/nfs/turbo/...` 在本环境**不存在**：不得新建指向它们的 symlink，不得把它们写进任何新脚本的默认值；既有代码里的这些路径按各自任务单独立项修，**不静默改、不绕过**。**turbo 上的历史产物在本环境不可得**（`v1-prod-*` run、`4task-gl` / `4task-gl-framesamp` 数据集、`openpi-assets`、`train-assets`、各基线的 `env.json` 与固化梯度数组等），凡依赖它们的对拍、基线复用、第 18 条第二块的「复用既有基线固化产物」路径**一律视作失效**，必须重建基线或改口径，起跑前先问用户。吞吐基准仍必须记录**底层存储介质**（本环境写「AWS 本地 NVMe RAID（`/dev/md0`）」）与 batch size、worker 数、warmup 和稳定态统计；**与历史的 turbo NFS、旧本机 `/data` NVMe 数字不得混比**，跨环境对照必须在当前环境重测。本环境有 8 × A100-80GB，全量训练与建库都在这里跑（见「项目 scope」段），第 12、17 条的留档要求照旧。

  - 除最初的全局原始 H5 外，派生数据、索引、缓存、模型、tokenizer、checkpoint、日志和 smoke 产物都必须放在本仓库目录内，且一律收敛到单一根 `v1-store/`（整体不进 git）——该根随仓库走：**环境 A** 位于 `/data/hongzefu/robomme_policy_learning_MotionJEPA/v1-store/`，**环境 B** 位于 `/scratch/hongze/robomme_policy_learning_MotionJEPA/v1-store/`（当前尚不存在，首次跑 `paths.sh` 的 `v1_prepare_dirs` 时创建）。不得自行把新的外部目录作为长期依赖。
    - **仅环境 A 适用**：**turbo 归档的旧产物只能以只读 symlink 引用**——symlink 逐项指向具体目录或文件、不整层链；禁止穿透 symlink 向 turbo 写入。
    - **环境 B**：**主工作副本** `/scratch/hongze/robomme_policy_learning_MotionJEPA/` 的 `v1-store/` 下**没有任何 symlink 外链，全部是实体目录**。
      **唯一例外——开发副本（2026-09-15 用户批准）**：长训练期间主副本要锁死只读（第 13 条环境 B 段），开发工作转到 `/scratch/hongze/robomme_policy_learning_MotionJEPA-temp/`，而 3.9 T 的 `v1-store` 不可能复制第二份，故开发副本的 `v1-store` **整体是一条指向主副本 `v1-store/` 的 symlink**。它与环境 A 的只读 turbo 链性质不同——**这条链是可写的**，因此：
      - 开发副本里一切写入 `v1-store/` 的操作**等同于直接写主副本数据**，按写主副本的标准审慎对待；
      - **红线**：开发副本里**禁止执行任何带 `--force` 或输出根参数的破坏性命令**（`build_dataset.py --force` 会 `rmtree` 整个输出根，穿透 symlink 即删主副本数据）。确需执行时回到主副本，并按下一条先 `ls -ld` 确认；
      - 开发副本**必须有自己的 `.venv`**，不得共用主副本的——共用时 `uv sync` / `uv add` 会换掉正被训练进程使用的包文件，dataloader worker 重建时读到新文件即污染在跑的训练；
      - 开发副本是**临时工作区**，不跨长训练周期保留；训练结束、主副本解除只读后即可删除，或与主副本同步后继续用。仓库权威副本始终是主副本。
    - 两个环境都适用：凡带 `--force` 或输出根参数的命令起跑前先 `ls -ld <输出根>` 确认它是本环境的实体目录（`build_dataset.py --force` 会 `rmtree` 整个输出根）。**禁止覆盖 `HOME`** —— 覆盖会打断 ssh 与一切按 `~` 定位的配置（环境 A 下直接打断集群提交）；改为逐项显式设置 `UV_CACHE_DIR` / `XDG_CACHE_HOME` / `WANDB_*` / `HF_HOME` 等缓存类环境变量指向 `v1-store/cache/`。
- **覆盖第 15 条（原始 H5 的来源与暂存，按环境分叉；本仓库原规则 15 原文）**：
  - 原始 H5 的来源与暂存按环境分叉：
    - **仅环境 A 适用**：为集群作业而在 turbo 上暂存的原始 H5 副本属于**临时暂存**，必须与本机原件逐文件 sha256 核对同源，并在全流程验收通过后删除；本机 `/data` 的原件永久保留。
    - **环境 B（当前）**：无 turbo，本机也**没有 H5 原件**。原始 16 任务 × 100 episode 的 H5 需从公开数据集 `Yinpei/robomme_data_h5` 获取（口径见根目录 `external-assets-lock.md` 第五节「异地无 NFS 机器从零复刻」），落点在 `/scratch/hongze/` 下，并逐文件记 sha256 入 `v1-store/` 的 input manifest。**获取前先与用户确认落点与 episode 口径，不得自行开始几百 GB 的下载。**
- **覆盖第 24 条（第三方源码）**：本仓库以 submodule + 锁定 gitlink 方式引入 `third_party/robomme_benchmark`（来源 RoboMME / robomme_benchmark）；修改第三方代码走 `PolicyEvalThirdParty-<主仓库任务分支>` 专用分支，禁止以 fork 最新 HEAD 替换锁定版本。
- **覆盖第 12 / 13 条（留档根）**：`<DOC_ROOT>` = `docs/training-doc/`（训练 / 评估）与 `docs/dataset-build-doc/`（数据集构建）。

## 占位符取值

| 占位符 | 本仓库取值（环境 A / 环境 B） |
|---|---|
| `<WORK_ROOT>` | `/data/hongzefu/robomme_policy_learning_MotionJEPA` / `/scratch/hongze/robomme_policy_learning_MotionJEPA` |
| `<ARCHIVE_ROOT>` | `/nfs/turbo/coe-chaijy-unreplicated/hongzefu/robomme_policy_learning_MotionJEPA`（只读归档；评估任务经用户授权例外可写） / 无 |
| `<STORE_ROOT>` | `v1-store/` |
| `<DOC_ROOT>` | `docs/training-doc/`、`docs/dataset-build-doc/` |
| `<FAST_LOCAL_CACHE_ROOT>` | `v1-store/cache/` / `/scratch/hongze/.cache` |
| `<PY_INTERPRETER>` | `/nfs/turbo/coe-chaijy-unreplicated/hongzefu/uv-python/cpython-3.11.14-linux-x86_64-gnu/bin/python3.11`（环境 A） / 本机 uv 解释器 |
| `<SHARED_ROOT>` / `<LOCAL_ROOT>` / `<SINGLE_NODE_ROOT>` | `/nfs/turbo/coe-chaijy-unreplicated/hongzefu` / `/data/hongzefu` / `/scratch/hongze` |
| `<GL_REPO>` | `/nfs/turbo/coe-chaijy-unreplicated/hongzefu/robomme_policy_learning_MotionJEPA` |
| `<GL_SUBMIT>` | `scripts/training/gl_submit.py`（`REPO` 仍指 turbo；占位 job 按 `greatlakes.md` 标准提交块） |
| `<GL_ACCOUNT>` / `<GL_PARTITION>` / `<SSH_HOST>` | `chaijy2` / `spgpu` / `greatlakes` |
| `<PROTECTED_DIRS>` | 无 |
| `<COMMIT_SUBJECT_STYLE>` | `commitV<x>.<y>:` + `docs:` / `fix:` / `revert:` |
| `<PLAN_EXEMPLAR>` | `0829-destructive-restructure-plan.md` |

## 项目 scope（未来工作，不代表当前实施授权）

- 仓库总体目标：修改 MME-VLA 的 `perceptual-framesamp-context`，并在后续阶段接入 [MotionJEPA](https://github.com/hongzefu/MotionJEPA) motion token。
- `v1-dataloader-Restructure` 分支只用于 dataloader 重构，目标是在不改变训练语义的前提下尽可能提升训练吞吐。
- v1 只关注 `ButtonUnmask`、`VideoUnmask`、`ButtonUnmaskSwap`、`VideoUnmaskSwap` 四个任务。
- （环境 A 历史口径）四任务全量数据处理在 GreatLakes 上以 8×1GPU job array 完成；本机只跑一致性验证的对照产物、资源档位实测与功能性 smoke run，本机吞吐不作为最终指标。**环境 B 下没有集群**，全量建库、训练与评估一律在本机 8×A100 上完成，本机数字即最终指标。
- 除全局原始 H5 外，后续生成的文件和模型全部放在**当前环境工作副本**的 `v1-store/` 内（环境 A：`/data/hongzefu/robomme_policy_learning_MotionJEPA/v1-store/`；环境 B：`/scratch/hongze/robomme_policy_learning_MotionJEPA/v1-store/`）。
- commit `d951aef` 的 `scripts/v1_dataloader_restructure/` 与 `scripts/smoke_train_once.py` 经判定不可靠，已删除弃用，勿从 git 历史里翻出重新采用。

## 规则来源与未采用清单

- 通用规则 = 上方标记块，正本 commit 见标记行 `src=`（2026-09-26 首次接入；此前本文件的 20 条强制规则为 2026-08 自 MotionJEPA commit `a9a467e3a4536e68f620283703e331ed469a561d` 的 `CLAUDE.md` 迁移并逐步演化的版本，其全部内容已被正本吸收，本轮不再另存）。
- 未采用的正本条目及原因：第 21 条（受保护目录）——本仓库没有需要逐个批准的目录；第 23 条（服务型 / 并发作业）——本仓库评测由 `third_party/robomme_benchmark` 的 server + client 拓扑承担，相关纪律以该第三方分支的 `AGENTS.md` 为准。
- 旧条号对照（历史留档沿用旧号）：旧 1–12 与正本第 1–12 条同号；旧 13 → 第 14 条（覆盖）；旧 14 → 第 14 条（覆盖）；旧 15 → 第 15 条（覆盖）；旧 16 → 第 16 条；旧 17 → 第 17 条；旧 18 → 第 18 条；旧 19 → 第 19 条；旧 20 → 第 20 条。
- Claude Code 独有机制见同目录 `CLAUDE.md`（标记块 `common-claude`）；集群规约见 `greatlakes.md`（标记块 `common-greatlakes` + 本仓库放行记录）。两份文件冲突时以本文件为准。
