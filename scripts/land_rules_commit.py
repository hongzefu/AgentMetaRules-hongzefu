#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""规则文件「文件级精确」落地脚本 land_rules_commit.py

用途：把 AgentMetaRules 正本里的规则块同步进目标仓库的 AGENTS.md / CLAUDE.md / greatlakes.md 时，
做到「只动这几个文件、只动规则块」：远端侧只推一个单亲提交 RP（只快进），本地侧落一个合并提交
M=(H, RP)；全程不用临时索引建树、不 stash、不扰动他人的在途暂存与未暂存改动。

只依赖 Python 标准库 + git 命令行（按 2.43 编写），可用 `uv run --no-project python` 运行。

子命令（每步打印一行判定 `NAME=PASS|FAIL k=v`）：
  remote    B1–B6：基于 origin/<分支> 构造 RP；--push 时只做快进推送，被拒即退出 4
  merge     C0–C6：构造本地合并提交 M，持 index.lock 原子落地 ref / 索引 / 工作树并复核
  rollback  撤销一次 merge 落地（ref 旧值校验、索引写回、工作树按条件写回）
  verify    C7：M 及 M..分支 的每个提交里规则块是否仍完好

推荐编排（目标 A，本地领先 + 工作树脏）：
  1) remote（不带 --push，只在本地对象库造出 RP）
  2) merge --dry-run（C0–C3 可行性，FEASIBLE=FAIL 即停，远端不推）
  3) remote --push（同一 --date 重建出同一 RP，快进推送）
  4) merge（真落地）→ 5) 之后任意时刻 verify
目标 B 只做 1)+3)；目标 C 不走本脚本。

退出码：
  0 成功或 NOOP
  2 前置/校验失败（未写 ref、索引、工作树；remote 可能已写入无引用的对象）
  3 FEASIBLE=FAIL（在途 hunk 落在被替换区域，整个 merge 不做任何写入）
  4 PUSH=REJECTED reason=remote_advanced（远端已前进；本脚本从不加 + 或强推选项）
  5 认证/网络错误
  6 推送被远端以其他理由拒绝（hook、保护分支等）
  7 落地中途失败且已完整回滚（ROLLBACK=DONE）
  8 回滚不完整，需人工处置（ROLLBACK=PARTIAL）
  9 已落地但事后核验失败（B6 / C5 / C6），按打印的 rollback 命令处置

transform 来源（二选一）：
  --transform-cmd CMD  外部命令桩：stdin 读原文，stdout 写结果，stderr 须含一行 MODE=update|onboard|create|noop；
                       子进程可读环境变量 LAND_FILE / LAND_CANON_REV / LAND_EXISTS(1|0)。
  缺省                 导入同目录（或 --sync-rules-dir）的 sync_rules：块名/正本块/onboard 规格分别取自
                       sync-targets.json（--sync-config、--sync-target）、sync_rules.Canon、--onboard-dir，
                       详见 ModuleTransformer。
「规则块完好」一律定义为：对该内容再跑一次 transform 结果为 noop（幂等不动点）。

彩排专用环境变量（生产环境不要设置）：
  LAND_TEST_HOOK_AFTER_B4     remote：B4 通过后、B5 推前复核之前执行的 shell 命令
  LAND_TEST_HOOK_BEFORE_PUSH  remote：B5 推前复核之后、git push 之前执行的 shell 命令
  LAND_TEST_LOCK_HELD_FILE    merge：拿到 index.lock 后创建该文件，安装索引前删除
  LAND_TEST_HOLD_LOCK_MS      merge：创建/删除上面文件后各额外持锁的毫秒数
  LAND_TEST_FAIL_AT           merge：after_wt_write | after_ref_commit，在该点注入失败以演练回滚
"""

import argparse
import dataclasses
import datetime as _dt
import hashlib
import importlib
import json
import os
import re
import select
import shlex
import shutil
import stat as st_mod
import subprocess
import sys
import tempfile
import time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

EXIT_OK = 0
EXIT_FAIL = 2
EXIT_INFEASIBLE = 3
EXIT_PUSH_REJECTED = 4
EXIT_PUSH_NETWORK = 5
EXIT_PUSH_OTHER = 6
EXIT_ROLLED_BACK = 7
EXIT_ROLLBACK_PARTIAL = 8
EXIT_POSTCHECK = 9

VALID_MODES = ("update", "onboard", "create", "noop")
REGULAR_MODES = ("100644", "100755")
DIFF_KINDS = (("head", ("HEAD",)), ("cached", ("--cached",)), ("unstaged", ()))
DIFF_OPTS = ("--no-ext-diff", "--no-textconv", "--no-color", "--no-renames", "-U0")

# 这些环境变量会改变 git 的仓库发现或身份，一律剔除，身份与日期由本脚本显式给出
_STRIP_ENV = (
    "GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_COMMON_DIR", "GIT_NAMESPACE", "GIT_PREFIX",
    "GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL", "GIT_AUTHOR_DATE",
    "GIT_COMMITTER_NAME", "GIT_COMMITTER_EMAIL", "GIT_COMMITTER_DATE",
)


# ───────────────────────────── 输出与错误 ─────────────────────────────

class LandError(Exception):
    """带判定行信息的失败：name/reason 进判定行，code 决定退出码。"""

    def __init__(self, name, reason, code=EXIT_FAIL, **kv):
        super().__init__(f"{name}: {reason}")
        self.name = name
        self.reason = reason
        self.code = code
        self.kv = kv
        self.emitted = False


def _fmt(v):
    s = v if isinstance(v, str) else str(v)
    if s == "" or re.search(r"\s", s):
        return json.dumps(s, ensure_ascii=False)
    return s


def emit(name, status, **kv):
    """打印一行判定：NAME=STATUS k=v ...（立即 flush，便于 tee/Monitor 实时看到）。"""
    parts = [f"{name}={status}"] + [f"{k}={_fmt(v)}" for k, v in kv.items()]
    print(" ".join(parts), flush=True)


def emit_error(e):
    if not e.emitted:
        emit(e.name, "FAIL", reason=e.reason, **e.kv)
        e.emitted = True


def info(msg):
    print(f"# {msg}", flush=True)


def _err_line(b):
    lines = [x.strip() for x in b.decode("utf-8", "replace").splitlines() if x.strip()]
    for x in lines:
        if x.startswith(("fatal:", "error:")):
            return x[:300]
    return lines[0][:300] if lines else ""


# ───────────────────────────── git 封装 ─────────────────────────────

class Git:
    """所有 git 调用统一带 --no-optional-locks，并剔除会改变仓库发现的环境变量。"""

    def __init__(self, repo):
        self.repo = os.path.abspath(repo)
        env = {k: v for k, v in os.environ.items() if k not in _STRIP_ENV}
        env.update({"GIT_OPTIONAL_LOCKS": "0", "GIT_TERMINAL_PROMPT": "0",
                    "LC_ALL": "C", "LANGUAGE": "C"})
        self.env = env

    def run(self, *args, input=None, env=None, check=True, name="GIT"):
        full_env = dict(self.env)
        if env:
            full_env.update(env)
        p = subprocess.run(["git", "--no-optional-locks", "-C", self.repo, *args],
                           input=input, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=full_env)
        if check and p.returncode != 0:
            raise LandError(name, "git_failed", EXIT_FAIL, cmd=" ".join(str(x) for x in args[:2]),
                            rc=p.returncode, err=_err_line(p.stderr))
        return p

    def out(self, *args, **kw):
        return self.run(*args, **kw).stdout.decode("utf-8", "surrogateescape").rstrip("\n")

    def rev(self, spec, kind="commit"):
        p = self.run("rev-parse", "-q", "--verify", f"{spec}^{{{kind}}}", check=False)
        return p.stdout.decode().strip() if p.returncode == 0 else None

    def is_ancestor(self, a, b):
        p = self.run("merge-base", "--is-ancestor", a, b, check=False)
        if p.returncode in (0, 1):
            return p.returncode == 0
        raise LandError("GIT", "merge_base_failed", err=_err_line(p.stderr))

    def config(self, key, typ=None):
        args = ["config"] + ([f"--type={typ}"] if typ else []) + ["--get", key]
        p = self.run(*args, check=False)
        if p.returncode == 1:
            return None
        if p.returncode != 0:
            raise LandError("GIT", "config_failed", key=key, err=_err_line(p.stderr))
        return p.stdout.decode("utf-8", "surrogateescape").strip()

    def git_path(self, name):
        p = self.out("rev-parse", "--git-path", name)
        return p if os.path.isabs(p) else os.path.normpath(os.path.join(self.repo, p))

    def blob_at(self, rev, path):
        return self.run("cat-file", "blob", f"{rev}:{path}").stdout

    def blob(self, oid):
        return self.run("cat-file", "blob", oid).stdout

    def write_blob(self, data):
        return self.run("hash-object", "-w", "--no-filters", "--stdin", input=data).stdout.decode().strip()


# ───────────────────────────── 对象计算 ─────────────────────────────

def obj_id(kind, body, fmt):
    h = hashlib.new(fmt)
    h.update(b"%s %d\0" % (kind.encode(), len(body)))
    h.update(body)
    return h.hexdigest()


def git_blob_id(data, fmt="sha1"):
    """与 `git hash-object --no-filters` 等价的 blob id（契约同名函数的本地实现）。"""
    return obj_id("blob", data, fmt)


def ls_tree_root(g, rev):
    """解析 `git ls-tree -z <rev>`：{名字(bytes): (mode, type, oid)}，只看根目录。"""
    out = g.run("ls-tree", "-z", "--full-tree", rev).stdout
    ents = {}
    for rec in out.split(b"\0"):
        if not rec:
            continue
        meta, name = rec.split(b"\t", 1)
        mode, typ, oid = meta.decode().split(" ")
        ents[name] = (mode, typ, oid)
    return ents


def build_tree_bytes(entries):
    """按 git 树排序规则（目录名按「名字/」比较）拼出树对象正文，供不落盘地预算树 id。"""
    def key(item):
        name, (_mode, typ, _oid) = item
        return name + (b"/" if typ == "tree" else b"")
    parts = []
    for name, (mode, _typ, oid) in sorted(entries.items(), key=key):
        parts.append(mode.lstrip("0").encode() + b" " + name + b"\0" + bytes.fromhex(oid))
    return b"".join(parts)


def mktree_input(entries):
    return b"".join(f"{mode} {typ} {oid}\t".encode() + name + b"\0"
                    for name, (mode, typ, oid) in entries.items())


def parse_date(s):
    """把 --date 规范成 git 内部格式 `@<epoch> <+zzzz>`；必须显式带时区，防止同一输入得出不同 sha。"""
    s = s.strip()
    m = re.fullmatch(r"@?(\d+) ([+-])(\d{2})(\d{2})", s)
    if m:
        return f"@{int(m.group(1))} {m.group(2)}{m.group(3)}{m.group(4)}"
    try:
        d = _dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        raise LandError("ARGS", "bad_date", date=s)
    if d.tzinfo is None:
        raise LandError("ARGS", "date_needs_offset", date=s)
    mins = int(d.utcoffset().total_seconds() // 60)
    sign = "+" if mins >= 0 else "-"
    mins = abs(mins)
    return f"@{int(d.timestamp())} {sign}{mins // 60:02d}{mins % 60:02d}"


class CommitMaker:
    """作者/提交者取仓库现有 git config（经 `git var` 规范化），日期固定为 --date，禁用签名，同一输入同一 sha。"""

    def __init__(self, g, date, msg_file, fmt):
        self.g = g
        self.fmt = fmt
        self.msg_file = os.path.abspath(msg_file)
        with open(self.msg_file, "rb") as fh:
            self.msg = fh.read()
        self.env = {"GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date}
        enc = g.config("i18n.commitEncoding")
        if enc and enc.lower().replace("-", "") != "utf8":
            raise LandError("ARGS", "commit_encoding_not_utf8", value=enc)
        self.author = g.run("var", "GIT_AUTHOR_IDENT", env=self.env).stdout.rstrip(b"\n")
        self.committer = g.run("var", "GIT_COMMITTER_IDENT", env=self.env).stdout.rstrip(b"\n")

    def predict(self, tree, parents):
        body = b"tree " + tree.encode() + b"\n"
        for p in parents:
            body += b"parent " + p.encode() + b"\n"
        body += b"author " + self.author + b"\ncommitter " + self.committer + b"\n\n" + self.msg
        return obj_id("commit", body, self.fmt)

    def create(self, tree, parents):
        args = ["commit-tree", "--no-gpg-sign", tree]
        for p in parents:
            args += ["-p", p]
        args += ["-F", self.msg_file]
        return self.g.run(*args, env=self.env).stdout.decode().strip()


# ───────────────────────────── transform ─────────────────────────────

def _check_tx(f, data, out, mode):
    if mode not in VALID_MODES:
        raise LandError("TRANSFORM", "bad_mode", file=f, mode=mode)
    if not isinstance(out, (bytes, bytearray)):
        raise LandError("TRANSFORM", "bad_output_type", file=f)
    out = bytes(out)
    if mode == "noop" and out != data:
        raise LandError("TRANSFORM", "noop_but_changed", file=f)
    return out, mode


class CmdTransformer:
    """外部命令桩（同事交付 sync_rules 之前用于彩排）。"""

    kind = "cmd"

    def __init__(self, cmd, canon_rev):
        self.argv = shlex.split(cmd)
        self.canon_rev = canon_rev
        self.cache = {}

    def transform(self, f, data, exists):
        key = (f, bool(exists), hashlib.sha256(data).hexdigest())
        if key in self.cache:
            return self.cache[key]
        env = dict(os.environ)
        env.update(LAND_FILE=f, LAND_CANON_REV=self.canon_rev, LAND_EXISTS="1" if exists else "0")
        try:
            p = subprocess.run(self.argv, input=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
        except OSError as e:
            raise LandError("TRANSFORM", "cmd_not_runnable", file=f, err=str(e))
        if p.returncode != 0:
            raise LandError("TRANSFORM", "cmd_failed", file=f, rc=p.returncode, err=_err_line(p.stderr))
        modes = re.findall(rb"^MODE=([a-z]+)\s*$", p.stderr, re.M)
        if not modes:
            raise LandError("TRANSFORM", "no_mode_line", file=f)
        res = _check_tx(f, data, p.stdout, modes[-1].decode())
        self.cache[key] = res
        return res


class ModuleTransformer:
    """适配同事的 scripts/sync_rules.py（已交付，接口按其模块文档）：

      transform_bytes(data, block, canon_block, canon_rev, onboard_spec) -> (out, mode)，失败抛 SyncError
      - block        块名：--block-map 显式给出，否则取 sync-targets.json 里 --sync-target 的 files 映射，
                     再否则取 canon.files（正本文件名 -> 块名）
      - canon_block  sync_rules.Canon(cfg, canon_rev).block(块名)：`git cat-file blob <rev>:<正本文件>` 经源 lint
                     后用 parse_markers 取出的块内容（正本路径可用 --canon-repo 覆盖配置里的 canon.path）
      - onboard_spec 给了 --sync-target 时取 load_onboard_spec(--onboard-dir, 目标名, 文件名)，否则 None
    """

    kind = "module"

    def __init__(self, a):
        sync_dir = os.path.abspath(a.sync_rules_dir or SCRIPT_DIR)
        if sync_dir not in sys.path:
            sys.path.insert(0, sync_dir)
        try:
            self.sr = importlib.import_module("sync_rules")
        except ImportError as e:
            raise LandError("TRANSFORM", "sync_rules_missing", dir=sync_dir, err=str(e))
        sr = self.sr
        self.canon_rev = a.canon_rev
        try:
            cfg = sr.load_config(os.path.abspath(a.sync_config) if a.sync_config else sr.DEFAULT_TARGETS)
            if a.canon_repo:
                cfg = dataclasses.replace(cfg, canon_path=os.path.abspath(a.canon_repo))
            self.canon = sr.Canon(cfg, rev_arg=a.canon_rev)
            sha = self.canon.resolve()
            self.target = a.sync_target
            blocks = dict(cfg.target(a.sync_target).files if a.sync_target else cfg.canon_files)
        except sr.SyncError as e:
            raise LandError("TRANSFORM", e.reason, detail=e.detail[:200])
        if sha != a.canon_rev:
            raise LandError("TRANSFORM", "canon_rev_resolves_differently", canon_rev=a.canon_rev, resolved=sha)
        for item in (a.block_map or "").split(","):
            if item.strip():
                k, _, v = item.partition("=")
                blocks[k.strip()] = v.strip()
        self.blocks = blocks
        self.onboard_dir = os.path.abspath(a.onboard_dir or os.path.join(sync_dir, "onboard"))
        self._spec = {}
        self.cache = {}

    def spec(self, f):
        if not self.target:
            return None
        if f not in self._spec:
            try:
                self._spec[f] = self.sr.load_onboard_spec(self.onboard_dir, self.target, f)
            except self.sr.SyncError as e:
                raise LandError("TRANSFORM", e.reason, file=f, detail=e.detail[:200])
        return self._spec[f]

    def transform(self, f, data, exists):
        key = (f, bool(exists), hashlib.sha256(data).hexdigest())
        if key in self.cache:
            return self.cache[key]
        blk = self.blocks.get(f)
        if blk is None:
            raise LandError("TRANSFORM", "no_block_for_file", file=f)
        try:
            out, mode = self.sr.transform_bytes(data, blk, self.canon.block(blk), self.canon_rev, self.spec(f))
        except self.sr.SyncError as e:
            raise LandError("TRANSFORM", e.reason, file=f, detail=e.detail[:200])
        except LandError:
            raise
        except Exception as e:  # 同事模块抛出的其他异常也转成判定行
            raise LandError("TRANSFORM", "module_raised", file=f, err=f"{type(e).__name__}: {e}")
        res = _check_tx(f, data, out, mode)
        self.cache[key] = res
        return res


def make_transformer(a):
    if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", a.canon_rev or ""):
        raise LandError("ARGS", "canon_rev_must_be_full_hex", canon_rev=a.canon_rev)
    if a.transform_cmd:
        return CmdTransformer(a.transform_cmd, a.canon_rev)
    return ModuleTransformer(a)


def block_intact(tr, f, data):
    """规则块完好 ⇔ 再跑一次 transform 结果为 noop；transform 本身报错（如标记被删坏）也算不完好。"""
    try:
        _out, mode = tr.transform(f, data, True)
    except LandError as e:
        if e.name != "TRANSFORM":
            raise
        info(f"{f}：块完好性检查时 transform 报错 {e.reason}")
        return False
    return mode == "noop"


# ───────────────────────────── 通用小工具 ─────────────────────────────

def parse_files(s):
    files = []
    for x in (s or "").split(","):
        x = x.strip()
        if not x:
            continue
        if "/" in x or x in (".", "..") or x.startswith("-") or "\0" in x:
            raise LandError("ARGS", "only_root_level_files_supported", file=x)
        if x not in files:
            files.append(x)
    if not files:
        raise LandError("ARGS", "no_files")
    return files


def _write_file(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(data)


def _read_file(path):
    with open(path, "rb") as fh:
        return fh.read()


def _read_path(path):
    """读工作树文件；不存在返回 None；拒绝跟随符号链接。"""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except FileNotFoundError:
        return None
    try:
        return _pread_all(fd)
    finally:
        os.close(fd)


def _pread_all(fd):
    chunks, off = [], 0
    while True:
        b = os.pread(fd, 1 << 20, off)
        if not b:
            break
        chunks.append(b)
        off += len(b)
    return b"".join(chunks)


def _write_all(fd, data):
    view = memoryview(data)
    while view:
        n = os.write(fd, view)
        view = view[n:]


def _fsync_dir(d):
    fd = os.open(d, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _test_hook(var):
    cmd = os.environ.get(var)
    if not cmd:
        return
    info(f"彩排钩子 {var} 执行")
    sys.stdout.flush()
    subprocess.run(cmd, shell=True, stdout=sys.stderr, stderr=sys.stderr)


def _test_fail(point):
    if os.environ.get("LAND_TEST_FAIL_AT") == point:
        raise LandError("TEST_INJECT", "injected_failure", point=point)


def _test_sleep():
    ms = int(os.environ.get("LAND_TEST_HOLD_LOCK_MS", "0") or 0)
    if ms > 0:
        time.sleep(ms / 1000.0)


def normal_diff(old, new, workdir):
    """等价于 `diff <(旧版) <(新版)` 的 normal 格式输出（不含文件名）。"""
    fa = tempfile.NamedTemporaryFile(dir=workdir, delete=False)
    fb = tempfile.NamedTemporaryFile(dir=workdir, delete=False)
    try:
        fa.write(old); fa.close()
        fb.write(new); fb.close()
        p = subprocess.run(["diff", fa.name, fb.name], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           env={**os.environ, "LC_ALL": "C"})
        if p.returncode not in (0, 1):
            raise LandError("EXPECT_DIFF", "diff_failed", err=_err_line(p.stderr))
        return p.stdout
    finally:
        for n in (fa.name, fb.name):
            try:
                os.unlink(n)
            except FileNotFoundError:
                pass


def merge_file(g, workdir, cur, base, other):
    """`git merge-file -p <cur> <base> <other>`：返回 (输出, 冲突数)。"""
    names = []
    try:
        for tag, data in (("cur", cur), ("base", base), ("other", other)):
            fd, p = tempfile.mkstemp(prefix=f"mf_{tag}_", dir=workdir)
            with os.fdopen(fd, "wb") as fh:
                fh.write(data)
            names.append(p)
        p = subprocess.run(["git", "merge-file", "-p", *names], stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE, env=g.env)
        if p.returncode < 0 or p.returncode >= 128:
            raise LandError("MERGE_FILE", "error", rc=p.returncode, err=_err_line(p.stderr))
        return p.stdout, p.returncode
    finally:
        for n in names:
            try:
                os.unlink(n)
            except FileNotFoundError:
                pass


def parse_ls_stage(out):
    """解析 `ls-files -s -z`：{路径(bytes): [(mode, oid, stage), ...]}。"""
    ents = {}
    for rec in out.split(b"\0"):
        if not rec:
            continue
        meta, path = rec.split(b"\t", 1)
        mode, oid, stage = meta.decode().split(" ")
        ents.setdefault(path, []).append((mode, oid, stage))
    return ents


def stage0(ents, f):
    lst = ents.get(f.encode())
    if not lst:
        return None
    mode, oid, stage = lst[0]
    return (mode, oid) if stage == "0" else None


def parse_status(out):
    """解析 `status --porcelain=v1 -z --no-renames`：{路径(bytes): XY}。"""
    res = {}
    for rec in out.split(b"\0"):
        if len(rec) < 4:
            continue
        res[rec[3:]] = rec[:2].decode()
    return res


def strip_hunk_meta(b):
    return b"".join(l for l in b.splitlines(keepends=True)
                    if not (l.startswith(b"index ") or l.startswith(b"@@ ")))


# ───────────────────────────── 先比对再替换 ─────────────────────────────

def _sig(st):
    return (st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns)


def _pread_range(fd, start, end):
    chunks, off = [], start
    while off < end:
        b = os.pread(fd, min(1 << 20, end - off), off)
        if not b:
            break
        chunks.append(b)
        off += len(b)
    return b"".join(chunks)


def _snap_read(fd):
    """先 fstat 再按其 st_size 精确读前缀：对只追加的写者，i_size 以内的字节必已写完，读出的是一致快照；
    之后的追加由调用方用 fstat 的变化追平。读到的比 st_size 短（被截断）时原样返回，由调用方判为非追加改动。"""
    st = os.fstat(fd)
    chunks, off = [], 0
    while off < st.st_size:
        b = os.pread(fd, min(1 << 20, st.st_size - off), off)
        if not b:
            break
        chunks.append(b)
        off += len(b)
    return b"".join(chunks), st


def _new_tmp(d, base, data, mode_bits):
    for i in range(1000):
        tmp = os.path.join(d, f".{base}.land-{os.getpid()}-{i}.tmp")
        try:
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        except FileExistsError:
            continue
        _write_all(fd, data)
        os.fsync(fd)
        os.fchmod(fd, mode_bits)
        return tmp, fd
    raise LandError("WT_WRITE", "tmp_name_exhausted", file=base)


def careful_replace(path, full_fn, *, expected=None, progress=None, block_ok=None, settle=0.2,
                    max_recompute=3, max_rounds=5, max_catchup=5000, create_mode=0o644, label=""):
    """「先比对再替换」地改写一个工作树文件。

    full_fn(旧内容或 None) -> 新内容（None 表示无需改动）。要求 full_fn 对「末尾追加」透明：
    full_fn(X + E) == full_fn(X) + E，这样并发追加可以直接追平而不必重算；追平过的结果最后仍用
    full_fn 慢速复核一次，不透明就判失败。

    流程：读旧 inode（保留 fd）→ 算新内容 → 同目录临时文件写入 + fsync + chmod → 用旧 fd 的 fstat
    追平窗口内的追加（只写不 fsync，让「最后一次 fstat → rename」窗口尽量短）→ os.replace → fsync 新文件
    与目录 → settle 后再用旧 fd 检查有没有人写进旧 inode：有则把丢在旧 inode 的字节补进下一轮；最后重读
    确认规则块完好。progress 字典实时记录已写入的内容，供失败时回滚。
    """
    d, base = os.path.split(path)
    stats = {"rounds": 0, "catchups": 0, "recomputes": 0, "fast_path": False}
    open_fds, old_fds = [], []
    tmp = tfd = None
    prev_pre = prev_post = None
    lost = b""
    try:
        for rnd in range(1, max_rounds + 1):
            stats["rounds"] = rnd
            try:
                fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
            except FileNotFoundError:
                fd = None
            if fd is None:
                if rnd > 1:
                    raise LandError("WT_WRITE", "file_vanished", file=label)
                if expected is not None:
                    raise LandError("WT_WRITE", "file_deleted_concurrently", file=label)
                target = full_fn(None)
                if target is None:
                    return None
                tmp, tfd = _new_tmp(d, base, target, create_mode)
                try:
                    os.link(tmp, path)  # 只在目标不存在时创建，绝不覆盖同期出现的文件
                except FileExistsError:
                    raise LandError("WT_WRITE", "file_appeared_concurrently", file=label)
                os.unlink(tmp)
                tmp = None
                os.close(tfd)
                tfd = None
                if progress is not None:
                    progress.update(created=True, pre=None, post=target, lost=b"")
                _fsync_dir(d)
                time.sleep(settle)
                live = _read_path(path)
                if live is None or not live.startswith(target):
                    raise LandError("WT_WRITE", "live_changed_after_write", file=label)
                if block_ok is not None and not block_ok(live):
                    raise LandError("WT_WRITE", "block_broken_after_write", file=label)
                stats.update(created=True, pre=None, post=target, tail=len(live) - len(target))
                return stats
            open_fds.append(fd)
            cur, st = _snap_read(fd)
            if not st_mod.S_ISREG(st.st_mode):
                raise LandError("WT_WRITE", "not_regular_file", file=label)
            if rnd == 1:
                if expected is not None and cur != expected:
                    stats["recomputes"] += 1  # 与 C2 所见不同 → 重算
                pre = cur
                post = full_fn(pre)
                if post is None or post == pre:
                    return None
            else:
                if not cur.startswith(prev_post):
                    raise LandError("WT_WRITE", "live_changed_non_append", file=label)
                tail = cur[len(prev_post):]
                pre = prev_pre + lost + tail
                post = prev_post + lost + tail
                stats["fast_path"] = True
            known = bytearray(cur)
            pre, post = bytearray(pre), bytearray(post)  # 追平时原地 += ，避免每次整份拷贝
            tmp, tfd = _new_tmp(d, base, bytes(post), st_mod.S_IMODE(st.st_mode))
            while True:  # 追平：用旧 fd 的 fstat 判断读后是否又有人写
                s_now = os.fstat(fd)
                if _sig(s_now) == _sig(st):
                    break
                stats["catchups"] += 1
                if stats["catchups"] > max_catchup:
                    raise LandError("WT_WRITE", "too_many_catchups", file=label)
                if s_now.st_size >= len(known):
                    # 只读增量（O(增量)）；前缀若被原地改写，替换后对旧 inode 的整读复核会发现并判失败
                    extra = _pread_range(fd, len(known), s_now.st_size)
                    known += extra
                    pre += extra
                    post += extra
                    st = s_now
                    _write_all(tfd, extra)  # 追平阶段不 fsync，缩短「最后一次 fstat → rename」窗口；替换后再 fsync
                    stats["fast_path"] = True
                    continue
                else:
                    cur2, st2 = _snap_read(fd)
                    if rnd > 1:
                        raise LandError("WT_WRITE", "live_changed_non_append", file=label)
                    stats["recomputes"] += 1
                    if stats["recomputes"] > max_recompute:
                        raise LandError("WT_WRITE", "too_many_recomputes", file=label)
                    pre = bytearray(cur2)
                    post = full_fn(cur2)
                    post = bytearray(cur2 if post is None else post)
                    os.ftruncate(tfd, 0)
                    os.lseek(tfd, 0, os.SEEK_SET)
                    _write_all(tfd, bytes(post))
                    known, st = bytearray(cur2), st2
            known, pre, post = bytes(known), bytes(pre), bytes(post)
            if stats["recomputes"] > max_recompute:
                raise LandError("WT_WRITE", "too_many_recomputes", file=label)
            os.replace(tmp, path)
            tmp = None
            if progress is not None:
                progress.update(created=False, pre=pre, post=post, lost=b"")
            os.fsync(tfd)  # 覆盖追平阶段补写的字节
            os.close(tfd)
            tfd = None
            _fsync_dir(d)
            old_fds.append([fd, len(known)])
            time.sleep(settle)
            now_old, _ = _snap_read(fd)
            if not now_old.startswith(known):
                raise LandError("WT_WRITE", "old_inode_rewritten", file=label)
            lost = now_old[len(known):]
            old_fds[-1][1] = len(now_old)
            if lost:  # 窗口内有人写进了旧 inode：把这些字节补进下一轮
                if progress is not None:
                    progress["lost"] = lost
                info(f"{label}：替换窗口内有 {len(lost)} 字节写进旧 inode，进入第 {rnd + 1} 轮补写")
                prev_pre, prev_post = pre, post
                continue
            live = _read_path(path)
            if live is None or not live.startswith(post):
                raise LandError("WT_WRITE", "live_changed_after_write", file=label)
            if stats["fast_path"] and full_fn(pre) != post:
                raise LandError("WT_WRITE", "append_not_transparent", file=label)
            if block_ok is not None and not block_ok(live):
                raise LandError("WT_WRITE", "block_broken_after_write", file=label)
            for ofd, olen in old_fds:
                if os.fstat(ofd).st_size != olen:
                    raise LandError("WT_WRITE", "late_write_to_old_inode", file=label)
            stats.update(created=False, pre=pre, post=post, tail=len(live) - len(post))
            return stats
        raise LandError("WT_WRITE", "too_many_rounds", file=label)
    finally:
        if tfd is not None:
            os.close(tfd)
        if tmp is not None:
            try:
                os.unlink(tmp)
            except FileNotFoundError:
                pass
        for fd in open_fds:
            try:
                os.close(fd)
            except OSError:
                pass


def restore_file(path, rec, settle, label):
    """把我们写过的工作树文件恢复为落地前的逻辑内容。

    只在当前内容仍以「我们写入的内容」为前缀（其后只可能是别人新追加的字节）时恢复：
    恢复结果 = 落地前内容 + 窗口内丢进旧 inode 的字节 + 当前尾部追加。否则跳过并报告。
    返回 restored / removed / untouched / skip:<原因>。
    """
    if not rec or rec.get("post") is None:
        return "untouched"
    post = rec["post"]
    live = _read_path(path)
    if rec.get("created"):
        if live is None:
            return "skip:missing"
        if live != post:
            return "skip:changed_since_write"
        d, base = os.path.split(path)
        trash = os.path.join(d, f".{base}.land-removed-{os.getpid()}")
        os.rename(path, trash)
        _fsync_dir(d)
        if _read_file(trash) != post:  # 极端竞态：改名瞬间被写，放回原处交人工
            os.rename(trash, path)
            return "skip:changed_during_remove"
        os.unlink(trash)
        return "removed"
    if live is None or not live.startswith(post):
        return "skip:changed_since_write"
    base_pre = rec["pre"] + (rec.get("lost") or b"")

    def fn(cur):
        if cur is None or not cur.startswith(post):
            raise LandError("ROLLBACK_WT", "changed_since_write", file=label)
        return base_pre + cur[len(post):]

    careful_replace(path, fn, settle=settle, label=label)
    return "restored"


# ───────────────────────────── 锁与引用事务 ─────────────────────────────

class IndexLock:
    """与 git 相同的 `<index>.lock` 协议：O_CREAT|O_EXCL 取锁；绝不删除不是自己创建的锁。"""

    def __init__(self, lock_path, index_path):
        self.path = lock_path
        self.index_path = index_path
        self.fd = None
        self.ino = None
        self.installed = False

    def acquire(self, retries=20, interval=0.5):
        attempt = 0
        while True:
            attempt += 1
            try:
                fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o666)
            except FileExistsError:
                if attempt > retries:
                    raise LandError("INDEX_LOCK", "busy", attempts=attempt, lock=self.path)
                time.sleep(interval)
                continue
            self.fd = fd
            self.ino = os.fstat(fd).st_ino
            return attempt

    def install(self, data):
        """把索引副本写进我们持有的锁文件，fsync 后 rename 成 index（git 自己的落盘方式）。"""
        try:
            os.fchmod(self.fd, st_mod.S_IMODE(os.stat(self.index_path).st_mode))
        except FileNotFoundError:
            pass
        _write_all(self.fd, data)
        os.fsync(self.fd)
        os.rename(self.path, self.index_path)
        self.installed = True
        os.close(self.fd)
        self.fd = None
        _fsync_dir(os.path.dirname(self.index_path))

    def release(self):
        if self.fd is None or self.installed:
            return "not_held"
        try:
            cur = os.stat(self.path)
        except FileNotFoundError:
            cur = None
        released = "gone"
        if cur is not None and cur.st_ino == self.ino:
            os.unlink(self.path)
            released = "released"
        os.close(self.fd)
        self.fd = None
        return released


class RefTxn:
    """`git update-ref --stdin` 事务：start / update <ref> <new> <old> / prepare / commit|abort。"""

    def __init__(self, g, reflog_msg, timeout=60):
        self.timeout = timeout
        self.p = subprocess.Popen(
            ["git", "--no-optional-locks", "-C", g.repo, "update-ref", "-m", reflog_msg, "--stdin"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=g.env, bufsize=0)
        self.state = "new"

    def _cmd(self, line, expect):
        try:
            self.p.stdin.write(line.encode() + b"\n")
            self.p.stdin.flush()
        except BrokenPipeError:
            raise LandError("REF_TXN", "git_exited", cmd=line.split(" ")[0], err=self._stderr())
        if expect is None:
            return
        r, _, _ = select.select([self.p.stdout], [], [], self.timeout)
        resp = self.p.stdout.readline().decode().strip() if r else "<timeout>"
        if resp != expect:
            raise LandError("REF_TXN", "unexpected_reply", cmd=line.split(" ")[0], got=resp or "<eof>",
                            err=self._stderr())

    def _stderr(self):
        try:
            if self.p.poll() is None:
                self.p.stdin.close()
                self.p.wait(timeout=5)
            return _err_line(self.p.stderr.read())
        except Exception:
            return ""

    def start(self):
        self._cmd("start", "start: ok")
        self.state = "started"

    def update(self, ref, new, old):
        self._cmd(f"update {ref} {new} {old}", None)

    def prepare(self):
        self._cmd("prepare", "prepare: ok")
        self.state = "prepared"

    def commit(self):
        self._cmd("commit", "commit: ok")
        self.state = "committed"
        self._close()

    def abort(self):
        if self.state in ("new", "started", "prepared") and self.p.poll() is None:
            try:
                self._cmd("abort", "abort: ok")
            except LandError:
                pass
        self.state = "aborted"
        self._close()

    def _close(self):
        try:
            self.p.stdin.close()
        except Exception:
            pass
        try:
            self.p.wait(timeout=10)
        except Exception:
            self.p.kill()


# ───────────────────────────── remote（B1–B6） ─────────────────────────────

PUSH_QUIET = ("-c", "advice.pushUpdateRejected=false", "-c", "advice.pushNonFFCurrent=false",
              "-c", "advice.pushNonFFMatching=false", "-c", "advice.pushFetchFirst=false",
              "-c", "advice.pushAlreadyExists=false")


def ls_remote(g, ref, name="LS_REMOTE"):
    p = g.run("ls-remote", "origin", ref, check=False)
    if p.returncode != 0:
        raise LandError(name, "auth_or_network", EXIT_PUSH_NETWORK, err=_err_line(p.stderr))
    for line in p.stdout.decode().splitlines():
        parts = line.split("\t")
        if len(parts) == 2 and parts[1] == ref:
            return parts[0]
    return None


def cmd_remote(a):
    g = Git(a.repo_path)
    files = parse_files(a.files)
    tr = make_transformer(a)
    fmt = g.out("rev-parse", "--show-object-format")
    cm = CommitMaker(g, parse_date(a.date), a.message_file, fmt)
    br = a.branch
    head_ref = f"refs/heads/{br}"
    track = f"refs/remotes/origin/{br}"
    if (g.config("remote.origin.mirror", "bool") or "false") == "true":
        raise LandError("REMOTE_BASE", "origin_is_mirror")
    if a.dry_run and a.push:
        info("--dry-run 下忽略 --push")

    # B1：取远端基点 O
    prev = g.rev(track)
    p = g.run("fetch", "-q", "--no-tags", "origin", head_ref, check=False)
    if p.returncode != 0:
        raise LandError("REMOTE_BASE", "fetch_failed", EXIT_PUSH_NETWORK, err=_err_line(p.stderr))
    O = g.rev(track)
    lr = ls_remote(g, head_ref, "REMOTE_BASE")
    if O is None:
        raise LandError("REMOTE_BASE", "no_tracking_ref", ref=track)
    if lr != O:
        raise LandError("REMOTE_BASE", "tracking_ne_ls_remote", O=O, ls_remote=lr or "none")
    ff = "none"
    if prev is not None:
        if not g.is_ancestor(prev, O):
            raise LandError("REMOTE_BASE", "tracking_ref_not_fast_forward", prev=prev, O=O, ff_from_prev=0)
        ff = "1"
    emit("REMOTE_BASE", "PASS", O=O, ls_remote=lr, ff_from_prev=ff)

    # B2：逐文件 transform
    root = ls_tree_root(g, O)
    work = tempfile.mkdtemp(prefix="land_remote_")
    results = []
    try:
        for f in files:
            ent = root.get(f.encode())
            if ent is None:
                data, exists = b"", False
            else:
                mode, typ, _oid = ent
                if typ != "blob" or mode not in REGULAR_MODES:
                    raise LandError("TRANSFORM", "not_regular_blob", file=f, mode=mode, type=typ)
                data, exists = g.blob_at(O, f), True
            out, mode_tx = tr.transform(f, data, exists)
            if not exists and mode_tx not in ("create", "noop"):
                raise LandError("TRANSFORM", "missing_file_but_not_create", file=f, mode=mode_tx)
            changed = out != data
            out_oid = git_blob_id(out, fmt)
            emit("TRANSFORM", "PASS", file=f, mode=mode_tx, exists=int(exists), changed=int(changed),
                 in_blob=ent[2] if ent else "none", out_blob=out_oid)
            if a.emit_diff_dir or a.expect_diff_dir:
                dd = normal_diff(data, out, work)
                if a.emit_diff_dir:
                    dst = os.path.join(a.emit_diff_dir, f + ".diff")
                    _write_file(dst, dd)
                    emit("EMIT_DIFF", "DONE", file=f, path=dst, bytes=len(dd))
                if a.expect_diff_dir:
                    exp_path = os.path.join(a.expect_diff_dir, f + ".diff")
                    if not os.path.exists(exp_path):
                        raise LandError("EXPECT_DIFF", "review_file_missing", file=f, path=exp_path)
                    if _read_file(exp_path) != dd:
                        raise LandError("EXPECT_DIFF", "differs_from_review", file=f, path=exp_path)
                    emit("EXPECT_DIFF", "PASS", file=f)
            results.append((f, ent, out, out_oid, changed, mode_tx))
    finally:
        shutil.rmtree(work, ignore_errors=True)

    changed = [r for r in results if r[4]]
    if not changed:
        emit("REMOTE_COMMIT", "NOOP", O=O, files=0)
        if a.push and not a.dry_run:
            emit("PUSH", "SKIP", reason="noop")
        print(f"RP={O}", flush=True)
        return EXIT_OK

    # B3：写 blob、mktree、commit-tree（dry-run 只在内存里算 id，不写任何对象）
    new_root = dict(root)
    for f, ent, _out, oid, _c, _m in changed:
        new_root[f.encode()] = (ent[0] if ent else "100644", "blob", oid)
    T = obj_id("tree", build_tree_bytes(new_root), fmt)
    RP = cm.predict(T, [O])
    if a.dry_run:
        emit("REMOTE_COMMIT", "PASS", dry_run=1, O=O, RP=RP, tree=T, files=len(changed), other_paths=0)
        print(f"RP={RP}", flush=True)
        return EXIT_OK
    for f, _ent, out, oid, _c, _m in changed:
        w = g.write_blob(out)
        if w != oid:
            raise LandError("REMOTE_COMMIT", "blob_id_mismatch", file=f, expect=oid, got=w)
    T2 = g.run("mktree", "-z", input=mktree_input(new_root)).stdout.decode().strip()
    if T2 != T:
        raise LandError("REMOTE_COMMIT", "tree_id_mismatch", expect=T, got=T2)
    RP2 = cm.create(T, [O])
    if RP2 != RP:
        raise LandError("REMOTE_COMMIT", "commit_id_mismatch", expect=RP, got=RP2)

    # B4：只改了这几个文件、只多一个提交
    ns = g.out("diff-tree", "-r", "--no-renames", "--name-status", O, RP).splitlines()
    got = {}
    for line in ns:
        st, _, path = line.partition("\t")
        got[path] = st
    want = {f: ("A" if ent is None else "M") for f, ent, *_ in changed}
    other = sorted(set(got) - set(want))
    if len(ns) != len(changed) or got != want:
        raise LandError("REMOTE_COMMIT", "unexpected_paths", got=",".join(sorted(got)) or "none",
                        other_paths=len(other))
    cnt = g.out("rev-list", "--count", f"{O}..{RP}")
    if cnt != "1":
        raise LandError("REMOTE_COMMIT", "commit_count_ne_1", count=cnt)
    emit("REMOTE_COMMIT", "PASS", O=O, RP=RP, files=len(changed), other_paths=0,
         paths=",".join(f"{got[f]}:{f}" for f in want))

    if not a.push:
        emit("PUSH", "SKIP", reason="no_push_flag")
        print(f"RP={RP}", flush=True)
        return EXIT_OK

    # B5：推前复核 + 只快进推送
    _test_hook("LAND_TEST_HOOK_AFTER_B4")
    lr2 = ls_remote(g, head_ref, "PUSH")
    if lr2 != O:
        emit("PUSH", "REJECTED", reason="remote_advanced", stage="precheck", O=O, ls_remote=lr2 or "none")
        return EXIT_PUSH_REJECTED
    _test_hook("LAND_TEST_HOOK_BEFORE_PUSH")
    p = g.run(*PUSH_QUIET, "push", "--porcelain", "--no-follow-tags", "origin", f"{RP}:{head_ref}", check=False)
    ref_line = None
    for line in p.stdout.decode("utf-8", "replace").splitlines():
        parts = line.split("\t")
        if len(parts) >= 3 and parts[1].endswith(":" + head_ref):
            ref_line = parts
    if ref_line is None:
        emit("PUSH", "FAIL", reason="auth_or_network", rc=p.returncode, err=_err_line(p.stderr))
        return EXIT_PUSH_NETWORK
    flag, summary = ref_line[0], ref_line[2]
    if flag == "!":
        if "[rejected]" in summary and any(k in summary for k in ("non-fast-forward", "fetch first", "stale info")):
            emit("PUSH", "REJECTED", reason="remote_advanced", stage="push", detail=summary)
            return EXIT_PUSH_REJECTED
        emit("PUSH", "FAIL", reason="remote_rejected", detail=summary)
        return EXIT_PUSH_OTHER
    if flag not in (" ", "="):
        emit("PUSH", "FAIL", reason="unexpected_push_flag", flag=repr(flag), detail=summary)
        return EXIT_POSTCHECK
    emit("PUSH", "PASS", ref=head_ref, summary=summary)

    # B6：远端与跟踪引用都等于 RP
    lr3 = ls_remote(g, head_ref, "REMOTE_POST")
    tr3 = g.rev(track)
    if lr3 != RP or tr3 != RP:
        emit("REMOTE_POST", "FAIL", ls_remote=lr3 or "none", tracking=tr3 or "none", RP=RP)
        print(f"RP={RP}", flush=True)
        return EXIT_POSTCHECK
    emit("REMOTE_POST", "PASS", ls_remote=lr3, tracking=tr3)
    print(f"RP={RP}", flush=True)
    return EXIT_OK


# ───────────────────────────── merge（C0–C6） ─────────────────────────────

class FilePlan:
    def __init__(self, f):
        self.f = f
        self.h_ent = None      # (mode, type, oid) 或 None
        self.h_bytes = None
        self.th = b""
        self.th_mode = "noop"
        self.th_oid = None
        self.th_changed = False
        self.idx_seen = None   # (mode, oid) 或 None
        self.wt_seen = None    # C1 备份内容；None 表示工作树无此文件

    @property
    def h_oid(self):
        return self.h_ent[2] if self.h_ent else None


def feasible_target(ctx, pl, x, where):
    """在途内容 X 的目标 = T(X)，并用 `git merge-file -p X H T(H)` 交叉验证。"""
    try:
        tx, _mode = ctx.tr.transform(pl.f, x, True)
    except LandError as e:
        raise LandError("FEASIBLE", "transform_failed", EXIT_INFEASIBLE, file=pl.f, where=where, err=e.reason)
    merged, conflicts = merge_file(ctx.g, ctx.work, x, pl.h_bytes if pl.h_bytes is not None else b"", pl.th)
    if conflicts != 0 or merged != tx:
        raise LandError("FEASIBLE", "hunk_in_region", EXIT_INFEASIBLE, file=pl.f, where=where,
                        merge_conflicts=conflicts, merge_equals_tx=int(merged == tx))
    return tx


def index_target(ctx, pl, seen):
    """返回 (mode, oid, bytes, kind, src)；无需改动时 oid == seen oid。"""
    if seen is None:
        if pl.h_bytes is not None:
            raise LandError("FEASIBLE", "staged_delete", EXIT_INFEASIBLE, file=pl.f, where="index")
        if not pl.th_changed:
            return None
        return ("100644", pl.th_oid, pl.th, "absent", None)
    mode, oid = seen
    if pl.h_oid is not None and oid == pl.h_oid:
        return (mode, pl.th_oid, pl.th, "same_as_head", pl.h_bytes)
    src = ctx.g.blob(oid)
    tx = feasible_target(ctx, pl, src, "index")
    return (mode, git_blob_id(tx, ctx.fmt), tx, "in_flight", src)


def make_wt_fn(ctx, pl):
    def fn(content):
        if content is None:
            if pl.h_bytes is not None:
                raise LandError("FEASIBLE", "worktree_deleted", EXIT_INFEASIBLE, file=pl.f, where="worktree")
            return pl.th if pl.th_changed else None
        if pl.h_bytes is not None and content == pl.h_bytes:
            return pl.th
        return feasible_target(ctx, pl, content, "worktree")
    return fn


def wt_kind(pl, content):
    if content is None:
        return "absent"
    return "same_as_head" if content == pl.h_bytes else "in_flight"


class Ctx:
    pass


def take_snapshot(g, files, outdir, prefix):
    snap = {
        "status": g.run("status", "--porcelain=v1", "-z", "--untracked-files=no", "--no-renames").stdout,
        "lsfiles": g.run("ls-files", "-s", "-z", "--", *files).stdout,
    }
    for kind, extra in DIFF_KINDS:
        snap["diff_" + kind] = g.run("diff", *DIFF_OPTS, *extra, "--", *files).stdout
    for k, v in snap.items():
        _write_file(os.path.join(outdir, f"{prefix}_{k}.bin"), v)
    return snap


def load_snapshot(outdir, prefix):
    snap = {}
    for k in ("status", "lsfiles", "diff_head", "diff_cached", "diff_unstaged"):
        snap[k] = _read_file(os.path.join(outdir, f"{prefix}_{k}.bin"))
    return snap


def diff_body(g, a, b, workdir):
    """内容级 -U0 diff 的 hunk 正文（只保留 @@ 之后的 +/-/\\ 行），用于同期改动时的虚拟比对。"""
    if a == b:
        return b""
    names = []
    try:
        for tag, data in (("a", a), ("b", b)):
            if data is None:
                names.append(os.devnull)
                continue
            fd, p = tempfile.mkstemp(prefix=f"vd_{tag}_", dir=workdir)
            with os.fdopen(fd, "wb") as fh:
                fh.write(data)
            names.append(p)
        p = subprocess.run(["git", "diff", "--no-index", *DIFF_OPTS, *names], stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE, env=g.env)
        if p.returncode not in (0, 1):
            raise LandError("HUNKSET_EQUAL", "no_index_diff_failed", err=_err_line(p.stderr))
    finally:
        for n in names:
            if n != os.devnull:
                try:
                    os.unlink(n)
                except FileNotFoundError:
                    pass
    body, in_hunk = [], False
    for l in p.stdout.splitlines(keepends=True):
        if l.startswith(b"@@ "):
            in_hunk = True
            continue
        if l.startswith(b"diff --git "):
            in_hunk = False
            continue
        if in_hunk and l[:1] in (b"+", b"-", b"\\"):
            body.append(l)
    return b"".join(body)


def _xy(h, i, w):
    """由 (HEAD, 索引, 工作树) 三者的 oid 推出 porcelain v1 的 XY（-uno 口径）；两位都空返回 None。"""
    if h == i:
        x = " "
    elif h is None:
        x = "A"
    elif i is None:
        x = "D"
    else:
        x = "M"
    if i is None or i == w:
        y = " "
    elif w is None:
        y = "D"
    else:
        y = "M"
    xy = x + y
    return None if xy == "  " else xy


def compare_states(ctx, files, before, after, virtual=None):
    """C5：逐类比对 hunk 集合与 status。virtual 给出时，严格比对不等再按「同期新动作」做虚拟比对。"""
    ok = True
    for kind, _extra in DIFF_KINDS:
        b = strip_hunk_meta(before["diff_" + kind])
        a = strip_hunk_meta(after["diff_" + kind])
        if a == b:
            emit("HUNKSET_EQUAL", "PASS", kind=kind, basis="snapshot")
            continue
        vr = virtual.hunks_equal(kind) if virtual else (False, "no_virtual")
        if vr[0]:
            emit("HUNKSET_EQUAL", "PASS", kind=kind, basis="virtual", note="同期有新动作，按落地时实际源内容复核")
        else:
            emit("HUNKSET_EQUAL", "FAIL", kind=kind, reason=vr[1])
            ok = False
    bs, as_ = parse_status(before["status"]), parse_status(after["status"])
    bad, virt = [], 0
    for f in files:
        k = f.encode()
        if bs.get(k) == as_.get(k):
            continue
        if virtual and virtual.status_xy(f) == as_.get(k):
            virt += 1
            continue
        bad.append(f"{f}:{bs.get(k) or '--'}->{as_.get(k) or '--'}")
    news = []
    for pth in sorted((set(bs) | set(as_)) - {f.encode() for f in files}):
        if bs.get(pth) != as_.get(pth):
            news.append(pth)
            emit("STATUS_NEW_ACTIVITY", "INFO", path=pth.decode("utf-8", "replace"),
                 before=bs.get(pth) or "clean", after=as_.get(pth) or "clean")
    if bad:
        emit("STATUS_EQUAL", "FAIL", files=";".join(bad))
        ok = False
    else:
        emit("STATUS_EQUAL", "PASS", rule_files=len(files), virtual=virt, new_activity=len(news))
    return ok


class Virtual:
    """同期新动作存在时的虚拟基线：落地前等价状态 =（H，锁内所见索引，落地源内容 + 之后的追加尾巴）。"""

    def __init__(self, ctx, plans, idx_info, wt_recs):
        self.ctx = ctx
        self.views = {}
        g = ctx.g
        cur = parse_ls_stage(g.run("ls-files", "-s", "-z", "--", *plans).stdout)
        for f, pl in plans.items():
            v = {"err": None}
            v["h"] = pl.h_bytes
            v["m"] = pl.th if pl.th_changed else pl.h_bytes
            now = stage0(cur, f)
            info_f = idx_info.get(f) or {}
            if (list(now) if now else None) != info_f.get("after"):
                v["err"] = "index_changed_after_install"
            v["idx_now"] = g.blob(now[1]) if now else None
            v["idx_before"] = info_f.get("src")
            wt_now = _read_path(os.path.join(ctx.top, f))
            v["wt_now"] = wt_now
            rec = wt_recs.get(f)
            if not rec:
                v["wt_before"] = wt_now
            elif rec.get("created"):
                if wt_now != rec["post"]:
                    v["err"] = v["err"] or "created_file_changed"
                v["wt_before"] = None
            elif wt_now is None or not wt_now.startswith(rec["post"]):
                v["err"] = v["err"] or "worktree_changed_non_append"
                v["wt_before"] = wt_now
            else:
                v["wt_before"] = rec["pre"] + (rec.get("lost") or b"") + wt_now[len(rec["post"]):]
            self.views[f] = v

    def hunks_equal(self, kind):
        g, work = self.ctx.g, self.ctx.work
        for f, v in self.views.items():
            if v["err"]:
                return False, f"{f}:{v['err']}"
            if kind == "head":
                pb, pa = (v["h"], v["wt_before"]), (v["m"], v["wt_now"])
            elif kind == "cached":
                pb, pa = (v["h"], v["idx_before"]), (v["m"], v["idx_now"])
            else:
                pb, pa = (v["idx_before"], v["wt_before"]), (v["idx_now"], v["wt_now"])
            if diff_body(g, *pb, work) != diff_body(g, *pa, work):
                return False, f"{f}:virtual_hunks_differ"
        return True, ""

    def status_xy(self, f):
        v = self.views[f]
        if v["err"]:
            return "<err>"
        fmt = self.ctx.fmt
        oid = (lambda b: None if b is None else git_blob_id(b, fmt))
        return _xy(oid(v["h"]), oid(v["idx_before"]), oid(v["wt_before"]))


def _seq_state(g):
    for name in ("MERGE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD", "rebase-merge", "rebase-apply", "BISECT_LOG"):
        if os.path.exists(g.git_path(name)):
            return name
    return None


def _local_prechecks(ctx, br, name="LOCAL_PRE"):
    g, files = ctx.g, ctx.files
    head = g.run("symbolic-ref", "-q", "HEAD", check=False).stdout.decode().strip()
    if head != f"refs/heads/{br}":
        raise LandError(name, "head_not_on_branch", head=head or "detached", branch=br)
    ents = parse_ls_stage(g.run("ls-files", "-s", "-z", "--", *files).stdout)
    for f in files:
        lst = ents.get(f.encode(), [])
        if len(lst) > 1 or any(s != "0" for _m, _o, s in lst):
            raise LandError(name, "unmerged_entry", file=f)
    for rec in g.run("ls-files", "-v", "-z", "--", *files).stdout.split(b"\0"):
        if rec and rec[:1] != b"H":
            raise LandError(name, "index_flag_not_H", entry=rec.decode("utf-8", "replace"))
    if os.path.exists(ctx.lock_path):
        raise LandError(name, "index_lock_exists", lock=ctx.lock_path)
    if (g.config("core.splitIndex", "bool") or "false") == "true":
        raise LandError(name, "split_index_enabled")
    attrs = g.out("check-attr", "-a", "--", *files)
    if attrs.strip():
        raise LandError(name, "attributes_present", attrs=attrs.replace("\n", ";"))
    if (g.config("core.autocrlf") or "false").lower() == "true":
        raise LandError(name, "autocrlf_true")
    seq = _seq_state(g)
    if seq:
        raise LandError(name, "operation_in_progress", state=seq)
    return ents


def _ctx_common(a, need_msg=True):
    ctx = Ctx()
    g0 = Git(a.repo_path)
    top = g0.out("rev-parse", "--show-toplevel")
    ctx.g = Git(top)
    ctx.top = top
    ctx.files = parse_files(a.files)
    ctx.fmt = ctx.g.out("rev-parse", "--show-object-format")
    ctx.lock_path = ctx.g.git_path("index.lock")
    ctx.index_path = ctx.g.git_path("index")
    return ctx


def cmd_merge(a):
    ctx = _ctx_common(a)
    g, files = ctx.g, ctx.files
    ctx.tr = make_transformer(a)
    cm = CommitMaker(g, parse_date(a.date), a.message_file, ctx.fmt)
    br = a.branch
    ref = f"refs/heads/{br}"
    snap = os.path.abspath(a.snapshot_dir or tempfile.mkdtemp(prefix="land_rules_merge_"))
    os.makedirs(snap, exist_ok=True)
    ctx.work = os.path.join(snap, "work")
    os.makedirs(ctx.work, exist_ok=True)
    print(f"SNAPSHOT_DIR={snap}", flush=True)
    settle = a.settle_ms / 1000.0

    # C0：前置检查
    H = g.rev(ref)
    RP = g.rev(a.rp)
    if H is None or RP is None:
        raise LandError("LOCAL_PRE", "rev_missing", H=H or "none", RP=RP or "none")
    parents = g.out("rev-list", "--parents", "-n", "1", RP).split()[1:]
    if not parents:
        raise LandError("LOCAL_PRE", "rp_has_no_parent", RP=RP)
    O = parents[0]
    if not g.is_ancestor(O, H):
        raise LandError("LOCAL_PRE", "O_not_ancestor_of_H", O=O, H=H)
    idx_ents = _local_prechecks(ctx, br)
    h_root = ls_tree_root(g, H)
    plans = {}
    for f in files:
        pl = FilePlan(f)
        ent = h_root.get(f.encode())
        if ent is not None and (ent[1] != "blob" or ent[0] not in REGULAR_MODES):
            raise LandError("LOCAL_PRE", "head_entry_not_regular", file=f, mode=ent[0])
        pl.h_ent = ent
        pl.idx_seen = stage0(idx_ents, f)
        path = os.path.join(ctx.top, f)
        try:
            lst = os.lstat(path)
            if not st_mod.S_ISREG(lst.st_mode):
                raise LandError("LOCAL_PRE", "worktree_not_regular_file", file=f)
            if ent is None and pl.idx_seen is None:
                raise LandError("LOCAL_PRE", "untracked_file_in_the_way", file=f)
        except FileNotFoundError:
            pass
        plans[f] = pl
    emit("LOCAL_PRE", "PASS", branch=br, H=H, O=O, RP=RP)

    # T(H)
    for f, pl in plans.items():
        pl.h_bytes = g.blob_at(H, f) if pl.h_ent else None
        pl.th, pl.th_mode = ctx.tr.transform(f, pl.h_bytes if pl.h_bytes is not None else b"", pl.h_ent is not None)
        pl.th_changed = pl.th != (pl.h_bytes if pl.h_bytes is not None else b"")
        pl.th_oid = git_blob_id(pl.th, ctx.fmt)

    # RP 已并入 H：幂等 NOOP
    if g.is_ancestor(RP, H):
        diff = [f for f, pl in plans.items() if pl.th_changed]
        if diff:
            raise LandError("LOCAL_COMMIT", "rp_merged_but_blocks_differ", files=",".join(diff))
        emit("LOCAL_COMMIT", "NOOP", H=H, RP=RP, reason="rp_already_in_head_and_blocks_intact")
        print(f"M={H}", flush=True)
        return EXIT_OK

    # RP 守卫：相对 O 只动了规则文件，且 RP 里规则块完好
    rp_paths = [x for x in g.out("diff-tree", "-r", "--no-renames", "--name-only", O, RP).splitlines() if x]
    extra = sorted(set(rp_paths) - set(files))
    if extra:
        raise LandError("RP_CHECK", "rp_touches_other_paths", paths=",".join(extra))
    rp_root = ls_tree_root(g, RP)
    for f in files:
        if f.encode() not in rp_root:
            raise LandError("RP_CHECK", "rp_lacks_file", file=f)
        if not block_intact(ctx.tr, f, g.blob_at(RP, f)):
            raise LandError("RP_CHECK", "rp_block_not_canonical", file=f)
    emit("RP_CHECK", "PASS", O=O, RP=RP, rp_paths=",".join(rp_paths) or "none")
    o_root = ls_tree_root(g, O)
    for f, pl in plans.items():  # 仅供参考：三方合并与 T(H) 是否一致（不一致说明本地分支改过规则区，M 以正本为准）
        if pl.h_bytes is None or f.encode() not in o_root:
            continue
        mo, rc = merge_file(g, ctx.work, pl.h_bytes, g.blob_at(O, f), g.blob_at(RP, f))
        res = "agree" if rc == 0 and mo == pl.th else ("conflict" if rc else "differ")
        emit("THREEWAY", "INFO", file=f, result=res)

    # C1：快照 + 工作树备份
    before = take_snapshot(g, files, snap, "c1")
    for f, pl in plans.items():
        src = os.path.join(ctx.top, f)
        if os.path.lexists(src):
            dst = os.path.join(snap, "wt_backup", f)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)  # 等价 cp -p
            pl.wt_seen = _read_file(dst)
            if not a.dry_run:
                g.write_blob(pl.wt_seen)
    emit("SNAPSHOT", "PASS", dir=snap, backups=sum(1 for pl in plans.values() if pl.wt_seen is not None),
         objects=0 if a.dry_run else 1)

    # C2：可行性
    idx_plan = {}
    for f, pl in plans.items():
        it = index_target(ctx, pl, pl.idx_seen)
        idx_plan[f] = it
        wfn = make_wt_fn(ctx, pl)
        wfn(pl.wt_seen)
        emit("FEASIBLE", "PASS", file=f, th_mode=pl.th_mode, index=it[3] if it else "absent_unchanged",
             worktree=wt_kind(pl, pl.wt_seen))

    # C3：构造 M
    new_root = dict(h_root)
    for f, pl in plans.items():
        if pl.th_changed:
            new_root[f.encode()] = (pl.h_ent[0] if pl.h_ent else "100644", "blob", pl.th_oid)
    n_changed = sum(1 for pl in plans.values() if pl.th_changed)
    T_M = obj_id("tree", build_tree_bytes(new_root), ctx.fmt)
    M = cm.predict(T_M, [H, RP])
    if a.dry_run:
        emit("LOCAL_COMMIT", "PASS", dry_run=1, H=H, M=M, parents="H,RP", first_parent_files=n_changed)
        emit("DRY_RUN", "STOP", before="C4", M=M)
        print(f"M={M}", flush=True)
        return EXIT_OK
    for f, pl in plans.items():
        if pl.th_changed and g.write_blob(pl.th) != pl.th_oid:
            raise LandError("LOCAL_COMMIT", "blob_id_mismatch", file=f)
        it = idx_plan[f]
        if it and g.write_blob(it[2]) != it[1]:
            raise LandError("LOCAL_COMMIT", "blob_id_mismatch", file=f, where="index")
    T2 = g.run("mktree", "-z", input=mktree_input(new_root)).stdout.decode().strip()
    if T2 != T_M:
        raise LandError("LOCAL_COMMIT", "tree_id_mismatch", expect=T_M, got=T2)
    M2 = cm.create(T_M, [H, RP])
    if M2 != M:
        raise LandError("LOCAL_COMMIT", "commit_id_mismatch", expect=M, got=M2)
    ns = [x for x in g.out("diff-tree", "-r", "--no-renames", "--name-only", H, M).splitlines() if x]
    want = sorted(f for f, pl in plans.items() if pl.th_changed)
    if len(ns) != n_changed or sorted(ns) != want:
        raise LandError("LOCAL_COMMIT", "first_parent_paths_unexpected", got=",".join(ns) or "none")
    if not g.is_ancestor(RP, M):
        raise LandError("LOCAL_COMMIT", "rp_not_ancestor_of_m")
    emit("LOCAL_COMMIT", "PASS", H=H, M=M, parents="H,RP", first_parent_files=n_changed)

    # C4：持锁落地
    try:
        idx_info, wt_recs = land_locked(ctx, a, plans, ref, H, M, snap, settle)
    except LandError as e:
        emit_error(e)
        raise

    # 落地元数据（rollback 用）
    meta = {"version": 1, "branch": br, "H": H, "M": M, "RP": RP, "O": O, "files": files,
            "index": {}, "worktree": {}}
    for f in files:
        ii = idx_info.get(f) or {}
        meta["index"][f] = {"before": ii.get("before"), "after": ii.get("after")}
        rec = wt_recs.get(f)
        if rec:
            ent = {"created": bool(rec.get("created"))}
            for k in ("pre", "post", "lost"):
                if rec.get(k) is not None:
                    p = os.path.join(snap, f"wt_{k}", f)
                    _write_file(p, rec[k])
                    g.write_blob(rec[k])
                    ent[k] = os.path.relpath(p, snap)
            meta["worktree"][f] = ent
        else:
            meta["worktree"][f] = None
    _write_file(os.path.join(snap, "landing.json"), json.dumps(meta, ensure_ascii=False, indent=1).encode())

    # C5：复核 hunk 集合与 status
    after = take_snapshot(g, files, snap, "c5")
    virtual = Virtual(ctx, plans, idx_info, wt_recs)
    ok5 = compare_states(ctx, files, before, after, virtual)

    # C6：可快进推送
    c = g.run("rev-list", "--left-right", "--count", f"refs/remotes/origin/{br}...HEAD", check=False)
    ok6 = False
    if c.returncode == 0:
        behind, ahead = c.stdout.decode().split()
        ok6 = behind == "0"
        emit("FF_READY", "PASS" if ok6 else "FAIL", behind=behind, ahead=ahead)
    else:
        emit("FF_READY", "FAIL", reason="no_tracking_ref", err=_err_line(c.stderr))
    rb = (f"rollback --repo-path {shlex.quote(ctx.top)} --branch {br} --m {M} --h {H} "
          f"--snapshot-dir {shlex.quote(snap)}")
    if not (ok5 and ok6):
        emit("MERGE", "FAIL", reason="postcheck_failed", rollback_cmd=rb)
        print(f"M={M}", flush=True)
        return EXIT_POSTCHECK
    emit("MERGE", "PASS", H=H, M=M, snapshot=snap)
    print(f"M={M}", flush=True)
    return EXIT_OK


def land_locked(ctx, a, plans, ref, H, M, snap, settle):
    """C4：取 index.lock → 索引副本改三条 → 引用事务 prepare → 工作树先比对再替换 → 事务 commit → 安装索引。"""
    g, files = ctx.g, ctx.files
    lock = IndexLock(ctx.lock_path, ctx.index_path)
    attempts = lock.acquire(a.lock_retries, a.lock_interval)
    emit("INDEX_LOCK", "PASS", attempts=attempts)
    held_file = os.environ.get("LAND_TEST_LOCK_HELD_FILE")
    txn = None
    committed = False
    progress = {}
    idx_info = {}
    wt_recs = {}
    try:
        if held_file:
            _write_file(held_file, b"held\n")
            _test_sleep()
        # 索引副本
        work_idx = os.path.join(snap, "index.work")
        idx_bytes = _read_file(ctx.index_path)
        idx_digest = hashlib.sha256(idx_bytes).hexdigest()
        _write_file(work_idx, idx_bytes)
        for p in (work_idx + ".lock",):
            if os.path.exists(p):
                os.unlink(p)
        ienv = {"GIT_INDEX_FILE": work_idx}
        full_before = parse_ls_stage(g.run("ls-files", "-s", "-z", env=ienv).stdout)
        updates = []
        recomputed = 0
        for f, pl in plans.items():
            seen = stage0(full_before, f)
            if f.encode() in full_before and seen is None:
                raise LandError("INDEX_DELTA", "unmerged_entry_appeared", file=f)
            if seen != pl.idx_seen:
                recomputed += 1
                info(f"{f}：锁内索引条目与 C2 所见不同（{pl.idx_seen} → {seen}），锁内重算")
            it = index_target(ctx, pl, seen)
            if it is None:
                idx_info[f] = {"before": list(seen) if seen else None, "after": list(seen) if seen else None,
                               "src": None}
                continue
            mode, oid, data, kind, src = it
            if g.write_blob(data) != oid:
                raise LandError("INDEX_DELTA", "blob_id_mismatch", file=f)
            after_ent = [mode, oid]
            idx_info[f] = {"before": list(seen) if seen else None, "after": after_ent,
                           "src": src if seen else None}
            if seen is None or seen[1] != oid:
                updates.append((f, mode, oid))
        for f, mode, oid in updates:
            g.run("update-index", "--add", "--cacheinfo", f"{mode},{oid},{f}", env=ienv)
        full_after = parse_ls_stage(g.run("ls-files", "-s", "-z", env=ienv).stdout)
        delta = sorted(p.decode("utf-8", "surrogateescape") for p in set(full_before) | set(full_after)
                       if full_before.get(p) != full_after.get(p))
        if delta != sorted(f for f, _m, _o in updates):
            raise LandError("INDEX_DELTA", "unexpected_changes", delta=",".join(delta) or "none")
        emit("INDEX_DELTA", "PASS", changed=len(delta), recomputed=recomputed)

        txn = RefTxn(g, f"land_rules_commit: 合并规则提交到 {ref}")
        txn.start()
        txn.update(ref, M, H)
        txn.prepare()
        emit("REF_PREPARE", "PASS", ref=ref, old=H, new=M)

        umask = os.umask(0)
        os.umask(umask)
        for f, pl in plans.items():
            path = os.path.join(ctx.top, f)
            prog = progress.setdefault(f, {})
            res = careful_replace(path, make_wt_fn(ctx, pl), expected=pl.wt_seen, progress=prog,
                                  block_ok=lambda data, _f=f: block_intact(ctx.tr, _f, data), settle=settle,
                                  max_recompute=a.max_recompute, create_mode=0o666 & ~umask, label=f)
            if res is None:
                emit("WT_WRITE", "SKIP", file=f, reason="unchanged")
                continue
            wt_recs[f] = {"created": res["created"], "pre": res["pre"], "post": res["post"],
                          "lost": prog.get("lost") or b""}
            emit("WT_WRITE", "PASS", file=f, created=int(res["created"]), rounds=res["rounds"],
                 catchups=res["catchups"], recomputes=res["recomputes"], tail_bytes=res["tail"])
        _test_fail("after_wt_write")

        txn.commit()
        committed = True
        emit("REF_CAS", "PASS", ref=ref, old=H, new=M)
        _test_fail("after_ref_commit")

        if hashlib.sha256(_read_file(ctx.index_path)).hexdigest() != idx_digest:
            raise LandError("INDEX_INSTALL", "index_changed_under_lock")
        if held_file:
            try:
                os.unlink(held_file)
            except FileNotFoundError:
                pass
            _test_sleep()
        lock.install(_read_file(work_idx))
        emit("INDEX_INSTALL", "PASS", index=ctx.index_path)
        return idx_info, wt_recs
    except BaseException as e:
        if isinstance(e, LandError):
            emit_error(e)
        else:
            emit("C4", "FAIL", reason="exception", err=f"{type(e).__name__}: {e}")
        ok = True
        if txn is not None and not committed:
            txn.abort()
        if committed:
            p = g.run("update-ref", "-m", "land_rules_commit: 回滚", ref, H, M, check=False)
            if p.returncode != 0:
                ok = False
                emit("ROLLBACK_REF", "FAIL", err=_err_line(p.stderr))
            else:
                emit("ROLLBACK_REF", "PASS", ref=ref, restored=H)
        for f, prog in progress.items():
            if prog.get("post") is None:
                continue
            try:
                r = restore_file(os.path.join(ctx.top, f), prog, settle, f)
            except LandError as e2:
                r = f"skip:{e2.reason}"
            emit("ROLLBACK_WT", "PASS" if not r.startswith("skip") else "FAIL", file=f, result=r)
            if r.startswith("skip"):
                ok = False
        rel = lock.release()
        if held_file:
            try:
                os.unlink(held_file)
            except FileNotFoundError:
                pass
        emit("ROLLBACK", "DONE" if ok else "PARTIAL", lock=rel)
        if isinstance(e, LandError):
            e.emitted = True
            if ok:
                e.code = EXIT_INFEASIBLE if e.name == "FEASIBLE" else EXIT_ROLLED_BACK
            else:
                e.code = EXIT_ROLLBACK_PARTIAL
            raise
        raise LandError("C4", "exception_rolled_back", EXIT_ROLLED_BACK if ok else EXIT_ROLLBACK_PARTIAL)
    finally:
        if lock.fd is not None and not lock.installed:
            lock.release()


# ───────────────────────────── rollback ─────────────────────────────

def cmd_rollback(a):
    ctx = _ctx_common(a)
    g, files = ctx.g, ctx.files
    snap = os.path.abspath(a.snapshot_dir)
    ctx.work = os.path.join(snap, "work")
    os.makedirs(ctx.work, exist_ok=True)
    meta = json.loads(_read_file(os.path.join(snap, "landing.json")))
    br = a.branch
    ref = f"refs/heads/{br}"
    M, H = g.rev(a.m), g.rev(a.h)
    if meta["M"] != M or meta["H"] != H or meta["branch"] != br:
        raise LandError("ROLLBACK_PRE", "snapshot_mismatch", meta_M=meta["M"], meta_H=meta["H"])
    if sorted(meta["files"]) != sorted(files):
        raise LandError("ROLLBACK_PRE", "files_mismatch", meta_files=",".join(meta["files"]))
    cur = g.rev(ref)
    if cur != M:
        raise LandError("ROLLBACK_PRE", "branch_not_at_M", branch_tip=cur or "none", M=M)
    ents = _local_prechecks(ctx, br, "ROLLBACK_PRE")
    for f in files:
        now = stage0(ents, f)
        want = meta["index"][f]["after"]
        if (list(now) if now else None) != want:
            raise LandError("ROLLBACK_PRE", "index_changed_since_land", file=f)
    recs = {}
    for f in files:
        w = meta["worktree"].get(f)
        if not w:
            continue
        recs[f] = {"created": w["created"]}
        for k in ("pre", "post", "lost"):
            recs[f][k] = _read_file(os.path.join(snap, w[k])) if w.get(k) else (b"" if k == "lost" else None)
    emit("ROLLBACK_PRE", "PASS", branch=br, M=M, H=H)
    settle = a.settle_ms / 1000.0

    lock = IndexLock(ctx.lock_path, ctx.index_path)
    attempts = lock.acquire(a.lock_retries, a.lock_interval)
    emit("INDEX_LOCK", "PASS", attempts=attempts)
    txn = None
    ok = True
    try:
        work_idx = os.path.join(snap, "index.rollback")
        idx_bytes = _read_file(ctx.index_path)
        digest = hashlib.sha256(idx_bytes).hexdigest()
        _write_file(work_idx, idx_bytes)
        ienv = {"GIT_INDEX_FILE": work_idx}
        full_before = parse_ls_stage(g.run("ls-files", "-s", "-z", env=ienv).stdout)
        zero = "0" * (40 if ctx.fmt == "sha1" else 64)
        lines, touched = [], []
        for f in files:
            now = stage0(full_before, f)
            if (list(now) if now else None) != meta["index"][f]["after"]:
                raise LandError("INDEX_DELTA", "index_changed_since_land", file=f)
            b = meta["index"][f]["before"]
            if b == meta["index"][f]["after"]:
                continue
            touched.append(f)
            lines.append(f"{b[0]} {b[1]}\t{f}" if b else f"0 {zero}\t{f}")
        if lines:
            g.run("update-index", "--index-info", input=("\n".join(lines) + "\n").encode(), env=ienv)
        full_after = parse_ls_stage(g.run("ls-files", "-s", "-z", env=ienv).stdout)
        delta = sorted(p.decode() for p in set(full_before) | set(full_after) if full_before.get(p) != full_after.get(p))
        if delta != sorted(touched):
            raise LandError("INDEX_DELTA", "unexpected_changes", delta=",".join(delta) or "none")
        emit("INDEX_DELTA", "PASS", changed=len(delta))
        txn = RefTxn(g, f"land_rules_commit: 回滚 {ref} 到 {H}")
        txn.start()
        txn.update(ref, H, M)
        txn.prepare()
        emit("REF_PREPARE", "PASS", ref=ref, old=M, new=H)
        for f, rec in recs.items():
            try:
                r = restore_file(os.path.join(ctx.top, f), rec, settle, f)
            except LandError as e2:
                r = f"skip:{e2.reason}"
            emit("ROLLBACK_WT", "FAIL" if r.startswith("skip") else "PASS", file=f, result=r)
            if r.startswith("skip"):
                ok = False
        txn.commit()
        emit("REF_CAS", "PASS", ref=ref, old=M, new=H)
        if hashlib.sha256(_read_file(ctx.index_path)).hexdigest() != digest:
            raise LandError("INDEX_INSTALL", "index_changed_under_lock")
        lock.install(_read_file(work_idx))
        emit("INDEX_INSTALL", "PASS")
    except LandError as e:
        emit_error(e)
        if txn is not None and txn.state != "committed":
            txn.abort()
        lock.release()
        emit("ROLLBACK", "FAIL", reason=e.reason, note="引用未提交时已放弃事务；工作树已恢复的文件保持恢复后状态")
        e.code = EXIT_ROLLBACK_PARTIAL
        raise
    finally:
        if lock.fd is not None and not lock.installed:
            lock.release()

    before = load_snapshot(snap, "c1")
    after = take_snapshot(g, files, snap, "rb")
    ok5 = compare_states(ctx, files, before, after, None)
    emit("ROLLBACK", "PASS" if (ok and ok5) else "PARTIAL", branch_tip=H)
    return EXIT_OK if (ok and ok5) else EXIT_ROLLBACK_PARTIAL


# ───────────────────────────── verify（C7） ─────────────────────────────

def cmd_verify(a):
    g = Git(a.repo_path)
    files = parse_files(a.files)
    tr = make_transformer(a)
    ref = f"refs/heads/{a.branch}"
    M = g.rev(a.m)
    tip = g.rev(ref)
    if M is None or tip is None:
        raise LandError("NO_REVERT", "rev_missing", M=M or "none", tip=tip or "none")
    if not g.is_ancestor(M, tip):
        raise LandError("NO_REVERT", "m_not_in_branch", M=M, tip=tip)
    commits = [c for c in g.out("rev-list", f"{M}..{tip}").splitlines() if c]
    seen = {}
    for c in [M] + commits:
        root = ls_tree_root(g, c)
        for f in files:
            ent = root.get(f.encode())
            if ent is None:
                raise LandError("NO_REVERT", "file_missing", commit=c, file=f)
            key = (f, ent[2])
            if key not in seen:
                seen[key] = block_intact(tr, f, g.blob(ent[2]))
            if not seen[key]:
                raise LandError("NO_REVERT", "block_changed", commit=c, file=f)
    emit("NO_REVERT", "PASS", commits=len(commits), checked=len(commits) + 1, M=M, tip=tip)
    return EXIT_OK


# ───────────────────────────── 参数 ─────────────────────────────

def build_parser():
    ap = argparse.ArgumentParser(prog="land_rules_commit.py",
                                 description="规则文件「文件级精确」落地：remote / merge / rollback / verify。",
                                 formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p, need_canon=True):
        p.add_argument("--repo-path", required=True, help="目标仓库路径")
        p.add_argument("--branch", required=True, help="目标分支名（不带 refs/heads/）")
        p.add_argument("--files", required=True, help="逗号分隔的根目录规则文件，如 AGENTS.md,CLAUDE.md,greatlakes.md")
        p.add_argument("--canon-rev", required=need_canon, help="正本仓库 commit（完整 sha）")
        p.add_argument("--transform-cmd", help="外部 transform 命令（桩）；不给则导入 sync_rules")
        p.add_argument("--sync-rules-dir", help="sync_rules.py 所在目录，缺省为本脚本目录")
        p.add_argument("--sync-config", help="sync-targets.json 路径，缺省为 sync_rules.DEFAULT_TARGETS")
        p.add_argument("--sync-target", help="sync-targets.json 里的目标名（benchmark / mjepa …），决定块名与 onboard 规格")
        p.add_argument("--onboard-dir", help="onboard 规格目录，缺省为 sync_rules 同目录下的 onboard/")
        p.add_argument("--canon-repo", help="覆盖配置里的正本仓库路径")
        p.add_argument("--block-map", help="块名覆盖：文件=块名,...")

    def commit_args(p):
        p.add_argument("--message-file", required=True, help="提交说明文件（原样写入）")
        p.add_argument("--date", required=True, help="固定作者/提交日期，ISO8601 带时区或 '@epoch +zzzz'")
        p.add_argument("--dry-run", action="store_true", help="只算不写：不写对象、不推送、不落地")

    p = sub.add_parser("remote", help="B1–B6：构造并（可选）快进推送单亲提交 RP")
    common(p)
    commit_args(p)
    p.add_argument("--push", action="store_true", help="推送（只快进，被拒退出 4）")
    p.add_argument("--expect-diff-dir", help="审阅版 diff 目录：<文件>.diff 须与 diff <(O 版) <(新版) 逐字节一致")
    p.add_argument("--emit-diff-dir", help="把 diff <(O 版) <(新版) 写到该目录，供人工审阅")
    p.set_defaults(func=cmd_remote)

    p = sub.add_parser("merge", help="C0–C6：本地合并提交 M 持锁落地")
    common(p)
    commit_args(p)
    p.add_argument("--rp", required=True, help="remote 步骤打印的 RP")
    p.add_argument("--snapshot-dir", help="快照/备份目录（缺省新建临时目录）")
    p.add_argument("--settle-ms", type=int, default=200, help="替换后复查旧 inode 前的等待毫秒数")
    p.add_argument("--lock-retries", type=int, default=20, help="index.lock 拿不到时的重试次数")
    p.add_argument("--lock-interval", type=float, default=0.5, help="index.lock 重试间隔秒数")
    p.add_argument("--max-recompute", type=int, default=3, help="工作树内容变化时的最大重算次数")
    p.set_defaults(func=cmd_merge)

    p = sub.add_parser("rollback", help="撤销一次 merge 落地")
    p.add_argument("--repo-path", required=True)
    p.add_argument("--branch", required=True)
    p.add_argument("--m", required=True, help="merge 产生的 M")
    p.add_argument("--h", required=True, help="merge 前的 H")
    p.add_argument("--snapshot-dir", required=True, help="merge 的快照目录（含 landing.json）")
    p.add_argument("--files", default=None, help="缺省取快照里的文件表")
    p.add_argument("--settle-ms", type=int, default=200)
    p.add_argument("--lock-retries", type=int, default=20)
    p.add_argument("--lock-interval", type=float, default=0.5)
    p.set_defaults(func=cmd_rollback)

    p = sub.add_parser("verify", help="C7：M..分支 每个提交里规则块是否仍完好")
    common(p)
    p.add_argument("--m", required=True, help="merge 产生的 M")
    p.set_defaults(func=cmd_verify)
    return ap


def main(argv=None):
    ap = build_parser()
    a = ap.parse_args(argv)
    if a.cmd == "rollback" and not a.files:
        try:
            a.files = ",".join(json.loads(_read_file(os.path.join(a.snapshot_dir, "landing.json")))["files"])
        except (OSError, ValueError, KeyError) as e:
            emit("ROLLBACK_PRE", "FAIL", reason="landing_json_unreadable", err=str(e))
            return EXIT_FAIL
    try:
        return a.func(a)
    except LandError as e:
        emit_error(e)
        return e.code


if __name__ == "__main__":
    sys.exit(main())
