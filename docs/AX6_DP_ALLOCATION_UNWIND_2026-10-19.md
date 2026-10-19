# DP 初始化失败回滚与调用方合同

## 根因与修正

当前 `ath11k_core_qmi_firmware_ready()` 在 `ath11k_dp_alloc()` 失败时只转到
firmware stop，不调用完整 `dp_free()`。因此 `dp_alloc()` 必须自行回滚
本次已经成功取得的资源，不能将部分状态留给调用方猜测清理。

950–951/r17联合修复父子两层分配合同：

1. link-descriptor setup 失败时，子函数虽会清理自己的部分 bank/scatter，
   但父函数此前分配的 WBM idle ring 仍在。现在经过已有的 guarded link
   cleanup，释放父层 ring；已清空的子对象不会重复释放。
2. 第N个 TX status 分配失败时，原来不释放前面成功的槽位。现在只逆序
   释放本轮 `[0, N)`，同时置NULL，再清公共ring及link资源。
3. 下钻确认SRNG在DMA分配后遇到无效DP类型/HAL setup错误直接返回，
   也会留下本层内存。951在这两条出口同步释放，并记录本次分配的缓存
   属性，避免复用对象残留cached=1导致coherent/noncoherent释放API不配对。

不能以全量 `dp_free()` 替代：后面的 TX lock/pool 尚未完成初始化。
成功路径、环数量/大小、NSS选择、FW来源、IRQ及offload参数不变。

## 验证与限制

完整包按锁定来源零fuzz重放；与r16相比编译源只改dp.c。GCC与Clang
ASan/UBSan覆盖默认/512M布局，执行完整分配函数与四个真实清理helper，
setup/DMA/allocator等是替身。每布局42场景、1224断言，新代码0失败；
旧代码54失败，四变异全部由断言拒绝，成功分配模型签名不变。

SRNG另执行完整setup/cleanup、实际枚举和参数布局：840个组合场景、
5072断言，GCC/ASan下新码0失败，旧码680失败，五变异被拒。HAL失败
限定为准确HAL函数在发布initialized前拒绝ring id，不能扩为全部硬件
错误可恢复。父层setup替身的无残留合同由该下层实验补证，但仍非真实DMA。

测试提取器新增跨行返回类型支持，保持原函数字节，并增加歧义/原型/
CRLF正反检查；原回归需要在新提取器和同一准备树下重新运行。

官方Linux精确提交c03c1a14507dfaf8b856c2608f9ac216021fc222的dp.c仍有
上述返回/回滚形态。本补丁是本地经验证候选，`Upstream-Status: Pending`，
不是冒称已合入的官方backport，也不升级来源train。

本次不关闭：CE ring部分初始化、core_start的MAC/REO阶段、REGISTERED
恢复失败、冷启动超时/重启/晚到事件、NSS异步持有者及完整退出。这些
需要真实资源账本和各自调用方验证，不得因为本函数回滚通过就认定已修。

没有目标编译或实机测试，不证明当前吞吐根因、最高性能或整机无故障。
命令及API模型边界见 `tests/ath11k-dp-allocation/README.md`。
