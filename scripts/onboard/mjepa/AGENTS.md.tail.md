
## 项目专属规则

- **P1. 评估指标一律绝对口径（2026-08-06 用户拍板）。** 一切 loss 曲线与指标的参照系
    必须统一为绝对参照：
    - **像素域一律对无损源帧比**：四臂 pred vs 源帧 / GT decode vs 源帧（= VAE 底噪
      线，近似下限）。pred 只能逼近不能超越底噪线，模型真实误差 = pred 曲线与噪声线
      的竖直间距；像素 MSE 含 VAE decode 自带损耗，**仅供相对比较，不能当绝对评判
      标准**（逐帧偶发低于底噪线是交叉项噪声，不是"跑赢 VAE"）。
    - **latent 域用归一化 latent MSE**（纯净、无 VAE 参与）——计价基准。
    - **禁止相对参照口径**（如 pred vs GT-decode）及由此派生的比值/百分比指标
      （motion_utilization、"预测/底噪比"、"xx% 低于底噪"这类）。理由：VAE decode 是
      非线性映射，`D(pred) − D(z_gt)` 无可对消的公共项（"同过 decode 可对消 VAE 损耗"
      的论证不成立），且该口径把 `D(z_gt)` 当真值，而它本身就偏离真实帧。
    - ⚠ **训练日志里的相对口径量（tqdm `ident`、`loss_raw/latent_identity(_by_k)`、
      `loss_frac/*`、`loss_weighted/*`、`grad_norm/ratio_*`、tqdm `g_e/dec`）暂未清理
      ——训练侧刻意不动，但这些量在评估中已废弃**；每次涉及训练日志判读/训练指标引用
      时必须主动提醒用户这一点，判读以评估侧绝对口径（四臂绝对 latent/像素 loss）为准。


## 对正本的覆盖项（按正本条号；未列出的条目按正本执行）

- **覆盖第 2 条（计划密度标杆）**：`<PLAN_EXEMPLAR>` = policy 仓库 `0829-destructive-restructure-plan.md`（本仓库原文写的 `v3-destructive-restructure-plan.md` 是该文件旧名）；本仓库既有 `*-plan-v1.md` 计划沿用现名，新计划按正本 `MMDD-<主题>-plan.md` 命名。
- **覆盖第 4 条（核心短测；本仓库原规则 4 子项原文）**：
   - 无需数据集的验证候选：`uv run python tests/test_wan_model.py`、`uv run python tests/test_train_script_overrides.py`、`uv run python tests/test_window_mask.py`、`uv run python tests/test_utils.py`、`uv run python tests/test_viz_grid.py`、`uv run python tests/test_four_arm.py`、`uv run python tests/test_site_pages.py`、`uv run python tests/test_site_video.py`、`uv run python tests/test_label_swap.py`。按改动选取，运行前核实环境与依赖。
   - 有 v7 冒烟数据集时：`uv run python tests/test_dataloader_wan.py --data_root ./dataset-4env-v7-smoke`。
   - 改训练流程时优先实跑核心路径；历史双卡入口 `scripts/train-script-hongzefu/smoke_wan_local2gpu.sh` 按 wan-plan §7.5 跑 8 epoch。AWS 上先核实脚本路径与资源；短测可用更小 epoch 数手起 torchrun，不静默更改全局默认。
   - 改 `scripts/evaluate/common/html_site.py` 时额外运行 `uv run --no-project --with playwright python scripts/evaluate/common/test/test_scatter_interaction.py` 与 `scripts/evaluate/common/test/test_multirun_interaction.py`（后者用同一命令前缀）；历史耗时约 40 秒与 90–150 秒，需要 Plotly CDN。改 `scripts/evaluate/label_swap.py` 的页面或 JS 时运行 `scripts/evaluate/common/test/test_label_swap_interaction.py`（同一前缀，历史约 40 秒，不需外网）。这些测试需 chromium，`--shots <目录>` 留截图供目视复核；不计入无条件短测集，只在改对应页面时必跑。Playwright 使用临时环境，不加入正式依赖。静态文本检查无法替代实跑交互：V7.14 闸门页（333c29b）曾因首次执行 JS 抛错而动态内容全空。
- **覆盖第 8 条（集群提交按环境分叉）**：集群操作仅适用于明确授权且已核实的 GreatLakes 环境（环境 A），向 Slurm 提交前遵守本仓库 `greatlakes.md`（正本副本 + 项目实测节）；环境 B（AWS）默认不执行这些操作，历史命令不能作为已有访问权限或提交授权的依据。
- **覆盖第 10 条（超参落点）**：实际改动还必须满足 wan-plan §7.3 与 `tests/test_train_script_overrides.py` 的覆盖白名单，不能为满足落点选择绕过项目约束。
- **覆盖第 11 条（commit 体例与 push）**：`<COMMIT_SUBJECT_STYLE>` = 功能性改动 `commitV<大版本>.<小版本>: <中文描述>`，文档、修补、撤销用 `docs:`、`fix:`、`revert:`，接续 `git log` 中最近一次 `commitV*`。**本仓库不继承自动推送长期授权**（正本第 11 条声明式例外）：只在当前任务已有推送授权时同步对应分支，不擅自修改 upstream 或凭据；非快进拒绝时保留本地提交并报告，不改写历史。
- **覆盖第 12 条（训练 / 评估留档的本仓库取值）**：`<DOC_ROOT>` = `docs/training-doc/`；归档清单 `metrics/train_metrics_epoch.jsonl`、`metrics/sig_loss_epoch1.csv`、`metrics/train.summary.log`、`eval/latent_eval_checkpoints.{csv,json}`、`eval/motion_usage_ep*.json`、`eval/*.summary.log`；配置 ≡ `configs/default.yaml @ <Beta hash>` + 入口脚本覆盖项，README ③节写 `git show <beta-hash>:configs/default.yaml`；checkpoint 留在 `runs/`；⚠ v7 前三个 run（gate8ep-a / bf16-8ep-a / bf16-72ep-a）先起跑后提交的教训是本条的来源。
- **覆盖第 13 条（数据集构建留档的本仓库取值；主流程 `scripts/dataset-build/`，2026-08-18 随 v8-400ep 定稿，全文出自 dataset-v8-400ep-plan-v1.md §F）**：`<DOC_ROOT>` = `docs/dataset-build-doc/`；正式构建 = 走 `KIND=full*` 的构建，Beta commit 在跑 raw 构造之前；闸门 `CONFIRM_FULL=yes`；归档四道守卫与 G1–G10 的判定行、`compare-output` 的 max|Δ| 输出、`.mem` 采样峰值、pin 快照、`sacct` 耗时表（仅集群任务）、`make_mask_stats.json`；数据集产物留在 `dataset-4env-*/`；完整体例为十三节，冒烟 / 演练可用五节压缩版。
- **覆盖第 14 条（存储边界）**：以上方「当前运行环境与存储边界」为准（环境 B 一切持久化只落 `/scratch/hongze/`，不覆盖 `HOME`，缓存逐项设 `UV_CACHE_DIR` / `HF_HOME` 等）；环境 A 的产物根 `runs/`、`dataset-4env-*`，本机消费数据集优先用 `/data/hongzefu/dataset-4env-*` 本机副本、NFS 原件为权威源、同步只用 rsync。
- **覆盖第 15 条（数据路径；本仓库原规则 13 原文）**：
13. **数据路径按实际环境核实，当前 AWS 使用 `/scratch/hongze/` 内的本地数据。** 不猜测已有副本、数据规模或同步状态；输入需先核实来源，输出需核实实际目录。跨硬件、存储或环境比较必须记录差异，并在当前环境重测。
    - 以下为 **GreatLakes / 旧本机环境的历史规则，当前 AWS 不执行**：本机消费数据集优先使用 `/data/hongzefu/dataset-4env-v7`（2026-08-05 从 NFS 同名目录同步），集群作业使用节点可见的 NFS 路径。旧 `/data` 为本机 NVMe（14 TB），集群节点不可见。
    - 历史实测中 NFS 带宽约 132 MB/s，batch 48→88 时吞吐 234.0→233.6 samples/s，瓶颈为 latent bin 读取。这不是当前 AWS 的带宽或吞吐上限。
    - 历史同步仅使用 rsync，NFS 原件是权威源，原件重建或增量更新后重新同步。以下命令只用于已授权并核实路径的旧环境：
      ```bash
      rsync -a --info=progress2 /nfs/turbo/coe-chaijy-unreplicated/hongzefu/MotionJEPA/dataset-4env-v7 /data/hongzefu/
      ```
- **覆盖第 16 条（性能证据）**：跨硬件、存储或环境比较必须记录差异并在当前环境重测；历史 NFS 带宽约 132 MB/s 与 batch 48→88 吞吐 234.0→233.6 samples/s 的实测不是 AWS 的上限。

## 占位符取值

| 占位符 | 本仓库取值（环境 A / 环境 B） |
|---|---|
| `<WORK_ROOT>` | `/nfs/turbo/coe-chaijy-unreplicated/hongzefu/MotionJEPA`（vail 侧检出） / `/scratch/hongze/MotionJEPA` |
| `<ARCHIVE_ROOT>` | 无 |
| `<STORE_ROOT>` | `runs/`、`dataset-4env-*` |
| `<DOC_ROOT>` | `docs/training-doc/`、`docs/dataset-build-doc/`、`docs/labeldata-eval-doc/` |
| `<FAST_LOCAL_CACHE_ROOT>` | `$HOME/.cache/uv`（NFS 副本时） / `/scratch/hongze/.cache` |
| `<PY_INTERPRETER>` | `/nfs/turbo/coe-chaijy-unreplicated/hongzefu/uv-python/cpython-3.11.14-linux-x86_64-gnu/bin/python3.11`（环境 A） / 本机 uv 解释器 |
| `<SHARED_ROOT>` / `<LOCAL_ROOT>` / `<SINGLE_NODE_ROOT>` | `/nfs/turbo/coe-chaijy-unreplicated/hongzefu` / `/data/hongzefu` / `/scratch/hongze` |
| `<GL_REPO>` | `/nfs/turbo/coe-chaijy-unreplicated/hongzefu/MotionJEPA` |
| `<GL_SUBMIT>` | `scripts/train-script-hongzefu/gl_submit.py`（占位 job 按 `greatlakes.md` 标准提交块） |
| `<GL_ACCOUNT>` / `<GL_PARTITION>` / `<SSH_HOST>` | `chaijy2` / `spgpu` / `greatlakes` |
| `<PROTECTED_DIRS>` | 无 |
| `<COMMIT_SUBJECT_STYLE>` | `commitV<x>.<y>:` + `docs:` / `fix:` / `revert:` |
| `<PLAN_EXEMPLAR>` | policy 仓库 `0829-destructive-restructure-plan.md` |

## 规则来源与未采用清单

- 通用规则 = 上方标记块，正本 commit 见标记行 `src=`（2026-09-26 首次接入）。此前本文件的 20 条强制规则于 2026-09-12 从 `robomme_policy_learning_MotionJEPA` 的 `v2-motionmem` 分支提交 `82c2ccef509d34800a397f547d7144e151cb8d4a` 选择性迁移而来；本仓库原有架构、指标与详细归档要求保留在标记块之外；未迁移源仓库的任务清单、数据布局、下载范围、凭据设置或自动推送长期授权。当前文档不能据此被解读为脚本或数据已经迁移。
- 未采用的正本条目及原因：第 21 条（受保护目录）——本仓库没有需要逐个批准的目录；第 23 条（服务型 / 并发作业）——本仓库无 server + client 评测拓扑，job array 分片纪律按 `greatlakes.md`；第 24 条（第三方源码）——本仓库无 submodule / vendoring。
- 旧条号对照（历史留档沿用旧号）：旧 1 → 正本第 1 条；旧 2 → 第 3 条；旧 3 → 第 8 条（覆盖）；旧 4 → 第 4 条（覆盖）；旧 5 → 第 5 条；旧 6 → 第 6 条；旧 7 → 第 7 条；旧 8 → 第 2 条；旧 9 → 第 9 条；旧 10 → 第 10 条（覆盖）；旧 11 → 第 11 条（覆盖）；旧 12 → 第 12 条（覆盖）；旧 13 → 第 15 条（覆盖）；旧 14 → P1；旧 15 → 第 13 条（覆盖）；旧 16 → 第 17 条；旧 17 → 第 16 条；旧 18 → 第 18 条；旧 19 → 第 19 条；旧 20 → 第 20 条。
- Claude Code 独有机制见同目录 `CLAUDE.md`（标记块 `common-claude`）；集群规约见 `greatlakes.md`（标记块 `common-greatlakes` + 本仓库现成脚本与实测节）。两份文件冲突时以本文件为准。

