import sys
import json
import shutil
import subprocess
from datetime import date, datetime, timedelta
from pathlib import Path

import yfinance as yf

sys.path.insert(0, str(Path(__file__).parent.parent))

from bloom_terminal.db import BloomDB
from config import load_config, OPENCODE_NEWS_MODEL, NEWS_LOOKBACK_DAYS


def _opencode_path() -> str:
    for name in ("opencode", "opencode.cmd", "opencode.ps1"):
        resolved = shutil.which(name)
        if resolved:
            return resolved
    npm_dir = Path.home() / "AppData" / "Roaming" / "npm"
    for name in ("opencode.cmd", "opencode", "opencode.ps1"):
        candidate = npm_dir / name
        if candidate.exists():
            return str(candidate)
    return "opencode.cmd"


OPENCODE_CMD = _opencode_path()


def pull_vix_data() -> dict:
    try:
        vix = yf.Ticker("^VIX")
        vix_hist = vix.history(period="1y")
        if vix_hist.empty:
            vix_hist = vix.history(period="6mo")
        vix_current = float(vix_hist["Close"].iloc[-1]) if not vix_hist.empty else 20.0
        vix_pct = float(vix_hist["Close"].rank(pct=True).iloc[-1]) * 100 if len(vix_hist) > 20 else 50.0
    except Exception:
        vix_current = 20.0
        vix_pct = 50.0

    try:
        vix3m = yf.Ticker("^VIX3M")
        vix3m_hist = vix3m.history(period="1mo")
        vix3m_val = float(vix3m_hist["Close"].iloc[-1]) if not vix3m_hist.empty else vix_current
        vix_term = ((vix3m_val - vix_current) / vix_current) * 100
    except Exception:
        vix_term = 0.0

    try:
        spy = yf.Ticker("SPY")
        spy_hist = spy.history(period="1y")
        spy_200ma = spy_hist["Close"].rolling(200).mean().iloc[-1] if len(spy_hist) >= 200 else spy_hist["Close"].iloc[-1]
        spy_current = spy_hist["Close"].iloc[-1]
        breadth = (spy_current / spy_200ma - 1) * 100
    except Exception:
        breadth = 0.0

    try:
        hyg = yf.Ticker("HYG")
        tlt = yf.Ticker("TLT")
        hyg_hist = hyg.history(period="1mo")
        tlt_hist = tlt.history(period="1mo")
        if not hyg_hist.empty and not tlt_hist.empty:
            hyg_yield = float(hyg_hist["Close"].iloc[-1])
            tlt_price = float(tlt_hist["Close"].iloc[-1])
            credit = ((tlt_price - hyg_yield) / hyg_yield) * 100
        else:
            credit = 0.0
    except Exception:
        credit = 0.0

    return {
        "vix_current": round(vix_current, 2),
        "vix_percentile": round(vix_pct, 1),
        "vix_term_structure": round(vix_term, 2),
        "breadth_pct": round(breadth, 2),
        "credit_spread": round(credit, 2),
    }


def score_macro(data: dict, weights: dict) -> dict:
    vix = data["vix_current"]
    vix_pct = data["vix_percentile"]
    vix_term = data["vix_term_structure"]
    breadth = data["breadth_pct"]
    credit = data["credit_spread"]

    vix_level_score = max(0, 100 - vix * 2)
    vix_pct_score = max(0, 100 - vix_pct)
    vix_term_score = 50.0
    if vix_term < -5:
        vix_term_score = 80
    elif vix_term < 0:
        vix_term_score = 60
    elif vix_term > 10:
        vix_term_score = 20

    breadth_score = max(0, min(100, 50 + breadth * 5))
    credit_score = max(0, min(100, 50 + credit * 2))

    total = (
        weights.get("vix_level", 0.25) * vix_level_score
        + weights.get("vix_percentile", 0.20) * vix_pct_score
        + weights.get("vix_term", 0.20) * vix_term_score
        + weights.get("breadth", 0.20) * breadth_score
        + weights.get("credit", 0.15) * credit_score
    )

    return {
        "score": round(total, 1),
        "components": {
            "vix_level": round(vix_level_score, 1),
            "vix_percentile": round(vix_pct_score, 1),
            "vix_term": round(vix_term_score, 1),
            "breadth": round(breadth_score, 1),
            "credit": round(credit_score, 1),
        },
        "raw_data": data,
    }


def _call_opencode(prompt: str, model: str) -> str | None:
    try:
        result = subprocess.run(
            [OPENCODE_CMD, "run", "--model", model, "--pure"],
            input=prompt, capture_output=True, encoding="utf-8", timeout=120,
        )
        out = result.stdout.strip()
        lines = [l for l in out.split("\n") if l.strip() and not l.strip().startswith(">")]
        return "\n".join(lines) if lines else None
    except subprocess.TimeoutExpired:
        print("  [DEBUG] subprocess timed out after 120s", file=sys.stderr)
        return None
    except Exception as e:
        print(f"  [DEBUG] subprocess error: {e}", file=sys.stderr)
        return None


def _get_content(item: dict) -> dict:
    return item.get("content") or item

def _extract_title(item: dict) -> str:
    return _get_content(item).get("title", "")

def _extract_pubdate(item: dict) -> datetime | None:
    c = _get_content(item)
    pub = c.get("pubDate") or c.get("providerPublishTime")
    if not pub:
        return None
    if isinstance(pub, (int, float)):
        return datetime.fromtimestamp(pub)
    try:
        from datetime import timezone
        return datetime.fromisoformat(pub.replace("Z", "+00:00"))
    except Exception:
        return None


def analyze_news_opencode(ticker_headlines: dict[str, list[dict]], model: str) -> dict[str, dict]:
    if not ticker_headlines:
        return {}

    sections = []
    for ticker, headlines in ticker_headlines.items():
        if not headlines:
            continue
        titles = [_extract_title(h) for h in headlines[:6]]
        titles = [t for t in titles if t]
        if titles:
            sections.append(f"[{ticker}]\n" + "\n".join(f"- {t}" for t in titles))

    if not sections:
        return {}

    prompt = (
        "You are a financial analyst. Analyze these headlines per ticker.\n\n"
        + "\n\n".join(sections)
        + '\n\nReturn JSON where keys are the plain ticker symbols (e.g. "AAPL", not "[AAPL]"). '
        + 'Values: {"summary": str, "sentiment": "positive|neutral|negative", "key_drivers": [str], "position_relevant": bool}. '
        + "Return ONLY a JSON object. No markdown."
    )

    raw = _call_opencode(prompt, model)
    if not raw:
        return {}

    json_str = raw.strip()
    if "```" in json_str:
        for block in json_str.split("```"):
            block = block.strip()
            if block.startswith("json"):
                block = block[4:].strip()
            if block.startswith("{") and block.endswith("}"):
                json_str = block
                break
            if block.startswith("{") and "}" in block:
                import re as _re
                m = _re.search(r"\{.*\}", block, _re.DOTALL)
                if m:
                    json_str = m.group()
                    break

    try:
        result = json.loads(json_str)
        if isinstance(result, dict):
            return result
    except json.JSONDecodeError:
        import re as _re
        m = _re.search(r"\{.*\}", json_str, _re.DOTALL)
        if m:
            try:
                result = json.loads(m.group())
                if isinstance(result, dict):
                    return result
            except json.JSONDecodeError:
                pass

    return {}


def run_layer3(
    positions: list[dict],
    db: BloomDB,
    config: dict,
    asof: str | None = None,
    opencode_model: str | None = None,
    skip_macro: bool = False,
):
    run_date = asof or date.today().isoformat()

    macro_result = None
    if not skip_macro:
        macro_data = pull_vix_data()
        weights = config.get("macro_weights", load_config().get("MACRO_WEIGHTS", {}))
        macro_result = score_macro(macro_data, weights)
        db.save_macro_score(run_date, macro_result)

    news_analyses = {}
    tickers = set(p["ticker"] for p in positions)
    news_lookback = config.get("news_lookback_days", NEWS_LOOKBACK_DAYS)
    from datetime import timezone
    cutoff = datetime.now(timezone.utc) - timedelta(days=news_lookback)

    uncached = {}
    for ticker in tickers:
        cached = db.get_news_analysis(ticker, run_date)
        if cached:
            news_analyses[ticker] = cached
            continue

        try:
            tk = yf.Ticker(ticker)
            news = tk.news or []
        except Exception:
            news = []

        recent = [
            n for n in news
            if (pd := _extract_pubdate(n)) and pd > cutoff
        ]

        if recent:
            uncached[ticker] = recent
        else:
            analysis = {"ticker": ticker, "summary": "No recent news.", "sentiment": "neutral", "key_drivers": [], "position_relevant": False}
            db.save_news_analysis(ticker, run_date, analysis, [])
            news_analyses[ticker] = analysis

    if uncached and opencode_model:
        batch_result = analyze_news_opencode(uncached, opencode_model)
        for ticker, headlines in uncached.items():
            analysis = batch_result.get(ticker) or batch_result.get(f"[{ticker}]", {})
            if not analysis or "summary" not in analysis:
                analysis = {
                    "ticker": ticker,
                    "summary": "Analysis unavailable.",
                    "sentiment": "neutral",
                    "key_drivers": [],
                    "position_relevant": False,
                }
            analysis["ticker"] = ticker
            db.save_news_analysis(ticker, run_date, analysis, headlines)
            news_analyses[ticker] = analysis

    return {"run_date": run_date, "macro": macro_result, "news": news_analyses}
