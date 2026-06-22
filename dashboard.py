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
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;500;600;700;800&family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');

html, body, .stApp {
    background: radial-gradient(ellipse at 20% 50%, #0a0a1a 0%, #050508 100%) !important;
    color: #e8e8e8;
    font-family: 'JetBrains Mono', 'SF Mono', 'Consolas', monospace;
}
.stApp::before {
    content: '';
    position: fixed; top: 0; left: 0; right: 0; bottom: 0;
    background: radial-gradient(ellipse 600px 400px at 80% 20%, rgba(0,200,83,0.03) 0%, transparent 70%);
    pointer-events: none;
    z-index: 0;
}
.block-container {
    padding: 1.2rem 2rem !important;
    max-width: 100% !important;
    position: relative;
    z-index: 1;
}
h1 {
    font-size: 1.5rem !important;
    color: #00c853 !important;
    font-family: 'JetBrains Mono', monospace !important;
    letter-spacing: -0.02em !important;
    text-shadow: 0 0 40px rgba(0,200,83,0.15);
    margin-bottom: 0.75rem !important;
}
h2 {
    font-size: 0.85rem !important;
    color: #e0e0e0 !important;
    font-weight: 600 !important;
    letter-spacing: 0.08em !important;
    text-transform: uppercase !important;
    border-bottom: 1px solid rgba(255,255,255,0.06);
    padding-bottom: 0.4rem;
    margin: 1rem 0 0.6rem 0 !important;
}
h3 {
    font-size: 0.75rem !important;
    color: #999 !important;
    font-weight: 400 !important;
    letter-spacing: 0.05em;
}
p, li, div, span, td, th {
    font-family: 'JetBrains Mono', 'SF Mono', 'Consolas', monospace !important;
}
a {
    color: #64b5f6 !important;
    transition: color 0.2s ease !important;
}
a:hover {
    color: #90caf9 !important;
    text-decoration: underline !important;
}

/* ── Glass card base ── */
.glass {
    background: rgba(255,255,255,0.02);
    backdrop-filter: blur(16px);
    -webkit-backdrop-filter: blur(16px);
    border: 1px solid rgba(255,255,255,0.06);
    border-radius: 10px;
    transition: all 0.25s cubic-bezier(0.32,0.72,0,1);
}
.glass:hover {
    border-color: rgba(255,255,255,0.12);
    background: rgba(255,255,255,0.035);
}

/* ── Status cards ── */
.status-card {
    background: rgba(255,255,255,0.02);
    backdrop-filter: blur(12px);
    -webkit-backdrop-filter: blur(12px);
    border: 1px solid rgba(255,255,255,0.06);
    border-radius: 10px;
    padding: 0.45rem 0.55rem;
    text-align: center;
    transition: all 0.25s cubic-bezier(0.32,0.72,0,1);
    position: relative;
    overflow: hidden;
}
.status-card::before {
    content: '';
    position: absolute; top: 0; left: 0; right: 0; height: 2px;
    border-radius: 10px 10px 0 0;
}
.status-card:hover {
    border-color: rgba(255,255,255,0.15);
    transform: translateY(-1px);
    box-shadow: 0 4px 20px rgba(0,0,0,0.3);
}

/* ── Alert boxes ── */
.alert-box {
    padding: 0.45rem 0.65rem;
    margin: 0.25rem 0;
    border-left: 3px solid;
    border-radius: 0 6px 6px 0;
    font-size: 0.7rem;
    backdrop-filter: blur(8px);
    transition: all 0.2s ease;
}
.alert-box:hover {
    transform: translateX(2px);
}
.alert-high {
    border-color: #ff5252;
    background: rgba(255,82,82,0.08);
    box-shadow: inset 3px 0 12px rgba(255,82,82,0.05);
}
.alert-warn {
    border-color: #ffd740;
    background: rgba(255,215,64,0.06);
    box-shadow: inset 3px 0 12px rgba(255,215,64,0.04);
}
.alert-info {
    border-color: #64b5f6;
    background: rgba(100,181,246,0.06);
    box-shadow: inset 3px 0 12px rgba(100,181,246,0.04);
}

/* ── News box ── */
.news-box {
    background: rgba(255,255,255,0.02);
    backdrop-filter: blur(8px);
    -webkit-backdrop-filter: blur(8px);
    border: 1px solid rgba(255,255,255,0.06);
    border-radius: 8px;
    padding: 0.6rem;
    margin: 0.35rem 0;
    font-size: 0.72rem;
    transition: all 0.2s ease;
}
.news-box:hover {
    border-color: rgba(255,255,255,0.12);
}

/* ── Macro box ── */
.macro-box {
    background: rgba(0,200,83,0.04);
    backdrop-filter: blur(12px);
    -webkit-backdrop-filter: blur(12px);
    border: 1px solid rgba(0,200,83,0.12);
    border-radius: 10px;
    padding: 0.6rem 0.8rem;
    text-align: center;
    transition: all 0.3s ease;
}
.macro-box:hover {
    border-color: rgba(0,200,83,0.25);
    box-shadow: 0 0 30px rgba(0,200,83,0.05);
}
.macro-score {
    font-size: 2rem;
    font-weight: 700;
    letter-spacing: -0.03em;
}

/* ── DTE pills ── */
.dte-pill {
    display: inline-block;
    padding: 0.1rem 0.5rem;
    border-radius: 6px;
    font-size: 0.62rem;
    font-weight: 700;
    line-height: 1.4;
}
.dte-urgent {
    background: linear-gradient(135deg, #ff5252, #ff1744);
    color: #fff;
    box-shadow: 0 0 12px rgba(255,82,82,0.3);
}
.dte-warn {
    background: linear-gradient(135deg, #ffd740, #ffab00);
    color: #1a1a1a;
    box-shadow: 0 0 12px rgba(255,215,64,0.2);
}
.dte-ok {
    background: rgba(255,255,255,0.06);
    color: #888;
}

/* ── Sentiment ── */
.sentiment-positive { color: #00c853; }
.sentiment-negative { color: #ff5252; }
.sentiment-neutral { color: #ffd740; }

/* ── Strike ladder ── */
.strike-hed {
    font-weight: 700;
    color: #ffd740;
    text-shadow: 0 0 20px rgba(255,215,64,0.15);
}
.strike-new { color: #00c853; }

/* ── Progress bars ── */
.prog-wrap { margin: 3px 0; }
.prog-label { font-size: 0.55rem; color: #666; margin-bottom: 1px; }
.prog-track { background: rgba(255,255,255,0.04); border-radius: 3px; height: 4px; overflow: hidden; }
.prog-fill {
    height: 100%;
    border-radius: 3px;
    transition: width 0.5s cubic-bezier(0.32,0.72,0,1);
    position: relative;
}
.prog-fill.target {
    background: linear-gradient(90deg, #ffd740, #00c853);
}
.prog-fill.stop {
    background: linear-gradient(90deg, #ffd740, #ff5252);
}

/* ── Buttons ── */
.stButton button {
    background: rgba(255,255,255,0.03) !important;
    border: 1px solid rgba(255,255,255,0.08) !important;
    border-radius: 8px !important;
    color: #ccc !important;
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 0.75rem !important;
    transition: all 0.25s cubic-bezier(0.32,0.72,0,1) !important;
    backdrop-filter: blur(8px);
}
.stButton button:hover {
    border-color: rgba(0,200,83,0.4) !important;
    background: rgba(0,200,83,0.06) !important;
    color: #00c853 !important;
    box-shadow: 0 0 24px rgba(0,200,83,0.08) !important;
    transform: translateY(-1px);
}
.stButton button:active {
    transform: translateY(0) scale(0.98);
}

/* ── Selectbox / Input ── */
.stSelectbox div[data-baseweb="select"] > div,
.stTextInput input {
    background: rgba(255,255,255,0.03) !important;
    border: 1px solid rgba(255,255,255,0.08) !important;
    border-radius: 6px !important;
    color: #e0e0e0 !important;
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 0.75rem !important;
    backdrop-filter: blur(8px);
    transition: border 0.2s ease;
}
.stSelectbox div[data-baseweb="select"] > div:hover,
.stTextInput input:hover {
    border-color: rgba(255,255,255,0.15) !important;
}
.stSelectbox div[data-baseweb="select"] > div:focus,
.stTextInput input:focus {
    border-color: rgba(0,200,83,0.3) !important;
    box-shadow: 0 0 16px rgba(0,200,83,0.04) !important;
}

/* ── Dataframe / metric styling ── */
[data-testid="stMetricValue"] {
    font-size: 1.1rem !important;
    font-weight: 600 !important;
}
[data-testid="stMetricLabel"] {
    font-size: 0.6rem !important;
    color: #666 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.08em !important;
}

/* ── Spinner ── */
.stSpinner > div {
    border-color: rgba(0,200,83,0.3) !important;
    border-top-color: #00c853 !important;
}

/* ── Expander ── */
.streamlit-expanderHeader {
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 0.75rem !important;
    background: rgba(255,255,255,0.02) !important;
    border-radius: 6px !important;
}

/* ── Caption ── */
.stCaption {
    color: #555 !important;
    font-size: 0.65rem !important;
}

/* ── Info/Error boxes ── */
.stAlert {
    backdrop-filter: blur(8px);
    border-radius: 8px !important;
}

/* ── Scrollbar ── */
::-webkit-scrollbar { width: 4px; height: 4px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.08); border-radius: 4px; }
::-webkit-scrollbar-thumb:hover { background: rgba(255,255,255,0.15); }

/* ── Table styling ── */
table { border-collapse: collapse; width: 100%; }
th { color: #555 !important; font-weight: 500 !important; font-size: 0.6rem !important; letter-spacing: 0.06em !important; text-transform: uppercase !important; }
tr { transition: background 0.2s ease; }
tr:hover { background: rgba(255,255,255,0.02); }
td { transition: color 0.2s ease; }

/* ── Regime analysis ── */
.regime-box {
    background: rgba(255,255,255,0.02);
    backdrop-filter: blur(12px);
    -webkit-backdrop-filter: blur(12px);
    border: 1px solid;
    border-radius: 10px;
    padding: 1rem 1.2rem;
    margin: 0.5rem 0;
    transition: all 0.3s ease;
}
.regime-box:hover {
    background: rgba(255,255,255,0.035);
}
.regime-stat {
    text-align: center;
}
.regime-stat-label {
    color: #666;
    font-size: 0.55rem;
    text-transform: uppercase;
    letter-spacing: 0.06em;
}
.regime-stat-value {
    color: #e0e0e0;
    font-size: 1.2rem;
    font-weight: 700;
}
.regime-timeline-item {
    border-left: 3px solid;
    padding: 0.2rem 0.6rem;
    margin: 0.15rem 0;
    font-size: 0.7rem;
    transition: all 0.2s ease;
    border-radius: 0 4px 4px 0;
}
.regime-timeline-item:hover {
    background: rgba(255,255,255,0.02);
}

/* ── Tab styling ── */
button[data-baseweb="tab"] {
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 0.7rem !important;
}
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

# ── header with nav button ──────────────────────────────────────
hcol1, hcol2, hcol3 = st.columns([1, 0.5, 1])
with hcol2:
    st.markdown(f"<h1 style='text-align:center;'>\U0001f33b BLOOM TERMINAL</h1>", unsafe_allow_html=True)
with hcol3:
    st.page_link("pages/2_Regime_Analysis.py", label="📊 REGIME ANALYSIS", icon=None)
st.markdown(f"<div style='text-align:center;color:#555;font-size:0.6rem;letter-spacing:0.06em;margin-bottom:0.5rem;'>{today}</div>", unsafe_allow_html=True)

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
        f"<div class='status-card'>"
        f"<div style='color:#666;font-size:0.55rem;text-transform:uppercase;letter-spacing:0.06em;'>{['NAV','P&L','P&L%','Pos','Alerts','Macro','\u0394','\u0398/d','\u03a5/pt'][i]}</div>"
        f"<div style='font-size:0.9rem;font-weight:700;color:#e0e0e0;'>{sv[i]}</div></div>", unsafe_allow_html=True)

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
                bars += f"<div class='prog-wrap'><div class='prog-label'>Target {pt:.0f}%</div><div class='prog-track'><div class='prog-fill target' style='width:{pt_clamped}%;'></div></div></div>"
            if ps is not None:
                ps_clamped = min(max(ps,0),100)
                bars += f"<div class='prog-wrap'><div class='prog-label'>Stop {ps:.0f}%</div><div class='prog-track'><div class='prog-fill stop' style='width:{ps_clamped}%;'></div></div></div>"

            rows_data.append({
                "name":f"<div title='{pid}'>{name}</div>", "type":type_str,
                "dte":dte_str, "entry":entry_str, "mark":mark_str,
                "value":val_str, "pnl$":pnl_d_str, "pnl%":pnl_p_str,
                "delta":delta_str, "\u03b8/d":td_str, "iv":iv_str,
                "bars":bars,
            })

        headers = ["Name","","DTE","Entry","Mark","Value","P&L $","P&L %","\u0394","\u0398/d","IV","Prog"]
        html = '<table style="width:100%;font-size:0.68rem;">'
        html += "<tr>"
        for h in headers:
            html += f"<th style='padding:0.3rem 0.4rem;text-align:left;'>{h}</th>"
        html += "</tr>"
        for r in rows_data:
            html += "<tr>"
            for k in headers:
                val = r.get(k,"")
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
                              paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                              font=dict(family="JetBrains Mono, monospace",size=10,color="#b0bec5"),
                              legend=dict(orientation="h",y=1.1,x=0,font=dict(size=9,color="#888")),
                              xaxis=dict(gridcolor="rgba(255,255,255,0.04)", zerolinecolor="rgba(255,255,255,0.06)", title_font=dict(size=10,color="#666")),
                              yaxis=dict(gridcolor="rgba(255,255,255,0.04)", zerolinecolor="rgba(255,255,255,0.06)", title_font=dict(size=10,color="#666")))
            st.plotly_chart(fig, use_container_width=True)

        # ── strike ladder ─────────────────────────────────
        st.markdown("## STRIKE LADDER")
        for v in vals:
            if v["asset_type"] != "option":
                continue
            ticker = v["ticker"]
            held_strike = v.get("option_strike")
            snapshot = q1("SELECT chain_json FROM snapshots WHERE ticker=? AND run_date=?", (ticker, today))
            if not snapshot:
                continue
            chain = json.loads(snapshot["chain_json"])
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
            st.markdown(f"<div style='font-size:0.72rem;color:#90caf9;margin:0.5rem 0 0.2rem;font-weight:600;letter-spacing:0.04em;'>{ticker} ${opt_type.upper()} {expiry}</div>", unsafe_allow_html=True)

            ladder_html = '<table style="width:100%;font-size:0.62rem;">'
            ladder_html += "<tr>"
            for hh in ["Strike","Bid","Ask","Last","IV","Vol","OI"]:
                ladder_html += f"<th style='padding:0.2rem 0.3rem;text-align:right;'>{hh}</th>"
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
                ladder_html += f"<tr class='{row_class}'>"
                for val in [strike_label, bid, ask, last, iv_l, vol, oi]:
                    ladder_html += f"<td style='padding:0.15rem 0.3rem;text-align:right;'>{val}</td>"
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
                                  paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                                  font=dict(family="JetBrains Mono, monospace",size=10,color="#b0bec5"), showlegend=False)
                fig.update_xaxes(gridcolor="rgba(255,255,255,0.04)"); fig.update_yaxes(gridcolor="rgba(255,255,255,0.04)")
                st.plotly_chart(fig, use_container_width=True)
            with col2:
                df2 = pd.DataFrame([{"Sector": s, "%": p} for s, p in sp.items()])
                fig2 = px.bar(df2, x="Sector", y="%", color="%",
                              color_continuous_scale="RdYlGn", text="%")
                fig2.update_layout(height=200, margin=dict(l=10,r=10,t=10,b=20),
                                   paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                                   font=dict(family="JetBrains Mono, monospace",size=10,color="#b0bec5"), showlegend=False)
                fig2.update_xaxes(gridcolor="rgba(255,255,255,0.04)"); fig2.update_yaxes(gridcolor="rgba(255,255,255,0.04)")
                st.plotly_chart(fig2, use_container_width=True)

        # ── news with clickable headlines ─────────────────
        if news:
            st.markdown("## NEWS ANALYSIS")
            for t, n in news.items():
                s = json.loads(n["analysis_json"]).get("sentiment", "neutral")
                an = json.loads(n["analysis_json"])
                hl = json.loads(n["headlines_json"]) if n.get("headlines_json") else []
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
                        headline_links += f"<div style='margin:0.1rem 0;'><a href='{link}' target='_blank' style='color:#64b5f6;text-decoration:none;font-size:0.65rem;transition:color 0.2s;'>{title[:90]}</a></div>"
                st.markdown(
                    f"<div class='news-box'><div class='news-header'>"
                    f"<strong>{t}</strong>{pr_flag} <span class='sentiment-{s}'>{icon} {s.upper()}</span>"
                    f"</div><div style='color:#b0bec5;margin-top:0.3rem;line-height:1.45;'>{an.get('summary','No summary')}</div>"
                    f"<div style='color:#555;font-size:0.62rem;margin-top:0.3rem;letter-spacing:0.03em;'>Drivers: {', '.join(an.get('key_drivers',['\u2014']))}</div>",
                    unsafe_allow_html=True)
                if headline_links:
                    st.markdown(
                        f"<div style='margin-top:0.35rem;padding-top:0.35rem;border-top:1px solid rgba(255,255,255,0.06);'>{headline_links}</div></div>",
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
            st.markdown(f"<div style='display:flex;justify-content:space-between;font-size:0.65rem;color:#888;padding:0.12rem 0;border-bottom:1px solid rgba(255,255,255,0.03);'><span>{k}</span><span>{v:.0f}</span></div>", unsafe_allow_html=True)

    # ── aggregate greeks ───────────────────────────────────
    st.markdown("## AGGREGATE GREEKS")
    items = [
        ("Net Delta (sh eq)", f"{agg.get('net_delta_share_eq',0):+,.0f}", "green" if agg.get('net_delta_share_eq',0)>0 else "red"),
        ("Theta/Day", f"${agg.get('total_theta_dollars',0):+,.2f}", "red" if (agg.get('total_theta_dollars',0) or 0) < 0 else "green"),
        ("Vega / IV pt", f"${agg.get('net_vega_per_iv_point',0):+,.2f}", ""),
    ]
    for label, val, color in items:
        st.markdown(
            f"<div style='display:flex;justify-content:space-between;font-size:0.68rem;padding:0.22rem 0;border-bottom:1px solid rgba(255,255,255,0.04);'>"
            f"<span style='color:#666;'>{label}</span><span style='color:{color};font-weight:600;'>{val}</span></div>",
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
                st.markdown(f"<div style='font-size:0.65rem;color:#666;padding:0.15rem 0;border-bottom:1px solid rgba(255,255,255,0.03);'>{t}: building history <span style='color:#888;'>({ir.get('current_iv','\u2014')}%)</span></div>", unsafe_allow_html=True)
            else:
                flag_txt = ""
                if ir.get("iv_rank") and ir["iv_rank"] >= 70: flag_txt = "<span style='color:#ff5252;font-weight:700;'> RICH</span>"
                elif ir.get("iv_rank") and ir["iv_rank"] <= 30: flag_txt = "<span style='color:#00c853;font-weight:700;'> CHEAP</span>"
                st.markdown(f"<div style='font-size:0.65rem;color:#666;padding:0.15rem 0;border-bottom:1px solid rgba(255,255,255,0.03);'>{t}: rank {ir.get('iv_rank','\u2014')}%ile <span style='color:#888;'>(curr {ir.get('current_iv','\u2014'):.1f}%)</span>{flag_txt}</div>", unsafe_allow_html=True)
    else:
        st.caption("No IV history yet.")

    # ── pipeline button always visible ─────────────────────
    st.markdown("---")
    if st.button("Run Pipeline"):
        run_pipeline()

st.markdown(
    "<div style='text-align:center;padding:0.5rem 0;'>"
    "<span style='color:#333;font-size:0.6rem;letter-spacing:0.08em;'>"
    "BLOOM TERMINAL \u2022 REPORTS CONDITIONS \u2022 TRACKS YOUR OWN TARGETS \u2022 NEVER RECOMMENDS TRADES"
    "</span></div>",
    unsafe_allow_html=True)
