"""Lưu lịch sử giá và cảnh báo vào SQLite (1 file, không cần cài database)."""
import sqlite3

import pandas as pd

SCHEMA = """
CREATE TABLE IF NOT EXISTS ticks (
    ts TEXT NOT NULL, symbol TEXT NOT NULL, price REAL NOT NULL,
    change_24h REAL, volume_24h REAL, source TEXT,
    PRIMARY KEY (ts, symbol, source)
);
CREATE TABLE IF NOT EXISTS alerts (
    ts TEXT NOT NULL, symbol TEXT NOT NULL, rule TEXT NOT NULL, message TEXT NOT NULL
);
"""


class Store:
    def __init__(self, path):
        self.con = sqlite3.connect(path, check_same_thread=False)
        self.con.executescript(SCHEMA)

    def save_ticks(self, df: pd.DataFrame, source: str) -> int:
        rows = [(r.ts.isoformat(), r.symbol, float(r.price),
                 None if pd.isna(r.change_24h) else float(r.change_24h),
                 None if pd.isna(r.volume_24h) else float(r.volume_24h), source)
                for r in df.itertuples()]
        cur = self.con.executemany("INSERT OR IGNORE INTO ticks VALUES (?,?,?,?,?,?)", rows)
        self.con.commit()
        return cur.rowcount

    def ticks(self, symbol=None, since=None) -> pd.DataFrame:
        sql, args = "SELECT * FROM ticks WHERE 1=1", []
        if symbol:
            sql += " AND symbol = ?"
            args.append(symbol)
        if since is not None:
            sql += " AND ts >= ?"
            args.append(pd.Timestamp(since).isoformat())
        df = pd.read_sql(sql + " ORDER BY ts", self.con, params=args)
        df["ts"] = pd.to_datetime(df["ts"], utc=True, format="ISO8601")
        return df

    def save_alert(self, ts, symbol, rule, message):
        self.con.execute("INSERT INTO alerts VALUES (?,?,?,?)", (pd.Timestamp(ts).isoformat(), symbol, rule, message))
        self.con.commit()

    def alerts(self, limit=50) -> pd.DataFrame:
        return pd.read_sql("SELECT * FROM alerts ORDER BY ts DESC LIMIT ?", self.con, params=[limit])
