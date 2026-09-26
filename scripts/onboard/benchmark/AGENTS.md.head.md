# RoboMME 新任务发布仓库（newtaskRelease）— AGENTS.md

本文件由三部分构成：①下面的「运行环境判定」与本段头部；②标记块 `common-agents`——[AgentMetaRules-hongzefu](https://github.com/hongzefu/AgentMetaRules-hongzefu) 正本 `AGENTS.md`「强制规则」第 1–26 条与附录 A 的逐字副本（标记行 `src=` 记正本 commit、`blob=` 记块内容 blob id，**块内禁止手改**；同步核对命令 `uv run --no-project python /data/hongzefu/AgentMetaRules-hongzefu/scripts/sync_rules.py check --repo benchmark`）；③标记块之后的项目专属规则、覆盖项、占位符取值与规则来源。仓库目标、当前进度与追加式执行日志（本仓库的持续状态账本，正本第 22 条）保持在文件末尾原样追加。优先级：系统 / 开发者 / 用户当前指令 > 标记块外明确写出的覆盖项 > 标记块内的正本条目。平时只读本文件，不需要去读 GitHub 上的正本；正本改动经同步脚本回流。

## 0. 运行环境判定（每次开工第一步）

（正本第 0 条的本仓库实例。）每次会话开工前、执行任何带路径的命令之前，先跑一次只读判定，并把结论写进当轮第一条回复；判定未完成前不得执行任何带写入的命令：

```bash
echo "repo=$(git rev-parse --show-toplevel 2>/dev/null)"
hostname
for p in /nfs/turbo/coe-chaijy-unreplicated/hongzefu /data/hongzefu ~/.ssh/config; do
  printf '%s: %s\n' "$p" "$([ -e "$p" ] && echo 存在 || echo 不存在)"
done
nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | sort | uniq -c
command -v micromamba >/dev/null && echo "micromamba: 有" || echo "micromamba: 无"
```

| 判据 | 环境 A：sled-vail 本机（2026-09-26 口径） |
|---|---|
| 主机名（`hostname` 前缀） | `sled-vail` |
| 仓库根 | `/data/hongzefu/robomme_benchmark_MotionJEPANewTask`（`newtaskRelease-v5` 分支；`dataset-gen-NewSeed` 分支另检出在 `/data/hongzefu/robomme_benchmark_MotionJEPA`） |
| 共享存储路径（NFS） | `/nfs/turbo/coe-chaijy-unreplicated/hongzefu/` 存在、可直读；集群侧克隆 `robomme_benchmark-newtask-gl` |
| 本机盘路径 | `/data/hongzefu/`（NVMe 14 TB） |
| 单机工作盘路径 | 无（不适用） |
| `~/.ssh/config`（集群 ControlMaster） | 存在（`greatlakes`、`sled-aspen` 别名） |
| GPU（型号 × 数量） | 2 × RTX 6000 Ada |
| Slurm / 集群提交 | 可用：greatlakes `chaijy2` / `spgpu`，一律 48 h 占位 job（见 `greatlakes.md`）；aspen 优先 |
| 原始数据 | 官方参考集与生成产物落 `artifacts/`（不进 git）；跨仓库数据优先取 `/data/hongzefu/` 本机副本 |
| 可做的事 | 生成 / 对拍 / 轻量测试在本机；批量生成整批上 greatlakes 占位 job 或 aspen |

**冲突即停**（正本第 0 条）：判定输出与上表不符（主机名不是 `sled-vail`、NFS 不存在、出现第二套 GPU 等），一律停下把原始输出交用户裁决，不得自行套用。本仓库目前只有这一个环境列；出现其他机器时先补判据表再开工。

