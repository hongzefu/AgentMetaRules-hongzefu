# AWS p4de 单机（各项目「环境 B」）硬件与网络连通性

2026-10-13 在本机实测记录（只读探测 + 两次 8 GiB 直写直读磁盘测试）。这是带日期的记录，不是判据门槛；硬件或网络变化时以当场实测为准，按第 0 条记录差异。

## 一句话结论

AWS `p4de.24xlarge`（us-west-2c）：8 × A100-SXM4-80GB 全互联 NVLink、96 vCPU、1.1 TiB 内存、`/scratch` 为 8 块本地 NVMe 组成的 6.9 T RAID0（实测直写 2.8 GB/s、直读 4.0 GB/s）。出网畅通、无代理，GitHub / Hugging Face / PyPI 都可直连；无 GreatLakes / Slurm 访问。**GitHub 必须用 `~/.ssh/id_ed25519_hongzefu`**，默认 key 属于另一个账号。

## 主机与系统

| 项 | 值 |
|---|---|
| 实例类型 | `p4de.24xlarge`，区域 `us-west-2`，可用区 `us-west-2c` |
| 主机名 | `ip-10-242-11-177.us-west-2.compute.internal` |
| 系统 | Amazon Linux 2023（2023.12.20260727），内核 `6.12.94-123.192.amzn2023.x86_64` |
| 登录账号 | `ec2-user`，**多人共用**（实测同时 6 个会话；`/shared` 下有他人的 openpi / robocasa 等仓库） |
| 资源限制 | `ulimit -n` 1048576，进程数不限 |
| 工具 | `uv` 0.12.2（`~/.local/bin/uv`）、`tmux`、`docker` 25.0.14、`aws` CLI（SSO 令牌已过期，`sts get-caller-identity` 报错）；没有 `gh`；系统 `python3` 是 3.9.25，项目一律走 uv |

## CPU 与内存

| 项 | 值 |
|---|---|
| CPU | 2 × Intel Xeon Platinum 8275CL @ 3.00GHz，每路 24 核，超线程 → 96 vCPU |
| NUMA | 2 个节点：node0 = CPU 0–23,48–71；node1 = CPU 24–47,72–95；L3 共 71.5 MiB |
| 内存 | 1121 GiB，无 swap |
| `/dev/shm` | tmpfs 561 G（DataLoader 共享内存余量充足） |

## GPU

| 项 | 值 |
|---|---|
| 型号 | 8 × `NVIDIA A100-SXM4-80GB`（81920 MiB / 卡） |
| 驱动 / CUDA | 驱动 595.71.05，CUDA 13.2 |
| 互联 | `nvidia-smi topo -m` 任意两卡均为 `NV12`（12 条 NVLink 经 NVSwitch 全互联）；`nvidia-fabricmanager` 服务 active |
| NUMA 亲和 | GPU 0–3 → node0（CPU 0–23,48–71）；GPU 4–7 → node1（CPU 24–47,72–95）。绑核时按此分组 |
| PCIe | Gen4 x16 |
| GPUDirect 相关内核模块 | `gdrdrv`、`efa_nv_peermem` 已加载 |

## 存储

| 挂载点 | 介质 | 容量（2026-10-13 占用） | 用途 |
|---|---|---|---|
| `/` | EBS `nvme0n1`，xfs | 1.0 T（已用 141 G） | 系统与 `$HOME`；**不放持久化项目文件** |
| `/scratch` | `/dev/md0`：8 × 875 G EC2 实例存储 NVMe 的 RAID0（512k chunk），xfs | 6.9 T（已用 4.6 T，余 2.3 T） | 一切持久化文件落 `/scratch/hongze/`（全局约定）|
| `/shared` | Lustre（FSx，`10.242.11.5@tcp:/nowptb4v`） | 6.8 T（已用 1.4 T） | 他人共享数据与代码；不是本项目落点 |

实测 `/scratch`（`dd bs=1M count=8192`，`oflag/iflag=direct`）：顺序写 **2.8 GB/s**、顺序读 **4.0 GB/s**。

⚠ **实例存储是临时盘**：实例 stop / 终止或宿主机故障时 `/scratch` 整盘清空（reboot 不丢）。重要产物（checkpoint、留档）要另有远端副本（GitHub、HF bucket 等）。

## 网络

### 拓扑

| 项 | 值 |
|---|---|
| 网卡 | `ens32`（ENA），私网 `10.242.11.177/24`；`docker0` 未启用 |
| VPC / 子网 / 安全组 | `vpc-0fc6459545e0ae6c8` / `subnet-029adfb9e225d68f8` / `sg-08980476771f2dd5b` |
| 默认路由 / DNS | `10.242.11.1` / VPC 解析器 `10.242.0.2` |
| 出网公网 IP | `44.230.63.13`（`checkip.amazonaws.com` 所见） |
| 代理 | 无（没有任何 `*_proxy` 环境变量） |
| EFA | 内核模块 `efa` 已加载，`/sys/class/infiniband` 下有设备 `0`，但没有 `/dev/infiniband`、`lspci` 只看到 ENA——**单机训练用 NVLink 即可，跨机 EFA 未验证可用** |
| IAM | 实例角色 `AmazonSSMRoleForInstancesQuickSetup`（SSM 管理用，不应假设有 S3 读写权限） |

### 出站连通性与速度（2026-10-13）

| 目标 | 结果 | 延迟（ping 平均） | 实测下载 |
|---|---|---|---|
| github.com | HTTPS 200；SSH 22 端口通 | 13.4 ms | release 小文件约 21 MB/s（11 MB，受 TCP 起速限制） |
| huggingface.co | 200 | 5.9 ms | 440 MB safetensors 约 **96 MB/s**（4.6 s） |
| pypi.org / files.pythonhosted.org | 200 | 7.3 ms | 19 MB 源码包约 66 MB/s |
| download.pytorch.org | 403（根路径，正常；wheel 路径可用） | — | — |
| conda.anaconda.org | 302 | — | — |
| s3.amazonaws.com | 307 | — | — |
| api.anthropic.com / google.com / 8.8.8.8 | 通 | 8.8.8.8 7.7 ms | — |
| 非常用出站端口（8080、587） | 通 | — | — |

没有出站防火墙限制可见；大文件从 HF / PyPI 拉取不是瓶颈。

### 入站

- 监听 `0.0.0.0:22`（sshd）、`0.0.0.0:8888`、`0.0.0.0:9091`，其余服务只绑 127.0.0.1；`*:988` 是 Lustre LNet。
- 从本机连自己的公网 IP 22 端口不通（安全组或 NAT 回环限制），**公网入站是否开放未验证**；对外暴露服务前先查安全组 `sg-08980476771f2dd5b`。

## GitHub 身份（重要）

| key | GitHub 认证身份 | 对 hongzefu 仓库 |
|---|---|---|
| `~/.ssh/id_rsa`（默认，ssh 不带 `-i` 时使用） | `yinpei-tri` | **无写权限**（push 报 access rights 错误） |
| `~/.ssh/id_ed25519_hongzefu` | `hongzefu` | 可读写 |

用户 2026-10-13 原话：「~/.ssh/id_ed25519_hongzefu 这台机器以后都用这个」。落地方式：

- `~/.gitconfig` 里加 `includeIf "gitdir:/scratch/hongze/"`，指向 `/scratch/hongze/.config/git/hongzefu.gitconfig`（写 `core.sshCommand = ssh -i ~/.ssh/id_ed25519_hongzefu -o IdentitiesOnly=yes` 与 hongzefu 的 `user`）。`/scratch/hongze/` 下所有仓库自动生效，不改动账号里其他人的仓库。
- 新克隆时 includeIf 还没生效（目标目录还不是仓库），首次 clone 用 `GIT_SSH_COMMAND="ssh -i ~/.ssh/id_ed25519_hongzefu -o IdentitiesOnly=yes" git clone git@github.com:hongzefu/<repo>.git`。
- **不要创建 `~/.ssh/config`**：各项目第 0 条判据表把「`~/.ssh/config` 不存在」写成环境 B 的判据，创建后所有仓库的环境判定都会冲突。
- 本机没有 `gh` CLI，PR 等操作需另行安装或在网页上做。

## 复测命令

```bash
TOK=$(curl -s -X PUT http://169.254.169.254/latest/api/token -H "X-aws-ec2-metadata-token-ttl-seconds: 60")
curl -s -H "X-aws-ec2-metadata-token: $TOK" http://169.254.169.254/latest/meta-data/instance-type; echo
lscpu | egrep 'Model name|^CPU\(s\)|NUMA node'; free -g; df -hT / /scratch /shared; cat /proc/mdstat
nvidia-smi --query-gpu=index,name,memory.total,driver_version --format=csv; nvidia-smi topo -m
ip -br addr; curl -s https://checkip.amazonaws.com
for u in https://github.com https://huggingface.co https://pypi.org/simple/; do curl -s -o /dev/null -m8 -w "$u %{http_code} %{time_total}s\n" $u; done
ssh -i ~/.ssh/id_ed25519_hongzefu -o IdentitiesOnly=yes -T git@github.com
```
