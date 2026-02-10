"""Schema creation and data ingestion into target SQLite DB."""
import re
import sqlite3
from pathlib import Path
from typing import Any

from db import get_target_db_path


def run_ddl(project_id: str, ddl: str) -> None:
    """Create tables in project DB from DDL (SQLite)."""
    path = get_target_db_path(project_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    try:
        # Run only CREATE TABLE and ALTER TABLE
        for stmt in _split_ddl(ddl):
            stmt = stmt.strip()
            if stmt and not stmt.startswith("--"):
                conn.execute(stmt)
        conn.commit()
    finally:
        conn.close()


def _split_ddl(ddl: str) -> list[str]:
    """Split DDL into single statements (simple split by ;)."""
    return [s.strip() for s in ddl.split(";") if s.strip()]


def _table_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    """Return actual column names for table (excluding id if auto-generated)."""
    infos = conn.execute(f'PRAGMA table_info("{table}")').fetchall()
    cols = [c[1] for c in infos]
    if cols and cols[0].lower() == "id":
        return cols[1:]
    return cols


def insert_extracted_data(project_id: str, extraction: dict, table_data: list[dict[str, Any]] | None = None) -> int:
    """
    Insert sample/extracted rows into target DB.
    table_data: list of { "table": "TableName", "rows": [ {"col": "val", ...}, ... ] }
    Matches row keys to table columns case-insensitively so Title/title both work.
    Returns number of rows inserted.
    """
    if not table_data:
        return 0
    path = get_target_db_path(project_id)
    if not path.exists():
        return 0
    conn = sqlite3.connect(str(path))
    total = 0
    try:
        for block in table_data:
            table = (block.get("table") or "data").replace(" ", "_")
            rows = block.get("rows", [])
            if not rows:
                continue
            try:
                table_cols = _table_columns(conn, table)
            except Exception:
                continue
            if not table_cols:
                continue
            col_lower_to_real = {c.lower(): c for c in table_cols}
            placeholders = ", ".join("?" for _ in table_cols)
            col_list = ", ".join(f'"{c}"' for c in table_cols)
            for row in rows:
                vals = []
                for tc in table_cols:
                    key = col_lower_to_real.get(tc.lower())
                    if key is None:
                        continue
                    val = None
                    for row_k, row_v in row.items():
                        if str(row_k).lower() == tc.lower():
                            val = row_v
                            break
                    vals.append(val)
                if len(vals) != len(table_cols):
                    continue
                try:
                    conn.execute(
                        f'INSERT INTO "{table}" ({col_list}) VALUES ({placeholders})',
                        vals,
                    )
                    total += 1
                except Exception:
                    pass
        conn.commit()
    finally:
        conn.close()
    return total


def get_table_preview(project_id: str, limit: int = 5) -> list[dict]:
    """Return list of { table_name, columns, rows } for preview."""
    path = get_target_db_path(project_id)
    if not path.exists():
        return []
    conn = sqlite3.connect(str(path))
    result = []
    try:
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
        for (name,) in cur.fetchall():
            cols = [c[1] for c in conn.execute(f'PRAGMA table_info("{name}")').fetchall()]
            rows = conn.execute(f'SELECT * FROM "{name}" LIMIT ?', (limit,)).fetchall()
            result.append({
                "table_name": name,
                "columns": cols,
                "rows": [dict(zip(cols, r)) for r in rows],
            })
    finally:
        conn.close()
    return result
