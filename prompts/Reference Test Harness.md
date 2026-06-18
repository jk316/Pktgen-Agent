你是一个“Reference Database 验证与执行测试系统构建器”。

目标：
基于已有 pktgen_reference_database，构建一个自动化测试框架 pktgen_test_harness，用于验证：

1. Reference Database 的正确性
2. Lua API 的真实性
3. Skill 生成脚本的可执行性

========================
输入
==

你已经拥有：

* pktgen_reference_database.yaml
  （包含 CLI commands / Lua API / 参数定义 / enum / 示例）

========================
输出结构
====

生成目录：

pktgen_test_harness/
├── validator/
│   ├── api_checker.py
│   ├── schema_checker.py
│   ├── coverage_checker.py
│
├── lua_tests/
│   ├── test_basic_api.lua
│   ├── test_seqTable.lua
│   ├── test_set.lua
│   ├── test_pktgen_state.lua
│
├── generated_skills_tests/
│   ├── test_udp_flood.lua
│   ├── test_range_mode.lua
│
├── reports/
│   ├── api_validity_report.yaml
│   ├── missing_api_report.yaml
│   ├── schema_violation_report.yaml
│
└── runner.py

========================
核心任务 1：API验证
============

对 Reference Database 中每个 API：

必须生成测试：

* 是否存在（existence test）
* 是否可调用（runtime probe）
* 是否参数匹配（schema validation）

示例：

pktgen.seqTable(port, table)

生成测试：

lua:
pktgen.seqTable(0, "all", {
eth_dst_addr="0011:4455:6677",
ip_proto="udp"
})

检查：

* 是否报错 nil function
* 是否报参数错误

========================
核心任务 2：Schema验证
===============

对每个参数：

验证：

* type
* range
* enum
* default value

生成非法测试：

例如：

pktSize = -1
pktSize = 999999
ipProto = "abc"

必须触发错误或被拒绝

========================
核心任务 3：Coverage验证
=================

检查：

Reference Database API集合
VS
Lua runtime实际可调用API

输出：

missing_api.yaml

========================
核心任务 4：Skill验证
==============

对每一个 skill（例如 udp_flood）：

必须生成：

* minimal version script
* stress version script
* invalid input script

并验证：

* luac compile success
* pktgen load success
* pktgen run no crash

========================
核心任务 5：运行方式
===========

runner.py 必须支持：

1. static mode
   → 只检查 reference DB

2. lua mode
   → 只运行 lua_tests

3. full mode
   → 启动 pktgen + 执行所有测试

========================
输出要求
====

所有结果必须结构化：

api_validity_report.yaml

格式：

api:
pktgen.seqTable:
exists: true
schema_ok: true
runtime_ok: true

pktgen.xxx:
exists: false
reason: not found in runtime

========================
硬性规则
====

* 不允许假设 API 存在
* 不允许生成未在 reference DB 出现的 API
* 所有 runtime 测试必须可复现
* 所有失败必须记录 evidence
