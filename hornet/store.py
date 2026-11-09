"""SQLite-Speicher: Alarme, Einstellungen, Push-Abos. Thread-sicher über ein Lock."""
from __future__ import annotations

import json
import shutil
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    camera TEXT,
    kind TEXT NOT NULL,            -- new | update | reminder | test
    species TEXT,
    label TEXT,
    conf REAL,
    count INTEGER,
    muted INTEGER DEFAULT 0,
    event_id INTEGER,
    snapshot TEXT,
    clip TEXT,
    verify TEXT,
    delivery TEXT,
    detections TEXT
);
CREATE INDEX IF NOT EXISTS idx_alerts_ts ON alerts(ts DESC);
CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS push_subs (endpoint TEXT PRIMARY KEY, data TEXT NOT NULL, created REAL);
CREATE TABLE IF NOT EXISTS mesh_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    direction TEXT NOT NULL,       -- in | out
    via TEXT,                      -- lora | freenet
    typ TEXT,                      -- A | U | T | R
    ident TEXT,
    station TEXT,
    count INTEGER,
    conf REAL,
    ai TEXT,
    lat REAL,
    lon REAL,
    note TEXT,
    status TEXT                    -- ok | queued | sent | failed | limited
);
CREATE INDEX IF NOT EXISTS idx_mesh_ts ON mesh_log(ts DESC);
CREATE INDEX IF NOT EXISTS idx_mesh_station ON mesh_log(station, direction);
CREATE TABLE IF NOT EXISTS mesh_seen (key TEXT PRIMARY KEY, ts REAL NOT NULL);
"""

ALERT_COLS = frozenset({"ts", "camera", "kind", "species", "label", "conf", "count", "muted", "event_id",
                        "snapshot", "clip", "verify", "delivery", "detections"})
MESH_COLS = frozenset({"ts", "direction", "via", "typ", "ident", "station", "count", "conf", "ai", "lat", "lon",
                       "note", "status"})
MESH_LOG_MAX = 20000          # Obergrenze der Funkprotokoll-Zeilen (Schutz vor Überflutung des Speichers)
MESH_LOG_TRIM_EVERY = 500     # nach so vielen neuen Zeilen wird gekürzt
MESH_SEEN_MAX = 20000
MESH_SEEN_TTL = 7 * 86400


def _only(cols: frozenset, fields: dict) -> None:
    """Spaltennamen kommen nie aus fremden Daten – trotzdem nur bekannte zulassen (kein SQL über Namen)."""
    bad = [k for k in fields if k not in cols]
    if bad:
        raise ValueError(f"Unbekannte Spalte: {bad[0]}")

JSON_FIELDS = ("verify", "delivery", "detections")


class Store:
    def __init__(self, db_path: Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(db_path), check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        self._mesh_adds = 0
        with self._lock:
            self._db.execute("PRAGMA journal_mode=WAL")
            self._db.execute("PRAGMA synchronous=NORMAL")   # in WAL-Modus sicher gegen Programmabsturz, viel schneller
            self._db.execute("PRAGMA busy_timeout=5000")
            self._db.executescript(SCHEMA)
            self._db.commit()

    def close(self) -> None:
        with self._lock:
            self._db.close()

    # -- Alarme -----------------------------------------------------------------------
    def add_alert(self, **f: Any) -> int:
        _only(ALERT_COLS, f)
        f.setdefault("ts", time.time())
        for k in JSON_FIELDS:
            if k in f and not isinstance(f[k], str):
                f[k] = json.dumps(f[k], ensure_ascii=False)
        cols = ", ".join(f)
        qs = ", ".join("?" for _ in f)
        with self._lock:
            cur = self._db.execute(f"INSERT INTO alerts ({cols}) VALUES ({qs})", list(f.values()))
            self._db.commit()
            return int(cur.lastrowid)

    def update_alert(self, alert_id: int, **f: Any) -> None:
        if not f:
            return
        _only(ALERT_COLS, f)
        for k in JSON_FIELDS:
            if k in f and not isinstance(f[k], str):
                f[k] = json.dumps(f[k], ensure_ascii=False)
        sets = ", ".join(f"{k}=?" for k in f)
        with self._lock:
            self._db.execute(f"UPDATE alerts SET {sets} WHERE id=?", [*f.values(), alert_id])
            self._db.commit()

    def merge_delivery(self, alert_id: int, results: dict) -> None:
        with self._lock:
            row = self._db.execute("SELECT delivery FROM alerts WHERE id=?", (alert_id,)).fetchone()
            cur = json.loads(row["delivery"]) if row and row["delivery"] else {}
            for ch, res in results.items():
                cur.setdefault(ch, {}).update(res)
            self._db.execute("UPDATE alerts SET delivery=? WHERE id=?",
                             (json.dumps(cur, ensure_ascii=False), alert_id))
            self._db.commit()

    @staticmethod
    def _row(r: sqlite3.Row | None) -> dict | None:
        if r is None:
            return None
        d = dict(r)
        for k in JSON_FIELDS:
            if d.get(k):
                try:
                    d[k] = json.loads(d[k])
                except ValueError:
                    pass
        d["muted"] = bool(d.get("muted"))
        return d

    def get_alert(self, alert_id: int) -> dict | None:
        with self._lock:
            return self._row(self._db.execute("SELECT * FROM alerts WHERE id=?", (alert_id,)).fetchone())

    def list_alerts(self, limit: int = 50, offset: int = 0, include_tests: bool = True) -> list[dict]:
        q = "SELECT * FROM alerts"
        if not include_tests:
            q += " WHERE kind != 'test'"
        q += " ORDER BY ts DESC LIMIT ? OFFSET ?"
        with self._lock:
            return [self._row(r) for r in self._db.execute(q, (limit, offset)).fetchall()]

    def count_alerts(self, since: float = 0.0) -> int:
        with self._lock:
            r = self._db.execute(
                "SELECT COUNT(*) c FROM alerts WHERE ts>=? AND kind IN ('new')", (since,)).fetchone()
            return int(r["c"])

    # -- Key/Value --------------------------------------------------------------------
    def kv_get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            r = self._db.execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
        if not r:
            return default
        try:
            return json.loads(r["value"])
        except ValueError:
            return default

    def kv_set(self, key: str, value: Any) -> None:
        with self._lock:
            self._db.execute("INSERT INTO kv(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                             (key, json.dumps(value)))
            self._db.commit()

    # -- Web-Push-Abos ------------------------------------------------------------------
    def push_add(self, sub: dict) -> None:
        with self._lock:
            self._db.execute(
                "INSERT INTO push_subs(endpoint,data,created) VALUES(?,?,?) "
                "ON CONFLICT(endpoint) DO UPDATE SET data=excluded.data",
                (sub["endpoint"], json.dumps(sub), time.time()))
            self._db.commit()

    def push_remove(self, endpoint: str) -> None:
        with self._lock:
            self._db.execute("DELETE FROM push_subs WHERE endpoint=?", (endpoint,))
            self._db.commit()

    def push_list(self) -> list[dict]:
        with self._lock:
            return [json.loads(r["data"]) for r in self._db.execute("SELECT data FROM push_subs").fetchall()]

    # -- Funknetz -------------------------------------------------------------------------
    def mesh_add(self, **f: Any) -> int:
        _only(MESH_COLS, f)
        f.setdefault("ts", time.time())
        cols = ", ".join(f)
        qs = ", ".join("?" for _ in f)
        with self._lock:
            cur = self._db.execute(f"INSERT INTO mesh_log ({cols}) VALUES ({qs})", list(f.values()))
            self._mesh_adds += 1
            if self._mesh_adds % MESH_LOG_TRIM_EVERY == 0:
                self._trim_mesh_log()
            self._db.commit()
            return int(cur.lastrowid)

    def mesh_update(self, row_id: int, **f: Any) -> None:
        if not f:
            return
        _only(MESH_COLS, f)
        sets = ", ".join(f"{k}=?" for k in f)
        with self._lock:
            self._db.execute(f"UPDATE mesh_log SET {sets} WHERE id=?", [*f.values(), row_id])
            self._db.commit()

    def _trim_mesh_log(self) -> None:
        self._db.execute("DELETE FROM mesh_log WHERE id <= (SELECT MAX(id) FROM mesh_log) - ?", (MESH_LOG_MAX,))
        self._db.execute("DELETE FROM mesh_seen WHERE ts < ?", (time.time() - MESH_SEEN_TTL,))
        self._db.execute("DELETE FROM mesh_seen WHERE key NOT IN (SELECT key FROM mesh_seen ORDER BY ts DESC LIMIT ?)",
                         (MESH_SEEN_MAX,))

    def mesh_list(self, limit: int = 100, offset: int = 0, direction: str | None = None) -> list[dict]:
        q = "SELECT * FROM mesh_log"
        args: list[Any] = []
        if direction in ("in", "out"):
            q += " WHERE direction=?"
            args.append(direction)
        q += " ORDER BY id DESC LIMIT ? OFFSET ?"
        args += [max(1, min(int(limit), 500)), max(0, int(offset))]
        with self._lock:
            return [dict(r) for r in self._db.execute(q, args).fetchall()]

    def mesh_ack_counts(self, idents: list[str]) -> dict[str, int]:
        """Wie viele Stationen haben die gesendete Meldung quittiert?"""
        ids = [i for i in idents if i]
        if not ids:
            return {}
        qs = ",".join("?" for _ in ids)
        with self._lock:
            rows = self._db.execute(
                f"SELECT ident, COUNT(*) c FROM mesh_log WHERE direction='in' AND typ='R' AND ident IN ({qs}) "
                "GROUP BY ident", ids).fetchall()
        return {r["ident"]: int(r["c"]) for r in rows}

    def mesh_count(self) -> int:
        with self._lock:
            return int(self._db.execute("SELECT COUNT(*) c FROM mesh_log").fetchone()["c"])

    def mesh_station_stats(self, station: str) -> dict:
        """Wie lange und wie oft eine Station bereits (angenommen) gemeldet hat – Grundlage für „bekannte Station“."""
        with self._lock:
            r = self._db.execute(
                "SELECT COUNT(*) n, MIN(ts) first, MAX(ts) last FROM mesh_log "
                "WHERE direction='in' AND station=? AND status='ok'", (station,)).fetchone()
        return {"n": int(r["n"] or 0), "first": r["first"], "last": r["last"]}

    def mesh_stations(self, limit: int = 50) -> list[dict]:
        with self._lock:
            rows = self._db.execute(
                "SELECT station, COUNT(*) n, MIN(ts) first, MAX(ts) last, MAX(via) via FROM mesh_log "
                "WHERE direction='in' AND status='ok' AND station IS NOT NULL GROUP BY station "
                "ORDER BY last DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    def mesh_seen_has(self, key: str) -> bool:
        with self._lock:
            return self._db.execute("SELECT 1 FROM mesh_seen WHERE key=?", (key,)).fetchone() is not None

    def mesh_seen_add(self, key: str, ts: float | None = None) -> bool:
        """True, wenn der Schlüssel neu war."""
        with self._lock:
            cur = self._db.execute("INSERT OR IGNORE INTO mesh_seen(key, ts) VALUES(?,?)", (key, ts or time.time()))
            self._db.commit()
            return cur.rowcount > 0

    # -- Aufräumen ----------------------------------------------------------------------
    def cleanup(self, alerts_dir: Path, retention_days: int) -> int:
        with self._lock:
            self._trim_mesh_log()
            self._db.commit()
        if retention_days <= 0:
            return 0
        cutoff = time.time() - retention_days * 86400
        with self._lock:
            rows = self._db.execute("SELECT id FROM alerts WHERE ts<?", (cutoff,)).fetchall()
            ids = [r["id"] for r in rows]
            if ids:
                self._db.executemany("DELETE FROM alerts WHERE id=?", [(i,) for i in ids])
                self._db.commit()
        for i in ids:
            shutil.rmtree(alerts_dir / str(i), ignore_errors=True)
        with self._lock:
            self._db.execute("DELETE FROM mesh_log WHERE ts<?", (cutoff,))
            self._db.commit()
        return len(ids)
