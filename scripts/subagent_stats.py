#!/usr/bin/env python3
"""子代理超时统计：记录运行超过 15 分钟的 Claude Code 子代理，按项目与全局各落一份。

用法（均只用标准库，经 `uv run --no-project --quiet python` 运行）：
  hook                SubagentStop hook 入口，从 stdin 读 hook 输入 JSON；任何异常都只写错误日志、退出码 0
  backfill [--dry-run] 扫 ~/.claude/projects 下历史子代理转录，补录超过阈值且尚未记录的条目
  summarize [--file F] [--project ROOT]  按类型与模型汇总，输出 Markdown 表

落盘位置：
  全局   ~/.claude/subagent-stats/over-15min.jsonl（所有项目、所有目录）
  项目   <项目主检出>/docs/subagent-stats/over-15min.jsonl，仅限已接入 AgentMetaRules 的仓库
         （CLAUDE.md 或 AGENTS.md 含 AGENTMETARULES 标记块，或就是正本仓库本身）
时长取子代理转录首末两条记录的 timestamp 之差；同一 agent_id 被续接后再次停止会追加新行，
汇总时按 agent_id 只取最后一行。
"""
import argparse
import collections
import fcntl
import glob
import json
import os
import statistics
import subprocess
import sys
import traceback
from datetime import datetime, timezone

THRESHOLD_S = 15 * 60
CANON = "/data/hongzefu/AgentMetaRules-hongzefu"
HOME = os.path.expanduser("~")
GLOBAL_DIR = os.path.join(HOME, ".claude", "subagent-stats")
GLOBAL_FILE = os.path.join(GLOBAL_DIR, "over-15min.jsonl")
ERROR_LOG = os.path.join(GLOBAL_DIR, "hook-errors.log")
PROJECT_REL = os.path.join("docs", "subagent-stats", "over-15min.jsonl")
MARKER = "AGENTMETARULES:BEGIN"


def _parse_ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def read_transcript(path):
    """返回首末时间戳、工具调用数、实际模型、cwd、分支、会话号、版本。"""
    first = last = None
    tool_uses = 0
    models = collections.Counter()
    cwd = branch = session = version = None
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                d = json.loads(line)
            except ValueError:
                continue
            ts = d.get("timestamp")
            if ts:
                first = first or ts
                last = ts
            cwd = cwd or d.get("cwd")
            branch = branch or d.get("gitBranch")
            session = session or d.get("sessionId")
            version = version or d.get("version")
            msg = d.get("message")
            if d.get("type") == "assistant" and isinstance(msg, dict):
                if msg.get("model"):
                    models[msg["model"]] += 1
                for block in msg.get("content") or []:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        tool_uses += 1
    return {
        "start": first,
        "end": last,
        "tool_uses": tool_uses,
        "model_actual": models.most_common(1)[0][0] if models else None,
        "cwd": cwd,
        "git_branch": branch,
        "session_id": session,
        "cc_version": version,
    }


def read_meta(transcript_path):
    meta_path = transcript_path[: -len(".jsonl")] + ".meta.json"
    try:
        with open(meta_path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def project_root(cwd):
    """把 cwd（可能是已删除的 worktree）解析成主检出根；解析不到返回 None。"""
    if not cwd:
        return None
    cand = cwd
    if not os.path.isdir(cand) and "/.claude/worktrees/" in cand:
        cand = cand.split("/.claude/worktrees/")[0]
    if not os.path.isdir(cand):
        return None
    try:
        out = subprocess.run(
            ["git", "-C", cand, "rev-parse", "--path-format=absolute", "--git-common-dir"],
            capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if out.returncode != 0:
        return None
    common = out.stdout.strip()
    return os.path.dirname(common) if common.endswith("/.git") else None


def adopted(root):
    if not root:
        return False
    if os.path.realpath(root) == os.path.realpath(CANON):
        return True
    for name in ("CLAUDE.md", "AGENTS.md"):
        try:
            with open(os.path.join(root, name), encoding="utf-8") as f:
                if MARKER in f.read():
                    return True
        except OSError:
            pass
    return False


def build_record(transcript_path, agent_id=None, agent_type=None, source="hook"):
    t = read_transcript(transcript_path)
    if not t["start"] or not t["end"]:
        return None
    dur = (_parse_ts(t["end"]) - _parse_ts(t["start"])).total_seconds()
    meta = read_meta(transcript_path)
    aid = agent_id or os.path.basename(transcript_path)[len("agent-"): -len(".jsonl")]
    root = project_root(t["cwd"])
    return {
        "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": source,
        "agent_id": aid,
        "agent_type": agent_type or meta.get("agentType"),
        "description": meta.get("description"),
        "model_requested": meta.get("model"),
        "model_actual": t["model_actual"],
        "spawn_depth": meta.get("spawnDepth"),
        "request_shape": meta.get("requestShape"),
        "workflow": "/workflows/" in transcript_path,
        "start": t["start"],
        "end": t["end"],
        "duration_s": round(dur, 1),
        "duration_min": round(dur / 60, 1),
        "tool_uses": t["tool_uses"],
        "session_id": t["session_id"],
        "project_root": root,
        "cwd": t["cwd"],
        "git_branch": t["git_branch"],
        "cc_version": t["cc_version"],
        "transcript": transcript_path,
    }


def append_line(path, rec):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            f.flush()
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def targets(rec):
    out = [GLOBAL_FILE]
    if adopted(rec.get("project_root")):
        out.append(os.path.join(rec["project_root"], PROJECT_REL))
    test_dir = os.environ.get("SUBAGENT_STATS_TEST_DIR")  # 仅供测试：所有写入改落到该目录
    if test_dir:
        out = [os.path.join(test_dir, "global.jsonl")] + [
            os.path.join(test_dir, "project-%s.jsonl" % os.path.basename(rec["project_root"])) for _ in out[1:]]
    return out


def load(path):
    rows = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        rows.append(json.loads(line))
                    except ValueError:
                        pass
    except OSError:
        pass
    return rows


def cmd_hook():
    try:
        inp = json.load(sys.stdin)
        tp = inp.get("agent_transcript_path")
        if not tp and inp.get("transcript_path") and inp.get("agent_id"):
            base = os.path.splitext(inp["transcript_path"])[0]
            tp = os.path.join(base, "subagents", "agent-%s.jsonl" % inp["agent_id"])
        os.makedirs(GLOBAL_DIR, exist_ok=True)
        with open(os.path.join(GLOBAL_DIR, "last-hook.json"), "w", encoding="utf-8") as f:  # 心跳：证明 hook 在跑
            json.dump({"at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                       "agent_id": inp.get("agent_id"), "agent_type": inp.get("agent_type")}, f)
        if not tp or not os.path.isfile(tp):
            return 0
        rec = build_record(tp, inp.get("agent_id"), inp.get("agent_type"), "hook")
        if rec and rec["duration_s"] > THRESHOLD_S:
            if not rec["cwd"]:
                rec["cwd"] = inp.get("cwd")
                rec["project_root"] = project_root(inp.get("cwd"))
            for p in targets(rec):
                append_line(p, rec)
    except Exception:  # hook 绝不能打断会话
        os.makedirs(GLOBAL_DIR, exist_ok=True)
        with open(ERROR_LOG, "a", encoding="utf-8") as f:
            f.write(datetime.now(timezone.utc).isoformat() + "\n" + traceback.format_exc() + "\n")
    return 0


def cmd_backfill(dry_run):
    seen = {}
    for p in [GLOBAL_FILE]:
        seen[p] = {r.get("agent_id") for r in load(p)}
    paths = sorted(glob.glob(os.path.join(HOME, ".claude", "projects", "**", "agent-*.jsonl"), recursive=True))
    added = collections.Counter()
    over = 0
    for tp in paths:
        try:
            rec = build_record(tp, source="backfill")
        except Exception:
            continue
        if not rec or rec["duration_s"] <= THRESHOLD_S:
            continue
        over += 1
        for p in targets(rec):
            if p not in seen:
                seen[p] = {r.get("agent_id") for r in load(p)}
            if rec["agent_id"] in seen[p]:
                continue
            seen[p].add(rec["agent_id"])
            added[p] += 1
            if not dry_run:
                append_line(p, rec)
    print("BACKFILL scanned=%d over_threshold=%d dry_run=%s" % (len(paths), over, dry_run))
    for p, n in sorted(added.items()):
        print("  +%d  %s" % (n, p))
    return 0


def cmd_summarize(path, project):
    rows = load(path)
    if project:
        rows = [r for r in rows if r.get("project_root") == project]
    last = {}
    for r in rows:
        last[r.get("agent_id")] = r
    rows = list(last.values())
    print("# 超过 15 分钟的子代理统计\n")
    print("来源 `%s`，去重后 %d 条。\n" % (path, len(rows)))
    if not rows:
        return 0

    def table(title, keyf):
        groups = collections.defaultdict(list)
        for r in rows:
            groups[keyf(r)].append(r["duration_min"])
        print("## %s\n" % title)
        print("| 分组 | 个数 | 总时长（分钟） | 中位数 | 最长 |")
        print("|---|---|---|---|---|")
        for k, v in sorted(groups.items(), key=lambda kv: -sum(kv[1])):
            print("| %s | %d | %.0f | %.1f | %.1f |" % (k, len(v), sum(v), statistics.median(v), max(v)))
        print()

    table("按子代理类型", lambda r: "%s%s" % (r.get("agent_type") or "?", "（workflow）" if r.get("workflow") else ""))
    table("按请求模型", lambda r: r.get("model_requested") or r.get("model_actual") or "?")
    table("按项目", lambda r: r.get("project_root") or "（非仓库目录）")
    print("## 最长的 15 个\n")
    print("| 分钟 | 类型 | 模型 | 描述 | 项目 | 结束时间 |")
    print("|---|---|---|---|---|---|")
    for r in sorted(rows, key=lambda r: -r["duration_min"])[:15]:
        print("| %.1f | %s | %s | %s | %s | %s |" % (
            r["duration_min"], r.get("agent_type"), r.get("model_requested") or r.get("model_actual"),
            (r.get("description") or "").replace("|", "／"),
            os.path.basename(r.get("project_root") or "") or "—", (r.get("end") or "")[:16]))
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("hook")
    b = sub.add_parser("backfill")
    b.add_argument("--dry-run", action="store_true")
    s = sub.add_parser("summarize")
    s.add_argument("--file", default=GLOBAL_FILE)
    s.add_argument("--project")
    a = ap.parse_args()
    if a.cmd == "hook":
        return cmd_hook()
    if a.cmd == "backfill":
        return cmd_backfill(a.dry_run)
    return cmd_summarize(a.file, a.project)


if __name__ == "__main__":
    sys.exit(main())
