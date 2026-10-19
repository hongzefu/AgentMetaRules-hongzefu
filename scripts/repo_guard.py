#!/usr/bin/env python3
"""开工检查与提交后检查（AGENTS.md 第 29 条；只用 Python 标准库）。

三个子命令
==========
- ``start``：只读（唯一的网络操作是 fetch）。对当前仓库 ``git fetch --quiet``，对子模块 ``.agentmetarules``
  做 ``git fetch --quiet origin main``，输出三行判定：

    REPO_SYNC=OK|BEHIND n=|DIVERGED|NO_UPSTREAM|FETCH_FAIL|DETACHED|NOT_GIT
    PUSH_STATE=CLEAN|AHEAD n=|EXEMPT reason=sub_worktree|no_upstream|hold
    RULES_SYNC=OK|BEHIND n=|NO_SUBMODULE|NOT_ONBOARDED

- ``fix``：agent 在开工第一步执行。先查 HOLD 标记文件与 detached，再依次：① 落后时 ``git merge --ff-only @{u}``；
  ② 领先且有 upstream 时裸 ``git push``；③ 有标记块但没有子模块时 ``git submodule add -b main <url> .agentmetarules``；
  ④ ``git submodule update --init --remote .agentmetarules``；⑤ 用子模块里的 ``sync_rules.py self-apply``；
  ⑥ 有变化就逐个路径 ``git add`` 规则文件并提交，有 upstream 就推送。末行 ``GUARD_FIX=PASS|STOP reason=…``。
- ``post-commit``：PostToolUse hook。从 stdin 读 hook 输入 JSON，命令匹配 ``\\bgit\\b[^|;&]*\\bcommit\\b`` 时才检查
  是否有未推送的 commit，有就输出 additionalContext 提醒；不匹配立即退出，不 fetch。

安全约束
========
- 任何异常都只输出一行 ``GUARD_ERROR=<简述>``，退出码恒为 0，绝不阻断会话（红线 R6）。
- 所有 git 调用带超时：fetch 等网络操作 20 秒，其余 10 秒。
- 不 rebase、不 merge 非快进、不 ``--force``、不 ``reset``；被拒即停（K5、K6、R3）。
- 豁免：分支名匹配 ``worktree-agent-*``（子代理 worktree）、当前分支没有 upstream、存在
  ``$(git rev-parse --git-dir)/AGENTMETARULES_HOLD``（合并后审查 FAIL 或冻结期，由主会话写入与删除）。
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Dict, List, Optional, Tuple

#: 正本仓库 HTTPS 地址（公开仓库，fetch 不需要凭据）；测试可用环境变量 AGENTMETARULES_URL 覆盖。
DEFAULT_URL = "https://github.com/hongzefu/AgentMetaRules-hongzefu.git"
#: 子模块跟踪的正本分支。
CANON_BRANCH = "main"
#: 子模块目录（相对仓库根）。
SUBMODULE_PATH = ".agentmetarules"
#: 根目录规则文件（与 sync_rules.py 自同步模式的固定映射一致）。
RULE_FILES = ("AGENTS.md", "CLAUDE.md", "greatlakes.md")
#: 「规则文件有别人的在途改动」检查的路径（三份 md 与 .gitmodules）。
RULES_DIRTY_PATHS = (".gitmodules",) + RULE_FILES
#: 本地 HOLD 标记文件名（位于 git-dir 内，不进版本库）。
HOLD_NAME = "AGENTMETARULES_HOLD"
#: 子代理 worktree 分支名模式。
SUB_WORKTREE_GLOB = "worktree-agent-*"
#: post-commit 过滤正则：命令里出现 git …… commit（中间不跨管道与命令分隔符）。
COMMIT_RE = re.compile(r"\bgit\b[^|;&]*\bcommit\b")
#: 根目录 md 里表示「已有标记块（项目副本格式）」的行：BEGIN 行带 src=。
#: 正本源文件的 BEGIN 行不带属性，不算——正本仓库自己不加子模块（红线 R1）。
MARKER_LINE_RE = re.compile(rb"^<!-- AGENTMETARULES:BEGIN common-[a-z]+ src=[0-9a-f]{40} ", re.M)

TIMEOUT_FETCH = 20  # 网络操作（fetch / push / 子模块 clone 与 update）
TIMEOUT_GIT = 10  # 其余 git 调用
TIMEOUT_APPLY = 120  # self-apply（uv 启动 + 读写三份文件）

CO_AUTHOR = "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"


class GuardStop(Exception):
    """fix 需要停下：reason 进 GUARD_FIX=STOP 判定行，output 是附在后面的 git 原文。"""

    def __init__(self, reason: str, output: str = ""):
        super().__init__(reason)
        self.reason = reason
        self.output = output


# ---------------------------------------------------------------------------
# 基础工具
# ---------------------------------------------------------------------------


def emit(line: str) -> None:
    sys.stdout.write(line + "\n")
    sys.stdout.flush()


def _env() -> Dict[str, str]:
    env = dict(os.environ)
    env["LC_ALL"] = "C"
    env["GIT_TERMINAL_PROMPT"] = "0"  # 需要凭据时直接失败，不挂住等输入
    return env


def git(args: List[str], cwd: str, timeout: int = TIMEOUT_GIT, extra_config: Optional[List[str]] = None
        ) -> subprocess.CompletedProcess:
    """执行一条 git 命令（文本模式、捕获输出、带超时）；超时抛 subprocess.TimeoutExpired。"""
    cmd = ["git"]
    for kv in extra_config or []:
        cmd += ["-c", kv]
    cmd += args
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, errors="backslashreplace",
                          timeout=timeout, env=_env())


def git_out(args: List[str], cwd: str, timeout: int = TIMEOUT_GIT) -> Optional[str]:
    """成功返回去掉首尾空白的 stdout，失败返回 None。"""
    r = git(args, cwd, timeout)
    return r.stdout.strip() if r.returncode == 0 else None


def _raw(r: subprocess.CompletedProcess) -> str:
    return ((r.stdout or "") + (r.stderr or "")).strip()


def _url() -> str:
    return os.environ.get("AGENTMETARULES_URL") or DEFAULT_URL


def _file_proto_config(url: str) -> List[str]:
    """本地路径或 file:// 地址（测试用）需要放行 file 协议才能 submodule add / update。"""
    if url.startswith("file://") or url.startswith("/") or url.startswith("."):
        return ["protocol.file.allow=always"]
    return []


# ---------------------------------------------------------------------------
# 状态采集（start 与 fix 共用）
# ---------------------------------------------------------------------------


class State:
    """当前仓库的同步状态。"""

    def __init__(self) -> None:
        self.top: Optional[str] = None
        self.git_dir: Optional[str] = None
        self.branch: Optional[str] = None
        self.upstream: Optional[str] = None
        self.fetch_ok = True
        self.ahead = 0
        self.behind = 0
        self.dirty = 0
        self.hold: Optional[str] = None  # HOLD 文件内容（存在时）
        self.rules = "NO_SUBMODULE"
        self.rules_behind: Optional[int] = None
        self.rules_note = ""

    # 三行判定 -------------------------------------------------------------

    def repo_line(self) -> str:
        if self.top is None:
            return "REPO_SYNC=NOT_GIT"
        extra = f" dirty={self.dirty}"
        if self.branch is None:
            return "REPO_SYNC=DETACHED" + extra
        if self.upstream is None:
            return f"REPO_SYNC=NO_UPSTREAM branch={self.branch}" + extra
        tail = f" branch={self.branch} upstream={self.upstream}" + extra
        if not self.fetch_ok:
            return f"REPO_SYNC=FETCH_FAIL local_ahead={self.ahead} local_behind={self.behind}" + tail
        if self.ahead and self.behind:
            return f"REPO_SYNC=DIVERGED ahead={self.ahead} behind={self.behind}" + tail
        if self.behind:
            return f"REPO_SYNC=BEHIND n={self.behind}" + tail
        return "REPO_SYNC=OK" + tail

    def exempt_reason(self) -> Optional[str]:
        if self.branch is not None and fnmatch.fnmatchcase(self.branch, SUB_WORKTREE_GLOB):
            return "sub_worktree"
        if self.hold is not None:
            return "hold"
        if self.upstream is None:
            return "no_upstream"
        return None

    def push_line(self) -> str:
        reason = self.exempt_reason()
        if reason:
            return f"PUSH_STATE=EXEMPT reason={reason}"
        if self.ahead:
            return f"PUSH_STATE=AHEAD n={self.ahead} branch={self.branch}"
        return "PUSH_STATE=CLEAN"

    def rules_line(self) -> str:
        if self.rules == "BEHIND":
            n = "unknown" if self.rules_behind is None else str(self.rules_behind)
            return f"RULES_SYNC=BEHIND n={n}" + (f" {self.rules_note}" if self.rules_note else "")
        return f"RULES_SYNC={self.rules}" + (f" {self.rules_note}" if self.rules_note else "")

    def print_lines(self) -> None:
        emit(self.repo_line())
        if self.top is None:
            return
        emit(self.push_line())
        emit(self.rules_line())


def _has_markers(top: str) -> bool:
    for f in RULE_FILES:
        try:
            with open(os.path.join(top, f), "rb") as fh:
                if MARKER_LINE_RE.search(fh.read()):
                    return True
        except OSError:
            continue
    return False


def _submodule_registered(top: str) -> bool:
    """.gitmodules 里是否已登记 .agentmetarules。"""
    if not os.path.isfile(os.path.join(top, ".gitmodules")):
        return False
    r = git(["config", "-f", ".gitmodules", "--get-regexp", r"^submodule\..*\.path$"], top)
    if r.returncode != 0:
        return False
    return any(line.split(" ", 1)[-1].strip() == SUBMODULE_PATH for line in r.stdout.splitlines())


def _hold_path(git_dir: str) -> str:
    return os.path.join(git_dir, HOLD_NAME)


def collect(cwd: str, do_fetch: bool = True) -> State:
    """采集状态；do_fetch=False 时不碰网络（post-commit 用）。"""
    st = State()
    top = git_out(["rev-parse", "--show-toplevel"], cwd)
    if not top:
        return st
    st.top = top
    gd = git_out(["rev-parse", "--absolute-git-dir"], top)
    st.git_dir = gd
    if gd and os.path.isfile(_hold_path(gd)):
        try:
            with open(_hold_path(gd), "r", encoding="utf-8", errors="backslashreplace") as fh:
                st.hold = fh.read()
        except OSError as exc:
            st.hold = f"（读取失败：{exc}）"
    st.branch = git_out(["symbolic-ref", "--short", "-q", "HEAD"], top) or None
    porcelain = git_out(["status", "--porcelain", "--ignore-submodules=dirty"], top)
    st.dirty = len([ln for ln in (porcelain or "").splitlines() if ln.strip()])
    if st.branch is not None:
        st.upstream = git_out(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"], top) or None
    if st.upstream is not None:
        if do_fetch:
            try:
                st.fetch_ok = git(["fetch", "--quiet"], top, TIMEOUT_FETCH).returncode == 0
            except subprocess.TimeoutExpired:
                st.fetch_ok = False
        counts = git_out(["rev-list", "--left-right", "--count", "HEAD...@{u}"], top)
        if counts:
            a, b = counts.split()
            st.ahead, st.behind = int(a), int(b)
    _collect_rules(st, do_fetch)
    return st


def _collect_rules(st: State, do_fetch: bool) -> None:
    top = st.top
    sub = os.path.join(top, SUBMODULE_PATH)
    if os.path.exists(os.path.join(sub, ".git")):
        fetch_note = ""
        if do_fetch:
            try:
                ok = git(["fetch", "--quiet", "origin", CANON_BRANCH], sub, TIMEOUT_FETCH).returncode == 0
            except subprocess.TimeoutExpired:
                ok = False
            if not ok:
                fetch_note = "fetch=fail"
        n = git_out(["rev-list", "--count", f"HEAD..origin/{CANON_BRANCH}"], sub)
        if n is None:
            st.rules, st.rules_behind, st.rules_note = "BEHIND", None, ("reason=no_origin_main " + fetch_note).strip()
        elif int(n) == 0:
            st.rules, st.rules_note = "OK", fetch_note
        else:
            st.rules, st.rules_behind, st.rules_note = "BEHIND", int(n), fetch_note
        return
    if _submodule_registered(top):
        # 新 clone：.gitmodules 已登记但子模块目录未初始化，fix 的第 ④ 步会 --init。
        st.rules, st.rules_behind, st.rules_note = "BEHIND", None, "reason=uninitialized"
        return
    st.rules = "NOT_ONBOARDED" if _has_markers(top) else "NO_SUBMODULE"


# ---------------------------------------------------------------------------
# start
# ---------------------------------------------------------------------------


def cmd_start(args) -> None:
    collect(os.getcwd(), do_fetch=True).print_lines()


# ---------------------------------------------------------------------------
# fix
# ---------------------------------------------------------------------------


def _staged(top: str) -> List[Tuple[str, str]]:
    """已暂存条目 (状态字母, 路径)，不做重命名检测。"""
    r = git(["diff", "--cached", "--name-status", "--no-renames", "-z"], top)
    if r.returncode != 0:
        raise GuardStop("foreign_staged", _raw(r))
    parts = [p for p in r.stdout.split("\0") if p]
    out = []
    for i in range(0, len(parts) - 1, 2):
        out.append((parts[i], parts[i + 1]))
    return out


def _under(path: str, roots: List[str]) -> bool:
    for r in roots:
        r = r.rstrip("/")
        if path == r or path.startswith(r + "/"):
            return True
    return False


def _check_foreign_staged(top: str, removal_roots: List[str]) -> List[str]:
    """已暂存内容只允许是 --include-staged-removal 路径下的删除；返回这些删除路径。其他内容 → STOP foreign_staged。"""
    foreign, removals = [], []
    for status, path in _staged(top):
        if status == "D" and _under(path, removal_roots):
            removals.append(path)
        else:
            foreign.append(f"{status}\t{path}")
    if foreign:
        raise GuardStop("foreign_staged", "已暂存的其他内容：\n" + "\n".join(foreign))
    return removals


def _check_rules_dirty(top: str) -> None:
    r = git(["status", "--porcelain", "--", *RULES_DIRTY_PATHS], top)
    lines = [ln for ln in r.stdout.splitlines() if ln.strip()]
    if r.returncode != 0 or lines:
        raise GuardStop("rules_dirty", _raw(r))


def _status_sb(top: str) -> str:
    try:
        r = git(["status", "-sb"], top)
        return _raw(r)
    except Exception as exc:  # noqa: BLE001 —— 只是附带原文，失败不影响判定
        return f"（git status -sb 失败：{exc}）"


def _sync_rules_cmd(top: str) -> List[str]:
    script = os.path.join(top, SUBMODULE_PATH, "scripts", "sync_rules.py")
    uv = shutil.which("uv")
    if uv:
        return [uv, "run", "--no-project", "--quiet", "python", script, "self-apply", "--root", top]
    return [sys.executable, script, "self-apply", "--root", top]


def _self_apply(top: str) -> Tuple[int, str]:
    r = subprocess.run(_sync_rules_cmd(top), cwd=top, capture_output=True, text=True, errors="backslashreplace",
                       timeout=TIMEOUT_APPLY, env=_env())
    return r.returncode, ((r.stdout or "") + (r.stderr or "")).strip()


def _sub_head(top: str) -> Optional[str]:
    sub = os.path.join(top, SUBMODULE_PATH)
    if not os.path.exists(os.path.join(sub, ".git")):
        return None
    return git_out(["rev-parse", "HEAD"], sub)


def _commit_message(prefix: str, before: Optional[str], after: Optional[str], changed: List[str],
                    sync_summary: str, removal_roots: List[str], rules_changed: bool) -> str:
    short = (after or "-")[:7]
    if rules_changed:
        subject = f"{prefix} 规则子模块更新到 {short}"
    else:
        # 规则已一致、只有 --include-staged-removal 的删除要提交
        subject = f"{prefix} 规则子模块已是 {short}，删除 {', '.join(removal_roots)}"
    body = [
        subject,
        "",
        "由 repo_guard.py fix 自动生成（AGENTS.md 第 29 条开工检查）。",
        "",
        f"子模块 {SUBMODULE_PATH} 前：{before or '无（首次接入）'}",
        f"子模块 {SUBMODULE_PATH} 后：{after or '-'}",
        "",
        "改动文件：",
        *[f"  {c}" for c in changed],
        "",
        sync_summary or "SYNC_SUMMARY=-（本次未执行 self-apply）",
        "",
        CO_AUTHOR,
        "",
    ]
    return "\n".join(body)


def _fix(args, st: State) -> None:
    top = st.top
    removal_roots = list(args.include_staged_removal or [])

    if st.branch is None:
        raise GuardStop("detached", _status_sb(top))
    if st.upstream is not None and st.fetch_ok and st.ahead and st.behind:
        raise GuardStop("diverged", _status_sb(top))
    _check_rules_dirty(top)
    _check_foreign_staged(top, removal_roots)

    # ① 落后 → 只快进
    if st.upstream is not None and st.behind:
        r = git(["merge", "--ff-only", "@{u}"], top)
        if r.returncode != 0:
            raise GuardStop("ff_refused", _raw(r))
        emit(f"GUARD_STEP=ff_merge behind={st.behind} PASS")
        # 快进可能带进远端已登记的 .gitmodules 与子模块 gitlink，重采规则状态再走后续子模块步骤
        _collect_rules(st, do_fetch=False)
    # ② 领先且有 upstream → 补推
    if st.upstream is not None and st.ahead:
        r = git(["push"], top, TIMEOUT_FETCH)
        if r.returncode != 0:
            raise GuardStop("push_rejected", _raw(r))
        emit(f"GUARD_STEP=push ahead={st.ahead} PASS")

    sync_summary = ""
    before = _sub_head(top)
    url = _url()
    cfg = _file_proto_config(url)
    sub_needed = st.rules in ("NOT_ONBOARDED", "OK", "BEHIND")
    if sub_needed:
        # ③ 有标记块但还没有子模块 → 接入
        if st.rules == "NOT_ONBOARDED":
            r = git(["submodule", "add", "-b", CANON_BRANCH, url, SUBMODULE_PATH], top, TIMEOUT_FETCH, cfg)
            if r.returncode != 0:
                raise GuardStop("submodule_add_failed", _raw(r))
            emit(f"GUARD_STEP=submodule_add url={url} PASS")
        # ④ 子模块切到 origin/main 最新
        r = git(["submodule", "update", "--init", "--remote", SUBMODULE_PATH], top, TIMEOUT_FETCH, cfg)
        if r.returncode != 0:
            raise GuardStop("submodule_update_failed", _raw(r))
        after_update = _sub_head(top)
        emit(f"GUARD_STEP=submodule_update sha={after_update} PASS")
        # ⑤ self-apply
        rc, out = _self_apply(top)
        for ln in out.splitlines():
            if ln.startswith("SYNC_SUMMARY="):
                sync_summary = ln
        if rc not in (0, 3):
            raise GuardStop("self_apply_failed", out)
        emit(f"GUARD_STEP=self_apply rc={rc} {sync_summary or 'SYNC_SUMMARY=-'}")
    after = _sub_head(top)

    # ⑥ 有变化就逐个路径 git add，再提交
    rules_changed = False
    if sub_needed:
        paths = [".gitmodules", SUBMODULE_PATH, *RULE_FILES]
        for p in paths:
            if not os.path.exists(os.path.join(top, p)):
                continue
            r = git(["status", "--porcelain", "--", p], top)
            if r.stdout.strip():
                ra = git(["add", "--", p], top)
                if ra.returncode != 0:
                    raise GuardStop("add_failed", _raw(ra))
                rules_changed = True
    staged_all = _staged(top)
    removals = [p for s_, p in staged_all if s_ == "D" and _under(p, removal_roots)]
    if not staged_all:
        st2 = collect(top, do_fetch=False)
        emit(st2.push_line())
        emit("GUARD_FIX=PASS commit=none")
        return
    changed = [f"{s}\t{p}" for s, p in staged_all]
    if not rules_changed and not removals:
        raise GuardStop("foreign_staged", "已暂存的其他内容：\n" + "\n".join(changed))
    msg = _commit_message(args.subject_prefix, before, after, changed, sync_summary, removal_roots, rules_changed)
    fd, msg_path = tempfile.mkstemp(prefix="repo_guard_msg_", suffix=".txt")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(msg)
        r = git(["commit", "--quiet", "-F", msg_path], top)
    finally:
        try:
            os.unlink(msg_path)
        except OSError:
            pass
    if r.returncode != 0:
        raise GuardStop("commit_failed", _raw(r))
    sha = git_out(["rev-parse", "HEAD"], top)
    emit(f"GUARD_STEP=commit sha={sha} files={len(changed)} PASS")
    if st.upstream is None:
        emit("PUSH_STATE=EXEMPT reason=no_upstream")
        emit(f"GUARD_FIX=PASS commit={sha} push=pending_user")
        return
    r = git(["push"], top, TIMEOUT_FETCH)
    if r.returncode != 0:
        raise GuardStop("push_rejected", _raw(r))
    emit("PUSH_STATE=CLEAN")
    emit(f"GUARD_FIX=PASS commit={sha} push=done")


def cmd_fix(args) -> None:
    st = collect(os.getcwd(), do_fetch=True)
    st.print_lines()
    if st.top is None:
        return
    if st.hold is not None:
        # HOLD：不提交、不推送、不快进，只输出三行判定和文件内容
        emit(f"HOLD_FILE={_hold_path(st.git_dir)}")
        for ln in st.hold.splitlines():
            emit(f"HOLD: {ln}")
        return
    if st.exempt_reason() == "sub_worktree":
        # 子代理 worktree：不提交、不推送
        return
    try:
        _fix(args, st)
    except GuardStop as stop:
        emit(f"GUARD_FIX=STOP reason={stop.reason}")
        if stop.output:
            for ln in stop.output.splitlines():
                emit(f"GIT: {ln}")
        if stop.reason not in ("detached",):
            for ln in _status_sb(st.top).splitlines():
                emit(f"STATUS: {ln}")


# ---------------------------------------------------------------------------
# post-commit
# ---------------------------------------------------------------------------


def cmd_post_commit(args) -> None:
    raw = sys.stdin.read()
    try:
        data = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        return
    if not isinstance(data, dict) or data.get("tool_name") != "Bash":
        return
    tool_input = data.get("tool_input") or {}
    command = tool_input.get("command") if isinstance(tool_input, dict) else None
    if not isinstance(command, str) or not COMMIT_RE.search(command):
        return
    st = collect(os.getcwd(), do_fetch=False)
    if st.top is None or st.exempt_reason() in ("sub_worktree", "hold"):
        return
    if st.upstream is None or st.ahead <= 0:
        return
    msg = f"PUSH_STATE=AHEAD n={st.ahead} branch={st.branch}：按第 29 条立即 git push"
    emit(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": msg}},
                    ensure_ascii=False))


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="repo_guard.py", description="开工检查与提交后检查（AGENTS.md 第 29 条）。")
    sub = parser.add_subparsers(dest="cmd", required=True, metavar="子命令")
    p = sub.add_parser("start", help="只读检查（只 fetch），输出 REPO_SYNC / PUSH_STATE / RULES_SYNC 三行")
    p.set_defaults(func=cmd_start)
    p = sub.add_parser("fix", help="快进、补推、接入并更新子模块、self-apply、提交并推送")
    p.add_argument("--subject-prefix", default="docs:", help="迁移提交的 subject 前缀（默认 docs:，按仓库体例覆盖）")
    p.add_argument("--include-staged-removal", action="append", default=[], metavar="路径",
                   help="把该路径下已暂存的删除一并纳入本次提交（可重复）；其他已暂存内容存在时停下")
    p.set_defaults(func=cmd_fix)
    p = sub.add_parser("post-commit", help="PostToolUse hook：git commit 之后检查是否有未推送的 commit")
    p.set_defaults(func=cmd_post_commit)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="backslashreplace")
        except (AttributeError, ValueError):
            pass
    try:
        args = build_parser().parse_args(argv)
    except SystemExit as exc:
        if exc.code not in (0, None):
            emit("GUARD_ERROR=bad_arguments")
        return 0
    try:
        args.func(args)
    except subprocess.TimeoutExpired as exc:
        emit(f"GUARD_ERROR=timeout cmd={' '.join(map(str, exc.cmd))[:120]}")
    except Exception as exc:  # noqa: BLE001 —— R6：任何异常都不得阻断会话
        emit(f"GUARD_ERROR={type(exc).__name__}: {str(exc)[:160]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
