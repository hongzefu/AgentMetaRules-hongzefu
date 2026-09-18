---
name: greatlakes-usage
description: 检查 UMich greatlakes 集群 chaijy2 账户的 GPU / 内存 / CPU 占用与配额余量，以及 spgpu 分区全局 A40 物理占用情况。当用户问到 greatlakes 账号占用、还剩多少 GPU、内存(mem)够不够、配额满没满、谁在用 GPU/内存、我的 job 在不在跑、spgpu 排队/PENDING 情况、A40 全局/整个分区占用情况时使用。需要 SSH（密码 + Okta Verify 2FA）。
---

# greatlakes 账号占用检查

查 chaijy2 账户在 greatlakes 上的 **GPU / 内存 / CPU** 配额余量、各用户占用、自己的 job 状态、spgpu 分区**全局** A40 物理占用（跨全部 account，非仅 chaijy2）。这是**全局 skill**（脚本在本机跑、通过 SSH 连 greatlakes，与具体项目无关）。完整提交规约见 AgentMetaRules-hongzefu 仓库根目录 `greatlakes.md`（通用正本；`~/.claude/greatlakes.md` 应为其副本）。

## 何时用

用户问类似：
- "检查 greatlakes 账号占用 / chaijy2 还剩多少 GPU / 内存够不够 / 配额满了没"
- "谁在用 GPU / 谁占了内存 / 组里资源占用情况"
- "我的 job 还在跑吗 / 在 greatlakes 上有几个 job"
- "spgpu 排队情况 / 为什么我的 job 一直 PENDING"
- "spgpu / A40 全局占用情况 / 整个集群 A40 还剩多少 / 哪个组占了最多 A40"（**注意**：chaijy2 自己的 GPU 配额上限固定为 20，与 spgpu 分区物理 A40 总量 240 张是两回事——即使 chaijy2 配额有余量，若 spgpu 全局 A40 被其他组占满，job 也会 `PENDING (Resources)`，此时才需要看全局占用板块）

## 怎么做

> **优先复用 ControlMaster 主连接：认证一次，30d 内免认证、免手机。** 本机 `~/.ssh/config` 已为 `greatlakes` 配好 `ControlMaster auto` + `ControlPersist 30d`（`ControlPath ~/.ssh/cm-%r@%h:%p`）。OpenSSH 连接复用原理：主连接认证一次（密码 + Okta MFA）后建立 control socket，之后任何 `ssh greatlakes <cmd>` 直接复用已认证通道、**不再发起任何 SSH 认证握手**，因此零密码、零 MFA、零手机——与服务器 MFA 策略无关（slave 根本不认证）。

**标准流程（三步）：**

1. **先查主连接是否存活**（纯本地 socket 检查，不出网、不需凭据、不需 sandbox）：
   ```bash
   ssh -O check greatlakes   # exit 0 = 存活可复用；非 0(255) = 需先建主连接
   ```
2. **存活 → 直接出报告**（零认证、零手机，**不必问验证方式**）。`check_usage.py` 启动自动检测 master 并走系统 ssh：
   ```bash
   uv run --no-project --with pexpect python ~/.claude/skills/greatlakes-usage/check_usage.py
   ```
3. **不存活 → 建主连接**（**仅此步需要验证方式**，推荐 TOTP，给一次 6 位码即可、无需手机数字匹配），再回第 2 步：
   ```bash
   export GLPW='<密码>'
   export GLOTP='<Okta Verify 当前 6 位码>'
   uv run --no-project --with pexpect python ~/.claude/skills/greatlakes-usage/gl_connect.py
   unset GLPW GLOTP
   ```
   建好后当天后续任意次查询都走第 2 步、免认证免手机，直到 30d 过期再重建。

**没 master 时 check_usage.py 会自动建 master（不再回退一次性认证）。** 若设了 `GLPW`(+`GLOTP`)直接跑 check_usage.py，它检测不到 master 会先用这对凭据建立主连接、再查——等价于"先 gl_connect.py 再 check_usage.py"一步到位:

```bash
export GLPW='<密码>' GLOTP='<当前 6 位码>'
uv run --no-project --with pexpect python ~/.claude/skills/greatlakes-usage/check_usage.py
unset GLPW GLOTP
```

无 `GLPW` 又无 master 时，check_usage.py 直接报错并提示去建主连接（不会卡住等手机）。

凡走系统 ssh 出网的步骤（建主连接、master 复用查询/提交）都**必须**用 Bash 工具的 `dangerouslyDisableSandbox: true`；`ssh -O check` 是纯本地不需要。timeout：复用查询很快（~60000ms 够）；建 master 用 push 方式要等手机，设 ~180000ms（TOTP 则很快）。

### 三条铁律

1. **先查 master，再决定要不要问验证方式**：`ssh -O check greatlakes` 存活就直接干、全程不碰凭据不碰手机；**只有需要新建主连接（master 失效）时才问用户验证方式**（推荐 TOTP，无需数字匹配），不默认、不复用上次。
2. **TOTP 码时效**：6 位码每 30s 刷新且一次性，用户给码后要立刻发起；push 模式则提前提醒"准备好手机做数字匹配"，SSH 端会显示要选的数字 N——**实测把数字转达给用户极易超时（错过匹配窗口认证就失败），能用 TOTP 就别用 push**。
3. **密码/验证码绝不落盘**：由用户在对话即时提供，只经临时环境变量 `GLPW`（及可选 `GLOTP`）传入，`gl_master.py` / `gl_connect.py` / `check_usage.py` 本体都不含密码，跑完同条命令立即 `unset`。绝不写入任何文件 / 脚本 / commit / 对话总结。（见 greatlakes.md「ssh 提交流程」）

## 输出怎么读

脚本输出六块：

- **配额行**：`GPU 20 | MEM 960 G | CPU 80`——chaijy2 账户**所有成员共用**的三项上限（动态从 `sacctmgr` 的 GrpTRES 读，不写死）。**GPU 和内存都会卡提交**：GPU 满 → `PENDING (AssocGrpGRES)`，内存满 → `PENDING (AssocGrpMemLimit)`。内存经常是隐形瓶颈——GPU 还有余量但 mem 配额满了照样提交不动。
- **占用/余量**：三项各给 `当前 RUNNING 占用 → 剩余`。要申请的 GPU **和** mem **都**得 ≤ 对应余量才提交得动。
- **按用户分解**：每个组员各占多少 `GPU / MEM(G) / CPU`，自己标 `<== 你`。
- **我的 job**：自己全部 job（JOBID/分区/名字/状态/已运行时长/walltime/节点/CPU/内存/GPU/节点或 PENDING 原因）。
- **spgpu 节点状态**：分区节点 mix/alloc/idle，每节点 8×a40。
- **spgpu 全局 A40 占用情况**（跨全部 account，非仅 chaijy2）：
  - `物理容量: 共 240 张 A40（30 节点）`（来自 `scontrol show node` 逐节点 `Gres=gpu:a40:8`，故障/维护中的 down/drain 节点会单独扣除并标注）
  - `已分配 / 空闲`：逐节点 `AllocTRES` 里的 `gres/gpu` 求和，与「已分配」互补
  - **单节点空闲 GPU 分布 + N 卡 job 可调度节点数**：多卡单节点 job（如 `--gres=gpu:4 -N1`）必须**单节点凑齐 N 张空闲卡**才能立即调度——总空闲 50 张但碎在 30 个节点上时，4 卡 job 照样要排队。脚本给出直方图（`5张空闲×1节点 3张空闲×9节点 …`）以及分别按 4 卡 / 8 卡的可容纳节点列表；每个候选节点还核对空闲 CPU/内存（按典型配比每 4 卡需 8 CPU / 64G），**GPU 空但 CPU/内存被占满的节点会标注"装不下"**——这是"明明有空闲卡却一直 PENDING (Resources)"的常见真相
  - **按 account 汇总 GPU 占用 Top 15**：谁（哪个 lab/账户）占了 spgpu 最多 A40；chaijy2 若掉出 Top 15 会在末尾单独补一行标注全局排名，保证自己账户始终可见
  - **全局 PENDING 竞争**：spgpu 队列里所有 account 排队 job 总数与所需 GPU 总数，并拆出"因 `Priority`/`Resources` 真在抢物理卡"的部分（`AssocGrp*` 类是各组自己配额满，不与你抢空闲卡）。新 job 的实际等待取决于：可调度节点数（上一条）+ 排在前面的真实竞争需求
  - 这块解释的是 `PENDING (Resources)`（spgpu 物理节点被别的组占满，与 chaijy2 自己的 20-GPU 配额无关，等其他组释放即可，不受 chaijy2 配额约束）

### PENDING 原因对照（与 greatlakes.md 一致）

| REASON | 含义 | 处理 |
|---|---|---|
| `(Priority)` | 正常排队等调度 | 等 |
| `(Resources)` | spgpu 节点全被占 | 等 |
| `(AssocGrpMemLimit)` | chaijy2 总内存配额（960G）满 | 降 `--mem` 或等组员退（`--qos=interactive` 在 chaijy2/spgpu 实测 Invalid，别用） |
| `(AssocGrpGRES)` | chaijy2 GPU 配额（20）已被组内占满 | **只能等组员 job 退出，绝不可换 account/partition** |

## 实现说明

- 登录用户 `hongzefu`，账户 `chaijy2`，主用分区 `spgpu`（a40）。这些写在 `~/.claude/skills/greatlakes-usage/check_usage.py` 顶部常量里。
- 占用用 `squeue -O tres-alloc` 取每个 job 的 total AllocTRES（GPU/内存/CPU 一次拿全，已跨节点汇总）；该字段不可用时自动回退 `%C/%m/%b`（内存按 per-node × 节点数估算，报告会标注"回退估算"）。
- 内存统一换算成 GB（兼容 G/M/T/K 后缀及无单位 MB）；配额三项均从 GrpTRES 动态读取，不硬编码（组里配额若调整自动跟上）。
- 全部远程命令只读：`squeue` / `sinfo` / `sacctmgr` / `scontrol show node`，不提交、不取消、不改任何 job。
- 全局 A40 占用：`scontrol show node -o` 逐节点解析 `Partitions=`（过滤 spgpu）/ `Gres=gpu:a40:N`（物理总量）/ `AllocTRES` 的 `gres/gpu`（已分配）/ `State`（含 DOWN/DRAIN 记为故障容量，不计入空闲）；单节点余量另取 `CPUTot-CPUAlloc` 与 `RealMemory-AllocMem`（MB）核对 N 卡 job 是否真装得下。账户排名用 `squeue -p spgpu -t RUNNING -O account,tres-alloc`（不带 `-A` 过滤，故覆盖全部 account），同样有 `%a|%b` 回退；全局 PENDING 竞争用 `squeue -p spgpu -t PENDING -o '%a|%b|%r'`，按 REASON 拆分真实抢卡需求。
- **主连接复用机制（没 master 就建 master）**：三个脚本共用同目录的 `gl_master.py`（`master_alive` / `ensure_master` / `build_master` / `run_remote`）。`check_usage.py` 启动调 `ensure_master()`：master 存活直接走 `ssh greatlakes '<cmd>'` 复用；不存活则用 `GLPW`(+`GLOTP`)经 `pexpect` 驱动系统 ssh 建立主连接（匹配 password / Okta passcode / host-key prompt，认证通过标志是远端回显 `CONNECTED_OK_MARKER`），建好后复用。`gl_connect.py` 是"只建连"的薄包装。依赖 `~/.ssh/config` 的 `ControlMaster auto` + `ControlPersist 30d`；环境变量 `GL_SSH_ALIAS` 可覆盖别名。AgentMetaRules-hongzefu 的 `scripts/gl_submit.py`（通用提交器）自包含同一套逻辑（不 import skill），提交 slurm job 也复用同一个 master socket。
