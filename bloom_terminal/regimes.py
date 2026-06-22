import sys
import json
import math
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import requests
import yfinance as yf

sys.path.insert(0, str(Path(__file__).parent.parent))

SMA_WINDOWS = [20, 50, 200]


FOREX_SLASH_SYMBOLS = {"EURUSD", "GBPUSD", "USDJPY", "USDCAD", "USDCHF", "AUDUSD", "NZDUSD"}
CRYPTO_SLASH_SYMBOLS = {"BTCUSD", "ETHUSD", "SOLUSD", "XRPUSD", "ADAUSD", "DOGEUSD", "DOTUSD"}
COMMODITY_YAHOO = {
    "XAUUSD": "GC=F", "XAGUSD": "SI=F", "UKOIL": "BZ=F",
    "USOIL": "CL=F", "NATGAS": "NG=F", "COPPER": "HG=F",
}
INDEX_YAHOO = {
    "SPX": "^GSPC", "NDX": "^IXIC", "DJI": "^DJI",
    "RUT": "^RUT", "VIX": "^VIX",
}


def _yahoo_symbol(symbol: str) -> str:
    s = symbol.upper().replace("/", "").replace("-", "")
    if s in COMMODITY_YAHOO:
        return COMMODITY_YAHOO[s]
    if s in INDEX_YAHOO:
        return INDEX_YAHOO[s]
    if s in FOREX_SLASH_SYMBOLS:
        return s[:3] + "=" + s[3:] + "=X"
    return symbol


def fetch_data(
    symbol: str,
    start_date: str,
    end_date: str,
    source: str = "auto",
) -> pd.DataFrame:
    if source == "twelvedata":
        return _fetch_twelvedata(symbol, start_date, end_date, "demo")
    if source == "yfinance":
        return _fetch_yfinance(symbol, start_date, end_date)

    # auto: try TwelveData first (handles forex/crypto/indices natively), fallback yfinance
    try:
        return _fetch_twelvedata(symbol, start_date, end_date, "demo")
    except Exception:
        return _fetch_yfinance(_yahoo_symbol(symbol), start_date, end_date)


def _map_twelvedata_fields(data: dict, symbol: str) -> pd.DataFrame:
    values = data.get("values", [])
    if not values:
        raise ValueError(f"No data returned for {symbol}")
    rows = []
    for v in values:
        dt = datetime.strptime(v["datetime"].split("T")[0], "%Y-%m-%d").date()
        rows.append({
            "date": dt,
            "open": float(v["open"]),
            "high": float(v["high"]),
            "low": float(v["low"]),
            "close": float(v["close"]),
            "volume": float(v.get("volume", 0)),
        })
    df = pd.DataFrame(rows)
    df = df.sort_values("date").reset_index(drop=True)
    return df


def _fetch_yfinance(symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    try:
        tk = yf.Ticker(symbol)
        hist = tk.history(start=start_date, end=end_date)
        if hist.empty:
            raise ValueError(f"No yfinance data for {symbol}")
        df = hist.reset_index()
        date_col = df.columns[0]
        df = df.rename(columns={
            date_col: "date",
            "Open": "open", "High": "high",
            "Low": "low", "Close": "close", "Volume": "volume",
        })
        df["date"] = pd.to_datetime(df["date"]).dt.date
        return df[["date", "open", "high", "low", "close", "volume"]]
    except Exception as e:
        raise ValueError(f"yfinance error for {symbol}: {e}")


def _fetch_twelvedata(
    symbol: str,
    start_date: str,
    end_date: str,
    apikey: str = "demo",
) -> pd.DataFrame:
    sym = symbol.upper().replace("/", "")
    if sym in FOREX_SLASH_SYMBOLS:
        sym = sym[:3] + "/" + sym[3:]
    elif sym in CRYPTO_SLASH_SYMBOLS:
        sym = sym[:3] + "/" + sym[3:]

    url = "https://api.twelvedata.com/time_series"
    params = {
        "symbol": sym,
        "interval": "1day",
        "start_date": start_date,
        "end_date": end_date,
        "apikey": apikey,
        "format": "JSON",
    }
    resp = requests.get(url, params=params, timeout=30)
    data = resp.json()

    if data.get("status") == "error":
        raise ValueError(f"TwelveData API error: {data.get('message', 'unknown')}")

    values = data.get("values", [])
    if not values:
        raise ValueError(f"No data returned for {symbol}")

    rows = []
    for v in values:
        dt = datetime.strptime(v["datetime"].split("T")[0], "%Y-%m-%d").date()
        rows.append({
            "date": dt,
            "open": float(v["open"]),
            "high": float(v["high"]),
            "low": float(v["low"]),
            "close": float(v["close"]),
            "volume": float(v.get("volume", 0)),
        })

    df = pd.DataFrame(rows)
    df = df.sort_values("date").reset_index(drop=True)
    return df


def _sma(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window=window, min_periods=window).mean()


def _rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.rolling(window=period, min_periods=period).mean()
    avg_loss = loss.rolling(window=period, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, float("nan"))
    rsi = 100 - (100 / (1 + rs))
    return rsi


def _bb_width(series: pd.Series, window: int = 20, std_mult: float = 2.0) -> pd.Series:
    sma = series.rolling(window=window, min_periods=window).mean()
    std = series.rolling(window=window, min_periods=window).std()
    upper = sma + std_mult * std
    lower = sma - std_mult * std
    return (upper - lower) / sma * 100


def detect_regimes(df: pd.DataFrame) -> pd.DataFrame:
    n = len(df)
    if n < 20:
        df["regime"] = "INSUFFICIENT_DATA"
        return df

    close = df["close"]
    sma_windows = [w for w in SMA_WINDOWS if w <= n // 2]
    if not sma_windows:
        sma_windows = [max(5, n // 4)]

    for w in sma_windows:
        df[f"sma_{w}"] = _sma(close, w)
    rsi_period = min(14, max(5, n // 8))
    df["rsi_14"] = _rsi(close, rsi_period)
    bb_period = min(20, max(5, n // 6))
    df["bb_width"] = _bb_width(close, bb_period)

    vol_lookback = min(60, max(10, n // 3))
    df["volatility"] = close.pct_change().rolling(window=vol_lookback).std() * math.sqrt(252)

    min_required = max(rsi_period, bb_period, sma_windows[-1] if sma_windows else 10)
    sma_cols = sorted([c for c in df.columns if c.startswith("sma_")])

    conditions = []
    for i in range(len(df)):
        row = df.iloc[i]
        if i < min_required:
            conditions.append("INSUFFICIENT_DATA")
            continue

        rsi = row.get("rsi_14", 50)
        bbw = row.get("bb_width", 5)
        vol = row.get("volatility", 0.3)

        score = 0.0
        signals = 0

        # use available SMA columns for trend comparison
        if len(sma_cols) >= 2:
            short_col = sma_cols[0]
            long_col = sma_cols[-1]
            short_val = row.get(short_col)
            long_val = row.get(long_col)
            if short_val is not None and long_val is not None and long_val > 0:
                if short_val > long_val * 1.02:
                    score += 1.0
                elif short_val > long_val:
                    score += 0.5
                elif short_val < long_val * 0.98:
                    score -= 1.0
                elif short_val < long_val:
                    score -= 0.5
                else:
                    score += 0.0
                signals += 1

        if not pd.isna(bbw) and not df["bb_width"].isna().all():
            try:
                bb_thresh = bbw / df["bb_width"].median()
                if bb_thresh > 1.5:
                    score *= 0.5
                signals += 1
            except (ZeroDivisionError, TypeError):
                pass

        if not pd.isna(rsi):
            if rsi > 70:
                score -= 0.3
            elif rsi > 60:
                score += 0.2
            elif rsi < 30:
                score -= 0.5
            elif rsi < 40:
                score += 0.1
            signals += 1

        if signals > 0:
            score /= signals

        if score > 0.4:
            conditions.append("BULL")
        elif score > 0.1:
            conditions.append("RECOVERING")
        elif score < -0.4:
            conditions.append("BEAR")
        elif score < -0.1:
            conditions.append("CORRECTING")
        else:
            if not pd.isna(bbw) and not df["bb_width"].isna().all():
                try:
                    if bbw > df["bb_width"].quantile(0.8):
                        conditions.append("VOLATILE")
                    else:
                        conditions.append("RANGE_BOUND")
                except (ZeroDivisionError, TypeError):
                    conditions.append("RANGE_BOUND")
            else:
                conditions.append("RANGE_BOUND")

    df["regime"] = conditions
    return df


def _bb_vol(bbw: float, all_bbw: pd.Series) -> float:
    try:
        return bbw / all_bbw.median()
    except (ZeroDivisionError, TypeError):
        return 1.0


def score_confidence(df: pd.DataFrame) -> dict:
    regimes = df[df["regime"] != "INSUFFICIENT_DATA"]["regime"]
    if regimes.empty:
        return {"confidence": 0, "stability": 0, "regimes_detected": 0, "current_regime": "UNKNOWN"}

    current = regimes.iloc[-1]
    n = len(regimes)
    current_count = 0
    for val in reversed(regimes.values):
        if val == current:
            current_count += 1
        else:
            break

    stability = current_count

    close = df["close"]
    sma_cols = [c for c in df.columns if c.startswith("sma_")]
    sma_cols.sort()

    if len(sma_cols) >= 2:
        short_sma = sma_cols[0]
        long_sma = sma_cols[-1]
        short_val = df[short_sma].iloc[-1]
        long_val = df[long_sma].iloc[-1]

        if current in ("BULL", "RECOVERING") and long_val > 0:
            strength = (short_val / long_val - 1) * 100
        elif current in ("BEAR", "CORRECTING") and long_val > 0:
            strength = (1 - long_val / (short_val * 1.5)) * 100 if short_val > 0 else 0
        else:
            strength = 5.0 - abs(close.pct_change().rolling(min(20, len(close)//3)).std().iloc[-1] * 100)
    else:
        strength = 5.0

    confidence = min(100, max(10, abs(strength) * 8 + stability * 3))

    distinct = regimes.unique()
    return {
        "confidence": round(min(confidence, 100), 1),
        "stability": int(stability),
        "regimes_detected": int(len(distinct)),
        "current_regime": current,
    }


def compute_regime_report(df: pd.DataFrame) -> dict:
    df_reg = detect_regimes(df)
    info = score_confidence(df_reg)
    info["ticker"] = df.get("symbol", "N/A") if hasattr(df, "get") else "N/A"
    info["start_date"] = str(df["date"].iloc[0]) if not df.empty else ""
    info["end_date"] = str(df["date"].iloc[-1]) if not df.empty else ""

    segments = []
    current_seg = None
    seg_start = None
    for i in range(len(df_reg)):
        r = df_reg.iloc[i]["regime"]
        d = df_reg.iloc[i]["date"]
        if current_seg is None:
            current_seg = r
            seg_start = d
        elif r != current_seg:
            segments.append({"regime": current_seg, "from": str(seg_start), "to": str(df_reg.iloc[i - 1]["date"])})
            current_seg = r
            seg_start = d
    if current_seg is not None:
        segments.append({"regime": current_seg, "from": str(seg_start), "to": str(df_reg.iloc[-1]["date"])})

    info["segments"] = segments
    info["data"] = df_reg
    return info


def build_regime_chart(report: dict):
    df = report["data"]
    colors = {
        "BULL": "#00c853",
        "BEAR": "#ff5252",
        "RANGE_BOUND": "#ffd740",
        "VOLATILE": "#ff9100",
        "RECOVERING": "#64b5f6",
        "CORRECTING": "#ff4081",
        "INSUFFICIENT_DATA": "#444444",
    }

    traces = []
    for regime_name, color in colors.items():
        mask = df["regime"] == regime_name
        if not mask.any():
            continue
        subset = df[mask]
        traces.append(go.Scatter(
            x=subset["date"], y=subset["close"],
            mode="markers", name=regime_name,
            marker=dict(color=color, size=4, symbol="circle"),
            hovertemplate="%{x|%Y-%m-%d}<br>$%{y:.2f}<br>" + regime_name,
        ))

    traces.append(go.Scatter(
        x=df["date"], y=df["close"],
        mode="lines", name="Close",
        line=dict(color="#555", width=1),
        showlegend=False,
        hoverinfo="skip",
    ))

    sma_cols = sorted([c for c in df.columns if c.startswith("sma_")])
    sma_labels = {c: f"SMA({c.split('_')[1]})" for c in sma_cols}
    sma_palette = ["#90caf9", "#ffd740", "#ce93d8"]
    for ci, col in enumerate(sma_cols):
        traces.append(go.Scatter(
            x=df["date"], y=df[col],
            mode="lines", name=sma_labels.get(col, col),
            line=dict(color=sma_palette[ci % len(sma_palette)], width=1, dash="dash"),
        ))

    layout = go.Layout(
        height=400,
        margin=dict(l=40, r=20, t=30, b=40),
        paper_bgcolor="#0a0a0a",
        plot_bgcolor="#0a0a0a",
        font=dict(family="monospace", size=10, color="#e0e0e0"),
        legend=dict(orientation="h", y=1.12, x=0, font=dict(size=9)),
        xaxis=dict(
            title="", gridcolor="#1a1a1a", zerolinecolor="#222",
            rangeslider=dict(visible=True, thickness=0.08, bgcolor="#111"),
        ),
        yaxis=dict(title="Price ($)", gridcolor="#1a1a1a", zerolinecolor="#222"),
        hovermode="x unified",
    )

    fig = go.Figure(data=traces, layout=layout)
    return fig
