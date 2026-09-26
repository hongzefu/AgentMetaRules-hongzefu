
## 项目专属补充

- **Monitor 过滤词表补充**（标记块 Monitor 第 7 条）：生成 / 对拍作业的缺陷特征行 `NO RECORD`（录像器阶段跳过）、`reset 拒绝`、`svulkan2`、`EXCLUSIVE`、`RRT`；完成行 `全部完成`、`EXIT_CODE=`。
- **Skill 调用**：本机 sled-vail 有集群访问，查 `chaijy2` 占用先调 `greatlakes-usage`；占位 job 规格、开工先占卡、跑完按清单 `scancel` 按 `greatlakes.md`。
- **plan mode 只读核实清单**：`ls -1 scripts/*.py` 是否仍恰好五个入口；`git diff --quiet HEAD -- src/robomme/env_record_wrapper/RecordWrapper.py` 零 diff；冻结配置 `scripts/configs/newtask-v5/sampling_config.json` 的 SHA-256 与账本一致；`artifacts/` 不进 git；账本末尾最新一条日志的「下一步」。
- Agent 工具子代理与 Workflow 的用法以标记块为准（子代理一次性、默认只读；Workflow 逐次审批），本仓库无额外约定。
