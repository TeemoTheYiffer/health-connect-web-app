"""One-shot: dump the schema and a row sample of the Health Connect export."""
from __future__ import annotations

import sqlite3
from pathlib import Path

DB = Path(__file__).resolve().parents[1] / "health_connect_export.db"
OUT = Path(__file__).resolve().parents[1] / "scripts" / "_schema_dump.txt"


def main() -> None:
    con = sqlite3.connect(DB)
    cur = con.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = [r[0] for r in cur.fetchall()]

    lines: list[str] = []
    lines.append(f"# Health Connect export schema ({DB.name})")
    lines.append(f"# Tables: {len(tables)}\n")

    for t in tables:
        cur.execute(f'SELECT COUNT(*) FROM "{t}"')
        n = cur.fetchone()[0]
        cur.execute("SELECT sql FROM sqlite_master WHERE name=?", (t,))
        sql = cur.fetchone()[0] or ""
        lines.append(f"## {t} ({n} rows)")
        lines.append(sql.strip())
        # First-row sample, columns truncated
        if n:
            cur.execute(f'SELECT * FROM "{t}" LIMIT 1')
            row = cur.fetchone()
            cols = [d[0] for d in cur.description]
            sample = {c: (str(v)[:60] if v is not None else None) for c, v in zip(cols, row, strict=True)}
            lines.append(f"sample: {sample}")
        lines.append("")

    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {OUT} ({len(tables)} tables)")


if __name__ == "__main__":
    main()
