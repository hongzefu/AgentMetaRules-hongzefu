#!/usr/bin/env bash
# 日志监听过滤管道模板（挂在一个流上、有关心的行就发事件）。
# 对应 AGENTS.md 第 7 条与 CLAUDE.md「Monitor 工具」。
#
# 用法：
#   bash templates/monitor_filter.sh <日志路径> [扩展正则]
# 默认过滤词表（并集口径）：全部完成|done|EXIT_CODE=|Error|Traceback|out of memory|CUDA|找不到
# 存在「静默空转」缺陷的作业，把缺陷特征行也加进第二个参数，不能只盯 EXIT_CODE=。
#
# 为什么每一级都要行缓冲（2026-08-24 MotionJEPA 仓库两次实测踩中）：
#   中间夹的 tr / awk / sed 对管道输出默认 4KB 块缓冲——日志持续增长时事件被后续输出推出来、看似正常，
#   任务一结束，最后几行（RESULT / EXIT_CODE / PASS）就永远卡在缓冲区里，监听端静默、不唤醒。
#   修法：tr 写成 `stdbuf -oL tr`、awk 加 fflush()、sed 加 -u，只给 grep --line-buffered 不够。
# 一份日志挂一个 Monitor；禁止一条 tail -F 同时挂多个日志文件（多文件 tail 每次切换都打 `==> 文件 <==` 头部行，
# 实测噪声大到触发 Monitor 限流）。禁止在 Monitor 里塞 `while ...; do sleep N; done; echo 完成` 这种最后才输出一次的脚本。
# 进程存活检测禁止裸 `pgrep -f "<pattern>"`（pattern 在 Monitor 自身 argv 里 → 永远自匹配恒真），
# 用 `tmux has-session -t '=名'`、启动时 $! 记下的 PID，或括号技巧 `pgrep -f "[e]ntry.py"`。
set -euo pipefail

LOG="${1:?必须指定日志路径}"
PATTERN="${2:-全部完成|done|EXIT_CODE=|Error|Traceback|out of memory|CUDA|找不到}"

exec tail -n +1 -F "$LOG" \
  | stdbuf -oL tr '\r' '\n' \
  | grep --line-buffered -E "$PATTERN"
