#!/usr/bin/env python3
"""
Bloom Terminal - One screen, every morning.

Tracks real positions (options + shares), values live off yfinance,
reports conditions, never trades.

Usage:
    python runner.py                          # run today
    python runner.py --asof 2026-06-19        # run with specific date stamp
    python runner.py --skip-news              # skip opencode news analysis
    python runner.py --skip-macro             # skip macro gate
    python runner.py --notify                 # push alerts (Telegram/iMessage)

Cron (daily after close, M-F):
    30 20 * * 1-5 cd /path/to/Bloom Terminal && python runner.py --notify >> bloom.log 2>&1
"""

import argparse
import json
import sys
import os
from datetime import date
from pathlib import Path

from config import (
    load_positions, load_config, DB_PATH, OPENCODE_NEWS_MODEL,
)
from bloom_terminal.db import BloomDB
from bloom_terminal.layer1_data import run_layer1
from bloom_terminal.layer2_portfolio import run_layer2
from bloom_terminal.layer3_macro import run_layer3
from bloom_terminal.layer4_alerts import run_layer4
from bloom_terminal.notifier import maybe_send


def main():
    parser = argparse.ArgumentParser(description="Bloom Terminal — Portfolio Monitor")
    parser.add_argument("--asof", type=str, default=None, help="Run date YYYY-MM-DD")
    parser.add_argument("--skip-news", action="store_true", help="Skip opencode news analysis")
    parser.add_argument("--skip-macro", action="store_true", help="Skip macro gate")
    parser.add_argument("--notify", action="store_true", help="Push alerts via Telegram/iMessage")
    args = parser.parse_args()

    run_date = args.asof or date.today().isoformat()
    config = load_config()
    positions = load_positions()
    db = BloomDB(str(DB_PATH))

    print(f"Bloom Terminal — {run_date}")
    print("=" * 50)

    layer1 = run_layer1(positions, db, config, asof=args.asof)
    print(f"Layer 1: {len(layer1['valuations'])} positions valued")

    layer2 = run_layer2(db, config, asof=args.asof)
    print(f"Layer 2: Portfolio analytics computed")
    agg = layer2.get("aggregate_greeks", {})
    print(f"  Net Delta: {agg.get('net_delta_share_eq', 'N/A')} shares")
    print(f"  Theta/Day: ${agg.get('total_theta_dollars', 'N/A'):.2f}")
    print(f"  Net Vega:  ${agg.get('net_vega_per_iv_point', 'N/A'):.2f}")

    opencode_model = None if args.skip_news else OPENCODE_NEWS_MODEL
    skip_macro = args.skip_macro
    layer3 = run_layer3(positions, db, config, asof=args.asof, opencode_model=opencode_model, skip_macro=skip_macro)
    if layer3:
        macro = layer3.get("macro")
        if macro:
            print(f"Layer 3: Macro score = {macro.get('score', 'N/A')}/100")
        news_count = sum(1 for n in layer3.get("news", {}).values() if n.get("summary") not in ("No recent news.", "News unavailable."))
        if opencode_model and news_count:
            print(f"  News analyses: {news_count} names (via opencode)")

    layer4 = run_layer4(db, config, positions, asof=args.asof)
    alerts = layer4.get("alerts", [])
    print(f"Layer 4: {len(alerts)} alerts generated")

    high = [a for a in alerts if a["severity"] == "high"]
    warn = [a for a in alerts if a["severity"] == "warn"]
    if high:
        for a in high:
            print(f"  [HIGH] {a['message']}")
    if warn:
        for a in warn:
            print(f"  [WARN] {a['message']}")

    if args.notify:
        maybe_send(alerts, asof=args.asof)
        print("Notifications sent")

    print("\nDashboard: streamlit run dashboard.py")
    print("Done.")


if __name__ == "__main__":
    main()
