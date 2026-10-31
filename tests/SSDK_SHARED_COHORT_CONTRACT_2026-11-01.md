# UK/SD 全局与逐设备生命周期合同

## 范围和状态

基线 d220e99be27570bef24ac2028450a85f669cd20b；候选分支
codex/ax6-shared-prefix-contract-20261101。SSDK pin 保持
d9a196497ecee2530722d906e0efe1b7408b6ef6，候选 release21，DP9 不变。
此文件、纯顺序模型与生产修复必须分开解释。

- 042：原生 Linux API mutex 静态初始化、同模块重试不重置；补齐可选
  API_LOCK 对象选择。默认 FALSE 未改变，默认构建不链接这个对象。
- 043：正常根退出先完成所有列举的 driver/switch stop，再退出所有 SFP，
  再按原序清理 SDK。不是所有 producer、reader 或失败回滚的证明。
- `ssdk-cohort-contract/contract.py`：未来生产协调器的可执行设计合同，
  **没有安装到 SSDK**。它假定原子记账步骤及可信资源/排空证书，不提供内核
  锁、内存序、真实析构、RCU/SRCU 或硬件空闲证明。
- 本阶段禁止 make、模块/目标/固件/云构建、推送、主线合并、Release 和实机。
  只允许文本重放及全新隔离宿主夹具；不能借此给出运行或最高性能保证。

## 必须保持的资源边界

1. 根模块持有者：唯一控制全局准入与总退出；不能把 `module_exit` 的 void
   返回当作拒绝卸载机制。根失败不能只 free_priv 后留下其他工作源。
2. 设备持有者：成功取得的实际实例才增加 consumer；reserve、cfg 非NULL、
   设备编号或注册失败都不是取得成功。代号和实例身份不能回绕/混认。
3. UK transport：全局 endpoint/buffer/命令锁；041a 的传输保护不涵盖 FAL、
   SD、直接 MMIO 或 PHY 读者。第三方 endpoint 不能领养或 deregister。
4. SD callbacks：12 个有类型的借用指针，非NULL覆盖、NULL继承。回调本身
   不分配、不取得 provider 引用；相同函数地址也不代表 dev_id 对应映射存活。
5. API mutex：原生锁在模块加载时就绪，重试或最后设备退出不能重置/销毁。
   combined/standalone 的 spin/mutex 类型冲突和潜在递归锁仍未修。
6. PHY ops：按 PHY 类型共享，不等于每设备 phy_info。必须分别记“本轮创建”
   与“借用已有表”及各设备/读者引用，不能在每设备 cleanup 中盲 free 全局表。
7. 平台 provider：MMIO、MDIO/I2C、时钟及设备上下文在所有依赖读者结束前
   存活；撤掉函数指针或关闭 UK 不能替代这个条件。

## 发布和读者合同

全局阶段 OFF -> BUILD -> LIVE -> STOPPING -> PREFIX_RETIRED -> OFF。
它是设计，不是当前驱动已有的状态机。设备阶段账本需覆盖 platform、HSL、
VLAN、adapter、PHY、SFP 与各工作源，并区分 owned/borrowed/skip/
failed-clean/failed-held/unknown；未知绝不授权清理。

- 在 root BUILD 中先私有构造所有设备所需的 callback union，包含后到设备
  合法提供的 PSGMII/uniphy 等可选项，不能按“首设备非NULL”冻结全部能力。
- root commit 不等于 FAL/HSL 子构造返回：后续 switch 注册还读取寄存器。
  commit 必须等全部实际阶段成功，不能让 PHY 成功掩盖 FAL 失败。
- 公开读者在 LIVE 准入。UK/FAL/SD/direct/PHY 必须各有实际调用点保护，
  在共享指针取得引用之前与最后退休串行化；不能先取裸指针再加计数。
- 内部构造/析构继续访问必须使用显式、设备匹配且有期限的 operation，
  不接受“当前线程”“初始化中”或重入宏作为通行证。
- 关闭准入不等于排空；所有参与读者、工作源及跨设备依赖都需独立证书。
  get/put 不能漏接直接 qca_switch_reg_read 等绕过 SD 的路径。
- SD 调用存在睡眠和 IRQ-off 路径；不批量外包 mutex 或经典 RCU。
  先逐类确认上下文，再选择同步和慢路径，不能把文档计数当作实际保护。
- 标量/void legacy API 的 fallback 不能冒充失败读取得到的有效硬件数据。

## 回滚与最后持有者退休

1. 准入/冲突检查在任何外部发布和改旧资源前完成，保存 typed vector 和
   每项提供者上下文。只退本轮成功取得的资源，不退 borrowed/foreign。
2. 首错保留；补偿失败另外记录。失败导致状态 UNKNOWN 时保留所有权证据，
   不强 free、不假成功、不清账后允许另一轮覆盖。
3. 根 BUILD 失败也走同一资源账本，不把全局 once 当逐设备成功标记。
4. close public admission -> 停止并排空生产者 -> SFP -> 设备 SDK 子资源。
   043 只实现正常退出中列举调用的跨设备顺序，不实现这整套协议。
5. 当前 VLAN cleanup 仅释放软件 DB/list/pool，没有发现 SD/HW 析构调用；
   不据猜测重排到 HSL 前。HSL 成功退出不授权丢掉仍持有 VLAN/adapter/PHY
   的 consumer。所读 PHY exit 插槽均为空，不能编造强制 post-FAL SD 依赖。
6. SFP 退出仍读取 HSL/PHY/总线元数据，必须在这些资源退出之前。
   共享 PHY 表只在最后已证明的引用退休后清理，borrowed 表不清理。
7. 全部设备消费者、读者和共享 PHY 引用退完，且当前发布身份仍属本轮，
   才能注销 UK/恢复借用 SD 基线。别人替换的发布不能覆盖。
8. 最后再 unmap/clock/provider/free_priv；UK BUSY 不得转换成假成功，
   UK UNKNOWN 不得盲重试。还必须解决正常 module_exit 不可拒绝的问题。

## 分阶段实施与验证

本轮先验收 042，再验收 043。后续生产集成顺序：

1. 逐调用者的读者/生产者入口清单及可执行资源所有权证书。
2. 全局协调器与设备实例日志、私有 callback union、内部继续访问 API。
3. 根初始化错误传播和准确逆向回滚，包含 adapter/PHY 的真实析构能力。
4. 最后持有者清理、读者排空和模块退出契约联合接线；不能只改 HSL 一处。
5. root fatal、第三方替换、空设备/多设备、所有分配与注册失败、UNKNOWN、
   再入/重试/多代号、并发与真实内核上下文分别验证。
6. 用户另行允许后才做目标工具链/最终产物、实机生命周期和吞吐验证。

需要保留的开放项：完整 C01/C04、SD/direct/exported reader、共享 PHY 表、
根部分失败、adapter 析构、combined/standalone API_LOCK、实际硬件/FW/DMA
退休、构建与运行资格。不得把本轮局部成功计为这些整项关闭。

## 上游依据

精确 Git pin 和准备回执优先。只读对照 openwrt/qca-ssdk 镜像
bb4f3f0b947ebfce51c78a8d39f57c7c758521c9；它不是 pin 的后代，不能直接合并。
CodeLinaro 在线访问受限，不声称已获取其中未公开/不可读内容或审核全部最新提交。

- [上游 SSDK init](https://github.com/openwrt/qca-ssdk/blob/bb4f3f0b947ebfce51c78a8d39f57c7c758521c9/src/init/ssdk_init.c)
- [Linux mutex 定义和初始化约束](https://github.com/torvalds/linux/blob/v6.18/include/linux/mutex.h)
- [引用取得与最后释放规则](https://github.com/torvalds/linux/blob/v6.18/Documentation/core-api/kref.rst)
- [RCU 使用前提](https://github.com/torvalds/linux/blob/v6.18/Documentation/RCU/checklist.rst)

这些规则提供约束，不构成 Qualcomm 对本地候选补丁的背书。

## 本阶段宿主证据

准确31层/692纯文本准备，无偏移/模糊，旧29层保持不变；新增三个输出。
042 新父 GCC16/Clang17-ASan 各13正控、8种源码变异/15语义负控。
043 新父 GCC/Clang 各312完整调用轨迹、六种实际函数变异/六语义负控，
覆盖0..3设备、所有登记位图、六类chip guard/SFP开关和多次清理失败。
31项纯顺序模型及六个模型退化控制另列，不能当真实SDK执行。
父数据核回绑定所有输入与生成尾hash；源码和测试质量独审需各自身份匹配。
作者提取空格错误及模型负控文案错误均保留失败结果，不改生产去追绿。

证据目录 `/Volumes/FX-MD87/Review-AX6/audits/20261101/ssdk-cohort-contract`。
最终说明 `/Volumes/FX-MD87/Review/AX6_SHARED_COHORT_CONTRACT_AND_ROOT_RETIREMENT_2026-11-01.md`。
