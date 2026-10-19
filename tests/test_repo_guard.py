"""repo_guard.py（start / fix / post-commit）的端到端测试。

在临时目录里建：bare 正本 canon.git（内容取自本仓库工作树）、bare 项目远端 remote.git、
种子仓库 seed（用 repo_guard fix 首次接入子模块并推送）、两个 clone A / B。
子模块地址用 file://，经环境变量 AGENTMETARULES_URL 交给 repo_guard；不访问网络、不依赖全局 git 配置。
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
GUARD = REPO / "scripts" / "repo_guard.py"
CANON_FILES = ("AGENTS.md", "CLAUDE.md", "greatlakes.md", "scripts/sync_rules.py")
FILE_ALLOW = ["-c", "protocol.file.allow=always"]
ZERO = "0" * 40
BEGIN = "<!-- AGENTMETARULES:BEGIN common-agents src={z} blob={z} -->\n".format(z=ZERO)
END = "<!-- AGENTMETARULES:END common-agents src={z} blob={z} -->\n".format(z=ZERO)
STATS = "docs/subagent-stats/over-15min.jsonl"


@pytest.fixture(autouse=True)
def git_env(tmp_path, monkeypatch):
    """隔离 git 配置：空的全局配置文件、不读系统配置、身份走环境变量。"""
    gcfg = tmp_path / "gitconfig"
    gcfg.write_text("")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(gcfg))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    for k, v in {
        "GIT_AUTHOR_NAME": "测试者", "GIT_AUTHOR_EMAIL": "t@example.com",
        "GIT_COMMITTER_NAME": "测试者", "GIT_COMMITTER_EMAIL": "t@example.com",
    }.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("AGENTMETARULES_URL", f"file://{tmp_path / 'canon.git'}")
    monkeypatch.delenv("AGENTMETARULES_MACHINE", raising=False)


def git(cwd, *args, check=True):
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if check and r.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} 失败：{r.stdout}{r.stderr}")
    return r.stdout.strip()


def guard(cwd, *args, stdin=None):
    r = subprocess.run([sys.executable, str(GUARD), *args], cwd=cwd, capture_output=True, text=True,
                       input=stdin, timeout=120)
    assert r.returncode == 0, r.stdout + r.stderr  # R6：退出码恒为 0
    assert "GUARD_ERROR=" not in r.stdout, r.stdout
    return r.stdout


def lines(out, key):
    return [ln for ln in out.splitlines() if ln.startswith(key + "=")]


def commit_file(repo, name, text, msg):
    p = Path(repo) / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    git(repo, "add", "--", name)
    git(repo, "commit", "-q", "-m", msg)


class World:
    def __init__(self, tmp: Path):
        self.tmp = tmp
        self.remote = tmp / "remote.git"
        # 正本
        self.canon_src = tmp / "canon-src"
        self.canon_src.mkdir()
        git(self.canon_src, "init", "-q", "-b", "main")
        for f in CANON_FILES:
            (self.canon_src / f).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(REPO / f, self.canon_src / f)
        git(self.canon_src, "add", "--", *CANON_FILES)
        git(self.canon_src, "commit", "-q", "-m", "正本初始")
        git(tmp, "init", "-q", "--bare", "--initial-branch=main", "canon.git")
        git(self.canon_src, "remote", "add", "origin", str(tmp / "canon.git"))
        git(self.canon_src, "push", "-q", "origin", "main")
        # 项目远端与种子：只有标记块、没有子模块 → fix 首次接入
        git(tmp, "init", "-q", "--bare", "--initial-branch=main", "remote.git")
        git(tmp, "clone", "-q", str(self.remote), "seed")
        seed = tmp / "seed"
        git(seed, "checkout", "-q", "-b", "main")
        (seed / "AGENTS.md").write_text("# 项目\n\n" + BEGIN + "旧版内容\n" + END + "\n项目专属尾部\n", encoding="utf-8")
        (seed / "other.txt").write_text("一\n", encoding="utf-8")
        (seed / STATS).parent.mkdir(parents=True)
        (seed / STATS).write_text("{}\n", encoding="utf-8")
        git(seed, "add", "--", "AGENTS.md", "other.txt", STATS)
        git(seed, "commit", "-q", "-m", "项目初始")
        git(seed, "push", "-q", "-u", "origin", "main")
        out = guard(seed, "fix")
        assert "RULES_SYNC=NOT_ONBOARDED" in out, out
        assert "GUARD_STEP=submodule_add" in out and "GUARD_FIX=PASS" in out and "push=done" in out, out
        self.a = self.clone("A")
        self.b = self.clone("B")

    def clone(self, name):
        git(self.tmp, *FILE_ALLOW, "clone", "-q", "--recurse-submodules", str(self.remote), name)
        return self.tmp / name

    def remote_head(self, branch="main"):
        return git(self.remote, "rev-parse", f"refs/heads/{branch}")

    def head(self, repo):
        return git(repo, "rev-parse", "HEAD")

    def b_push(self, name="other.txt", text="二\n"):
        commit_file(self.b, name, text, "B 的提交")
        git(self.b, "push", "-q")

    def canon_advance(self):
        p = self.canon_src / "AGENTS.md"
        data = p.read_text(encoding="utf-8")
        marker = "<!-- AGENTMETARULES:END common-agents -->"
        assert data.count(marker) == 1
        p.write_text(data.replace(marker, "正本新增的一行。\n" + marker), encoding="utf-8")
        git(self.canon_src, "commit", "-q", "-am", "正本前进")
        git(self.canon_src, "push", "-q", "origin", "main")
        return git(self.canon_src, "rev-parse", "HEAD")


@pytest.fixture
def w(tmp_path):
    return World(tmp_path)


def test_behind_fast_forwards(w):
    w.b_push()
    out = guard(w.a, "fix")
    assert "REPO_SYNC=BEHIND n=1" in out, out
    assert "GUARD_STEP=ff_merge" in out and "GUARD_FIX=PASS" in out, out
    assert w.head(w.a) == w.remote_head()


def test_ahead_pushes(w):
    commit_file(w.a, "a.txt", "甲\n", "A 的提交")
    out = guard(w.a, "fix")
    assert "PUSH_STATE=AHEAD n=1" in out, out
    assert "GUARD_STEP=push" in out and "GUARD_FIX=PASS" in out, out
    assert w.remote_head() == w.head(w.a)


def test_diverged_stops(w):
    commit_file(w.a, "a.txt", "甲\n", "A 的提交")
    before = w.head(w.a)
    w.b_push()
    out = guard(w.a, "fix")
    assert "REPO_SYNC=DIVERGED ahead=1 behind=1" in out, out
    assert "GUARD_FIX=STOP reason=diverged" in out, out
    assert w.head(w.a) == before and w.remote_head() != before


def test_unrelated_dirty_still_fast_forwards(w):
    (w.a / "notes.txt").write_text("未跟踪\n", encoding="utf-8")
    (w.a / STATS).write_text("{\"改\": 1}\n", encoding="utf-8")
    w.b_push()
    out = guard(w.a, "fix")
    assert "GUARD_FIX=PASS" in out, out
    assert w.head(w.a) == w.remote_head()
    assert (w.a / "notes.txt").exists() and "改" in (w.a / STATS).read_text(encoding="utf-8")


def test_dirty_blocking_fast_forward_stops(w):
    (w.a / "other.txt").write_text("本地未提交\n", encoding="utf-8")
    before = w.head(w.a)
    w.b_push()
    out = guard(w.a, "fix")
    assert "GUARD_FIX=STOP reason=ff_refused" in out, out
    assert any(ln.startswith("GIT: ") for ln in out.splitlines()), out
    assert w.head(w.a) == before
    assert (w.a / "other.txt").read_text(encoding="utf-8") == "本地未提交\n"


def test_rules_file_dirty_stops(w):
    p = w.a / "AGENTS.md"
    p.write_text(p.read_text(encoding="utf-8") + "别人的在途改动\n", encoding="utf-8")
    w.canon_advance()
    before = w.head(w.a)
    out = guard(w.a, "fix")
    assert "GUARD_FIX=STOP reason=rules_dirty" in out, out
    assert w.head(w.a) == before
    assert p.read_text(encoding="utf-8").endswith("别人的在途改动\n")


def test_no_upstream_commits_without_push(w):
    git(w.a, "checkout", "-q", "-b", "feat")
    new_canon = w.canon_advance()
    before = w.head(w.a)
    out = guard(w.a, "fix")
    assert "REPO_SYNC=NO_UPSTREAM" in out and "PUSH_STATE=EXEMPT reason=no_upstream" in out, out
    assert "RULES_SYNC=BEHIND n=1" in out, out
    assert "GUARD_FIX=PASS" in out and "push=pending_user" in out, out
    assert w.head(w.a) != before
    assert git(w.a / ".agentmetarules", "rev-parse", "HEAD") == new_canon
    msg = git(w.a, "log", "-1", "--format=%B")
    assert msg.startswith(f"docs: 规则子模块更新到 {new_canon[:7]}"), msg
    assert "SYNC_SUMMARY=PASS" in msg and "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" in msg, msg
    assert "正本新增的一行。" in (w.a / "AGENTS.md").read_text(encoding="utf-8")
    assert git(w.remote, "branch", "--list", "feat") == ""
    assert git(w.a, "status", "--porcelain") == ""


def test_sub_worktree_exempt(w):
    git(w.a, "checkout", "-q", "-b", "worktree-agent-x")
    commit_file(w.a, "a.txt", "甲\n", "子代理提交")
    w.canon_advance()
    before = w.head(w.a)
    out = guard(w.a, "fix")
    assert "PUSH_STATE=EXEMPT reason=sub_worktree" in out, out
    assert not lines(out, "GUARD_FIX") and not lines(out, "GUARD_STEP"), out
    assert w.head(w.a) == before


def test_hold_file_exempt(w):
    git_dir = Path(git(w.a, "rev-parse", "--absolute-git-dir"))
    (git_dir / "AGENTMETARULES_HOLD").write_text("freeze abc1234\n", encoding="utf-8")
    w.b_push()
    commit_file(w.a, "a.txt", "甲\n", "A 的提交")
    before = w.head(w.a)
    out = guard(w.a, "fix")
    assert "PUSH_STATE=EXEMPT reason=hold" in out, out
    assert "HOLD: freeze abc1234" in out, out
    assert not lines(out, "GUARD_FIX") and not lines(out, "GUARD_STEP"), out
    assert w.head(w.a) == before


def test_detached_stops(w):
    git(w.a, "checkout", "-q", "--detach")
    before = w.head(w.a)
    out = guard(w.a, "fix")
    assert "REPO_SYNC=DETACHED" in out, out
    assert "GUARD_FIX=STOP reason=detached" in out, out
    assert w.head(w.a) == before


def test_push_rejected_stops(w):
    hook = w.remote / "hooks" / "pre-receive"
    hook.write_text("#!/bin/sh\necho 远端拒绝 >&2\nexit 1\n", encoding="utf-8")
    hook.chmod(0o755)
    commit_file(w.a, "a.txt", "甲\n", "A 的提交")
    before_remote = w.remote_head()
    out = guard(w.a, "fix")
    assert "GUARD_FIX=STOP reason=push_rejected" in out, out
    assert "远端拒绝" in out, out
    assert w.remote_head() == before_remote


def test_include_staged_removal_single_commit(w):
    new_canon = w.canon_advance()
    git(w.a, "rm", "-r", "-q", "docs/subagent-stats")
    # 其他已暂存内容存在时停下
    commit_ready = w.a / "foreign.txt"
    commit_ready.write_text("别人暂存的\n", encoding="utf-8")
    git(w.a, "add", "--", "foreign.txt")
    out = guard(w.a, "fix", "--include-staged-removal", "docs/subagent-stats")
    assert "GUARD_FIX=STOP reason=foreign_staged" in out, out
    git(w.a, "rm", "-q", "--cached", "--", "foreign.txt")
    before = w.head(w.a)
    out = guard(w.a, "fix", "--subject-prefix", "docs:", "--include-staged-removal", "docs/subagent-stats")
    assert "GUARD_FIX=PASS" in out and "push=done" in out, out
    assert git(w.a, "rev-parse", "HEAD~1") == before  # 只多一个 commit
    names = git(w.a, "show", "--name-status", "--format=", "HEAD")
    assert f"D\t{STATS}" in names and "M\t.agentmetarules" in names and "M\tAGENTS.md" in names, names
    assert git(w.a, "log", "-1", "--format=%s").startswith(f"docs: 规则子模块更新到 {new_canon[:7]}")
    assert w.remote_head() == w.head(w.a)
    assert (w.a / "foreign.txt").exists()  # 未跟踪的别人文件原样保留


def test_post_commit_reminds_when_ahead(w):
    commit_file(w.a, "a.txt", "甲\n", "A 的提交")
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": "git add a.txt && git commit -m x"}})
    out = guard(w.a, "post-commit", stdin=payload)
    obj = json.loads(out)
    ctx = obj["hookSpecificOutput"]["additionalContext"]
    assert obj["hookSpecificOutput"]["hookEventName"] == "PostToolUse"
    assert ctx.startswith("PUSH_STATE=AHEAD n=1 branch=main"), ctx


def test_post_commit_silent_when_not_matching(w):
    commit_file(w.a, "a.txt", "甲\n", "A 的提交")  # 有未推送的 commit，但命令不匹配
    for cmd in ("ls -la", "git log | grep commit", "echo git; echo commit"):
        payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd}})
        assert guard(w.a, "post-commit", stdin=payload) == "", cmd
    payload = json.dumps({"tool_name": "Read", "tool_input": {"command": "git commit"}})
    assert guard(w.a, "post-commit", stdin=payload) == ""
    git(w.a, "push", "-q")
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": "git commit -m y"}})
    assert guard(w.a, "post-commit", stdin=payload) == ""  # 已推送：匹配也不输出


def test_behind_not_onboarded_fast_forwards_into_onboarded(w):
    """B 落后且未接入，远端已由 A 接入：一次 fix 快进后应走 --init，而不是再 submodule add。"""
    tmp = w.tmp
    git(tmp, "init", "-q", "--bare", "--initial-branch=main", "remote2.git")
    remote2 = tmp / "remote2.git"
    git(tmp, "clone", "-q", str(remote2), "seed2")
    seed = tmp / "seed2"
    git(seed, "checkout", "-q", "-b", "main")
    (seed / "AGENTS.md").write_text("# 项目\n\n" + BEGIN + "旧版内容\n" + END + "\n项目专属尾部\n", encoding="utf-8")
    git(seed, "add", "--", "AGENTS.md")
    git(seed, "commit", "-q", "-m", "项目初始")
    git(seed, "push", "-q", "-u", "origin", "main")
    a = tmp / "A2"
    b = tmp / "B2"
    git(tmp, "clone", "-q", str(remote2), "A2")
    git(tmp, "clone", "-q", str(remote2), "B2")
    # A 完成接入并推送
    out = guard(a, "fix")
    assert "RULES_SYNC=NOT_ONBOARDED" in out and "GUARD_STEP=submodule_add" in out, out
    assert "GUARD_FIX=PASS" in out and "push=done" in out, out
    remote_after_a = git(remote2, "rev-parse", "refs/heads/main")
    # B 落后、未接入
    out = guard(b, "fix")
    assert "REPO_SYNC=BEHIND n=1" in out and "RULES_SYNC=NOT_ONBOARDED" in out, out
    assert "GUARD_STEP=ff_merge" in out and "GUARD_STEP=submodule_add" not in out, out
    assert "GUARD_FIX=PASS" in out and "commit=none" in out, out
    assert git(b, "rev-parse", "HEAD") == remote_after_a  # 无多余 commit
    assert git(remote2, "rev-parse", "refs/heads/main") == remote_after_a
    assert git(b / ".agentmetarules", "rev-parse", "HEAD") == git(tmp / "canon.git", "rev-parse", "refs/heads/main")
    check = subprocess.run([sys.executable, str(b / ".agentmetarules" / "scripts" / "sync_rules.py"), "self-check"],
                           cwd=b, capture_output=True, text=True, timeout=120)
    assert "SYNC_SUMMARY=PASS" in check.stdout, check.stdout + check.stderr
    assert git(b, "status", "--porcelain") == ""
