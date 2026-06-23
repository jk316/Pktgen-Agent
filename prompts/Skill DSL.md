你是一个"Domain-Specific Language (DSL) 设计与实现工程师"。

目标：
基于 knowledge/ 目录下的 Pktgen 知识库，设计并实现一个 Skill DSL，用于描述如何使用 Pktgen Lua API 构建流量生成、控制与观测任务。

====================================================
输入
==

knowledge/ 目录（9 个 YAML 文件）：

  knowledge/docs_index.yaml      — 全部14个页面的索引与交叉引用
  knowledge/commands.yaml        — CLI 命令、参数、取值范围、别名
  knowledge/lua_api.yaml         — Lua API 函数签名、seqTable 键值、range.* 子函数
  knowledge/packet_fields.yaml   — 数据包字段定义（Ethernet/IP/Transport/VLAN/...）
  knowledge/range_mode.yaml      — Range 模式 SMMI 参数（start/min/max/inc）
  knowledge/sequence_mode.yaml   — Sequence 模式（seq/seqTable，最多16条/端口）
  knowledge/pcap.yaml            — PCAP 发送/捕获命令
  knowledge/startup.yaml         — EAL 选项、Pktgen 选项、-m 映射 BNF、run.py 配置
  knowledge/examples.yaml        — 所有官方代码示例（逐字保留）

====================================================
目标
==

设计一个 Skill DSL，用于：

1. 表达 pktgen 任务（intent）
2. 描述 API 调用计划（execution plan）
3. 强制 API 合法性（grounded in reference DB）
4. 可用于后续 Lua code generation

====================================================
输出 1：DSL Schema Definition
==========================

定义 Skill DSL 的 JSON/YAML schema：

必须包含：

* intent（任务类型）
* params（输入参数）
* topology（端口绑定，可选）：逻辑端口名 → portlist 映射，skill 内通过逻辑名引用
* setup（初始化步骤，可选）：如 screen off、require、ARP 配置等
* plan（执行步骤）
* teardown（清理步骤，可选）：如 stop、reset、screen on 等
* constraints（参数约束）

====================================================
输出 2：Skill DSL Library
======================

生成至少以下 skills：

1. udp_flood
2. tcp_flood
3. pcap_replay
4. packet_sequence_generation
5. range_based_scan
6. stats_monitoring
7. safe_stop_and_reset

每个 skill 必须：

* 只使用 knowledge/ 中存在的 API
* 包含 topology（端口绑定）
* 包含 setup / plan / teardown 完整生命周期
* 包含参数 schema
* 可以直接编译成 Lua
* **满足对应 intent 的功能完整性要求（见下方）**

====================================================
Intent 功能完整性要求（CRITICAL）
============================

每个 intent 类型有不同的参数完整性要求。生成 skill 时必须覆盖所有对应维度：

### traffic_generation（流量生成 — UDP flood, TCP flood, ICMP flood 等）

IP 层流量生成 skill 必须包含以下参数维度：

**L2 寻址（至少一个）：**
- dst_mac：目的 MAC 地址（通常必需，除非使用 ARP 自动解析）
- src_mac：源 MAC 地址（可选，有默认值）

**L3 寻址（至少一个）：**
- dst_ip：目的 IP 地址（必需 — 否则包发到哪里？）
- src_ip：源 IP 地址（可选，有默认值）

**L4 参数（按协议）：**
- UDP/TCP：sport, dport（源/目的端口）
- ICMP：ttl（无端口概念）
- ARP：arp_type（L2 协议，不需要 IP 参数）

**流量控制：**
- rate：发送速率
- count：包数量（0 = 持续发送）
- pktSize：包大小
- burst：突发大小

> 反例：一个 udp_flood 有 sport/dport 但没有 dst_ip/dst_mac → 不通过，因为用户无法指定包发给谁。

### traffic_scanning（范围扫描）

必须包含：
- scan_field：要变化的字段（dst_ip, src_ip, dst_port, src_port, dst_mac, src_mac, vlan_id, pkt_size）
- start/min/max/inc：范围的四元组（SMMI）

### monitoring（监控/观测）

必须包含：
- 监控对象（端口、统计类型）
- 轮询间隔
- 迭代次数或持续条件

不包含流量生成步骤（monitoring 是只读操作）。

### control（控制操作 — stop, reset 等）

必须：
- 安全：先 stop 再 reset，确保流量已停
- 幂等：多次调用结果一致
- 可选步骤用 condition 控制（如 save_config）

### packet_crafting（包构造 — sequence 等）

必须包含完整的包字段定义（所有 seqTable 必要键值）。

====================================================
Skill DSL 结构规范
==============

每个 skill 必须遵循：

skill:
  name: string
  intent: string              # traffic_generation | packet_crafting | traffic_scanning | monitoring | control

  params:                     # 必须覆盖对应 intent 的所有维度（见上方功能完整性要求）
    - name: rate
      type: float
      description: "..."
      required: true
      constraints: { min: 0, max: 100 }

  topology:                   # 可选，端口绑定
    <logical_name>:           # 逻辑端口名，skill 内通过此名引用
      portlist: "0"           # 物理 portlist 表达式

  setup:                      # 初始化步骤。典型内容：
                              #   1. pktgen.screen("off") — 禁用屏幕更新提高性能
                              #   2. pktgen.set_type — 设置包类型（ipv4/ipv6/vlan/arp）
                              #   3. pktgen.set_proto — 设置协议（udp/tcp/icmp）
                              #   4. pktgen.set_ipaddr — 设置源/目的 IP 地址
                              #   5. pktgen.set_mac — 设置源/目的 MAC 地址
                              #   6. pktgen.icmp_echo / pktgen.send_arp — 协议特定初始化
    - step:
        api: pktgen.xxx
        args: [...]

  plan:                       # 必需，执行步骤。至少 1 个 step
    - step:
        api: pktgen.xxx
        args: [...]

  teardown:                   # 清理步骤。典型内容：
                              #   1. pktgen.stop — 停止流量
                              #   2. pktgen.reset / pktgen.clear — 重置/清理配置
                              #   3. pktgen.screen("on") — 恢复屏幕更新
    - step:
        api: pktgen.xxx
        args: [...]

====================================================
完整示例：udp_flood（traffic_generation）
================================

以下是一个功能完整的 udp_flood skill 示例，作为 traffic_generation 类型 skill 的参考模板：

skill:
  name: "udp_flood"
  intent: "traffic_generation"
  description: "Configure ports and send a UDP packet flood to a specified destination."

  params:
    # ── 必需参数 ──
    - name: "rate"
      type: "float"
      description: "Packet rate in percentage (0-100)"
      required: true
      constraints: { min: 0, max: 100 }

    # ── L3 寻址 ──
    - name: "dst_ip"
      type: "ip_address"
      description: "Destination IP address"
      required: false
      default: '"10.10.10.2"'

    - name: "src_ip"
      type: "string"
      description: "Source IP address (CIDR format, e.g. 192.168.1.1/24)"
      required: false
      default: '"192.168.1.1/24"'

    # ── L2 寻址 ──
    - name: "dst_mac"
      type: "string"
      description: "Destination MAC address (format: XX:XX:XX:XX:XX:XX)"
      required: false
      default: '"00:00:00:00:00:01"'

    - name: "src_mac"
      type: "string"
      description: "Source MAC address (format: XX:XX:XX:XX:XX:XX)"
      required: false
      default: '"00:00:00:00:00:02"'

    # ── L4 端口 ──
    - name: "sport"
      type: "integer"
      description: "UDP source port"
      required: false
      default: 1234

    - name: "dport"
      type: "integer"
      description: "UDP destination port"
      required: false
      default: 5678

    # ── 流量控制 ──
    - name: "pktSize"
      type: "integer"
      description: "Packet size in bytes"
      required: false
      default: 256
      constraints: { min: 64, max: 1518 }

    - name: "count"
      type: "integer"
      description: "Number of packets to transmit (0 = forever)"
      required: false
      default: 0

    - name: "burst"
      type: "integer"
      description: "Tx burst size"
      required: false
      default: 128

  topology:
    tx_port:
      portlist: "0"
      description: "Port used for TX"

  setup:
    - comment: "Disable screen updates for performance"
      api: "pktgen.screen"
      args: ['"off"']

    - comment: "Set packet type to IPv4"
      api: "pktgen.set_type"
      args: ["$topology.tx_port", '"ipv4"']

    - comment: "Set packet protocol to UDP"
      api: "pktgen.set_proto"
      args: ["$topology.tx_port", '"udp"']

    - comment: "Set destination IP address"
      api: "pktgen.set_ipaddr"
      args: ["$topology.tx_port", '"dst"', "$params.dst_ip"]

    - comment: "Set source IP address"
      api: "pktgen.set_ipaddr"
      args: ["$topology.tx_port", '"src"', "$params.src_ip"]

    - comment: "Set destination MAC address"
      api: "pktgen.set_mac"
      args: ["$topology.tx_port", '"dst"', "$params.dst_mac"]

    - comment: "Set source MAC address"
      api: "pktgen.set_mac"
      args: ["$topology.tx_port", '"src"', "$params.src_mac"]

  plan:
    - comment: "Configure packet size"
      api: "pktgen.set"
      args: ["$topology.tx_port", '"size"', "$params.pktSize"]

    - comment: "Configure burst size"
      api: "pktgen.set"
      args: ["$topology.tx_port", '"burst"', "$params.burst"]

    - comment: "Set source port"
      api: "pktgen.set"
      args: ["$topology.tx_port", '"sport"', "$params.sport"]

    - comment: "Set destination port"
      api: "pktgen.set"
      args: ["$topology.tx_port", '"dport"', "$params.dport"]

    - comment: "Set packet rate"
      api: "pktgen.set"
      args: ["$topology.tx_port", '"rate"', "$params.rate"]

    - comment: "Set packet count (0 = transmit forever)"
      api: "pktgen.set"
      args: ["$topology.tx_port", '"count"', "$params.count"]

    - comment: "Start transmitting"
      api: "pktgen.start"
      args: ["$topology.tx_port"]

  teardown:
    - comment: "Stop all traffic"
      api: "pktgen.stop"
      args: ["$topology.tx_port"]

    - comment: "Re-enable screen updates"
      api: "pktgen.screen"
      args: ['"on"']

  constraints: {}

====================================================
核心约束（非常重要）
==========

1. ❌ 禁止使用 knowledge/ 中不存在的 API
2. ❌ 禁止发明新函数名
3. ❌ 所有参数必须来自 schema 或 examples
4. ❌ Skill 必须是可编译 execution plan，不是自然语言
5. ✔ DSL 必须 deterministic（相同 input → 相同 output）
6. ✔ **必须满足对应 intent 的功能完整性要求** — 用户调用 skill 后应得到有意义的结果。同类 skill（如 udp_flood / tcp_flood）的参数集应保持一致性。

====================================================
输出校验（生成 skills 后必须自查）
=========================

在输出每个 skill 之前，逐项确认：

- [ ] 所有 API 在 knowledge/lua_api.yaml 或 schema.yaml valid_apis 中存在
- [ ] 所有参数类型在 schema.yaml 的 params.type enum 中定义
- [ ] IP 层流量生成 skill：包含 dst_ip 和 dst_mac 参数（或明确说明使用 ARP 解析）
- [ ] L4 协议 skill：包含对应的协议参数（UDP/TCP → sport/dport, ICMP → ttl, ARP → arp_type）
- [ ] setup 包含 screen("off") 和包类型/协议配置
- [ ] teardown 包含 stop 和 screen("on")，必要时包含 reset/clear
- [ ] control 类 skill 安全且幂等
- [ ] 同类 skill 参数一致（udp_flood 和 tcp_flood 的寻址参数应相同）

====================================================
输出 3：DSL → Lua Mapping Rules
============================

生成规则：

* DSL step → Lua function mapping
* 参数绑定规则
* sequence / table 结构转换规则

例如：

DSL:
api: pktgen.set
args: ["all", "rate", 100]

→

Lua:
pktgen.set("all", "rate", 100)

====================================================
输出格式
====

输出到 dsl/ 目录：

  dsl/schema.yaml       — DSL Schema Definition
  dsl/skills/            — Skill DSL Library（每个 skill 一个文件）
  dsl/mapping.yaml       — DSL → Lua Mapping Rules

只输出 YAML + mapping rules，不要解释。
