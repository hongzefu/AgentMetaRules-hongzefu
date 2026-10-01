# Codex SSH App 更新与模型列表排查

## 2026-10-01 sled-vail 实例

用户报告桌面 SSH App 中找不到 GPT-6.1。`codex update` 把独立安装的 Codex CLI 从 `0.157.0` 更新到 `0.159.3`，`codex --version` 返回 `codex-cli 0.159.3`。新版临时 `codex app-server --stdio` 的 `model/list` 返回 `gpt-6.1-sol`（显示名 `GPT-6.1-Sol`）；`codex exec --ephemeral --skip-git-repo-check -C /tmp -s read-only -m gpt-6.1-sol '只输出：模型连接成功。不要调用工具。'` 退出码为 0，实际返回「模型连接成功」。这两项只验证新版后端的模型目录和 CLI 推理。

桌面 SSH App 使用的常驻后端没有随安装更新：`codex app-server daemon version` 同时报告 `cliVersion=0.159.3`、`managedCodexVersion=0.159.3`、`appServerVersion=0.157.0`；在跑的后端可执行文件仍指向 `0.157.0`。本机 `models_cache.json` 只查到 `gpt-6-sol`，未查到 `gpt-6.1-sol`。因此不能凭新版 CLI 成功就说桌面模型选择器已经修好；截至本次记录，桌面端仍找不到 GPT-6.1，桌面端实际推理也未验证。

## 排查与恢复顺序

1. 在 SSH 目标机确认 `command -v codex`、`codex --version`、`codex app-server daemon version`。分别记录磁盘上的 CLI 版本和**运行中**的 `appServerVersion`；两者不同说明常驻后端尚未切换。
2. 用新版独立后端的 `model/list` 核对准确标识符 `gpt-6.1-sol`，再用一次最小推理确认该账号能实际调用。模型目录仅是目录，不能代替推理授权验证。不要把 CLI 结果写成桌面 App 端到端结果。
3. 若常驻后端版本仍旧，先核实该后端上是否有别的在跑任务及其归属。`codex app-server daemon restart` 会影响共用后端；只有确认可以中断相关会话或取得相应授权后才执行。保留已有任务，不用 `pkill`、通配 `kill` 或全局清理代替精确管理命令。
4. 后端重启后重新连接桌面 SSH，在桌面模型选择器中核对 `GPT-6.1-Sol`，再从**桌面 App** 发起一条最小请求，确认所选模型与完成状态。分别记录 `DAEMON_VERSION=PASS`、`APP_MODEL_LIST=PASS`、`APP_INFERENCE=PASS`；任一步未完成，就如实标为未验证。

本次只完成第 1、2 步；第 3、4 步尚未执行。`~/.codex/config.toml` 的默认 `model = "gpt-6-sol"` 不会自动改成 GPT-6.1；用户可在更新后的桌面模型选择器里显式选择新模型。

参考：[GPT-6.1 Sol 模型标识符](https://developers.openai.com/api/docs/models/gpt-6.1-sol)、[Codex app-server 的 `model/list` 与推理区别](https://developers.openai.com/siwc/token-sharing-open-source/codex-app-server)、[模型目录的缓存边界](https://developers.openai.com/siwc/token-sharing-open-source/models-and-inference)。
