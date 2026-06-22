import os
import sys
import json
from datetime import datetime, date
from pathlib import Path

import yfinance as yf
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

from bloom_terminal.greeks import compute_greeks
from bloom_terminal.db import BloomDB
from config import load_positions, load_config, SNAPSHOTS_DIR


def days_to_expiry(expiry_str: str) -> int:
    exp = datetime.strptime(expiry_str, "%Y-%m-%d").date()
    return max((exp - date.today()).days, 0)


def pull_chain(ticker: str) -> list[dict]:
    t = yf.Ticker(ticker)
    try:
        opts = t.options
    except Exception:
        return []
    if not opts:
        return []

    chains = []
    for exp in opts[:6]:
        try:
            opt_chain = t.option_chain(exp)
        except Exception:
            continue
        for row in opt_chain.calls.to_dict("records"):
            row["option_type"] = "call"
            row["expiry"] = exp
            chains.append(row)
        for row in opt_chain.puts.to_dict("records"):
            row["option_type"] = "put"
            row["expiry"] = exp
            chains.append(row)
    return chains


def get_mid(row: dict) -> float | None:
    bid = row.get("bid")
    ask = row.get("ask")
    if bid is not None and ask is not None and bid > 0 and ask > 0:
        return (bid + ask) / 2.0
    last = row.get("last", 0)
    return last if last and last > 0 else None


def run_layer1(positions: list[dict], db: BloomDB, config: dict, asof: str | None = None):
    run_date = asof or date.today().isoformat()
    tickers = set(p["ticker"] for p in positions)
    spots = {}
    chains = {}

    for t in tickers:
        try:
            tk = yf.Ticker(t)
            tk_info = tk.history(period="1d")
            if not tk_info.empty:
                spots[t] = float(tk_info["Close"].iloc[-1])
            else:
                spots[t] = 0.0
        except Exception:
            spots[t] = 0.0

        chain_data = pull_chain(t)
        chains[t] = chain_data
        if chain_data:
            db.save_snapshot(t, run_date, chain_data)

    today = date.today()
    rfr = config.get("risk_free_rate", 0.045)
    valuations = []

    for pos in positions:
        pid = pos.get("id", f"{pos['ticker']}_{pos.get('strike','')}_{pos.get('expiry','')}")
        ticker = pos["ticker"]
        asset_type = pos["asset_type"]
        contracts = pos["contracts"]
        entry_price = pos["entry_price"]
        target = pos.get("target_price")
        stop = pos.get("stop_price")

        spot = spots.get(ticker, 0.0)

        if asset_type == "shares":
            mark = spot
            current_value = mark * contracts
            cost_basis = entry_price * contracts
            pnl_dollars = current_value - cost_basis
            pnl_pct = ((mark - entry_price) / entry_price * 100) if entry_price else 0.0
            dte = None
            delta = gamma = theta = vega = iv = None

            progress_target = None
            progress_stop = None

            if target and target != entry_price:
                pt = ((mark - entry_price) / (target - entry_price)) * 100
                progress_target = round(pt, 1)
            if stop and stop != entry_price:
                ps = ((mark - entry_price) / (entry_price - stop)) * 100
                progress_stop = round(ps, 1)

            valuations.append({
                "position_id": pid,
                "ticker": ticker,
                "asset_type": asset_type,
                "mark": mark,
                "current_value": round(current_value, 2),
                "cost_basis": round(cost_basis, 2),
                "pnl_dollars": round(pnl_dollars, 2),
                "pnl_pct": round(pnl_pct, 2),
                "dte": dte,
                "delta": delta,
                "gamma": gamma,
                "theta": theta,
                "vega": vega,
                "iv": iv,
                "progress_target": progress_target,
                "progress_stop": progress_stop,
            })

        elif asset_type == "option":
            expiry = pos["expiry"]
            strike = pos["strike"]
            opt_type = pos["option_type"]
            dte = days_to_expiry(expiry)

            chain = chains.get(ticker, [])
            match = None
            for c in chain:
                if (c.get("strike") == strike
                        and c["expiry"] == expiry
                        and c["option_type"] == opt_type):
                    match = c
                    break

            if match:
                mark = get_mid(match)
                if mark is None:
                    mark = match.get("last", 0.0)
                iv_val = match.get("impliedVolatility", 0.0)
                if iv_val is None or iv_val == 0.0:
                    iv_val = 0.30
            else:
                mark = 0.0
                iv_val = 0.30

            if mark is None or mark == 0.0:
                mark = 0.0

            current_value = mark * contracts * 100
            cost_basis = entry_price * contracts * 100
            pnl_dollars = current_value - cost_basis
            pnl_pct = ((mark - entry_price) / entry_price * 100) if entry_price else 0.0

            greeks = compute_greeks(spot, strike, dte, iv_val * 100, opt_type, rfr)

            progress_target = None
            progress_stop = None

            if target and target != entry_price:
                if target > entry_price:
                    pt = ((mark - entry_price) / (target - entry_price)) * 100
                else:
                    pt = ((entry_price - mark) / (entry_price - target)) * 100
                progress_target = round(pt, 1)

            if stop and stop != entry_price:
                if entry_price > stop:
                    ps = ((entry_price - mark) / (entry_price - stop)) * 100
                else:
                    ps = ((mark - entry_price) / (stop - entry_price)) * 100
                progress_stop = round(ps, 1)

            valuations.append({
                "position_id": pid,
                "ticker": ticker,
                "asset_type": asset_type,
                "mark": round(mark, 2),
                "current_value": round(current_value, 2),
                "cost_basis": round(cost_basis, 2),
                "pnl_dollars": round(pnl_dollars, 2),
                "pnl_pct": round(pnl_pct, 2),
                "dte": dte,
                "delta": greeks["delta"],
                "gamma": greeks["gamma"],
                "theta": greeks["theta"],
                "vega": greeks["vega"],
                "iv": round(iv_val * 100, 2),
                "progress_target": progress_target,
                "progress_stop": progress_stop,
            })

    db.save_valuations(run_date, valuations)
    return {"run_date": run_date, "valuations": valuations, "spots": spots}
