#!/usr/bin/env python
"""建立 greatlakes 的 OpenSSH ControlMaster 主连接:认证一次,之后 30d 免认证。

薄 CLI 包装,核心逻辑在 gl_master.py。有 master 就提示已存在;没有就用 GLPW(+GLOTP)
经 pexpect 建立。建好后任何 `ssh greatlakes <cmd>`（含 check_usage.py / gl_submit.py）
在 30d 内复用主连接、零密码零 MFA 零手机。

用法（凭据只经环境变量,绝不落盘）:
    export GLPW='<密码>' GLOTP='<Okta 6 位 TOTP 码>'
    uv run --with pexpect python ~/.claude/skills/greatlakes-usage/gl_connect.py
    unset GLPW GLOTP

推荐 TOTP（给一次 6 位码、无需手机数字匹配）;不设 GLOTP 会在 passcode 处留空触发 push。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gl_master  # noqa: E402

try:
    if gl_master.master_alive():
        print(f">>> master 已存在,无需重建（ssh {gl_master.ALIAS} '<cmd>' 直接免认证）")
    else:
        gl_master.build_master()
    print(f">>> 现在起 30 天内,`ssh {gl_master.ALIAS} '<cmd>'` 直接执行、无需任何凭据。")
except RuntimeError as e:
    sys.exit(f"ERROR: {e}")
