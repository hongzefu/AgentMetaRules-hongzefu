#!/usr/bin/env python
"""greatlakes ControlMaster 共享逻辑:检测 / 建立主连接 + 复用执行远程命令。

被 gl_connect.py（建连 CLI）和 check_usage.py（查占用）共用。核心理念:**没有 master
就建立 master**——认证一次（密码 + Okta MFA）后建立 control socket，ControlPersist=30d
让它后台保持;之后所有 `ssh greatlakes <cmd>` 复用已认证通道、不再发起任何 SSH 认证握手,
因此零密码、零 MFA、零手机（slave 根本不认证,与服务器 MFA 策略无关）。

依赖 ~/.ssh/config 中已配好的:
    Host greatlakes
        HostName greatlakes.arc-ts.umich.edu
        User hongzefu
        ControlMaster auto
        ControlPath ~/.ssh/cm-%r@%h:%p
        ControlPersist 30d

凭据只经环境变量 GLPW（必需）/ GLOTP（可选 6 位 TOTP，推荐;不设则在 passcode 处留空
触发 push）传入,本模块绝不把它们写入任何文件。
"""
import os
import subprocess
import sys

ALIAS = os.environ.get("GL_SSH_ALIAS", "greatlakes")  # ~/.ssh/config 里的 ControlMaster 别名


def master_alive(alias: str = ALIAS) -> bool:
    """ControlMaster 主连接是否存活（存活则可零认证复用）。纯本地 socket 检查,不出网。"""
    try:
        r = subprocess.run(["ssh", "-O", "check", alias],
                           capture_output=True, text=True, timeout=10)
        return r.returncode == 0
    except Exception:
        return False


def build_master(alias: str = ALIAS) -> None:
    """无 master 时用 GLPW(+GLOTP) 经 pexpect 驱动系统 ssh 建立 ControlMaster 主连接。

    成功后 control socket 就绪、ControlPersist 30d 内免认证。失败抛 RuntimeError。
    """
    pw = os.environ.get("GLPW")
    if not pw:
        raise RuntimeError(
            "无 ControlMaster 主连接,且未设 GLPW——无法建立主连接。\n"
            "  请提供凭据建主连接（之后 30d 内所有操作免认证免手机）:\n"
            "    export GLPW='<密码>' GLOTP='<Okta 6 位 TOTP 码>'\n"
            "  推荐 TOTP（给一次码即可,无需手机数字匹配）。")

    import pexpect  # lazy:仅真正建连时才需要,master 存活的纯查询路径不依赖它

    otp = os.environ.get("GLOTP", "")
    mark = "CONNECTED_OK_MARKER"
    ssh_args = [
        "-o", "StrictHostKeyChecking=accept-new",
        "-o", "ConnectTimeout=25",
        "-o", "ControlMaster=auto",
        "-o", "NumberOfPasswordPrompts=1",
        alias,
        f"echo {mark} && hostname",
    ]
    print(f">>> 无 master,正在建立 {alias} 主连接"
          f"（{'TOTP 码认证' if otp else '留空触发 push,需手机数字匹配'}）...",
          file=sys.stderr, flush=True)

    child = pexpect.spawn("ssh", ssh_args, encoding="utf-8", timeout=90)
    pats = [
        r"[Pp]assword:",                                       # 0 密码
        r"[Pp]asscode",                                        # 1 Okta passcode（TOTP）
        mark,                                                  # 2 认证通过、命令已远端执行
        r"(?i)are you sure you want to continue connecting",   # 3 首次 host key 确认
        r"(?i)(permission denied|authentication failed)",      # 4 认证失败
        pexpect.EOF,                                            # 5
        pexpect.TIMEOUT,                                        # 6
    ]
    sent_pw = False
    while True:
        i = child.expect(pats)
        if i == 0:
            if sent_pw:
                raise RuntimeError("密码似乎被拒（再次询问 password）")
            child.sendline(pw)
            sent_pw = True
        elif i == 1:
            child.sendline(otp)            # 空串=回车=触发 push
        elif i == 2:
            break
        elif i == 3:
            child.sendline("yes")
        elif i == 4:
            raise RuntimeError(f"认证失败（密码或 OTP 不对）:\n{child.before}")
        elif i == 5:
            raise RuntimeError(f"连接意外结束（认证未通过?）:\n{child.before}")
        else:
            raise RuntimeError(f"超时（网络或认证卡住）:\n{child.before}")
    child.expect(pexpect.EOF)

    if not master_alive(alias):
        raise RuntimeError("建立后 master 复核未通过,请检查 ~/.ssh/config 的 ControlPersist。")
    print(">>> master 已建立（ControlPersist 30d 内免认证）", file=sys.stderr, flush=True)


def ensure_master(alias: str = ALIAS) -> bool:
    """确保 master 存在:存活直接返回 True;否则建立。返回 True=之前已存活,False=本次新建。"""
    if master_alive(alias):
        return True
    build_master(alias)
    return False


def run_remote(cmd: str, alias: str = ALIAS, timeout: int = 60) -> str:
    """经 master 复用执行远程命令（零认证）。stderr 非空时以 [stderr] 前缀附到返回文本。"""
    r = subprocess.run(["ssh", alias, cmd],
                       capture_output=True, text=True, timeout=timeout)
    text = r.stdout
    if r.stderr.strip():
        text += f"\n[stderr] {r.stderr.strip()}"
    return text
