# ManiSkill / robomme 多进程与多 worker 生成：实测经验（通用正本，源自 robomme_benchmark_MotionJEPANewTask 2026-09-22）

只收本仓库 2026-09-21～22 亲自跑出来、有判定行或原始数字为证的结论。与集群操作相关的条目在
[`../greatlakes.md`](../greatlakes.md)，容差校验方法与命令在 robomme_benchmark_MotionJEPANewTask 仓库的 `scripts/test-vs-original/README.md`。

## 一、不可复现的根源只有一个：`mplib` 的 RRT 用墙钟预算

`.venv/lib/python3.11/site-packages/mplib/planner.py`：`planning_time=1`（"time limit for RRT"）。
同一个 seed 下，1 秒内迭代次数不同就搜出不同路径。所以：

| 条件 | 实测 |
|---|---|
| 同一次运行内、单 worker | 五路（A1/A2/B/C/D）144 局 720 对逐位相同 |
| 同一次运行内、4 worker | 144 局里 **1 局**（`PickHighlight/ep3`）帧数 641↔643；其余全同 |
| 单 worker、跨运行/跨节点 | 同一条身份 647 / 641 / 648 / 652 / 653 都出现过 |
| 对原版发布集（20 worker 生成） | 同架构单 worker：sled-vail 47/48 局在 1e-16 内、aspen 47/48 局**逐位相同**；例外都是 `PickHighlight/ep3` |

**推论**：
- 判据必须建立在**同一次运行内**的对拍（背靠背产出、共享同一段机器时间）；不能承诺"换台机器按同一份清单重跑得到同样的字节"。
- 要复现某批确切产物，只能用那批存档；"存档 + 校验和"比"可重跑"可靠。
- 多 worker 不是"普遍污染"：争抢只在时序临界的身份上掷骰子（`FailRecoverXY` + hard、失败恢复要重规划的局最敏感）。
- `C↔D`（显式配置 vs 回注冻结规格）在 4 worker 下仍 144/144 逐字节相同——D 重放的是 C 冻结下来的规划结果，掷骰子的环节被跳过。

## 二、跨 GPU 架构：永远不会逐位相同，但布局层是不变量

同代码、同配置、同单 worker，sled-vail（RTX 6000 Ada，sm_89）vs A40（sm_86）：整文件 108 对 0 个相同。

| 层 | 跨架构表现 |
|---|---|
| `timestep_0` 的 `front_depth`/`front_rgb`（reset 后整场景渲染） | 绝大多数局**逐像素相同**；reset 前有物理沉降的局（InsertPeg/1、PickHighlight/7、VideoRepick/11）差 0.13%～2.5% 像素 |
| `timestep_0` 的 `info/grounded_subgoal`（segmentation 算出的目标中心 `<y,x>`） | 几乎全同；个别局布局相同但**首个目标物选择不同**（BinFill/ep2 red↔green）——规划层差异 |
| 手臂通道（`joint_action[:7]`、`joint_state`、`eef_state`）同一条规划 | p99 ≤ 0.019 rad，从第 14～46 帧起漂移 |
| 帧数 | 约 1/3 的局不同，其中一半只差 ±1 帧 |
| 真重规划（帧差 > 4、手臂差达弧度级） | 10～15% 的局 |
| 由示范执行结果生成的指令（VideoPlaceOrder `first/second target`） | 示范重规划后**指令文本随之变** |

## 三、两个必须知道的数据结构陷阱

1. **夹爪元素**：`joint_action[7]`、`eef_action[6]` 取 ±1。翻转帧差 1 帧就造出 2.0 的"差异"，逐元素比会把同一条规划误判成重规划。**按翻转事件比**（次数相等、帧号偏移 ≤ 容差）。
2. **末段错位**：多/少 1 帧让后续整段错位一帧，`joint_state` max 飙到 0.7 而 p99 仅 0.03。手臂比较要允许 ±N 帧错位取最小差，主判据用 p99、max 只作宽松上界。

## 四、官方比较器的边界

`compare_joint_actions` 只比 `joint_action`、`delta != 0` 零容差计数、`max_abs_diff ≤ 1e-8` 判过，帧数/帧序不等的局报 `timestep sets do not match` 后**整局跳过**。
历史轮（1600 局、同架构 20 worker）对发布集：`max_abs_diff=0.0079`、错位 10 局；本轮 5d（144 局、A40 单 worker）：`0.0197`、错位 39 局。
两者都判 `failed`，且**错位局根本没进数值比较**——它不是为"多 worker 对原版"设计的。`validate_generated_dataset_contract` 只做单侧合同审计（seed / difficulty / 末帧 `is_completed` / `joint_action` 形状与有限性），可以原样复用。

## 五、进程模型与吞吐

- 官方 `generate_dataset.py`：`ProcessPoolExecutor(spawn)`，`DEFAULT_WORKERS=20`，`_parse_gpus` 只接受 `"0"`（生成锁在物理 GPU 0）；`max_workers=min(workers, len(jobs))`——**单身份时 4 worker 退化成 1**，验多 worker 等价性时至少放 9 条身份。
- 进程复用安全：同一 worker 进程连续跑甲→乙→甲，与独立进程逐位相同（`WORKER_ISOLATION=PASS`）。不可复现的来源是并行争抢，不是复用。
- 单 worker 单局吞吐：sled-vail 约 25 帧/秒（SwingXtimes 19 s、VideoPlaceOrder 45 s）；aspen A6000 约 52 s/局均值；A40 约慢 1.4 倍。三个 Video 环境每局 1000～1400 帧，占 48 局总时长近四成。
- 4 worker（4 CPU 的 job）：36 局 273～685 s，约为单 worker 的 2.1～2.2 倍吞吐。
- 4 worker 下用 `--gpus 0`、`CUDA_VISIBLE_DEVICES=0`；官方与本仓库 runner 都不做多卡分配。

## 六、容差校验的结论（详见 `scripts/test-vs-original/`）

- 按硬件分三档：`a6000`（aspen，逐位为主）/ `ada`（sled-vail，1e-6）/ `a40`（松，手臂 p99 0.04、帧差 4、REPLAN 率 ≤ 0.2188）。判定行必须标档位，`--tier auto` 用 `nvidia-smi` 选。
- 每局 IDENTICAL / DRIFT / REPLAN / FAIL；FAIL 只来自合同层与布局层（ts0 目标中心 + ts0 深度/rgb 图像）；规划层差异一律 REPLAN。
- 松档对 3 cm 级布局扰动没有检出力（ts0 图像阈值被跨架构物理沉降推到 5%/130）；**布局级回归用紧档查**。
- 三份 A40 144 局产物（新跑 4 worker、旧单 worker、旧 4 worker）四类计数完全相同（130/14/0）：判定对 worker 数与批次稳定。
- 全部比较一律"产物 vs 原版发布集"，产物互比只用于理解噪声结构、不进标定。

## 七、操作教训（2026-09-22 踩过的）

1. **`SAPIEN_DISABLE_RAY_TRACING=1` 不能用来绕问题**（用户明令）：它换渲染路径，产物不再逐位可比。
2. **删大目录前先抠出小元数据**：`run.log`、`run_config.json`（含 hostname/GPU/驱动指纹）、`results/*.json`、`jobs/`、`logs/`、合并后的 metadata 只有几百 KB，是复现场景的关键证据；本轮 sled-vail 与 greatlakes 两条线的这些文件随测试目录一起删了，只有 aspen 那份拦下来。
3. **NFS 上做逐帧比较很慢**：144 局全字段读取 10～15 分钟、合并 40 GB 约 25 分钟；多条比较链并行只是分摊等待，带宽是共享的。
4. **在同一台机器上串行跑新旧代码对比**比跨机器/跨批次对比干净——只有一个变量。
5. 设计 subagent 可能重做主会话已完成的探针而长时间无产出；主会话掌握全部数据时直接整合，不必等它。
