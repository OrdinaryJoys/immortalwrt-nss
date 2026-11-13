# NSS Root / Producer 事务修复与复核

日期：2026-11-13 CST。状态：**三项有界修正已纳入本地候选并完成宿主组合验证与独立复核；完整事务仍未闭环，不是可刷写批准。**

## 版本与边界

- 本地分支：`codex/ax6-nss-root-transaction-20261113`。
- 父提交：`5e5ccf0bb7b31a0f5890c98a37ca5b256a2749d8`，本批修改尚未提交或推送。
- NSS 厂商源码仍锁定 `6aa14c78e097b29c493ff2fef87e4d35906b2b5a`；不移动上游版本。
- 本地 `qca-nss-drv` release 从 27 增为 28，区分新增修正与旧固件。
- 构建仓仍冻结 `0c0eaba7eba9a70d5631a85e4a7442e1e8c9752c`，锁定父提交 / driver27。
- 旧 stock run `43228223638` 成功，但不包含本批修正；旧产物不能充当本批验收。
- 本轮未构建目标或云端固件，未访问或操作实机，未合 main、发布或改性能开关。

## 已纳入的有界修正

| 项目 | 根因与修正 | 已验证范围 | 未关闭边界 |
| --- | --- | --- | --- |
| 030：probe dummy 分配事务 | 旧路径在 clock/meminfo 等取得后分配 dummy；失败可能沿 `err == 0` 返回，并遗留已取得状态。改为先取得本地 dummy，OOM 立即 `-ENOMEM`；发布给 context 时清空本地别名，前缀失败只释放本地所有者 | 两编译器 ASan/UBSan、独立重放、完整函数提取；两 core、DT/非 DT、10 个 IRQ 失败点与外来所有者保护 | 不是完整 late-probe 回滚；不证明 Linux devres、共享 regulator、FW/DMA 退休安全 |
| 031：零长度 coredump 写入 | Linux 6.18.38 parser 对零长度写返回成功但不赋值；旧 NSS handler 仍写回旧快照，可能覆盖并发策略或触发旧命令。parser 后新增 `!*lenp` no-op 返回 | 实际 NSS handler 与实际 Linux parser；正常命令、读、错误、空写及确定性交错正负控，双编译器和独立重放 | 非空且非零偏移的 strict 写仍是独立开放项；未重写全部并发命令协议 |
| 032：IPQ807x 私有 pdata 事务 | 分配失败漏 node put；未验证 core-id 就索引固定数组；IRQ 解析失败漏掉本地 QGIC unmap，并已提前写 TCM。补引用配对、固定数组准入、本地映射回滚，把完整 TCM 清零和屏障推迟到所有 IRQ 解析成功后 | 全失败前缀、10 个 IRQ 位置、两类 node/cache API 模型、外来所有者保护；Clang/GCC 与独立重放；上游 OF/IRQ-domain/GICv2 代码交叉检查 | 不 dispose 可能借用的 virq，不改有效 id 的全局频率行为；不是完整 probe/FW/provider 回滚 |

030 的 OOM 优先级有意改变：分配失败先于后续 common/DT/FW 错误返回。
分配成功时非 OOM 路径的返回值、资源状态和调用顺序做了差分核验；这不证明所有旧清理路径正确。

032 已原样纳入，SHA256 `cbea3a32627028b1881d1a3564bc060b227a1a879e4586f3f2dc87d81a0b8a28`。
从实际仓库补丁重新准备的 484 文件与受测组合树逐项相同；相对父层只改变 `nss_hal.c`、`nss_init.c`、IPQ807x `nss_hal_pvt.c` 三份生产 C。
固定原有 27 份补丁未改；新增三份无 fuzz/offset。源归档内容重放不是目标工具链编译。

## 测试口径

| 测试 | 当前结果 | 说明 |
| --- | --- | --- |
| 030 新套件 | 每编译器 152 candidate 场景、224 非 OOM 阶段差分、20 精确运行负控；15 runner 单元测试 | 不是 396 个独立功能；224 是 112 个场景的两个观察阶段 |
| 031 新套件 | 每编译器 19 cases；旧源码 / 反向 guard / 屏蔽有效请求分别产生精确 11 / 28 / 2 个失败断言；5 runner 单元测试 | 三个负控变体，不是 41 个不同负控程序 |
| 032 新套件 | 每剖面 132 正控、24 精确负控；Clang/GCC 普通及 ASan/UBSan 重放通过；runner 各 11 正控 / 24 拒绝控制 | 132 是 33 场景乘四种 API 模式；24 是 12 变异体加 12 原始见证，不是 24 个生产缺陷 |
| 原 drv containment | 37 个有界角色通过 | 包含旧行为与宏控制，不是 37 个新增修复 |
| 原 root controls | Clang/GCC 各 23 正控、12 精确负控 | 与 containment 有重叠，不累计成独立修复数量 |
| 原提取与文本门 | 10 个提取单元测试、13 个 targeted-backport 文本检查通过 | 文本检查不证明运行生命周期 |
| 连接表交错见证 | IPv4/IPv6 各正常一次、选定交错两次相同地址释放请求 | 实际提取 C + 替代释放/调度器；未实际释放内核页，未修复、未实机复现 |

最终组合树重新执行：030 Clang/ASan/UBSan 152 / 224 / 20；031 GCC/ASan/UBSan 19 cases 及三个精确负控；032 GCC O2/ASan/UBSan 132 / 24；原 root controls GCC 23 / 12 与 containment 37。相同功能的重复重放不合并计数。
两路非作者复核分别接受 030/031 和 032 的限定范围，没有把根层全部路径或真实硬件认证一并签收。

新套件消费实际准备后的 C，不运行输入目录的脚本。IRQ、NAPI、provider、meminfo、FW 请求和硬件动作仍有宿主替代；不把替代模型称为真实内核执行。
030 的测试资产漂移缺口在独审中被发现并修正：现在冻结输入并绑定编译器、生成 C、二进制及运行前后哈希。

## 根层事务审查

| 阶段 | 所有权与顺序 | 当前结论 |
| --- | --- | --- |
| root 诊断创建 | checked 取得；只回滚已完成前缀；保存首错 | 既有 029 的有界宿主控制通过，本轮未发现需回退的生产差异 |
| sysctl/debugfs 退出 | 先停止入口，再注销并等待已接纳读者 | 有界模型已覆盖；不等于所有跨模块 raw/provider 读者均已排空 |
| producer/frequency/coredump | 关闭请求准入、撤销回调/工作并 join；借用 provider 不能由消费者随意释放 | 029 的部分控制和本批空写已验证；ACK/采样/有效写并发仍待闭环 |
| cold meminfo | 私有取得可按 receipt 回滚；commit 后归属不同 | 028 已保留；030 避开新增 dummy OOM 后置失败，不新增 committed backing free |
| pdata 构造 | node 引用、私有映射与 context 借用指针必须区分 | 032 的限定前缀已修并验；不能顺手 dispose 可能复用的 IRQ domain mapping |
| 成功 probe 后的后置失败 | Linux 注册流程可能已绑定设备，再在模块链接步骤失败 | Linux 会自动 detach；不能再次无条件 unregister，也不能假定负返回必然没有成功 probe |
| 连接表异步事务 | sysctl handler 完成不等于其后续 FW ACK/NACK 完成 | 高优先级 OPEN；free 在 RX drain 前，单所有者及 generation 合同不足 |
| GRE LAG workqueue | root 取得必须有 checked owner、三条排队入口关闭及延迟工作排空 | 分配后缺少完整退休路径；确认泄漏风险，不能直接推断必然 callback UAF |
| 模块退出 / FW backing | CPU 入口关闭和 IRQ/NAPI join 不代表 FW/DMA 已停止 | 必须取得厂商 stop/ACK 或硬件退休依据后才能 unmap/free |

## 剩余优先级与修复合同

1. **P1，连接表所有权与异步退休。** IPv4/IPv6 必须共享可审查的状态机思路：私有准备、host owned、FW published、stopping、retired；每个请求保留 generation 与 DMA device/address/length/direction 凭据。先关新请求，在 ACK 通道仍可用时排空已接纳操作，再停止 callback 入口。FW published 资源未经退休证明不得释放。不能只把 `free_pages()` 移到 unregister 后。
2. **P1/P2，late-probe 与注册失败完整回滚。** 已 commit meminfo 后的 IRQ 等失败仍可能让后续重试因已有资源被拒绝。必须同时覆盖成功设备被框架自动 detach、全局 provider 与 sibling 归属，不能只改 errno 或重复 unregister。
3. **P2，GRE LAG 工作队列。** 把一次性 workqueue 取得纳入 checked root 事务，失败前缀回滚；退出关闭三个 producer，逐节点 cancel/drain 后由唯一 owner destroy。先补真实函数和负控，不能直接补一条 destroy。
4. **P2，共享 provider。** regulator/clock 的 get、enable、borrow、put 不是同一权利；全局频率消费者不能保留已退役 devm handle。需要跨 core owner/reader 合同，不能依据 always-on DT 声称 consumer handle 永久有效。
5. **P2，coredump 非空非零偏移写。** 实际 parser 在 strict 模式可忽略输入却保留正长度；031 不关闭此问题。后续明确与内核 sysctl 的输入合同、警告及偏移语义，再设计无误触发方案。
6. **跨模块开放项。** NSS/EDMA 的持久 DMA/FW 身份、UK/SD/PHY/HPPE provider 与读者退出、SFP/I2C、MU-EDCA 协议编号、rpcd recover/LuCI/备份恢复链，未因本轮 NSS 局部通过而关闭。
7. **旧云产物遗留。** rxvt-unicode terminfo 缺项、Ruby autoreconf、fullcone 符号目录、宿主 init、GENENV 与其余告警仍按上一批证据分别处理；本轮没有顺手修改或宣称修好。

## 上游交叉验证

- CodeLinaro 的 `win.nss.1.1` / `win.nss.1.1.r35` 本轮远端查询仍为配方锁定的 `6aa14c78...`。默认 HEAD 指向另一历史分支，不能按 HEAD 时间或简称直接替换。
- qosmio/openwrt-ipq 的远端身份已核，但本轮未合并。上游身份相同不证明本地补丁正确，身份更新也不自动具备适配资格。
- Linux 6.18.38 的 `alloc_netdev_dummy/free_netdev`、driver-core 的 probe/attach/failure cleanup、sysctl parser 与 DMA 合同均以实际代码核对。
- AX6 的 NSS IRQ 继承 `qcom,msm-qgic2` / GICv2，不是 GICv3。OF 解析与 GICv2 descriptor/domain 建立不依赖 NSS TCM 清零；保持清零及 DSB 在 FW load/core start 之前。该判断不等于热重绑时 FW 已停。

参考一手源码：

- [QSDK NSS driver](https://git.codelinaro.org/clo/qsdk/oss/lklm/nss-drv)
- [qosmio 适配仓库](https://github.com/qosmio/openwrt-ipq)
- [Linux dummy netdev](https://raw.githubusercontent.com/gregkh/linux/v6.18.38/net/core/dev.c)
- [Linux driver probe](https://raw.githubusercontent.com/gregkh/linux/v6.18.38/drivers/base/dd.c)
- [Linux driver registration](https://raw.githubusercontent.com/gregkh/linux/v6.18.38/drivers/base/bus.c)
- [Linux sysctl parser](https://raw.githubusercontent.com/gregkh/linux/v6.18.38/kernel/sysctl.c)
- [Linux DMA API](https://raw.githubusercontent.com/gregkh/linux/v6.18.38/Documentation/core-api/dma-api.rst)
- [Linux OF IRQ](https://raw.githubusercontent.com/gregkh/linux/v6.18.38/drivers/of/irq.c)
- [Linux GICv2](https://raw.githubusercontent.com/gregkh/linux/v6.18.38/drivers/irqchip/irq-gic.c)

## 性能与下一道门

本批改动位于初始化和控制面，没有改稳态包处理算法、NAPI/GRO、IRQ/RPS/PBUF、时钟或 Wi-Fi 参数；不宣称吞吐提升或最高性能。
资源泄漏与错误发布修正有助于故障边界正确，但延时、丢包、双向吞吐和真实退出仍需后续单独授权测试。

本轮 030/031/032 的来源、独立复核、组合实际源码重放已完成。下一步优先完成上列连接表与 late-probe 的事务合同，再审定可交付范围及 driver28 的完整输入清单与新 CI 合同。其他 SoC 与全部内核配置尚未目标编译验证，不得由 AX6 宿主矩阵推导全平台通过。
旧 build 的 release27/profile/hash 门必须保留为旧批证据；不得从待验输入自动刷新期望哈希求通过。
未来云构建需要冻结新提交、更新经审查的锁和门、完整 Lint 后一次 stock，并独立检查实际产物；本轮不派发。

本轮原始证据：`/Volumes/FX-MD87/Review-AX6/audits/20261113/nss-root-transaction/`。
其中 `probe-independent/REVIEW.md` 是 030/031 非作者复核；`producer-worker/pdata-independent/GO.json` 和相邻说明是 032 非作者签收；`CURRENT-STATE.json` 保存最终源与实测记录回读。
`CONNECTION-TRANSACTION-NEXT.md` 保存连接表下一层合同，`connection-release-repro/RESULT.json` 保存未修交错见证。审查过程中发现的测试输入绑定缺口和独审 patch 备份文件污染已修正；早期失败记录保留，最终证据与开发试跑分开。
