#!/usr/bin/env bash
# 占位 job 运行器骨架（通用模板）。对应 greatlakes.md「调试 slurm 脚本」「算力使用规则」与 AGENTS.md 第 0、7、8、23 条。
#
# 用法：占位 job（templates/hold_job.sbatch）就位后，把工作负载经 srun 塞进去：
#   srun --jobid=<占位 JobID> --overlap --exact --ntasks=1 --cpus-per-task=<n> --gpu_cmode=shared \
#     bash templates/run_in_hold.sh <脚本与参数>
# srun 是前台进程：预计超过 5 分钟的工作负载按 AGENTS.md 第 7 条把上面整条命令放进 detached tmux 起，
# 每个工作负载一条 tmux、每份日志一个 Monitor（过滤 EXIT_CODE= 与报错行）。
#
# 结构：unset 诊断遗留开关 → 计算节点判定 fail-fast（任一不符 exit 2）→ cd <GL_REPO>
#       → 日志三件套 + trap cleanup EXIT → 前台运行 "$@" → 由 cleanup 写 EXIT_CODE= 尾行。
# 与原 job.sbatch 的「exec 交棒」同一思路：srun 直接起本运行器，Slurm 的终止信号直达带清理 trap 的进程，
# 不打到 wrapper 上留孤儿；本运行器内部为了 tee 日志不再 exec，改为显式 trap TERM/INT 转成退出码——
# 实测只挂 EXIT trap 时被 TERM 杀掉，trap 里的 $? 是 0，会误写 EXIT_CODE=0。
# 集群侧只用 .venv/bin/python 直调或 uv run --frozen --no-sync，不在计算节点安装依赖。
set -euo pipefail

# ---- 占位符（替换成项目实际值；保持引号，尖括号在 shell 里会被当成重定向）----
REPO="<GL_REPO>"                       # 集群侧可见的仓库绝对路径
SHARED_ROOT="<SHARED_ROOT>"            # 计算节点唯一可见的共享路径
LOCAL_ROOT="<LOCAL_ROOT>"              # 本机盘路径（计算节点上必须不存在）
EXPECTED_GPU="NVIDIA A40"              # 分区 GPU 型号
LOG_DIR="$REPO/<STORE_ROOT>/logs"      # 日志落点，遵守 <STORE_ROOT> 存储边界

[[ $# -ge 1 ]] || { echo "用法: srun --jobid=<占位 JobID> --overlap … bash templates/run_in_hold.sh <脚本与参数>"; exit 2; }

# 作业不得继承上一轮诊断遗留的兼容开关或设备覆盖（srun 默认把提交侧环境原样带进计算节点）：在此显式 unset。
# 按项目实际遗留填变量名，空格分隔，例如 "CUDA_LAUNCH_BLOCKING TORCH_COMPILE_DISABLE PYTORCH_NO_CUDA_MEMORY_CACHING"。
DIAG_LEFTOVERS=""
if [[ -n "$DIAG_LEFTOVERS" ]]; then
  # shellcheck disable=SC2086  # 有意按空格拆分成多个变量名
  unset $DIAG_LEFTOVERS
fi

# ---- 计算节点判定（BEGIN）：把 AGENTS.md 第 0 条的判据表编码成逐行 fail-fast，不接受第三套硬件或本机路径泄漏 ----
[[ -n "${SLURM_JOB_ID:-}" ]] || { echo "不在 Slurm 作业内：须经 srun --jobid=<占位 JobID> --overlap 塞入"; exit 2; }
hostname
[[ "$(hostname)" == gl* ]] || { echo "不是 GreatLakes 计算节点: $(hostname)"; exit 2; }
[[ -d "$SHARED_ROOT" ]] || { echo "共享路径不可见: $SHARED_ROOT"; exit 2; }
[[ ! -e "$LOCAL_ROOT" ]] || { echo "本机路径泄漏到计算节点: $LOCAL_ROOT"; exit 2; }
! command -v micromamba >/dev/null || { echo "计算节点不应有 micromamba"; exit 2; }
! command -v conda >/dev/null || { echo "计算节点不应有 conda"; exit 2; }
GPU_NAMES="$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | sort -u || true)"
[[ "$GPU_NAMES" == "$EXPECTED_GPU" ]] || { echo "GPU 型号不符或 step 未拿到 GPU: ${GPU_NAMES:-无}"; exit 2; }
# ---- 计算节点判定（END）----

cd "$REPO" || { echo "仓库路径不可进入: $REPO"; exit 2; }

# run 名由占位 JobID 与 step 号派生：同一占位 job 里多次 srun 各自唯一、可回查。
RUN_NAME="gl-${SLURM_JOB_ID}-s${SLURM_STEP_ID:-0}"
LOG="$LOG_DIR/${RUN_NAME}.log"
mkdir -p "$LOG_DIR"

cleanup() {
  local rc=$?
  # 只清理本运行器自己起的东西（附属 server、临时目录、端口占用等），按项目补充；禁止波及他人进程与目录。
  echo "EXIT_CODE=$rc" >> "$LOG"
}
trap cleanup EXIT
trap 'exit 143' TERM
trap 'exit 130' INT

# 日志三件套：PYTHONUNBUFFERED=1 防管道块缓冲吞输出；set -o pipefail（上方 set -euo pipefail 已开）防主命令崩了
# $? 被 tee 的 0 顶替；tee 落文件供 Monitor tail；结束由 cleanup 写 EXIT_CODE= 作统一完成信号。
echo "RUN_NAME=$RUN_NAME JOB=$SLURM_JOB_ID STEP=${SLURM_STEP_ID:-0} HOST=$(hostname) GPU=$GPU_NAMES 起始=$(date -Is)" | tee -a "$LOG"
echo "CMD=$*" | tee -a "$LOG"
PYTHONUNBUFFERED=1 "$@" 2>&1 | tee -a "$LOG"
