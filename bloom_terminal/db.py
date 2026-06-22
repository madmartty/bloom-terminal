import os
import sys
import sqlite3
import json
from datetime import datetime, date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


class BloomDB:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _conn(self):
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_schema(self):
        with self._conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticker TEXT NOT NULL,
                    run_date TEXT NOT NULL,
                    chain_json TEXT NOT NULL,
                    created_at TEXT DEFAULT (datetime('now')),
                    UNIQUE(ticker, run_date)
                );

                CREATE TABLE IF NOT EXISTS valuations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_date TEXT NOT NULL,
                    position_id TEXT NOT NULL,
                    ticker TEXT NOT NULL,
                    asset_type TEXT NOT NULL,
                    mark REAL,
                    current_value REAL,
                    cost_basis REAL,
                    pnl_dollars REAL,
                    pnl_pct REAL,
                    dte INTEGER,
                    delta REAL,
                    gamma REAL,
                    theta REAL,
                    vega REAL,
                    iv REAL,
                    progress_target REAL,
                    progress_stop REAL,
                    created_at TEXT DEFAULT (datetime('now'))
                );

                CREATE TABLE IF NOT EXISTS portfolio_analytics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_date TEXT NOT NULL UNIQUE,
                    analytics_json TEXT NOT NULL,
                    created_at TEXT DEFAULT (datetime('now'))
                );

                CREATE TABLE IF NOT EXISTS macro_scores (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_date TEXT NOT NULL UNIQUE,
                    macro_json TEXT NOT NULL,
                    created_at TEXT DEFAULT (datetime('now'))
                );

                CREATE TABLE IF NOT EXISTS news_cache (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticker TEXT NOT NULL,
                    run_date TEXT NOT NULL,
                    analysis_json TEXT NOT NULL,
                    headlines_json TEXT,
                    created_at TEXT DEFAULT (datetime('now')),
                    UNIQUE(ticker, run_date)
                );

                CREATE TABLE IF NOT EXISTS alerts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_date TEXT NOT NULL,
                    alert_type TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    ticker TEXT,
                    position_id TEXT,
                    message TEXT NOT NULL,
                    detail TEXT,
                    created_at TEXT DEFAULT (datetime('now'))
                );

                CREATE INDEX IF NOT EXISTS idx_valuations_run ON valuations(run_date);
                CREATE INDEX IF NOT EXISTS idx_valuations_pos ON valuations(position_id);
                CREATE INDEX IF NOT EXISTS idx_snapshots_ticker ON snapshots(ticker, run_date);
                CREATE INDEX IF NOT EXISTS idx_alerts_run ON alerts(run_date);
                CREATE INDEX IF NOT EXISTS idx_news_ticker ON news_cache(ticker, run_date);
            """)

    def save_snapshot(self, ticker: str, run_date: str, chain: list[dict]):
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO snapshots (ticker, run_date, chain_json) VALUES (?, ?, ?)",
                (ticker.upper(), run_date, json.dumps(chain, default=str)),
            )

    def get_snapshot(self, ticker: str, run_date: str) -> list[dict] | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT chain_json FROM snapshots WHERE ticker=? AND run_date=?",
                (ticker.upper(), run_date),
            ).fetchone()
            return json.loads(row["chain_json"]) if row else None

    def get_prior_snapshot(self, ticker: str, before_date: str) -> list[dict] | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT chain_json FROM snapshots WHERE ticker=? AND run_date<? ORDER BY run_date DESC LIMIT 1",
                (ticker.upper(), before_date),
            ).fetchone()
            return json.loads(row["chain_json"]) if row else None

    def get_all_snapshot_dates(self, ticker: str) -> list[str]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT run_date FROM snapshots WHERE ticker=? ORDER BY run_date",
                (ticker.upper(),),
            ).fetchall()
            return [r["run_date"] for r in rows]

    def get_iv_history(self, ticker: str) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT v.run_date, v.iv FROM valuations v
                   JOIN snapshots s ON v.ticker=s.ticker AND v.run_date=s.run_date
                   WHERE v.ticker=? AND v.iv IS NOT NULL AND v.asset_type='option'
                   ORDER BY v.run_date""",
                (ticker.upper(),),
            ).fetchall()
            return [dict(r) for r in rows]

    def save_valuations(self, run_date: str, valuations: list[dict]):
        with self._conn() as conn:
            conn.execute("DELETE FROM valuations WHERE run_date=?", (run_date,))
            for v in valuations:
                conn.execute(
                    """INSERT INTO valuations
                       (run_date, position_id, ticker, asset_type, mark, current_value,
                        cost_basis, pnl_dollars, pnl_pct, dte, delta, gamma, theta, vega, iv,
                        progress_target, progress_stop)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        run_date,
                        v["position_id"],
                        v["ticker"],
                        v["asset_type"],
                        v.get("mark"),
                        v.get("current_value"),
                        v.get("cost_basis"),
                        v.get("pnl_dollars"),
                        v.get("pnl_pct"),
                        v.get("dte"),
                        v.get("delta"),
                        v.get("gamma"),
                        v.get("theta"),
                        v.get("vega"),
                        v.get("iv"),
                        v.get("progress_target"),
                        v.get("progress_stop"),
                    ),
                )

    def save_portfolio_analytics(self, run_date: str, analytics: dict):
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO portfolio_analytics (run_date, analytics_json) VALUES (?, ?)",
                (run_date, json.dumps(analytics, default=str)),
            )

    def save_macro_score(self, run_date: str, macro: dict):
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO macro_scores (run_date, macro_json) VALUES (?, ?)",
                (run_date, json.dumps(macro, default=str)),
            )

    def get_macro_score(self, run_date: str) -> dict | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT macro_json FROM macro_scores WHERE run_date=?", (run_date,)
            ).fetchone()
            return json.loads(row["macro_json"]) if row else None

    def save_news_analysis(self, ticker: str, run_date: str, analysis: dict, headlines: list):
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO news_cache (ticker, run_date, analysis_json, headlines_json) VALUES (?,?,?,?)",
                (ticker.upper(), run_date, json.dumps(analysis, default=str), json.dumps(headlines, default=str)),
            )

    def get_news_analysis(self, ticker: str, run_date: str) -> dict | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT analysis_json FROM news_cache WHERE ticker=? AND run_date=?",
                (ticker.upper(), run_date),
            ).fetchone()
            return json.loads(row["analysis_json"]) if row else None

    def save_alerts(self, run_date: str, alerts: list[dict]):
        with self._conn() as conn:
            conn.execute("DELETE FROM alerts WHERE run_date=?", (run_date,))
            for a in alerts:
                conn.execute(
                    "INSERT INTO alerts (run_date, alert_type, severity, ticker, position_id, message, detail) VALUES (?,?,?,?,?,?,?)",
                    (run_date, a["alert_type"], a["severity"], a.get("ticker"), a.get("position_id"), a["message"], a.get("detail")),
                )

    def get_latest_valuations(self) -> list[dict]:
        with self._conn() as conn:
            row = conn.execute("SELECT MAX(run_date) as max_date FROM valuations").fetchone()
            if not row or not row["max_date"]:
                return []
            rows = conn.execute(
                "SELECT * FROM valuations WHERE run_date=? ORDER BY ticker", (row["max_date"],)
            ).fetchall()
            return [dict(r) for r in rows]

    def get_analytics(self, run_date: str) -> dict | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT analytics_json FROM portfolio_analytics WHERE run_date=?", (run_date,)
            ).fetchone()
            return json.loads(row["analytics_json"]) if row else None
