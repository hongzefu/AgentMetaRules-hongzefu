"""sync_rules.py 自同步模式（self-check / self-apply）的端到端测试。

在临时目录里建本地 bare 正本（内容取自本仓库工作树的三份规则文件与 sync_rules.py），
项目仓库用 file:// 地址把它接成子模块 .agentmetarules，再跑子模块里的 sync_rules.py。
不访问网络、不依赖全局 git 配置。
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
CANON_FILES = ("AGENTS.md", "CLAUDE.md", "greatlakes.md", "scripts/sync_rules.py")
FILE_ALLOW = ["-c", "protocol.file.allow=always"]
ZERO = "0" * 40


def _load_sync_rules():
    spec = importlib.util.spec_from_file_location("sync_rules_under_test", REPO / "scripts" / "sync_rules.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod  # dataclass 需要能按模块名找到模块
    spec.loader.exec_module(mod)
    return mod


SR = _load_sync_rules()


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
    monkeypatch.delenv("AGENTMETARULES_MACHINE", raising=False)


def git(cwd, *args, check=True):
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if check and r.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} 失败：{r.stdout}{r.stderr}")
    return r.stdout.strip()


def run_sync(script, *args):
    return subprocess.run([sys.executable, str(script), *args], capture_output=True, text=True)


def make_canon(tmp: Path) -> Path:
    """建正本工作区 canon-src（从本仓库工作树拷贝）并推进 bare 仓库 canon.git，返回 canon-src。"""
    src = tmp / "canon-src"
    src.mkdir()
    git(src, "init", "-q", "-b", "main")
    for f in CANON_FILES:
        (src / f).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO / f, src / f)
    git(src, "add", "--", *CANON_FILES)
    git(src, "commit", "-q", "-m", "正本初始")
    git(tmp, "init", "-q", "--bare", "--initial-branch=main", "canon.git")
    git(src, "push", "-q", str(tmp / "canon.git"), "main")
    return src


def old_block_file(block: str) -> bytes:
    old = "旧版内容\n".encode()
    blob = SR.git_blob_id(old)
    return (b"# \xe9\xa1\xb9\xe7\x9b\xae\n\n" + SR.begin_marker_line(block, ZERO, blob) + b"\n" + old
            + SR.end_marker_line(block, ZERO, blob) + b"\n\n" + "项目专属尾部\n".encode())


def make_project(tmp: Path) -> Path:
    proj = tmp / "proj"
    proj.mkdir()
    git(proj, "init", "-q", "-b", "main")
    (proj / "AGENTS.md").write_bytes(old_block_file("common-agents"))
    git(proj, "add", "--", "AGENTS.md")
    git(proj, "commit", "-q", "-m", "项目初始")
    git(proj, *FILE_ALLOW, "submodule", "add", "-q", "-b", "main", f"file://{tmp / 'canon.git'}", ".agentmetarules")
    git(proj, "commit", "-q", "-m", "接入子模块")
    return proj


@pytest.fixture
def world(tmp_path):
    src = make_canon(tmp_path)
    proj = make_project(tmp_path)
    return src, proj, proj / ".agentmetarules" / "scripts" / "sync_rules.py"


def test_first_apply_writes_canon_block(world):
    src, proj, script = world
    r = run_sync(script, "self-apply", "--root", str(proj))
    assert r.returncode == SR.EXIT_OK, r.stdout + r.stderr
    assert "MODE=self" in r.stdout
    assert "SYNC_SUMMARY=PASS pass=1 fail=0 missing=0" in r.stdout
    data = (proj / "AGENTS.md").read_bytes()
    _b0, c0, c1, _e1, attrs = SR.parse_markers(data, "common-agents")
    src_data = (src / "AGENTS.md").read_bytes()
    _s0, s1, s2, _s3, _a = SR.parse_markers(src_data, "common-agents")
    canon_block = src_data[s1:s2]
    assert data[c0:c1] == canon_block  # 字节级一致
    hashed = subprocess.run(["git", "hash-object", "--stdin"], input=canon_block, capture_output=True).stdout
    assert attrs["blob"] == hashed.decode().strip()
    assert attrs["src"] == git(proj / ".agentmetarules", "rev-parse", "HEAD")
    assert data.startswith("# 项目\n\n".encode()) and data.endswith("\n\n项目专属尾部\n".encode())


def test_second_apply_is_noop(world):
    _src, proj, script = world
    assert run_sync(script, "self-apply", "--root", str(proj)).returncode == SR.EXIT_OK
    before = (proj / "AGENTS.md").read_bytes()
    r = run_sync(script, "self-apply", "--root", str(proj))
    assert r.returncode == SR.EXIT_NOOP, r.stdout + r.stderr
    assert "APPLY=NOOP" in r.stdout
    assert (proj / "AGENTS.md").read_bytes() == before
    c = run_sync(script, "self-check", "--root", str(proj))
    assert c.returncode == SR.EXIT_OK and "MODE=self" in c.stdout and "SYNC_SUMMARY=PASS" in c.stdout


def test_refuses_when_canon_is_target(world):
    src, _proj, _script = world
    for script, root in ((src / "scripts" / "sync_rules.py", src), (REPO / "scripts" / "sync_rules.py", REPO)):
        for cmd in ("self-check", "self-apply"):
            r = run_sync(script, cmd, "--root", str(root))
            assert r.returncode == SR.EXIT_FAIL, r.stdout + r.stderr
            assert "SELF_SYNC=FAIL reason=canon_is_target" in r.stdout
    # 正本源文件未被改写（BEGIN 行仍不带属性）
    assert (src / "AGENTS.md").read_bytes() == (REPO / "AGENTS.md").read_bytes()


def test_refuses_dirty_submodule_unless_allowed(world):
    _src, proj, script = world
    with open(proj / ".agentmetarules" / "README.tmp", "w", encoding="utf-8") as fh:
        fh.write("未提交的改动\n")
    r = run_sync(script, "self-apply", "--root", str(proj))
    assert r.returncode == SR.EXIT_FAIL, r.stdout + r.stderr
    assert "SELF_SYNC=FAIL reason=canon_dirty" in r.stdout
    assert b"\xe6\x97\xa7\xe7\x89\x88" in (proj / "AGENTS.md").read_bytes()  # 未写入（仍是「旧版」）
    r = run_sync(script, "self-apply", "--root", str(proj), "--allow-dirty")
    assert r.returncode == SR.EXIT_OK, r.stdout + r.stderr
    assert "SELF_SYNC=WARN reason=canon_dirty" in r.stdout
    assert "SYNC_SUMMARY=PASS" in r.stdout
    assert not os.path.exists(proj / ".agentmetarules" / ".venv")
