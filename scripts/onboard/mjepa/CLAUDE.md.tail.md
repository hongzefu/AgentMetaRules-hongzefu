
## 项目专属补充

- **Skill 调用按环境分叉**：环境 A（sled 主机）查 `chaijy2` 占用先调 `greatlakes-usage`；环境 B（AWS）默认不执行集群操作，不得因历史文档提及 `greatlakes-usage` 就自行调用该 Skill 或尝试 SSH、Slurm 命令；用户明确要求且已核实为 GreatLakes 工作时，提交、认证和路径规约遵循 `greatlakes.md`，工具不可用时如实说明。
- **Monitor 过滤词表补充**：训练 / 抽取作业的缺陷特征行 `nan`、`NaN`、`CUDA out of memory`、`Killed`、`SHARD_EXIT_CODE=[1-9]`；完成行 `Epoch`、`FINALIZE_EXIT_CODE`、`EXIT_CODE=`。
- **plan mode 只读核实清单**：当前环境（A / B）与工作副本落点；`configs/` 下 overlay 配置（armw0、armwnull、filter10、filter10_armwnull、full1600_armwnull）与 `configs/default.yaml` 的关系；数据集副本路径是否已核实；计划文件现名。
- Agent 工具子代理与 Workflow 的用法以标记块为准，本仓库无额外约定。
