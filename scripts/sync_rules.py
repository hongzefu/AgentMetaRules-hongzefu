#!/usr/bin/env python3
"""AgentMetaRules 通用块同步工具（只用 Python 标准库）。

背景
====
正本仓库的 AGENTS.md / CLAUDE.md / greatlakes.md 各含一个「通用块」，用整行 HTML 注释标记圈出；
项目仓库的同名文件里用同样的标记圈出一份逐字副本，标记外是项目专属内容。本脚本负责：

1. 从正本某个 git 版本提取通用块（一律 ``git cat-file blob <rev>:<file>``，不读正本工作树）；
2. 变换目标文件：替换块内容、在标记行写入 src/blob，块外字节逐字节不变；
3. 比对项目副本与正本块是否漂移。

标记格式
========
- 正本（源）：``<!-- AGENTMETARULES:BEGIN <块名> -->`` …… ``<!-- AGENTMETARULES:END <块名> -->``，不带属性。
- 项目副本（目标）：``<!-- AGENTMETARULES:BEGIN <块名> src=<40hex> blob=<40hex> -->``，END 行带同样的属性
  （由常量 END_CARRIES_ATTRS 控制；解析时 END 不带属性也接受，但带了就必须与 BEGIN 完全一致）。
  src = 生成副本时的正本 commit 全 sha；blob = 块内容字节的 git blob id。
- 块名固定三个：common-agents / common-claude / common-greatlakes；文件与块名的对应只由 sync-targets.json 决定。
- 标记必须整行、从第 0 列开始；以 ``<!-- AGENTMETARULES:`` 开头但不符合正则的行一律判 FAIL。
- 解析时跟踪 Markdown 代码围栏（行首 ``` 或 ~~~，允许缩进），围栏内的标记原文不算标记；
  但块内容里（含围栏内）不允许出现以 ``<!-- AGENTMETARULES:`` 开头的行。
- 每个文件恰好一对标记、BEGIN 在 END 前；块内容 = BEGIN 行的 ``\\n`` 之后到 END 行行首之前的字节，
  必须非空且以 ``\\n`` 结尾。

字节语义
========
全部按字节处理：``rb`` 读、只按 ``b"\\n"`` 切分（不用 str.splitlines，它会在 \\x85、U+2028 等处断行），
不做 NFC、不动行尾空格。输入含 ``\\r`` 或以 UTF-8 BOM 开头 → ``EOL=FAIL``，不自动转换。

安全约束
========
本脚本的 git 调用全部只读（rev-parse / cat-file / status / merge-base / symbolic-ref），
并设置 GIT_OPTIONAL_LOCKS=0 避免 git status 顺手写 index；绝不执行 git add / commit / push。

可导入的函数（供落地脚本 import）
==================================
- ``parse_markers(data, block) -> (begin_line_start, content_start, content_end, end_line_end, attrs)``
- ``transform_bytes(data, block, canon_block, canon_rev, onboard_spec) -> (out, mode)``
- ``git_blob_id(data) -> str``
- 另有 ``transform_detail`` / ``verify_invariants`` / ``lint_source`` / ``load_config`` /
  ``load_onboard_spec`` / ``check_ledger`` / ``apply_to_path`` / ``main`` 等。
"""

from __future__ import annotations

import argparse
import dataclasses
import errno
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
from typing import Callable, Dict, List, Optional, Tuple

__all__ = [
    "BLOCK_NAMES",
    "MARKER_PREFIX",
    "MARKER_RE",
    "END_CARRIES_ATTRS",
    "SyncError",
    "MarkersAbsent",
    "TransformResult",
    "Config",
    "Target",
    "Canon",
    "git_blob_id",
    "eol_problem",
    "iter_lines",
    "parse_markers",
    "begin_marker_line",
    "end_marker_line",
    "validate_block_content",
    "lint_source",
    "transform_detail",
    "transform_bytes",
    "verify_invariants",
    "check_ledger",
    "outside_digests",
    "load_config",
    "load_onboard_spec",
    "apply_to_path",
    "main",
]

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

#: 允许的块名（固定三个）。
BLOCK_NAMES = ("common-agents", "common-claude", "common-greatlakes")

#: 所有标记行共同的前缀；以它开头却不符合 MARKER_RE 的行一律判 FAIL。
MARKER_PREFIX = b"<!-- AGENTMETARULES:"

#: 标记行正则（对不含 \n 的整行做 fullmatch，等价于 ^...$ 从第 0 列匹配）。
MARKER_RE = re.compile(
    rb"<!-- AGENTMETARULES:(BEGIN|END) (common-agents|common-claude|common-greatlakes)"
    rb"(?: src=([0-9a-f]{40}) blob=([0-9a-f]{40}))? -->"
)

#: 目标副本的 END 行是否也写 src/blob（与 BEGIN 相同）。改成 False 即输出不带属性的 END 行。
END_CARRIES_ATTRS = True

UTF8_BOM = b"\xef\xbb\xbf"
MAX_APPLY_ATTEMPTS = 3

EXIT_OK = 0  # 成功（transform：有改动）
EXIT_DRIFT = 1  # check 有 FAIL/MISSING、lint 有 FAIL
EXIT_FAIL = 2  # 判定失败、配置/正本错误
EXIT_NOOP = 3  # transform 无改动

DEFAULT_TARGETS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sync-targets.json"
)

_SHA40_RE = re.compile(r"[0-9a-f]{40}")
_SHA256_RE = re.compile(r"[0-9a-f]{64}")
# 围栏开行：行首任意空格/制表符缩进 + 至少 3 个 ` 或 ~，其后为 info 串。
_FENCE_OPEN_RE = re.compile(rb"[ \t]*(`{3,}|~{3,})(.*)", re.DOTALL)

ONBOARD_KEYS = ("start", "end", "known_region_sha256", "head", "tail")
#: onboard 规格里视为注释、直接忽略的键（另外所有以 "_" 开头的键也视为注释）。
ONBOARD_COMMENT_KEYS = ("note", "comment")


# ---------------------------------------------------------------------------
# 异常
# ---------------------------------------------------------------------------


class SyncError(Exception):
    """带机器可读 reason 码的失败；detail 为中文说明，info 携带附加结构化信息。"""

    def __init__(self, reason: str, detail: str = "", info: Optional[dict] = None):
        super().__init__(f"{reason}：{detail}" if detail else reason)
        self.reason = reason
        self.detail = detail
        self.info = info or {}


class MarkersAbsent(SyncError):
    """文件里没有任何（围栏外的）本块标记；onboard 模式据此走首次接入路径。"""


# ---------------------------------------------------------------------------
# 基础工具
# ---------------------------------------------------------------------------


def git_blob_id(data: bytes) -> str:
    """返回字节串的 git blob id（与 ``git hash-object --stdin`` 相同）。"""
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def eol_problem(data: bytes) -> Optional[str]:
    """检查换行/BOM：以 UTF-8 BOM 开头返回 'bom'，含 \\r 返回 'cr'，否则 None。"""
    if data.startswith(UTF8_BOM):
        return "bom"
    if b"\r" in data:
        return "cr"
    return None


def iter_lines(data: bytes):
    """只按 b"\\n" 切分，逐行产出 (行号, 行首偏移, 行尾偏移（不含 \\n）, 下一行行首偏移)。

    以 \\n 结尾的数据不会产出末尾空行；最后一行没有 \\n 时其「下一行行首」等于 len(data)。
    """
    pos = 0
    n = len(data)
    lineno = 0
    while pos < n:
        nl = data.find(b"\n", pos)
        lineno += 1
        if nl == -1:
            yield lineno, pos, n, n
            return
        yield lineno, pos, nl, nl + 1
        pos = nl + 1


def _scan(data: bytes):
    """带代码围栏跟踪的逐行扫描。

    返回 (行列表, EOF 时是否仍有未闭合围栏)；行列表元素为
    (行号, 行首, 行尾（不含 \\n）, 下一行行首, 是否在围栏内)。

    围栏规则：
    - 不在围栏内时，行首（允许任意空格/制表符缩进）出现至少 3 个 ` 或 ~ 即开围栏；
      反引号围栏的 info 串里若含反引号则不算围栏（CommonMark 规则）。
    - 在围栏内时，去掉首尾空格/制表符后全由同一围栏字符组成、且长度不少于开围栏长度的行关闭围栏。
    - 开/闭围栏行本身也记为「围栏内」，不参与标记识别。
    - 围栏未闭合则一直延续到文件尾（其后的标记全部视为围栏内原文）。
    """
    out = []
    fence: Optional[Tuple[bytes, int]] = None
    for lineno, s, e, nxt in iter_lines(data):
        line = data[s:e]
        if fence is None:
            m = _FENCE_OPEN_RE.fullmatch(line)
            if m and not (m.group(1)[:1] == b"`" and b"`" in m.group(2)):
                fence = (m.group(1)[:1], len(m.group(1)))
                out.append((lineno, s, e, nxt, True))
            else:
                out.append((lineno, s, e, nxt, False))
        else:
            ch, length = fence
            stripped = line.strip(b" \t")
            if len(stripped) >= length and stripped == ch * len(stripped):
                fence = None
            out.append((lineno, s, e, nxt, True))
    return out, fence is not None


def _show(line: bytes, limit: int = 120) -> str:
    """把一行字节转成便于在报错里展示的文本。"""
    text = line.decode("utf-8", "backslashreplace")
    return text if len(text) <= limit else text[:limit] + "…"


def _q(text: Optional[str]) -> str:
    """判定行里可能含空格的值用单引号包起来；None 输出 null。"""
    return "null" if text is None else "'" + text + "'"


# ---------------------------------------------------------------------------
# 标记解析
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class _Marker:
    kind: str
    lineno: int
    start: int
    end: int
    nxt: int
    src: Optional[str]
    blob: Optional[str]


def parse_markers(data: bytes, block: str):
    """解析 data 中块 ``block`` 的一对标记。

    返回 ``(begin_line_start, content_start, content_end, end_line_end, attrs)``：
    - begin_line_start：BEGIN 行行首偏移；
    - content_start：BEGIN 行 \\n 之后的偏移（块内容起点）；
    - content_end：END 行行首偏移（块内容终点，不含）；
    - end_line_end：END 行标记文本之后的偏移（不含 END 行自身的 \\n，该 \\n 属于块外字节）；
    - attrs：BEGIN 行属性 ``{"src": ..., "blob": ...}``，源格式（无属性）时为 ``{}``。

    失败抛 SyncError（reason 见下）；没有任何本块标记时抛 MarkersAbsent（reason=markers_absent）。
    reason：unknown_block / malformed_marker / foreign_block_marker / marker_count / marker_order /
    content_empty / content_no_trailing_newline / marker_in_content / end_attr_mismatch。
    """
    if block not in BLOCK_NAMES:
        raise SyncError("unknown_block", f"块名 {block!r} 不在 {BLOCK_NAMES} 中")
    bname = block.encode("ascii")
    lines, unclosed = _scan(data)
    markers: List[_Marker] = []
    fenced_prefixed: List[Tuple[int, int]] = []  # 围栏内以标记前缀开头的行 (行号, 行首)
    for lineno, s, e, nxt, fenced in lines:
        if not data.startswith(MARKER_PREFIX, s):
            continue
        if fenced:
            fenced_prefixed.append((lineno, s))
            continue
        line = data[s:e]
        m = MARKER_RE.fullmatch(line)
        if m is None:
            raise SyncError(
                "malformed_marker",
                f"第 {lineno} 行以 {MARKER_PREFIX.decode()} 开头但不符合标记格式：{_show(line)}",
            )
        kind, name, src, blob = m.group(1), m.group(2), m.group(3), m.group(4)
        if name != bname:
            raise SyncError(
                "foreign_block_marker",
                f"第 {lineno} 行是块 {name.decode()} 的标记，本文件只允许块 {block}",
            )
        markers.append(
            _Marker(
                kind.decode(),
                lineno,
                s,
                e,
                nxt,
                src.decode() if src else None,
                blob.decode() if blob else None,
            )
        )
    begins = [m for m in markers if m.kind == "BEGIN"]
    ends = [m for m in markers if m.kind == "END"]
    if not begins and not ends:
        hint = "（注意：文件末尾有未闭合的代码围栏，围栏后的标记会被当成围栏内原文）" if unclosed else ""
        raise MarkersAbsent("markers_absent", f"没有找到块 {block} 的标记{hint}")
    if len(begins) != 1 or len(ends) != 1:
        where = "、".join(f"{m.kind}@第{m.lineno}行" for m in markers)
        raise SyncError(
            "marker_count",
            f"块 {block} 的 BEGIN {len(begins)} 个、END {len(ends)} 个（要求各恰好 1 个）：{where}",
        )
    b, e = begins[0], ends[0]
    if e.start < b.start:
        raise SyncError("marker_order", f"END（第 {e.lineno} 行）出现在 BEGIN（第 {b.lineno} 行）之前")
    content_start, content_end = b.nxt, e.start
    if content_end <= content_start:
        raise SyncError("content_empty", f"块 {block} 内容为空（BEGIN 第 {b.lineno} 行、END 第 {e.lineno} 行）")
    if data[content_end - 1 : content_end] != b"\n":
        raise SyncError("content_no_trailing_newline", f"块 {block} 内容不以 \\n 结尾")
    inner = [ln for ln, s in fenced_prefixed if content_start <= s < content_end]
    if inner:
        raise SyncError(
            "marker_in_content",
            f"块 {block} 内容里（代码围栏内）有以 {MARKER_PREFIX.decode()} 开头的行：第 {inner} 行",
        )
    attrs: Dict[str, str] = {"src": b.src, "blob": b.blob} if b.src else {}
    if e.src is not None and (e.src, e.blob) != (b.src, b.blob):
        raise SyncError(
            "end_attr_mismatch",
            f"END 行属性 src={e.src} blob={e.blob} 与 BEGIN 行属性 {attrs or '（无）'} 不一致",
        )
    return b.start, content_start, content_end, e.end, attrs


def begin_marker_line(block: str, src: Optional[str] = None, blob: Optional[str] = None) -> bytes:
    """构造 BEGIN 标记行（不含 \\n）；src/blob 为 None 时构造源格式。"""
    attr = b"" if src is None else b" src=%s blob=%s" % (src.encode(), blob.encode())
    return b"<!-- AGENTMETARULES:BEGIN %s%s -->" % (block.encode(), attr)


def end_marker_line(block: str, src: Optional[str] = None, blob: Optional[str] = None) -> bytes:
    """构造 END 标记行（不含 \\n）；END_CARRIES_ATTRS 为 False 或 src 为 None 时不带属性。"""
    if not END_CARRIES_ATTRS or src is None:
        return b"<!-- AGENTMETARULES:END %s -->" % block.encode()
    return b"<!-- AGENTMETARULES:END %s src=%s blob=%s -->" % (block.encode(), src.encode(), blob.encode())


def validate_block_content(content: bytes, what: str = "正本块") -> None:
    """校验块内容本身：非空、以 \\n 结尾、无 \\r/BOM、无以标记前缀开头的行（围栏内也不行）。"""
    if not content:
        raise SyncError("content_empty", f"{what}为空")
    if not content.endswith(b"\n"):
        raise SyncError("content_no_trailing_newline", f"{what}不以 \\n 结尾")
    prob = eol_problem(content)
    if prob:
        raise SyncError("eol", f"{what}含 {prob}")
    for lineno, s, _e, _n in iter_lines(content):
        if content.startswith(MARKER_PREFIX, s):
            raise SyncError("marker_in_content", f"{what}第 {lineno} 行以 {MARKER_PREFIX.decode()} 开头")


def lint_source(data: bytes, block: str) -> List[Tuple[str, str]]:
    """对正本文件做源 lint，返回问题列表 [(reason, 说明)]；空列表即 PASS。

    检查：无 \\r / BOM；标记存在且唯一、BEGIN 在 END 前；BEGIN/END 均无属性；
    块内（含围栏内）无标记前缀行；块非空且以 \\n 结尾；围栏外无畸形标记、无其他块名的标记。
    """
    prob = eol_problem(data)
    if prob:
        return [("eol", f"文件含 {prob}（EOL=FAIL，不自动转换）")]
    try:
        _b0, _c0, _c1, _e1, attrs = parse_markers(data, block)
    except SyncError as exc:
        return [(exc.reason, exc.detail)]
    if attrs:
        # parse_markers 已保证 END 属性与 BEGIN 一致，因此 BEGIN 无属性时 END 也必然无属性。
        return [("source_has_attrs", "正本的 BEGIN 标记不得带 src/blob 属性")]
    return []


# ---------------------------------------------------------------------------
# 变换
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class TransformResult:
    """变换结果与校验所需的位置信息。

    - mode：update / onboard / create / noop；
    - keep_prefix：输入输出共同保留的前缀长度（in[:p] == out[:p]）；
    - in_suffix_start / out_suffix_start：输入/输出里共同保留的后缀起点（in[i:] == out[o:]）；
    - region：onboard 模式下被替换区域的信息（start/end/bytes/sha256/status）；
    - onboard_skipped：给了 onboard 规格但输入已有标记、退化为普通模式；
    - block_blob：正本块的 git blob id。
    """

    out: bytes
    mode: str
    keep_prefix: int
    in_suffix_start: int
    out_suffix_start: int
    region: Optional[dict]
    onboard_skipped: bool
    block_blob: str


def _spec_bytes(spec: dict, key: str) -> bytes:
    data = spec.get(key + "_bytes")
    if data is None:
        return b""
    if not isinstance(data, (bytes, bytearray)):
        raise SyncError("onboard_spec_invalid", f"onboard 规格的 {key}_bytes 必须是 bytes")
    data = bytes(data)
    if not data:
        return data
    if not data.endswith(b"\n"):
        raise SyncError("onboard_fixture_invalid", f"{key} 文件内容必须以 \\n 结尾（或为空）")
    prob = eol_problem(data)
    if prob:
        raise SyncError("onboard_fixture_invalid", f"{key} 文件含 {prob}")
    for lineno, s, _e, _n in iter_lines(data):
        if data.startswith(MARKER_PREFIX, s):
            raise SyncError("onboard_fixture_invalid", f"{key} 文件第 {lineno} 行以标记前缀开头")
    return data


def _unique_line_offset(data: bytes, text: str, label: str) -> int:
    """整行精确匹配（第 0 列起、不含 \\n）text，要求恰好命中 1 次，返回该行行首偏移。"""
    if not isinstance(text, str) or not text or "\n" in text or "\r" in text:
        raise SyncError("onboard_spec_invalid", f"{label} 必须是非空单行字符串")
    want = text.encode("utf-8")
    hits = [(ln, s) for ln, s, e, _n in iter_lines(data) if data[s:e] == want]
    if len(hits) != 1:
        raise SyncError(
            "onboard_anchor_count",
            f"{label}={text!r} 整行命中 {len(hits)} 次（行号 {[h[0] for h in hits]}），要求恰好 1 次",
        )
    return hits[0][1]


def _onboard_transform(data: bytes, spec: dict, new_region: bytes, blob: str) -> TransformResult:
    if not isinstance(spec, dict):
        raise SyncError("onboard_spec_invalid", "onboard 规格必须是 dict")
    for key in ("start", "end"):
        if key not in spec:
            raise SyncError("onboard_spec_invalid", f"onboard 规格缺少 {key} 字段（新建文件请显式写 null）")
    head = _spec_bytes(spec, "head")
    tail = _spec_bytes(spec, "tail")
    start, end = spec["start"], spec["end"]
    insertion = head + new_region + b"\n" + tail
    if start is None:
        if end is not None:
            raise SyncError("onboard_spec_invalid", "start 为 null（新建文件）时 end 也必须为 null")
        if data:
            raise SyncError(
                "create_target_not_empty",
                f"onboard 规格 start=null 表示目标文件不存在，但输入有 {len(data)} 字节且没有标记",
            )
        return TransformResult(insertion, "create", 0, 0, len(insertion), None, False, blob)
    s_off = _unique_line_offset(data, start, "start")
    if end is None:
        e_off = len(data)
    else:
        e_off = _unique_line_offset(data, end, "end")
        if e_off <= s_off:
            raise SyncError("onboard_end_before_start", f"end 行 {end!r} 不在 start 行 {start!r} 之后")
    region = data[s_off:e_off]
    sha = sha256_hex(region)
    known = list(spec.get("known_region_sha256") or [])
    status = "UNCHECKED" if not known else ("PASS" if sha in known else "FAIL")
    info = {"start": start, "end": end, "bytes": len(region), "sha256": sha, "status": status}
    if status == "FAIL":
        raise SyncError(
            "onboard_region_unknown",
            f"被替换区域 sha256={sha}（{len(region)} 字节）不在 known_region_sha256 集合中",
            info={"region": info},
        )
    out = data[:s_off] + insertion + data[e_off:]
    return TransformResult(out, "onboard", s_off, e_off, s_off + len(insertion), info, False, blob)


def transform_detail(
    data: bytes,
    block: str,
    canon_block: bytes,
    canon_rev: str,
    onboard_spec: Optional[dict] = None,
) -> TransformResult:
    """transform_bytes 的详细版：返回 TransformResult（含保留前后缀位置、onboard 区域信息）。"""
    if block not in BLOCK_NAMES:
        raise SyncError("unknown_block", f"块名 {block!r} 不在 {BLOCK_NAMES} 中")
    if not isinstance(canon_rev, str) or not _SHA40_RE.fullmatch(canon_rev):
        raise SyncError("bad_canon_rev", f"canon_rev 必须是 40 位小写十六进制的完整 commit sha：{canon_rev!r}")
    validate_block_content(canon_block)
    prob = eol_problem(data)
    if prob:
        raise SyncError("eol", f"输入含 {prob}（EOL=FAIL，不自动转换）", info={"eol": prob})
    blob = git_blob_id(canon_block)
    new_region = begin_marker_line(block, canon_rev, blob) + b"\n" + canon_block + end_marker_line(block, canon_rev, blob)
    try:
        b0, _c0, _c1, e1, _attrs = parse_markers(data, block)
    except MarkersAbsent:
        if onboard_spec is None:
            raise
        return _onboard_transform(data, onboard_spec, new_region, blob)
    out = data[:b0] + new_region + data[e1:]
    mode = "noop" if out == data else "update"
    return TransformResult(out, mode, b0, e1, b0 + len(new_region), None, onboard_spec is not None, blob)


def transform_bytes(
    data: bytes,
    block: str,
    canon_block: bytes,
    canon_rev: str,
    onboard_spec: Optional[dict] = None,
) -> Tuple[bytes, str]:
    """把 data 里块 block 的内容换成 canon_block，返回 (out, mode)。

    - 普通模式（输入已有标记）：只替换两条标记行及其间内容，BEGIN/END 写入 src=canon_rev、blob=新块 blob；
      标记外字节逐字节不变；结果与输入相同时 mode='noop'，否则 'update'。
    - onboard_spec 非 None 且输入没有标记：按规格首次接入，mode='onboard'（替换区域）或 'create'（新建文件）。
      onboard_spec 是单个文件的规格 dict：start / end / known_region_sha256 / head_bytes / tail_bytes
      （用 load_onboard_spec 从 fixture 目录加载即得）。输入已有标记时 onboard 规格被忽略、退化为普通模式。
    失败抛 SyncError。
    """
    res = transform_detail(data, block, canon_block, canon_rev, onboard_spec)
    return res.out, res.mode


def outside_digests(data: bytes, res: TransformResult) -> Tuple[str, str]:
    """返回 (输入块外 sha256, 输出块外 sha256)，块外 = 保留前缀 + 保留后缀 直接拼接。"""
    p = res.keep_prefix
    return (
        sha256_hex(data[:p] + data[res.in_suffix_start :]),
        sha256_hex(res.out[:p] + res.out[res.out_suffix_start :]),
    )


def verify_invariants(
    data: bytes,
    res: TransformResult,
    block: str,
    canon_block: bytes,
    canon_rev: str,
    onboard_spec: Optional[dict] = None,
) -> List[Tuple[str, str, str]]:
    """逐条校验变换不变式，返回 [(名称, PASS|FAIL|SKIP, 失败说明)]。

    - prefix：out[:begin] == in[:begin]；
    - suffix：out[end_out:] == in[end_in:]；
    - block：输出重新解析后块内容 == 正本块，属性 == {src: canon_rev, blob: 正本块 blob}；
    - idempotent：T(T(x)) == T(x)（第二次变换必须是 noop）；
    - noop_when_synced：输入已同步（标记行与块内容与期望完全一致）时 T(x) == x，否则 SKIP。
    """
    out = res.out
    results: List[Tuple[str, str, str]] = []

    def add(name: str, ok: Optional[bool], detail: str) -> None:
        results.append((name, "SKIP" if ok is None else ("PASS" if ok else "FAIL"), "" if ok else detail))

    p = res.keep_prefix
    add("prefix", out[:p] == data[:p], f"out[:{p}] 与 in[:{p}] 不一致")
    suf_ok = (len(out) - res.out_suffix_start == len(data) - res.in_suffix_start) and (
        out[res.out_suffix_start :] == data[res.in_suffix_start :]
    )
    add("suffix", suf_ok, f"out[{res.out_suffix_start}:] 与 in[{res.in_suffix_start}:] 不一致")

    want_attrs = {"src": canon_rev, "blob": git_blob_id(canon_block)}
    try:
        _b0, c0, c1, _e1, attrs = parse_markers(out, block)
        add("block", out[c0:c1] == canon_block and attrs == want_attrs, f"输出块内容或属性不符（attrs={attrs}）")
    except SyncError as exc:
        add("block", False, f"输出无法解析：{exc}")

    try:
        res2 = transform_detail(out, block, canon_block, canon_rev, onboard_spec)
        add("idempotent", res2.out == out and res2.mode == "noop", f"第二次变换不是 noop（mode={res2.mode}）")
    except SyncError as exc:
        add("idempotent", False, f"第二次变换失败：{exc}")

    try:
        b0, _c0, _c1, e1, _attrs = parse_markers(data, block)
        blob = want_attrs["blob"]
        expected = begin_marker_line(block, canon_rev, blob) + b"\n" + canon_block + end_marker_line(block, canon_rev, blob)
        synced = data[b0:e1] == expected
    except SyncError:
        synced = False
    add("noop_when_synced", (out == data and res.mode == "noop") if synced else None, "输入已同步但输出与输入不同")
    return results


def _all_line_offsets(data: bytes, want: bytes) -> List[Tuple[int, int]]:
    return [(ln, s) for ln, s, e, _n in iter_lines(data) if data[s:e] == want]


def check_ledger(data_in: bytes, data_out: bytes, anchor: str) -> dict:
    """校验项目账本字节：从 anchor 整行（输入、输出中各须恰好 1 次）起到文件尾，输入输出必须逐字节相同。

    返回 {"status": PASS|FAIL, "bytes": int|None, "sha256": str|None, "reason": str}。
    """
    want = anchor.encode("utf-8")
    hin = _all_line_offsets(data_in, want)
    hout = _all_line_offsets(data_out, want)
    if len(hin) != 1:
        return {"status": "FAIL", "bytes": None, "sha256": None, "reason": f"anchor_count_in_{len(hin)}"}
    tail_in = data_in[hin[0][1] :]
    if len(hout) != 1:
        return {"status": "FAIL", "bytes": len(tail_in), "sha256": sha256_hex(tail_in), "reason": f"anchor_count_out_{len(hout)}"}
    tail_out = data_out[hout[0][1] :]
    ok = tail_in == tail_out
    return {
        "status": "PASS" if ok else "FAIL",
        "bytes": len(tail_in),
        "sha256": sha256_hex(tail_in),
        "reason": "ok" if ok else "bytes_changed",
    }


# ---------------------------------------------------------------------------
# 配置与 onboard 规格
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class Target:
    name: str
    path: str
    branch: Optional[str]
    remote: Optional[str]
    files: Dict[str, str]
    ledger_anchor: Dict[str, str]


@dataclasses.dataclass
class Config:
    source: str
    canon_path: str
    canon_branch: str
    canon_files: Dict[str, str]  # 正本文件名 -> 块名
    block_to_file: Dict[str, str]  # 块名 -> 正本文件名
    targets: List[Target]

    def target(self, name: str) -> Target:
        for t in self.targets:
            if t.name == name:
                return t
        raise SyncError("unknown_repo", f"sync-targets.json 里没有名为 {name!r} 的目标（可选：{[t.name for t in self.targets]}）")


def _cfg_fail(msg: str) -> SyncError:
    return SyncError("config_invalid", msg)


def _check_files_map(obj, where: str) -> Dict[str, str]:
    if not isinstance(obj, dict) or not obj:
        raise _cfg_fail(f"{where}.files 必须是非空对象")
    for k, v in obj.items():
        if not isinstance(k, str) or not k or os.path.isabs(k) or ".." in k.split("/"):
            raise _cfg_fail(f"{where}.files 的文件名不合法：{k!r}")
        if v not in BLOCK_NAMES:
            raise _cfg_fail(f"{where}.files[{k!r}] 的块名 {v!r} 不在 {BLOCK_NAMES} 中")
    if len(set(obj.values())) != len(obj):
        raise _cfg_fail(f"{where}.files 里同一块名对应了多个文件")
    return dict(obj)


def load_config(path: str) -> Config:
    """加载并校验 sync-targets.json。"""
    try:
        with open(path, "rb") as fh:
            raw = json.loads(fh.read().decode("utf-8"))
    except FileNotFoundError:
        raise SyncError("config_missing", f"找不到配置文件 {path}")
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _cfg_fail(f"{path} 解析失败：{exc}")
    if not isinstance(raw, dict) or not isinstance(raw.get("canon"), dict) or not isinstance(raw.get("targets"), list):
        raise _cfg_fail("顶层必须含 canon（对象）与 targets（数组）")
    canon = raw["canon"]
    for key in ("path", "branch"):
        if not isinstance(canon.get(key), str) or not canon[key]:
            raise _cfg_fail(f"canon.{key} 必须是非空字符串")
    canon_files = _check_files_map(canon.get("files"), "canon")
    block_to_file = {v: k for k, v in canon_files.items()}
    targets: List[Target] = []
    seen = set()
    for i, t in enumerate(raw["targets"]):
        where = f"targets[{i}]"
        if not isinstance(t, dict):
            raise _cfg_fail(f"{where} 必须是对象")
        name = t.get("name")
        if not isinstance(name, str) or not name or name in seen:
            raise _cfg_fail(f"{where}.name 必须是非空且唯一的字符串")
        seen.add(name)
        if not isinstance(t.get("path"), str) or not t["path"]:
            raise _cfg_fail(f"{where}.path 必须是非空字符串")
        files = _check_files_map(t.get("files"), where)
        for f, blk in files.items():
            if blk not in block_to_file:
                raise _cfg_fail(f"{where}.files[{f!r}] 的块 {blk} 在 canon.files 里没有对应的正本文件")
        anchors = t.get("ledger_anchor") or {}
        if not isinstance(anchors, dict):
            raise _cfg_fail(f"{where}.ledger_anchor 必须是对象")
        for f, a in anchors.items():
            if f not in files:
                raise _cfg_fail(f"{where}.ledger_anchor 的文件 {f!r} 不在 files 里")
            if not isinstance(a, str) or not a or "\n" in a or "\r" in a:
                raise _cfg_fail(f"{where}.ledger_anchor[{f!r}] 必须是非空单行字符串")
        targets.append(Target(name, t["path"], t.get("branch"), t.get("remote"), files, dict(anchors)))
    return Config(os.path.abspath(path), canon["path"], canon["branch"], canon_files, block_to_file, targets)


def load_onboard_spec(fixture_dir: str, repo: str, file: str) -> Optional[dict]:
    """从 ``<fixture_dir>/<repo>.json`` 读取文件 file 的 onboard 规格；json 里没有该文件时返回 None。

    返回 dict：start / end / known_region_sha256 / head / tail（原始值）以及 head_bytes / tail_bytes
    （按 fixture_dir 相对路径读出的字节；null 视为空）。note / comment 以及以 "_" 开头的键视为注释、忽略；
    其余未知键报错（防拼写错误）。
    start 与 end 两个键必须显式出现（新建文件写 null）。
    """
    jpath = os.path.join(fixture_dir, f"{repo}.json")
    try:
        with open(jpath, "rb") as fh:
            cfg = json.loads(fh.read().decode("utf-8"))
    except FileNotFoundError:
        raise SyncError("onboard_fixture_missing", f"找不到 onboard 规格 {jpath}")
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SyncError("onboard_fixture_invalid", f"{jpath} 解析失败：{exc}")
    if not isinstance(cfg, dict):
        raise SyncError("onboard_fixture_invalid", f"{jpath} 顶层必须是对象")
    entry = cfg.get(file)
    if entry is None:
        return None
    if not isinstance(entry, dict):
        raise SyncError("onboard_fixture_invalid", f"{jpath} 的 {file} 条目必须是对象")
    unknown = [k for k in entry if k not in ONBOARD_KEYS and k not in ONBOARD_COMMENT_KEYS and not str(k).startswith("_")]
    if unknown:
        raise SyncError("onboard_fixture_invalid", f"{jpath} 的 {file} 条目有未知字段 {unknown}")
    for key in ("start", "end"):
        if key not in entry:
            raise SyncError("onboard_fixture_invalid", f"{jpath} 的 {file} 条目缺少 {key}（新建文件请显式写 null）")
        v = entry[key]
        if v is not None and (not isinstance(v, str) or not v or "\n" in v or "\r" in v):
            raise SyncError("onboard_fixture_invalid", f"{jpath} 的 {file}.{key} 必须是非空单行字符串或 null")
    known = entry.get("known_region_sha256")
    if known is None:
        known = []
    if not isinstance(known, list) or any(not isinstance(x, str) or not _SHA256_RE.fullmatch(x) for x in known):
        raise SyncError("onboard_fixture_invalid", f"{jpath} 的 {file}.known_region_sha256 必须是 64 位小写十六进制字符串数组")
    spec = {"start": entry["start"], "end": entry["end"], "known_region_sha256": list(known)}
    for key in ("head", "tail"):
        name = entry.get(key)
        if name is None:
            spec[key], spec[key + "_bytes"] = None, b""
            continue
        if not isinstance(name, str) or not name or os.path.isabs(name) or ".." in name.replace("\\", "/").split("/"):
            raise SyncError("onboard_fixture_invalid", f"{jpath} 的 {file}.{key} 必须是 fixture 目录内的相对路径：{name!r}")
        p = os.path.join(fixture_dir, name)
        try:
            with open(p, "rb") as fh:
                spec[key], spec[key + "_bytes"] = name, fh.read()
        except FileNotFoundError:
            raise SyncError("onboard_fixture_missing", f"找不到 {key} 文件 {p}")
    # 提前校验 head/tail 内容，报错更早更清楚
    _spec_bytes(spec, "head")
    _spec_bytes(spec, "tail")
    return spec


# ---------------------------------------------------------------------------
# git 只读调用
# ---------------------------------------------------------------------------


def _git(repo: str, args: List[str]) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["GIT_OPTIONAL_LOCKS"] = "0"
    env["LC_ALL"] = "C"
    return subprocess.run(["git", "-C", repo, *args], capture_output=True, env=env)


def git_resolve_commit(repo: str, rev: str) -> Optional[str]:
    r = _git(repo, ["rev-parse", "--verify", "--quiet", "--end-of-options", f"{rev}^{{commit}}"])
    if r.returncode != 0:
        return None
    sha = r.stdout.decode().strip()
    return sha if _SHA40_RE.fullmatch(sha) else None


def git_is_repo(repo: str) -> bool:
    return _git(repo, ["rev-parse", "--git-dir"]).returncode == 0


def git_read_blob(repo: str, spec: str) -> Optional[bytes]:
    """读 ``git cat-file blob <spec>``；对象不存在返回 None。"""
    if _git(repo, ["cat-file", "-e", spec]).returncode != 0:
        return None
    r = _git(repo, ["cat-file", "blob", spec])
    if r.returncode != 0:
        raise SyncError("git_error", f"git -C {repo} cat-file blob {spec} 失败：{_show(r.stderr.strip())}")
    return r.stdout


def git_dirty_entries(repo: str) -> List[str]:
    """返回工作树不干净的条目（git status --porcelain，含未跟踪文件）。"""
    r = _git(repo, ["status", "--porcelain", "--untracked-files=all"])
    if r.returncode != 0:
        raise SyncError("git_error", f"git -C {repo} status 失败：{_show(r.stderr.strip())}")
    return [ln for ln in r.stdout.decode("utf-8", "backslashreplace").split("\n") if ln]


def git_current_branch(repo: str) -> Optional[str]:
    r = _git(repo, ["symbolic-ref", "--short", "-q", "HEAD"])
    return r.stdout.decode().strip() if r.returncode == 0 else None


def git_relation(repo: str, a: str, b: str) -> str:
    """a 相对 b 的关系：same / behind（a 是 b 的祖先）/ ahead / diverged / unknown（对象不存在）。"""
    if a == b:
        return "same"
    for sha in (a, b):
        if _git(repo, ["cat-file", "-e", f"{sha}^{{commit}}"]).returncode != 0:
            return "unknown"
    if _git(repo, ["merge-base", "--is-ancestor", a, b]).returncode == 0:
        return "behind"
    if _git(repo, ["merge-base", "--is-ancestor", b, a]).returncode == 0:
        return "ahead"
    return "diverged"


# ---------------------------------------------------------------------------
# 正本
# ---------------------------------------------------------------------------


class Canon:
    """正本仓库某个 git 版本的只读视图；块内容一律经 git cat-file 读取并先过源 lint。"""

    def __init__(self, cfg: Config, rev_arg: Optional[str] = None):
        self.cfg = cfg
        self.path = cfg.canon_path
        self.rev_arg = rev_arg or f"refs/heads/{cfg.canon_branch}"
        self.sha: Optional[str] = None
        self._blocks: Dict[str, bytes] = {}

    def resolve(self) -> str:
        if not os.path.isdir(self.path):
            raise SyncError("path_absent", f"正本路径不存在：{self.path}")
        sha = git_resolve_commit(self.path, self.rev_arg)
        if sha is None:
            raise SyncError("bad_rev", f"正本 {self.path} 里无法解析版本 {self.rev_arg!r}")
        self.sha = sha
        return sha

    def read_file(self, file: str) -> Optional[bytes]:
        assert self.sha, "先调用 resolve()"
        return git_read_blob(self.path, f"{self.sha}:{file}")

    def block(self, block: str) -> bytes:
        if block in self._blocks:
            return self._blocks[block]
        file = self.cfg.block_to_file[block]
        data = self.read_file(file)
        if data is None:
            raise SyncError("canon_file_absent", f"正本 {self.sha} 里没有 {file}", info={"file": file})
        problems = lint_source(data, block)
        if problems:
            raise SyncError(
                "canon_lint",
                f"正本 {file}@{self.sha[:12]} 源 lint 未通过：" + "；".join(f"{r}（{d}）" for r, d in problems),
                info={"file": file, "reason": problems[0][0]},
            )
        _b0, c0, c1, _e1, _attrs = parse_markers(data, block)
        self._blocks[block] = data[c0:c1]
        return self._blocks[block]


# ---------------------------------------------------------------------------
# 文件读写
# ---------------------------------------------------------------------------


def _read_file(path: str) -> Optional[bytes]:
    """按字节读文件；不存在返回 None。（测试会 monkeypatch 这个函数模拟并发修改。）"""
    try:
        with open(path, "rb") as fh:
            return fh.read()
    except FileNotFoundError:
        return None


def _current_umask() -> int:
    mask = os.umask(0)
    os.umask(mask)
    return mask


def _copy_xattrs(src: str, dst: str) -> None:
    """把 src 的扩展属性（含 system.nfs4_acl / system.posix_acl_access 等 ACL）复制到 dst。

    设置失败时若 dst 上已有相同值则忽略，否则抛 SyncError（宁可不写，也不静默丢 ACL）。
    """
    if not hasattr(os, "listxattr"):
        return
    try:
        names = os.listxattr(src)
    except OSError as exc:
        if exc.errno in (errno.ENOTSUP, errno.EOPNOTSUPP):
            return
        raise SyncError("xattr_copy_failed", f"读取 {src} 扩展属性列表失败：{exc}")
    for name in names:
        try:
            value = os.getxattr(src, name)
        except OSError as exc:
            raise SyncError("xattr_copy_failed", f"读取 {src} 的 {name} 失败：{exc}")
        try:
            os.setxattr(dst, name, value)
        except OSError as exc:
            try:
                current = os.getxattr(dst, name)
            except OSError:
                current = None
            if current != value:
                raise SyncError("xattr_copy_failed", f"无法把 {name} 复制到临时文件：{exc}")


def _atomic_write(path: str, data: bytes, *, exclusive_create: bool, note: Callable[[str], None]) -> None:
    """同目录临时文件 + fsync + （保留权限/属组/xattr）+ os.replace 原子写回。

    exclusive_create=True 时要求目标不存在：用 os.link 原子占位，目标已存在抛 FileExistsError。
    """
    d = os.path.dirname(os.path.abspath(path))
    try:
        st = os.stat(path)
    except FileNotFoundError:
        st = None
    if exclusive_create and st is not None:
        raise FileExistsError(errno.EEXIST, "目标文件已存在", path)
    fd, tmp = tempfile.mkstemp(dir=d, prefix="." + os.path.basename(path) + ".", suffix=".sync-tmp")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        if st is not None:
            try:
                os.chown(tmp, -1, st.st_gid)
            except OSError as exc:
                note(f"警告：无法把临时文件属组设为 {st.st_gid}：{exc}")
            os.chmod(tmp, stat.S_IMODE(st.st_mode))
            _copy_xattrs(path, tmp)
            got = stat.S_IMODE(os.stat(tmp).st_mode)
            if got != stat.S_IMODE(st.st_mode):
                note(f"警告：复制 ACL 后权限位为 {oct(got)}，原文件为 {oct(stat.S_IMODE(st.st_mode))}")
        else:
            os.chmod(tmp, 0o666 & ~_current_umask())
        if exclusive_create:
            try:
                os.link(tmp, path)
            except FileExistsError:
                raise
            except OSError:
                # 文件系统不支持硬链接时退回 replace（仍先确认目标不存在）
                if os.path.lexists(path):
                    raise FileExistsError(errno.EEXIST, "目标文件已存在", path)
                os.replace(tmp, path)
            else:
                os.unlink(tmp)
        else:
            os.replace(tmp, path)
        try:
            dfd = os.open(d, os.O_RDONLY)
            try:
                os.fsync(dfd)
            finally:
                os.close(dfd)
        except OSError:
            pass
    finally:
        if os.path.lexists(tmp):
            try:
                os.unlink(tmp)
            except OSError:
                pass


# ---------------------------------------------------------------------------
# CLI 公共流程
# ---------------------------------------------------------------------------


def _printer(stream) -> Callable[[str], None]:
    def emit(line: str) -> None:
        stream.write(line + "\n")
        stream.flush()

    return emit


def _note(msg: str) -> None:
    sys.stderr.write(msg + "\n")
    sys.stderr.flush()


def _open_canon(cfg: Config, args, emit, *, need_clean: bool) -> Optional[Canon]:
    """解析正本版本（必要时检查工作树干净），打印 CANON 判定行；失败返回 None。"""
    canon = Canon(cfg, getattr(args, "canon_rev", None))
    try:
        canon.resolve()
    except SyncError as exc:
        emit(f"CANON=FAIL reason={exc.reason} path={canon.path} rev={canon.rev_arg}")
        _note(f"错误：{exc.detail}")
        return None
    if need_clean:
        try:
            dirty = git_dirty_entries(canon.path)
        except SyncError as exc:
            emit(f"CANON=FAIL reason={exc.reason} path={canon.path}")
            _note(f"错误：{exc.detail}")
            return None
        if dirty:
            _note("正本工作树不干净（git status --porcelain）：\n  " + "\n  ".join(dirty[:20]) + ("\n  ……" if len(dirty) > 20 else ""))
            if not getattr(args, "allow_dirty", False):
                emit(f"CANON=FAIL reason=dirty_source path={canon.path} dirty_entries={len(dirty)}")
                _note("提示：先提交正本改动；本地调试可加 --allow-dirty 放行（块内容仍取自 git 版本，不读工作树）。")
                return None
            emit(f"CANON=WARN reason=dirty_source path={canon.path} dirty_entries={len(dirty)} allowed=1")
    emit(f"CANON=PASS path={canon.path} rev={canon.rev_arg} sha={canon.sha}")
    return canon


def _load_blocks(canon: Canon, blocks, emit) -> Optional[Dict[str, bytes]]:
    got: Dict[str, bytes] = {}
    for blk in blocks:
        try:
            got[blk] = canon.block(blk)
        except SyncError as exc:
            emit(f"CANON=FAIL reason={exc.reason} file={exc.info.get('file', '-')} block={blk} sha={canon.sha}")
            _note(f"错误：{exc.detail}")
            return None
    return got


def _transform_line(status: str, repo: str, file: str, *, mode: str = "-", bytes_in="-", bytes_out="-",
                    block_blob: str = "-", out_in: str = "-", out_out: str = "-", reason: str = "ok") -> str:
    return (
        f"TRANSFORM={status} repo={repo} file={file} mode={mode} bytes_in={bytes_in} bytes_out={bytes_out} "
        f"block_blob={block_blob} outside_sha256_in={out_in} outside_sha256_out={out_out} reason={reason}"
    )


def _run_transform(emit, repo: str, file: str, block: str, data: bytes, canon_block: bytes, canon_sha: str,
                   onboard_spec: Optional[dict], ledger_anchor: Optional[str]) -> Tuple[str, Optional[TransformResult]]:
    """执行一次变换并打印全部判定行（ONBOARD/INVARIANT/LEDGER_BYTES/TRANSFORM），返回 (状态, 结果)。"""
    prob = eol_problem(data)
    if prob:
        emit(f"EOL=FAIL repo={repo} file={file} reason={prob}")
        emit(_transform_line("FAIL", repo, file, bytes_in=len(data), reason="eol"))
        _note(f"错误：{repo}/{file} 含 {prob}，不自动转换换行/BOM，请先人工处理")
        return "FAIL", None
    try:
        res = transform_detail(data, block, canon_block, canon_sha, onboard_spec)
    except SyncError as exc:
        reg = exc.info.get("region")
        if reg:
            emit(
                f"ONBOARD_REGION={reg['status']} repo={repo} file={file} start={_q(reg['start'])} "
                f"end={_q(reg['end'])} bytes={reg['bytes']} sha256={reg['sha256']}"
            )
        emit(_transform_line("FAIL", repo, file, bytes_in=len(data), reason=exc.reason))
        _note(f"错误：{repo}/{file} 变换失败：{exc.detail or exc.reason}")
        return "FAIL", None
    if res.onboard_skipped:
        emit(f"ONBOARD=SKIP repo={repo} file={file} reason=markers_present")
    if res.region:
        reg = res.region
        emit(
            f"ONBOARD_REGION={reg['status']} repo={repo} file={file} start={_q(reg['start'])} "
            f"end={_q(reg['end'])} bytes={reg['bytes']} sha256={reg['sha256']}"
        )
    failed = []
    for name, status, detail in verify_invariants(data, res, block, canon_block, canon_sha, onboard_spec):
        emit(f"INVARIANT={status} name={name} repo={repo} file={file}")
        if status == "FAIL":
            failed.append(name)
            _note(f"错误：不变式 {name} 失败：{detail}")
    if ledger_anchor is not None:
        led = check_ledger(data, res.out, ledger_anchor)
        emit(
            f"LEDGER_BYTES={led['status']} repo={repo} file={file} from={_q(ledger_anchor)} "
            f"bytes={led['bytes'] if led['bytes'] is not None else '-'} sha256={led['sha256'] or '-'} reason={led['reason']}"
        )
        if led["status"] != "PASS":
            failed.append("ledger")
            _note(f"错误：账本区（{ledger_anchor} 起到文件尾）校验失败：{led['reason']}")
    o_in, o_out = outside_digests(data, res)
    if failed:
        status = "FAIL"
        reason = "invariant_" + "+".join(failed)
    else:
        status = "NOOP" if res.mode == "noop" else "PASS"
        reason = "ok"
    emit(
        _transform_line(status, repo, file, mode=res.mode, bytes_in=len(data), bytes_out=len(res.out),
                        block_blob=res.block_blob, out_in=o_in, out_out=o_out, reason=reason)
    )
    return status, (None if status == "FAIL" else res)


def apply_to_path(emit, repo: str, file: str, path: str, block: str, canon_block: bytes, canon_sha: str,
                  onboard_spec: Optional[dict], ledger_anchor: Optional[str]) -> str:
    """对单个工作树文件做 transform 并原子写回；返回 PASS / NOOP / FAIL（并打印 APPLY 判定行）。

    写前重读一次，确认与变换时读到的字节一致，不一致则重试（最多 MAX_APPLY_ATTEMPTS 次）；NOOP 不写。
    绝不调用任何 git 写操作。
    """
    if os.path.islink(path):
        emit(f"APPLY=FAIL repo={repo} file={file} reason=symlink path={path}")
        _note(f"错误：{path} 是符号链接，拒绝原子替换（会把链接替换成普通文件）")
        return "FAIL"
    for attempt in range(1, MAX_APPLY_ATTEMPTS + 1):
        before = _read_file(path)
        absent = before is None
        if absent and not (onboard_spec is not None and onboard_spec.get("start") is None):
            emit(f"APPLY=FAIL repo={repo} file={file} reason=file_absent path={path}")
            _note(f"错误：{path} 不存在；新建文件需在 onboard 规格里写 start=null")
            return "FAIL"
        data = b"" if absent else before
        status, res = _run_transform(emit, repo, file, block, data, canon_block, canon_sha, onboard_spec, ledger_anchor)
        if status == "FAIL":
            emit(f"APPLY=FAIL repo={repo} file={file} reason=transform_failed path={path}")
            return "FAIL"
        if status == "NOOP":
            emit(f"APPLY=NOOP repo={repo} file={file} mode=noop bytes={len(data)} attempts={attempt} path={path}")
            return "NOOP"
        again = _read_file(path)
        if again != before:
            _note(f"提示：{path} 在读取后被修改（第 {attempt} 次尝试），重新读取再变换")
            continue
        try:
            _atomic_write(path, res.out, exclusive_create=absent, note=_note)
        except FileExistsError:
            _note(f"提示：{path} 在新建前被他人创建（第 {attempt} 次尝试），重新读取再变换")
            continue
        except SyncError as exc:
            emit(f"APPLY=FAIL repo={repo} file={file} reason={exc.reason} path={path}")
            _note(f"错误：{exc.detail}")
            return "FAIL"
        except OSError as exc:
            emit(f"APPLY=FAIL repo={repo} file={file} reason=write_error path={path}")
            _note(f"错误：写入 {path} 失败：{exc}")
            return "FAIL"
        verify = _read_file(path)
        if verify != res.out:
            emit(f"APPLY=FAIL repo={repo} file={file} reason=post_write_mismatch path={path}")
            _note(f"错误：写回后重读 {path} 与预期不一致（可能有并发写入），请人工检查")
            return "FAIL"
        emit(
            f"APPLY=PASS repo={repo} file={file} mode={res.mode} bytes_in={len(data)} bytes_out={len(res.out)} "
            f"attempts={attempt} path={path}"
        )
        return "PASS"
    emit(f"APPLY=FAIL repo={repo} file={file} reason=concurrent_modification attempts={MAX_APPLY_ATTEMPTS} path={path}")
    _note(f"错误：{path} 连续 {MAX_APPLY_ATTEMPTS} 次在读取后被修改，放弃写入")
    return "FAIL"


def _warn_branch(emit, target: Target) -> None:
    if not target.branch or not git_is_repo(target.path):
        return
    cur = git_current_branch(target.path)
    if cur != target.branch:
        emit(f"BRANCH=WARN repo={target.name} expected={target.branch} actual={cur or 'DETACHED'}")


# ---------------------------------------------------------------------------
# 子命令
# ---------------------------------------------------------------------------


def cmd_blocks(args) -> int:
    emit = _printer(sys.stdout)
    cfg = load_config(args.targets)
    files = list(cfg.canon_files)
    if args.file:
        if args.file not in cfg.canon_files:
            _note(f"错误：--file {args.file!r} 不在 canon.files {files} 中")
            return EXIT_FAIL
        files = [args.file]
    canon = _open_canon(cfg, args, emit, need_clean=False)
    if canon is None:
        return EXIT_FAIL
    rc = EXIT_OK
    for f in files:
        blk = cfg.canon_files[f]
        try:
            content = canon.block(blk)
        except SyncError as exc:
            emit(f"BLOCK=FAIL file={f} block={blk} reason={exc.info.get('reason', exc.reason)} canon_rev={canon.sha}")
            _note(f"错误：{exc.detail}")
            rc = EXIT_FAIL
            continue
        n_lines = content.count(b"\n")
        emit(
            f"BLOCK={blk} file={f} blob={git_blob_id(content)} bytes={len(content)} "
            f"lines={n_lines} canon_rev={canon.sha}"
        )
    return rc


def cmd_lint(args) -> int:
    emit = _printer(sys.stdout)
    cfg = load_config(args.targets)
    canon = _open_canon(cfg, args, emit, need_clean=False)
    if canon is None:
        return EXIT_FAIL
    n_pass = n_fail = 0
    for f, blk in cfg.canon_files.items():
        if args.worktree:
            where = "worktree"
            data = _read_file(os.path.join(canon.path, f))
        else:
            where = f"rev:{canon.sha}"
            data = canon.read_file(f)
        if data is None:
            emit(f"LINT=FAIL file={f} block={blk} where={where} reason=file_absent")
            n_fail += 1
            continue
        problems = lint_source(data, blk)
        if problems:
            emit(f"LINT=FAIL file={f} block={blk} where={where} reason={problems[0][0]}")
            for r, d in problems:
                _note(f"  {f}: {r}：{d}")
            n_fail += 1
            continue
        _b0, c0, c1, _e1, _a = parse_markers(data, blk)
        content = data[c0:c1]
        n_lines = content.count(b"\n")
        emit(
            f"LINT=PASS file={f} block={blk} where={where} blob={git_blob_id(content)} "
            f"bytes={len(content)} lines={n_lines}"
        )
        n_pass += 1
    emit(f"LINT_SUMMARY={'FAIL' if n_fail else 'PASS'} pass={n_pass} fail={n_fail}")
    return EXIT_DRIFT if n_fail else EXIT_OK


def cmd_transform(args) -> int:
    to_stdout = args.output == "-"
    # 输出字节走 stdout 时，判定行改走 stderr，避免污染输出。
    emit = _printer(sys.stderr if to_stdout else sys.stdout)
    cfg = load_config(args.targets)
    target = cfg.target(args.repo)
    if args.file not in target.files:
        _note(f"错误：--file {args.file!r} 不在目标 {target.name} 的 files {list(target.files)} 中")
        return EXIT_FAIL
    block = target.files[args.file]
    canon = _open_canon(cfg, args, emit, need_clean=False)
    if canon is None:
        return EXIT_FAIL
    blocks = _load_blocks(canon, [block], emit)
    if blocks is None:
        return EXIT_FAIL
    onboard_spec = None
    if args.onboard:
        try:
            onboard_spec = load_onboard_spec(args.onboard, target.name, args.file)
        except SyncError as exc:
            emit(_transform_line("FAIL", target.name, args.file, reason=exc.reason))
            _note(f"错误：{exc.detail}")
            return EXIT_FAIL
    if args.input == "-":
        data: Optional[bytes] = sys.stdin.buffer.read()
    else:
        in_path = args.input or os.path.join(target.path, args.file)
        data = _read_file(in_path)
    if data is None:
        if onboard_spec is not None and onboard_spec.get("start") is None:
            data = b""
        else:
            emit(_transform_line("FAIL", target.name, args.file, reason="file_absent"))
            _note(f"错误：输入文件不存在：{in_path}")
            return EXIT_FAIL
    if onboard_spec is None and args.onboard:
        # fixture 里没有该文件的条目：输入有标记时照常走普通模式，没有则由 transform 报 markers_absent
        _note(f"提示：{args.onboard}/{target.name}.json 里没有 {args.file} 的条目，按普通模式处理")
    status, res = _run_transform(emit, target.name, args.file, block, data, blocks[block], canon.sha,
                                 onboard_spec, target.ledger_anchor.get(args.file))
    if status == "FAIL":
        return EXIT_FAIL
    if to_stdout:
        sys.stdout.flush()
        sys.stdout.buffer.write(res.out)
        sys.stdout.buffer.flush()
    else:
        try:
            if os.path.exists(args.output) and not os.path.isfile(args.output):
                # /dev/null 之类的非普通文件：直接写，不做原子替换
                with open(args.output, "wb") as fh:
                    fh.write(res.out)
            else:
                _atomic_write(args.output, res.out, exclusive_create=False, note=_note)
        except (OSError, SyncError) as exc:
            _note(f"错误：写输出文件 {args.output} 失败：{exc}")
            return EXIT_FAIL
    return EXIT_NOOP if status == "NOOP" else EXIT_OK


def cmd_check(args) -> int:
    emit = _printer(sys.stdout)
    cfg = load_config(args.targets)
    if args.rev and args.where:
        _note("错误：--rev 与 --where 不能同时使用")
        return EXIT_FAIL
    targets = [cfg.target(args.repo)] if args.repo else list(cfg.targets)
    canon = _open_canon(cfg, args, emit, need_clean=True)
    if canon is None:
        return EXIT_FAIL
    need = sorted({blk for t in targets for blk in t.files.values()})
    blocks = _load_blocks(canon, need, emit)
    if blocks is None:
        return EXIT_FAIL
    where = "worktree" if not (args.rev or args.where) else (f"rev:{args.rev}" if args.rev else args.where)
    n_pass = n_fail = n_missing = 0

    def sync_line(status, t, f, reason, file_src="-", file_blob="-", blk=None):
        canon_blob = git_blob_id(blocks[blk]) if blk else "-"
        emit(
            f"SYNC={status} repo={t.name} file={f} where={where} file_src={file_src} file_blob={file_blob} "
            f"canon_rev={canon.sha} canon_blob={canon_blob} reason={reason}"
        )

    for t in targets:
        if not os.path.isdir(t.path):
            for f, blk in t.files.items():
                sync_line("MISSING", t, f, "path_absent", blk=blk)
                n_missing += 1
            continue
        rev_sha = None
        if where != "worktree":
            if not git_is_repo(t.path):
                for f, blk in t.files.items():
                    sync_line("FAIL", t, f, "not_git_repo", blk=blk)
                    n_fail += 1
                continue
            if where != "index":
                rev_sha = git_resolve_commit(t.path, args.rev or "HEAD")
                if rev_sha is None:
                    for f, blk in t.files.items():
                        sync_line("FAIL", t, f, "bad_rev", blk=blk)
                        n_fail += 1
                    continue
        if not args.rev:
            _warn_branch(emit, t)
        for f, blk in t.files.items():
            try:
                if where == "worktree":
                    data = _read_file(os.path.join(t.path, f))
                elif where == "index":
                    data = git_read_blob(t.path, f":{f}")
                else:
                    data = git_read_blob(t.path, f"{rev_sha}:{f}")
            except SyncError as exc:
                sync_line("FAIL", t, f, exc.reason, blk=blk)
                _note(f"错误：{exc.detail}")
                n_fail += 1
                continue
            if data is None:
                sync_line("MISSING", t, f, "file_absent", blk=blk)
                n_missing += 1
                continue
            prob = eol_problem(data)
            if prob:
                emit(f"EOL=FAIL repo={t.name} file={f} reason={prob}")
                sync_line("FAIL", t, f, "eol", blk=blk)
                n_fail += 1
                continue
            try:
                _b0, c0, c1, _e1, attrs = parse_markers(data, blk)
            except SyncError as exc:
                sync_line("FAIL", t, f, exc.reason, blk=blk)
                _note(f"  {t.name}/{f}: {exc.detail}")
                n_fail += 1
                continue
            content = data[c0:c1]
            actual = git_blob_id(content)
            src = attrs.get("src", "-")
            if attrs and attrs["blob"] != actual:
                emit(f"BLOB_MISMATCH=FAIL repo={t.name} file={f} where={where} attr_blob={attrs['blob']} actual_blob={actual}")
            canon_block = blocks[blk]
            if content != canon_block:
                reason = "content_drift"
                _note(f"  {t.name}/{f}: 块内容与正本不同（{_first_diff(content, canon_block)}）")
            elif not attrs:
                reason = "missing_attrs"
            elif attrs["blob"] != actual:
                reason = "blob_mismatch"
            else:
                reason = "ok"
            if reason == "ok":
                sync_line("PASS", t, f, reason, src, actual, blk)
                n_pass += 1
                if src != canon.sha:
                    rel = git_relation(canon.path, src, canon.sha)
                    emit(f"SHA_STALE=INFO repo={t.name} file={f} file_src={src} canon_rev={canon.sha} relation={rel}")
            else:
                sync_line("FAIL", t, f, reason, src, actual, blk)
                n_fail += 1
    ok = n_fail == 0 and n_missing == 0
    emit(f"SYNC_SUMMARY={'PASS' if ok else 'FAIL'} pass={n_pass} fail={n_fail} missing={n_missing}")
    return EXIT_OK if ok else EXIT_DRIFT


def _first_diff(a: bytes, b: bytes) -> str:
    la, lb = a.split(b"\n"), b.split(b"\n")
    for i, (x, y) in enumerate(zip(la, lb), 1):
        if x != y:
            return f"块内第 {i} 行起不同；副本：{_show(x, 60)!r}；正本：{_show(y, 60)!r}"
    na, nb = a.count(b"\n"), b.count(b"\n")
    return f"行数不同：副本 {na} 行，正本 {nb} 行"


def cmd_apply(args) -> int:
    emit = _printer(sys.stdout)
    cfg = load_config(args.targets)
    target = cfg.target(args.repo)
    files = list(target.files)
    if args.file:
        if args.file not in target.files:
            _note(f"错误：--file {args.file!r} 不在目标 {target.name} 的 files {files} 中")
            return EXIT_FAIL
        files = [args.file]
    canon = _open_canon(cfg, args, emit, need_clean=True)
    if canon is None:
        return EXIT_FAIL
    blocks = _load_blocks(canon, sorted({target.files[f] for f in files}), emit)
    if blocks is None:
        return EXIT_FAIL
    n = {"PASS": 0, "NOOP": 0, "FAIL": 0}
    if not os.path.isdir(target.path):
        for f in files:
            emit(f"APPLY=FAIL repo={target.name} file={f} reason=path_absent path={os.path.join(target.path, f)}")
        emit(f"APPLY_SUMMARY=FAIL written=0 noop=0 fail={len(files)}")
        return EXIT_FAIL
    _warn_branch(emit, target)
    for f in files:
        blk = target.files[f]
        spec = None
        if args.onboard:
            try:
                spec = load_onboard_spec(args.onboard, target.name, f)
            except SyncError as exc:
                emit(f"APPLY=FAIL repo={target.name} file={f} reason={exc.reason}")
                _note(f"错误：{exc.detail}")
                n["FAIL"] += 1
                continue
        status = apply_to_path(emit, target.name, f, os.path.join(target.path, f), blk, blocks[blk], canon.sha,
                               spec, target.ledger_anchor.get(f))
        n[status] += 1
    emit(f"APPLY_SUMMARY={'FAIL' if n['FAIL'] else 'PASS'} written={n['PASS']} noop={n['NOOP']} fail={n['FAIL']}")
    return EXIT_FAIL if n["FAIL"] else EXIT_OK


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------

_EPILOG = """\
判定行一律打印到 stdout（transform 输出字节走 stdout 时改走 stderr），错误说明打印到 stderr。
退出码：
  blocks     0 全部成功 / 2 失败
  transform  0 有改动 / 3 NOOP / 2 FAIL
  check      0 全部 PASS / 1 有 FAIL 或 MISSING / 2 正本或配置错误
  apply      0 全部写入或 NOOP / 2 有 FAIL
  lint       0 全部 PASS / 1 有 FAIL / 2 正本或配置错误
本脚本绝不执行 git add / commit / push；git 调用全部只读。
"""


# argparse 内置提示语的中文化（仅替换本脚本用到的几条，其余保持原文）。
_ARGPARSE_ZH = {
    "usage: ": "用法：",
    "positional arguments": "位置参数",
    "options": "选项",
    "show this help message and exit": "显示本帮助并退出",
    "%(prog)s: error: %(message)s\n": "%(prog)s：错误：%(message)s\n",
    "the following arguments are required: %s": "缺少必需参数：%s",
    "unrecognized arguments: %s": "无法识别的参数：%s",
    "argument %(argument_name)s: %(message)s": "参数 %(argument_name)s：%(message)s",
    "invalid choice: %(value)r (choose from %(choices)s)": "无效取值 %(value)r（可选：%(choices)s）",
    "expected one argument": "需要一个参数值",
}


def _localize_argparse() -> None:
    orig = getattr(argparse, "_sync_rules_orig_gettext", None) or argparse._
    argparse._sync_rules_orig_gettext = orig
    argparse._ = lambda text: _ARGPARSE_ZH.get(text, orig(text))


def build_parser() -> argparse.ArgumentParser:
    _localize_argparse()
    parser = argparse.ArgumentParser(
        prog="sync_rules.py",
        description="AgentMetaRules 通用块同步工具：从正本 git 版本提取通用块、变换项目副本、比对漂移。",
        epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="cmd", required=True, metavar="子命令")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--targets", default=DEFAULT_TARGETS, help="同步配置 JSON（默认：仓库根的 sync-targets.json）")
    common.add_argument(
        "--canon-rev",
        default=None,
        help="正本 git 版本（默认：canon.branch 分支的 HEAD，即 refs/heads/<branch>）；块内容一律经 git cat-file 读取",
    )

    p = sub.add_parser("blocks", parents=[common], help="打印正本各块的 blob id、字节数、行数",
                       description="打印正本各块的 blob id、字节数、行数（BLOCK=<块名> file=… blob=… bytes=… lines=…）。")
    p.add_argument("--file", help="只看某个正本文件（如 AGENTS.md）")
    p.set_defaults(func=cmd_blocks)

    p = sub.add_parser("transform", parents=[common], help="读输入字节、输出替换通用块后的字节",
                       description="读输入字节，输出替换通用块后的字节；块外字节逐字节不变。退出码 0 有改动 / 3 NOOP / 2 FAIL。")
    p.add_argument("--repo", required=True, help="sync-targets.json 里的目标名（决定文件与块名的对应、ledger_anchor）")
    p.add_argument("--file", required=True, help="目标文件名（必须是该目标 files 里的键）")
    p.add_argument("--onboard", metavar="FIXTURE_DIR", help="首次接入模式：读取 <FIXTURE_DIR>/<repo>.json 的锚点规格")
    p.add_argument("--input", metavar="PATH|-", help="输入文件（默认：目标工作树里的该文件；- 表示 stdin）")
    p.add_argument("--output", metavar="PATH|-", default="-", help="输出位置（默认 -，即 stdout；此时判定行改走 stderr）")
    p.set_defaults(func=cmd_transform)

    p = sub.add_parser("check", parents=[common], help="比对各目标文件的块字节是否等于正本块",
                       description="比对各目标文件的块字节是否等于正本块；任一 FAIL/MISSING 退出 1。")
    p.add_argument("--repo", help="只检查某个目标（默认全部）")
    p.add_argument("--rev", help="读目标仓库某个 git 版本（git cat-file blob <rev>:<file>），与 --where 互斥")
    p.add_argument("--where", choices=("worktree", "head", "index"), help="读工作树（默认）/ HEAD / index")
    p.add_argument("--allow-dirty", action="store_true", help="正本工作树不干净时也放行（本地调试用）")
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("apply", parents=[common], help="对目标工作树文件做 transform 并原子写回（不做任何 git 写操作）",
                       description="对目标工作树文件做 transform 并原子写回（同目录临时文件 + os.replace，保留权限/属组/xattr）；"
                                   "写前重读确认未被并发修改，否则重试最多 3 次；NOOP 不写。绝不执行 git add/commit/push。")
    p.add_argument("--repo", required=True, help="sync-targets.json 里的目标名")
    p.add_argument("--file", help="只处理某个文件（默认该目标的全部文件）")
    p.add_argument("--onboard", metavar="FIXTURE_DIR", help="首次接入模式：读取 <FIXTURE_DIR>/<repo>.json 的锚点规格")
    p.add_argument("--allow-dirty", action="store_true", help="正本工作树不干净时也放行（本地调试用）")
    p.set_defaults(func=cmd_apply)

    p = sub.add_parser("lint", parents=[common], help="对正本三文件做源 lint",
                       description="对正本三文件做源 lint：标记存在且唯一、BEGIN 无属性、块内无标记行、块以 \\n 结尾、无 \\r/BOM。")
    p.add_argument("--worktree", action="store_true", help="改为 lint 正本工作树文件（仅供提交前自查；其余子命令从不读工作树）")
    p.set_defaults(func=cmd_lint)
    return parser


def _setup_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="backslashreplace")
        except (AttributeError, ValueError):
            pass


def main(argv: Optional[List[str]] = None) -> int:
    _setup_stdio()
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except SyncError as exc:
        print(f"CONFIG=FAIL reason={exc.reason}", flush=True)
        _note(f"错误：{exc.detail or exc.reason}")
        return EXIT_FAIL


if __name__ == "__main__":
    sys.exit(main())
