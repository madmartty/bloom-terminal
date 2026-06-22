import sys
import traceback
from pathlib import Path

import streamlit as st

st.set_page_config(page_title="Bloom Terminal", page_icon="\U0001f33b",
                   layout="wide", initial_sidebar_state="collapsed")

ROOT = Path(__file__).resolve().parent if "__file__" in dir() else Path.cwd()

st.markdown("""<style>
html, body, .stApp { background-color:#0a0a0a; color:#e0e0e0; font-family:monospace; }
.block-container { padding:1.5rem 2rem !important; }
h1 { color:#00c853 !important; font-size:1.5rem !important; }
</style>""", unsafe_allow_html=True)

try:
    import json, sqlite3
    from datetime import date
    import pandas as pd
    import plotly.express as px
    from config import DB_PATH, load_positions

    DB_FILE = str(ROOT / "bloom_terminal.db")
    today = date.today().isoformat()

    def q(sql, params=()):
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(sql, params).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def q1(sql, params=()):
        rows = q(sql, params)
        return rows[0] if rows else None

    vals = q("SELECT * FROM valuations")
    macro = q1("SELECT * FROM macro_scores WHERE run_date=?", (today,))
    analytics = q1("SELECT * FROM portfolio_analytics WHERE run_date=?", (today,))
    alerts = q("SELECT * FROM alerts WHERE run_date=? ORDER BY CASE severity WHEN 'high' THEN 0 WHEN 'warn' THEN 1 ELSE 2 END, id", (today,))

    tickers = set(p["ticker"] for p in load_positions())
    news = {}
    for t in tickers:
        n = q1("SELECT * FROM news_cache WHERE ticker=? AND run_date=?", (t, today))
        if n:
            news[t] = n

    nav = sum(v.get("current_value", 0) for v in vals) if vals else 0
    cost = sum(v.get("cost_basis", 0) for v in vals) if vals else 0
    pnl = nav - cost
    pnl_pct = (pnl / cost * 100) if cost else 0
    agg = (analytics or {}).get("aggregate_greeks", {})
    ms = (macro or {}).get("score", "\u2014") if macro else "\u2014"

    st.markdown(f"<h1>\U0001f33b BLOOM TERMINAL  <span style='color:#666;font-size:0.8rem;font-weight:400;'>| {today}</span></h1>", unsafe_allow_html=True)

    cols = st.columns(8)
    svals = [f"${nav:,.0f}" if nav else "\u2014", f"${pnl:+,.0f}", f"{pnl_pct:+.1f}%" if cost else "\u2014",
             str(len(vals)), str(len(alerts)), str(ms),
             f"{agg.get('net_delta_share_eq',0):+,.0f}", f"${agg.get('total_theta_dollars',0):+,.0f}"]
    for i, c in enumerate(cols):
        c.markdown(f"<div style='background:#111;border:1px solid #2a2a2a;border-radius:4px;padding:0.4rem;text-align:center;'><div style='color:#666;font-size:0.6rem;'>{['NAV','P&L','P&L%','Pos','Alerts','Macro','\u0394','\u0398/d'][i]}</div><div style='font-size:1rem;font-weight:700;'>{svals[i]}</div></div>", unsafe_allow_html=True)

    st.markdown("---")
    left, right = st.columns([2, 1])

    with left:
        st.markdown("## POSITIONS")
        if vals:
            h = ["Name", "Type", "Mark", "Value", "P&L $", "P&L %", "\u0394", "IV"]
            html = '<table style="width:100%;border-collapse:collapse;font-size:0.75rem;">'
            html += "<tr style='border-bottom:1px solid #333;'>"
            for x in h:
                html += f"<th style='padding:0.3rem;text-align:left;color:#666;font-weight:400;'>{x}</th>"
            html += "</tr>"
            for v in vals:
                pnld = v.get("pnl_dollars", 0)
                pc = "green" if pnld >= 0 else "red"
                html += "<tr style='border-bottom:1px solid #1a1a1a;'>"
                html += f"<td style='padding:0.3rem;'>{v['ticker']}</td>"
                html += f"<td style='padding:0.3rem;'>{v['asset_type'][0].upper()}</td>"
                html += f"<td style='padding:0.3rem;'>${v.get('mark',0):.2f}</td>"
                html += f"<td style='padding:0.3rem;'>${v.get('current_value',0):,.0f}</td>"
                html += f"<td style='padding:0.3rem;color:{pc}'>{pnld:+,.0f}</td>"
                html += f"<td style='padding:0.3rem;color:{pc}'>{v.get('pnl_pct',0):+.1f}%</td>"
                html += f"<td style='padding:0.3rem;'>{v.get('delta','\u2014')}</td>"
                html += f"<td style='padding:0.3rem;'>{v.get('iv','\u2014')}</td>"
                html += "</tr>"
            html += "</table>"
            st.markdown(html, unsafe_allow_html=True)

            alloc = (analytics or {}).get("allocation", {})
            tp = alloc.get("by_ticker", {})
            if tp:
                df = pd.DataFrame([{"Ticker": t, "%": p} for t, p in tp.items()])
                fig = px.bar(df, x="Ticker", y="%", color="%", color_continuous_scale="RdYlGn", text="%")
                fig.update_layout(height=250, margin=dict(l=10,r=10,t=10,b=20),
                                  paper_bgcolor="#0a0a0a", plot_bgcolor="#0a0a0a",
                                  font=dict(family="monospace",size=10,color="#e0e0e0"), showlegend=False)
                st.plotly_chart(fig)

            if news:
                st.markdown("### News")
                for t, n in news.items():
                    s = n.get("sentiment", "neutral")
                    st.markdown(
                        f"<div style='background:#111;border:1px solid #2a2a2a;border-radius:4px;padding:0.5rem;margin:0.3rem 0;font-size:0.75rem;'>"
                        f"<strong>{t}</strong> <span style='color:#{'#00c853' if s=='positive' else '#ff5252' if s=='negative' else '#ffd740'}'>\U0001f7e2 {s.upper()}</span>"
                        f"<div style='color:#b0bec5;'>{n.get('summary','')[:200]}</div>"
                        f"</div>", unsafe_allow_html=True)

        else:
            st.info("Run the pipeline locally: `python runner.py`")

    with right:
        st.markdown("## ALERTS")
        if alerts:
            for a in alerts:
                sev = a["severity"]
                icon = {"high": "\U0001f534", "warn": "\U0001f7e1"}.get(sev, "\u2139\ufe0f")
                st.markdown(
                    f"<div style='padding:0.4rem;margin:0.2rem 0;border-left:3px solid {'#ff5252' if sev=='high' else '#ffd740'};"
                    f"font-size:0.75rem;background:rgba(255,82,82,0.08);'><strong>{icon} {a['message']}</strong>"
                    f"<br><span style='color:#888;font-size:0.65rem;'>{a.get('detail','')}</span></div>",
                    unsafe_allow_html=True)
        else:
            st.caption("No alerts.")

        st.markdown("## MACRO")
        if macro:
            sc = macro.get("score", 0)
            c = "#00c853" if sc >= 60 else "#ffd740" if sc >= 35 else "#ff5252"
            st.markdown(f"<div style='text-align:center;font-size:1.8rem;font-weight:700;color:{c}'>{sc}<div style='font-size:0.7rem;color:#666;'>/ 100</div></div>", unsafe_allow_html=True)
            comp = macro.get("components", {})
            for k, v in comp.items():
                st.markdown(f"<div style='display:flex;justify-content:space-between;font-size:0.7rem;color:#888;'><span>{k}</span><span>{v:.0f}</span></div>", unsafe_allow_html=True)

        st.markdown("## GREEKS")
        if agg:
            for label, key, unit in [("Net Delta", "net_delta_share_eq", "sh"), ("Theta/Day", "total_theta_dollars", "$"), ("Vega/IV", "net_vega_per_iv_point", "$")]:
                val = agg.get(key, 0)
                st.markdown(
                    f"<div style='display:flex;justify-content:space-between;font-size:0.75rem;padding:0.2rem 0;border-bottom:1px solid #1a1a1a;'>"
                    f"<span style='color:#666;'>{label}</span>"
                    f"<span>{unit}{val:+,.2f}</span></div>", unsafe_allow_html=True)

    st.markdown("---")
    st.caption("Bloom Terminal \u2022 Reports conditions, never trades")

except Exception as e:
    st.error(f"Startup error: {e}")
    st.code(traceback.format_exc())
