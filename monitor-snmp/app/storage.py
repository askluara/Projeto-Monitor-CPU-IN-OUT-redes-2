"""Persistencia em SQLite (arquivo unico, sem servidor).

Tabelas:
  samples(ts, in_bps, out_bps, cpu)       -> amostras coletadas
  errors(ts, kind, message)               -> falhas de coleta
  alert_events(ts, metric, value, threshold, channels, message)

ts = epoch UTC em segundos (float). A conversao para data/hora local fica na
camada de apresentacao. Valores NULL significam "sem dado valido" (ex.: a
primeira leitura nao tem taxa, ou a amostra foi descartada).

Thread-safe: o worker de coleta grava e a interface le, em threads diferentes.
"""
import sqlite3
import threading
import time
from typing import List, Optional, Tuple

SCHEMA = """
CREATE TABLE IF NOT EXISTS samples (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    ts      REAL NOT NULL,
    in_bps  REAL,
    out_bps REAL,
    cpu     REAL
);
CREATE INDEX IF NOT EXISTS idx_samples_ts ON samples(ts);

CREATE TABLE IF NOT EXISTS errors (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    ts      REAL NOT NULL,
    kind    TEXT NOT NULL,
    message TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_errors_ts ON errors(ts);

CREATE TABLE IF NOT EXISTS alert_events (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    ts        REAL NOT NULL,
    metric    TEXT NOT NULL,
    value     REAL NOT NULL,
    threshold REAL NOT NULL,
    channels  TEXT NOT NULL,
    message   TEXT
);
CREATE INDEX IF NOT EXISTS idx_alerts_ts ON alert_events(ts);
"""

Sample = Tuple[float, Optional[float], Optional[float], Optional[float]]


class Storage:
    def __init__(self, path: str = "monitor.db"):
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    # ---- escrita --------------------------------------------------
    def add_sample(self, in_bps, out_bps, cpu, ts: Optional[float] = None) -> float:
        ts = time.time() if ts is None else ts
        with self._lock:
            self._conn.execute(
                "INSERT INTO samples(ts, in_bps, out_bps, cpu) VALUES (?,?,?,?)",
                (ts, in_bps, out_bps, cpu),
            )
            self._conn.commit()
        return ts

    def add_error(self, kind: str, message: str, ts: Optional[float] = None):
        ts = time.time() if ts is None else ts
        with self._lock:
            self._conn.execute(
                "INSERT INTO errors(ts, kind, message) VALUES (?,?,?)",
                (ts, kind, message),
            )
            self._conn.commit()

    def add_alert_event(self, metric: str, value: float, threshold: float,
                        channels: str, message: str = "", ts: Optional[float] = None):
        ts = time.time() if ts is None else ts
        with self._lock:
            self._conn.execute(
                "INSERT INTO alert_events(ts, metric, value, threshold, channels, message)"
                " VALUES (?,?,?,?,?,?)",
                (ts, metric, value, threshold, channels, message),
            )
            self._conn.commit()

    # ---- leitura --------------------------------------------------
    def query_samples(self, start: Optional[float] = None,
                      end: Optional[float] = None) -> List[Sample]:
        """Amostras com start <= ts <= end (limites opcionais), ordem cronologica."""
        sql, args = "SELECT ts, in_bps, out_bps, cpu FROM samples", []
        where = []
        if start is not None:
            where.append("ts >= ?")
            args.append(start)
        if end is not None:
            where.append("ts <= ?")
            args.append(end)
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY ts ASC"
        with self._lock:
            return self._conn.execute(sql, args).fetchall()

    def query_errors(self, limit: int = 100):
        with self._lock:
            return self._conn.execute(
                "SELECT ts, kind, message FROM errors ORDER BY ts DESC LIMIT ?",
                (limit,)).fetchall()

    def query_alert_events(self, limit: int = 100):
        with self._lock:
            return self._conn.execute(
                "SELECT ts, metric, value, threshold, channels, message"
                " FROM alert_events ORDER BY ts DESC LIMIT ?", (limit,)).fetchall()

    def count_samples(self) -> int:
        with self._lock:
            return self._conn.execute("SELECT COUNT(*) FROM samples").fetchone()[0]

    def close(self):
        with self._lock:
            self._conn.close()
