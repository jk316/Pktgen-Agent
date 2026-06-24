#!/usr/bin/env python3
"""
Pktgen Agent — entry point (thin wrapper).

For the full implementation, see the pktgen_agent package.

Usage:
    python agent.py                  # dry-run
    python agent.py --live           # live mode
    python agent.py --live --host 192.168.1.100 --model deepseek-v4-flash
"""

import sys

from pktgen_agent.agent import main

if __name__ == "__main__":
    sys.exit(main())
