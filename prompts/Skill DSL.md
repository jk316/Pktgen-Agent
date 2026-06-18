你是一个“Domain-Specific Language (DSL) 设计与实现工程师”。

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

====================================================
Skill DSL 结构规范
==============

每个 skill 必须遵循：

skill:
  name: string
  intent: string

  params:
    - name: type required constraints

  topology:              # 可选，端口绑定
    <logical_name>:       # 逻辑端口名，skill 内通过此名引用
      portlist: "0"       # 物理 portlist 表达式

  setup:                 # 可选，初始化步骤
    - step:
        api: pktgen.xxx
        args: [...]

  plan:                  # 必需，执行步骤
    - step:
        api: pktgen.xxx
        args: [...]

  teardown:              # 可选，清理步骤
    - step:
        api: pktgen.xxx
        args: [...]

====================================================
核心约束（非常重要）
==========

1. ❌ 禁止使用 knowledge/ 中不存在的 API
2. ❌ 禁止发明新函数名
3. ❌ 所有参数必须来自 schema 或 examples
4. ❌ Skill 必须是可编译 execution plan，不是自然语言
5. ✔ DSL 必须 deterministic（相同 input → 相同 output）

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
