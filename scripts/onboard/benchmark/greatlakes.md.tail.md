
## 项目专属

- **本仓库实测记录**：[`docs/greatlakes.md`](docs/greatlakes.md)（`--gpu_cmode=shared` 必须显式、单 worker 才逐位复现、`AssocGrpCpuLimit` 撞线、生成耗时参考、2026-09-22 教训清单）。
- **集群侧克隆**：`/nfs/turbo/coe-chaijy-unreplicated/hongzefu/robomme_benchmark-newtask-gl`；产物落 NFS、比较在本机 sled-vail 跑，不搬数据。
- **占位 job 清单**：`<日志目录>/hold-jobs-<任务名>.txt`；V6 生成占位 job 的 JobID 与释放记录写在 `AGENTS.md` 账本。
