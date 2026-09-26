
## 项目专属补充

- **Skill 调用按环境分叉**：环境 A（sled-vail）查 `chaijy2` 占用先调 `greatlakes-usage`；环境 B（AWS）没有集群账户，禁止调用 `greatlakes-usage`、禁止手搓 `ssh` + `squeue` 试探（`~/.ssh/config` 不存在），用户问到集群时先说明当前环境无 GreatLakes 访问；`greatlakes.md` 在环境 B 只作历史存档，不作为可执行指引。
- **Monitor 过滤词表补充**：训练 / 建库作业的缺陷特征行 `nan`、`NaN`、`CUDA out of memory`、`Killed`；完成行 `EXIT_CODE=`、`Epoch`。
- **plan mode 只读核实清单**：当前环境（A / B）与工作副本落点；`v1-store/` 是实体目录还是可写 symlink（开发副本例外）；`.venv` 是否独立；`paths.sh` 的 `v1_prepare_dirs` 定义在 `scripts/training/paths.sh` 还是 `scripts/dataset/paths.sh`；计划文件现名（`MMDD-` 前缀）。
- Agent 工具子代理与 Workflow 的用法以标记块为准，本仓库无额外约定。
