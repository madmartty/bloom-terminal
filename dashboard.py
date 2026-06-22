import sqlite3
import json
from datetime import date, datetime
from pathlib import Path

import streamlit as st
import pandas as pd
import plotly.express as px

from config import DB_PATH, load_positions
from bloom_terminal.db import BloomDB

st.set_page_config(
    page_title="Bloom Terminal",
    page_icon="\U0001f33b",
    layout="wide",
    initial_sidebar_state="collapsed",
)

DB = BloomDB(str(DB_PATH))
today = date.today().isoformat()


def run_pipeline_safe():
    try:
        import shutil
        from config import load_config, OPENCODE_NEWS_MODEL
        from bloom_terminal.layer1_data import run_layer1
        from bloom_terminal.layer2_portfolio import run_layer2
        from bloom_terminal.layer3_macro import run_layer3
        from bloom_terminal.layer4_alerts import run_layer4

        config = load_config()
        positions = load_positions()
        opencode_ok = shutil.which("opencode") is not None or shutil.which("opencode.cmd") is not None

        run_layer1(positions, DB, config, asof=today)
        run_layer2(DB, config, asof=today)
        run_layer3(positions, DB, config, asof=today,
                   opencode_model=OPENCODE_NEWS_MODEL if opencode_ok else None)
        run_layer4(DB, config, positions, asof=today)
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Pipeline error: {e}")
        return False


def get_latest_valuations():
    return DB.get_latest_valuations()


def get_alerts():
    with DB._conn() as conn:
        rows = conn.execute(
            "SELECT * FROM alerts WHERE run_date=? ORDER BY "
            "CASE severity WHEN 'high' THEN 0 WHEN 'warn' THEN 1 ELSE 2 END, id",
            (today,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_analytics():
    return DB.get_analytics(today)


def get_macro():
    return DB.get_macro_score(today)


def get_news():
    tickers = set(p["ticker"] for p in load_positions())
    news = {}
    for t in tickers:
        n = DB.get_news_analysis(t, today)
        if n:
            news[t] = n
    return news


vals = get_latest_valuations()
alerts = get_alerts()
analytics = get_analytics()
macro = get_macro()
news_analyses = get_news()

total_nav = sum(v.get("current_value", 0) for v in vals) if vals else 0
total_cost = sum(v.get("cost_basis", 0) for v in vals) if vals else 0
total_pnl = total_nav - total_cost
total_pnl_pct = (total_pnl / total_cost * 100) if total_cost else 0
n_positions = len(vals)
n_alerts = len(alerts)

agg = (analytics or {}).get("aggregate_greeks", {})
macro_score = (macro or {}).get("score", "\u2014") if macro else "\u2014"

st.markdown("""
<style>
html, body, .stApp { background-color: #0a0a0a; color: #e0e0e0; font-family: 'JetBrains Mono', 'SF Mono', 'Consolas', monospace; }
.block-container { padding: 1.5rem 2rem !important; }
h1, h2, h3 { font-family: 'JetBrains Mono', monospace !important; font-weight: 600 !important; letter-spacing: -0.5px; }
h1 { font-size: 1.5rem !important; color: #00c853 !important; }
h2 { font-size: 1.1rem !important; color: #90caf9 !important; margin-top: 0 !important; }
h3 { font-size: 0.9rem !important; color: #b0bec5 !important; }
p, li, div, span { font-family: 'JetBrains Mono', 'SF Mono', 'Consolas', monospace !important; }
div[data-testid="stMetricValue"] { font-family: 'JetBrains Mono', monospace; }
.alert-box { padding: 0.4rem 0.6rem; margin: 0.2rem 0; border-left: 3px solid; font-size: 0.75rem; }
.alert-high { border-color: #ff5252; background: rgba(255,82,82,0.08); }
.alert-warn { border-color: #ffd740; background: rgba(255,215,64,0.08); }
.alert-info { border-color: #64b5f6; background: rgba(100,181,246,0.08); }
.news-box { background: #111; border: 1px solid #2a2a2a; border-radius: 4px; padding: 0.6rem; margin: 0.3rem 0; font-size: 0.75rem; }
.macro-box { background: #0d1b0d; border: 1px solid #1a3a1a; border-radius: 4px; padding: 0.5rem 0.75rem; text-align: center; }
.macro-score { font-size: 1.8rem; font-weight: 700; }
.macro-score.good { color: #00c853; }
.macro-score.ok { color: #ffd740; }
.macro-score.bad { color: #ff5252; }
.dte-pill { display: inline-block; padding: 0.1rem 0.5rem; border-radius: 8px; font-size: 0.7rem; font-weight: 600; }
.dte-urgent { background: #ff5252; color: #000; }
.dte-warn { background: #ffd740; color: #000; }
.dte-ok { background: #2a2a2a; color: #999; }
.news-header { display: flex; justify-content: space-between; }
.sentiment-positive { color: #00c853; }
.sentiment-negative { color: #ff5252; }
.sentiment-neutral { color: #ffd740; }
</style>
""", unsafe_allow_html=True)

st.markdown(f"# \U0001f33b BLOOM TERMINAL  <span style='color:#666;font-size:0.8rem;font-weight:400;'>| {today}</span>", unsafe_allow_html=True)

cols = st.columns(8)
labels = ["NAV", "P&L", "P&L %", "Positions", "Alerts", "Macro", "Net \u0394", "\u0398/Day"]
values = [
    f"${total_nav:,.0f}" if total_nav else "\u2014",
    f"${total_pnl:+,.0f}",
    f"{total_pnl_pct:+.1f}%" if total_cost else "\u2014",
    str(n_positions),
    str(n_alerts),
    str(macro_score),
    f"{agg.get('net_delta_share_eq', 0):+,.0f}",
    f"${agg.get('total_theta_dollars', 0):+,.0f}",
]
colors = ["", "green" if total_pnl >= 0 else "red", "green" if total_pnl_pct >= 0 else "red", "", "", "", "", ""]
for i, col in enumerate(cols):
    col.markdown(
        f"<div style='background:#111;border:1px solid #2a2a2a;border-radius:4px;"
        f"padding:0.4rem 0.6rem;text-align:center;'>"
        f"<div style='color:#666;font-size:0.6rem;text-transform:uppercase;'>{labels[i]}</div>"
        f"<div style='font-size:1rem;font-weight:700;color:#e0e0e0;'>{values[i]}</div></div>",
        unsafe_allow_html=True
    )

st.markdown("---")

left_col, right_col = st.columns([2, 1])

with left_col:
    st.markdown("## POSITIONS")

    if vals:
        rows = []
        for v in vals:
            ticker = v["ticker"]
            ptype = v["asset_type"]
            pid = v["position_id"]
            positions = load_positions()
            pos_obj = None
            for p in positions:
                if p.get("id", "") == pid:
                    pos_obj = p
                    break
                if p["ticker"] == ticker and p["asset_type"] == ptype:
                    pos_obj = p
            strike = pos_obj.get("strike", "") if pos_obj else ""
            opt_type = pos_obj.get("option_type", "").upper() if pos_obj else ""
            expiry = pos_obj.get("expiry", "") if pos_obj else ""

            if v["asset_type"] == "option":
                name = f"{ticker} {opt_type} ${strike}"
                expiry_display = expiry
                dte = v.get("dte", 0)
                if dte is not None:
                    dte_class = "dte-urgent" if dte <= 14 else ("dte-warn" if dte <= 45 else "dte-ok")
                    dte_str = f"<span class='dte-pill {dte_class}'>{dte}d</span>"
                else:
                    dte_str = "\u2014"
            else:
                name = ticker
                expiry_display = "\u2014"
                dte_str = "\u2014"

            pnl_d = v.get("pnl_dollars", 0)
            pnl_color = "green" if pnl_d >= 0 else "red"
            pct = v.get("pnl_pct", 0)
            delta = v.get("delta")
            theta = v.get("theta")
            iv = v.get("iv")
            theta_display = f"${theta*100*100:.2f}" if theta is not None and pos_obj else "\u2014"
            entry_display = f"${v.get('cost_basis',0)/max(v.get('current_value',0),1):.2f}" if v["asset_type"] == "shares" else (f"${pos_obj.get('entry_price',0):.2f}" if pos_obj else "\u2014")

            rows.append({
                "Name": name,
                "Type": "C" if v["asset_type"] == "option" and opt_type == "CALL" else ("P" if v["asset_type"] == "option" else "EQ"),
                "Expiry": expiry_display,
                "DTE": dte_str,
                "Entry": entry_display,
                "Mark": f"${v.get('mark',0):.2f}",
                "Value": f"${v.get('current_value',0):,.0f}",
                "P&L $": f"<span style='color:{pnl_color}'>{pnl_d:+,.0f}</span>",
                "P&L %": f"<span style='color:{pnl_color}'>{pct:+.1f}%</span>",
                "\u0394": f"{delta:.2f}" if delta is not None else "\u2014",
                "\u0398/d": theta_display,
                "IV": f"{iv:.1f}%" if v["asset_type"] == "option" and iv else "\u2014",
            })

        headers = ["Name", "Type", "Expiry", "DTE", "Entry", "Mark", "Value", "P&L $", "P&L %", "\u0394", "\u0398/d", "IV"]
        html = '<table style="width:100%;border-collapse:collapse;font-size:0.72rem;">'
        html += "<tr style='border-bottom:1px solid #333;'>"
        for h in headers:
            html += f"<th style='padding:0.4rem 0.5rem;text-align:left;color:#666;font-weight:400;'>{h}</th>"
        html += "</tr>"
        for r in rows:
            html += "<tr style='border-bottom:1px solid #1a1a1a;'>"
            for k in headers:
                html += f"<td style='padding:0.35rem 0.5rem;'>{r.get(k, '\u2014')}</td>"
            html += "</tr>"
        html += "</table>"
        st.markdown(html, unsafe_allow_html=True)

        for v in vals:
            pt = v.get("progress_target")
            ps = v.get("progress_stop")
            if pt is not None or ps is not None:
                bar_cols = st.columns([3, 1])
                with bar_cols[0]:
                    if pt is not None:
                        st.progress(min(max(pt, 0), 100) / 100.0, text=f"Target: {pt:.0f}%")
                    if ps is not None:
                        st.progress(min(max(ps, 0), 100) / 100.0, text=f"Stop:   {ps:.0f}%")
    else:
        if st.button("Run Pipeline"):
            run_pipeline_safe()
            st.rerun()
        st.info("No data for today. Click 'Run Pipeline' to pull live market data.")

    st.markdown("### Allocation")
    if analytics:
        alloc = analytics.get("allocation", {})
        ticker_pcts = alloc.get("by_ticker", {})
        if ticker_pcts:
            td = pd.DataFrame([{"Ticker": t, "%": p} for t, p in ticker_pcts.items()])
            fig = px.bar(td, x="Ticker", y="%", color="%",
                         color_continuous_scale="RdYlGn", text="%")
            fig.update_layout(height=250, margin=dict(l=10, r=10, t=10, b=20),
                              paper_bgcolor="#0a0a0a", plot_bgcolor="#0a0a0a",
                              font=dict(family="monospace", size=10, color="#e0e0e0"),
                              showlegend=False)
            fig.update_xaxes(gridcolor="#1a1a1a")
            fig.update_yaxes(gridcolor="#1a1a1a")
            st.plotly_chart(fig)

    st.markdown("### News Analysis")
    if news_analyses:
        for ticker, na in news_analyses.items():
            sent = na.get("sentiment", "neutral")
            sent_icon = {"positive": "\U0001f7e2", "negative": "\U0001f534", "neutral": "\U0001f7e1"}.get(sent, "\U0001f7e1")
            st.markdown(
                f"<div class='news-box'><div class='news-header'>"
                f"<strong>{ticker}</strong> "
                f"<span class='sentiment-{sent}'>{sent_icon} {sent.upper()}</span>"
                f"</div><div style='color:#b0bec5;margin-top:0.3rem;'>{na.get('summary', 'No summary')}</div>"
                f"<div style='color:#666;font-size:0.65rem;margin-top:0.3rem;'>Drivers: {', '.join(na.get('key_drivers', ['\u2014']))}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )
    else:
        st.caption("No news analysis for today.")

with right_col:
    st.markdown("## ALERTS")
    if alerts:
        for a in alerts:
            sev = a["severity"]
            icon = {"high": "\U0001f534", "warn": "\U0001f7e1", "info": "\u2139\ufe0f"}.get(sev, "\u2139\ufe0f")
            st.markdown(
                f"<div class='alert-box alert-{sev}'><strong>{icon} {a['message']}</strong>"
                f"<br><span style='color:#888;font-size:0.65rem;'>{a.get('detail', '')}</span></div>",
                unsafe_allow_html=True
            )
    else:
        st.caption("No alerts for today.")

    st.markdown("## MACRO GATE")
    if macro:
        score = macro.get("score", 0)
        grade = "good" if score >= 60 else ("ok" if score >= 35 else "bad")
        st.markdown(
            f"<div class='macro-box'><div class='macro-score {grade}'>{score}</div>"
            f"<div style='color:#666;font-size:0.7rem;'>/ 100</div>"
            f"<div style='margin-top:0.5rem;font-size:0.7rem;color:#b0bec5;'>"
            f"VIX: {macro.get('raw_data',{}).get('vix_current','\u2014')}</div></div>",
            unsafe_allow_html=True,
        )
        comp = macro.get("components", {})
        for k, v in comp.items():
            st.markdown(
                f"<div style='display:flex;justify-content:space-between;font-size:0.7rem;color:#888;padding:0.1rem 0;'>"
                f"<span>{k}</span><span>{v:.0f}</span></div>",
                unsafe_allow_html=True
            )

    st.markdown("## AGGREGATE GREEKS")
    if agg:
        items = [
            ("Net Delta (sh eq)", f"{agg.get('net_delta_share_eq', 0):+,.0f}",
             "green" if agg.get('net_delta_share_eq', 0) > 0 else "red"),
            ("Theta/Day", f"${agg.get('total_theta_dollars', 0):+,.2f}",
             "red" if agg.get('total_theta_dollars', 0) < 0 else "green"),
            ("Vega / IV pt", f"${agg.get('net_vega_per_iv_point', 0):+,.2f}", ""),
        ]
        for label, val, color in items:
            st.markdown(
                f"<div style='display:flex;justify-content:space-between;font-size:0.75rem;padding:0.2rem 0;"
                f"border-bottom:1px solid #1a1a1a;'>"
                f"<span style='color:#666;'>{label}</span>"
                f"<span style='color:{color};'>{val}</span></div>",
                unsafe_allow_html=True
            )

    st.markdown("## DTE WARNINGS")
    if analytics:
        dte_flags = analytics.get("dte_flags", [])
        if dte_flags:
            for f in dte_flags:
                st.markdown(f"<div class='alert-box alert-warn'>{f['message']}</div>", unsafe_allow_html=True)
        else:
            st.caption("No positions approaching expiry.")

    st.markdown("## IV ENVIRONMENT")
    if analytics:
        iv_ranks = analytics.get("iv_ranks", {})
        if iv_ranks:
            for ticker, ir in iv_ranks.items():
                status = ir.get("status", "building_history")
                if status == "building_history":
                    st.markdown(f"<div style='font-size:0.7rem;color:#888;'>{ticker}: building history ({ir.get('current_iv', '\u2014')}%)</div>", unsafe_allow_html=True)
                else:
                    flag = ""
                    if ir.get("iv_rank") and ir["iv_rank"] >= 70:
                        flag = " RICH"
                    elif ir.get("iv_rank") and ir["iv_rank"] <= 30:
                        flag = " CHEAP"
                    st.markdown(f"<div style='font-size:0.7rem;color:#888;'>{ticker}: IV rank {ir.get('iv_rank', '\u2014')}%ile (curr {ir.get('current_iv', '\u2014'):.1f}%){flag}</div>", unsafe_allow_html=True)
        else:
            st.caption("No option IV data.")

st.markdown("---")
st.caption("Bloom Terminal \u2022 Reports conditions, tracks targets \u2022 Never trades")
