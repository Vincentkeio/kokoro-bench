# kokoro-bench

一键测完一台 VPS 的**硬件 / 磁盘 / CPU / 网络 / IP 质量 / 回程路由**，输出**结构化 JSON**。

给探针、监控面板、自动化流水线用的 —— 不是给人看的彩色终端。

```bash
curl -fsSL https://raw.githubusercontent.com/kokoro-probe/kokoro-bench/main/kokoro-bench.sh | bash
```

---

## 为什么又造一个轮子

社区已经有一堆优秀的一键脚本（YABS、IPQuality、NetQuality、融合怪、NodeQuality…），
它们**给人看**都很好用。但要把结果喂给程序，就都不太合适：

| 问题 | 实际表现 |
| --- | --- |
| 输出是彩色终端 | 进度条、转圈动画（大量 `\r` 帧）、赞助商广告 |
| JSON 夹在中间 | 得先正则捞出最外层 `{}`，还要赌脚本没改版 |
| 字段结构会变 | 按固定路径取值的代码，脚本一升级就失效 |
| 一项失败全盘皆输 | 某个工具装不上，整轮什么都没有 |

实测跑一遍 NodeQuality 抓下来的日志，**九成是广告和动画帧**，真正的数据夹在里面。
硬解析它，等于逆着它的设计走。

所以这个脚本只坚持一件事：

> **输出即接口。**

---

## 设计

```
stdout  =  每行一个 JSON 事件（NDJSON），程序逐行读、逐行入库
stderr  =  给人看的进度（彩色、转圈，随便刷，不影响解析）
```

事件类型：

```jsonc
{"event":"start",   "schema":1, "tests":["env","sysinfo","disk","cpu","net","ip","route"]}
{"event":"progress","test":"disk","pct":30,"msg":"fio 顺序读写"}
{"event":"result",  "test":"disk","ok":true,"data":{"seq_read_mbs":1704,"seq_write_mbs":1707}}
{"event":"result",  "test":"net", "ok":false,"error":"测速失败：..."}
{"event":"done",    "ok":true, "elapsed_ms":41200, "failed":[]}
```

**每一项独立失败。** 某个工具装不上，只影响那一项，其余照跑照报 ——
跑分脚本最忌讳"跑到一半整个挂掉，什么结果都没有"。

**不编造结果。** 测不了就明确报 `skipped` 或 `ok:false`，
绝不报一个 `0` 出来。`0 MB/s` 和"没测成"是两回事，前者会让人以为磁盘真这么慢。

---

## 用法

```bash
bash kokoro-bench.sh                    # 全部（默认）
bash kokoro-bench.sh --only disk,cpu    # 只跑指定项
bash kokoro-bench.sh --list             # 列出可跑的项
bash kokoro-bench.sh --no-install       # 不自动装依赖（缺啥降级/跳过）
```

## 测试项

| 项 | 内容 | 依赖 | 无依赖时 |
| --- | --- | --- | --- |
| `env` | 环境预检（缺 `/dev/zero`、是否 root…） | 无 | — |
| `sysinfo` | CPU 型号 / 核数 / 内存 / 磁盘 / 系统 / 虚拟化 | 无 | — |
| `disk` | fio 顺序读写 + 4K 随机 IOPS | fio | dd（需 `/dev/zero`），否则报 skipped |
| `cpu` | sysbench 单核 / 多核 | sysbench | openssl sha256 吞吐 |
| `net` | 上下行测速 + 延迟 | speedtest | curl 下载测速 |
| `ip` | IP 类型 / 风险分 / 流媒体解锁 | python3 + xykt/IPQuality | 报错并跳过 |
| `route` | 三网回程路由跳数 | nexttrace | 报错并跳过 |

依赖**按需自动安装**（apt / dnf / yum / apk），装包失败会重试 3 次 ——
并发跑多个测试时 apt 锁会冲突，一次失败就放弃太脆。

`ip` 这一项复用的是社区事实标准 [xykt/IPQuality](https://github.com/xykt/IPQuality)：
流媒体解锁要打一堆厂商接口、判断各种"地区不可用"的文案，自己实现很容易失效。
**我们只做"翻译"（把它的 JSON 转成我们的结构），不重新发明。**

---

## 输出示例

```json
{"event":"start","schema":1,"tests":["env","sysinfo","disk","cpu"]}
{"event":"result","test":"env","ok":true,"data":{"virt":"kvm","root":true,"issues":[]}}
{"event":"result","test":"sysinfo","ok":true,"data":{"cpu":"Intel(R) Xeon(R) Platinum 8272CL CPU @ 2.60GHz","cores":1,"mem_total":1014341632,"os":"Debian GNU/Linux 13 (trixie)","virt":"kvm"}}
{"event":"result","test":"disk","ok":true,"data":{"seq_read_mbs":1704,"seq_write_mbs":1707,"rand4k_read_iops":284157,"rand4k_write_iops":283919,"tool":"fio"}}
{"event":"result","test":"cpu","ok":true,"data":{"single_eps":1073.48,"multi_eps":1074.15,"threads":1,"tool":"sysbench"}}
{"event":"done","ok":true,"elapsed_ms":66198,"failed":[]}
```

## 环境预检会报出什么

有些小鸡的环境是坏的，表现出来是"某个测试莫名其妙失败"，排查半天。
`env` 这一项把它变成一条明确的信息：

```json
{"event":"result","test":"env","ok":true,"data":{
  "virt":"kvm","root":true,
  "issues":["缺少 /dev/zero（devtmpfs 异常，dd 类测试会失败）","缺少 /dev/urandom","/dev/null 不是设备节点（环境不标准）"]
}}
```

---

## 许可

MIT
