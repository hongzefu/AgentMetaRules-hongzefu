#!/usr/bin/env bash
# rehearse_land.sh —— land_rules_commit.py 的彩排脚本（只在自建临时仓库里跑，绝不碰任何真实仓库）
#
# 用法：
#   bash scripts/rehearse_land.sh <工作目录> [stub|module|both]
#
#   <工作目录>  必须不在任何 git 仓库内（脚本会检查）；其下 <模式>/ 子目录每次清空重建
#   stub       transform 用外部命令桩（与 sync_rules 解耦，缺省）
#   module     transform 直接导入同目录 sync_rules.py（自建正本仓库 + sync-targets.json + onboard 规格）
#   both       两种各跑一遍全部八个场景
#
# 每个环境 = remote.git（bare）+ local（领先 2 个提交、索引里有他人暂存、工作树有未暂存追加、有未跟踪文件）
#          + other（第三方 clone，用来制造远端竞态）。八个场景：
#   ① remote 正常推送快进（含审阅 diff 生成 / 篡改负例 / 逐字节比对）
#   ② merge 正常落地，HUNKSET_EQUAL / STATUS_EQUAL / FF_READY 全 PASS，第一父 diff 只有三文件
#   ③ 远端竞态：B4 与 B5 之间第三方推送 → PUSH=REJECTED（git 拒绝与推前复核两种），日志不出现强推字样
#   ④ 本地竞态：C4 期间每 10 ms 追加 AGENTS.md（400 行）+ 每 50 ms 尝试提交 → 行数与顺序完整、提交因锁失败、verify PASS
#   ⑤ 幂等：再跑 remote 与 merge 都 NOOP、不产生新提交
#   ⑥ 以后推送：Codex 提交后裸 git push 快进成功；git pull --rebase 预期冲突并 abort
#   ⑦ 回滚演练：注入失败自动回滚两例 + rollback 子命令撤销一次真实落地
#   ⑧ FEASIBLE=FAIL：在途 hunk 落在被替换区域（工作树 / 索引各一例）→ merge 退出 3 且远端不推
# 末行输出 REHEARSAL=PASS scenarios=8；任一断言失败输出 SCENARIO_n=FAIL 与 REHEARSAL=FAIL 并以 1 退出。
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
LAND="$SCRIPT_DIR/land_rules_commit.py"
BR=newtaskRelease-v5
FILES=AGENTS.md,CLAUDE.md,greatlakes.md
DATE="2026-09-26T12:00:00+08:00"
LAND_PY=(uv run --no-project python -B "$LAND")

usage() { sed -n '2,24p' "$0" >&2; exit 2; }
[ $# -ge 1 ] || usage
ROOT=$(realpath -m "$1")
case "${2:-stub}" in
  stub|module) MODE_LIST=("${2:-stub}") ;;
  both) MODE_LIST=(stub module) ;;
  *) usage ;;
esac
mkdir -p "$ROOT"
if git -C "$ROOT" rev-parse --git-dir >/dev/null 2>&1; then
  echo "拒绝：工作目录 $ROOT 位于某个 git 仓库内；彩排只能在独立临时目录里进行" >&2
  exit 2
fi

# 与用户全局 git 配置隔离：hooks、模板、签名等一律不继承
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_OBJECT_DIRECTORY GIT_ALTERNATE_OBJECT_DIRECTORIES GIT_COMMON_DIR
unset GIT_AUTHOR_NAME GIT_AUTHOR_EMAIL GIT_AUTHOR_DATE GIT_COMMITTER_NAME GIT_COMMITTER_EMAIL GIT_COMMITTER_DATE
export GIT_CONFIG_NOSYSTEM=1 PYTHONDONTWRITEBYTECODE=1 GIT_TERMINAL_PROMPT=0

BGPIDS=()
cleanup() { for p in "${BGPIDS[@]:-}"; do [ -n "$p" ] && kill "$p" 2>/dev/null || true; done; }
trap cleanup EXIT

CUR=0
MODE=stub
fail() {
  echo "SCENARIO_${CUR}=FAIL mode=$MODE reason=$*"
  echo "REHEARSAL=FAIL scenario=$CUR mode=$MODE"
  exit 1
}
pass() { echo "SCENARIO_${CUR}=PASS mode=$MODE $*"; }

# run_land <步骤名> <子命令及参数...>：结果在 LAST_RC / LAST_LOG，并展示判定行
run_land() {
  local name=$1; shift
  LAST_LOG="$W/logs/${name}.log"
  set +e
  "${LAND_PY[@]}" "$@" > "$LAST_LOG" 2>&1
  LAST_RC=$?
  set -e
  echo "  ▸ ${name} rc=${LAST_RC}"
  grep -E '^[A-Z][A-Z0-9_]*=' "$LAST_LOG" | sed 's/^/      /' || true
}
tx() { # 生成 transform 相关参数
  if [ "$MODE" = stub ]; then
    printf '%s\0' --canon-rev "$CANON_REV" --transform-cmd "python3 -B $FX/stub_transform.py $FX/stub"
  else
    printf '%s\0' --canon-rev "$CANON_REV" --sync-config "$FX/sync-targets.json" --sync-target rehearsal \
      --onboard-dir "$FX/onboard"
  fi
}
land_remote() { local name=$1 repo=$2; shift 2; local t; mapfile -d '' t < <(tx)
  run_land "$name" remote --repo-path "$repo" --branch "$BR" --files "$FILES" "${t[@]}" \
    --message-file "$FX/msg_remote.txt" --date "$DATE" "$@"; }
land_merge() { local name=$1 repo=$2 rp=$3; shift 3; local t; mapfile -d '' t < <(tx)
  run_land "$name" merge --repo-path "$repo" --branch "$BR" --files "$FILES" "${t[@]}" \
    --message-file "$FX/msg_merge.txt" --date "$DATE" --rp "$rp" "$@"; }
land_verify() { local name=$1 repo=$2 m=$3; local t; mapfile -d '' t < <(tx)
  run_land "$name" verify --repo-path "$repo" --branch "$BR" --files "$FILES" "${t[@]}" --m "$m"; }

want_rc() { [ "$LAST_RC" = "$1" ] || fail "$(basename "$LAST_LOG") 退出码 $LAST_RC，期望 $1"; }
want() { grep -qE "$1" "$LAST_LOG" || fail "$(basename "$LAST_LOG") 缺少判定行 /$1/"; }
want_n() { local n; n=$(grep -cE "$1" "$LAST_LOG" || true); [ "$n" = "$2" ] || fail "$(basename "$LAST_LOG") 判定行 /$1/ 出现 $n 次，期望 $2"; }
lastval() { grep -E "^$1=" "$LAST_LOG" | tail -1 | cut -d= -f2 | cut -d' ' -f1; }
eq() { [ "$1" = "$2" ] || fail "$3：得到 [$1]，期望 [$2]"; }
rtip() { git -C "$1/remote.git" rev-parse "refs/heads/$BR"; }

# 抓取本地仓库可观察状态：HEAD、索引、全部 status（含未跟踪）、三类 diff、工作树文件副本
capture_state() {
  local repo=$1 out=$2
  rm -rf "$out"; mkdir -p "$out"
  git -C "$repo" --no-optional-locks rev-parse HEAD > "$out/head"
  git -C "$repo" --no-optional-locks ls-files -s > "$out/lsfiles"
  git -C "$repo" --no-optional-locks status --porcelain=v1 --untracked-files=all > "$out/status"
  git -C "$repo" --no-optional-locks diff --cached > "$out/diff_cached"
  git -C "$repo" --no-optional-locks diff > "$out/diff_unstaged"
  for f in AGENTS.md CLAUDE.md greatlakes.md other_session.txt untracked_note.txt README.md; do
    if [ -e "$repo/$f" ]; then cp -p "$repo/$f" "$out/wt_$f"; fi
  done
  [ ! -e "$repo/.git/index.lock" ] || echo "index.lock 残留" > "$out/lock"
}
same_state() {
  if ! diff -r "$1" "$2" > "$W/logs/state_diff.txt" 2>&1; then
    sed 's/^/      /' "$W/logs/state_diff.txt" | head -40
    fail "$3：本地仓库状态与基线不一致"
  fi
}

region_sha() { python3 -B - "$@" <<'PY'
import hashlib, sys
path, start, end = sys.argv[1:4]
data = open(path, "rb").read()
off, s, e = 0, None, None
for ln in data.splitlines(keepends=True):
    t = ln.rstrip(b"\n")
    if s is None and t == start.encode():
        s = off
    if e is None and t == end.encode():
        e = off
    off += len(ln)
print(hashlib.sha256(data[s:e]).hexdigest())
PY
}

wt_block_ok() { # wt_block_ok <文件路径> <文件名>：用与落地相同的 transform 判断规则块是否完好
  local t; mapfile -d '' t < <(tx)
  python3 -B - "$LAND" "$1" "$2" "${t[@]}" <<'PY'
import importlib.util, sys
land, path, fname, *rest = sys.argv[1:]
spec = importlib.util.spec_from_file_location("land_rules_commit", land)
L = importlib.util.module_from_spec(spec)
spec.loader.exec_module(L)
a = L.build_parser().parse_args(["verify", "--repo-path", ".", "--branch", "x", "--files", fname, "--m", "x", *rest])
print("BLOCK_OK" if L.block_intact(L.make_transformer(a), fname, open(path, "rb").read()) else "BLOCK_BAD")
PY
}

make_fixtures() {
  mkdir -p "$FX/stub" "$FX/onboard/rehearsal" "$FX/seed"
  cat > "$W/gitconfig" <<'EOF'
[user]
	name = 彩排机器人
	email = rehearsal@example.invalid
[init]
	defaultBranch = main
[advice]
	detachedHead = false
[pull]
	rebase = false
EOF
  # 正本块正文（两种模式共用）
  cat > "$FX/stub/AGENTS.md.block" <<'EOF'
## 强制规则（最高优先级）

1. 正本规则一：默认简体中文。
2. 正本规则二：依赖变更一律落地 pyproject.toml。
3. 正本规则三：长任务用 tmux，等待用 Monitor。
4. 正本规则四：只提交本轮改动。
EOF
  cat > "$FX/stub/CLAUDE.md.block" <<'EOF'
## 通用约定

- 正本通用约定 1：Workflow 逐次审批。
- 正本通用约定 2：Monitor 管道逐级行缓冲。
EOF
  cat > "$FX/stub/greatlakes.md.block" <<'EOF'
## 提交规约（正本）

- 只用 spgpu 分区。
- 必须带 --gpu_cmode=shared。
EOF
  cat > "$FX/stub/spec.json" <<'EOF'
{"AGENTS.md": {"start": "## 强制规则（最高优先级）", "end": "## 仓库目标"},
 "CLAUDE.md": {"start": "## 通用约定", "end": "## 项目专属"},
 "greatlakes.md": {"start": null, "end": null}}
EOF
  cat > "$FX/stub_transform.py" <<'PY'
#!/usr/bin/env python3
"""彩排用 transform 桩：stdin 原文 → stdout 结果，stderr 报 MODE=update|onboard|create|noop。

argv[1] 为桩目录：spec.json 给每个文件的 onboard 区域（start/end 为整行文本，end=null 到文件尾，
start=null 表示新建），<文件名>.block 为正本块正文。已有 RULES 标记时只替换标记块（普通模式）。"""
import json
import os
import re
import sys


def die(msg):
    sys.stderr.write(f"桩 transform 失败：{msg}\n")
    sys.exit(2)


d = sys.argv[1]
f = os.environ["LAND_FILE"]
rev = os.environ["LAND_CANON_REV"]
data = sys.stdin.buffer.read()
spec = json.load(open(os.path.join(d, "spec.json"), encoding="utf-8")).get(f)
body = open(os.path.join(d, f + ".block"), "rb").read()
begin = b"<!-- RULES:BEGIN " + f.encode() + b" canon=" + rev.encode() + b" -->\n"
end = b"<!-- RULES:END " + f.encode() + b" -->\n"
m = re.search(rb"^<!-- RULES:BEGIN " + re.escape(f.encode()) + rb" canon=[0-9a-f]+ -->\n", data, re.M)
if m:
    e = data.find(end, m.end())
    if e < 0:
        die("有 BEGIN 无 END")
    out, mode = data[:m.start()] + begin + body + end + data[e + len(end):], "update"
elif spec is None:
    die("无标记且无 onboard 规格")
elif spec["start"] is None:
    if data:
        die("create 模式但输入非空")
    out, mode = begin + body + end, "create"
else:
    def line_at(text):
        hits = [x.start() for x in re.finditer(rb"^" + re.escape(text.encode()) + rb"$", data, re.M)]
        if len(hits) != 1:
            die(f"锚点 {text} 命中 {len(hits)} 次")
        return hits[0]
    s = line_at(spec["start"])
    e = line_at(spec["end"]) if spec["end"] else len(data)
    if e <= s:
        die("end 在 start 之前")
    out, mode = data[:s] + begin + body + end + b"\n" + data[e:], "onboard"
if out == data:
    mode = "noop"
sys.stdout.buffer.write(out)
sys.stderr.write(f"MODE={mode}\n")
PY
  # 种子文件
  cat > "$FX/seed/AGENTS.md" <<'EOF'
# 彩排仓库 AGENTS.md

## 强制规则（最高优先级）

1. 旧规则一：默认中文。
2. 旧规则二：uv 管理依赖。
3. 旧规则三：长任务用 tmux。

## 仓库目标

彩排用的仓库目标说明。

## 当前进度

- 进度 A
- 进度 B

## 追加式执行日志

- 日志 1
EOF
  cat > "$FX/seed/CLAUDE.md" <<'EOF'
# CLAUDE.md（彩排）

## 通用约定

- 旧通用约定 1
- 旧通用约定 2

## 项目专属

- 专属条目 1
EOF
  printf '# 彩排仓库\n' > "$FX/seed/README.md"
  mkdir -p "$FX/seed/data"
  printf '子目录里的文件，用来检验建树排序\n' > "$FX/seed/data/notes.txt"
  printf '同名前缀文件\n' > "$FX/seed/data.txt"

  # 自建正本仓库：module 模式读它；stub 模式只借用它的 commit sha 当 canon_rev
  git init -q -b main "$FX/canon_repo"
  { printf '# 正本 AGENTS.md（彩排）\n\n<!-- AGENTMETARULES:BEGIN common-agents -->\n'; cat "$FX/stub/AGENTS.md.block"
    printf '<!-- AGENTMETARULES:END common-agents -->\n\n## 附录（正本专属，不同步）\n'; } > "$FX/canon_repo/AGENTS.md"
  { printf '# 正本 CLAUDE.md（彩排）\n\n<!-- AGENTMETARULES:BEGIN common-claude -->\n'; cat "$FX/stub/CLAUDE.md.block"
    printf '<!-- AGENTMETARULES:END common-claude -->\n'; } > "$FX/canon_repo/CLAUDE.md"
  { printf '# 正本 greatlakes.md（彩排）\n\n<!-- AGENTMETARULES:BEGIN common-greatlakes -->\n'; cat "$FX/stub/greatlakes.md.block"
    printf '<!-- AGENTMETARULES:END common-greatlakes -->\n'; } > "$FX/canon_repo/greatlakes.md"
  git -C "$FX/canon_repo" add -A
  git -C "$FX/canon_repo" commit -q -m "正本：彩排版"
  CANON_REV=$(git -C "$FX/canon_repo" rev-parse HEAD)

  # module 模式的 onboard 规格：known_region_sha256 收远端版与本地修订版两份（对应真实场景的两个已知版本）
  sed 's/^2\. 旧规则二：uv 管理依赖。$/2. 旧规则二：uv 管理依赖（本地修订）。/' "$FX/seed/AGENTS.md" > "$FX/agents_local_variant.md"
  local sha_o sha_h sha_c
  sha_o=$(region_sha "$FX/seed/AGENTS.md" "## 强制规则（最高优先级）" "## 仓库目标")
  sha_h=$(region_sha "$FX/agents_local_variant.md" "## 强制规则（最高优先级）" "## 仓库目标")
  sha_c=$(region_sha "$FX/seed/CLAUDE.md" "## 通用约定" "## 项目专属")
  printf '# greatlakes.md（彩排仓库）\n\n' > "$FX/onboard/rehearsal/greatlakes.md.head.md"
  cat > "$FX/onboard/rehearsal.json" <<EOF
{"AGENTS.md": {"start": "## 强制规则（最高优先级）", "end": "## 仓库目标",
               "known_region_sha256": ["$sha_o", "$sha_h"], "head": null, "tail": null},
 "CLAUDE.md": {"start": "## 通用约定", "end": "## 项目专属", "known_region_sha256": ["$sha_c"]},
 "greatlakes.md": {"start": null, "end": null, "head": "rehearsal/greatlakes.md.head.md", "tail": null}}
EOF
  cat > "$FX/sync-targets.json" <<EOF
{"canon": {"path": "$FX/canon_repo", "branch": "main",
           "files": {"AGENTS.md": "common-agents", "CLAUDE.md": "common-claude", "greatlakes.md": "common-greatlakes"}},
 "targets": [{"name": "rehearsal", "path": "$W", "branch": "$BR",
              "files": {"AGENTS.md": "common-agents", "CLAUDE.md": "common-claude", "greatlakes.md": "common-greatlakes"}}]}
EOF
  printf '规则同步：接入 AgentMetaRules 正本通用块（彩排）\n' > "$FX/msg_remote.txt"
  printf '合并远端规则同步提交（彩排）\n\n只动 AGENTS.md / CLAUDE.md / greatlakes.md 三个文件。\n' > "$FX/msg_merge.txt"
  cat > "$FX/other_push.sh" <<'EOF'
#!/usr/bin/env bash
# 彩排钩子：由第三方 clone 往远端推一个无关提交，制造远端竞态
set -euo pipefail
cd "$1"
git pull -q --ff-only
echo "$2" >> race.txt
git add race.txt
git commit -q -m "第三方竞态提交 $2"
git push -q origin HEAD
EOF
}

# 搭一套环境：remote.git + local（领先 2 + 脏）+ other
setup_env() {
  local d=$1
  rm -rf "$d"; mkdir -p "$d"
  git init -q --bare "$d/remote.git"
  git -C "$d/remote.git" symbolic-ref HEAD "refs/heads/$BR"
  git init -q -b "$BR" "$d/seed"
  cp -r "$FX/seed/." "$d/seed/"
  git -C "$d/seed" add -A
  git -C "$d/seed" commit -q -m "初始：彩排种子"
  git -C "$d/seed" push -q "$d/remote.git" "$BR:refs/heads/$BR"
  git clone -q -b "$BR" "$d/remote.git" "$d/local"
  git clone -q -b "$BR" "$d/remote.git" "$d/other"
  ( cd "$d/local"
    sed -i 's/^2\. 旧规则二：uv 管理依赖。$/2. 旧规则二：uv 管理依赖（本地修订）。/' AGENTS.md
    git commit -q -am "本地提交1：本地修订强制规则区"
    sed -i 's/^- 进度 B$/- 进度 B\n- 进度 C/' AGENTS.md
    echo "本地说明" >> README.md
    git commit -q -am "本地提交2：更新进度"
    # 他人会话的在途改动：暂存一处（块外）+ 新文件
    sed -i 's/^- 进度 C$/- 进度 C\n- 进度 D（他人已暂存）/' AGENTS.md
    git add AGENTS.md
    echo "他人会话的新文件" > other_session.txt
    git add other_session.txt
    # 未暂存：追加到 AGENTS.md / CLAUDE.md 末尾
    echo "- 日志 2（他人未暂存追加）" >> AGENTS.md
    echo "- 专属条目 2（未暂存）" >> CLAUDE.md
    echo "未跟踪笔记" > untracked_note.txt )
}

# ───────── 环境 A：①②⑤⑥ ─────────
scenarios_env_a() {
  local E="$W/envA"
  setup_env "$E"
  local O; O=$(rtip "$E")

  CUR=1; echo "== 场景①：remote 正常推送快进（mode=$MODE）"
  land_remote s1a_remote_dryrun_emit "$E/local" --dry-run --emit-diff-dir "$E/review"
  want_rc 0; want '^REMOTE_COMMIT=PASS dry_run=1'; want_n '^EMIT_DIFF=DONE' 3
  local RP_DRY; RP_DRY=$(lastval RP)
  cp -r "$E/review" "$E/review_bad"; echo "篡改" >> "$E/review_bad/CLAUDE.md.diff"
  land_remote s1b_remote_tampered_review "$E/local" --dry-run --expect-diff-dir "$E/review_bad"
  want_rc 2; want '^EXPECT_DIFF=FAIL reason=differs_from_review file=CLAUDE.md'
  land_remote s1c_remote_build_only "$E/local" --expect-diff-dir "$E/review"
  want_rc 0; want '^PUSH=SKIP reason=no_push_flag'; eq "$(lastval RP)" "$RP_DRY" "不推送时的 RP 与 dry-run 预算"
  land_merge s1d_merge_dryrun "$E/local" "$RP_DRY" --dry-run --snapshot-dir "$E/snap_dry"
  want_rc 0; want '^DRY_RUN=STOP before=C4'; want_n '^FEASIBLE=PASS' 3
  M_DRY=$(lastval M)
  eq "$(rtip "$E")" "$O" "merge --dry-run 之后远端"
  land_remote s1e_remote_push "$E/local" --push --expect-diff-dir "$E/review"
  want_rc 0
  want "^REMOTE_BASE=PASS O=$O ls_remote=$O ff_from_prev=1"
  want '^TRANSFORM=PASS file=AGENTS.md mode=onboard'
  want '^TRANSFORM=PASS file=CLAUDE.md mode=onboard'
  want '^TRANSFORM=PASS file=greatlakes.md mode=create'
  want_n '^EXPECT_DIFF=PASS' 3
  want '^REMOTE_COMMIT=PASS .*files=3 other_paths=0'
  want '^PUSH=PASS'; want '^REMOTE_POST=PASS'
  RP=$(lastval RP)
  eq "$RP" "$RP_DRY" "推送的 RP 与 dry-run 预算（同一输入同一 sha）"
  eq "$(rtip "$E")" "$RP" "远端分支"
  eq "$(git -C "$E/local" rev-parse "$RP^")" "$O" "RP 的父提交"
  eq "$(git -C "$E/local" diff-tree -r --name-only "$O" "$RP" | sort | tr '\n' ,)" "AGENTS.md,CLAUDE.md,greatlakes.md," "RP 改动的路径"
  pass "O=$O RP=$RP"

  CUR=2; echo "== 场景②：merge 正常落地（mode=$MODE）"
  local H; H=$(git -C "$E/local" rev-parse HEAD)
  capture_state "$E/local" "$E/state_before2"
  land_merge s2_merge "$E/local" "$RP" --snapshot-dir "$E/snap2"
  want_rc 0
  for k in LOCAL_PRE RP_CHECK SNAPSHOT INDEX_LOCK INDEX_DELTA REF_PREPARE REF_CAS INDEX_INSTALL STATUS_EQUAL MERGE; do want "^$k=PASS"; done
  want_n '^FEASIBLE=PASS' 3
  want "^LOCAL_COMMIT=PASS H=$H M=[0-9a-f]{40} parents=H,RP first_parent_files=3"
  want_n '^WT_WRITE=PASS' 3
  want '^HUNKSET_EQUAL=PASS kind=head basis=snapshot'
  want '^HUNKSET_EQUAL=PASS kind=cached basis=snapshot'
  want '^HUNKSET_EQUAL=PASS kind=unstaged basis=snapshot'
  want '^FF_READY=PASS behind=0 ahead=3'
  M=$(lastval M)
  eq "$M" "$M_DRY" "落地的 M 与 dry-run 预算"
  eq "$(git -C "$E/local" rev-parse HEAD)" "$M" "HEAD"
  eq "$(git -C "$E/local" rev-parse "$M^1") $(git -C "$E/local" rev-parse "$M^2")" "$H $RP" "M 的两个父提交"
  eq "$(git -C "$E/local" diff-tree -r --name-only "$H" "$M" | sort | tr '\n' ,)" "AGENTS.md,CLAUDE.md,greatlakes.md," "第一父 diff 路径"
  eq "$(git -C "$E/local" diff --cached --name-only | sort | tr '\n' ,)" "AGENTS.md,other_session.txt," "落地后仍暂存的路径"
  eq "$(git -C "$E/local" diff --name-only | sort | tr '\n' ,)" "AGENTS.md,CLAUDE.md," "落地后仍未暂存的路径"
  git -C "$E/local" show ":AGENTS.md" | grep -q '进度 D（他人已暂存）' || fail "索引里他人暂存的行丢失"
  ! git -C "$E/local" show ":AGENTS.md" | grep -q '日志 2' || fail "未暂存的行被错误写进索引"
  grep -q '日志 2（他人未暂存追加）' "$E/local/AGENTS.md" || fail "工作树未暂存追加丢失"
  [ -e "$E/local/untracked_note.txt" ] || fail "未跟踪文件丢失"
  [ "$(wt_block_ok "$E/local/AGENTS.md" AGENTS.md)" = BLOCK_OK ] || fail "工作树 AGENTS.md 规则块不完好"
  land_verify s2_verify "$E/local" "$M"
  want_rc 0; want '^NO_REVERT=PASS commits=0'
  pass "H=$H M=$M"

  CUR=5; echo "== 场景⑤：幂等（mode=$MODE）"
  capture_state "$E/local" "$E/state_before5"
  land_remote s5a_remote_again "$E/local" --push
  want_rc 0; want '^REMOTE_COMMIT=NOOP'; want '^PUSH=SKIP reason=noop'
  eq "$(lastval RP)" "$RP" "再跑 remote 打印的 RP"
  eq "$(rtip "$E")" "$RP" "再跑 remote 后远端"
  land_merge s5b_merge_again "$E/local" "$RP" --snapshot-dir "$E/snap5"
  want_rc 0; want '^LOCAL_COMMIT=NOOP'
  capture_state "$E/local" "$E/state_after5"
  same_state "$E/state_before5" "$E/state_after5" "幂等重跑前后"
  pass "remote=NOOP merge=NOOP HEAD=$M"

  CUR=6; echo "== 场景⑥：以后推送（mode=$MODE）"
  ( cd "$E/local"
    echo "Codex 写的说明" > codex_note.txt
    git add codex_note.txt
    git commit -q -m "Codex 提交：补充说明" -- codex_note.txt )
  local C; C=$(git -C "$E/local" rev-parse HEAD)
  eq "$(git -C "$E/local" rev-parse "$C^")" "$M" "Codex 提交的父提交"
  eq "$(git -C "$E/local" diff --cached --name-only | sort | tr '\n' ,)" "AGENTS.md,other_session.txt," "Codex 提交后他人暂存仍在"
  # git pull --rebase 在干净副本上演示：会把本地提交线性重放到 RP 上，预期冲突
  git clone -q -b "$BR" "$E/remote.git" "$E/rebase_demo"
  git -C "$E/rebase_demo" fetch -q "$E/local" "$BR"
  git -C "$E/rebase_demo" reset -q --hard FETCH_HEAD
  set +e
  git -C "$E/rebase_demo" pull --rebase > "$W/logs/s6_pull_rebase.log" 2>&1
  local prc=$?
  set -e
  [ "$prc" != 0 ] || fail "git pull --rebase 竟然成功（期望冲突）"
  grep -q CONFLICT "$W/logs/s6_pull_rebase.log" || fail "git pull --rebase 失败但不是冲突"
  echo "  ▸ git pull --rebase rc=$prc（冲突，符合预期）"
  git -C "$E/rebase_demo" rebase --abort
  eq "$(git -C "$E/rebase_demo" rev-parse HEAD)" "$C" "rebase --abort 后 HEAD"
  set +e
  git -C "$E/local" push > "$W/logs/s6_push.log" 2>&1
  local urc=$?
  set -e
  echo "  ▸ 裸 git push rc=$urc"; sed 's/^/      /' "$W/logs/s6_push.log"
  [ "$urc" = 0 ] || fail "裸 git push 失败"
  ! grep -qi 'forced' "$W/logs/s6_push.log" || fail "推送不是快进"
  eq "$(rtip "$E")" "$C" "推送后远端"
  land_verify s6_verify "$E/local" "$M"
  want_rc 0; want '^NO_REVERT=PASS commits=1'
  pass "push=fast-forward pull_rebase=conflict_aborted"
}

# ───────── 环境 B：③ ─────────
scenarios_env_b() {
  local E="$W/envB"
  CUR=3; echo "== 场景③：远端竞态（mode=$MODE）"
  setup_env "$E"
  export LAND_TEST_HOOK_BEFORE_PUSH="bash $FX/other_push.sh $E/other race-a"
  land_remote s3a_remote_race_at_push "$E/local" --push
  unset LAND_TEST_HOOK_BEFORE_PUSH
  want_rc 4; want '^PUSH=REJECTED reason=remote_advanced stage=push'
  local tip_a; tip_a=$(git -C "$E/other" rev-parse HEAD)
  eq "$(rtip "$E")" "$tip_a" "竞态 a 后远端仍是第三方提交"
  local log_a=$LAST_LOG
  export LAND_TEST_HOOK_AFTER_B4="bash $FX/other_push.sh $E/other race-b"
  land_remote s3b_remote_race_before_precheck "$E/local" --push
  unset LAND_TEST_HOOK_AFTER_B4
  want_rc 4; want '^PUSH=REJECTED reason=remote_advanced stage=precheck'
  local tip_b; tip_b=$(git -C "$E/other" rev-parse HEAD)
  eq "$(rtip "$E")" "$tip_b" "竞态 b 后远端仍是第三方提交"
  for lg in "$log_a" "$LAST_LOG"; do
    ! grep -qi 'force' "$lg" || fail "$(basename "$lg") 出现强推字样"
    ! grep -qE '\+[0-9a-f]{7,40}:' "$lg" || fail "$(basename "$lg") 出现带 + 的 refspec"
  done
  pass "git_reject=exit4 precheck_reject=exit4 no_force_in_logs"
}

# ───────── 环境 C：④ ─────────
scenarios_env_c() {
  local E="$W/envC"
  CUR=4; echo "== 场景④：本地竞态（mode=$MODE）"
  setup_env "$E"
  land_remote s4a_remote_push "$E/local" --push
  want_rc 0
  local RP4; RP4=$(lastval RP)
  local H; H=$(git -C "$E/local" rev-parse HEAD)
  local held="$E/lock_held" loopl="$W/logs/s4_commit_loop.log"
  rm -f "$held"; : > "$loopl"
  ( for i in $(seq 1 400); do printf 'APPEND-%03d\n' "$i" >> "$E/local/AGENTS.md"; sleep 0.01; done ) &
  local app=$!; BGPIDS+=("$app")
  ( cd "$E/local"
    for _ in $(seq 1 600); do [ -e "$held" ] && break; sleep 0.05; done
    while [ -e "$held" ]; do
      if { echo x >> dummy.txt; git add dummy.txt && git commit -q -m "竞态提交尝试"; } >> "$loopl.err" 2>&1; then
        echo COMMIT_OK >> "$loopl"
      else
        echo COMMIT_FAIL >> "$loopl"
      fi
      sleep 0.05
    done ) &
  local loop=$!; BGPIDS+=("$loop")
  sleep 0.2
  export LAND_TEST_LOCK_HELD_FILE="$held" LAND_TEST_HOLD_LOCK_MS=800
  land_merge s4b_merge_under_race "$E/local" "$RP4" --snapshot-dir "$E/snap4"
  unset LAND_TEST_LOCK_HELD_FILE LAND_TEST_HOLD_LOCK_MS
  wait "$app"; wait "$loop"
  want_rc 0
  for k in INDEX_LOCK INDEX_DELTA REF_PREPARE REF_CAS INDEX_INSTALL STATUS_EQUAL FF_READY MERGE; do want "^$k=PASS"; done
  want '^WT_WRITE=PASS file=AGENTS.md'
  local M4; M4=$(lastval M)
  local n; n=$(grep -c '^APPEND-' "$E/local/AGENTS.md" || true)
  eq "$n" 400 "AGENTS.md 里 APPEND 行数"
  grep '^APPEND-' "$E/local/AGENTS.md" | diff -q - <(seq -f 'APPEND-%03g' 1 400) > /dev/null || fail "APPEND 行顺序不连续"
  local span; span=$(grep -n '^APPEND-' "$E/local/AGENTS.md" | awk -F: 'NR==1{f=$1} {l=$1} END{print l-f+1}')
  eq "$span" 400 "APPEND 行在文件中连续"
  local okc failc
  okc=$(grep -c COMMIT_OK "$loopl" || true); failc=$(grep -c COMMIT_FAIL "$loopl" || true)
  echo "  ▸ 提交循环：成功 $okc 次、失败 $failc 次"
  eq "$okc" 0 "锁内提交循环成功次数"
  [ "$failc" -ge 5 ] || fail "锁内提交循环失败次数过少：$failc"
  grep -q 'index.lock' "$loopl.err" || fail "提交循环失败原因不是 index.lock"
  eq "$(git -C "$E/local" rev-parse HEAD)" "$M4" "竞态后 HEAD"
  git -C "$E/local" show ":AGENTS.md" | grep -q '进度 D（他人已暂存）' || fail "索引里他人暂存的行丢失"
  grep -q '日志 2（他人未暂存追加）' "$E/local/AGENTS.md" || fail "工作树未暂存追加丢失"
  [ "$(wt_block_ok "$E/local/AGENTS.md" AGENTS.md)" = BLOCK_OK ] || fail "竞态后工作树 AGENTS.md 规则块不完好"
  land_verify s4c_verify "$E/local" "$M4"
  want_rc 0; want '^NO_REVERT=PASS'
  local wt; wt=$(grep -E '^WT_WRITE=PASS file=AGENTS.md' "$W/logs/s4b_merge_under_race.log" | head -1)
  pass "appends=400 contiguous=1 commit_ok=$okc commit_fail=$failc ${wt#WT_WRITE=PASS }"
}

# ───────── 环境 D：⑦ ─────────
scenarios_env_d() {
  local E="$W/envD"
  CUR=7; echo "== 场景⑦：回滚演练（mode=$MODE）"
  setup_env "$E"
  land_remote s7_remote_push "$E/local" --push
  want_rc 0
  local RP7; RP7=$(lastval RP)
  local H; H=$(git -C "$E/local" rev-parse HEAD)
  capture_state "$E/local" "$E/state_before7"
  export LAND_TEST_FAIL_AT=after_ref_commit
  land_merge s7a_merge_fail_after_ref_commit "$E/local" "$RP7" --snapshot-dir "$E/snap7a"
  unset LAND_TEST_FAIL_AT
  want_rc 7; want '^REF_CAS=PASS'; want '^ROLLBACK_REF=PASS'; want '^ROLLBACK=DONE'
  capture_state "$E/local" "$E/state_after7a"
  same_state "$E/state_before7" "$E/state_after7a" "注入失败（ref 已提交）自动回滚后"
  export LAND_TEST_FAIL_AT=after_wt_write
  land_merge s7b_merge_fail_after_wt_write "$E/local" "$RP7" --snapshot-dir "$E/snap7b"
  unset LAND_TEST_FAIL_AT
  want_rc 7; want '^ROLLBACK=DONE'
  capture_state "$E/local" "$E/state_after7b"
  same_state "$E/state_before7" "$E/state_after7b" "注入失败（ref 未提交）自动回滚后"
  land_merge s7c_merge "$E/local" "$RP7" --snapshot-dir "$E/snap7c"
  want_rc 0; want '^MERGE=PASS'
  local M7; M7=$(lastval M)
  run_land s7d_rollback rollback --repo-path "$E/local" --branch "$BR" --m "$M7" --h "$H" --snapshot-dir "$E/snap7c"
  want_rc 0
  want '^INDEX_DELTA=PASS changed=3'; want '^REF_CAS=PASS'; want '^INDEX_INSTALL=PASS'
  want_n '^ROLLBACK_WT=PASS' 3
  want_n '^HUNKSET_EQUAL=PASS kind=[a-z]+ basis=snapshot' 3
  want '^STATUS_EQUAL=PASS'; want '^ROLLBACK=PASS'
  capture_state "$E/local" "$E/state_after7d"
  same_state "$E/state_before7" "$E/state_after7d" "rollback 子命令撤销后"
  pass "inject_after_ref_commit=DONE inject_after_wt_write=DONE rollback_cmd=PASS"
}

# ───────── 环境 E：⑧ ─────────
scenarios_env_e() {
  local E="$W/envE"
  CUR=8; echo "== 场景⑧：FEASIBLE=FAIL（mode=$MODE）"
  setup_env "$E"
  local O; O=$(rtip "$E")
  cp -p "$E/local/AGENTS.md" "$E/agents_wt_orig"
  sed -i 's/^3\. 旧规则三：长任务用 tmux。$/3. 旧规则三：长任务用 tmux（他人在途改动）。/' "$E/local/AGENTS.md"
  capture_state "$E/local" "$E/state_before8a"
  land_remote s8a_remote_build "$E/local"
  want_rc 0; want '^PUSH=SKIP'
  local RP8; RP8=$(lastval RP)
  land_merge s8a_merge_infeasible_worktree "$E/local" "$RP8" --snapshot-dir "$E/snap8a"
  want_rc 3; want '^FEASIBLE=FAIL reason=[a-z_]+ file=AGENTS.md where=worktree'
  ! grep -qE '^(INDEX_LOCK|REF_PREPARE|WT_WRITE)=' "$LAST_LOG" || fail "FEASIBLE=FAIL 之后仍有写入步骤"
  eq "$(rtip "$E")" "$O" "⑧a 后远端未推"
  capture_state "$E/local" "$E/state_after8a"
  same_state "$E/state_before8a" "$E/state_after8a" "⑧a 前后"
  # ⑧b：同一改动改为暂存（索引里的在途 hunk 落在被替换区域）
  git -C "$E/local" add AGENTS.md
  capture_state "$E/local" "$E/state_before8b"
  land_merge s8b_merge_infeasible_index "$E/local" "$RP8" --snapshot-dir "$E/snap8b"
  want_rc 3; want '^FEASIBLE=FAIL reason=[a-z_]+ file=AGENTS.md where=index'
  eq "$(rtip "$E")" "$O" "⑧b 后远端未推"
  capture_state "$E/local" "$E/state_after8b"
  same_state "$E/state_before8b" "$E/state_after8b" "⑧b 前后"
  pass "worktree=exit3 index=exit3 remote_unchanged=1"
}

run_mode() {
  MODE=$1
  W="$ROOT/$MODE"
  FX="$W/fixtures"
  rm -rf "$W"; mkdir -p "$W/logs" "$FX"
  export GIT_CONFIG_GLOBAL="$W/gitconfig"
  echo "######## 彩排模式：$MODE（工作目录 $W）"
  make_fixtures
  scenarios_env_a
  scenarios_env_b
  scenarios_env_c
  scenarios_env_d
  scenarios_env_e
  echo "MODE_RESULT=PASS mode=$MODE scenarios=8"
}

T0=$(date +%s)
for m in "${MODE_LIST[@]}"; do run_mode "$m"; done
echo "REHEARSAL_SUMMARY=PASS modes=$(IFS=,; echo "${MODE_LIST[*]}") seconds=$(( $(date +%s) - T0 ))"
echo "REHEARSAL=PASS scenarios=8"
