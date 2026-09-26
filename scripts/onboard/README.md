# scripts/onboard：首次接入（onboard）规格目录

项目仓库第一次接入通用块时，目标文件里还没有 `AGENTMETARULES` 标记。此时
`scripts/sync_rules.py transform|apply --onboard scripts/onboard` 依据本目录下的规格，
决定「把目标文件里哪一段旧内容换成正本通用块」，并在换入时写好带 `src=`/`blob=` 的标记。

**已经带标记的文件不会用到这里的规格**：输入里已有该块的一对标记时，onboard 自动退化为普通模式
（判定行 `ONBOARD=SKIP reason=markers_present`），所以接入完成后本目录的规格留着也无害。

## 目录布局

```
scripts/onboard/
├── README.md                    本说明
├── <repo>.json                  每个目标仓库一份；<repo> = sync-targets.json 里 targets[].name
│                                （当前为 benchmark / policy / mjepa）
└── <repo>/                      建议：该仓库用到的 head/tail 片段放在同名子目录，避免不同仓库重名
    ├── AGENTS.md.head.md
    ├── AGENTS.md.tail.md
    └── greatlakes.md.head.md
```

- `head` / `tail` 的路径一律**相对本目录**（即 `--onboard` 传入的 fixture_dir）解析；
  不得是绝对路径，不得含 `..`。
- `<repo>.json` 里没列出的文件：若目标文件已有标记，照常走普通模式；没有标记则 `TRANSFORM=FAIL reason=markers_absent`。

## `<repo>.json` 格式

顶层是对象，键为目标文件名（必须是 sync-targets.json 里该目标 `files` 的键），值为该文件的规格：

```json
{
  "AGENTS.md": {
    "start": "## 强制规则（最高优先级）",
    "end": "## 仓库目标",
    "known_region_sha256": ["<64 位小写十六进制>"],
    "head": "benchmark/AGENTS.md.head.md",
    "tail": "benchmark/AGENTS.md.tail.md"
  },
  "CLAUDE.md": {
    "start": "## 通用约定",
    "end": null,
    "known_region_sha256": [],
    "head": null,
    "tail": null
  },
  "greatlakes.md": {
    "_comment": "benchmark 仓库原本没有 greatlakes.md，新建",
    "start": null,
    "end": null,
    "head": "benchmark/greatlakes.md.head.md",
    "tail": null
  }
}
```

| 字段 | 类型 | 必填 | 语义 |
|---|---|---|---|
| `start` | 字符串或 `null` | **必须显式写出** | 被替换区域的起始行。整行精确匹配（从第 0 列起、不含行尾 `\n`，按 UTF-8 字节比较），全文件命中次数必须恰好 1 次。`null` 表示目标文件整个不存在、需要新建（create 模式）。 |
| `end` | 字符串或 `null` | **必须显式写出** | 被替换区域的结束行（**该行本身保留**，不在区域内）。同样整行精确匹配、恰好 1 次，且必须在 `start` 之后。`null` 表示区域一直到文件尾。`start` 为 `null` 时 `end` 也必须为 `null`。 |
| `known_region_sha256` | 字符串数组 | 否（缺省即 `[]`） | 被替换区域字节的 sha256 白名单（64 位小写十六进制）。实际值不在集合里 → `ONBOARD_REGION=FAIL`，整次变换失败、不写任何东西。空集合表示不校验，但仍打印实际值（`ONBOARD_REGION=UNCHECKED`）。可放多个值（如工作树版与 HEAD 版）。create 模式下忽略。 |
| `head` | 字符串或 `null` | 否 | 插在 BEGIN 标记行之前的片段文件；`null`/缺省表示空。 |
| `tail` | 字符串或 `null` | 否 | 插在 END 标记行之后的片段文件；`null`/缺省表示空。 |
| `note` / `comment` / `_xxx` | 任意 | 否 | 注释键（`note`、`comment` 以及任何以下划线开头的键），忽略。其余未知键一律报错（防拼写错误）。 |

片段文件（head/tail）的约束：内容为空或以 `\n` 结尾；不得含 `\r`、不得以 UTF-8 BOM 开头；
不得有以 `<!-- AGENTMETARULES:` 开头的行（否则输出里会出现多余标记）。

## 变换语义（全部按字节）

设输入字节为 `in`，`s` 为 start 行行首偏移，`e` 为 end 行行首偏移（`end` 为 `null` 时 `e = len(in)`）：

- **onboard 模式**（`start` 非 null，输入无标记）：
  被替换区域 = `in[s:e]`（从 start 行起，到 end 行之前）；
  `out = in[:s] + head + BEGIN行\n + 正本块 + END行\n + tail + in[e:]`。
- **create 模式**（`start` 为 null）：要求输入为空（目标文件不存在）；
  `out = head + BEGIN行\n + 正本块 + END行\n + tail`。
  `apply` 新建文件时用硬链接原子占位，若期间别人抢先建了同名文件则重试。
- **退化**：输入已有该块的标记 → 普通模式（只替换标记行及块内容），规格被忽略。

BEGIN/END 行的格式为
`<!-- AGENTMETARULES:BEGIN <块名> src=<正本 commit 全 sha> blob=<块内容 git blob id> -->`（END 行同样带属性）。

每次变换都会断言并打印不变式：
`prefix`（`out[:s] == in[:s]`）、`suffix`（`in[e:]` 原样出现在输出末尾）、`block`（输出重新解析后块内容与属性正确）、
`idempotent`（再变换一次必须是 NOOP）。`TRANSFORM` 行里的 `outside_sha256_in` / `outside_sha256_out`
分别是「输入去掉被替换区域」与「输出去掉 head+标记+块+tail」后的 sha256，两者相等说明区域外字节未被改动。

若 sync-targets.json 给该文件配了 `ledger_anchor`（如 benchmark 的 AGENTS.md 配 `## 仓库目标`），
还会额外校验「从锚点行到文件尾」的字节在输入输出中完全相同（`LEDGER_BYTES=PASS|FAIL`）。
因此 benchmark AGENTS.md 的 `end` 应取 `## 仓库目标`（或更靠前的行），不能把账本区划进被替换区域。

## 如何取得 `known_region_sha256`

先把该文件的 `known_region_sha256` 写成 `[]`，把变换结果输出到临时文件（不改目标仓库）：

```bash
cd /data/hongzefu/AgentMetaRules-hongzefu
uv run --no-project python scripts/sync_rules.py transform --repo benchmark --file AGENTS.md \
    --onboard scripts/onboard --output /path/to/scratch/benchmark.AGENTS.md
```

从判定行 `ONBOARD_REGION=UNCHECKED ... bytes=<字节数> sha256=<值>` 取实际值，人工 diff 确认被替换的正是想替换的旧通用规则后，
把该值填进 `known_region_sha256`。这样之后目标文件的这一段若又被人改过，接入会失败而不是悄悄删掉新增内容。

## 常用命令

```bash
# 预览（输出到文件，判定行在 stdout）
uv run --no-project python scripts/sync_rules.py transform --repo policy --file AGENTS.md --onboard scripts/onboard --output /path/to/scratch/x.md
# 写回目标工作树（原子写，不做任何 git add/commit/push）
uv run --no-project python scripts/sync_rules.py apply --repo policy --onboard scripts/onboard
# 接入后核对
uv run --no-project python scripts/sync_rules.py check --repo policy
```
