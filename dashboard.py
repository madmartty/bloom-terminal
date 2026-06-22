import sys
import json
import sqlite3
import traceback
from datetime import date, datetime, timedelta
from pathlib import Path

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px

st.set_page_config(page_title="Bloom Terminal", page_icon="\U0001f33b",
                   layout="wide", initial_sidebar_state="collapsed")

ROOT = Path(__file__).resolve().parent
DB_FILE = str(ROOT / "bloom_terminal.db")

sqlite3.connect(DB_FILE).executescript("""
    CREATE TABLE IF NOT EXISTS valuations (id INTEGER PRIMARY KEY AUTOINCREMENT, run_date TEXT, position_id TEXT, ticker TEXT, asset_type TEXT, mark REAL, current_value REAL, cost_basis REAL, pnl_dollars REAL, pnl_pct REAL, dte INTEGER, delta REAL, gamma REAL, theta REAL, vega REAL, iv REAL, progress_target REAL, progress_stop REAL, option_expiry TEXT, option_strike REAL);
    CREATE TABLE IF NOT EXISTS portfolio_analytics (id INTEGER PRIMARY KEY AUTOINCREMENT, run_date TEXT UNIQUE, analytics_json TEXT);
    CREATE TABLE IF NOT EXISTS macro_scores (id INTEGER PRIMARY KEY AUTOINCREMENT, run_date TEXT UNIQUE, macro_json TEXT);
    CREATE TABLE IF NOT EXISTS news_cache (id INTEGER PRIMARY KEY AUTOINCREMENT, ticker TEXT, run_date TEXT, analysis_json TEXT, headlines_json TEXT, UNIQUE(ticker, run_date));
    CREATE TABLE IF NOT EXISTS alerts (id INTEGER PRIMARY KEY AUTOINCREMENT, run_date TEXT, alert_type TEXT, severity TEXT, ticker TEXT, position_id TEXT, message TEXT, detail TEXT);
    CREATE TABLE IF NOT EXISTS snapshots (id INTEGER PRIMARY KEY AUTOINCREMENT, ticker TEXT, run_date TEXT, chain_json TEXT, UNIQUE(ticker, run_date));
""").close()

st.markdown("""<style>
html, body, .stApp { background-color:#0a0a0a; color:#e0e0e0; font-family:'JetBrains Mono','SF Mono','Consolas',monospace; }
.block-container { padding:1.5rem 2rem !important; max-width:100% !important; }
h1 { font-size:1.5rem !important; color:#00c853 !important; font-family:'JetBrains Mono',monospace !important; }
h2 { font-size:1.1rem !important; color:#90caf9 !important; margin-top:0 !important; }
h3 { font-size:0.9rem !important; color:#b0bec5 !important; }
p,li,div,span { font-family:'JetBrains Mono','SF Mono','Consolas',monospace !important; }
.alert-box { padding:0.4rem 0.6rem; margin:0.2rem 0; border-left:3px solid; font-size:0.75rem; }
.alert-high { border-color:#ff5252; background:rgba(255,82,82,0.08); }
.alert-warn { border-color:#ffd740; background:rgba(255,215,64,0.08); }
.alert-info { border-color:#64b5f6; background:rgba(100,181,246,0.08); }
.news-box { background:#111; border:1px solid #2a2a2a; border-radius:4px; padding:0.6rem; margin:0.3rem 0; font-size:0.75rem; }
.macro-box { background:#0d1b0d; border:1px solid #1a3a1a; border-radius:4px; padding:0.5rem 0.75rem; text-align:center; }
.macro-score { font-size:1.8rem; font-weight:700; }
.dte-pill { display:inline-block; padding:0.08rem 0.45rem; border-radius:8px; font-size:0.65rem; font-weight:700; line-height:1.3; }
.dte-urgent { background:#ff5252; color:#000; }
.dte-warn { background:#ffd740; color:#000; }
.dte-ok { background:#2a2a2a; color:#999; }
.news-header { display:flex; justify-content:space-between; align-items:center; }
.sentiment-positive { color:#00c853; }
.sentiment-negative { color:#ff5252; }
.sentiment-neutral { color:#ffd740; }
.strike-ladder { font-size:0.65rem; }
.strike-hed { font-weight:700; color:#ffd740; }
.strike-new { color:#00c853; }
.prog-wrap { margin:2px 0; }
.prog-label { font-size:0.6rem; color:#888; }
.prog-fill { height:3px; border-radius:2px; transition:width 0.3s; }
.stButton button { background:#1a1a1a !important; border:1px solid #333 !important; color:#e0e0e0 !important; font-family:'JetBrains Mono',monospace !important; }
.stButton button:hover { border-color:#00c853 !important; }
</style>""", unsafe_allow_html=True)

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

@st.dialog("Pipeline Status")
def run_pipeline():
    with st.spinner("Running pipeline ..."):
        try:
            from config import load_config, load_positions, OPENCODE_NEWS_MODEL
            import shutil
            sys.path.insert(0, str(ROOT))
            from bloom_terminal.db import BloomDB
            from bloom_terminal.layer1_data import run_layer1
            from bloom_terminal.layer2_portfolio import run_layer2
            from bloom_terminal.layer3_macro import run_layer3
            from bloom_terminal.layer4_alerts import run_layer4
            db = BloomDB(DB_FILE)
            cfg = load_config()
            pos = load_positions()
            opencode_avail = (shutil.which("opencode") or shutil.which("opencode.cmd")) is not None
            run_layer1(pos, db, cfg, asof=today)
            run_layer2(db, cfg, asof=today)
            run_layer3(pos, db, cfg, asof=today,
                       opencode_model=OPENCODE_NEWS_MODEL if opencode_avail else None)
            run_layer4(db, cfg, pos, asof=today)
            st.success("Pipeline complete!")
            st.rerun()
        except Exception as e:
            st.error(f"Pipeline failed: {e}\n{traceback.format_exc()}")

# ── load data ──────────────────────────────────────────────────
vals = q("SELECT * FROM valuations ORDER BY ticker, id")
macro = q1("SELECT * FROM macro_scores WHERE run_date=?", (today,))
analytics = q1("SELECT * FROM portfolio_analytics WHERE run_date=?", (today,))
alerts = q("SELECT * FROM alerts WHERE run_date=? ORDER BY CASE severity WHEN 'high' THEN 0 WHEN 'warn' THEN 1 ELSE 2 END, id", (today,))
agg = json.loads(analytics["analytics_json"]).get("aggregate_greeks", {}) if analytics else {}
alloc = json.loads(analytics["analytics_json"]).get("allocation", {}) if analytics else {}
concentration = json.loads(analytics["analytics_json"]).get("concentration_flags", []) if analytics else []
iv_ranks = json.loads(analytics["analytics_json"]).get("iv_ranks", {}) if analytics else {}
dte_flags = json.loads(analytics["analytics_json"]).get("dte_flags", []) if analytics else {}

from config import load_positions
positions = load_positions()
tickers = set(p["ticker"] for p in positions)
news = {}
for t in tickers:
    n = q1("SELECT * FROM news_cache WHERE ticker=? AND run_date=?", (t, today))
    if n:
        news[t] = n

nav = sum(v.get("current_value", 0) for v in vals) if vals else 0
cost = sum(v.get("cost_basis", 0) for v in vals) if vals else 0
pnl = nav - cost
pnl_pct = (pnl / cost * 100) if cost else 0
ms = json.loads(macro["macro_json"]).get("score", "\u2014") if macro else "\u2014"

# ── status strip ───────────────────────────────────────────────
st.markdown(f"<h1>\U0001f33b BLOOM TERMINAL  <span style='color:#666;font-size:0.8rem;font-weight:400;'>| {today}</span></h1>", unsafe_allow_html=True)

cols = st.columns(9)
sv = [f"${nav:,.0f}" if nav else "\u2014",
      f"${pnl:+,.0f}",
      f"{pnl_pct:+.1f}%" if cost else "\u2014",
      str(len(vals)),
      str(len(alerts)),
      str(ms),
      f"{agg.get('net_delta_share_eq',0):+,.0f}",
      f"${agg.get('total_theta_dollars',0):+,.2f}",
      f"${agg.get('net_vega_per_iv_point',0):+,.2f}"]
for i, c in enumerate(cols):
    c.markdown(
        f"<div style='background:#111;border:1px solid #2a2a2a;border-radius:4px;padding:0.35rem 0.5rem;text-align:center;'>"
        f"<div style='color:#666;font-size:0.55rem;text-transform:uppercase;'>{['NAV','P&L','P&L%','Pos','Alerts','Macro','\u0394','\u0398/d','\u03a5/pt'][i]}</div>"
        f"<div style='font-size:0.9rem;font-weight:700;color:#e0e0e0;'>{sv[i]}</div></div>", unsafe_allow_html=True)

st.markdown("---")

# ── left column: positions, theta decay, strike ladder, news ──
left, right = st.columns([2.2, 1])

with left:
    if not vals:
        st.info("No data yet. Click Run Pipeline to fetch today's data.")
        if st.button("Run Pipeline"):
            run_pipeline()
    else:
        # ── positions grid ────────────────────────────────────
        st.markdown("## POSITIONS")
        rows_data = []
        for v in vals:
            pid = v.get("position_id", "")
            pos_obj = None
            for p in positions:
                if p.get("id", "") == pid or (p["ticker"] == v["ticker"] and p["asset_type"] == v["asset_type"] and p.get("strike") == v.get("option_strike")):
                    pos_obj = p; break
            if not pos_obj:
                for p in positions:
                    if p["ticker"] == v["ticker"] and p["asset_type"] == v["asset_type"]:
                        pos_obj = p; break
            strike = pos_obj.get("strike","") if pos_obj else ""
            opt_type = pos_obj.get("option_type","").upper() if pos_obj and pos_obj.get("option_type") else ""
            expiry = pos_obj.get("expiry","") if pos_obj else ""
            if v["asset_type"] == "option":
                dte = v.get("dte", 0)
                dte_class = "dte-urgent" if dte and dte <= 14 else ("dte-warn" if dte and dte <= 45 else "dte-ok")
                dte_str = f"<span class='dte-pill {dte_class}'>{dte}</span>" if dte else "\u2014"
            else:
                dte_str = "\u2014"
            pnl_d = v.get("pnl_dollars", 0)
            pnl_c = "green" if pnl_d >= 0 else "red"
            pct_val = v.get("pnl_pct", 0)
            delta = v.get("delta")
            td = v.get("theta")
            iv_val = v.get("iv")
            mark = v.get("mark", 0)
            entry = pos_obj.get("entry_price", 0) if pos_obj else 0
            ct = pos_obj.get("contracts", 0) if pos_obj else 0
            val = v.get("current_value", 0)

            # theta per day in dollars for this position
            theta_dollar = (td * ct * 100) if td is not None and v["asset_type"]=="option" else None
            td_str = f"${theta_dollar:+,.2f}" if theta_dollar is not None else "\u2014"
            iv_str = f"{iv_val:.1f}%" if iv_val else "\u2014" if v["asset_type"]=="option" else "\u2014"
            delta_str = f"{delta:.2f}" if delta is not None else "\u2014"
            entry_str = f"${entry:.2f}"
            mark_str = f"${mark:.2f}"
            val_str = f"${val:,.0f}"
            pnl_d_str = f"<span style='color:{pnl_c}'>{pnl_d:+,.0f}</span>"
            pnl_p_str = f"<span style='color:{pnl_c}'>{pct_val:+.1f}%</span>"
            name = f"{v['ticker']} {opt_type} ${strike}" if v["asset_type"]=="option" else v["ticker"]
            type_str = {"call":"C","put":"P"}.get(pos_obj.get("option_type","").lower(),"EQ") if pos_obj else "EQ"

            # progress bars
            pt = v.get("progress_target")
            ps = v.get("progress_stop")
            bars = ""
            if pt is not None:
                pt_clamped = min(max(pt,0),100)
                pcol = "#00c853" if pt>=100 else "#ffd740"
                bars += f"<div class='prog-wrap'><div class='prog-label'>Target {pt:.0f}%</div><div style='background:#1a1a1a;border-radius:2px;'><div class='prog-fill' style='width:{pt_clamped}%;background:{pcol};'></div></div></div>"
            if ps is not None:
                ps_clamped = min(max(ps,0),100)
                scol = "#ff5252" if ps>=100 else "#ffd740"
                bars += f"<div class='prog-wrap'><div class='prog-label'>Stop {ps:.0f}%</div><div style='background:#1a1a1a;border-radius:2px;'><div class='prog-fill' style='width:{ps_clamped}%;background:{scol};'></div></div></div>"

            rows_data.append({
                "name":f"<div title='{pid}'>{name}</div>", "type":type_str,
                "dte":dte_str, "entry":entry_str, "mark":mark_str,
                "value":val_str, "pnl$":pnl_d_str, "pnl%":pnl_p_str,
                "delta":delta_str, "\u03b8/d":td_str, "iv":iv_str,
                "bars":bars,
            })

        headers = ["Name","","DTE","Entry","Mark","Value","P&L $","P&L %","\u0394","\u0398/d","IV","Prog"]
        html = '<table style="width:100%;border-collapse:collapse;font-size:0.68rem;">'
        html += "<tr style='border-bottom:1px solid #333;'>"
        for h in headers:
            html += f"<th style='padding:0.3rem 0.4rem;text-align:left;color:#666;font-weight:400;'>{h}</th>"
        html += "</tr>"
        for r in rows_data:
            html += "<tr style='border-bottom:1px solid #151515;'>"
            for k in headers:
                val = r.get(k,"")
                bw = "0" if k != "Prog" else "60" if k in r else ""
                html += f"<td style='padding:0.2rem 0.4rem;'>{val}</td>"
            html += "</tr>"
        html += "</table>"
        st.markdown(html, unsafe_allow_html=True)

        # ── theta decay chart ──────────────────────────────
        st.markdown("## THETA DECAY")
        theta_data = []
        for v in vals:
            if v["asset_type"] == "option" and v.get("theta") and v.get("dte"):
                pos_obj = None
                for p in positions:
                    if p["ticker"]==v["ticker"] and p["asset_type"]=="option" and p.get("strike")==v.get("option_strike"):
                        pos_obj=p; break
                ct = pos_obj.get("contracts",0) if pos_obj else 0
                decay = []
                for day_offset in range(0, v["dte"]+1, 5):
                    from scipy.stats import norm as _norm
                    import math as _math
                    dte_local = v["dte"] - day_offset
                    if dte_local <= 0:
                        break
                    t = dte_local / 365.0
                    rfr = 0.045
                    S = v.get("mark", 100) * 5  # rough proxy
                    K = v.get("option_strike", 100) or 100
                    iv = (v.get("iv", 30) or 30) / 100.0
                    opt_type = (pos_obj.get("option_type","call") if pos_obj else "call").lower()
                    try:
                        d1 = (_math.log(S/K) + (rfr + 0.5*iv*iv)*t) / (iv*_math.sqrt(t)) if S>0 and K>0 and t>0 else 0
                        d2 = d1 - iv*_math.sqrt(t) if t > 0 else 0
                        theta_decay = -S * _norm.pdf(d1) * iv / (2*_math.sqrt(t)) - rfr*K*_math.exp(-rfr*t)*_norm.cdf(-d1 if opt_type=="put" else d2)
                        theta_decay /= 365.0
                    except:
                        theta_decay = 0
                    decay.append(round(theta_decay * ct * 100, 2))
                if decay:
                    theta_data.append({"name": f"{v['ticker']} {'C' if opt_type and opt_type.lower()=='call' else 'P'} ${v.get('option_strike','')}", "days": list(range(0, len(decay)*5, 5))[:len(decay)], "theta": decay})

        if theta_data:
            fig = go.Figure()
            for td_item in theta_data:
                fig.add_trace(go.Scatter(x=td_item["days"], y=td_item["theta"], mode="lines+markers",
                                         name=td_item["name"], line=dict(width=1.5), marker=dict(size=3)))
            fig.update_layout(height=250, margin=dict(l=40,r=10,t=10,b=30),
                              paper_bgcolor="#0a0a0a", plot_bgcolor="#0a0a0a",
                              font=dict(family="monospace",size=10,color="#e0e0e0"),
                              legend=dict(orientation="h",y=1.1,x=0,font=dict(size=9)),
                              xaxis_title="Days Forward", yaxis_title="\u0398/day ($)")
            fig.update_xaxes(gridcolor="#1a1a1a", zerolinecolor="#222")
            fig.update_yaxes(gridcolor="#1a1a1a", zerolinecolor="#222")
            st.plotly_chart(fig, use_container_width=True)

        # ── strike ladder ─────────────────────────────────
        st.markdown("## STRIKE LADDER")
        # for each option position, query snapshot and show +/-6 strikes
        for v in vals:
            if v["asset_type"] != "option":
                continue
            ticker = v["ticker"]
            held_strike = v.get("option_strike")
            snapshot = q1("SELECT chain_json FROM snapshots WHERE ticker=? AND run_date=?", (ticker, today))
            if not snapshot:
                continue
            chain = json.loads(snapshot["chain_json"])
            # find matching expiry
            pos_obj = None
            for p in positions:
                if p["ticker"]==ticker and p["asset_type"]=="option" and p.get("strike")==held_strike:
                    pos_obj=p; break
            expiry = pos_obj.get("expiry","") if pos_obj else ""
            opt_type = (pos_obj.get("option_type","call") if pos_obj else "call").lower()
            expiry_calls = [c for c in chain if c.get("expiry")==expiry and c.get("option_type")=="call"]
            expiry_puts = [c for c in chain if c.get("expiry")==expiry and c.get("option_type")=="put"]
            legs = expiry_calls if opt_type == "call" else expiry_puts
            if not legs:
                continue

            legs.sort(key=lambda x: x.get("strike",0))
            held_idx = None
            for i, l in enumerate(legs):
                if abs(l.get("strike",0) - held_strike) < 0.01:
                    held_idx = i; break
            if held_idx is None:
                continue

            start = max(0, held_idx-6)
            end = min(len(legs), held_idx+7)
            band = legs[start:end]
            st.markdown(f"<div style='font-size:0.75rem;color:#90caf9;margin:0.5rem 0 0.2rem;'><strong>{ticker} ${opt_type.upper()} {expiry}</strong></div>", unsafe_allow_html=True)

            ladder_html = '<table style="width:100%;border-collapse:collapse;font-size:0.62rem;">'
            ladder_html += "<tr style='border-bottom:1px solid #333;color:#666;'>"
            for hh in ["Strike","Bid","Ask","Last","IV","Vol","OI"]:
                ladder_html += f"<th style='padding:0.2rem 0.3rem;text-align:right;font-weight:400;'>{hh}</th>"
            ladder_html += "</tr>"
            for l in band:
                is_held = abs(l.get("strike",0)-held_strike) < 0.01
                row_class = "strike-hed" if is_held else ""
                strike_label = f"${l.get('strike',0):.0f}"
                bid = f"{l.get('bid',0):.2f}" if l.get("bid") else "\u2014"
                ask = f"{l.get('ask',0):.2f}" if l.get("ask") else "\u2014"
                last = f"{l.get('last',0):.2f}" if l.get("last") else "\u2014"
                iv_l = f"{l.get('impliedVolatility',0)*100:.1f}%" if l.get("impliedVolatility") else "\u2014"
                vol = f"{l.get('volume',0):,}" if l.get("volume") else "\u2014"
                oi = f"{l.get('openInterest',0):,}" if l.get("openInterest") else "\u2014"
                ladder_html += f"<tr class='{row_class}' style='border-bottom:1px solid #151515;'>"
                ladder_html += f"<td style='padding:0.15rem 0.3rem;text-align:right;'>{strike_label}</td>"
                ladder_html += f"<td style='padding:0.15rem 0.3rem;text-align:right;'>{bid}</td>"
                ladder_html += f"<td style='padding:0.15rem 0.3rem;text-align:right;'>{ask}</td>"
                ladder_html += f"<td style='padding:0.15rem 0.3rem;text-align:right;'>{last}</td>"
                ladder_html += f"<td style='padding:0.15rem 0.3rem;text-align:right;'>{iv_l}</td>"
                ladder_html += f"<td style='padding:0.15rem 0.3rem;text-align:right;'>{vol}</td>"
                ladder_html += f"<td style='padding:0.15rem 0.3rem;text-align:right;'>{oi}</td>"
                ladder_html += "</tr>"
            ladder_html += "</table>"
            st.markdown(ladder_html, unsafe_allow_html=True)

        # ── allocation bars ────────────────────────────────
        tp = alloc.get("by_ticker", {})
        sp = alloc.get("by_sector", {})
        if tp:
            st.markdown("## ALLOCATION")
            col1, col2 = st.columns(2)
            with col1:
                df = pd.DataFrame([{"Ticker": t, "%": p} for t, p in tp.items()])
                fig = px.bar(df, x="Ticker", y="%", color="%",
                             color_continuous_scale="RdYlGn", text="%")
                fig.update_layout(height=200, margin=dict(l=10,r=10,t=10,b=20),
                                  paper_bgcolor="#0a0a0a", plot_bgcolor="#0a0a0a",
                                  font=dict(family="monospace",size=10,color="#e0e0e0"), showlegend=False)
                fig.update_xaxes(gridcolor="#1a1a1a"); fig.update_yaxes(gridcolor="#1a1a1a")
                st.plotly_chart(fig, use_container_width=True)
            with col2:
                df2 = pd.DataFrame([{"Sector": s, "%": p} for s, p in sp.items()])
                fig2 = px.bar(df2, x="Sector", y="%", color="%",
                              color_continuous_scale="RdYlGn", text="%")
                fig2.update_layout(height=200, margin=dict(l=10,r=10,t=10,b=20),
                                   paper_bgcolor="#0a0a0a", plot_bgcolor="#0a0a0a",
                                   font=dict(family="monospace",size=10,color="#e0e0e0"), showlegend=False)
                fig2.update_xaxes(gridcolor="#1a1a1a"); fig2.update_yaxes(gridcolor="#1a1a1a")
                st.plotly_chart(fig2, use_container_width=True)

        # ── news with clickable headlines ─────────────────
        if news:
            st.markdown("## NEWS ANALYSIS")
            for t, n in news.items():
                s = json.loads(n["analysis_json"]).get("sentiment", "neutral")
                an = json.loads(n["analysis_json"])
                hl = json.loads(n["headlines_json"]) if n.get("headlines_json") else []
                sc = "#00c853" if s=="positive" else "#ff5252" if s=="negative" else "#ffd740"
                icon = "\u25cf"
                pr_flag = ""
                if an.get("position_relevant"):
                    pr_flag = "<span style='color:#ff5252;font-size:0.6rem;margin-left:0.5rem;'>\u26a0 POSITION RELEVANT</span>"
                headline_links = ""
                for h in hl[:5]:
                    try:
                        hcontent = json.loads(h) if isinstance(h, str) else h
                    except:
                        hcontent = h if isinstance(h, dict) else {"title":str(h)[:80]}
                    title = hcontent.get("title","")
                    link = hcontent.get("link","")
                    if link and title:
                        headline_links += f"<div style='margin:0.1rem 0;'><a href='{link}' target='_blank' style='color:#64b5f6;text-decoration:none;font-size:0.65rem;'>{title[:90]}</a></div>"
                st.markdown(
                    f"<div class='news-box'><div class='news-header'>"
                    f"<strong>{t}</strong>{pr_flag} <span class='sentiment-{s}'>{icon} {s.upper()}</span>"
                    f"</div><div style='color:#b0bec5;margin-top:0.3rem;'>{an.get('summary','No summary')}</div>"
                    f"<div style='color:#666;font-size:0.65rem;margin-top:0.3rem;'>Drivers: {', '.join(an.get('key_drivers',['\u2014']))}</div>",
                    unsafe_allow_html=True)
                if headline_links:
                    st.markdown(
                        f"<div style='margin-top:0.3rem;padding-top:0.3rem;border-top:1px solid #222;'>{headline_links}</div></div>",
                        unsafe_allow_html=True)
                else:
                    st.markdown("</div>", unsafe_allow_html=True)

with right:
    # ── alerts ──────────────────────────────────────────────
    st.markdown("## ALERTS")
    if alerts:
        for a in alerts:
            sev = a["severity"]
            icon = {"high": "\u26a0", "warn": "\u26a1", "info": "\u2139\ufe0f"}.get(sev, "\u2139\ufe0f")
            st.markdown(
                f"<div class='alert-box alert-{sev}'><strong>{icon} {a['message']}</strong>"
                f"<br><span style='color:#888;font-size:0.65rem;'>{a.get('detail','')}</span></div>",
                unsafe_allow_html=True)
    else:
        st.caption("No alerts for today.")

    # ── concentration flags ────────────────────────────────
    if concentration:
        st.markdown("## CONCENTRATION")
        for cf in concentration:
            st.markdown(f"<div class='alert-box alert-warn'>{cf['message']}</div>", unsafe_allow_html=True)

    # ── macro gate ─────────────────────────────────────────
    st.markdown("## MACRO GATE")
    if macro:
        mj = json.loads(macro["macro_json"])
        sc = mj.get("score", 0)
        grade = "good" if sc >= 60 else ("ok" if sc >= 35 else "bad")
        c = "#00c853" if grade=="good" else "#ffd740" if grade=="ok" else "#ff5252"
        st.markdown(
            f"<div class='macro-box'><div class='macro-score' style='color:{c}'>{sc}"
            f"<div style='color:#666;font-size:0.7rem;'>/ 100</div>"
            f"<div style='margin-top:0.5rem;font-size:0.7rem;color:#b0bec5;'>VIX: {mj.get('raw_data',{}).get('vix_current','\u2014')}</div></div>",
            unsafe_allow_html=True)
        for k, v in mj.get("components",{}).items():
            st.markdown(f"<div style='display:flex;justify-content:space-between;font-size:0.65rem;color:#888;padding:0.1rem 0;'><span>{k}</span><span>{v:.0f}</span></div>", unsafe_allow_html=True)

    # ── aggregate greeks ───────────────────────────────────
    st.markdown("## AGGREGATE GREEKS")
    items = [
        ("Net Delta (sh eq)", f"{agg.get('net_delta_share_eq',0):+,.0f}", "green" if agg.get('net_delta_share_eq',0)>0 else "red"),
        ("Theta/Day", f"${agg.get('total_theta_dollars',0):+,.2f}", "red" if (agg.get('total_theta_dollars',0) or 0) < 0 else "green"),
        ("Vega / IV pt", f"${agg.get('net_vega_per_iv_point',0):+,.2f}", ""),
    ]
    for label, val, color in items:
        st.markdown(
            f"<div style='display:flex;justify-content:space-between;font-size:0.7rem;padding:0.2rem 0;border-bottom:1px solid #1a1a1a;'>"
            f"<span style='color:#666;'>{label}</span><span style='color:{color};'>{val}</span></div>",
            unsafe_allow_html=True)

    # ── DTE warnings ───────────────────────────────────────
    st.markdown("## DTE WARNINGS")
    if dte_flags:
        for f in dte_flags:
            st.markdown(f"<div class='alert-box alert-warn'>{f['message']}</div>", unsafe_allow_html=True)
    else:
        st.caption("No positions approaching expiry.")

    # ── IV environment ─────────────────────────────────────
    st.markdown("## IV ENVIRONMENT")
    if iv_ranks:
        for t, ir in iv_ranks.items():
            status = ir.get("status", "building_history")
            if status == "building_history":
                st.markdown(f"<div style='font-size:0.65rem;color:#888;padding:0.1rem 0;'>{t}: building history ({ir.get('current_iv','\u2014')}%)</div>", unsafe_allow_html=True)
            else:
                flag_txt = ""
                if ir.get("iv_rank") and ir["iv_rank"] >= 70: flag_txt = "<span style='color:#ff5252;'> RICH</span>"
                elif ir.get("iv_rank") and ir["iv_rank"] <= 30: flag_txt = "<span style='color:#00c853;'> CHEAP</span>"
                st.markdown(f"<div style='font-size:0.65rem;color:#888;padding:0.1rem 0;'>{t}: rank {ir.get('iv_rank','\u2014')}%ile (curr {ir.get('current_iv','\u2014'):.1f}%){flag_txt}</div>", unsafe_allow_html=True)
    else:
        st.caption("No IV history yet.")

    # ── pipeline button always visible ─────────────────────
    st.markdown("---")
    if st.button("Run Pipeline"):
        run_pipeline()

# ── regime analysis (full width) ───────────────────────────────
st.markdown("---")
st.markdown("## REGIME ANALYSIS")
st.caption("Detect market regimes (Bull / Bear / Range-Bound / Volatile) using TwelveData price data")

regime_ticker = st.text_input("Ticker", value="AAPL", key="regime_ticker", label_visibility="collapsed")
col_a, col_b, col_c, _ = st.columns([2, 2, 2, 6])
with col_a:
    regime_start = st.text_input("Start Date", value="2026-01-01", key="regime_start")
with col_b:
    regime_end = st.text_input("End Date", value=today, key="regime_end")
with col_c:
    data_source = st.selectbox("Data Source", options=["yfinance", "twelvedata"], key="regime_source")

if st.button("Run Regime Analysis", use_container_width=True):
    with st.spinner(f"Fetching {regime_ticker.upper()} ..."):
        try:
            from bloom_terminal.regimes import fetch_data, compute_regime_report, build_regime_chart
            df = fetch_data(regime_ticker, regime_start, regime_end, source=data_source)
            report = compute_regime_report(df)
            fig = build_regime_chart(report)

            regime_colors = {
                "BULL": "#00c853", "BEAR": "#ff5252", "RANGE_BOUND": "#ffd740",
                "VOLATILE": "#ff9100", "RECOVERING": "#64b5f6", "CORRECTING": "#ff4081",
                "INSUFFICIENT_DATA": "#444", "UNKNOWN": "#888",
            }
            rc = regime_colors.get(report["current_regime"], "#888")

            st.markdown(
                f"<div style='background:#111;border:1px solid {rc};border-radius:6px;padding:1rem 1.2rem;margin:0.5rem 0;'>"
                f"<div style='display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:0.5rem;'>"
                f"<div style='font-size:1.1rem;font-weight:700;color:#e0e0e0;'>{regime_ticker.upper()} \u00b7 {regime_start} \u2192 {regime_end}</div>"
                f"<div style='display:flex;gap:1.5rem;flex-wrap:wrap;'>"
                f"<div style='text-align:center;'><div style='color:#666;font-size:0.55rem;text-transform:uppercase;'>Current Regime</div>"
                f"<div style='color:{rc};font-size:1.2rem;font-weight:700;'>{report['current_regime']}</div></div>"
                f"<div style='text-align:center;'><div style='color:#666;font-size:0.55rem;text-transform:uppercase;'>Confidence</div>"
                f"<div style='color:#e0e0e0;font-size:1.2rem;font-weight:700;'>{report['confidence']:.0f}%</div></div>"
                f"<div style='text-align:center;'><div style='color:#666;font-size:0.55rem;text-transform:uppercase;'>Stability</div>"
                f"<div style='color:#e0e0e0;font-size:1.2rem;font-weight:700;'>{report['stability']}d</div></div>"
                f"<div style='text-align:center;'><div style='color:#666;font-size:0.55rem;text-transform:uppercase;'>Regimes Detected</div>"
                f"<div style='color:#e0e0e0;font-size:1.2rem;font-weight:700;'>{report['regimes_detected']}</div></div>"
                f"</div></div>"
                f"<div style='color:#888;font-size:0.65rem;margin-top:0.5rem;'>{regime_ticker.upper()} \u00b7 {report['segments'][0]['from'] if report['segments'] else regime_start} | CURRENT REGIME | CONFIDENCE | STABILITY | REGIMES DETECTED</div>"
                f"</div>",
                unsafe_allow_html=True,
            )

            st.plotly_chart(fig, use_container_width=True)

            # regime timeline
            st.markdown("### Regime Timeline")
            for s in report["segments"]:
                sc = regime_colors.get(s["regime"], "#888")
                st.markdown(
                    f"<div style='border-left:3px solid {sc};padding:0.2rem 0.6rem;margin:0.15rem 0;font-size:0.7rem;'>"
                    f"<strong style='color:{sc};'>{s['regime']:20s}</strong>  "
                    f"<span style='color:#888;'>{s['from']} \u2192 {s['to']}</span></div>",
                    unsafe_allow_html=True,
                )

        except Exception as e:
            st.error(f"Regime analysis failed: {e}")

st.markdown("---")
st.caption("Bloom Terminal \u2022 Reports conditions, tracks your own targets \u2022 Never recommends trades")
