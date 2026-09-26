
## 项目专属

下面各节是本仓库的历史实测与现成脚本（2026-08 集群时期），`<GL_REPO>` = `/nfs/turbo/coe-chaijy-unreplicated/hongzefu/MotionJEPA`，提交器 `scripts/train-script-hongzefu/gl_submit.py`；占位 job 清单 `<日志目录>/hold-jobs-<任务名>.txt`。历史 sbatch 工作 job 的写法已被占位 job 口径取代，表中的 `--time`、`--gpus-per-node` 只作记录。

## 现成的 slurm 脚本（2026-08-14 新增；2026-08-16 起 `scripts/dataset-build/` 下另有抽取入口，见下节）

`scripts/train-script-hongzefu/` 下带 `gl_` 前缀的三个脚本是**训练侧可直接 sbatch 的集群入口**，
其余（`smoke_/bf16_/filter10_*_local2gpu.sh`）都是本地 torchrun 包装，不能当 sbatch 提交：

| 脚本 | 资源 | 用途 |
|---|---|---|
| `gl_bf16_wan_smoke.sh` | 2 GPU / 8 CPU / 48G / 00:30:00 | 集群侧冒烟 v1（已于 2026-08-14 全绿跑通，见下表）：验 NFS venv、DDP、NFS 数据吞吐与 A40 上默认 batch 88 的显存；含每 20 秒一次的显存采样与峰值打印。run 名硬编码 `gl-wan-bf16-smoke`，跑完删 `runs/gl-wan-bf16-smoke/` 即可复跑 |
| `gl_bf16_wan_smoke_v2.sh` | 2 GPU / **4 CPU / 16G** / 00:30:00 | 冒烟 v2 = **CPU/RAM 降配口径（已验证，冒烟一律用它）**：2026-08-14 五 agent 对抗验证裁决档位，当天实测通过（job 57642560，见下面 v2 实测小节）——排队 <1 分钟、epoch 零退化、anon 峰值仅 3.85 GiB。训练配方与 v1 逐字节相同，新增 cgroup v2 内存采样（memory.current + anon/file/shmem 拆分）与 checkpoint 落盘体积硬断言。run 名硬编码 `gl-wan-bf16-smoke-v2` |
| `gl_bf16_wan2gpu.sh` | 2 GPU / **4 CPU / 16G** / **16:00:00** | bf16 长训，与本机 `bf16_wan_local2gpu.sh` 逐项同口径（有效 batch 352、SIGReg N=352）。**walltime 16h 与 2 GPU 超出下述调试限额，2026-08-14 经用户显式放行**；CPU/RAM 于同日经 v2 冒烟实测后由用户拍板「长训按照 4 CPU / 16G」，自带与冒烟 v2 同款 cgroup anon/file 采样，**首个 16G 档长训 run 结束须以采样峰值复核档位** |

### 2026-08-14 冒烟实测（job 57628076 @ gl1502，全量 v7 数据集 1 epoch，bf16、每卡 batch 88）

| 项 | 集群 A40 | 本机 RTX 6000 Ada（基准 run `wan-v7-bf16-72ep-a`） |
|---|---|---|
| epoch 耗时 | **480.8 s** | 379.6 s（首）/ 389.6 s（均） |
| 吞吐 | **185.21 samples/s** | 230–235 samples/s |
| `max_memory_allocated` | **35.74 GiB** | 35.74 GiB（**逐位相同**） |
| `nvidia-smi` 实占 | **40,049 MiB = 86.9%** | 40,604 MiB = 88.1% |
| **MaxRSS（主机内存）** | **50,005,212 K ≈ 47.7 GiB** | 未记录（本机 377 G 从未成为约束） |
| AveCPU | 00:18:04 / 8:50 墙钟 ≈ 2.05 核当量 | — |
| checkpoint 体积 | 954,852,403 B（live + EMA 双权重） | 955 MB |

结论三条：①**A40 比本机慢 1.27×**，72 epoch 外推 ≈ 9.6 h，16 h walltime 裕度 1.6×；
②显存放得下 batch 88，**勿改 batch**；③⚠ **MaxRSS 47.7 GiB 不能当「真实需要 48G」的证据**
——本条为 2026-08-14 当天对抗验证的订正（旧表述「48G 是必需值、降到 32G 会 OOM」是从这一次
被自身 `--mem` 上限钉死的观测做的推断，非实测，已作废）：本 epoch 双卡逻辑读取量 =
253 step × accum 2 × batch 88 × 2 rank × 576 KB ≈ **48.93 GiB**，与申请的 48G、MaxRSS
47.71 GiB 三方两两之差 <3%，是「NFS 页缓存吃满给定上限」的典型信号；集群
`JobAcctGatherType=jobacct_gather/cgroup`（已查 `scontrol show config`），cgroup 记账含
file 页但干净页缓存触顶时被内核回收、不触发 OOM kill。真实不可回收工作集的独立证据：
本机单 rank 进程树 PSS 实测 3.13 GiB（双 rank 上界 ≈6.3 GiB）+ checkpoint save / NCCL /
shm 未测路径余量 ⇒ 估 8–9 GiB。**该推断已被当天 v2 实测证实（见下一小节）。**
另：计算节点能连 HF Hub（启动时读 Wan VAE config 走 `huggingface.co`，实测 200 OK）。

### 2026-08-14 冒烟 v2 降配实测（job 57642560 @ gl1509，4 CPU / 16G，同配方对照 v1）

| 项 | v2（4 CPU / 16G） | v1（8 CPU / 48G） |
|---|---|---|
| 排队时长 | **<1 分钟**（19:34:58 提交 → 19:35:43 起跑） | 长期 `(Priority)` PENDING |
| epoch 耗时 / 吞吐 | **479.9 s / 185.57 samples/s** | 480.8 s / 185.21 samples/s（**零退化**） |
| `max_memory_allocated` | 35.74 GiB（**逐位相同**） | 35.74 GiB |
| `nvidia-smi` 峰值 | 39,345 MiB = 85.4% | 40,049 MiB = 86.9% |
| MaxRSS | 16,540,592 K ≈ **15.77 GiB（贴 16G 上限）** | 47.71 GiB（贴 48G 上限） |
| **cgroup 峰值拆分** | **current=16.00 GiB｜anon=3.85 GiB｜file=12.07 GiB｜shmem=1.38 GiB** | 未采样 |
| TotalCPU | 18:25 / 8:44 墙钟 ≈ 2.11 核当量 | 18:07 / 8:50 ≈ 2.05 核当量 |
| checkpoint | 954,852,403 B（**逐字节相同**），体积硬断言通过 | 954,852,403 B |

判读：①**页缓存假说获双重铁证**——两代 MaxRSS 都精确贴住各自 `--mem` 申请上限
（47.71/48、15.77/16），而 cgroup 拆分显示真实不可回收 anon 峰值仅 **3.85 GiB**
（anon+shmem ≈ 5.2 GiB，与本机 PSS 外推 6.3 GiB 吻合），file 页缓存永远填满剩余配额且
可回收、零 OOM；②**性能零代价**——epoch 耗时/吞吐/显存/checkpoint 与 v1 全部持平或逐位
相同，「cache 减少拖慢顺序流式读」「4 核饿着 8 个 worker」两条担忧均被证伪；③冒烟一律
改用 v2 口径；**长训入口已于同日由用户拍板「长训按照 4 CPU / 16G」**（长训多 epoch 循环
扫同一数据集、cache 语义与单 epoch 冒烟不完全同构，但 56G 数据集任何档位都装不进 cache、
LRU 循环扫描命中率同样趋近 0；长训脚本已内置同款 cgroup 采样，首个 16G 档 run 结束以
anon/file 峰值复核）；④anon 实测 3.85 GiB 支持后续再做 12G 对照，暂不急。

两者都自带：run 目录 fail-loud 守卫（`train.py` 的 `resolve_run_dir` 对已存在目录是
`makedirs(exist_ok=True)` 静默复用，**本身不 fail-loud**，守卫必须写在 slurm 脚本里）、
2 卡口径断言、`.venv/bin/python` 直调（不走 `uv run`——集群侧 uv 装在 greatlakes 自己的
`/home`，而 `.venv/bin/python` 是指向 NFS `uv-python` 的 symlink，双端可用且不联网 sync）。

⚠ 新增 slurm 脚本时注意：`tests/test_train_script_overrides.py` 会 glob
`scripts/train-script-hongzefu/*.sh`，要求**每个 `.sh` 至少含 1 条 Hydra 覆盖、键在 §7.3
白名单内、字面量值不得与 `configs/default.yaml` 相同**。因此 slurm 脚本不能只是
`srun bash <本地入口>.sh`，必须自己直调 `scripts/train.py` 并带覆盖项；脚本内局部变量
一律全大写命名（小写 `key=value` 会被正则误当成 Hydra 覆盖）。

## 分布式 Wan latent 抽取（2026-08-16 新增，slurm-wan-extract）

`scripts/dataset-build/` 下的集群抽取入口（**不在** train-script-hongzefu，故不受
`tests/test_train_script_overrides.py` 的 Hydra 白名单 glob 约束）：

| 脚本 | 资源 | 用途 |
|---|---|---|
| `gl_probe_wan_consistency.sbatch` | 1 GPU / 2 CPU / 12G / 00:30:00 | 一致性探针（只读）：现场编码与 **v7 Ada 权威 .bin** 逐位比对 + 速率/显存/内存/指纹实测（⚠ reference 恒指 v7，指到 v8 会变 A40 自比恒 BITEXACT） |
| `gl_extract_wan_v8.sbatch` | **job array**，每 task 1 GPU / 2 CPU / 12G（full 0-7 / 08:30:00；full400 0-7 / **30:00:00**） | 分片并行抽取（lpt 装箱 + skip_motion 集群口径），断点续传，claim 防撞车；OUT/RAW_DIR/INPUT_MANIFEST 必传（由 prepare_v8_2_extract.sh 提交，不手提） |
| `gl_extract_wan_v8_finalize.sbatch` | 1 GPU / 4 CPU / 12G / 04:00:00 | `--dependency=afterok:<arrayJobId>` 串接：输入 sha256 核验 + 合并 + provenance 同源断言 + 四道守卫（spot_check 经 `--export` 传入：full 64 / full400 **256**） |

**放行记录**：8×1GPU 并发与 8.5h walltime 超出上文调试限额（≤2 GPU、≤30 分钟），
2026-08-16 经用户批准 slurm-wan-extract 计划显式放行（wan-plan §11 的全量抽取审批点
同次放行）。**2026-08-18 v8-400ep 全量抽取二次放行**（dataset-v8-400ep-plan §4 [2]
审批点，用户选「批准，立即提交」）：8×1GPU / 30h walltime / ≈173 GPU·h；实测
array 58239662 分片 Elapsed 22:21–22:57 全 `COMPLETED 0:0`（GPU 峰 4.7 GiB、cgroup
anon 峰 1.7 GiB，2 CPU / 12G 档位复核通过）、finalize 58239663 耗时 31:42。**job array 实测可用**：chaijy2/spgpu 接受 `--array`（job 57854615，2 task
独立调度到 gl1526/gl1514），MaxArraySize=5000——array task 逐个独立调度，等价于
「8 个分开请求的 1-GPU 小 job」，一次提交零手抄。

**⚠ 跨架构一致性结论（2026-08-16 探针 job 57854000 + smoke 演练 57855074/57855075 实测）**：
A40（sm_86）与本机 RTX 6000 Ada（sm_89）**不逐位一致**——max|Δ|≈1.2e-5（latent 值域
O(1–2)，相对 ~1e-6）、97% 元素有差、主体 16–256 ULP；分层指纹把分歧隔离到 VAE encoder
最后一层 conv_out（之前所有层逐位相同）；VAE 权重指纹与软件栈双端逐位同源已实证；
determinism 三档（default / cudnn.deterministic / cudnn.enabled=False）全部无效——
跨架构逐位对齐无 flag 可解。**故集群抽取按「换合同」口径交付**（2026-08-16 用户拍板）：
①集群产出自成一份数据集，metadata 逐 entry 带硬件/软件 provenance，finalize 断言全体
同源（机制上杜绝与本地字节混用）；②验收 = 量化等价（`wan_latents_manifest.py
compare-output --mode equivalence`，max|Δ|≤5e-5）+ 下游等价检查；③集群内部四道守卫
仍零容差（smoke 实测 spot_check 64 条 + oracle 14 条全部 max|diff|=0——A40 同架构
跨节点复算逐位成立）；④rgb_mag 一律本机 `--motion_only` 算（GPU 归约分块依赖 SM 数
84 vs 142，跨架构位不稳；全量 101,235 行实测与基线逐位相等）。

**资源实测（A40）**：速率 0.635 chunk/s/卡（LPT 最重分片 12,670 chunk ≈ 5.5h）；显存峰
5.72 GiB（T=551 压测 max_memory_allocated 1.77 GiB）；cgroup anon 峰 0.84 GiB
（12G 档宽裕，可再降）；CPU 2 核足够（h5/gzip 解压）。

**全量验证实测（2026-08-16，array 57856154 + finalize 57856155，600 entry / 101,235
chunk / 产物 60GB）**：8 分片耗时 5:38:47–5:48:38（极差 3%，LPT 均衡如预期；walltime
8:30 裕度 1.47×）；7 个 task 即时调度、第 8 个因 GPU 配额排队迟起 5.6h 后照常完成
（「分开请求 + 断点续传」的递补语义实证）；finalize 实测仅 **8:38**（含 17GB 输入
sha256 核验 + spot_check 64 全零差 + oracle 1200 chunk 全逐位，远快于 4h 预估）。
验收全绿：600 bin 量化等价 max|Δ|=2.420e-5（阈值 5e-5）、metadata 逐字段、
chunk_motion 逐位（rgb_mag 本机口径 101,235 行与基线逐位相等）、dataloader 七项
断言过、等丢弃率阈值重推 = 0.021994 / keep 99,195（与 default.yaml 现行值逐字相同）。
产物已按临时数据规约删除；`motionjepa-v7-gl/` 保留 data-raw 17GB、输入清单与两份
比对/motion 日志供复用。

**标准流程（2026-08-16 起 = v8 主流程四段，KIND=smoke|full，均本机跑，详见
docs/DATASET_zh.md）**：
1. `prepare_v8_1_stage.sh`：pin 校验（full）→ rsync raw 上 NFS → 输入清单 sha256 →
   `--motion_only` 本机算 rgb_mag 写进 v8 输出目录；
2. `prepare_v8_2_extract.sh`：pre-flight 五项 → 经 gl_submit 提交 array + afterok
   finalize（full 是审批点，须 `CONFIRM_FULL=yes`）；产物直接写 repo 内
   `dataset-4env-v8{,-smoke}/dataset-token`（v8 = A40 集群代际的最终家）；
3. 等 job 全绿后 `prepare_v8_3_verify.sh`：finalize 判定行 + dataloader + 可选基线
   量化等价比对，全绿打 VERIFY_PASS；
4. `prepare_v8_4_downstream.sh`：过滤预览（--raw_root 换根读 /data）+ arm mask +
   rsync /data 提示。
分片中断续跑：删该分片 `_claim_shard*.json` 后 `sbatch --array=<分片号>
--export=ALL,REQUIRE_EMPTY=0,<三路径>` 重提（断点续传，中断损失上界 ≈ 14 分钟）；
finalize 重跑须先把 `wan_chunk_latents/_shards_done/` 里的分片文件移回上一级。
⚠ `motionjepa-v7-gl/smoke-raw/` 是**探针专用**输入子集（7 entry 含最长
ButtonUnmaskSwap_ep3），与 v8 冒烟的 `data-raw-smoke/`（6 entry）集合不同，勿改写；
⚠ 抽取期间 8 task 读写同一 turbo 卷（~132 MB/s 天花板），勿并行跑集群训练；
⚠ v7 库（本机 Ada 产物）仍为现役训练数据与探针基线，训练 data_root 何时切 v8 是
独立决策，切换前须先把 v8 rsync 到 /data 本机副本。

