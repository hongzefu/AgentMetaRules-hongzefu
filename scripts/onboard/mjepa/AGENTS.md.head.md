## 通用规则（AgentMetaRules 正本副本）

下方标记块 `common-agents` 是 [AgentMetaRules-hongzefu](https://github.com/hongzefu/AgentMetaRules-hongzefu) 正本 `AGENTS.md`「强制规则」第 1–26 条与附录 A 的逐字副本（标记行 `src=` 记正本 commit、`blob=` 记块内容 blob id，**块内禁止手改**；同步核对命令 `uv run --no-project python /data/hongzefu/AgentMetaRules-hongzefu/scripts/sync_rules.py check --repo mjepa`）。优先级：系统 / 开发者 / 用户当前指令 > 标记块外明确写出的覆盖项 > 标记块内的正本条目。平时只读本文件，不需要去读 GitHub 上的正本；正本改动经同步脚本回流。标记块之后是本仓库的项目专属规则、覆盖项、占位符取值与规则来源；再之后是项目概览、环境、数据来源、常用命令、项目结构与架构各节。

### 0. 运行环境判定（正本第 0 条的本仓库实例）

上方「当前运行环境与存储边界」记录的是环境 B（AWS 单机）的实测口径；本仓库在 sled 主机上也有检出，开工先按正本第 0 条跑判定命令并写明结论：

| 判据 | 环境 A：sled 主机 / NFS 检出（2026-09-26 口径） | 环境 B：AWS 单机（2026-09-12 口径） |
|---|---|---|
| 主机名（`hostname` 前缀） | `sled-vail` / `sled-aspen` | 非 `sled-*` |
| 仓库根 | `/nfs/turbo/coe-chaijy-unreplicated/hongzefu/MotionJEPA`（vail 侧检出） | `/scratch/hongze/MotionJEPA` |
| 共享存储路径（NFS） | `/nfs/turbo/coe-chaijy-unreplicated/hongzefu/` 存在 | 不存在 |
| 本机盘路径 | `/data/hongzefu/` 存在 | 不存在 |
| 单机工作盘路径 | 无 | `/scratch/hongze`（`/dev/md0`，本地 NVMe RAID） |
| `~/.ssh/config`（集群 ControlMaster） | 存在 | 不存在 |
| GPU（型号 × 数量） | 2 × RTX 6000 Ada（vail）/ 2 × RTX A6000（aspen） | 8 × A100-SXM4-80GB |
| Slurm / 集群提交 | 可用（greatlakes 占位 job，`greatlakes.md`） | 不可用，禁止 |
| 原始数据 | NFS 原件 + `/data/hongzefu/dataset-4env-*` 本机副本 | `/scratch/hongze/` 内已核实副本 |
| 可做的事 | 评估 / 可视化 / 轻量测试；大批量整批上 greatlakes 或 aspen | 全量训练、抽取、建库 |

**冲突即停**（正本第 0 条）：判定输出与上表任一列不符或两列矛盾，一律停下把原始输出交用户裁决，不得自行挑一列往下走。

