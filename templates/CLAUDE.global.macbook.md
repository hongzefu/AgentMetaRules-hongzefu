# 全局指令(本机器所有项目通用)

本文件是本机器的全局 CLAUDE.md,适用于该机器上的**所有项目和会话**。其中的规则优先级高于默认行为,必须严格遵守。

## 语言:始终使用简体中文

- **在任何时候、任何项目中,都使用简体中文与用户沟通,无一例外。**
- 不仅最终回答用中文,**过程中的所有说明也一律用中文**,包括:
  - 调用工具前后的解释说明
  - 进度更新、状态汇报
  - 计划(plan)、todo、阶段性总结
  - 报错解释、原因分析、结论
- 即使用户用英文提问,默认仍用中文回复;只有当用户**明确要求**改用其他语言时才切换。
- 代码、命令、文件名、API 名称、标识符、报错原文等**保持原样**(通常为英文),不翻译;但围绕它们的解释用中文。
- 提交信息(commit message)、PR 标题/正文、代码注释等是否用中文,**遵循该项目已有的惯例**;若项目无明确惯例,可询问用户。

## 运行环境

- 本机为 MacBook(macOS / zsh),单机环境,无集群、无 GPU 服务器访问;不要 ssh 试探集群、不调用集群相关 skill。
- 以下规则整理自 [AgentMetaRules-hongzefu](https://github.com/hongzefu/AgentMetaRules-hongzefu)(`AGENTS.md` 第 3、7 条与 `CLAUDE.md`「Monitor 工具」),只保留本机适用的 uv / tmux / Monitor 三块。

## uv 管理 Python(强制)

- 执行任何 Python 命令前先确认 `command -v uv`。uv 可用时:脚本一律 `uv run ...`,测试 `uv run python -m pytest ...`,建环境 `uv venv`;**绝不回退到裸 `python` / `python3` / `pip` / `python -m venv`**。
- 依赖变更必须落地到 `pyproject.toml`:用 `uv add <pkg>` / `uv remove <pkg>`,或手改 `pyproject.toml` 后 `uv lock` + `uv sync`。**禁止**用 `uv pip install` 或 `pip install` 装正式依赖(不回写声明,环境不可复现)。
- 唯一例外:用后即弃的临时环境(一次性诊断、复现沙盒、临时工具),可用 `uv pip install` 或 `uv run --no-project --with <pkg> ...`,不改项目依赖;不得把它当长期环境用。
- 子目录/子工具依赖与主项目冲突时,在该目录另建独立 `pyproject.toml`,各自 `uv lock` / `uv sync`(venv 名可用 `UV_PROJECT_ENVIRONMENT=<目录名>` 指定);**不要用 uv workspace 收编冲突子项目**(共享同一份 `uv.lock`,隔离失效)。
- `pyproject.toml` 与 `uv.lock` 必须纳入 git;`.venv` 照常 gitignore。解释器版本用 `uv python pin` / `requires-python` 钉死,不依赖系统 python。

## 长任务放 detached tmux(强制)

- 预计超过 5 分钟的训练、评估、数据处理、诊断等,必须放进 detached tmux session,脱离 agent 会话(会话退出会连带杀死子进程)。若 `tmux` 未安装,先提示用户 `brew install tmux`,不擅自改用 nohup。
- 标准模板(日志三件套:`PYTHONUNBUFFERED=1`、`set -o pipefail`、`tee` 落日志,结束写 `EXIT_CODE=` 尾行;不要用 `> log 2>&1` 纯重定向):

  ```bash
  tmux new-session -d -s <前缀-唯一会话名> \
    "set -o pipefail; PYTHONUNBUFFERED=1 <长任务命令> 2>&1 | tee <日志绝对路径>; echo \"EXIT_CODE=\$?\" >> <日志绝对路径>"
  ```

- 多变量/复杂长命令先写成脚本文件,再 `tmux new-session -d -s <名> "bash <脚本>"`(`export A=1 bash x.sh` 会把 bash 当成 export 参数)。
- 配套命令:死活判断 `tmux has-session -t '=完整会话名'`(`=` 为精确匹配);中途停止 `tmux kill-session -t '=完整会话名'`(强杀不写 `EXIT_CODE=`,不能当成功);结束后必须核对日志里的 `EXIT_CODE=`。
- **禁止裸 `pgrep -f "<pattern>"` 判断存活**(会匹配到自己,恒真);确需时用括号技巧 `pgrep -f "[t]rain.py"`,或用启动时 `$!` 记下的 PID。
- **tmux 清理红线(最高优先级)**:任何情况下禁止 `tmux kill-server`、`tmux kill-session -a`、`pkill -f tmux`、`killall tmux` 及指定 `-L`/`-S` 的变体——tmux server 是全用户共享的,会连带杀掉用户自己的会话,不可恢复。
  - 唯一允许的清理:`tmux kill-session -t '=确切会话名'`,一次一个,禁止通配、前缀匹配、`xargs` 批量。
  - 自己起的会话必须带可辨识前缀(如 `cc-`、`ev-`),并在当轮回复里列出本轮起过的会话名清单;清理只以该清单为依据,清单外的会话一律不动。
  - 删前删后各跑一次 `tmux ls` 核对,差集不等于目标会话时立即停止并把原文交给用户;有任何疑问先问用户。

## Monitor 工具(强制)

1. **等待任何后台进程必须挂 Monitor**(服务启动、测试、评估、构建、日志变化等);禁止写 `sleep` 忙轮询。唯一例外:单次、确定小于 3 秒的固定等待。
2. ≤5 分钟的短任务用 `run_in_background` 启动,其退出时 harness 会自动唤醒,**不必再挂轮询去等**;需要看中途输出时再挂 Monitor。
3. **tmux 里起的任务 harness 感知不到退出,Monitor 是唯一完成信号,必须挂。**
4. Monitor 的 command 必须「挂在一个流上、有关心的行就发事件」,禁止 `while ...; do sleep N; done; echo 完成` 这类最后才输出一次的脚本。标准写法(管道每一级都必须行缓冲:`tr` 用 `stdbuf -oL tr`、awk 加 `fflush()`、sed 加 `-u`,只给 `grep --line-buffered` 不够,否则结尾的 `EXIT_CODE=` 会卡在缓冲区永不上报):

   ```bash
   tail -n +1 -F <日志绝对路径> | stdbuf -oL tr '\r' '\n' \
     | grep --line-buffered -E "全部完成|done|EXIT_CODE=|Error|Traceback|out of memory|找不到"
   ```

5. **一份日志挂一个 Monitor**;禁止一条 `tail -F` 同时跟多个文件(`==> 文件 <==` 头部行噪声会触发限流)。
6. Monitor 里同样禁止裸 `pgrep -f`(pattern 就在 Monitor 自己的 argv 里,永远自匹配);存活判断用 `tmux has-session -t '=名'`、`$!` PID 或括号技巧。
7. 对可能「进程活着却永不产出」的任务,过滤词里还要加上其缺陷特征字符串,不能只盯 `EXIT_CODE=`。
8. Monitor 不可用时如实说明,改用宿主支持的等待/通知机制,不声称已挂载。
