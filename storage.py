from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data"
OUTPUT_DIR = APP_DIR / "output"
DB_PATH = DATA_DIR / "timesheets.sqlite3"


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def get_connection() -> sqlite3.Connection:
    ensure_dirs()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS profile (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS timesheets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                reporting_week TEXT NOT NULL,
                employee_name TEXT NOT NULL,
                supervisor_name TEXT NOT NULL,
                total_hours REAL NOT NULL,
                pdf_path TEXT NOT NULL,
                docx_path TEXT NOT NULL,
                payload_json TEXT NOT NULL
            )
            """
        )
        conn.commit()


def save_profile(profile: Dict[str, Any]) -> None:
    with get_connection() as conn:
        for key, value in profile.items():
            conn.execute(
                "INSERT OR REPLACE INTO profile (key, value) VALUES (?, ?)",
                (key, json.dumps(value)),
            )
        conn.commit()


def load_profile() -> Dict[str, Any]:
    init_db()
    with get_connection() as conn:
        rows = conn.execute("SELECT key, value FROM profile").fetchall()
    profile: Dict[str, Any] = {}
    for row in rows:
        try:
            profile[row["key"]] = json.loads(row["value"])
        except json.JSONDecodeError:
            profile[row["key"]] = row["value"]
    return profile


def add_history_record(
    *,
    reporting_week: str,
    employee_name: str,
    supervisor_name: str,
    total_hours: float,
    pdf_path: Path,
    docx_path: Path,
    payload: Dict[str, Any],
) -> int:
    init_db()
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO timesheets (
                created_at, reporting_week, employee_name, supervisor_name,
                total_hours, pdf_path, docx_path, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                datetime.now().isoformat(timespec="seconds"),
                reporting_week,
                employee_name,
                supervisor_name,
                total_hours,
                str(pdf_path),
                str(docx_path),
                json.dumps(payload, default=str),
            ),
        )
        conn.commit()
        return int(cursor.lastrowid)


def list_history(limit: int = 50) -> List[Dict[str, Any]]:
    init_db()
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT * FROM timesheets
            ORDER BY datetime(created_at) DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def get_history_record(record_id: int) -> Optional[Dict[str, Any]]:
    init_db()
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM timesheets WHERE id = ?", (record_id,)).fetchone()
    if row is None:
        return None
    result = dict(row)
    try:
        result["payload"] = json.loads(result.get("payload_json", "{}"))
    except json.JSONDecodeError:
        result["payload"] = {}
    return result
