#!/usr/bin/env bash
# GreatLakes sbatch 骨架模板（通用正本）。对应 greatlakes.md「调试 slurm 脚本」与 AGENTS.md 第 0、8、23 条。
# 使用前把尖括号占位符全部替换；资源值默认为日常调试包络（≤2 GPU、≤00:30:00），超出须用户逐次放行。
#
#SBATCH --job-name=<项目>-<用途>-smoke
#SBATCH --account=<GL_ACCOUNT>
#SBATCH --partition=<GL_PARTITION>
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=4
#SBATCH --gpus-per-node=1
#SBATCH --mem=32G
#SBATCH --time=00:30:00
#SBATCH --output=<GL_REPO>/<STORE_ROOT>/logs/%x-%j.log
# 注：不要加 --qos=interactive（chaijy2/spgpu 实测报 Invalid qos specification），用默认 qos。
# 注：spgpu 强制至少 1 GPU（--gpus-per-node=0 报 QOSMinGRES，2026-06-17 实证），纯 CPU 测试 job 也要带 1 GPU。
# 注：同卡跑多个需要独立 CUDA 上下文的进程（如 server + client 共驻）时加 `#SBATCH --gpu_cmode=shared`。
# 注：多片并行用 `#SBATCH --array=0-N`，每片必须用独立输出目录；串接用 `--dependency=afterok:<jobid>`。
set -euo pipefail

# ---- 占位符（替换成项目实际值；保持引号，尖括号在 shell 里会被当成重定向）----
REPO="<GL_REPO>"                       # 集群侧可见的仓库绝对路径
SHARED_ROOT="<SHARED_ROOT>"            # 计算节点唯一可见的共享路径
LOCAL_ROOT="<LOCAL_ROOT>"              # 本机盘路径（计算节点上必须不存在）
EXPECTED_GPU="NVIDIA A40"              # 分区 GPU 型号
RUNNER="<运行器脚本相对路径>"           # 带 trap cleanup EXIT 与日志三件套的运行器
DIAG_LEFTOVERS=""                      # 上一轮诊断遗留的环境变量名，空格分隔；作业模板不得继承它们

# 作业模板不得继承上一轮诊断遗留的兼容开关或设备覆盖：在此显式 unset。
[ -n "$DIAG_LEFTOVERS" ] && unset $DIAG_LEFTOVERS

# 计算节点判定：把 AGENTS.md 第 0 条的判据表编码成逐行 fail-fast，判据不符一律 exit 2，不接受第三套硬件或本机路径泄漏。
hostname
[[ "$(hostname)" == gl* ]] || { echo "不是 GreatLakes 计算节点: $(hostname)"; exit 2; }
[[ -d "$SHARED_ROOT" ]] || { echo "共享路径不可见: $SHARED_ROOT"; exit 2; }
[[ ! -e "$LOCAL_ROOT" ]] || { echo "本机路径泄漏到计算节点: $LOCAL_ROOT"; exit 2; }
! command -v micromamba >/dev/null || { echo "计算节点不应有 micromamba"; exit 2; }
! command -v conda >/dev/null || { echo "计算节点不应有 conda"; exit 2; }
GPU_NAMES="$(nvidia-smi --query-gpu=name --format=csv,noheader | sort -u)"
[[ "$GPU_NAMES" == "$EXPECTED_GPU" ]] || { echo "GPU 型号不符: $GPU_NAMES"; exit 2; }

cd "$REPO"

# 日志三件套（PYTHONUNBUFFERED=1 / set -o pipefail / tee / EXIT_CODE=）与 `trap cleanup EXIT` 下沉到运行器脚本；
# sbatch 层只做判定 + exec 交棒，让 Slurm 的终止信号直达带清理 trap 的运行器而不是打到 wrapper 上留孤儿。
# 集群侧只用 `.venv/bin/python` 直调或 `uv run --frozen --no-sync`，不在计算节点安装依赖。
# run 名由 SLURM_JOB_ID 派生，天然唯一、可回查；必填参数用 ${N:?中文提示} 缺失即报错退出。
exec bash "$RUNNER" "gl-${SLURM_JOB_ID}" "${1:?必须指定 <第一个参数含义>}" "${2:-<第二个参数默认值>}"
