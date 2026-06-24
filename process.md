# Pktgen Agent 端到端流程

从用户输入一句话到 Pktgen 机器开始发包，经过 **6 个阶段**。

---

## 全景图

```
你输入一句话
    │
    ▼
┌─────────────────────────────────────────────────────┐
│ 阶段① main()              agent.py:162              │
│   解析参数 → 加载配置 → 创建工具 → 创建大脑            │
├─────────────────────────────────────────────────────┤
│ 阶段② run_interactive()    agent.py:122              │
│   REPL 循环：读用户输入 → 喂给 AI Agent               │
├─────────────────────────────────────────────────────┤
│ 阶段③ AI 决策              LangChain 内部             │
│   大模型理解意图 → 选择工具 → 填参数 → 发起 tool call   │
├─────────────────────────────────────────────────────┤
│ 阶段④ create_skill_tool    tools/execute.py:234      │
│   接收到 tool call → 调用 SkillCompiler               │
├─────────────────────────────────────────────────────┤
│ 阶段⑤ SkillCompiler.compile  compiler/compile.py:401 │
│   Phase1: 校验参数 → Phase2: 发射 Lua 代码             │
├─────────────────────────────────────────────────────┤
│ 阶段⑥ 执行（dry-run 或 live）                         │
│   dry-run: 保存 Lua 到磁盘，返回 JSON                  │
│   live:    通过 TCP 发 Lua → Pktgen 执行 → 返回结果    │
└─────────────────────────────────────────────────────┘
    │
    ▼
结果返回给你："成功了，正在以 80% 速率发 UDP 包"
```

---

## 四层架构

| 层级 | 类比 | 实际是什么 |
|------|------|-----------|
| AI 大脑 | 服务员（听懂你的需求） | LangChain + DeepSeek 大模型 |
| 技能工具箱 | 菜谱（9 种做菜方法） | 9 个 YAML 技能文件 |
| 编译器 | 厨师（把菜谱变成菜） | 把 YAML + 你的参数 → Lua 代码 |
| 网络客户端 | 传菜员（把菜端过去） | TCP 连接 Pktgen，发送代码 |

---

## 阶段① 启动 — `main()` 干了什么

代码位置：`pktgen_agent/agent.py:162`

启动时按顺序做的事：

1. 解析命令行参数（`--live` / `--host` / `--port` / `--model` / `--verbose`）
2. `setup_logging()` — 配置日志
3. `check_dependencies()` — 检查 pyyaml, langchain, pydantic 是否安装
4. `load_topology_config()` — 读 `topology.yaml`，拿到 Pktgen 的 IP 和端口
5. `get_tool_catalog()` — 扫描 `dsl/skills/*.yaml`，打印可用技能列表
6. **`create_tools()`** — 核心：为每个 YAML 创建一个 LangChain 工具
7. `get_model()` — 创建 DeepSeek 大模型连接 (`api.deepseek.com`)
8. `create_pktgen_agent()` — 把大脑 + 工具 + 系统提示词组装成一个 Agent
9. `run_interactive()` — 进入交互循环

### 第 6 步 `create_tools()` 详解

代码位置：`pktgen_agent/tools/execute.py:272`

```python
# create_all_tools() — 扫描 dsl/skills/ 目录
for skill_file in sorted(_SKILLS_DIR.glob("*.yaml")):  # 遍历所有 .yaml 文件
    skill_name = skill_file.stem                          # 比如 "udp_flood"
    tool = create_skill_tool(skill_name, host, port, dry_run)
    tools.append(tool)
```

`create_skill_tool()` 做三件事（`tools/execute.py:198`）：

| 步骤 | 代码位置 | 干了什么 |
|------|---------|---------|
| a. 读 YAML | `_load_skill_meta()` :156 | 解析 `udp_flood.yaml`，提取参数定义（rate, dst_ip, pktSize...） |
| b. 造 Pydantic 模型 | `_build_pydantic_model()` :166 | 动态创建一个类，把 YAML 参数变成带类型校验的字段 |
| c. 包成 LangChain @tool | :250 | 用 `@lc_tool(args_schema=...)` 装饰器包起来，让大模型能"看到"并"调用" |

最终 9 个 YAML 变成 9 个可调用的工具：`udp_flood()`, `tcp_flood()`, `icmp_flood()`, `arp_flood()`, `range_based_scan()`, `packet_sequence_generation()`, `pcap_replay()`, `stats_monitoring()`, `safe_stop_and_reset()`.

---

## 阶段② 交互循环 — 等你输入

代码位置：`pktgen_agent/agent.py:122`

```python
# run_interactive() — REPL 循环
while True:
    cmd = _safe_input("> ")          # 等你敲字
    result = agent.invoke({           # 把输入喂给 AI Agent
        "messages": [{"role": "user", "content": cmd}]
    })
    print(last_msg.content)           # 打印 AI 的回复
```

你输入 `"用 80% 速率发 UDP 洪水到 10.10.10.2"` → 变成一条消息 → 发给 Agent。

---

## 阶段③ AI 大脑决策 — LangChain 内部

这是 LangChain/LangGraph 的处理过程。Agent 内部发生的事：

```
1. LangGraph 收到 {"messages": [{"role": "user", "content": "用80%速率发UDP..."}]}
2. 把 system_prompt + 历史消息 + 工具列表(带 JSON Schema) 打包发给 DeepSeek API
3. DeepSeek 理解意图后返回一个 tool_call：
   {
     "name": "udp_flood",
     "args": {"rate": 80, "dst_ip": "10.10.10.2"}
   }
4. LangGraph 执行这个 tool_call → 进入阶段④
5. 拿到工具返回的 JSON 结果 → 再发给 DeepSeek 做一次总结
6. DeepSeek 生成自然语言回复："UDP洪水已启动，速率80%，目标10.10.10.2..."
```

**关键点**：AI 不直接写 Lua，它只是选择了正确的工具 + 填了正确的参数。

---

## 阶段④ 工具执行 — 从 tool call 到编译器

当 LangGraph 调用 `udp_flood(rate=80, dst_ip="10.10.10.2")` 时，实际触发：

代码位置：`pktgen_agent/tools/execute.py:234`

```python
# create_skill_tool 内部的 _execute()
def _execute(**kwargs):     # kwargs = {"rate": 80, "dst_ip": "10.10.10.2"}
    if dry_run:
        return execute_skill_dry_run(skill_name, kwargs)   # 只编译不执行
    return execute_skill_live(skill_name, kwargs, host, port)  # 编译 + TCP 发送
```

### dry-run 路径（`execute.py:86`）

```python
def execute_skill_dry_run(skill_name, params):
    lua_code = compiler.compile(skill_name, params)   # → 阶段⑤
    _save_lua_script(skill_name, lua_code, "dry_run")  # 保存到 lua_scripts/ 目录
    return {"success": True, "skill": skill_name, "lua_code": lua_code, ...}
```

### live 路径（`execute.py:102`）

```python
def execute_skill_live(skill_name, params, host, port):
    lua_code = compiler.compile(skill_name, params)   # → 阶段⑤
    _save_lua_script(skill_name, lua_code, "live")
    response = execute_lua(lua_code, host, port)       # → 阶段⑥
    return {"success": True, "response": response, ...}
```

---

## 阶段⑤ 编译器 — YAML → Lua（最核心的一步）

代码位置：`pktgen_agent/compiler/compile.py:401`

整个项目最复杂的函数，分两阶段：

### Phase 1：参数校验（:423-486）

```python
for p in skill_params:          # 遍历 YAML 里定义的每个参数
    # 1. 检查必填参数有没有
    if p.required and pname not in user_params:
        raise CompileError("缺少必填参数")

    # 2. 类型检查
    if ptype == "float" and not isinstance(val, (int, float)):
        raise CompileError("参数类型不对")

    # 3. 范围检查
    if "min" in constraints and val < constraints["min"]:
        raise CompileError("参数值太小")
    if "max" in constraints and val > constraints["max"]:
        raise CompileError("参数值太大")

    # 4. 枚举检查
    if valid_enum and val not in valid_enum:
        raise CompileError("参数值不在允许范围内")
```

例如你写 `rate=150`，编译器直接报错：`"Parameter 'rate'=150 above maximum 100"`，根本不会进入下一步。

### Phase 2：发射 Lua 代码（:488-525）

按 **setup → plan → teardown** 三阶段逐行翻译：

```python
# 每个 step 都走 compile_step() (:203)
def compile_step(step, user_params, skill):
    api = step["api"]                        # 如 "pktgen.set"
    args = step["args"]                      # 如 ["$topology.tx_port", '"rate"', "$params.rate"]

    # 替换 $topology.tx_port → "0"    (resolve_topology)
    # 替换 $params.rate → 80           (resolve_params)
    # 替换 $params.dst_ip → "10.10.10.2"

    # 校验 API 在白名单里 (validate_api)
    # 校验 set key 合法 (validate_set_key)

    # 发射 Lua 行
    return [f'{api}({", ".join(resolved_args)});']
```

**翻译过程示意**：

```
YAML 里的这行：
  api: "pktgen.set"
  args: ["$topology.tx_port", '"rate"', "$params.rate"]

        ↓ resolve_topology:  $topology.tx_port → "0"
        ↓ resolve_params:    $params.rate → 80

生成 Lua：
  pktgen.set("0", "rate", 80);
```

### 最终生成的完整 Lua 脚本示例

```lua
package.path = package.path ..";?.lua;test/?.lua;app/?.lua;"

require "Pktgen"

-- [setup]
pktgen.screen("off");
pktgen.set_type("0", "ipv4");
pktgen.set_proto("0", "udp");
pktgen.set_ipaddr("0", "dst", "10.10.10.2");
pktgen.set_ipaddr("0", "src", "192.168.1.1/24");
pktgen.set_mac("0", "dst", "00:00:00:00:00:01");
pktgen.set_mac("0", "src", "00:00:00:00:00:02");

-- [plan]
pktgen.set("0", "size", 256);
pktgen.set("0", "burst", 128);
pktgen.set("0", "sport", 1234);
pktgen.set("0", "dport", 5678);
pktgen.set("0", "rate", 80);
pktgen.set("0", "count", 0);
pktgen.start("0");

-- [teardown]
pktgen.stop("0");
pktgen.screen("on");
```

---

## 阶段⑥ 执行 — TCP 发送到 Pktgen

**只有 live 模式走这一步。** dry-run 到此为止，只把 Lua 存到 `lua_scripts/` 目录。

代码位置：`pktgen_agent/client.py:141`

```python
# execute_lua() — 连接、发送、接收、断开
def execute_lua(lua_code, host, port):
    with PktgenClient(host=host, port=port) as client:  # ① 建立 TCP 连接
        return client.execute(lua_code)                  # ② 发送 + 接收
```

`PktgenClient` 内部（`client.py:29`）：

```
① connect()    → socket.connect((host, 22022))      # 连上 Pktgen 的 TCP 端口
② send_lua()   → sock.sendall(lua_code.encode())     # 把 Lua 脚本发过去
③ recv 循环    → sock.recv(65536) 直到超时            # 读 Pktgen 返回的结果
④ disconnect() → sock.close()                        # 断开连接
```

Pktgen 收到 Lua 后开始执行 — 发包机器开始工作。

---

## 完整调用链（一次请求的函数调用栈）

```
你的输入: "用80%速率发UDP洪水"
│
main()                                    # agent.py:162
├─ create_tools()                         # tools/execute.py:272
│   └─ for yaml in skills/*.yaml:
│       └─ create_skill_tool()            # tools/execute.py:198
│           ├─ _load_skill_meta()         # 读 YAML
│           └─ _build_pydantic_model()    # 造参数模型
│
├─ get_model()                            # agent.py:55
│   └─ init_chat_model("deepseek-v4-flash", base_url="api.deepseek.com")
│
├─ create_pktgen_agent()                  # agent.py:74
│   └─ create_agent(model, tools, SYSTEM_PROMPT)
│
└─ run_interactive()                      # agent.py:122
    └─ while True:
        cmd = input("> ")
        agent.invoke({"messages": [{"role": "user", "content": cmd}]})
        │
        │  LangChain 内部：大模型返回 tool_call("udp_flood", {rate:80})
        │
        ├─▶ udp_flood(rate=80)            # 工具被调用
        │    └─ _execute(**kwargs)         # tools/execute.py:234
        │        ├─ compiler.compile("udp_flood", {rate:80})
        │        │   # compiler/compile.py:401
        │        │   ├─ 校验 rate: 80 在 [0,100] 内
        │        │   ├─ resolve_topology("$topology.tx_port") → "0"
        │        │   ├─ resolve_params("$params.rate") → 80
        │        │   └─ emit: pktgen.set("0","rate",80);\npktgen.start("0");
        │        │
        │        └─ [live] execute_lua(lua_code, host, port)
        │             # client.py:141
        │             ├─ PktgenClient.connect()  → TCP 三次握手
        │             ├─ send_lua(lua_code)       → 发送 Lua 源码
        │             ├─ recv()...                → 读返回结果
        │             └─ disconnect()             → TCP 四次挥手
        │
        └─ 返回 {"success": true, "skill": "udp_flood", ...}
        │
        │  LangChain 再调一次大模型，总结结果
        │
        └─ print("UDP洪水已启动，速率80%...")
```

---

## 时间线视角

| 时间 | 谁在干活 | 干什么 |
|------|---------|--------|
| t=0ms | `main()` | 启动，加载 9 个工具 |
| t=100ms | `create_agent()` | 组装 LangGraph Agent |
| t=200ms | `run_interactive()` | 打印提示符 `>`，等你输入 |
| **你输入...** | | |
| t=+100ms | LangChain → DeepSeek API | 把你的话 + 工具列表发给大模型 |
| t=+800ms | DeepSeek 返回 | `tool_call: udp_flood(rate=80)` |
| t=+801ms | `SkillCompiler.compile()` | 校验 rate=80 |
| t=+805ms | `compile_phase()` | 遍历 setup/plan/teardown，替换所有 `$params` 和 `$topology` |
| t=+810ms | | Lua 代码生成完毕 |
| t=+811ms | `PktgenClient.connect()` | TCP 连 Pktgen:22022 |
| t=+815ms | `send_lua()` | 发送 Lua 脚本 |
| t=+820ms | Pktgen 返回 | 读响应 |
| t=+825ms | LangChain → DeepSeek API | 把工具结果发回大模型做总结 |
| t=+1500ms | DeepSeek 返回 | 生成自然语言回复 |
| t=+1501ms | `print()` | 终端显示："UDP洪水已启动" |

---

## 项目结构

```
项目根目录/
├── dsl/skills/          ← 9 个"菜谱"（每种操作一个 YAML 文件）
│   ├── udp_flood.yaml       发 UDP 洪水
│   ├── tcp_flood.yaml       发 TCP 洪水
│   ├── icmp_flood.yaml      发 ICMP（ping）洪水
│   ├── arp_flood.yaml       发 ARP 洪水
│   ├── range_based_scan.yaml 批量扫描一段 IP
│   ├── pcap_replay.yaml     回放抓包文件
│   ├── stats_monitoring.yaml 查看端口统计
│   └── safe_stop_and_reset.yaml  安全停止
│
├── pktgen_agent/         ← Python 核心代码
│   ├── agent.py              入口程序（启动 AI 对话）
│   ├── agent_prompt.py       系统提示词
│   ├── compiler/compile.py   编译器（菜谱 → Lua）
│   ├── client.py             TCP 客户端（连接发包机器）
│   ├── tools/execute.py      工具生成器（自动把菜谱变成 AI 可调用的工具）
│   ├── config.py             配置与日志
│   └── topology.py           拓扑配置加载
│
├── knowledge/            ← Pktgen 官方文档（知识库）
├── tests/                ← 121 个测试
├── topology.yaml         ← 硬件拓扑（机器 IP、端口号）
└── lua_scripts/          ← 编译产物保存目录
```

---

## 9 个可用技能

| 技能名 | 用途 | 关键参数 |
|--------|------|---------|
| `udp_flood` | UDP 洪水攻击 | rate, dst_ip, src_ip, sport, dport, pktSize, count |
| `tcp_flood` | TCP 洪水攻击 | rate, dst_ip, src_ip, sport, dport, tcp_flags, pktSize, count |
| `icmp_flood` | ICMP 洪水攻击 | rate, dst_ip, src_ip, ttl, pktSize, count |
| `arp_flood` | ARP 洪水攻击 | rate, dst_ip, src_ip, dst_mac, src_mac, arp_type, count |
| `range_based_scan` | 范围扫描 | scan_field, start, min, max, inc, rate |
| `packet_sequence_generation` | 自定义序列发包 | sequences (包数组) |
| `pcap_replay` | PCAP 回放 | pcap_file, rate |
| `stats_monitoring` | 查看端口统计 | port_list |
| `safe_stop_and_reset` | 安全停止所有流量 | (无参数) |

---

## 关键设计决策

| 设计 | 好处 |
|------|------|
| **菜谱和硬件分离** | 技能文件只写 `$topology.tx_port`，不写死物理端口号。换机器只需改 `topology.yaml` |
| **默认干跑** | 不连机器就能看生成的 Lua 对不对，防止误操作把网络搞崩 |
| **自动发现新技能** | 往 `dsl/skills/` 里扔一个新 YAML，AI 自动学会调用，不用改任何代码 |
| **编译器先校验再发射** | 参数不对直接报错，不会生成非法的 Lua 发给 Pktgen |
| **安全停止技能** | `safe_stop_and_reset` 可以紧急停止所有发包 — 就像紧急刹车 |

---

**一句话总结**：你说人话 → AI 选工具 → 编译器把模板+参数翻译成 Lua → TCP 发给发包机 → 机器开始工作 → 结果返回给你。
