#!/usr/bin/env python3
"""greatlakes 通用提交器:优先复用 ControlMaster 主连接(认证一次,30d 免认证免手机)。

理念:**没有 master 就建立 master**——首次用 GLPW(+GLOTP)经 pexpect 驱动系统 ssh 建立
ControlMaster 主连接;之后所有提交/查询都经系统 ssh 复用该连接、零密码零 MFA 零手机
(slave 不发起认证握手,与服务器 MFA 策略无关)。依赖 ~/.ssh/config 的:

    Host greatlakes
        HostName greatlakes.arc-ts.umich.edu
        User hongzefu
        ControlMaster auto
        ControlPath ~/.ssh/cm-%r@%h:%p
        ControlPersist 30d

密码安全(硬规则):本文件绝不含密码,也绝不把密码写入任何文件。凭据由用户即时提供,
仅经临时环境变量 GLPW(建 master 时必需)/ GLOTP(可选 6 位 TOTP,推荐)传入,用完即 unset。

环境变量(全部可选,除 GL_REPO 在传自定义命令时必需):
  GL_SSH_ALIAS      ~/.ssh/config 里的 ControlMaster 别名,默认 greatlakes
  GLUSER            集群登录用户,默认 hongzefu(只影响默认的 squeue 查询)
  GL_REPO           集群侧可见的仓库绝对路径;自定义命令会自动前置 `cd $GL_REPO &&`
  GLPW / GLOTP      建 master 时的密码 / 6 位 TOTP(不设 GLOTP 则留空触发 push)
  GL_CONNECT_LOG    建连时把服务器输出实时落盘到该文件(push 路径必备,用户可 tail 看数字)
  GL_PUSH_SENTINEL  push 路径的回车握手 sentinel 文件路径:匹配到「Press enter to continue」后
                    阻塞轮询该文件出现才按回车(greatlakes.md「push 修法」第 3 条);
                    未设则立即回车并在 stderr 提示风险。⚠ sentinel 路径本轮未实测。

用法:
  export GL_REPO=/nfs/turbo/coe-chaijy-unreplicated/hongzefu/<仓库>
  export GLPW='<pw>' GLOTP='<6位TOTP>'   # 仅当无 master 需新建时才必需;master 在则可不设
  uv run --no-project --with pexpect python scripts/gl_submit.py
  uv run --no-project --with pexpect python scripts/gl_submit.py "squeue -u hongzefu"
  uv run --no-project --with pexpect python scripts/gl_submit.py "sbatch scripts/xxx.sbatch"
  unset GLPW GLOTP
"""
import os
import shlex
import subprocess
import sys
import time

ALIAS = os.environ.get("GL_SSH_ALIAS", "greatlakes")  # ~/.ssh/config 里的 ControlMaster 别名
USER = os.environ.get("GLUSER", "hongzefu")
REPO = os.environ.get("GL_REPO")  # 集群侧仓库绝对路径,由调用方按项目传入
# 无参数时不默认提交任何 job,只打印队列状态。提交任务请显式传完整命令。
DEFAULT_CMD = f"squeue -u {USER} -o '%.18i %.9P %.22j %.8T %.10M %.6D %R'"


def master_alive() -> bool:
    """ControlMaster 主连接是否存活。纯本地 socket 检查,不出网。"""
    try:
        return subprocess.run(["ssh", "-O", "check", ALIAS],
                              capture_output=True, text=True, timeout=10).returncode == 0
    except Exception:
        return False


def _wait_sentinel(path: str, timeout_s: int = 600) -> None:
    """push 路径的回车握手:阻塞轮询 sentinel 文件出现(用户在手机 approve 后 touch 它放行)。"""
    print(f">>> 等待 sentinel 文件放行后再按回车: touch {path}", file=sys.stderr, flush=True)
    deadline = time.monotonic() + timeout_s
    while not os.path.exists(path):
        if time.monotonic() > deadline:
            sys.exit(f"ERROR: 等待 sentinel 超时({timeout_s}s): {path}")
        time.sleep(1)
    try:
        os.remove(path)
    except OSError:
        pass


def build_master() -> None:
    """没有 master 就建立:用 GLPW(+GLOTP)经 pexpect 驱动系统 ssh 建 ControlMaster 主连接。"""
    pw = os.environ.get("GLPW")
    if not pw:
        sys.exit("ERROR: 无 ControlMaster 主连接,且未设 GLPW——无法建立。\n"
                 "  请 export GLPW='<pw>' GLOTP='<6位TOTP>' 后重试"
                 "(推荐 TOTP,给一次码即可、无需手机数字匹配)。")
    import pexpect  # lazy:仅建连时需要;master 已在的纯提交/查询路径不依赖它

    otp = os.environ.get("GLOTP", "")
    sentinel = os.environ.get("GL_PUSH_SENTINEL", "")
    mark = "CONNECTED_OK_MARKER"
    ssh_args = [
        "-o", "StrictHostKeyChecking=accept-new",
        "-o", "ConnectTimeout=25",
        "-o", "ControlMaster=auto",
        "-o", "NumberOfPasswordPrompts=1",
        ALIAS, f"echo {mark} && hostname",
    ]
    # push 要等用户看手机、做数字匹配,90 秒不够;TOTP 路径很快,保持 90。设了 sentinel 再放宽。
    timeout = 90 if otp else (900 if sentinel else 240)
    print(f">>> 无 master,正在建立 {ALIAS} 主连接"
          f"（{'TOTP 码认证' if otp else 'push,需在手机上做数字匹配'}）...", file=sys.stderr)
    child = pexpect.spawn("ssh", ssh_args, encoding="utf-8", timeout=timeout)
    # 把远端输出实时落盘,调用方可以 tail 这个文件拿到数字匹配提示（push 路径必备）。
    # logfile_read 只记录「读到的」服务器输出,不含我们 sendline 出去的密码/OTP。
    log_path = os.environ.get("GL_CONNECT_LOG")
    if log_path:
        child.logfile_read = open(log_path, "w", encoding="utf-8", buffering=1)

    # Okta Verify 的数字匹配提示与「按回车继续」——两者缺一,push 路径就会一直 expect 到 TIMEOUT,
    # 表现为「卡死」（2026-06-19 定位的真根因,见 greatlakes.md）。
    number_hint = r"(?i)(?:correct answer is|select the number|choose the number|number to select[^\d]*)[^\d]{0,20}(\d+)"
    press_enter = r"(?i)press enter to continue"
    pats = [r"[Pp]assword:", r"[Pp]asscode", mark,
            r"(?i)are you sure you want to continue connecting",
            number_hint,
            press_enter,
            r"(?i)(permission denied|authentication failed)",
            pexpect.EOF, pexpect.TIMEOUT]
    sent_pw = False
    while True:
        i = child.expect(pats)
        if i == 0:
            if sent_pw:
                sys.exit("ERROR: 密码似乎被拒（再次询问 password）")
            child.sendline(pw)
            sent_pw = True
        elif i == 1:
            child.sendline(otp)            # 空串=回车=触发 push
            if not otp:
                print(">>> 已触发 push,请留意手机上的 Okta Verify 通知", file=sys.stderr, flush=True)
        elif i == 2:
            break
        elif i == 3:
            child.sendline("yes")
        elif i == 4:
            number = child.match.group(1)
            print(f">>> OKTA_NUMBER={number}  请在手机上选这个数字", file=sys.stderr, flush=True)
        elif i == 5:
            # 「Press enter to continue」——缺这条会一路 TIMEOUT。
            # approve 之前就按回车会导致单次校验失败,故优先走 sentinel 握手。
            if sentinel:
                _wait_sentinel(sentinel)
            else:
                print(">>> 未设 GL_PUSH_SENTINEL,立即按回车;若用户尚未在手机 approve,本次校验会失败",
                      file=sys.stderr, flush=True)
            child.sendline("")
        elif i == 6:
            sys.exit(f"ERROR: 认证失败（密码或 OTP 不对）:\n{child.before}")
        elif i == 7:
            sys.exit(f"ERROR: 连接意外结束（认证未通过?）:\n{child.before}")
        else:
            sys.exit(f"ERROR: 超时（网络或认证卡住）:\n{child.before}")
    child.expect(pexpect.EOF)
    if not master_alive():
        sys.exit("ERROR: 建立后 master 复核未通过,检查 ~/.ssh/config 的 ControlPersist。")
    print(">>> master 已建立（ControlPersist 30d 内免认证）", file=sys.stderr)


def main():
    # 远程命令 cwd 是 greatlakes 的 home,自定义命令一律前置 cd $GL_REPO（相对路径才找得到脚本）。
    if len(sys.argv) > 1:
        if not REPO:
            sys.exit("ERROR: 传了自定义命令但未设 GL_REPO——远程 cwd 是 home,请 export GL_REPO=<集群侧仓库绝对路径>。")
        remote_cmd = f"cd {shlex.quote(REPO)} && " + " ".join(sys.argv[1:])
    else:
        remote_cmd = DEFAULT_CMD

    # 没有 master 就建立 master,然后经系统 ssh 复用执行（零认证）。
    if master_alive():
        print(f">>> 复用 {ALIAS} ControlMaster 主连接（免认证）", file=sys.stderr)
    else:
        build_master()

    print(f"[remote cmd] {remote_cmd}", file=sys.stderr)
    r = subprocess.run(["ssh", ALIAS, f"bash -lc {shlex.quote(remote_cmd)}"],
                       capture_output=True, text=True, timeout=120)
    sys.stdout.write(r.stdout)
    if r.stderr.strip():
        sys.stderr.write("[remote stderr]\n" + r.stderr)
    print(f"[remote exit {r.returncode}]", file=sys.stderr)
    sys.exit(0 if r.returncode == 0 else 5)


if __name__ == "__main__":
    main()
