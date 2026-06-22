import sys
import json
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from bloom_terminal.db import BloomDB
from config import load_config


def diff_chain(today: list[dict], prior: list[dict], held_strikes: list[float], band: float = 0.30) -> list[dict]:
    if not prior:
        return []

    today_strikes = {}
    today_expiries = set()
    prior_strikes = {}
    prior_expiries = set()

    for c in today:
        exp = c["expiry"]
        strike = c.get("strike", 0)
        today_expiries.add(exp)
        if exp not in today_strikes:
            today_strikes[exp] = set()
        today_strikes[exp].add(strike)

    for c in prior:
        exp = c["expiry"]
        strike = c.get("strike", 0)
        prior_expiries.add(exp)
        if exp not in prior_strikes:
            prior_strikes[exp] = set()
        prior_strikes[exp].add(strike)

    alerts = []

    new_expiries = today_expiries - prior_expiries
    for exp in sorted(new_expiries):
        alerts.append({
            "alert_type": "new_expiry",
            "severity": "info",
            "message": f"New expiry listed: {exp}",
        })

    for exp in today_strikes:
        if exp in prior_strikes:
            new_strikes = today_strikes[exp] - prior_strikes[exp]
            for s in sorted(new_strikes):
                if any(abs(s - held) / max(held, 1) <= band for held in held_strikes):
                    alerts.append({
                        "alert_type": "new_strike",
                        "severity": "info",
                        "message": f"New strike ${s:.2f} listed for {exp}",
                    })

    return alerts


def check_condition_alerts(valuations: list[dict], positions: list[dict], config: dict, prior_vals: list[dict] | None = None) -> list[dict]:
    alerts = []
    target_near = config.get("target_near_pct", 0.80)
    iv_change = config.get("iv_change_pct", 0.20)

    for v in valuations:
        pid = v["position_id"]
        ticker = v["ticker"]
        ptype = v["asset_type"]

        pt = v.get("progress_target")
        ps = v.get("progress_stop")
        pnl = v.get("pnl_dollars", 0)

        if pt is not None and pt >= 100:
            alerts.append({
                "alert_type": "target_hit",
                "severity": "high",
                "ticker": ticker,
                "position_id": pid,
                "message": f"{pid} hit your target level",
                "detail": f"P&L: ${pnl:.2f}, {v.get('pnl_pct', 0):.1f}%",
            })
        elif pt is not None and pt >= target_near * 100:
            alerts.append({
                "alert_type": "target_near",
                "severity": "info",
                "ticker": ticker,
                "position_id": pid,
                "message": f"{pid} is {pt:.0f}% toward target",
                "detail": f"{v.get('mark')} vs target",
            })

        if ps is not None and ps >= 100:
            alerts.append({
                "alert_type": "stop_hit",
                "severity": "high",
                "ticker": ticker,
                "position_id": pid,
                "message": f"{pid} crossed your stop level",
                "detail": f"P&L: ${pnl:.2f}, {v.get('pnl_pct', 0):.1f}%",
            })

    if prior_vals:
        prior_map = {pv["position_id"]: pv for pv in prior_vals}
        for v in valuations:
            pid = v["position_id"]
            if pid in prior_map:
                prev_iv = prior_map[pid].get("iv")
                curr_iv = v.get("iv")
                if prev_iv and curr_iv and prev_iv > 0:
                    iv_delta = abs(curr_iv - prev_iv) / prev_iv
                    if iv_delta >= iv_change:
                        alerts.append({
                            "alert_type": "iv_change",
                            "severity": "warn",
                            "ticker": v["ticker"],
                            "position_id": pid,
                            "message": f"{pid} IV moved {iv_delta*100:.0f}% vs prior run",
                            "detail": f"IV: {prev_iv:.1f} → {curr_iv:.1f}",
                        })

    return alerts


def run_layer4(
    db: BloomDB,
    config: dict,
    positions: list[dict],
    asof: str | None = None,
):
    run_date = asof or date.today().isoformat()
    valuations = db.get_latest_valuations()

    prior_vals = None
    if asof:
        prior_asof = (datetime.strptime(asof, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
        with db._conn() as conn:
            rows = conn.execute("SELECT * FROM valuations WHERE run_date=?", (prior_asof,)).fetchall()
            if rows:
                prior_vals = [dict(r) for r in rows]

    condition_alerts = check_condition_alerts(valuations, positions, config, prior_vals)

    tickers = set(p["ticker"] for p in positions)
    diff_alert_list = []
    for ticker in tickers:
        today_chain = db.get_snapshot(ticker, run_date)
        prior_chain = db.get_prior_snapshot(ticker, run_date)
        if today_chain and prior_chain:
            held_strikes = [
                p["strike"] for p in positions
                if p["ticker"] == ticker and p.get("strike")
            ]
            band = config.get("new_strike_band", 0.30)
            diffs = diff_chain(today_chain, prior_chain, held_strikes, band)
            diff_alert_list.extend(diffs)

    news_analyses = {}
    for ticker in tickers:
        news = db.get_news_analysis(ticker, run_date)
        if news and news.get("position_relevant"):
            condition_alerts.append({
                "alert_type": "news_flag",
                "severity": "warn",
                "ticker": ticker,
                "position_id": None,
                "message": f"{ticker}: {news.get('summary', 'Relevant news')[:80]}",
                "detail": json.dumps(news.get("relevant_headline_titles", [])),
            })

    from .layer2_portfolio import compute_allocation, compute_aggregate_greeks
    agg = compute_aggregate_greeks(valuations)
    alloc = compute_allocation(valuations)

    all_alerts = condition_alerts + diff_alert_list
    db.save_alerts(run_date, all_alerts)

    return {
        "run_date": run_date,
        "alerts": all_alerts,
        "agg_greeks": agg,
        "allocation": alloc,
    }


