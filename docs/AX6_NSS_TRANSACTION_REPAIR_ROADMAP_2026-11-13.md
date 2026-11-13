# NSS 连接表、late-probe 与 GRE 完整事务修复路线

证据日期：2026-11-13 07:07 CST。当前状态：三路专项分析与非作者独审已完成，IR-01/02/03补充已回读；路线有限通过，FW/provider/身份与复用机制等实施阻塞保留。

本轮按用户要求先规划：只读源码、交叉核对上游合同及保存文档；不新增生产或测试代码，不执行编译、云构建、实机访问或配置操作。本文件不是修复完成、固件可交付或实机性能通过的声明。

## 1. 冻结输入与已完成边界

| 输入 | 本轮核对的身份/边界 |
| --- | --- |
| 源码候选 | `codex/ax6-nss-root-transaction-20261113`，HEAD `5e5ccf0bb7b31a0f5890c98a37ca5b256a2749d8` |
| 本地既有增量 | 未提交的 030/031/032、driver release28 与三个宿主测试目录；原样保留，不重复算成本轮修复 |
| 实际展开源码 | `/Volumes/FX-MD87/Review-AX6/audits/20261113/nss-root-transaction/integrated-032/source`，不是只看补丁标题 |
| 厂商来源 | QSDK NSS driver `6aa14c78e097b29c493ff2fef87e4d35906b2b5a`，不移动 pin、不整仓合并上游 |
| 构建仓 | `0c0eaba7eba9a70d5631a85e4a7442e1e8c9752c`，本轮开始时干净，仍锁旧 source/driver27 |
| 当前软件证据 | 030/031/032 有前一阶段限定宿主验证和独审；连接表、late-probe 整体、GRE 退休不在该验收范围 |
| 实机证据 | 本轮没有采集；不能把源码可达风险称为已复现的路由崩溃、吞吐根因或当前设备配置错误 |

前一阶段说明：`docs/AX6_NSS_ROOT_TRANSACTION_2026-11-13.md`。本轮旁路证据：`/Volumes/FX-MD87/Review-AX6/audits/20261113/nss-root-transaction-plan/`。不运行封存目录内生成器、旧测试程序或产物。

## 2. 本轮已核清的问题与归因

下列行号对应上述实际展开树；厂商原版和本地修正后的行号不可混用。

| 编号/优先级 | 已见代码事实 | 根因/影响与尚未证明的部分 |
| --- | --- | --- |
| CT01 / P1 | IPv4 `nss_ipv4.c:409,498,586`，IPv6 对称路径；回调和清理共用可变全局表 | 无事务身份和单一释放所有者；既有宿主见证可产生重复释放请求，不等于真实内核 double-free 已复现 |
| CT02 / P1 | IPv4 `443-490`，IPv6 对称路径：映射地址只存消息字段，失败路径直接释放页 | 缺持久 DMA 凭据和已映射前缀回滚；第二次 map 或未发布发送失败时不能正确撤销第一次映射 |
| CT03 / P1 | root `nss_init.c:1347,1351` 在 `1369` platform unregister 前释放表 | 诊断入口注销不等于异步响应和设备 DMA 退休；仅把 free 后移也没有证明 FW 已停止访问 |
| CT04 / P1 | `nss_core.c:1843-1849,2352` 首次非队列初始化发起配置；返回值未处理 | 不是只由用户手改连接数触发。启动请求、接纳失败、异步成功、对外可见容量没有分开 |
| CT05 / P2 | `nss_hlos_if.h:26,27,35,43,46`：FW 默认1024，宿主 LOW512/MID2048/普通4096 | MID/普通默认可进入异步流程；LOW512 被当前1024粒度校验拒绝，不能宣称已发送成功。粒度应核 FW 合同，不可为通过测试放宽 mask |
| CT06 / P2 | `dma_map_single()` 结果赋给32位消息字段后才检查错误 | 应保留原生 `dma_addr_t` 先验错/验可表达范围；是否在当前 AX6 地址窗口实际触发，未验证 |
| LP / P1 | late-probe 的 common/global、per-core、devm、meminfo 与 FW 发布混合 | 首错、取得权、提交点和兄弟 core 的共享使用未整体闭环；必须按失败前缀核对，不能无条件 disable/put/unmap |
| GR / P2 | GRE LAG singleton 队列与多个排队入口缺完整根层退休责任 | 新增 destroy 不是完整方案；必须处理延迟工作、重排队、回调、自取消与 provider/RX 依赖 |
| GR02 / P1 | `nss_gre_redir_lag_us.c:532` 配置失败的节点查找条件反向 | 已找到节点却提前返回；未找到时仍可能落到初始idx0取消错误槽位。主线程已回读实际函数确认，未做运行复现 |
| GR03 / P1 | GRE `208-242,266-277` 同步发送覆盖消息cb/app_data，worker重试前不重建消息 | 后一次可把内部completion回调当成客户回调；需与迟到ACK和请求身份一起修，不只是重新初始化completion |

CT05 是跨 profile 的源码不一致，不把 LOW 的结论套给当前未知实机 profile。模块参数是 `S_IRUGO` 的 `max_ipv4_conn/max_ipv6_conn`，不是连接数可写 sysctl。MID/普通启动路径仍必须覆盖。

## 3. 执行路线与分批准入

| 顺序 | 工作包 | 可以交付什么 | 不得越过的门 |
| --- | --- | --- | --- |
| G0 | 固定实际树、调用图、每项资源及外部调用者清单 | 可回读的来源、差异、所有权/返回值/执行上下文矩阵 | 输入变化先复核，不从待验输入自动刷新期望 hash |
| A0 | 连接表 wire/FW/DMA 合同 | 查询、发布、响应、退休证据与缺口，标识 CPU 与 FW 两条寿命 | 找不到 FW retirement 不能猜 ACK、超时或新消息号 |
| A1 | 私有分配、原生 DMA 凭据和未发布失败回滚 | 明确受限的本机失败前缀修复、正负控和独审 | 不顺手清理已经发布的表；A1 不能称完整退出修复 |
| A2 | 请求身份、接纳、单所有者与响应状态机 | IPv4/IPv6 一致合同，早到/迟到/重复响应和 root 关闭均有定义 | 不将现有同步 API 套进 NAPI；不引入悬空 app_data |
| A3 | 发布后 FW 退休与 root/跨模块退出 | 仅在停止与最后访问证明齐全时纳入完整清理 | 当前是阻塞门；无证明时不能签收卸载/失败初始化后代码寿命 |
| B | late-probe 分阶段取得、共享资源提交和失败回滚 | 私有前缀先闭合，共享 provider 与两 core 事务单独签收 | 已启动 FW、已提交 DMA 继承 A3；不能以保留内存掩盖 devres 释放 |
| C | GRE checked owner、关入口、排空、最后销毁 | 模块根层和节点级分别取得/释放，失败初始化与正常退出同审 | 保留 worker 所需响应通道；不能持 worker 所需锁同步取消 |
| D | 全组合、历史修复与跨模块独审 | 只在证据支持的范围更新关闭状态 | 不把局部宿主 PASS 推导为目标编译、实机或性能 PASS |

实施顺序是 A0→A1→A2→A3 审定→B→C→D。A3 缺外部证据时，暂停依赖它的释放路径，但仍可推进 B/C 中不依赖 FW 停止的本机所有权工作；不得无限重复同一有界测试冒充推进。

A1 可先隔离实现和审查，但纳入生产候选前必须连同 A2 的本机单所有者/回调合同验证：不能一边新建私有凭据，一边让旧 NACK/root 路径继续释放同一全局表。可以分别评审提交，不允许把尚未接齐的中间提交称为可交付修复。GR02/GR03 随 C 的完整节点/请求合同修正，简单改一个条件不能关闭 C。

## 4. A：连接表修复方法

### 4.1 所有权凭据和状态

每个事务至少保留 family、core/FW epoch、请求代号、请求容量、当前阶段、已接纳引用，以及 CE/CME 各自的 CPU 地址、原生 DMA 地址、device、映射长度、分配 order、direction、mapped/allocated 状态。分配 order/长度创建后不可被下一条 size 响应改写；软件 generation 不等于真实 FW epoch。

区分三种所有权：命令 skb 归 `nss_core_send_cmd/send_buffer`；连接表页归事务；FW 获得访问权后，本机暂时没有单方面释放权。不要在连接层补一次命令 skb 的 unmap/free，造成双重清理。

建议状态合同（名称是设计，不表示代码已实现）：

`EMPTY → SIZE_SUBMITTING → SIZE_PENDING → HOST_PREPARING → CONFIG_SUBMITTING → FW_EXPOSED → ACTIVE`

正交的 `CLOSING` 标志停止新请求；只有本机未发布失败进入 `HOST_ROLLBACK → EMPTY`。`FW_EXPOSED/ACTIVE` 必须经有证据的 `RETIRING → RETIRED` 才能 unmap/free。未知发布结果、未知旧代回应或超时记为 `RETIREMENT_UNPROVEN`，不是自动回到 EMPTY。

`send_buffer` 在返回前更新 FW 可见 ring index，响应可能在发送函数返回前到达。因此在调用 TX 之前安装事务状态和引用，TX 返回与回调共同结算；不能成功返回后才登记 pending，也不能回调释放后发送方继续使用该对象。

还须覆盖嵌套提前完成：SIZE TX尚未返回时，SIZE ACK已分配并发送CFG，甚至CFG ACK已把事务推进ACTIVE。旧SIZE发送栈帧收尾不得把它回写为SIZE_PENDING；两个发送栈帧分别持有并归还引用，不能按一个笼统inflight位覆盖。

锁只保护状态转换、引用和所有权摘取，不在持有该锁时调用可能回调/等待的 TX、同步排空或释放共享provider。drop-lock之后依靠已取得的事务引用保持对象寿命，不依赖重新读取全局裸指针。锁类型必须按实际NAPI/进程/硬中断调用图选择，不随意用全局IRQ-off锁覆盖整段配置；引入timeout/timer/work则同时纳入root取得和退出账本。

每个 family 同时只允许一个活动配置事务。预算检查须区分 requested/reserved/accepted，防止 IPv4/IPv6 同时请求时超额或失败覆盖对方状态。必须保留对外 API 兼容性，先查 `nss_ipv[46]_max_conn_count()` 的全部调用者，再决定何时发布 accepted 值。

接纳门还必须覆盖导出的 `nss_ipv[46]_tx/tx_with_size` 与可能直达通用 `nss_core_send_cmd` 的连接配置命令。仅给当前启动调用点加门不能证明外部调用者无法绕过；固定版本 clients 源码未完整展开审计前，此项标为调用图待闭合。不要不加区分地阻断所有 IPv4/IPv6 数据/统计消息。

### 4.2 私有失败回滚

1. 查询响应必须匹配 family、类型、payload 最小长度、代号、请求容量及合法范围；错误响应不能覆盖已接纳表。
2. 所有大小/order/加法溢出及 wire 可表达范围检查在分配/转换之前。边界来自实际内核和 FW 合同，不从测试预期凭空设限制。
3. CE/CME 先保存在私有凭据。map 用原生 `dma_addr_t` 接收，先 `dma_mapping_error()`，再检查消息32位地址能否表达，最后写 wire 字段。
4. 仅确认尚未发布的失败：按 CME map→CE map→CME pages→CE pages 的逆序撤销实际已取得项，匹配原 device/address/length/direction；不要按新全局 size 重新计算释放 order。
5. 保留首个失败及归属。cleanup 错误单列，不覆盖原错误；异步 TX 接纳成功不能返回为“配置已成功”。
6. direction 保持需要审查的合同项。不能凭“这是连接表”就把 `DMA_TO_DEVICE` 改成 BIDIRECTIONAL，也不能因硬件 cache coherent 而省略映射配对。

`mapped` 必须是明确取得状态，不能用DMA地址非零代替；平台允许时DMA地址0是合法值。payload最小长度检查要位于第一次字段读取之前，包含日志函数而不仅是最终callback：当前IPv4 RX在调用callback前已调用log，CFG日志还会读payload。后续核对transport的实际buffer长度、header.len和相关日志编译配置，避免只在最后回调加检查形成预检盲区。

### 4.3 回调、关闭与退休

- 查询和配置回调不能只依赖全局指针。优先审查现有 opaque `app_data` 的 echo 能力、位宽及代号复用；不改 wire 布局，不猜协议字段。
- 有效回调只改变其所属事务，晚到/重复/乱序响应不得重新发布新表或释放另一代。身份对象必须活到已接纳发送者和实际 RX 回调全部退出；禁止把将被释放的对象裸指针当永久 app_data。
- 身份检查还必须保护间接调用本身：现有IPv4/GRE RX直接调用响应中的`cm.cb`，外层core还有注册回调快照。不能进入可能已失效的`cm.cb`后才靠app_data查表。针对本轮管理消息，先核实并采用存活的分派入口验证token，再调用受寿命保护的回调，或证明从发布至最后可能响应全部代码始终存活；两层分派均纳入join。具体实现仍须核FW echo/位宽/epoch，不重构无关全部NSS消息。
- root 先关闭真正的初始化 producer 和配置入口，再排空已接纳发送者；如果退休需要 ACK，则此时 RX/NAPI/provider 必须仍可用。随后才在合同许可下关闭响应分发并 join 读者。
- 现有 size/config ACK 只说明相应命令结果；NACK、超时、把 callback 置 NULL、`synchronize_rcu()` 或 NAPI disable 均不能单独证明 FW 不再访问表。
- FW 已停止访问和 CPU 回调已排空必须分别有证据。退役凭据还应绑定正确 core/FW epoch，不能把另一个 core 的 reset 当成本 core 的退休。
- “不释放页”仅能避免某个提前 free，不解决模块代码卸载、devm handle/DMA ops 自动释放或 provider 消失。不能作为永久完成方案；`module_exit` 是 void，也不能设计成返回 EBUSY 来阻止卸载。
- `module_init` 失败返回也会丢失模块代码寿命，不能假定此后还有一次 module_exit 替它收尾；模块引用只能按实际调用合同设计，不能作为失败初始化后悬空回调的通用补救。
- 1024 快速返回不是“改回默认并回收旧表”的命令。未核清能力前不自动禁用动态表、不改连接数或以降低功能/性能来冒充修复；如果未来必须选择拒绝启动或降级容量，应另行解释影响并取得用户决定。

### 4.4 连接表质量矩阵

| 测试族 | 正控/失败前缀 | 必须精确击中的负控 |
| --- | --- | --- |
| 默认与配置 | LOW/MID/普通、FW1024快速路径、IPv4单独/双栈、非法负数/极值/粒度/总预算 | 忽略入口失败、带溢出求和、提前发布请求容量 |
| 取得回滚 | CE/CME alloc、map1/map2、合法DMA地址0、地址不可表达、TX未发布失败 | 漏 unmap、错 device/方向/长度/order、释放外来表、双重清理 |
| 异步身份 | ACK早于TX返回、延迟/重复/乱序 size/config 响应、错误 family/type/短payload、代号复用 | 成功返回后才装 pending、旧响应覆盖新事务、裸悬空 app_data |
| 分派代码寿命 | SIZE发送尚未返回但CFG已ACTIVE；未知/旧token；外层已取回调、内层尚未调用 | 旧发送帧回写旧阶段、进入失效函数后才验token、漏一层分派join |
| 关闭交错 | root与回调交错、查询中关闭、准备中关闭、FW已发布后关闭 | 关入口后仍发新请求、漏发送者引用、free早于RX join或FW retirement |
| 跨 family | 一边失败一边成功、并行预留、一个family未编入 | 错误回滚对方预算、共享锁/状态覆盖、初始化顺序依赖 |

宿主替代可以验证软件选择的交错和清理动作，不能制造“FW 已退休”的真值并据此宣称硬件合同通过。负控必须失败于目标断言，不以编译错误、超时或 sanitizer 启动失败充数。

死锁专项的例外判据须预先固定：可观察的等待依赖环/锁序见证加受控watchdog，用于判定指定deadlock mutation；原因不明的整体超时仍是环境或测试失败，不能算有效负控。所有结果记录实际断言、退出原因和执行环境。

最终签收不变量：每个成功alloc/map只有一个归属；每次回滚只消费本次未发布取得；所有对FW可见的地址保持原device/域及backing有效；closing之后无新外部操作获准；每个已接纳操作有可证明的结束；没有旧代回调能改新代状态；模块代码退出前无仍可执行的函数指针。任意一条未证明，都不能把整段事务标为关闭。

## 5. B：late-probe 共享资源回滚方法

每个资源分别记录 `未取得 / 本地私有 / 共享借用 / 已发布 / 已停止 / 已释放`，并区分 get、prepare、enable、mapping、FW publication 和最后持有者退休。Linux devres 管理 handle 不意味着自动撤销所有 enable 或跨设备借用。

执行步骤：

1. 完整枚举 common reset、device node、pdata/QGIC、clock/regulator、FW load、meminfo pending/commit、context publication、IRQ/NAPI、core start、global frequency consumers 的实际取得顺序和错误返回。
2. 私有资源只由本次 probe 的 owner 回滚；context 中借用 pdata 的别名必须在私有释放前撤下并排空读者，不能以两个非空指针认为两份资源。
3. common/global 的一次初始化与逐 core 持有权分离；core0成功、core1失败时不能复位/禁用core0资源。不能把 `get_device()` 当成 provider不会解绑或 devm handle仍有效的证明。
4. meminfo pending 可按其既有凭据撤销；commit/core start 后必须核对 FW 与 DMA 访问，不在新增 goto 中调用无条件 free。失败后重试应有明确可重入状态，不能仅清标志伪造冷启动。
5. 实际 probe 返回失败时，框架会释放 devres，但未必调用驱动 remove；成功 probe 后框架后续失败会走 remove。两类路径分别验证，不能依赖一条 remove 覆盖所有失败。
6. driver registration 返回失败不等于没有成功 probe；框架可能已自动 detach 成功设备。保留首错并防止第二次 unregister/释放；registration成功也不等于每个core probe成功。

矩阵：core0/1首次成功与逐阶段失败、交换探测顺序、兄弟core存活、provider延迟/解绑、get成功enable失败、借用handle、同设备重试、框架自动detach、部分IRQ建立、meminfo未提交/已提交、FW未启动/已启动。必要负控：多put、少disable、错owner、提前撤销共享资源、devm释放后global仍访问、首错丢失、重复remove。

阶段实现细节以本轮 `late-probe/PLAN.md` 及 Linux 实际 driver-core/devres 证据为补充；涉及 FW 发布后的释放仍受 A3 阻塞，不因 B 的软件回滚测试通过而解除。

专项已列出 P00-P14 精确失败前缀。主线程回读时钟实现确认：common有13项时钟取得，本核另有5项；core clock在正常配置中多次get/enable，不能假定仅需配对一次disable。NPU regulator只由core0取得但保存为全局；普通devm_get不自动平衡enable。`regulator_set_voltage()` 当前返回值未处理，须先核电源要求和回滚能力再补错误传播，不只加一个goto。

共享owner的具体实现选择仍需供应关系证明：不能把任意先probe设备的devres句柄直接转成root永久持有，也不能仅加refcount。先验证固定DTS/provider、跨core频率worker和错误返回后框架释放顺序，再在明确owner方案上实现；未核定前不迁移取得API或修改频率/电压策略。

core1失败必须区分私有未发布与跨核已发布：前者可只回滚core1，后者若core0仍可能通过C2C访问，就不能同时声称“core0继续服务”及“core1内存已回收”。现有全组receive quiesce保护不能为局部恢复而简单删除。H414-861全feature注册/注销仍需逐项补审，当前P00-P14表不代表这一整段读者合同已关闭。

## 6. C：GRE 工作队列退出方法

1. 队列取得纳入 checked root 初始化，只有成功取得的根层 owner 能销毁；保留原外部 API 的调用兼容性，查清重复 register 和失败传播。
2. 节点注册、外部查询和 worker 重排队各自采用可审查的准入；先标 root/node closing，关闭新producer，等待已接纳排队调用越过其最后queue点，再同步取消每个 delayed_work。
3. 在取消前核清 worker 对同步 FW 请求、RX回调、节点数据和provider的依赖。保留其完成所需通道；不要先disable全部NAPI再等待需要ACK的worker。
4. 不持 worker 要获取的锁调用 `cancel_delayed_work_sync()`/flush/destroy；不让工作项同步取消自身。回调触发解绑时用已证明寿命的管理上下文延后收尾，不能用未受控的新work绕开旧work退休。
5. 每节点停止并 join 后才能撤其读者数据；所有节点和producer排空后最后owner销毁队列。`flush_workqueue()` 不是取消尚在timer侧的delayed_work，也不能阻止producer再次入队。
6. 正常退出和初始化失败使用同一取得/退休账本。root未成功取得或节点未完整初始化时，不取消未初始化的work，不destroy外来队列。

GRE 专项还必须覆盖：槽位 `CLOSING/RETIRED` 与可复用的 `FREE` 分离；配置成功ACK后才启动轮询；修正反向查找且missing-node不可落入idx0；每次重试使用未污染的消息回调字段；全局completion不得由上一请求迟到ACK唤醒下一请求。保持当前合法客户回调的上下文与语义，先核固定clients调用者再改变公开接口。若绑定core/handler_id缺实际取得证明，不把全局非NULL地址当provider ready。

矩阵：队列OOM、重复初始化、node失败、三条producer逐条与关闭交错、worker运行/等待ACK/超时、重排队、回调中解绑、自取消、锁序、并行节点退出与root退出。负控必须复现关闭后排队、node引用过早释放、destroy前漏timer、同步取消死锁、共享队列重复销毁及ACK通道过早关闭。

具体调用点和上游 workqueue 合同由本轮 `gre-workqueue/PLAN.md` 补充；它不自动证明GRE协议或FW异步响应已退休。

GRE节点dealloc失败时保留其归属和未验证状态，只能作为仍存活模块中的受控状态；不能带着未排空的callback/代码引用结束module_exit。动态接口服务若需要独立ACK，也必须在关闭全局RX之前结清。

### 独审补入的共享动态接口合同

IR-01：实际 `nss_dynamic_interface.c:82-104` 在请求callback之前就修改`assigned_types`并通知；同步等待超时后，栈上`di_data`可能已结束寿命。不能仅在最后callback拒绝旧ACK，或仅把栈对象换成堆对象。身份、payload长度、core/type/ifnum范围及本代所有权必须在任何类型表修改/通知之前验证，请求完成/超时/重复响应只消费一次。改共享服务前至少检查GRE DS、virt_if、rmnet等当前调用者及真实clients，避免修US时改变别的接口行为。

IR-02：host槽位和FW ifnum是两种复用权。GRE的NOTIFY及数据可能没有可核验的请求cookie，却会按当前ifnum注册分发。CPU已进入回调全部退出，不证明旧数据不再从FW/ring到来；普通DEALLOC ACK也未证明全通道drain。必须取得覆盖旧通知/数据的dealloc/drain/epoch合同或经证明的代际过滤，否则ifnum不可复用。不得凭空增加wire字段或关功能；未证实的隔离状态不能算可卸载退休。

IR-03：连接表和GRE统一遵守4.3的间接调用前代码寿命约束，不能用app_data代号检查代替模块寿命。请求cookie、host generation、FW epoch、ifnum退休分别留证，不能混成一个计数器。

新增精确负控：A超时后B尝试使用同ifnum，A旧DEALLOC ACK不得修改B类型/通知/completion；旧NOTIFY/数据在CPU dispatcher之前暂停，CPU join后复用必须被拒或由已证明机制丢弃旧消息；未知token不能先执行客户callback或解引用旧请求地址。这些是后续验证设计，当前没有运行。

## 7. 独立复核与分层验收

| 层级 | 内容 | 本轮/后续边界 |
| --- | --- | --- |
| Q0 方案 | 实际C、原厂pin、内核API、所有权表、执行上下文、失败前缀及跨模块时序 | 本轮执行；不编译 |
| Q1 本地实现 | 后续提取实际修改C、完整调用依赖、故障注入；普通/ASan/UBSan与两编译器；输入/编译器/生成C/结果绑定 | 本轮只制定，不运行；sanitizer环境先验，不能用模型数代表生产函数覆盖 |
| Q2 目标验证 | 实际目标headers/ABI、配置组合、链接和符号/模块依赖；可行时隔离kernel测试lockdep/KASAN/KCSAN/DMA_API_DEBUG | 需后续授权，不用宿主stub替代真实同步机制 |
| Q3 云端/产物 | 冻结新source/build、完整Lint、唯一stock构建；独立验锁、OFF rpcd、manifest、模块ABI、DTB/FIT/UBI、hash和实际payload | 本轮不派发，不套旧固件；构建成功不代替Q4 |
| Q4 实机 | 明确授权后备份/恢复边界、冷启动、失败注入可行性、真实FW退休、长时流量、延时丢包双向吞吐和Wi-Fi | 当前完全禁止；不得以无日志异常视作通过 |

每一工作包必须依次有：缺陷见证→来源/合同→最小完整事务修改→正控→精确负控→作者自审→非作者源码与测试复核→组合回归→证据状态更新。先固定验证合同再写实现，不从实现自动生成所有预期以“自己证明自己”。

独立复核重点：遗漏的外部读者、提前unmap/free、atomic上下文睡眠、锁内等待、自取消、devm/sibling所有权、同请求重用、FW epoch未经证明、历史门禁被弱化。作者不能替独审签署通过；两个分析代理同意也不等于目标运行证明。

历史保护：重新执行时保留030 dummy OOM前缀、031空写no-op、032 pdata引用/id/QGIC/TCM顺序、028 meminfo pending/commit、029 rootcontrols、现有NSS/EDMA与MCS门。新组合树与冻结输入完整比较；目录内脚本不作为输入执行。

真实读者屏障必须覆盖现有 poll-tail 和已复制的 callback 指针，不把 `napi_disable()` 的所有权等待直接写成全部 poll 函数/所有core/所有外部raw读者已经返回。测试要分别观察 gate关闭、最后发送、最后callback、最后poll尾部、FW停止证明、unmap/free、provider退出的时序。

## 8. 性能与优化验收方法

本阶段先消除所有权错误，不更改NSS开关、IRQ/RPS/PBUF/GRO、时钟、电源、Wi-Fi参数或连接数策略。事务控制优先留在初始化/控制面，不向逐包热路径引入全局互斥锁或无界日志。

离线先审查新增锁的范围、是否睡眠、失败路径复杂度和重试上限；实际性能结论等待同硬件/同配置/同端点的授权测试。后续应记录基线与候选的双向吞吐、P50/P95/P99延时、丢包/重传、CPU/softirq、IRQ-off时长、内存/映射增长、控制请求超时及长时稳定性。不能用编译时间、用例数量或没有新增告警证明性能最高。

## 9. 保持开放与停止规则

- FW表访问结束/stop ACK/reset时序与实际epoch未证明：禁止发布后free、卸载安全签收或把遗留页“隔离”宣称完整修复。
- 来源冲突、原始ABI/方向/供应接口未知：先记证据和最小问题，不移动pin、不猜FW行为、不临时关闭功能求通过。
- 发现其他任务修改同一候选：保存差异并协调，不覆盖；同一文件只由一个实现owner写入。
- 失败负控未击中指定断言、测试环境失效、提取遗漏真实依赖：质量门保持失败，不能放宽为PASS。
- UK/SD/PHY/HPPE跨模块provider、017/018真实HW/FW/DMA、I2C ABI、mirror/FRAG、MU-EDCA编号、rpcd/LuCI恢复链、coredump非空非零偏移写和历史第三方告警仍独立开放，本文件没有关闭这些项。
- 本轮不更新云仓版本锁、不推送、不发布、不操作实机；实施和后续编译必须分别按届时用户边界推进。

## 10. 一手依据

- [QSDK NSS driver](https://git.codelinaro.org/clo/qsdk/oss/lklm/nss-drv)：固定pin与本地实际展开C逐路径比较，不把README概述当FW退休协议。
- [qosmio/openwrt-ipq](https://github.com/qosmio/openwrt-ipq)：适配配方与补丁是候选来源，不直接合并；本轮不是所有组件最新版本普查。
- [Linux 6.18.38 DMA API](https://raw.githubusercontent.com/gregkh/linux/v6.18.38/Documentation/core-api/dma-api.rst)：device、原生DMA地址、长度和方向的配对核对依据。
- [Linux 6.18.38 workqueue](https://raw.githubusercontent.com/gregkh/linux/v6.18.38/Documentation/core-api/workqueue.rst)：队列/工作项生命周期核对；取消、入队和锁序仍需结合实际实现。
- [Linux 6.18.38 driver core](https://github.com/gregkh/linux/blob/v6.18.38/drivers/base/dd.c)、[devres](https://github.com/gregkh/linux/blob/v6.18.38/drivers/base/devres.c)、[bus registration](https://github.com/gregkh/linux/blob/v6.18.38/drivers/base/bus.c)：区分probe失败、成功后失败、自动detach与devres释放。

结论：可以先进入 A0/A1 的有界实现准备；A3 完整 FW 退休与由它支配的释放仍需协议/硬件证据。本轮完成的是修复路线与质量门设计，不是全部故障的修复验收。

### 专项交叉核验记录

- [FW/DMA 退休合同与上游范围](/Volumes/FX-MD87/Review-AX6/audits/20261113/nss-root-transaction-plan/fw-contract/PLAN.md)：命令发布边界、各profile、固定CodeLinaro四分支、Linux固定提交以及未找到退休协议的搜索边界。
- [late-probe 共享资源与失败前缀](/Volumes/FX-MD87/Review-AX6/audits/20261113/nss-root-transaction-plan/late-probe/PLAN.md)：P00-P14、13项common/本核时钟与regulator计数、meminfo发布、两core及自动detach，明确全feature/provider待核范围。
- [GRE 队列与请求完整事务](/Volumes/FX-MD87/Review-AX6/audits/20261113/nss-root-transaction-plan/gre-workqueue/PLAN.md)：三条排队入口、节点槽位/重试/自注销、checked root取得、动态接口与RX依赖、独立质量矩阵。
- [非作者独立方案复核](/Volumes/FX-MD87/Review-AX6/audits/20261113/nss-root-transaction-plan/independent-review/REVIEW.md)：有限通过；IR-01/02/03已补入主路线，但其生产实现、完整身份/复用合同及B1/B2实际退休证据仍未完成。

CodeLinaro `NHSS.QSDK.12.5@53a0dc1` 与 `NHSS.QSDK.13.0.r2@e96972f` 的六份连接表相关文件同固定6aa一致；较新的分支名不是已有退休修复的证据。该结论只覆盖所列文件，不是全分支、全部驱动或私有FW实现已审完。Linux6.18.38 peeled commit 为 `e46dc0adfe39724bcf52cea47b8f9c9aed86a394`。主文档的来源链接和专项证据共同使用，不把外网页面读取失败写成成功。
