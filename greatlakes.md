# greatlakes Slurm 提交规约（通用正本）

<!-- AGENTMETARULES:BEGIN common-greatlakes -->

当端到端验证、数据生成或训练需要 GPU、本地 GPU 资源不足时，可以 ssh 到 UMich greatlakes 集群，
通过 **48 h 占位 job** 拿到席位后把工作负载塞进去跑。**以后所有 greatlakes 提交都必须遵守本文件；违反任何
"硬规则"前必须先与用户确认，不可静默放宽。** 本文件是通用正本：账户 / 分区 / 认证 / 路径 /
venv / 提交流程 / 占位 job 与运行器骨架 / PENDING 读法 / 算力使用规则都在这里；各项目的实测表、现成脚本清单
与放行记录留在各项目仓库（不收进本文件的内容见 [`docs/excluded.md`](https://github.com/hongzefu/AgentMetaRules-hongzefu/blob/main/docs/excluded.md)）。
占位符：`<GL_REPO>`（集群侧可见的仓库绝对路径）、`<GL_SUBMIT>`（提交器路径，默认本仓库
[`scripts/gl_submit.py`](https://github.com/hongzefu/AgentMetaRules-hongzefu/blob/main/scripts/gl_submit.py)）、`<STORE_ROOT>`（仓库内产物根）、`<SSH_HOST>`
（`~/.ssh/config` 别名，默认 `greatlakes`）。无集群访问的环境本文件只作只读存档，见 `AGENTS.md` 第 8 条。

## 登录认证（硬规则，不可静默放宽）

**优先复用 ControlMaster 主连接:认证一次，30d 内所有 ssh 操作（提交/查询）免认证、免手机；
没有 master 才需建立（仅这一次走 Okta 2FA）。** ssh 二次验证已从 Duo 迁移到 **Okta Verify**。
**仅在"建立主连接"那一次需要验证；此时必须先问用户用哪种方式（6 位 TOTP 码 / 留空触发
push + 数字匹配，强烈推荐 TOTP），不要默认或复用上次选择。** 先 `ssh -O check greatlakes`
判断 master 是否存活：存活就直接干活、不必问验证方式。详见下方「ssh 提交流程（ControlMaster
复用，Okta Verify）」。

## 资源约束（硬规则，不可静默放宽）

- `--account=chaijy2`：不能切换到任何其他 account（即便看到别的 account 可绕过排队也不行）；
- `--partition=spgpu`：不能用其他 partition（如 standard / gpu / largemem）；唯一长期例外是「HF 上传校验 job」走 `standard`（见同名一节）；
- `--nodes=1` + `--ntasks-per-node=1`：永远只提单 node 单 task；
- **一切工作负载一律经占位 job 运行，不把工作负载直接 `sbatch`**（用户 2026-09-25、2026-09-26 定；唯一例外是「HF 上传校验 job」直接 `sbatch` 跑完即退）：先
  `sbatch --gres=gpu:1 --time=48:00:00 --wrap='sleep infinity'` 拿席位，再用
  `srun --jobid=<hold> --overlap --exact --ntasks=1 --cpus-per-task=<n> --gpu_cmode=shared <脚本>` 塞进去跑；
  长训练同样在占位 job 内跑，预计超过 48 h 的训练靠 checkpoint 续到下一个占位 job，续跑前先问用户。
- **占位 job 规格默认压到最低：`--cpus-per-task=1 --mem=24G`**，保证快速排队；唯一例外是 ManiSkill 多 worker
  CPU 生成，按每 worker 1 CPU + 12 G 定席位（细则见「算力使用规则」第 4 条）。资源不够报错（OOM / CPU 争抢）
  再重新提交更大的，不预先放大。
- **`--time` 一律 `48:00:00`**，不按预计耗时缩短；跑完按清单 `scancel`（「算力使用规则」第 8、10 条）。
- 不指定 `--qos`：**实测 `--qos=interactive` 在 chaijy2/spgpu 下报 `Invalid qos specification`，不要再用**；
  遇到 `(AssocGrpMemLimit)` 时先降 `--mem`，正确的 qos 名待用 `sacctmgr show assoc user=hongzefu format=qos`
  （或 `sacctmgr show qos`）查清；`(AssocGrpGRES)` 表示 chaijy2 账户 GPU 配额已被组内
  其他用户占满，此时只能等他们的 job 退出，不可换 account / partition 绕开。

**账户配额口径**（`sacctmgr` 的 GrpTRES，全组共用，skill `greatlakes-usage` 动态读取不写死）：
`GPU 20 | MEM 960 G | CPU 80`。GPU 与内存都会卡提交：GPU 满 → `PENDING (AssocGrpGRES)`，
内存满 → `PENDING (AssocGrpMemLimit)`，CPU 满 → `PENDING (AssocGrpCpuLimit)`；要申请的 GPU、mem、CPU **都**得 ≤ 对应余量才提交得动。
chaijy2 自己的 GPU 配额上限固定为 20，与 spgpu 分区物理 A40 总量 240 张（30 节点 × 8）是两回事。

**放行制度**：超出「1 GPU × 48 h 占位、默认 1 CPU / 24 G 规格、一次最多 4 个」的申请——单 job 多 GPU、单 job 超默认规格、
一次超过 4 个占位 job——由用户逐次放行（超规格先提交再提醒、超数量先审核；逐 job 列出规格、用途），
放行记录写在**项目仓库**的 `greatlakes.md` 或对应留档里，不写进本正本。同批多个 job 的调度方式（串行链 / 并行 / 节点排除清单）
同样是放行内容之一，变更调度方式而不扩包络时也要记一笔。

## 路径可见性（硬规则，不可静默放宽）

greatlakes 计算节点唯一能看到的共享路径是 `/nfs/turbo/coe-chaijy-unreplicated/hongzefu/`。
本机 `sled-vail` 的其它路径在 slurm 节点上全部不可见，写进脚本会立刻
`No such file or directory`：

- `/home/...`（本机 home，包括 `~/...`）—— 注意 greatlakes 有自己的 `/home/hongzefu`，
  与本机 home 是**两个不同的目录**，内容不互通；
- `/data/...`（本机 data 盘）；
- `/tmp/...`、`/var/tmp/...`（计算节点的 `/tmp` 是节点自己的，跟本机无关）；
- 任何不以 `/nfs/turbo/coe-chaijy-unreplicated/hongzefu/` 开头的本机绝对路径；
- 相对路径（slurm job 的 cwd 不是本机当前目录；脚本内先 `cd` 到 NFS 绝对路径再用相对路径可以）。

所有 slurm 脚本里出现的路径——`data.data_root`、checkpoint / `runs_root` 目录、
`--output` 日志、yaml / config、norm_stats、wandb dir、`cd` 的工作目录、python
解释器路径——都必须落在 `/nfs/turbo/coe-chaijy-unreplicated/hongzefu/` 下，并写成绝对路径。

如果要用的数据 / 产物当前还在本机非共享路径，提交 slurm 前必须先 rsync 到
`/nfs/turbo/coe-chaijy-unreplicated/hongzefu/` 下；不要尝试 mount / symlink / 把本机
路径硬塞给 sbatch。

另：计算节点能连 HF Hub（启动时读模型 config 走 `huggingface.co`，实测 200 OK）。

## venv 可移植性（硬规则：解释器必须由 uv 安装在 NFS 上）

uv 默认把 managed Python 装在本机 home（`/home/hongzefu/.local/share/uv/python/`），
`.venv/bin/python` symlink 过去，在 greatlakes 计算节点上是**死链**。**禁止用手动
重链 / 改 pyvenv.cfg 的方式修补**；正规做法是把 uv 的解释器安装目录放到 NFS：

```bash
# 1. 解释器装到 NFS（已装好 3.11.14，重装其它版本时同样带这个环境变量）
UV_PYTHON_INSTALL_DIR=/nfs/turbo/coe-chaijy-unreplicated/hongzefu/uv-python \
    uv python install 3.11.14

# 2. 重建 venv 时显式指定 NFS 解释器的绝对路径（防止 uv 抓回本机 home 的解释器）
uv venv --python /nfs/turbo/coe-chaijy-unreplicated/hongzefu/uv-python/cpython-3.11.14-linux-x86_64-gnu/bin/python3.11
UV_LINK_MODE=copy uv sync    # cache 在本机盘、venv 在 NFS，跨设备必须 copy
```

这样 `pyvenv.cfg` 的 `home` 与 `bin/python` symlink 天然落在 NFS，本机与 greatlakes
双端可用，无任何手术。验证命令：
`.venv/bin/python -c "import torch; print(torch.__version__)"`。

集群侧一律 `.venv/bin/python` 直调或 `uv run --frozen --no-sync`（不做 `uv sync`——集群侧 uv 装在
greatlakes 自己的 `/home`，而 `.venv/bin/python` 是指向 NFS `uv-python` 的 symlink，双端可用且不联网 sync）；
`UV_CACHE_DIR` 显式压回本机 `$HOME/.cache/uv`，不让 `XDG_CACHE_HOME` 把它拖到 NFS（`AGENTS.md` 第 3 条）。

## ssh 提交流程（ControlMaster 复用，Okta Verify）

greatlakes 登录节点（`greatlakes.arc-ts.umich.edu`）拒绝纯密码 ssh，需要
`keyboard-interactive`（密码 + **Okta Verify** 2FA，已从旧 Duo 迁移）。**核心策略:没有
master 就建立 master——认证一次，30d 内所有提交/查询免认证、免手机。**

`~/.ssh/config` 已为 `greatlakes` 配好 `ControlMaster auto` + `ControlPersist 30d`
（`ControlPath ~/.ssh/cm-%r@%h:%p`）。OpenSSH 复用原理:主连接认证一次后建立 control
socket，之后 `ssh greatlakes <cmd>` 直接复用已认证通道、**不再发起任何 SSH 认证握手**，
因此零密码零 MFA 零手机（slave 不认证，与服务器 MFA 策略无关）。

提交器:**`<GL_SUBMIT>`**（默认本仓库 `scripts/gl_submit.py`；自包含，纯系统 ssh + ControlMaster,
不再用 paramiko）——逻辑就是"没 master 就建 master，再经系统 ssh 复用提交":

- **master 存活** → 直接提交，**无需任何凭据、不必问验证方式**；
- **master 不存活** → 用 `GLPW`(+`GLOTP`) 经 `pexpect` 驱动系统 ssh 建立主连接，再提交。

无参数默认只打印 squeue 队列状态；提交训练请传一条远程命令当参数
（如 `"squeue -u hongzefu"`）——会自动前置 `cd $GL_REPO &&`（远程 cwd 是 home，相对路径
否则找不到脚本；`GL_REPO` 由环境变量传入）。

**密码安全（硬规则）:绝不把密码写入任何文件、commit、CLAUDE.md 或对话历史。凭据由
用户即时提供，仅经临时环境变量 `GLPW`（建 master 时必需）/ `GLOTP`（可选 6 位 TOTP，推荐）
传入，用完立即 unset、绝不持久化。**

### 标准流程

1. **先查 master**（纯本地 socket 检查，不出网、不需凭据、不需 sandbox）:
   ```bash
   ssh -O check greatlakes   # exit 0 = 存活可复用;非 0(255) = 需先建
   ```
2. **存活 → 直接提交/查询**（零认证零手机，不必问验证方式）:
   ```bash
   export GL_REPO=<GL_REPO>
   uv run --no-project --with pexpect python <GL_SUBMIT> "squeue -u hongzefu"
   uv run --no-project --with pexpect python <GL_SUBMIT>   # 无参数=只打印队列
   ```
3. **不存活 → 建主连接**（**仅此步需要验证方式**，推荐 TOTP、给一次码无需手机匹配）。
   gl_submit 在无 master 时会自动用凭据建连后再提交;也可设好凭据直接跑:
   ```bash
   export GLPW='<密码>' GLOTP='<当前6位码>'
   uv run --no-project --with pexpect python <GL_SUBMIT> "<命令>"
   unset GLPW GLOTP
   ```
   建好后 30 天内所有提交/查询走第 2 步、免认证；到期后重建。（skill `greatlakes-usage`
   的 `gl_connect.py` 也能单独建 master，与此共用同一个 socket。）

凡走系统 ssh 出网的步骤（建主连接、master 复用查询/提交）都**必须**用 Bash 工具的
`dangerouslyDisableSandbox: true`；`ssh -O check` 是纯本地不需要。timeout：复用查询很快（~60000ms 够）；
建 master 用 push 方式要等手机，设 ~180000ms 以上（TOTP 则很快）。

### Okta 两条路 —— 仅"建主连接"那一次需要，且每次先问用户用哪种，不默认 / 复用上次

建 master 时 keyboard-interactive 的 prompt 依次是 `Password:` 和
`Okta passcode (leave blank to initiate a push):`:

1. **6 位 TOTP 码（强烈推荐，最可靠、无推送时序风险）**:从 Okta Verify app 读当前 6 位码
   填 `GLOTP`。码每 30s 刷新且一次性，**拿到立刻发起**。
2. **留空触发 push + number challenge（不推荐，除非按「push 修法」处理）**:不设 GLOTP，
   SSH 端依次显示 `Successfully initiated Okta push` → `The correct answer is N`（用户在手机
   Okta Verify 选中 N）→ `Press enter to continue:`（**approve 后还要再按一次回车，模块才校验**）。
   **2026-06-19 摸清真根因:以前判定的"转达数字超时、错过 ~60s 窗口"不准确——真正原因是
   `gl_submit.py` / `gl_connect.py` / `gl_master.py` 的 pexpect 模式表里没有 `Press enter to
   continue` 这一条,发完空 passcode 就一直 `expect()` 干等到 TIMEOUT，根本没按那下回车，于是
   "看起来卡死/超时"。** 用未打补丁的驱动走 push 必挂;要么用 TOTP，要么按下方「push 修法」用增强
   驱动。**能用 TOTP 就用 TOTP（无回车握手、无数字转达）。**

pexpect 建连要点（见 gl_submit.py / skill 的 `gl_master.py`）:匹配 `Password:` 填 GLPW、
`Okta passcode` 填 GLOTP（空则触发 push）、首次 host key 提示自动答 `yes`，认证通过的标志是
远端回显 `CONNECTED_OK_MARKER`。本机无 expect/sshpass，故用 `uv run --with pexpect` 临时
拉 pexpect 驱动系统 ssh，无需 sudo 装包。**注意:skill 里的 `gl_master.py` 只覆盖 TOTP 路径——模式表里
没有 push 的 `Press enter to continue`，故走 push 会卡死（见上）。push 必须用下方增强驱动；本仓库
`scripts/gl_submit.py` 已实现增强驱动的三条（sentinel 握手需设 `GL_PUSH_SENTINEL`）。**

#### push 修法（2026-06-19 实测一次过；仅当用户坚持用 push 时才需要）

若必须走 push，用一个增强版 pexpect 驱动（一次性脚本即可，密码仍只经 `GLPW` 不落盘），相对
现成驱动多做三件事:

1. **补两条 pexpect 模式**:`correct answer is (\d+)`（捕获数字 N，实时打印/落盘）+
   `Press enter to continue`（匹配到就 `sendline("")` 按回车，模块这才去校验 approval）。缺第二条
   就是"卡死"的全部原因。
2. **服务器输出实时落盘 + 把日志路径直接给用户**:`child.logfile_read = <每写即 flush 的文件>`
   （只记服务器→本地，不含密码），并把该日志绝对路径丢给用户自己 `tail -f` 看 N——别靠转述，
   转述既慢又易漏（数字行常是单字符、易被过滤器吃掉）。
3. **回车用 sentinel 文件握手**:驱动在 `Press enter to continue` 处阻塞轮询一个 sentinel
   文件（如 `/tmp/gl_push_go`），用户在手机点完 N、回话确认后再 `touch` 该文件放行、然后才按
   回车——**避免 approve 之前就按回车导致单次校验失败**。

完成后 `ssh -O check greatlakes` 应为 `Master running`，主连接建好，后续提交/查询零认证。
**结论不变:push 全程要"看数字→点→确认→放行回车"四步握手，TOTP 一步到位，优先 TOTP。**

### 已知坑

- **远程命令 cwd 是 greatlakes 的 `/home/hongzefu`，不是 REPO**:gl_submit 已对自定义命令
  自动前置 `cd $GL_REPO &&`，直接传 `"squeue -u hongzefu"`；提交新 slurm 脚本前须先按本文件审批资源
  即可，**不要再自己写 cd**（会变成双 cd，虽无害但多余）。squeue 的 `-o '...'` 单引号在外层
  参数里是字面、远程 bash 才解析。
- **spgpu 强制至少 1 GPU**:提交 `--gpus-per-node=0` 报 `QOSMinGRES` / `Batch job
  submission failed`（2026-06-17 实证）。纯 CPU 的 sleep 测试 job 也必须带 `--gpus-per-node=1`。
- **本机 `sled-vail` 与集群解释器不共享**：`micromamba` / `conda` 在计算节点都没有；sbatch 里凡是
  `command -v micromamba` 为真即说明跑错了机器（见下方骨架的 fail-fast 判定）。

## job array、依赖链与节点排除（通用技巧）

- **job array 实测可用**：chaijy2/spgpu 接受 `--array`（job 57854615，2 task 独立调度到 gl1526/gl1514），
  MaxArraySize=5000——array task 逐个独立调度，等价于「N 个分开请求的 1-GPU 小 job」，一次提交零手抄。
  全量分片实测（array 57856154，8 × 1 GPU）：7 个 task 即时调度、第 8 个因 GPU 配额排队迟起 5.6h 后照常完成
  （「分开请求 + 断点续传」的递补语义实证）。分片中断续跑：清掉该分片的 claim 文件后
  `sbatch --array=<分片号> --export=ALL,<必要变量>` 重提。
- **每片独立输出目录**、断点续传、claim 防撞车是分片抽取的三要素（`AGENTS.md` 第 23 条）。
- **依赖链**：`--dependency=afterok:<arrayJobId>` 串接 finalize（前置全成功才起）；
  `--dependency=afterany:<jobid>` 让多个 job 严格串行执行（避免同节点共驻 / 互相预热污染性能判据）。
  集群紧张时的策略：先全部提交排队，若出现同节点干扰再重新提交。
- **节点排除**：`--exclude=gl1514,gl1501,gl1508,gl1512,gl1519` 排除碰过热缓存的节点以保 cold-like 口径。
- **抽取期间多 task 读写同一 turbo 卷（~132 MB/s 天花板）**，勿并行跑集群训练。
- **任何需要第二个 CUDA context 的情形都要 `--gpu_cmode=shared`**——不只是同卡多进程（server + client 共驻），
  **单进程里 torch + Vulkan/图形互操作也算**（SAPIEN / ManiSkill 的 svulkan2 建 Vulkan logical device 时为
  CUDA-Vulkan 互操作单独开一个 context）。`sbatch --help` 明写 `--gpu_cmode=<shared|exclusive|prohibited>`
  **默认 `exclusive`**；`Exclusive_Process` 下整卡只允许一个 context，torch 先拿到、Vulkan 被拒，报错固定是
  `[svulkan2] CUDA device 0 is in EXCLUSIVE or EXCLUSIVE_PROCESS mode` +
  `vk::PhysicalDevice::createDeviceUnique: ErrorInitializationFailed`。占位 job 里起步骤时 `srun` 同样要带：
  `srun --jobid=<hold> --overlap --exact --ntasks=1 --cpus-per-task=4 --gpu_cmode=shared <脚本>`。
  （2026-09-22 robomme_benchmark_MotionJEPANewTask 实测：不带该参数 `VULKAN_FAILS=1`，带上 `MODE=Default`、生成正常。）
  排查这类问题**先读命令自带帮助再下"无解"结论**；已排除且不必重走的方向：换 `--gres`/去 `--exact`、换分区、
  `nvidia-smi -c 0`（`Insufficient Permissions`）、残留进程、驱动/重启、MPS（集群未配且 Vulkan 不走 MPS）。
  **不得用 `SAPIEN_DISABLE_RAY_TRACING=1` 绕开**——它换渲染路径，产物不再逐位可比。

## 调试 slurm 脚本（同样塞进占位 job 跑）

如需临时调试脚本，使用 `run_slurm_debug5min.sh` 这类独立名称，并遵守以下要点：

- 独立 `run_name`（绝不复用生产 run_name —— `overwrite=true` 一类覆盖参数会清空 `runs/<run_name>/`）；
- 关闭 wandb、只跑 1 个 epoch / 少量步；
- 只写项目覆盖白名单允许的键，不写与默认配置相同的字面量（项目若有覆盖项守卫测试会双重判违规）；
- 不 `source` 任何 home 下的 rc 文件，python 用 NFS 绝对路径；
- 脚本内局部变量一律全大写命名（小写 `key=value` 会被覆盖项正则误当成 Hydra 覆盖）；
- run 目录 fail-loud 守卫写在运行器脚本里（训练入口对已存在目录常是 `makedirs(exist_ok=True)` 静默复用）。

调试也不单独 `sbatch` 工作负载：先按下方骨架起占位 job，再把运行器塞进去。两个模板：占位 job
[`templates/hold_job.sbatch`](https://github.com/hongzefu/AgentMetaRules-hongzefu/blob/main/templates/hold_job.sbatch) 与运行器 [`templates/run_in_hold.sh`](https://github.com/hongzefu/AgentMetaRules-hongzefu/blob/main/templates/run_in_hold.sh)
（含计算节点判定 fail-fast 与 `exec` 交棒）。

占位 job 骨架（默认规格）：

```
#SBATCH --account=chaijy2
#SBATCH --partition=spgpu
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --gres=gpu:1
#SBATCH --gpu_cmode=shared
#SBATCH --cpus-per-task=1
#SBATCH --mem=24G
#SBATCH --time=48:00:00
#SBATCH --job-name=<任务>-hold-<k>
# 注：不要加 --qos=interactive（chaijy2/spgpu 报 Invalid qos specification），用默认 qos
#SBATCH --output=<GL_REPO>/<STORE_ROOT>/logs/%x-%j.log
sleep infinity
```

提交后立刻把 JobID 追加到 `<日志目录>/hold-jobs-<任务名>.txt`。塞入运行：
`srun --jobid=<hold> --overlap --exact --ntasks=1 --cpus-per-task=<n> --gpu_cmode=shared bash <运行器> <脚本与参数>`。

运行器骨架：`set -euo pipefail` → `unset` 上一轮诊断遗留的兼容开关 → 计算节点判定
（`hostname` 前缀 `gl*`、共享路径存在、本机路径不存在、无 micromamba/conda、GPU 型号 `NVIDIA A40`，
任一不符 `exit 2`）→ `cd <GL_REPO>` → 日志三件套 + `trap cleanup EXIT` → 运行 `"$@"` 并写 `EXIT_CODE=` 尾行。
run 名由 `SLURM_JOB_ID` 与任务名派生，天然唯一、可回查；Slurm 的终止信号经 `srun` 直达带清理 trap 的运行器，
而不是打到 wrapper 上留孤儿。

## PENDING 状态读法

- `(Priority)` → 正常排队等调度，等就行。⚠ **配额没满不代表马上能起跑**：slurm 判能否分配
  看的是**单节点**的空闲 GPU / 空闲 CPU / 可分配内存（= `MEMORY − ALLOCMEM`，不是 `FREE_MEM`）
  三者同时够。2026-08-14 实测：chaijy2 尚余 18 GPU / 768G / 72 CPU，但 spgpu 全 30 个节点里
  同时有 ≥2 张空闲 A40 的只有 3 个（gl1515：3 CPU/137G、gl1527：27 CPU/**13.6G**、
  gl1528：5 CPU/47.3G），一个 2GPU+8CPU+48G 的 job 在每个节点都差一维，只能干等。
  查碎片：`sinfo -p spgpu -N -O 'NodeHost:12,CPUsState:16,AllocMem:10,Memory:10,GresUsed:16'`；
- `(Priority)` 但急着跑 → 在**不动训练配方**的前提下降 `--cpus-per-task` / `--mem`：
  已验证的降配实例是 MotionJEPA v7 双卡 bf16 的 **4 CPU / 16G**（2026-08-14 v2 冒烟实测：排队 <1 分钟、
  epoch 零退化、cgroup anon 峰值仅 3.85 GiB）。旧推断「MaxRSS 47.7G ⇒ 48G 是贴边值、降 mem 会 OOM」
  已被实测证伪——MaxRSS 只是页缓存填满申请上限的读数。长训（多 epoch）档位未单独实测，降配前先向用户确认；
- `(AssocGrpMemLimit)` → chaijy2 总 mem 配额满了，先降 `--mem`（`--qos=interactive` 实测无效，别用）；
- `(AssocGrpGRES)` → chaijy2 总 GPU 配额满了，只能等组内其他用户的 job 退出，不可换 account；
- `(Resources)` → spgpu 全集群节点都被占，等就行（与 chaijy2 自己的 20-GPU 配额无关，看全局占用板块）。

**页缓存 vs 真实内存的判读方法**（2026-08-14 两代冒烟实测得出，适用于所有读大数据集的 job）：
集群 `JobAcctGatherType=jobacct_gather/cgroup`（已查 `scontrol show config`），cgroup 记账含 file 页，
但干净页缓存触顶时被内核回收、不触发 OOM kill。因此 **MaxRSS 精确贴住 `--mem` 申请上限不能当
「真实需要这么多内存」的证据**（47.71/48、15.77/16 两代都贴边），真实不可回收工作集看 cgroup 拆分的
anon（+shmem）峰值（实测 3.85 GiB），file 页缓存永远填满剩余配额且可回收、零 OOM。降配时以 anon 峰值定档，
首个新档位长 run 结束以采样峰值复核。

## 分区授权与占位 job（2026-09-22 补）

- **分区只用用户授权的那个**（当前所有项目：`spgpu`）。排查问题时也不要往 `gpu` / `gpu-rtx6000` / `gpu_mig40` / `viz` 提探针 job——
  用户已明令禁止；且 compute mode 这类全局设置换分区无效。`viz`/`viz-long` 对 chaijy2 直接 `Access/permission denied`。
- **占位 job 模式**：`sbatch --gres=gpu:1 --cpus-per-task=1 --mem=24G --time=48:00:00 --wrap='sleep infinity'`（默认规格；
  ManiSkill 多 worker 席位按「算力使用规则」第 4 条）拿到资源后反复
  `srun --jobid=<hold> --overlap --exact --ntasks=1 --cpus-per-task=<n> --gpu_cmode=shared <脚本>` 进去跑；
  每个 job 一条 tmux，每份日志一个 Monitor（续挂用 `tail -n 0`）。chaijy2 的 CPU 配额 80，多 worker 席位会撞 `AssocGrpCpuLimit`。
- **本机 sled-vail 与 aspen 都能直读集群 NFS**（`/nfs/turbo/coe-chaijy-unreplicated/...`）：产物落 NFS、比较在本机跑、不搬数据；
  但 NFS 上逐帧读大文件很慢（144 局全字段比较 10～15 min、合并 40 GB 约 25 min），多条比较链并行只是分摊等待。
- **删测试目录前先抠小文件**：`run.log`、`run_config.json`（hostname/GPU/驱动指纹）、`results/*.json`、`jobs/`、`logs/`、
  合并 metadata 归到仓库再 `rm -rf`。2026-09-22 两条线的这些文件随大目录一起删了，只拦下一份。

## HF 上传校验 job（2026-10-03 定，硬规则）

用户原话（2026-10-03）：「上传HUGingFace的文件需要校验。但是校验不要在本机进行你可以生成一个在greatlake上的纯CPUJ0B来实现。以后都要这么做写进AgentMetarule」；同日 AskUserQuestion 选定「standard 分区」「直接 sbatch 跑完即退」。

- **适用范围**：凡上传到 HF（model / dataset repo 或 Storage Bucket）的文件，上传后的读回校验一律放在 greatlakes 纯 CPU job 里做，**不在本机**（sled-vail、aspen 等工作机）下载或重算。只限这类校验，不外延到其他 CPU 工作负载。
- **提交规格**：
  `sbatch --account=chaijy2 --partition=standard --nodes=1 --ntasks-per-node=1 --cpus-per-task=4 --mem=8G --time=12:00:00 --job-name=<任务>-hfverify --output=<NFS 日志目录>/%x_%j.out <校验脚本>`
  - 不带 GPU，不带 `--gpu_cmode`；
  - 这是「只用 `spgpu`」与「一律经占位 job」两条规则的唯一长期例外；
  - 规格超过默认值时，按「算力使用规则」第 7 条先提交、再提醒用户；
  - 正常结束自行释放；超时或失败时，按清单 `scancel` 自己的 JobID（第 10 条），不 `scancel -u`。
- **校验做法**：
  - job 内逐个对象流式读回（HTTP 分块读取，边下边算 sha256，不落盘，节点 `/tmp` 也不留文件），与上传时随附的 `SHA256SUMS` 逐行比对；
  - 同时核对对象数、逐对象字节数，以及清单外是否多出对象；
  - 末行写判定行 `HF_VERIFY=PASS|FAIL objects=<n> sha_match=<n> size_equal=<n> missing=<n> extra=<n>`，日志落 NFS，结束追加 `EXIT_CODE=`；
  - 正式校验前，先用同一脚本只校验 1 个小对象做冒烟。
- **清单来源**：`SHA256SUMS` 里的 sha 优先取生成或搬运时已经记录并核对过的值（例如节点上逐局算过、暂存时复核过的 sha），不为了生成清单在本机重读大文件；只有没有记录的小文件才在本机计算。
- **凭据**：
  - 私有对象的 HF token 只经环境变量进入 job：提交端环境里已有 `HF_TOKEN` 时用 `--export=ALL`。不写进脚本、日志、命令行参数或 GL 上的任何文件（第 15 条）。
  - GL 侧没有可用的 token 来源时，先问用户，不自行在 GL 落 token 文件。
  - 公开对象匿名读取。
- **网络**：计算节点出网走 HTTP 代理（GL 实测）。冒烟不通时记录原始报错并交用户，不改在本机校验。
- **无集群访问的环境**：按 `AGENTS.md` 第 8 条无集群分支，在本机校验，并在汇报里写明原因。

## aspen（sled 组自有机器，2026-09-22 打通）

- `ssh -i ~/.ssh/id_ed25519_umich hongzefu@sled-aspen.eecs.umich.edu`——**必须显式 `-i`**（公钥文件名非默认，不带会被拒
  `Permission denied (publickey,password)`）；校园网/VPN 内直连，校外走 `-J <uniqname>@login.itd.umich.edu`。
- 2× RTX A6000 48 GB（Ampere GA102）、compute_mode `Default`、驱动 570.195.03（CUDA 12.8）、16 核 / 251 GB、无 Slurm、`/data` 14 T。
- NFS 已挂载；**NFS 克隆的 `.venv` 直接可用**（python 3.11.14 / torch 2.9.1+cu128，torch 走 NFS 导入约 32 s），零环境搭建。
- tmux 在 aspen 上起，`CUDA_VISIBLE_DEVICES=0` 锁单卡；48 局单 worker 生成约 41 min。
- **aspen 是 robomme 原版发布集的"同机器"**：对发布集 47/48 局逐位复现（含四路图像）；需要与原版逐位对拍的验证优先排 aspen，
  sled-vail 次之（1e-16 舍入），A40 只能做容差校验。

### aspen 常态化使用（用户 2026-09-22 定：常驻算力，GPU 无他人占用时优先用）

- **定位**：aspen 是常驻机器，无 Slurm、不排队，与 sled-vail、greatlakes 共用同一份 `/nfs/turbo/coe-chaijy-unreplicated`。
  **以后凡是能落在 NFS turbo 上的 compute，若 aspen 的 GPU 没被其他用户占用，优先放 aspen**，其次 greatlakes 占位 job，再次本机。
- **登录**：`~/.ssh/config` 已加别名，直接 `ssh sled-aspen`（等价于 `ssh -i ~/.ssh/id_ed25519_umich hongzefu@sled-aspen.eecs.umich.edu`）。
- **开工前查占用**（两张卡各自看，别人在用就不抢）：
  ```bash
  ssh sled-aspen 'nvidia-smi --query-gpu=index,name,memory.used,utilization.gpu --format=csv,noheader; nvidia-smi --query-compute-apps=pid,used_memory --format=csv,noheader; who'
  ```
  判读：`memory.used` 只有几百 MiB 且无 compute app → 空闲可用；有他人进程 → 换另一张卡或改走集群。
- **起任务模板**（tmux 在 aspen 上起，NFS 克隆的 venv 直接用，锁单卡，日志落 NFS 供本机 Monitor 直读）：
  ```bash
  ssh sled-aspen "tmux new-session -d -s <任务名> \"set -o pipefail; cd /nfs/turbo/coe-chaijy-unreplicated/hongzefu/<GL_REPO 对应的 NFS 克隆>; CUDA_VISIBLE_DEVICES=<0或1> PYTHONUNBUFFERED=1 .venv/bin/python <脚本与参数> 2>&1 | tee <NFS 日志路径>; echo \\\"EXIT_CODE=\\\$?\\\" >> <NFS 日志路径>\""
  ```
  完成信号仍靠本机 Monitor `tail -F` 那份 NFS 日志；死活判断 `ssh sled-aspen 'tmux has-session -t <任务名>'`。
- **纪律**：只测/只跑用户授权的 worker 数（当前：单 worker）；不要动别人的进程；`/data/hongzefu` 可作本地盘，大产物仍优先落 NFS 便于本机直读。

## 算力使用规则（用户 2026-09-22 定、2026-09-25 与 2026-09-26 补，硬规则）

用户原话（2026-09-22）：「greatlakes除了长训练job 尽可能都使用1gpu占用48小时 然后在全部结束后关闭 尽可能压低为1cpu24mem
除了maniskill多worker情形 如果报错不够 再重新提交 每次提交占位job默认尽可能用满4个超过4个都要用户审核数量
如果1个job要超过1cpu24mem 先提交然后提醒用户 记得任务结束commit后要释放资源！ 尽可能优先先用aspen
如果仓库都在data hongzefu上 那就不做并行 问用户」
（2026-09-25）：「不要用sbatch 而是用占用job的形式 占用48小时的形式」「把以后都用占用48小时 跑完scancel 并且生成多worker需要这样大cpu/mem」
（2026-09-26）：「greatlakes都采用占用job的形式 而不是现在这样 在修改代码之前 启动工作的时候 尽可能早的占卡 如果是maniskill多worker cpu生成的
我记得这几个仓库有实测验证 其他情况下压低cpu mem保证快速排队 每次job都直接48小时 工作完成后kill 这样可以让排队和修改代码并行」

1. **优先级：aspen 优先。** 能落在 NFS turbo 上的 compute，先看 aspen 的 GPU 有没有被其他用户占用（见「aspen 常态化使用」的查占用命令），空闲就用 aspen；aspen 不可用再上 greatlakes。aspen 优先只适用于**整个任务都放得下 aspen** 的情形（第 11 条）。
2. **greatlakes 一律占位 job，不把工作负载直接 `sbatch`**：`1 GPU`、`--time=48:00:00`、`--wrap='sleep infinity'`，工作负载全部用 `srun --jobid=<hold> --overlap --exact --ntasks=1 --cpus-per-task=<n> --gpu_cmode=shared` 塞进去跑；长训练也在占位 job 内跑，超过 48 h 的靠 checkpoint 续到下一个占位 job，续前问用户。原因：spgpu 全局常年 228/240 满卡、数百 GPU 在排队，直接 sbatch 的工作 job 起跑时间不可控；占位 job 一旦拿到席位，后续无论跑几轮都不用重新排队，跑完按 JobID `scancel` 释放。
3. **开工先占卡（2026-09-26 定）**：任务一旦确定要上 greatlakes，**开工第一步、在读代码或改代码之前就提交占位 job**，让排队与修改代码并行；`sbatch` 后立刻把 JobID 追加到清单文件 `<日志目录>/hold-jobs-<任务名>.txt`（第 10 条的清单）；改代码期间用 skill `greatlakes-usage` 或 `squeue --me` 看席位是否到手，到手后再塞任务。提交前先用 skill 看哪个节点同时有空 GPU + 足够空 CPU + 空内存，否则会 `PENDING (Resources)`（2026-09-25 实测：查询到提交之间 gl1510 的那张空卡就被别的组拿走，第二个席位只能排队）。
4. **规格默认压到最低：`--cpus-per-task=1 --mem=24G`**，保证快速排队。**唯一例外是 ManiSkill 多 worker CPU 生成**（2026-09-25 本机实测定）：瓶颈在 CPU 不在 GPU——单 worker 峰值内存 9 G（PatternLock 最重）、显存不到 2 G、锁 1 核只比不限核慢 1.4 倍，因此**每 worker 配 1 CPU + 12 G**，一张 A40 带 16 个 worker 毫无压力；参考席位 `--cpus-per-task=16 --mem=192G`（已批准并实提），两个这样的席位（2 GPU / 32 CPU / 384 G）共 32 个 worker，折合约 22 个 RTX 6000 Ada worker，比本机 8 worker 快约 2.5 倍；塞入时每席 `--draw-workers 16 --workers 16`，并必须设 `OMP_NUM_THREADS=1 MKL_NUM_THREADS=1`（不限线程时单 worker 会瞬时吃到 13.8 核，多 worker 同机互相踩）。其他情况一律压低 CPU / 内存；资源不够报错（OOM / CPU 争抢导致的失败）再重新提交更大的，不预先放大；跑之前先在本机用进程树采样器量一次单 worker 的 RSS / CPU / 显存峰值再定 `--mem`，不要按训练 job 的 MaxRSS 贴边法估。
5. **时长一律 48 小时**：每个占位 job 直接 `--time=48:00:00`，不按预计耗时缩短。
6. **一次默认提交最多 4 个占位 job**，尽可能用满 4 个；**超过 4 个必须先让用户审核数量**。大 CPU / 内存席位同样计入。
7. **单个 job 若需要超过 1 CPU / 24 GB：先提交，再提醒用户**（不阻塞，但必须提醒并说明原因）。
8. **工作完成后 kill**：任务结束、commit 完成后必须释放资源——按第 10 条的清单逐个 `scancel <jobid>` 全部占位 job，并在收尾汇报里写明已释放；`git status -sb` 干净不等于收尾完成。
9. **仓库若都在本机 `/data/hongzefu`（不在 NFS turbo 上），不做跨机并行——先问用户**怎么处理（同步到 NFS 还是只在本机跑）。

10. **绝不取消不是本会话提交的 job（硬规则，2026-09-22 事故后立的）。**
   - **禁止 `scancel -u $USER`，禁止按名字模式批量取消。** 取消只能按**本会话自己记录的具体 JobID** 逐个 `scancel <jobid>`。
   - 本会话每次 `sbatch` 后必须把 JobID 追加到清单文件（`<日志目录>/hold-jobs-<任务名>.txt`），收尾释放只读这个清单。
   - 用户说"占位 job 都取消"时，只取消清单内的；同账户下清单外的 job（别的会话/别的任务在用）**列出来问用户，不动**。
   - 事故记录：2026-09-22 14:24，我用 `scancel -u hongzefu` 一把清空，连带杀掉了另一会话的 `ev2048-hold-1～4`
     （61721503～06，各 1 GPU / 1 CPU / 24 GB / 48 h，12:24 起跑，另一个 eval 任务的占位 job）。
     "都取消"指的是**我的**占位 job；同账户 ≠ 同会话。取消 job 是不可逆、影响他人工作的动作，拿不准就问，不要顺手一把清。

11. **同一任务不得异构拆分（用户 2026-09-22 定）。** 需要大量并行时整批提交 greatlakes；**不得一半 greatlakes 一半 aspen**，
   不允许同一任务跨机器混跑——不同 GPU 架构的产物不可逐位比、时序不同重规划也不同，混在一批里既没法当同一份数据用，
   也没法对拍。aspen 优先只适用于**整个任务都放得下 aspen** 的情形；放不下就整批上集群。

标准提交（占位 job，默认规格；完整模板见 [`templates/hold_job.sbatch`](https://github.com/hongzefu/AgentMetaRules-hongzefu/blob/main/templates/hold_job.sbatch)）：
```bash
sbatch --account=chaijy2 --partition=spgpu --nodes=1 --ntasks-per-node=1 --gres=gpu:1 --gpu_cmode=shared \
       --cpus-per-task=1 --mem=24G --time=48:00:00 \
       --job-name=<任务>-hold-<k> --output=<日志目录>/%x-%j.log --wrap='sleep infinity'
```
ManiSkill 多 worker 席位（第 4 条；提交后按第 7 条提醒用户）：
```bash
sbatch --account=chaijy2 --partition=spgpu --nodes=1 --ntasks-per-node=1 --gres=gpu:1 --gpu_cmode=shared \
       --cpus-per-task=16 --mem=192G --time=48:00:00 \
       --job-name=<任务>-hold-<k> --output=<日志目录>/%x_%j.out --wrap='sleep infinity'
```
进去跑：`srun --jobid=<hold> --overlap --exact --ntasks=1 --cpus-per-task=<n> --gpu_cmode=shared bash <运行器> <脚本与参数>`（运行器模板见 [`templates/run_in_hold.sh`](https://github.com/hongzefu/AgentMetaRules-hongzefu/blob/main/templates/run_in_hold.sh)）。

<!-- AGENTMETARULES:END common-greatlakes -->
