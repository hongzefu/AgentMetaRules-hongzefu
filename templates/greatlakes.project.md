# greatlakes 提交规约（<仓库名> 副本）

本文件标记块内是正本 `greatlakes.md` 通用块（H1 标题之后到文末）的逐字副本，由 `sync_rules.py apply` 填入、不得手改；`<GL_REPO>` 等占位符的本仓库取值见 `AGENTS.md`「占位符取值」；本仓库的放行记录、现成脚本与实测表写在标记块之后。

<!-- AGENTMETARULES:BEGIN common-greatlakes src=<正本 sha> blob=<块 blob> -->
（由 sync_rules.py apply 填入，勿手改）
<!-- AGENTMETARULES:END common-greatlakes -->

## 项目专属

### 放行记录

超出「1 GPU × 48 h 占位 job、默认规格、一次 4 个」的逐次放行记在这里，每条一段：

- **<日期> <任务名>**：用户原话「<…>」；资源包络 `<GPU / CPU / mem / walltime / job 数>`；调度方式（串行链 / 并行 / 节点排除清单）；用途；JobID 清单文件 `<日志目录>/hold-jobs-<任务名>.txt`。

### 现成脚本

| 脚本 | 用途 | 占位 job 规格 | srun 塞入参数 | 备注 |
|---|---|---|---|---|
| `<路径>` | | | | |

### 实测表

| 日期 | JobID | 规格 | 排队时长 | 结果 | 备注 |
|---|---|---|---|---|---|
| | | | | | |
