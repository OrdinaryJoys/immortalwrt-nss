# AX6 NSS 连接表本机事务 (DRV29)

本批沿用 Astra 路线，只实施连接表 A1/A2。本机事务候选供隔离验证，
不能作为可刷写发布：设备首次运行、固件回传与 DMA 退休尚未签收。
此前 030/031/032、厂商 pin、Wi-Fi/NSS 调参和硬件布局保持原样。

## 实现与边界

- IPv4/IPv6 共用内部事务；单次接纳记录 family、core、token、请求量和
  预留量。用已接受的容量服务原 ECM API。LOW 仍执行既有粒度约束；
  MID/full 在确认动态 ACK 前报告不超过固件默认的保守容量。
- CE/CME 在任何分配前检查双长度。持久 DMA 凭据记录 device、原生
  DMA 地址、长度、方向、阶数和 mapped 状态；地址 0 有效。确认发送未
  发布时按实际取得前缀逆序还原，也检查控制 skb 映射未截断后再入环。
- 复用原消息类型、common header、3 个 payload 字和字节序，不增加
  私有 opcode。接收入口先限制可读范围；两个表管理 opcode 直接进
  宿主静态分派，不调用返回的 `cm.cb`。错误 core、token、状态或字段
  长度不能推进。提前 CFG 响应只暂存，成功入环后才结算；入环失败
  不因有响应而失去释放权。导出的通用 TX 不可绕过表事务。
- 先关接纳并等待已接纳发送/准备操作退出。现有 RX 排空未撤销，但
  RX 结束不证明 FW 已停止 DMA。发布后的 NACK、丢回复或退出不回收。
  这只是避免提前 free，不意味着 DMA provider、设备或模块可安全卸载。

## Astra 复核门

1. 锁定 12.5-210 Hawkeye image 的 SIZE/CFG opaque `app_data` 回传，
   含错误分支、`cb == NULL`、上下文和回复长度。ECM 其他 opcode 使用
   scalar cookie 是先例，不能替代该契约。未回传时不得退回无身份 RX。
2. 明确 FW 使用 CE/CME 的方向、最后访问和 DMA 域的寿命。现有 remove
   不能用保留页替代设备级 retirement，禁止把该候选认作卸载安全。
3. 通用 N2H descriptor 在进入状态解析器前的 DMA unmap 仍用固件提供
   的 offset/len，且 H2N 空缓冲返回没有独立全套原始映射记录；
   本批的 RX 读取上限和命令 DMA 检查不修复该环级账本。应另做跨 TX/RX
   环的生命周期设计，避免只修改一个 unmap 或掩盖历史负控。
4. late-probe 共享 provider、GRE 工作队列及接口复用仍按原路线开放；
   不把宿主正/负控解释为目标编译或吞吐证明。

证据目录：`/Volumes/FX-MD87/Review-AX6/audits/20261113/nss-conn-implementation.PW422t`。请以对应源码和构建 SHA 的实际日志、产物验收和
设备许可状态为准；本说明不表示已经启动、编译成功或批准刷机。
