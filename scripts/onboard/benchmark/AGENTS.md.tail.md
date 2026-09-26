
## 项目专属规则

- **P1. `scripts/` 顶层只允许存在五个入口文件，新增任何顶层文件必须先与用户沟通并获准。**（2026-09-22 用户原话「只保留这五个入口 以后新增要和用户沟通」。）
    - **五个入口**：`generate_dataset_newseed.py`（主入口：生成 / `--extract-config` / `--merge-only`）、`seed_layout.py`（seed 公式与 16 任务规范序）、`dataset_replay.py`、`evaluation.py`、`run_example.py`。后三者与上游 main 逐字节相同，不得改动。
    - **其余一律收进子目录**：新值注入链路进 `scripts/injection/`（含 `hf_release.py`）；对拍链路进 `scripts/parity/`（`train_split_*.py` 六件、`comparator_fixtures.py`、`compare_vs_original.py`、`calibrate.py` 等）；冻结配置进 `scripts/configs/`。
    - **本条约束的是"新增顶层文件"这个动作**，不是禁止写新脚本：新脚本默认落到已有子目录；确实不属于任何现有子目录时，先向用户说明用途与建议位置，获准后再建新子目录。临时脚本一律写到 scratchpad 或 `artifacts/`，不得落在 `scripts/` 顶层。
    - 核查方式：`ls -1 scripts/*.py` 应恰好列出上述五个文件。
- **P2. 对 `src/robomme/` 的任何改动和覆盖都必须由用户逐个批准**（正本第 21 条的本仓库实例，`<PROTECTED_DIRS>` = `src/robomme/`；2026-09-10 用户原话「在agentsmd中加入新约定 对 src/robomme 的任何改动和覆盖 都需要用户逐个批准」）。
    - **「改动」**指对该目录下任何文件的新增、修改、删除、重命名；**「覆盖」**指不改源文件但改变其运行行为的一切手段：子类覆写方法、monkeypatch、运行时替换类或函数、导入钩子打补丁、`sys.modules` 注入替身等。两者同等对待。
    - **逐个批准**：动手前先列出「文件 / 函数或类锚点 / 改什么 / 为什么」清单交用户，用户逐条明确同意后只改被同意的那一条；同一文件里未点名的其他改动、以及「顺手修」都不算获准。计划文档里写了改动清单不等于批准；某一处获准也不延伸到下一处或下一轮。
    - **默认冻结项**：录像器 `src/robomme/env_record_wrapper/RecordWrapper.py`（`RobommeRecordWrapper` 的视频合成、`NO RECORD` 阶段跳过、不补 reset 帧、命名与落盘位置）当前明确冻结，不改、不覆盖；需要视频状态时在生成入口 `scripts/` 侧做只读核验。验证命令 `git diff --quiet HEAD -- src/robomme/env_record_wrapper/RecordWrapper.py`。
    - 测试代码在 `tests/` 里对 `src/robomme` 做的临时 mock／patch 仅限测试进程内且不落盘时不受本条约束；但生产入口（`scripts/`）与对拍观察器对 `src/robomme` 的运行时补丁属于「覆盖」，同样逐个批准。

## 对正本的覆盖项（按正本条号；未列出的条目按正本执行）

- **覆盖第 1 条（历史英文化遗留）**：无豁免清单——原豁免对象 `scripts/data-generation-v2-noPatch/` 与 `tests/lightweight/test_no_patch_report_debug_environment.py` 已于 2026-09-09 删除。
- **覆盖第 2 条（计划密度标杆与命名）**：`<PLAN_EXEMPLAR>` = policy 仓库 [`0901-motion-memory-plan.md`](https://github.com/hongzefu/robomme_policy_learning_MotionJEPA/blob/v2-motionmem/0901-motion-memory-plan.md) 的「第一部分（给人看）」（原链接名 `motion-memory-plan.md` 已改名）；本仓库既有计划文件沿用现名（`NEWTASK_RELEASE_V*_PLAN.md`、`INJECTION_REFACTOR_PLAN.md`），新计划按正本 `MMDD-<主题>-plan.md` 命名。
- **覆盖第 4 条（核心短测）**：无需数据集的核心短测 `timeout 280s uv run --no-sync python -m pytest tests/lightweight/ -m 'not gpu and not slow' -q`（2026-09-26 账本口径；`tests/lightweight/` 全量实测超过 5 分钟，历史 710 s）；需要数据集 / MuJoCo 环境的条件测试 `uv run --no-sync python -m pytest tests/dataset/ -q`；只改某条生成链路时至少跑该链路的定向单测；涉及实跑生成一律先做「单任务、单 episode、单 worker」smoke。
- **覆盖第 5 条**：本仓库所有可视化脚本同受最近邻放大约束。
- **覆盖第 11 条（commit 体例与 push）**：`<COMMIT_SUBJECT_STYLE>` = `<大版本>.<小版本>[.<修订>] <中文描述>`（如 `2.9.2 变体简图出图验证与账本补记`），从 `git log` 最近一次接续；主分支 commit 后立即 push（正本口径）；V6 对拍用的副本分支（`v6-draft/*` worktree 上的分支）一律不 push（2026-09-26 用户决策）。
- **覆盖第 14 条（存储）**：`<WORK_ROOT>` = `/data/hongzefu/robomme_benchmark_MotionJEPANewTask`；`<STORE_ROOT>` = `artifacts/`（`.gitignore` 整体忽略，`artifacts/injection/` 例外）；跨仓库引用 MotionJEPA 侧数据时优先取 `/data/hongzefu/` 下的本机副本，NFS 原件是权威源、同步只用 rsync；集群侧克隆 `<GL_REPO>` 的产物落 NFS、比较在本机跑。
- **覆盖第 21 条**：见 P2。
- **覆盖第 22 条（账本）**：本仓库以本文件末尾的「当前进度」与「追加式执行日志」为持续状态账本，`<DOC_ROOT>` = 本文件账本 + `docs/`（验证与实测记录）。

## 占位符取值

| 占位符 | 本仓库取值 |
|---|---|
| `<WORK_ROOT>` | `/data/hongzefu/robomme_benchmark_MotionJEPANewTask` |
| `<ARCHIVE_ROOT>` | 无 |
| `<STORE_ROOT>` | `artifacts/` |
| `<DOC_ROOT>` | 本文件账本；`docs/` |
| `<FAST_LOCAL_CACHE_ROOT>` | 默认（本机盘） |
| `<PY_INTERPRETER>` | 本仓库 uv 管理的 `.venv` |
| `<SHARED_ROOT>` / `<LOCAL_ROOT>` / `<SINGLE_NODE_ROOT>` | `/nfs/turbo/coe-chaijy-unreplicated/hongzefu` / `/data/hongzefu` / 无 |
| `<GL_REPO>` | `/nfs/turbo/coe-chaijy-unreplicated/hongzefu/robomme_benchmark-newtask-gl` |
| `<GL_SUBMIT>` | 不用提交器；占位 job 按 `greatlakes.md` 标准提交块手提 |
| `<GL_ACCOUNT>` / `<GL_PARTITION>` / `<SSH_HOST>` | `chaijy2` / `spgpu` / `greatlakes` |
| `<PROTECTED_DIRS>` | `src/robomme/`（默认冻结 `src/robomme/env_record_wrapper/RecordWrapper.py`） |
| `<COMMIT_SUBJECT_STYLE>` | `<大>.<小>[.<修订>] <中文描述>` |
| `<PLAN_EXEMPLAR>` | policy 仓库 `0901-motion-memory-plan.md` 第一部分 |

## 规则来源与未采用清单

- 通用规则 = 上方标记块，正本 commit 见标记行 `src=`（2026-09-26 首次接入；此前本文件的强制规则 1–13 是 2026-08-18 自 MotionJEPA 移植、2026-09-09 拆分后的旧版）。
- 未采用的正本条目及原因：第 10 条（训练超参落点）、第 12 条（训练 / 评估留档）、第 16 条（GPU 利用率判读）、第 18 条（训练链路一致性）——本仓库无训练链路；第 13 条（数据集构建 Beta 体例）——本仓库生成留档走账本与 `docs/validation/`，不打 Beta commit；第 24 条（submodule / vendoring）——本仓库以 `scripts/parity/` 的隔离官方源码树（`--official-root`）与 AST 钉死 `scripts/` 不依赖 `tests/` 为准。
- 旧条号对照（2026-09-26 之前的历史账本沿用旧号）：旧 1 → 正本第 1 条；旧 2 → 第 3 条；旧 3 → 第 4 条（覆盖）；旧 4 → 第 7 条；旧 5 → 第 9 条；旧 6 → 第 5 条；旧 7 → 第 11 条（覆盖）；旧 8 → 第 14 条（覆盖）；旧 9 → 第 20 条；旧 10 → 第 2 条；旧 11 → P2 / 第 21 条；旧 12 → P1；旧 13 → 第 26 条。
- Claude Code 独有机制见同目录 `CLAUDE.md`（标记块 `common-claude`）；集群规约见 `greatlakes.md`（标记块 `common-greatlakes`）与 `docs/greatlakes.md`（本仓库实测记录）。两份文件冲突时以本文件为准。

