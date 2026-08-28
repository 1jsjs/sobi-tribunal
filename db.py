"""SQLite 연결 + verdicts 테이블 + ALTER 방식 마이그레이션(기존 DB 보존)."""
import os
import sqlite3

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "database.sqlite")

# 테이블 스키마 (컬럼 순서·타입은 api-contract.md 판결 계약 기준)
COLUMNS = [
    ("id", "INTEGER PRIMARY KEY AUTOINCREMENT"),
    ("email", "TEXT NOT NULL"),
    ("itemName", "TEXT"),
    ("price", "INTEGER"),
    ("boughtAt", "TEXT"),
    ("merchant", "TEXT"),
    ("category", "TEXT"),
    ("photoKey", "TEXT"),
    ("axisCode", "TEXT"),
    ("typeName", "TEXT"),
    ("guilt", "TEXT"),
    ("guiltScore", "INTEGER"),
    ("sentence", "TEXT"),
    ("verdictText", "TEXT"),
    ("plea", "TEXT"),
    ("evidenceJson", "TEXT"),
    ("costPerUse", "INTEGER"),
    ("createdAt", "TEXT DEFAULT (datetime('now'))"),
]


def get_conn():
    """행을 dict처럼 다룰 수 있는 커넥션을 반환한다."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _migrate(conn):
    """테이블이 없으면 만들고, 있으면 누락 컬럼만 ALTER로 추가한다(기존 DB 보존)."""
    cols_sql = ",\n    ".join(f"{name} {decl}" for name, decl in COLUMNS)
    conn.execute(f"CREATE TABLE IF NOT EXISTS verdicts (\n    {cols_sql}\n)")

    existing = {row["name"] for row in conn.execute("PRAGMA table_info(verdicts)")}
    for name, decl in COLUMNS:
        if name in existing:
            continue
        # PK/NOT NULL 제약과 비상수 DEFAULT(datetime('now') 등)는 SQLite가
        # ALTER ADD COLUMN에서 거부하므로 타입만 남긴다
        add_decl = decl
        if "PRIMARY KEY" in add_decl or "NOT NULL" in add_decl or "DEFAULT (" in add_decl:
            add_decl = add_decl.split()[0]  # 타입만
        conn.execute(f"ALTER TABLE verdicts ADD COLUMN {name} {add_decl}")

    conn.execute("CREATE INDEX IF NOT EXISTS idx_verdicts_email ON verdicts(email)")
    conn.commit()


def init_db():
    """앱 기동 시 1회 호출: DB 파일/테이블/인덱스 보장."""
    conn = get_conn()
    try:
        _migrate(conn)
    finally:
        conn.close()
