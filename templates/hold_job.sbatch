#!/usr/bin/env bash
# GreatLakes 48 h 占位 job 骨架（通用模板）。对应 greatlakes.md「资源约束」「算力使用规则」与 AGENTS.md 第 8 条。
#
# 用途：任务确定要上 GL 时，开工第一步（改代码之前）就提交本 job 占卡，让排队与改代码并行；
# 拿到资源后，一切工作负载都经 srun 塞进本 job 里跑（运行器骨架见 templates/run_in_hold.sh）：
#   srun --jobid=<占位 JobID> --overlap --exact --ntasks=1 --cpus-per-task=<n> --gpu_cmode=shared \
#     bash templates/run_in_hold.sh <脚本与参数>
# 等价的一行式提交：sbatch <同下方 #SBATCH 参数> --wrap='sleep infinity'
#
# 使用前把尖括号占位符全部替换（#SBATCH 行不做 shell 展开，只能写字面值；多开时 <k> 取 1、2、3…）。
# 规格：
#   - 默认 --cpus-per-task=1 --mem=24G：压低规格保证快速排队；资源不够报错（OOM / CPU 争抢导致的失败）
#     再重新提交更大的，不预先放大。
#   - ManiSkill 多 worker CPU 生成变体：--cpus-per-task=<worker 数> --mem=<worker 数 × 12>G
#     （每 worker 1 CPU + 12 G；例：16 worker → --cpus-per-task=16 --mem=192G）。
#   - 一次默认最多 4 个占位 job；超过 4 个或超出默认规格，按 greatlakes.md「放行制度」处理。
# 提交后：立刻把 JobID 追加到本任务的清单文件，收尾释放只读这个清单：
#   jid=$(sbatch --parsable templates/hold_job.sbatch) && echo "$jid" >> <日志目录>/hold-jobs-<任务名>.txt
# 收尾（全部工作结束、commit 完成后）：只按清单逐个取消；禁止 scancel -u、禁止按名字模式批量取消：
#   while read -r jid; do scancel "$jid"; done < <日志目录>/hold-jobs-<任务名>.txt
# 注：spgpu 强制至少 1 GPU（--gpus-per-node=0 报 QOSMinGRES，2026-06-17 实证），纯 CPU 工作负载也要占 1 GPU。
# 注：不要加 --qos=interactive（chaijy2/spgpu 实测报 Invalid qos specification），用默认 qos。
# 注：--gpu_cmode=shared 让塞进来的多个进程共用同一张卡；默认 exclusive 模式下同卡第二个 CUDA / Vulkan 上下文起不来。
#
#SBATCH --job-name=<任务>-hold-<k>
#SBATCH --account=<GL_ACCOUNT>
#SBATCH --partition=<GL_PARTITION>
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --gres=gpu:1
#SBATCH --gpu_cmode=shared
#SBATCH --cpus-per-task=1
#SBATCH --mem=24G
#SBATCH --time=48:00:00
#SBATCH --output=<GL_REPO>/<STORE_ROOT>/logs/%x-%j.log
set -euo pipefail

# 占位 job 本身不跑任何工作负载：只留一行就位记录供日志回查，然后睡到被 scancel 或 48 h 到期。
echo "占位 job 已就位: JOB_ID=${SLURM_JOB_ID:-未知} 节点=$(hostname) 起始=$(date -Is)"
exec sleep infinity
