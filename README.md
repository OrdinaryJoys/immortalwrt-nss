# OrdinaryJoys ImmortalWrt NSS for Redmi AX6

这是 [AX6-OpenWRT 构建仓](https://github.com/OrdinaryJoys/AX6-OpenWRT) 的源码侧。这里包含 OpenWrt/ImmortalWrt 基础、Qualcomm 传统 NSS/ECM、DP/EDMA v1、SSDK 和 ath11k 适配。构建仓用明确提交锁定本树，不以默认分支 HEAD 作为构建证据。

## 上游修复隔离候选（2026-11-17）

基于已离线验收的 `828c21b4`，保持 Linux 6.18.38、NSS DRV29、Wi-Fi/交换机驱动、固件、板级配置和 rpcd OFF。只移植已审查的用户态/宿主解析修复：

- `package/network/services/dnsmasq`：2.93 安全与 SIGHUP/大量 hosts 修正；不改 init、代理范围或订阅。
- `package/network/services/odhcpd`：同一 pin 上成组覆盖 DHCPv6 IA、AUTH、relay、错误返回与客户端租约主机名转义。
- `package/network/services/hostapd`：BSS 对象不可用时拒绝重排；不动现有 ath11k 或校准适配。
- `package/network/config/netifd`：非法/空 VID 拒绝、创建失败回滚、引用中的重命名失败和 external 成员回收；不改 IRQ/RPS 默认或网络拓扑。
- `package/libs/libubox`：blobmsg JSON 对非扩展对象成员做边界检查并跳过其输出；不换 SONAME 或源码 pin。

这些源码集成不包含 054–073，也不是固件构建或实机验证的完成证明。独立解绑、LIVE、035、已发布 DMA/FW 退休和共享钟继续 HOLD。

## 验证和维护

- 保留包原始 pin；patch 目录按数字排序。源代码同名库、包修订和 ABI 是不同约束。
- 在原始源码归档上严格回放包内 patch，拒绝 fuzz。对下面的宿主函数验证要传已回放的 netifd、odhcpd 根目录：

  ```sh
  python3 -B tests/test-ax6-upstream-leaves.py --source . \
    --prepared-netifd /path/to/prepared/netifd --prepared-odhcpd /path/to/prepared/odhcpd
  ```

  该测试编译实际 VLAN 准入/回滚、BSS 重排和租约主机名转义函数；不是运行整套守护进程或无线驱动。libubox 的上游回归位于其准备后源码的 `tests/test-blobmsg-format-json.c`。

- 云端以构建仓 Lint、stock 构建、同 run 独立验包为准。检查 manifest、模块和实际镜像内容，不用旧 828c21b 产物代替候选。
- VIKINGYFY 旧 main、默认 owrt、qosmio、OpenWrt/ImmortalWrt 和 CodeLinaro 是不同适配来源。不要整体替换传统 NSS/pins，不把其他硬件的 DT/PPE 变更用于 AX6。

历史事务见 [2026-11-13 NSS 审查](docs/AX6_NSS_ROOT_TRANSACTION_2026-11-13.md) 和 [此前云端隔离验证](docs/AX6_ROOT_HOST_CLOUD_VALIDATION_2026-11-07.md)。许可见 [COPYING](COPYING) 和 [LICENSES](LICENSES/)。
