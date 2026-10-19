# PCI/MHI shutdown 补充修复与验证边界

## 来源与改动

`999-949-ath11k-cancel-ssr-before-pci-shutdown.patch` 回移 Qualcomm 作者的
Linux 主线提交 `8c79aac429b583301f387374ff37c59be671df87`。仅移植功能部分，
保留本地版权头及 NSS 上下文，不改变驱动源码来源、固件来源或硬件参数。

MHI RDDM 的 unregistering 检查/入队与 PCI shutdown 关闭准入共享
`ab->base_lock`；关闭准入后，在锁外同步取消 reset/dump work，再 power_down。
否则可能在设备关闭和 DMA 释放时仍有恢复工作运行或晚到入队。

mac80211 release 为 r16。本批没有修改数据面、IRQ 亲和性、PBUF、RPS、
offload 或统计轮询参数，也没有补入尚未闭合的 reset timer/冷启动方案。

## 验证等级

- 以主线上游的父/子源码作对照，两个完整函数的功能增量相同。
- 锁定 backports 与 SSDK/ECM 完整补丁链零 fuzz 重放；新旧 mac80211
  准备树仅 pci.c/mhi.c 改变，既有七份 .orig 文件保持原样，不进入编译。
- 专项测试执行完整函数，API 是替身，pthread 调度不等于内核调度。
  覆盖晚到回调、pending/running reset/dump、关闭后拒绝、正常回调不变；
  老码和六种变异须由断言失败拒绝，不能用编译失败追绿。
- GCC、Clang ASan/UBSan 与 Clang TSan 分别记录；受影响的原有 AHB、
  PCIC、provider、CE、QMI、SSDK 与 ECM 门禁继续验证。

最终目标工具链/固件/实机尚未验证，不能据此宣称最高性能或运行无故障。
源码测试的完整命令及限制见 `tests/ath11k-pci-ssr/README.md`。

## 必须保留的区别

上游明确该修复针对 PCI/MHI 正常 SSR，不是 native AHB 故障的证明。
源树另有 debugfs `hw-restart` 入口；当前 stock 配方关闭
`CONFIG_PACKAGE_MAC80211_DEBUGFS`，该条件入口不当作现网吞吐故障根因。
如果其他固件启用 debugfs，AHB/hybrid 的 reset/remove 与入口寿命必须另验。

PCI remove 的 QMI_FAIL 分支、AHB 的 REGISTERED+QMI_FAIL、部分恢复资源、
hybrid wake CE、timer 电源窗口、冷启动错误传播、统计代际与 IRQ-off、
真实双向吞吐仍开放。本补丁不等于这些流程已经完整修复。

主线来源：
https://github.com/torvalds/linux/commit/8c79aac429b583301f387374ff37c59be671df87
