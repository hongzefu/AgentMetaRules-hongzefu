# CLAUDE.global.md — 每台机器全局 `CLAUDE.md` 的通用块（正本 4）

本文件是各机器全局 `CLAUDE.md`（`$CLAUDE_CONFIG_DIR/CLAUDE.md`，默认 `~/.claude/CLAUDE.md`）里 `common-global` 标记块的正本。全局文件对本机**所有目录、所有会话**生效，包括没有接入正本的目录（例如直接在工作盘根目录开的会话），所以这里只放一份**自包含的摘录**：语言（第 1 条）、子代理派发政策（`AGENTS.md` 第 26 条与 `CLAUDE.md`「Workflow 与 Agent 模型」）、uv（第 3 条）、detached tmux（第 7 条）、Monitor（`CLAUDE.md`「Monitor 工具」）、git 提交纪律（第 11 条）。不 `@` 导入正本——双份注入每会话多占约 30k token（见 README「维护规则」）。

- **优先级**：接入正本的仓库里以仓库内 `AGENTS.md` / `CLAUDE.md` 标记块为准（更完整），本块只是兜底，两者冲突按仓库内规则执行。
- **维护**：改第 1、3、7、11、26 条或 `CLAUDE.md` Agent／Monitor 节时，**同一正本 commit 里同步改本文件**，不得只改一处；回流机制见 `AGENTS.md` 第 25 条「全局配置也是回流目标」（目标名 `global-claude`，每次开工核对同步时一并 `check`／`apply`）。
- **机器专属**内容（路径、集群有无、凭据、配置目录、正本 clone 位置）写在全局文件的标记外，骨架见 [`templates/CLAUDE.global.md`](templates/CLAUDE.global.md)，MacBook 用 [`templates/CLAUDE.global.macbook.md`](templates/CLAUDE.global.macbook.md)。

<!-- AGENTMETARULES:BEGIN common-global -->
## 通用规则（AgentMetaRules 正本摘录，勿手改）

本节由 [AgentMetaRules-hongzefu](https://github.com/hongzefu/AgentMetaRules-hongzefu) 的 `CLAUDE.global.md` 经 `scripts/sync_rules.py` 回流，是 `AGENTS.md` 第 1、3、7、11、26 条与 `CLAUDE.md`「Workflow 与 Agent 模型」「Monitor 工具」的自包含摘录。**当前目录或其上级已有带 `AGENTMETARULES` 标记块的 `CLAUDE.md` / `AGENTS.md` 时，以仓库内规则为准**（更完整，含第 0 条环境判定、第 2 条计划与开工令、第 27 条交接等），本节只约束未接入正本的目录，并在两者一致处重申。

### 语言：始终使用简体中文

- 在任何时候、任何项目中，都使用简体中文与用户沟通，无一例外：最终回答、过程说明、进度汇报、计划、报错解释、结论全部用中文；即使用户用英文提问也用中文回复，只有用户明确要求才切换。
- 代码、命令、文件名、API 名、标识符、报错原文保持原样不翻译；围绕它们的解释用中文。commit message、PR、注释是否用中文遵循该项目既有惯例。
- 子代理、Workflow、fork 会话、后台任务的产出最终落到用户眼前的叙述也必须是中文；允许英文工作的内部产出须在开头标注「[内部产出，英文]」并提醒消费方仍用中文汇报。
- 对用户报告时刻一律换算成美国东部时间并写明「美东」，不报 UTC；日志里的原始时间戳原样引用。

### 子代理派发政策（强制；`AGENTS.md` 第 26 条与 `CLAUDE.md` Agent 节摘录）

- **默认多代理，本节即委派许可**：凡任务能拆出独立的探索、规划、修改、运行、验证或审查子任务，尽量并发派子代理完成；主代理定总计划，自己只做下一步立即依赖其结果的阻塞步骤，依赖步骤顺序执行。不为凑并发制造重复任务，不扩大用户本轮授权。
- **模型按职责显式选择，每次派发都写 `model`，不继承主代理**（这是用户制定的角色政策，不是官方分工）：

  | 职责 | Claude Code `model` | 要点 |
  |---|---|---|
  | 探索、检索、定位、读日志、读信息 | `haiku` | 只读；主代理按需大量并发，无需预列或逐项审批；覆盖不全按目录／关键词／日志分片再派小模型，不升档到 Sonnet／Opus；「没找到」须主代理核实或再派分片复核 |
  | 规划、写代码、改文件、解冲突 | `opus` | 写入型一律 `isolation: "worktree"`；Plan 代理也用 `opus` |
  | 运行型（启动长任务、提交 job） | `opus` | 不加 worktree，在有环境与产物的主检出启动；只启动、验证起跑、交回句柄；不得改代码、配置、脚本、依赖或参数，不得自行派修复代理 |
  | 审查、对抗验证、文档与代码评审 | `sonnet` | 只读；钉死 BASE／TIP sha；同一 finding 只派一个审查者，不并行复制、不靠多数票 |
  | 画图（内联 SVG、SVG／PNG） | `fable` | 第 2 条 2026-10-12 用户指定的唯一 Fable 例外；交付前主会话必须渲染成位图目视复查重叠／对齐／溢出／图例 |

  - 除画图外**不派 `fable`／Astra 或白名单外模型**；子代理及递归子代理档位不得高于本次用户主请求。大角色不降档给 Haiku，探索不升档。
  - 职责档位与可用模型、宿主限制冲突，或模型不可用时，**停止该项派发并报告原始原因**，不静默换档，不以继承模型绕过显式选择。`fork` 类型永远跟父模型，不能用来规避本表。
  - Claude 子代理不规定推理强度（Codex 子代理最低 `high` 的要求不适用于 Claude）。
- **生命周期：同一决策点按批并发派出、一次性交回**：独立任务在同一条消息里发出全部 Agent 调用；一份结果交回即结束，下一决策点按需新派一批，不搭长期代理网络。`SendMessage` 只用于续接被中断、只差一步或审查失败需续改的同一代理。串行依赖不并行。数量按宿主容量（`CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS` 与 `CLAUDE_CODE_WORKFLOW_MAX_CONCURRENT_AGENTS` 均设 64），满额报 `Concurrent subagent limit reached` 时等已派批次返回，不忙重试；多开只缩短等待，用量仍计入主会话额度。
- **委派说明必须写清**：目标、上下文、工作树绝对路径与基线 sha、可读／可写文件、禁触路径、依赖、交付格式、验收命令与判定行。只读代理写明「只读，不改文件、不跑有副作用的命令」（只读提示不是权限沙箱）。同一文件单一 owner，告知「代码库里不只你一个在改：不碰集合外文件、不回滚他人改动」。有计划的任务按计划里的「子代理分配表」派，已授权范围内可调整职责、数量、依赖与整合顺序并说明原因；无分工时先形成明确委派再派，不把「可以自行拆分」当成可以扩权。
- **写入型子代理统一独立 worktree**：不得以写集不相交为由共用主检出写代码；派发前核对全局 `settings.json` 的 `worktree.baseRef` 为 `"head"`。子代理只在自己的 worktree 工作，commit subject 固定前缀 `sub/<子任务编号>: ` + 中文描述，全部原样保留；**子代理不 push、不合主分支、不 `--amend`／`reset --hard`**。主会话合并前审查（`sonnet`，钉死 `REVIEW_BASE`／`REVIEW_TIP`，输出 `PRE_MERGE_REVIEW=PASS|FAIL …`）→ `git merge --no-ff <TIP sha>` → 合并后审查（`POST_MERGE_REVIEW=PASS|FAIL …`）→ push → 清理 worktree。写入方与审查方不得是同一代理。
- **运行与修代码严格分工**：运行代理发现代码问题收集证据交主会话，主会话另派独立修复代理，修复经审查、验证、整合后再交确定版本续跑。主会话是唯一的资源、预算、监听、接续和清理负责人，登记全部 JobID／tmux 名；运行代理不得自行取消 job 或清理会话。
- **Workflow 逐次审批**：每次生成 workflow 前先把方案（做什么、分几个 phase、规模、用什么模型）交用户批准，获准后才调 Workflow 工具；`ultracode` 关键字、任务规模等一切其他开启条件作废。`agent()` 同样按上表选模型，脚本层不加并发限制、不人为拆批。
- **子代理超过 15 分钟**（完成通知 `duration_ms` > 900000）在当轮汇报里点名类型、描述、时长；统计由全局 `SubagentStop` hook 自动落盘。

### uv 管理 Python（强制）

- 执行任何 Python 命令前先确认 `command -v uv`。uv 可用时：脚本一律 `uv run ...`，测试 `uv run python -m pytest ...`，建环境 `uv venv`；**绝不回退到裸 `python` / `python3` / `pip` / `python -m venv`**。
- 依赖变更必须落地到 `pyproject.toml`：用 `uv add <pkg>` / `uv remove <pkg>`，或手改 `pyproject.toml` 后 `uv lock` + `uv sync`。**禁止**用 `uv pip install` 或 `pip install` 装正式依赖（不回写声明，环境不可复现）。
- 唯一例外：用后即弃的临时环境（一次性诊断、复现沙盒、临时工具），可用 `uv pip install` 或 `uv run --no-project --with <pkg> ...`，不改项目依赖；不得把它当长期环境用。
- 子目录／子工具依赖与主项目冲突时，在该目录另建独立 `pyproject.toml`，各自 `uv lock` / `uv sync`（venv 名可用 `UV_PROJECT_ENVIRONMENT=<目录名>` 指定）；**不要用 uv workspace 收编冲突子项目**（共享同一份 `uv.lock`，隔离失效）。
- `pyproject.toml` 与 `uv.lock` 必须纳入 git；`.venv` 照常 gitignore。解释器版本用 `uv python pin` / `requires-python` 钉死，不依赖系统 python。

### 长任务放 detached tmux（强制）

- 预计超过 5 分钟的训练、评估、数据处理、诊断等，必须放进 detached tmux session，脱离 agent 会话（会话退出会连带杀死子进程）。若 `tmux` 未安装，先提示用户安装，不擅自改用 nohup。
- 标准模板（日志三件套：`PYTHONUNBUFFERED=1`、`set -o pipefail`、`tee` 落日志，结束写 `EXIT_CODE=` 尾行；不要用 `> log 2>&1` 纯重定向）：

  ```bash
  tmux new-session -d -s <前缀-唯一会话名> \
    "set -o pipefail; PYTHONUNBUFFERED=1 <长任务命令> 2>&1 | tee <日志绝对路径>; echo \"EXIT_CODE=\$?\" >> <日志绝对路径>"
  ```

- 多变量／复杂长命令先写成脚本文件，再 `tmux new-session -d -s <名> "bash <脚本>"`（`export A=1 bash x.sh` 会把 bash 当成 export 参数）。
- 配套命令：死活判断 `tmux has-session -t '=完整会话名'`（`=` 为精确匹配）；中途停止 `tmux kill-session -t '=完整会话名'`（强杀不写 `EXIT_CODE=`，不能当成功）；结束后必须核对日志里的 `EXIT_CODE=`。
- **禁止裸 `pgrep -f "<pattern>"` 判断存活**（会匹配到自己，恒真）；确需时用括号技巧 `pgrep -f "[t]rain.py"`，或用启动时 `$!` 记下的 PID。
- **tmux 清理红线（最高优先级）**：任何情况下禁止 `tmux kill-server`、`tmux kill-session -a`、`pkill -f tmux`、`killall tmux` 及指定 `-L`/`-S` 的变体——tmux server 是全用户共享的，会连带杀掉用户自己的会话，不可恢复。
  - 唯一允许的清理：`tmux kill-session -t '=确切会话名'`，一次一个，禁止通配、前缀匹配、`xargs` 批量。
  - 自己起的会话必须带可辨识前缀（如 `cc-`、`ev-`），并在当轮回复里列出本轮起过的会话名清单；清理只以该清单为依据，清单外的会话一律不动。
  - 删前删后各跑一次 `tmux ls` 核对，差集不等于目标会话时立即停止并把原文交给用户；有任何疑问先问用户。

### Monitor 工具（强制）

1. **等待任何后台进程必须挂 Monitor**（服务启动、测试、评估、构建、日志变化等）；禁止写 `sleep` 忙轮询。唯一例外：单次、确定小于 3 秒的固定等待。
2. ≤5 分钟的短任务用 `run_in_background` 启动，其退出时 harness 会自动唤醒，**不必再挂轮询去等**；需要看中途输出时再挂 Monitor。
3. **tmux 里起的任务 harness 感知不到退出，Monitor 是唯一完成信号，必须挂。**
4. Monitor 的 command 必须「挂在一个流上、有关心的行就发事件」，禁止 `while ...; do sleep N; done; echo 完成` 这类最后才输出一次的脚本。标准写法（管道每一级都必须行缓冲：`tr` 用 `stdbuf -oL tr`、awk 加 `fflush()`、sed 加 `-u`，只给 `grep --line-buffered` 不够，否则结尾的 `EXIT_CODE=` 会卡在缓冲区永不上报）：

   ```bash
   tail -n +1 -F <日志绝对路径> | stdbuf -oL tr '\r' '\n' \
     | grep --line-buffered -E "全部完成|done|EXIT_CODE=|Error|Traceback|out of memory|找不到"
   ```

5. **一份日志挂一个 Monitor**；禁止一条 `tail -F` 同时跟多个文件（`==> 文件 <==` 头部行噪声会触发限流）。
6. Monitor 里同样禁止裸 `pgrep -f`（pattern 就在 Monitor 自己的 argv 里，永远自匹配）；存活判断用 `tmux has-session -t '=名'`、`$!` PID 或括号技巧。
7. 对可能「进程活着却永不产出」的任务，过滤词里还要加上其缺陷特征字符串，不能只盯 `EXIT_CODE=`。
8. Monitor 不可用时如实说明，改用宿主支持的等待／通知机制，不声称已挂载。

### git 提交纪律（`AGENTS.md` 第 11 条摘录）

- 每次改动完成并验证后必须 `git commit`；message 用简体中文，subject 沿用该仓库既有体例，body 至少写用户指令原话与验证结果（长改动按第 11 条六项详写）。
- **只 `git add <逐个明确路径>`**；禁止 `git add -A`、`git add .`、`git commit -a`。提交前 `git status --short` 核对工作区，用户或其他 agent 的在途改动一律绕开，不对其做提交、stash、checkout、clean、删除或回滚中的任何一种。
- commit 后立即裸 `git push`（已获用户长期授权）。例外先问用户：当前分支没有 upstream、仓库是第三方 fork、本机无凭据、项目声明不继承自动推送。**禁止 `git push --force` 与 `--force-with-lease`**；push 被拒即停、把 git 原文交用户，不改写历史、不反复重试。禁止 `git clean -x` / `git clean -X`。
<!-- AGENTMETARULES:END common-global -->
