package.path = package.path ..";?.lua;test/?.lua;app/?.lua;"

require "Pktgen"

-- [setup]
pktgen.screen("off");
pktgen.set_type(0, "ipv4");
pktgen.set_proto(0, "udp");
pktgen.set_ipaddr(0, "dst", "100.1.11.22");
pktgen.set_ipaddr(0, "src", "192.168.1.1/24");
pktgen.set_mac(0, "dst", "f0:c4:78:4c:a5:55");
pktgen.set_mac(0, "src", "00:00:00:00:00:02");

-- [plan]
pktgen.set(0, "size", 256);
pktgen.set(0, "burst", 128);
pktgen.set(0, "sport", 1234);
pktgen.set(0, "dport", 28763);
pktgen.set(0, "rate", 100);
pktgen.set(0, "count", 0);
pktgen.start(0);
pktgen.delay(100000);

-- [teardown]
pktgen.stop(0);
pktgen.screen("on");
