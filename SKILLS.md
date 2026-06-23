# Pktgen Agent — Skills Overview

9 skills organized by intent. Each skill is defined in `dsl/skills/<name>.yaml` and compiles to Lua for execution on a Pktgen-DPDK instance via TCP (port 22022).

## Traffic Generation（流量生成）

Send packets at high rate. All IP-layer skills support destination addressing (dst_ip, dst_mac, src_ip, src_mac).

### udp_flood
UDP packet flood. Rate is required; destination IP/MAC/port and packet size/count are optional.

| Param | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| rate | float | **yes** | — | Packet rate (0-100%) |
| dst_ip | ip_address | no | 10.10.10.2 | Destination IP |
| src_ip | string | no | 192.168.1.1/24 | Source IP (CIDR) |
| dst_mac | string | no | 00:00:00:00:00:01 | Destination MAC |
| src_mac | string | no | 00:00:00:00:00:02 | Source MAC |
| sport | integer | no | 1234 | UDP source port |
| dport | integer | no | 5678 | UDP destination port |
| pktSize | integer | no | 256 | Packet size (64-1518 bytes) |
| count | integer | no | 0 | Packet count (0=forever) |
| burst | integer | no | 128 | Tx burst size |

### tcp_flood
TCP packet flood. Adds `tcp_flags` on top of the addressing params shared with udp_flood.

Same addressing params as udp_flood, plus:

| Param | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| tcp_flags | string | no | ack | TCP flags (syn, ack, fin, rst, psh, urg, etc.) |

### icmp_flood
ICMP Echo Request (ping) flood. No port numbers — uses TTL instead.

Same addressing params as udp_flood, with:

| Param | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| ttl | integer | no | 64 | IP TTL value |

### arp_flood
ARP packet flood. L2-only protocol — no IP addressing needed.

| Param | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| rate | float | **yes** | — | Packet rate (0-100%) |
| arp_type | enum | no | request | request / gratuitous |
| count | integer | no | 0 | Packet count |
| burst | integer | no | 128 | Tx burst size |

### pcap_replay
Replay packets from a PCAP file. Addressing is embedded in the PCAP.

| Param | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| pcap_file | string | **yes** | — | Path to PCAP file |
| rate | float | no | 100 | Packet rate (0-100%) |
| count | integer | no | 0 | Packet count |

---

## Traffic Scanning（流量扫描）

### range_based_scan
Vary a field across a range. Each packet increments the field by `inc`, wrapping from `min` to `max`.

| Param | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| scan_field | enum | **yes** | — | dst_ip, src_ip, dst_port, src_port, dst_mac, src_mac, vlan_id, pkt_size |
| start | any | **yes** | — | Starting value |
| min | any | **yes** | — | Minimum (wrap lower bound) |
| max | any | **yes** | — | Maximum (wrap upper bound) |
| inc | any | **yes** | — | Increment per packet |
| rate | float | no | 50 | Packet rate (0-100%) |
| pktSize | integer | no | 128 | Packet size (64-1518 bytes) |
| count | integer | no | 0 | Packet count (0=forever) |

---

## Packet Crafting（包构造）

### packet_sequence_generation
Send up to 16 distinct packet templates in sequence. Each entry is a complete packet definition.

| Param | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| sequences | table | **yes** | — | Array of packet tables |
| rate | float | no | 100 | Packet rate (0-100%) |
| count | integer | no | 0 | Packet count |
| burst | integer | no | 128 | Tx burst size |

Each sequence entry must have: `eth_dst_addr`, `eth_src_addr`, `ip_dst_addr`, `ip_src_addr`, `sport`, `dport`, `ethType`, `ipProto`, `vlanid`, `pktSize`. Optional: `teid`, `cos`, `tos`, `tcp_flags`.

---

## Monitoring（监控）

### stats_monitoring
Poll and display port statistics. Read-only — does not generate traffic.

| Param | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| interval_ms | integer | no | 1000 | Polling interval (ms) |
| iterations | integer | no | 10 | Number of polls (0=forever) |
| mode | enum | no | all | all / link / sending / rates / packets / port |

---

## Control（控制）

### safe_stop_and_reset
Stop all traffic, optionally save config, clear stats, and reset ports. Idempotent — safe to call multiple times.

| Param | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| save_config | boolean | no | false | Save config before reset |
| config_file | string | no | backup.cmd | Config filename |
| clear_stats | boolean | no | true | Clear port statistics |
| reset_ports | boolean | no | true | Reset ports to defaults |
| return_to_main | boolean | no | true | Return display to main page |

---

## Quick Reference

```
traffic_generation:  udp_flood, tcp_flood, icmp_flood, arp_flood, pcap_replay
traffic_scanning:    range_based_scan
packet_crafting:     packet_sequence_generation
monitoring:          stats_monitoring
control:             safe_stop_and_reset
```

## Typical Workflow

```
safe_stop_and_reset()          # 1. clean slate
udp_flood(rate=80, ...)        # 2. start traffic
stats_monitoring(iterations=5) # 3. verify traffic flowing
safe_stop_and_reset()          # 4. stop
```
