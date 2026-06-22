import sys, json, sqlite3, traceback
from datetime import date
from pathlib import Path

import streamlit as st

st.set_page_config(page_title="Regime Analysis | Bloom Terminal", page_icon="📊",
                   layout="wide", initial_sidebar_state="collapsed")

ROOT = Path(__file__).resolve().parent.parent
DB_FILE = str(ROOT / "bloom_terminal.db")

today = date.today().isoformat()

st.markdown("""<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;500;600;700;800&display=swap');
html, body, .stApp {
    background: radial-gradient(ellipse at 20% 50%, #0a0a1a 0%, #050508 100%) !important;
    color: #e8e8e8;
    font-family: 'JetBrains Mono', 'SF Mono', 'Consolas', monospace;
}
.stApp::before {
    content: '';
    position: fixed; top: 0; left: 0; right: 0; bottom: 0;
    background: radial-gradient(ellipse 600px 400px at 80% 20%, rgba(0,200,83,0.03) 0%, transparent 70%);
    pointer-events: none; z-index: 0;
}
.block-container { padding: 1.2rem 2rem !important; max-width: 100% !important; position: relative; z-index: 1; }
h1 { font-size: 1.5rem !important; color: #00c853 !important; font-family: 'JetBrains Mono', monospace !important; text-shadow: 0 0 40px rgba(0,200,83,0.15); }
h2 { font-size: 0.85rem !important; color: #e0e0e0 !important; font-weight: 600 !important; letter-spacing: 0.08em !important; text-transform: uppercase !important; border-bottom: 1px solid rgba(255,255,255,0.06); padding-bottom: 0.4rem; }
.regime-box {
    background: rgba(255,255,255,0.02); backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px);
    border: 1px solid; border-radius: 10px; padding: 1rem 1.2rem; margin: 0.5rem 0;
    transition: all 0.3s ease;
}
.regime-box:hover { background: rgba(255,255,255,0.035); }
.regime-stat { text-align: center; }
.regime-stat-label { color: #666; font-size: 0.55rem; text-transform: uppercase; letter-spacing: 0.06em; }
.regime-stat-value { color: #e0e0e0; font-size: 1.2rem; font-weight: 700; }
.regime-timeline-item {
    border-left: 3px solid; padding: 0.2rem 0.6rem; margin: 0.15rem 0; font-size: 0.7rem;
    transition: all 0.2s ease; border-radius: 0 4px 4px 0;
}
.regime-timeline-item:hover { background: rgba(255,255,255,0.02); }
.stButton button {
    background: rgba(255,255,255,0.03) !important; border: 1px solid rgba(255,255,255,0.08) !important;
    border-radius: 8px !important; color: #ccc !important; font-family: 'JetBrains Mono', monospace !important;
    transition: all 0.25s ease !important;
}
.stButton button:hover {
    border-color: rgba(0,200,83,0.4) !important; background: rgba(0,200,83,0.06) !important;
    color: #00c853 !important; box-shadow: 0 0 24px rgba(0,200,83,0.08) !important;
}
.stSelectbox div[data-baseweb="select"] > div,
.stTextInput input {
    background: rgba(255,255,255,0.03) !important; border: 1px solid rgba(255,255,255,0.08) !important;
    border-radius: 6px !important; color: #e0e0e0 !important; font-family: 'JetBrains Mono', monospace !important;
}
::-webkit-scrollbar { width: 4px; height: 4px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.08); border-radius: 4px; }
</style>""", unsafe_allow_html=True)

col1, col2, col3 = st.columns([1, 0.5, 1])
with col2:
    st.markdown(f"<h1 style='text-align:center;'>📊 REGIME ANALYSIS</h1>", unsafe_allow_html=True)
with col1:
    st.page_link("dashboard.py", label="🌻 BLOOM TERMINAL", icon=None)
st.markdown(f"<div style='text-align:center;color:#555;font-size:0.6rem;letter-spacing:0.06em;margin-bottom:0.5rem;'>{today}</div>", unsafe_allow_html=True)

st.caption("Detect market regimes (Bull / Bear / Range-Bound / Volatile) using price data")

regime_ticker = st.text_input("Ticker", value="AAPL", key="regime_ticker", label_visibility="collapsed")
col_a, col_b, col_c, _ = st.columns([2, 2, 2, 6])
with col_a:
    regime_start = st.text_input("Start Date", value="2026-01-01", key="regime_start")
with col_b:
    regime_end = st.text_input("End Date", value=today, key="regime_end")
with col_c:
    data_source = st.selectbox("Data Source", options=["auto", "yfinance", "twelvedata"], key="regime_source")

if st.button("Run Regime Analysis", use_container_width=True):
    with st.spinner(f"Fetching {regime_ticker.upper()} ..."):
        try:
            from bloom_terminal.regimes import fetch_data, compute_regime_report, build_regime_chart
            df = fetch_data(regime_ticker, regime_start, regime_end, source=data_source)
            report = compute_regime_report(df)
            fig = build_regime_chart(report)
            fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                              font=dict(family="JetBrains Mono, monospace",size=9,color="#b0bec5"),
                              legend=dict(font=dict(size=9,color="#888")))
            fig.update_xaxes(gridcolor="rgba(255,255,255,0.04)", zerolinecolor="rgba(255,255,255,0.06)")
            fig.update_yaxes(gridcolor="rgba(255,255,255,0.04)", zerolinecolor="rgba(255,255,255,0.06)")

            regime_colors = {
                "BULL": "#00c853", "BEAR": "#ff5252", "RANGE_BOUND": "#ffd740",
                "VOLATILE": "#ff9100", "RECOVERING": "#64b5f6", "CORRECTING": "#ff4081",
                "INSUFFICIENT_DATA": "#444", "UNKNOWN": "#888",
            }
            rc = regime_colors.get(report["current_regime"], "#888")

            st.markdown(
                f"<div class='regime-box' style='border-color:{rc};'>"
                f"<div style='display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:0.5rem;'>"
                f"<div style='font-size:1.1rem;font-weight:700;color:#e0e0e0;letter-spacing:-0.02em;'>{regime_ticker.upper()} · {regime_start} → {regime_end}</div>"
                f"<div style='display:flex;gap:1.5rem;flex-wrap:wrap;'>"
                f"<div class='regime-stat'><div class='regime-stat-label'>Current Regime</div>"
                f"<div style='color:{rc};font-size:1.2rem;font-weight:700;'>{report['current_regime']}</div></div>"
                f"<div class='regime-stat'><div class='regime-stat-label'>Confidence</div>"
                f"<div class='regime-stat-value'>{report['confidence']:.0f}%</div></div>"
                f"<div class='regime-stat'><div class='regime-stat-label'>Stability</div>"
                f"<div class='regime-stat-value'>{report['stability']}d</div></div>"
                f"<div class='regime-stat'><div class='regime-stat-label'>Regimes</div>"
                f"<div class='regime-stat-value'>{report['regimes_detected']}</div></div>"
                f"</div></div>"
                f"<div style='color:#555;font-size:0.6rem;margin-top:0.5rem;letter-spacing:0.04em;'>{regime_ticker.upper()} · {report['segments'][0]['from'] if report['segments'] else regime_start} | CURRENT REGIME | CONFIDENCE | STABILITY | REGIMES DETECTED</div>"
                f"</div>",
                unsafe_allow_html=True,
            )

            st.plotly_chart(fig, use_container_width=True)

            st.markdown("<h3 style='margin-top:0.5rem;'>Regime Timeline</h3>", unsafe_allow_html=True)
            for s in report["segments"]:
                sc = regime_colors.get(s["regime"], "#888")
                st.markdown(
                    f"<div class='regime-timeline-item' style='border-color:{sc};'>"
                    f"<strong style='color:{sc};'>{s['regime']:20s}</strong>  "
                    f"<span style='color:#888;'>{s['from']} → {s['to']}</span></div>",
                    unsafe_allow_html=True,
                )

        except Exception as e:
            st.error(f"Regime analysis failed: {e}")

st.markdown(
    "<div style='text-align:center;padding:0.5rem 0;'>"
    "<span style='color:#333;font-size:0.6rem;letter-spacing:0.08em;'>"
    "BLOOM TERMINAL · REPORTS CONDITIONS · TRACKS YOUR OWN TARGETS · NEVER RECOMMENDS TRADES"
    "</span></div>",
    unsafe_allow_html=True)
