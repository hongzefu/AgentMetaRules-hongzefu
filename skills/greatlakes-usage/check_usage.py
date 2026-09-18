#!/usr/bin/env python
"""检查 greatlakes 集群 chaijy2 账户的 GPU / 内存 / CPU 占用与配额余量。

用法（密码只经环境变量传入，绝不写入文件 / commit / 历史）：

    # 方式 1：Okta Verify 6 位 TOTP 码（推荐，最可靠）
    export GLPW='<greatlakes 登录密码>'
    export GLOTP='<Okta Verify 当前 6 位码>'   # 30s 刷新且一次性，拿到立刻跑
    uv run --no-project --with pexpect python ~/.claude/skills/greatlakes-usage/check_usage.py
    unset GLPW GLOTP                 # 跑完立即清理

    # 方式 2：留空触发 push + 数字匹配（不设 GLOTP）
    export GLPW='<greatlakes 登录密码>'
    uv run --no-project --with pexpect python ~/.claude/skills/greatlakes-usage/check_usage.py
    unset GLPW

SSH 二次验证已从 Duo 迁移到 **Okta Verify**：设了 GLOTP 就用 TOTP 码认证；
不设 GLOTP 则留空触发手机 push，需在手机弹出的几个数字里选中 SSH 端显示的 N。
所有远程命令均为只读（squeue / sinfo / sacctmgr），不改动任何 job。
提交规约见 AgentMetaRules-hongzefu 仓库根目录 greatlakes.md。

GPU 和内存都是 chaijy2 账户级共享配额：GPU 满 -> PENDING (AssocGrpGRES)，
内存满 -> PENDING (AssocGrpMemLimit)，两者都会卡住 job 提交。
"""
import datetime
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gl_master  # noqa: E402  共享:检测/建立 ControlMaster 主连接 + 复用执行远程命令

USER = os.environ.get("GLUSER", "hongzefu")      # 登录用户，可用环境变量覆盖
ACCOUNT = os.environ.get("GL_ACCOUNT", "chaijy2")  # Slurm 账户，可用环境变量覆盖


def parse_tres(s: str) -> dict:
    """AllocTRES / GrpTRES（'=' 分隔）-> dict，如 cpu=10,mem=160G,gres/gpu=4。"""
    d = {}
    for kv in (s or "").split(","):
        kv = kv.strip()
        if "=" in kv:
            k, v = kv.split("=", 1)
            d[k.strip()] = v.strip()
    return d


def mem_to_gb(s: str) -> float:
    """'960G' / '163840M' / '1T' / 纯数字(MB) -> GB。"""
    s = (s or "").strip()
    m = re.match(r"([\d.]+)\s*([KMGTP]?)", s, re.I)
    if not m:
        return 0.0
    val = float(m.group(1))
    unit = m.group(2).upper()
    factor = {"K": 1 / (1024 * 1024), "M": 1 / 1024, "G": 1.0,
              "T": 1024.0, "P": 1024 * 1024, "": 1 / 1024}  # 无单位按 MB（SLURM 惯例）
    return val * factor.get(unit, 1.0)


def gpu_from_tres(d: dict) -> int:
    """从 AllocTRES dict 取 GPU 数（key 形如 gres/gpu 或 gres/gpu:a40）。"""
    for k, v in d.items():
        if k.startswith("gres/gpu"):
            return int(v) if str(v).isdigit() else 0
    return 0


def gpu_from_colon(b: str) -> int:
    """从 squeue %b（':' 分隔，如 gres/gpu:a40:1）取末段数字。"""
    m = re.search(r"gres/gpu\S*", b or "")
    if not m:
        return 0
    tail = m.group(0).split(":")[-1]
    return int(tail) if tail.isdigit() else 0


def parse_slurm_time(s: str) -> float:
    """SLURM 时间字符串（D-HH:MM:SS / HH:MM:SS / MM:SS）-> 分钟数。UNLIMITED 返回 inf。"""
    s = (s or "").strip()
    if not s or s.upper() in ("UNLIMITED", "INFINITE", "N/A", "INVALID"):
        return float("inf")
    days = 0
    if "-" in s:
        d_part, s = s.split("-", 1)
        try:
            days = int(d_part)
        except ValueError:
            pass
    parts = s.split(":")
    try:
        if len(parts) == 3:
            return days * 1440 + int(parts[0]) * 60 + int(parts[1]) + int(parts[2]) / 60
        elif len(parts) == 2:
            return days * 1440 + int(parts[0]) + int(parts[1]) / 60
        else:
            return days * 1440 + int(parts[0])
    except (ValueError, IndexError):
        return float("inf")


def fmt_mins(mins: float) -> str:
    """分钟数 -> 人可读字符串（1天2时3分）。"""
    if mins == float("inf") or mins < 0:
        return "未知"
    total = int(mins)
    d = total // 1440
    h = (total % 1440) // 60
    m = total % 60
    if d > 0:
        return f"{d}天{h}时{m}分"
    elif h > 0:
        return f"{h}时{m}分"
    else:
        return f"{m}分钟"


def main() -> None:
    now = datetime.datetime.now()

    # 没有 master 就建立 master（建好后 30d 免认证）;无凭据建不了则给出明确指引退出。
    try:
        existed = gl_master.ensure_master()
    except RuntimeError as e:
        sys.exit(f"ERROR: {e}")
    print(f">>> {'复用' if existed else '已建立'} {gl_master.ALIAS} "
          f"ControlMaster 主连接（免认证）\n", flush=True)

    def run(cmd: str) -> str:
        return gl_master.run_remote(cmd)

    # 1) 账户级配额（GrpTRES 设在 User 为空的 account 行）
    quota = {"gpu": None, "mem": None, "cpu": None}
    quota_raw = ""
    assoc = run(f"sacctmgr -n -P show assoc account={ACCOUNT} format=Account,User,GrpTRES")
    for line in assoc.splitlines():
        f = line.split("|")
        if len(f) >= 3 and f[1] == "" and ("gres/gpu=" in f[2] or "mem=" in f[2]):
            quota_raw = f[2]
            t = parse_tres(f[2])
            quota["gpu"] = gpu_from_tres(t)
            quota["mem"] = mem_to_gb(t.get("mem", ""))
            quota["cpu"] = int(t["cpu"]) if t.get("cpu", "").isdigit() else None

    # 2) 当前 RUNNING 占用：优先 tres-alloc（每 job total，已跨节点汇总）
    rows = []  # (user, gpu, mem_gb, cpu)
    out = run(f"squeue -A {ACCOUNT} -h -t RUNNING -O 'username:.18,tres-alloc:.150'")
    for line in out.splitlines():
        if not line.strip() or line.startswith("[stderr]"):
            continue
        parts = line.split(None, 1)
        if len(parts) < 2:
            continue
        t = parse_tres(parts[1])
        rows.append((parts[0], gpu_from_tres(t), mem_to_gb(t.get("mem", "")),
                     int(t["cpu"]) if t.get("cpu", "").isdigit() else 0))
    fallback = False
    if not rows:  # tres-alloc 字段不可用 -> 回退 %C/%m/%b（mem 按 per-node × 节点数）
        fallback = True
        out = run(f"squeue -A {ACCOUNT} -h -t RUNNING -o '%u|%D|%C|%m|%b'")
        for line in out.splitlines():
            if "|" not in line or line.startswith("[stderr]"):
                continue
            u, nd, c, m, b = (line.split("|") + ["", "", "", "", ""])[:5]
            nodes = int(nd) if nd.strip().isdigit() else 1
            rows.append((u, gpu_from_colon(b), mem_to_gb(m) * nodes,
                         int(c) if c.strip().isdigit() else 0))

    used = {"gpu": 0, "mem": 0.0, "cpu": 0}
    per_user: dict[str, dict] = {}
    for u, g, mgb, c in rows:
        used["gpu"] += g
        used["mem"] += mgb
        used["cpu"] += c
        a = per_user.setdefault(u, {"gpu": 0, "mem": 0.0, "cpu": 0})
        a["gpu"] += g
        a["mem"] += mgb
        a["cpu"] += c

    # 3) 其他用户 RUNNING job 详情（含时长）
    running_detail = run(
        f"squeue -A {ACCOUNT} -h -t RUNNING -o '%i|%u|%j|%M|%l|%C|%b'"
    )

    # 4) 我的 job（含 PENDING）
    myjobs = run(f"squeue -u {USER} "
                 "-o '%.18i %.10P %.22j %.8T %.10M %.10l %.4D %.5C %.8m %.14b %R'")

    # 5) 我的 PENDING job 资源需求（用于启动时间预测）
    my_pending_raw = run(f"squeue -u {USER} -t PENDING -h -o '%i|%j|%C|%b|%r'")

    # 6) 账户 PENDING 队列
    pending = run(f"squeue -A {ACCOUNT} -h -t PENDING -o '%i|%u|%j|%r'")

    # 7) spgpu 节点状态
    nodes_info = run("sinfo -p spgpu -o '%.10P %.5a %.11l %.5D %.7t %.16C %.24G'")

    # 8) spgpu 全局 A40 物理占用（跨全部 account，非仅 chaijy2）：逐节点 Gres/AllocTRES/State
    scontrol_nodes = run("scontrol show node -o")

    # 9) spgpu 全局各 account 的 GPU 占用（跨全部 account）
    global_acct_raw = run("squeue -p spgpu -h -t RUNNING -O 'account:.30,tres-alloc:.150'")

    # 10) spgpu 全局 PENDING 队列（跨全部 account，评估排队竞争）
    global_pending_raw = run("squeue -p spgpu -h -t PENDING -o '%a|%b|%r'")

    # ── 打印：配额与占用 ──────────────────────────────────────────────
    qg, qm, qc = quota["gpu"], quota["mem"], quota["cpu"]
    bar = "=" * 70
    print(bar)
    print(f"chaijy2 账户配额（所有成员共享）:  "
          f"GPU {qg if qg is not None else '?'}  |  "
          f"MEM {round(qm) if qm else '?'} G  |  "
          f"CPU {qc if qc is not None else '?'}    [{quota_raw}]")
    print(f"当前 RUNNING 占用:                "
          f"GPU {used['gpu']}  |  MEM {round(used['mem'])} G  |  CPU {used['cpu']}"
          + ("   (回退 per-node 估算)" if fallback else ""))
    if qg is not None:
        print(f"剩余:                            "
              f"GPU {qg - used['gpu']}  |  "
              f"MEM {round(qm - used['mem'])} G  |  "
              f"CPU {qc - used['cpu'] if qc is not None else '?'}")
    print("-" * 70)
    print(f"  {'USER':14s} {'GPU':>4s} {'MEM(G)':>8s} {'CPU':>5s}")
    for u, a in sorted(per_user.items(), key=lambda x: (-x[1]["gpu"], -x[1]["mem"])):
        mark = "   <== 你" if u == USER else ""
        print(f"  {u:14s} {a['gpu']:>4d} {round(a['mem']):>8d} {a['cpu']:>5d}{mark}")
    print(bar)

    if used["mem"] == 0 and rows:
        print("\n[警告] 内存解析为 0，原始占用行供核对解析规则：")
        for u, g, mgb, c in rows:
            print(f"    {u}: gpu={g} mem_gb={mgb} cpu={c}")

    # ── 打印：其他用户 RUNNING job 详情 ──────────────────────────────
    running_jobs = []
    for line in running_detail.splitlines():
        if "|" not in line or line.startswith("[stderr]"):
            continue
        parts = (line.strip().split("|") + [""] * 7)[:7]
        jid, user, name, elapsed_s, limit_s, cpus_s, tres_s = parts
        user = user.strip()
        if user == USER:
            continue
        elapsed = parse_slurm_time(elapsed_s.strip())
        limit = parse_slurm_time(limit_s.strip())
        remaining = (limit - elapsed) if limit != float("inf") else float("inf")
        cpus = int(cpus_s.strip()) if cpus_s.strip().isdigit() else 0
        gpu = gpu_from_colon(tres_s.strip())
        running_jobs.append({
            "jid": jid.strip(), "user": user, "name": name.strip(),
            "elapsed": elapsed, "limit": limit, "remaining": remaining,
            "cpu": cpus, "gpu": gpu,
        })

    # 按剩余时间升序（最快结束的排最前）
    running_jobs.sort(key=lambda x: x["remaining"] if x["remaining"] != float("inf") else 1e15)

    print(f"\n[其他用户 RUNNING job 详情（按剩余时间排序，共 {len(running_jobs)} 个）]")
    MAX_SHOW = 30
    shown = running_jobs[:MAX_SHOW]
    if shown:
        hdr = (f"  {'JOBID':>14s}  {'USER':10s}  {'NAME':22s}  "
               f"{'GPU':>3s}  {'CPU':>4s}  {'已运行':>10s}  {'时限':>10s}  "
               f"{'剩余':>10s}  {'预计结束':>12s}")
        print(hdr)
        print("  " + "-" * (len(hdr) - 2))
        for j in shown:
            if j["remaining"] != float("inf"):
                eta_dt = now + datetime.timedelta(minutes=j["remaining"])
                eta_s = eta_dt.strftime("%m-%d %H:%M")
                rem_s = fmt_mins(j["remaining"])
            else:
                eta_s = "未知"
                rem_s = "未知"
            print(f"  {j['jid']:>14s}  {j['user']:10s}  {j['name']:22s}  "
                  f"{j['gpu']:>3d}  {j['cpu']:>4d}  "
                  f"{fmt_mins(j['elapsed']):>10s}  {fmt_mins(j['limit']):>10s}  "
                  f"{rem_s:>10s}  {eta_s:>12s}")
        if len(running_jobs) > MAX_SHOW:
            print(f"  ... 还有 {len(running_jobs) - MAX_SHOW} 个 job 未显示")
    else:
        print("  无（或全是你自己的 job）")

    # ── 打印：预计我的 job 启动时间 ───────────────────────────────────
    print("\n[预计我的 job 启动时间]")
    my_pending_jobs = []
    for line in my_pending_raw.splitlines():
        if "|" not in line or line.startswith("[stderr]"):
            continue
        parts = (line.strip().split("|") + [""] * 5)[:5]
        jid, name, cpus_s, tres_s, reason = parts
        cpu_needed = int(cpus_s.strip()) if cpus_s.strip().isdigit() else 0
        gpu_needed = gpu_from_colon(tres_s.strip())
        my_pending_jobs.append({
            "jid": jid.strip(), "name": name.strip(),
            "cpu": cpu_needed, "gpu": gpu_needed,
            "reason": reason.strip(),
        })

    if not my_pending_jobs:
        print("  当前无 PENDING job")
    else:
        cpu_avail = (qc - used["cpu"]) if qc is not None else 0
        gpu_avail = (qg - used["gpu"]) if qg is not None else 0
        mem_avail = (qm - used["mem"]) if qm is not None else 0.0

        for pj in my_pending_jobs:
            reason = pj["reason"]
            print(f"\n  Job {pj['jid']} ({pj['name']})  "
                  f"需要 {pj['cpu']} CPU / {pj['gpu']} GPU")
            print(f"  当前余量: CPU {cpu_avail}  GPU {gpu_avail}  MEM {round(mem_avail)}G  "
                  f"| 卡住原因: {reason}")

            rl = reason.lower()
            if "cpulimit" in rl or ("cpu" in rl and "limit" in rl):
                short = pj["cpu"] - cpu_avail
                if short <= 0:
                    print(f"  → CPU 余量已足够，可能很快被调度")
                else:
                    print(f"  → 需再释放 {short} CPU 才能启动")
                    print(f"  → 按最快结束顺序逐步释放：")
                    cum = 0
                    fired = False
                    for j in running_jobs:
                        if j["cpu"] <= 0:
                            continue
                        cum += j["cpu"]
                        if j["remaining"] != float("inf"):
                            eta_dt = now + datetime.timedelta(minutes=j["remaining"])
                            eta_s = eta_dt.strftime("%m-%d %H:%M")
                        else:
                            eta_s = "未知"
                        marker = " ← 达到阈值" if (cum >= short and not fired) else ""
                        print(f"       {j['user']:10s}  {j['name'][:20]:20s}  "
                              f"+{j['cpu']:>3d} CPU  累计释放 {cum:>3d}  约 {eta_s}{marker}")
                        if cum >= short and not fired:
                            fired = True
                            print(f"  ★ 预计约 {eta_s} 释放到足够 CPU，你的 job 可启动")
                            break
                    if not fired:
                        print(f"  ★ 以上 job 全部结束仅释放 {cum} CPU，请确认是否有其他限制")
            elif "mem" in rl:
                short_mem = pj.get("mem", 0) - mem_avail  # 估算
                print(f"  → 内存配额不足，等待组员释放内存")
            elif "gres" in rl:
                short_gpu = pj["gpu"] - gpu_avail
                print(f"  → GPU 不足（需 {pj['gpu']}，余量 {gpu_avail}）")
                if short_gpu > 0:
                    cum = 0
                    fired = False
                    for j in running_jobs:
                        if j["gpu"] <= 0:
                            continue
                        cum += j["gpu"]
                        if j["remaining"] != float("inf"):
                            eta_dt = now + datetime.timedelta(minutes=j["remaining"])
                            eta_s = eta_dt.strftime("%m-%d %H:%M")
                        else:
                            eta_s = "未知"
                        marker = " ← 达到阈值" if (cum >= short_gpu and not fired) else ""
                        print(f"       {j['user']:10s}  {j['name'][:20]:20s}  "
                              f"+{j['gpu']:>2d} GPU  累计释放 {cum:>2d}  约 {eta_s}{marker}")
                        if cum >= short_gpu and not fired:
                            fired = True
                            print(f"  ★ 预计约 {eta_s} GPU 释放到位，你的 job 可启动")
                            break
            else:
                print(f"  → 原因 [{reason}]，排队中（非资源配额限制）")

    # ── 打印：我的全部 job ─────────────────────────────────────────────
    print("\n[我的 job]")
    print(myjobs.rstrip())

    # ── 打印：账户 PENDING 队列 ───────────────────────────────────────
    print("\n[chaijy2 PENDING 队列]")
    if pending.strip() and not pending.startswith("[stderr]"):
        for line in pending.splitlines():
            if line.startswith("[stderr]"):
                continue
            print("  " + "  ".join(line.split("|")))
    else:
        print("  无")

    # ── 打印：spgpu 节点状态 ──────────────────────────────────────────
    print("\n[spgpu 分区节点状态]")
    print(nodes_info.rstrip())

    # ── 打印：spgpu 全局 A40 占用情况（跨全部 account，非仅 chaijy2）────
    print("\n[spgpu 全局 A40 占用情况（跨全部 account，非仅 chaijy2）]")
    total_a40 = alloc_a40 = down_a40 = n_nodes = 0
    node_free = []  # (name, free_gpu, free_cpu, free_mem_gb, state) 仅健康节点
    for line in scontrol_nodes.splitlines():
        if "NodeName=" not in line or line.startswith("[stderr]"):
            continue
        pm = re.search(r"Partitions=(\S+)", line)
        if not pm or "spgpu" not in pm.group(1).split(","):
            continue
        n_nodes += 1
        name_m = re.search(r"NodeName=(\S+)", line)
        name = name_m.group(1) if name_m else "?"
        gm = re.search(r"Gres=\S*a40:(\d+)", line)
        node_total = int(gm.group(1)) if gm else 0
        total_a40 += node_total
        sm = re.search(r"State=(\S+)", line)
        state = sm.group(1) if sm else ""
        am = re.search(r"AllocTRES=(\S*)", line)
        node_alloc = gpu_from_tres(parse_tres(am.group(1))) if am else 0
        alloc_a40 += node_alloc
        if "DOWN" in state or "DRAIN" in state:
            down_a40 += node_total
            continue
        # 空闲 CPU / 内存（RealMemory/AllocMem 单位 MB）
        cpu_tot_m = re.search(r"CPUTot=(\d+)", line)
        cpu_alloc_m = re.search(r"CPUAlloc=(\d+)", line)
        free_cpu = (int(cpu_tot_m.group(1)) - int(cpu_alloc_m.group(1))
                    if cpu_tot_m and cpu_alloc_m else 0)
        real_m = re.search(r"RealMemory=(\d+)", line)
        alloc_m = re.search(r"AllocMem=(\d+)", line)
        free_mem_gb = ((int(real_m.group(1)) - int(alloc_m.group(1))) / 1024
                       if real_m and alloc_m else 0.0)
        node_free.append((name, node_total - node_alloc, free_cpu, free_mem_gb, state))
    idle_a40 = total_a40 - alloc_a40 - down_a40
    print(f"  物理容量: 共 {total_a40} 张 A40（{n_nodes} 节点）"
          + (f"  |  故障/维护(down/drain) {down_a40}" if down_a40 else ""))
    print(f"  已分配: {alloc_a40}  |  空闲: {idle_a40}")

    # 单节点空闲 GPU 分布（多卡 job 需单节点凑齐 N 张空闲卡才可立即调度）
    from collections import Counter
    hist = Counter(f[1] for f in node_free)
    hist_s = "  ".join(f"{k}张空闲×{hist[k]}节点" for k in sorted(hist, reverse=True))
    print(f"\n  单节点空闲 GPU 分布: {hist_s}")
    for need in (4, 8):
        cands = [f for f in node_free if f[1] >= need]
        # GPU 够但 CPU/内存不足的节点实际装不下典型 job（8CPU/64G 每 4 卡）
        need_cpu, need_mem = 2 * need, 16.0 * need
        ok = [f for f in cands
              if f[2] >= need_cpu and f[3] >= need_mem]
        print(f"  可立即容纳 {need} 卡单节点 job 的节点: "
              f"{len(cands)} 个（GPU 维度）"
              f"；其中 CPU≥{need_cpu} 且 MEM≥{round(need_mem)}G 也满足的: {len(ok)} 个")

    # 全部有空闲 GPU 的节点逐一列出内部情况（不只是聚合直方图/阈值计数）
    free_nodes = sorted([f for f in node_free if f[1] > 0], key=lambda x: -x[1])
    print(f"\n  空闲 A40 节点明细（全部 {len(free_nodes)} 个有空闲卡的节点，按空闲 GPU 数降序）:")
    if free_nodes:
        print(f"    {'NODE':10s} {'空闲GPU':>7s} {'空闲CPU':>7s} {'空闲MEM(G)':>10s}  STATE")
        for name, free_gpu, free_cpu, free_mem, state in free_nodes:
            note = ""
            if free_gpu >= 4 and (free_cpu < 8 or free_mem < 64):
                note = "   [CPU或内存不足，实际装不下 4 卡典型 job]"
            print(f"    {name:10s} {free_gpu:>7d} {free_cpu:>7d} "
                  f"{round(free_mem):>10d}  {state}{note}")
    else:
        print("    无空闲节点")

    acct_rows = []  # (account, gpu, jobs)
    acct_fallback = False
    acct_used: dict[str, dict] = {}
    for line in global_acct_raw.splitlines():
        if not line.strip() or line.startswith("[stderr]"):
            continue
        parts = line.split(None, 1)
        if len(parts) < 2:
            continue
        t = parse_tres(parts[1])
        g = gpu_from_tres(t)
        a = acct_used.setdefault(parts[0], {"gpu": 0, "jobs": 0})
        a["gpu"] += g
        a["jobs"] += 1
    if not acct_used:  # tres-alloc 不可用 -> 回退 %a/%b
        acct_fallback = True
        out = run("squeue -p spgpu -h -t RUNNING -o '%a|%b'")
        for line in out.splitlines():
            if "|" not in line or line.startswith("[stderr]"):
                continue
            acct, b = line.split("|", 1)
            a = acct_used.setdefault(acct.strip(), {"gpu": 0, "jobs": 0})
            a["gpu"] += gpu_from_colon(b.strip())
            a["jobs"] += 1

    acct_sorted = sorted(acct_used.items(), key=lambda x: -x[1]["gpu"])
    acct_ranks = {acct: i + 1 for i, (acct, _) in enumerate(acct_sorted)}
    print(f"\n  按 account 汇总 GPU 占用（Top 15{'，回退估算' if acct_fallback else ''}）:")
    print(f"    {'ACCOUNT':22s} {'GPU':>4s} {'JOBS':>5s}")
    for acct, a in acct_sorted[:15]:
        mark = "   <== 你的账户" if acct == ACCOUNT else ""
        print(f"    {acct:22s} {a['gpu']:>4d} {a['jobs']:>5d}{mark}")
    if ACCOUNT not in dict(acct_sorted[:15]) and ACCOUNT in acct_used:
        a = acct_used[ACCOUNT]
        print(f"    {'...':22s}")
        print(f"    {ACCOUNT:22s} {a['gpu']:>4d} {a['jobs']:>5d}"
              f"   <== 你的账户（全局第 {acct_ranks[ACCOUNT]} 名）")

    # 全局 PENDING 竞争：排在队里的 job 总共还要多少 GPU
    pend_jobs = pend_gpu = pend_prio_gpu = 0
    for line in global_pending_raw.splitlines():
        if "|" not in line or line.startswith("[stderr]"):
            continue
        acct, b, reason = (line.split("|") + ["", "", ""])[:3]
        g = gpu_from_colon(b.strip())
        pend_jobs += 1
        pend_gpu += g
        # 只有 Priority/Resources 是真在和你抢物理卡；AssocGrp* 是各组自己配额卡住
        if "Priority" in reason or "Resources" in reason:
            pend_prio_gpu += g
    print(f"\n  全局 PENDING 竞争: {pend_jobs} 个 job 排队，共需约 {pend_gpu} GPU"
          f"（其中因 Priority/Resources 真在抢物理卡的约 {pend_prio_gpu} GPU；"
          f"AssocGrp* 类是各组自己配额满，不与你抢空闲卡）")

    print("\n>>> done")


if __name__ == "__main__":
    main()
