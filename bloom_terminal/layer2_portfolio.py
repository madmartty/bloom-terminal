import sys
from datetime import date, datetime
from collections import defaultdict
from pathlib import Path

import yfinance as yf
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

from bloom_terminal.db import BloomDB
from config import load_config, get_sector, load_positions


def compute_allocation(valuations: list[dict]) -> dict:
    total_value = sum(v.get("current_value", 0.0) for v in valuations)
    by_ticker = defaultdict(float)
    by_sector = defaultdict(float)
    ticker_to_sector = {}

    for v in valuations:
        ticker = v["ticker"]
        val = v.get("current_value", 0.0)
        sector = get_sector(ticker)
        by_ticker[ticker] += val
        by_sector[sector] += val
        ticker_to_sector[ticker] = sector

    ticker_pct = {}
    sector_pct = {}
    for t, val in by_ticker.items():
        ticker_pct[t] = round(val / total_value * 100, 2) if total_value else 0.0
    for s, val in by_sector.items():
        sector_pct[s] = round(val / total_value * 100, 2) if total_value else 0.0

    return {
        "total_value": round(total_value, 2),
        "by_ticker": dict(ticker_pct),
        "by_sector": dict(sector_pct),
        "ticker_to_sector": ticker_to_sector,
    }


def compute_aggregate_greeks(valuations: list[dict]) -> dict:
    net_delta = 0.0
    total_theta = 0.0
    net_vega = 0.0

    for v in valuations:
        if v.get("asset_type") == "option":
            contracts = None
            positions = load_positions()
            for p in positions:
                if p.get("id", "").startswith(v["ticker"]):
                    contracts = p.get("contracts", 0)
                    break
            if contracts is None:
                for p in positions:
                    if p["ticker"] == v["ticker"] and p["asset_type"] == "option":
                        contracts = p.get("contracts", 0)
                        break
            if contracts is None:
                contracts = 0

            multiplier = contracts * 100
            net_delta += (v.get("delta", 0.0) or 0.0) * multiplier
            total_theta += (v.get("theta", 0.0) or 0.0) * multiplier
            net_vega += (v.get("vega", 0.0) or 0.0) * multiplier

        elif v.get("asset_type") == "shares":
            positions = load_positions()
            shares = 0
            for p in positions:
                if p.get("id", "").startswith(v["ticker"]) or p["ticker"] == v["ticker"]:
                    shares = p.get("contracts", 0)
                    break
            net_delta += shares

    return {
        "net_delta_share_eq": round(net_delta, 2),
        "total_theta_dollars": round(total_theta, 2),
        "net_vega_per_iv_point": round(net_vega, 2),
    }


def compute_iv_rank(db: BloomDB, ticker: str, lookback: int = 252, min_history: int = 20) -> dict:
    history = db.get_iv_history(ticker)
    ivs = [h["iv"] for h in history if h.get("iv") is not None]

    if len(ivs) < min_history:
        return {"iv_rank": None, "percentile": None, "current_iv": None, "status": "building_history"}

    recent = ivs[-lookback:] if len(ivs) > lookback else ivs
    current_iv = recent[-1]
    count_less = sum(1 for v in recent if v <= current_iv)
    percentile = count_less / len(recent) * 100

    return {
        "iv_rank": round(percentile, 1),
        "percentile": round(percentile, 1),
        "current_iv": current_iv,
        "status": "ready",
    }


def flag_dte(valuations: list[dict], threshold: int = 45) -> list[dict]:
    flags = []
    for v in valuations:
        if v.get("asset_type") == "option" and v.get("dte") is not None:
            if v["dte"] <= threshold:
                flags.append({
                    "position_id": v["position_id"],
                    "ticker": v["ticker"],
                    "dte": v["dte"],
                    "message": f"{v['ticker']} {v.get('dte')} days to expiry — within {threshold}d window",
                })
    return flags


def run_layer2(db: BloomDB, config: dict, asof: str | None = None):
    run_date = asof or date.today().isoformat()
    valuations = db.get_latest_valuations()

    allocation = compute_allocation(valuations)
    greeks = compute_aggregate_greeks(valuations)

    ticker_cap = config.get("concentration_ticker_cap", 0.40)
    sector_cap = config.get("concentration_sector_cap", 0.60)
    iv_lookback = config.get("iv_lookback_days", 252)
    iv_min = config.get("iv_min_history", 20)
    dte_threshold = config.get("dte_warn_threshold", 45)

    concentration_flags = []
    for ticker, pct in allocation.get("by_ticker", {}).items():
        if pct / 100.0 > ticker_cap:
            concentration_flags.append({
                "type": "ticker",
                "name": ticker,
                "pct": pct,
                "cap": ticker_cap * 100,
                "message": f"{ticker} at {pct:.1f}% exceeds {ticker_cap*100:.0f}% cap",
            })
    for sector, pct in allocation.get("by_sector", {}).items():
        if pct / 100.0 > sector_cap:
            concentration_flags.append({
                "type": "sector",
                "name": sector,
                "pct": pct,
                "cap": sector_cap * 100,
                "message": f"{sector} at {pct:.1f}% exceeds {sector_cap*100:.0f}% cap",
            })

    iv_ranks = {}
    for v in valuations:
        if v.get("asset_type") == "option":
            ticker = v["ticker"]
            if ticker not in iv_ranks:
                rank = compute_iv_rank(db, ticker, iv_lookback, iv_min)
                iv_ranks[ticker] = rank

    dte_flags = flag_dte(valuations, dte_threshold)

    analytics = {
        "allocation": allocation,
        "aggregate_greeks": greeks,
        "concentration_flags": concentration_flags,
        "iv_ranks": iv_ranks,
        "dte_flags": dte_flags,
    }

    db.save_portfolio_analytics(run_date, analytics)
    return analytics
