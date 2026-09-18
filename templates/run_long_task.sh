#!/usr/bin/env bash
# 长任务启动模板：detached tmux + 日志三件套 + EXIT_CODE= 尾行。
# 对应 AGENTS.md 第 7 条。预计超过 5 分钟的训练 / 抽取 / 评估 / 建库 / 诊断一律用它起。
#
# 用法：
#   bash templates/run_long_task.sh <会话名> <日志绝对路径> '<长任务命令（单引号包住）>'
# 例：
#   bash templates/run_long_task.sh wan-extract-0918 /path/to/store/logs/wan-extract-0918.log \
#     'uv run python scripts/extract.py --out /path/to/store/out'
#
# 约束：
#   - 会话名必须带可辨识前缀（如 ev- / p3- / wan-），并在当轮回复或留档 launch.md 里记下清单。
#   - 多变量长命令先写成脚本文件再传进来（`export A=1 B=2 bash x.sh` 会把 bash 当成 export 参数）。
#   - 日志落点遵守 <STORE_ROOT> 存储边界；不要用 `> log 2>&1` 纯重定向（后台面板会永远 "No output yet"）。
#
# 配套命令（`=` 前缀是 tmux 的精确匹配；不带 `=` 的 -t 做前缀匹配，`-t ev` 会命中所有 ev 开头的会话）：
#   tmux has-session -t '=<会话名>'      # 死活判断：运行中为真、结束后为假
#   tmux kill-session -t '=<会话名>'     # 中途停止：连 tee 一并退出、零孤儿；⚠ 强杀不写 EXIT_CODE= 尾行
#   tmux attach -t '<会话名>'            # 人肉围观，Ctrl-b d 脱开
#   tmux ls                              # 一览所有在跑任务
# 红线：任何情况下禁止 `tmux kill-server` / `kill-session -a` / `pkill -f tmux` / `killall tmux`。
set -euo pipefail

SESSION="${1:?必须指定 tmux 会话名（带可辨识前缀）}"
LOG="${2:?必须指定日志绝对路径}"
CMD="${3:?必须指定长任务命令（用单引号包住整条命令）}"

case "$LOG" in
  /*) ;;
  *) echo "日志路径必须是绝对路径: $LOG" >&2; exit 2 ;;
esac
mkdir -p "$(dirname "$LOG")"

if tmux has-session -t "=$SESSION" 2>/dev/null; then
  echo "会话已存在，拒绝覆盖: $SESSION（先核对它是不是本轮起的，再决定是否换名）" >&2
  exit 3
fi

# 三件套：PYTHONUNBUFFERED=1 防管道块缓冲吞输出；set -o pipefail 防主命令崩了 $? 被 tee 的 0 顶替；
# tee 落文件供后续 tail；结束写 EXIT_CODE= 作统一完成信号。
tmux new-session -d -s "$SESSION" \
  "set -o pipefail; PYTHONUNBUFFERED=1 $CMD 2>&1 | tee '$LOG'; echo \"EXIT_CODE=\$?\" >> '$LOG'"

echo "已启动 tmux 会话: $SESSION"
echo "日志: $LOG"
echo "死活判断: tmux has-session -t '=$SESSION'"
echo "监听模板: bash templates/monitor_filter.sh '$LOG'"
