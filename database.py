import json
import os
import sqlite3
import threading
import time
from datetime import datetime, timedelta, timezone
from time_sync import time_manager

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "pda_config.json")
LOCAL_DB_PATH = os.path.join(os.path.dirname(__file__), "pda_local.db")

_WARNED_MISSING_TABLES = set()
_schemas_verified = False
_db_initialized = False


def _check_supabase_error(e, table_name: str):
    """Silences repeat PGRST205 schema errors so terminal stays clean while offline."""
    err_str = str(e)
    if "PGRST205" in err_str or "Could not find the table" in err_str:
        if table_name not in _WARNED_MISSING_TABLES:
            _WARNED_MISSING_TABLES.add(table_name)
            print(f"[SUPABASE NOTICE] Table '{table_name}' not yet deployed to cloud. Falling back to local SQLite.")
    else:
        print(f"[SUPABASE ERROR] {table_name}: {e}")


# ---------------------------------------------------------------------------
# 1. CONFIGURATION & CLOUD CLIENT INSPECTION
# ---------------------------------------------------------------------------
STORAGE_MODE = "local"
supabase = None

if os.path.exists(CONFIG_PATH):
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            _cfg = json.load(f)
        STORAGE_MODE = _cfg.get("storage_mode", "local")

        if STORAGE_MODE == "supabase":
            from supabase import create_client
            url = _cfg.get("supabase_url")
            key = _cfg.get("supabase_key")
            if url and key:
                supabase = create_client(url, key)
            else:
                STORAGE_MODE = "local"
    except Exception as e:
        print(f"[CONFIG WARNING] Defaulting to local storage: {e}")
        STORAGE_MODE = "local"


# ---------------------------------------------------------------------------
# 2. THREAD-SAFE SQLITE CONNECTION (WAL MODE & 10S BUSY TIMEOUT)
# ---------------------------------------------------------------------------
def _get_sqlite_conn():
    """Returns a SQLite connection with a 10.0s busy timeout and WAL concurrency."""
    conn = sqlite3.connect(LOCAL_DB_PATH, timeout=10.0)
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
    except Exception:
        pass
    return conn


def verify_remote_schemas():
    """Triggers the automated HTTPS RPC schema sync ONCE on startup."""
    global _schemas_verified
    if _schemas_verified:
        return

    if STORAGE_MODE == "supabase" and supabase:
        try:
            res = supabase.rpc("sync_pda_schemas", {}).execute()
            print("[ALTERRA REMOTE] Remote schema verification:", res.data)
            _schemas_verified = True
        except Exception as e:
            print(f"[ALTERRA REMOTE] Schema sync bypass: {e}")


def prune_hot_cloud_cache(retention_days: int = 30):
    """
    Safely prunes records older than retention_days from Supabase,
    ensuring they are preserved in the desktop SQLite vault first.
    """
    if STORAGE_MODE != "supabase" or not supabase:
        return

    cutoff_iso = (datetime.now(timezone.utc) - timedelta(days=retention_days)).isoformat()
    tables = ("intake_logs", "hygiene_logs", "sleep_logs", "exercise_logs", "nap_logs")

    for tbl in tables:
        try:
            res = supabase.table(tbl).select("*").lt("logged_at", cutoff_iso).execute()
            old_records = res.data or []
            if not old_records:
                continue

            conn = _get_sqlite_conn()
            cur = conn.cursor()
            for r in old_records:
                ts = r.get("logged_at")
                if tbl == "intake_logs":
                    cur.execute("SELECT id FROM intake_logs WHERE logged_at = ?", (ts,))
                    if not cur.fetchone():
                        cur.execute(
                            "INSERT INTO intake_logs (type, amount, tag, logged_at, synced) VALUES (?, ?, ?, ?, 1)",
                            (r.get("type"), r.get("amount"), r.get("tag"), ts)
                        )
                elif tbl == "sleep_logs":
                    cur.execute("SELECT id FROM sleep_logs WHERE logged_at = ?", (ts,))
                    if not cur.fetchone():
                        cur.execute(
                            "INSERT INTO sleep_logs (sleep_time, wake_time, duration_hours, interruptions, quality_notes, logged_at, synced) VALUES (?, ?, ?, ?, ?, ?, 1)",
                            (r.get("sleep_time"), r.get("wake_time"), r.get("duration_hours"), r.get("interruptions"), r.get("quality_notes"), ts)
                        )
                elif tbl == "exercise_logs":
                    cur.execute("SELECT id FROM exercise_logs WHERE logged_at = ?", (ts,))
                    if not cur.fetchone():
                        cur.execute(
                            "INSERT INTO exercise_logs (exercise_type, duration_hours, intensity, notes, logged_at, synced) VALUES (?, ?, ?, ?, ?, 1)",
                            (r.get("exercise_type"), r.get("duration_hours"), r.get("intensity"), r.get("notes"), ts)
                        )
                elif tbl == "nap_logs":
                    cur.execute("SELECT id FROM nap_logs WHERE logged_at = ?", (ts,))
                    if not cur.fetchone():
                        cur.execute(
                            "INSERT INTO nap_logs (duration_minutes, notes, logged_at, synced) VALUES (?, ?, ?, 1)",
                            (r.get("duration_minutes"), r.get("notes"), ts)
                        )
                elif tbl == "hygiene_logs":
                    cur.execute("SELECT id FROM hygiene_logs WHERE logged_at = ?", (ts,))
                    if not cur.fetchone():
                        cur.execute(
                            "INSERT INTO hygiene_logs (tag, logged_at, synced) VALUES (?, ?, 1)",
                            (r.get("tag"), ts)
                        )
            conn.commit()
            conn.close()

            supabase.table(tbl).delete().lt("logged_at", cutoff_iso).execute()
            print(f"[ARCHIVER] Pruned {len(old_records)} cold entries from cloud table '{tbl}'.")
        except Exception as e:
            print(f"[ARCHIVER] Cloud prune notice on '{tbl}': {e}")


def flush_offline_buffer() -> int:
    """
    Scans local SQLite tables for un-synced entries (synced = 0)
    and flushes them to Supabase in chronological order.
    """
    if STORAGE_MODE != "supabase" or not supabase:
        return 0

    total_flushed = 0
    tables_config = {
        "intake_logs": {
            "cols": ["id", "type", "amount", "tag", "logged_at"],
            "payload": lambda r: {"type": r[1], "amount": r[2], "tag": r[3], "logged_at": r[4]}
        },
        "hygiene_logs": {
            "cols": ["id", "tag", "logged_at"],
            "payload": lambda r: {"tag": r[1], "logged_at": r[2]}
        },
        "sleep_logs": {
            "cols": ["id", "sleep_time", "wake_time", "duration_hours", "interruptions", "quality_notes", "logged_at"],
            "payload": lambda r: {
                "sleep_time": r[1], "wake_time": r[2], "duration_hours": r[3],
                "interruptions": r[4], "quality_notes": r[5], "logged_at": r[6]
            }
        },
        "exercise_logs": {
            "cols": ["id", "exercise_type", "duration_hours", "intensity", "notes", "logged_at"],
            "payload": lambda r: {
                "exercise_type": r[1], "duration_hours": r[2], "intensity": r[3],
                "notes": r[4], "logged_at": r[5]
            }
        },
        "nap_logs": {
            "cols": ["id", "duration_minutes", "notes", "logged_at"],
            "payload": lambda r: {"duration_minutes": r[1], "notes": r[2], "logged_at": r[3]}
        }
    }

    conn = _get_sqlite_conn()
    cur = conn.cursor()

    for tbl, cfg in tables_config.items():
        col_str = ", ".join(cfg["cols"])
        try:
            cur.execute(f"SELECT {col_str} FROM {tbl} WHERE synced = 0 ORDER BY id ASC")
            rows = cur.fetchall()
        except sqlite3.OperationalError:
            continue

        if not rows:
            continue

        for r in rows:
            record_id = r[0]
            body = cfg["payload"](r)
            try:
                supabase.table(tbl).insert(body).execute()
                up_conn = _get_sqlite_conn()
                up_conn.execute(f"UPDATE {tbl} SET synced = 1 WHERE id = ?", (record_id,))
                up_conn.commit()
                up_conn.close()
                total_flushed += 1
            except Exception as e:
                _check_supabase_error(e, tbl)
                break  # Stop processing this table to preserve transaction sequence

    conn.close()

    if total_flushed > 0:
        print(f"[BUFFER FLUSHER] Successfully pushed {total_flushed} offline transactions to Supabase.")

    return total_flushed


def _background_buffer_flusher(interval_sec: int = 25):
    """Daemon thread loop that flushes pending local records every interval."""
    while True:
        try:
            time.sleep(interval_sec)
            flush_offline_buffer()
        except Exception:
            pass


def _init_local_db():
    """Ensures local tables, migrations, and background workers run once per lifecycle."""
    global _db_initialized
    if _db_initialized:
        return

    conn = _get_sqlite_conn()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS intake_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT NOT NULL,
            amount REAL NOT NULL,
            tag TEXT,
            logged_at TEXT NOT NULL,
            synced INTEGER DEFAULT 0
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS hygiene_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tag TEXT NOT NULL,
            logged_at TEXT NOT NULL,
            synced INTEGER DEFAULT 0
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS sleep_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sleep_time TEXT NOT NULL,
            wake_time TEXT NOT NULL,
            duration_hours REAL NOT NULL,
            interruptions INTEGER DEFAULT 0,
            quality_notes TEXT,
            logged_at TEXT NOT NULL,
            synced INTEGER DEFAULT 0
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS exercise_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            exercise_type TEXT NOT NULL,
            duration_hours REAL NOT NULL,
            intensity TEXT NOT NULL,
            notes TEXT,
            logged_at TEXT NOT NULL,
            synced INTEGER DEFAULT 0
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS nap_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            duration_minutes INTEGER NOT NULL,
            notes TEXT,
            logged_at TEXT NOT NULL,
            synced INTEGER DEFAULT 0
        )
    """)

    # Safe migration: add 'synced' to existing tables if missing
    for tbl in ("intake_logs", "hygiene_logs", "sleep_logs", "exercise_logs", "nap_logs"):
        try:
            cur.execute(f"ALTER TABLE {tbl} ADD COLUMN synced INTEGER DEFAULT 1;")
        except sqlite3.OperationalError:
            pass

    conn.commit()
    conn.close()

    _db_initialized = True

    # 1. Run remote verification once
    verify_remote_schemas()

    # 2. Launch rolling 30-day cold vault archiver
    threading.Thread(target=prune_hot_cloud_cache, args=(30,), daemon=True).start()

    # 3. Launch offline buffer auto-flusher daemon
    threading.Thread(target=_background_buffer_flusher, args=(25,), daemon=True).start()


# Bootstraps local tables and background threads
_init_local_db()


# ---------------------------------------------------------------------------
# 3. TIMESTAMP CONVERTERS & HELPERS
# ---------------------------------------------------------------------------
def _get_now_utc_iso() -> str:
    """Standardized UTC ISO timestamp used for all records."""
    try:
        import time_sync
        return time_sync.get_current_iso()
    except Exception:
        return datetime.now(timezone.utc).isoformat()


def _parse_timestamp(val) -> float:
    """Safely converts arbitrary DB ISO strings to Unix epoch seconds."""
    if not val:
        return -1.0
    s = str(val).strip().replace("Z", "+00:00")
    if " " in s and "T" not in s:
        s = s.replace(" ", "T")
    if s.endswith("+00"):
        s += ":00"
    try:
        return datetime.fromisoformat(s).timestamp()
    except Exception:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                return datetime.strptime(s[:19], fmt).replace(tzinfo=timezone.utc).timestamp()
            except Exception:
                pass
        return -1.0


# ---------------------------------------------------------------------------
# 4. INTAKE LOGGING (WATER & MEALS)
# ---------------------------------------------------------------------------
def log_intake(intake_type: str, amount: float = 1.0, tag: str = ""):
    now_utc = _get_now_utc_iso()

    conn = _get_sqlite_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO intake_logs (type, amount, tag, logged_at, synced) VALUES (?, ?, ?, ?, 0)",
        (intake_type, amount, tag, now_utc)
    )
    row_id = cur.lastrowid
    conn.commit()
    conn.close()

    if STORAGE_MODE == "supabase" and supabase:
        try:
            supabase.table("intake_logs").insert({
                "type": intake_type,
                "amount": amount,
                "tag": tag,
                "logged_at": now_utc
            }).execute()

            up_conn = _get_sqlite_conn()
            up_conn.execute("UPDATE intake_logs SET synced = 1 WHERE id = ?", (row_id,))
            up_conn.commit()
            up_conn.close()
        except Exception as e:
            print(f"[BUFFER QUEUED] Intake stored locally (Offline ID {row_id}): {e}")


def log_water(amount_ml: float = 250.0):
    log_intake("hydration", amount_ml, "Hydration Fluid")

def log_snack(tag: str = "Nutrient Snack"):
    """Logs a light caloric snack (counted as 0.5 standard ration equivalent)."""
    log_intake("snack", 0.5, tag)

def log_meal(tag: str = "Standard Ration"):
    log_intake("meal", 1.0, tag)


# ---------------------------------------------------------------------------
# 5. HYGIENE LOGGING (BRUSHING & SHOWER)
# ---------------------------------------------------------------------------
def log_hygiene(tag: str = "brushing"):
    now_utc = _get_now_utc_iso()

    conn = _get_sqlite_conn()
    cur = conn.cursor()
    cur.execute("INSERT INTO hygiene_logs (tag, logged_at, synced) VALUES (?, ?, 0)", (tag, now_utc))
    row_id = cur.lastrowid
    conn.commit()
    conn.close()

    if STORAGE_MODE == "supabase" and supabase:
        try:
            supabase.table("hygiene_logs").insert({
                "tag": tag,
                "logged_at": now_utc
            }).execute()

            up_conn = _get_sqlite_conn()
            up_conn.execute("UPDATE hygiene_logs SET synced = 1 WHERE id = ?", (row_id,))
            up_conn.commit()
            up_conn.close()
        except Exception as e:
            print(f"[BUFFER QUEUED] Hygiene stored locally (Offline ID {row_id}): {e}")


def get_hygiene_today_count(tag: str = "brushing") -> int:
    local_now = time_manager.now()
    start_of_day_local = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    start_of_day_utc = start_of_day_local.astimezone(timezone.utc).isoformat()

    if STORAGE_MODE == "supabase" and supabase:
        try:
            res = (
                supabase.table("hygiene_logs")
                .select("id")
                .eq("tag", tag)
                .gte("logged_at", start_of_day_utc)
                .execute()
            )
            return len(res.data or [])
        except Exception as e:
            print(f"[SUPABASE ERROR] {e}")

    conn = _get_sqlite_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT COUNT(*) FROM hygiene_logs WHERE tag = ? AND logged_at >= ?",
        (tag, start_of_day_utc)
    )
    row = cur.fetchone()
    count = row[0] if row else 0
    conn.close()
    return count


def get_last_hygiene_time(tag: str = "shower"):
    if STORAGE_MODE == "supabase" and supabase:
        try:
            res = (
                supabase.table("hygiene_logs")
                .select("logged_at")
                .eq("tag", tag)
                .order("logged_at", desc=True)
                .limit(1)
                .execute()
            )
            if res.data:
                return res.data[0]["logged_at"]
            return None
        except Exception as e:
            print(f"[SUPABASE ERROR] {e}")

    conn = _get_sqlite_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT logged_at FROM hygiene_logs WHERE tag = ? ORDER BY logged_at DESC LIMIT 1",
        (tag,)
    )
    row = cur.fetchone()
    conn.close()
    return row[0] if row else None


def get_all_hygiene_history(limit: int = None, days: int = None, order: str = "desc") -> list:
    descending = (order.lower() == "desc")
    cutoff_iso = None
    if days is not None:
        cutoff_dt = datetime.now(timezone.utc) - timedelta(days=days)
        cutoff_iso = cutoff_dt.isoformat()

    if STORAGE_MODE == "supabase" and supabase:
        try:
            query = supabase.table("hygiene_logs").select("id, tag, logged_at")
            if cutoff_iso:
                query = query.gte("logged_at", cutoff_iso)
            query = query.order("logged_at", desc=descending)
            if limit:
                query = query.limit(limit)
            res = query.execute()
            return res.data or []
        except Exception as e:
            print(f"[SUPABASE ERROR] {e}")

    conn = _get_sqlite_conn()
    cur = conn.cursor()
    params = []
    sql = "SELECT id, tag, logged_at FROM hygiene_logs"
    if cutoff_iso:
        sql += " WHERE logged_at >= ?"
        params.append(cutoff_iso)
    sql += f" ORDER BY logged_at {'DESC' if descending else 'ASC'}"
    if limit:
        sql += " LIMIT ?"
        params.append(limit)

    cur.execute(sql, tuple(params))
    rows = cur.fetchall()
    conn.close()
    return [{"id": r[0], "tag": r[1], "logged_at": r[2]} for r in rows]


# ---------------------------------------------------------------------------
# 6. PHYSICAL EXERTION & NAP LOGGING
# ---------------------------------------------------------------------------
def log_exercise(duration_hours: float, intensity: str = "moderate", notes: str = "") -> bool:
    """Logs physical exertion (capped between 0.1h and 16.0h)."""
    now_utc = _get_now_utc_iso()

    try:
        conn = _get_sqlite_conn()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO exercise_logs (duration_hours, intensity, notes, logged_at, synced) VALUES (?, ?, ?, ?, 0)",
            (duration_hours, intensity, notes, now_utc)
        )
        row_id = cur.lastrowid
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[LOCAL DB ERROR] Failed to log exercise: {e}")
        return False

    if STORAGE_MODE == "supabase" and supabase:
        try:
            supabase.table("exercise_logs").insert({
                "duration_hours": duration_hours,
                "intensity": intensity,
                "notes": notes,
                "logged_at": now_utc
            }).execute()

            up_conn = _get_sqlite_conn()
            up_conn.execute("UPDATE exercise_logs SET synced = 1 WHERE id = ?", (row_id,))
            up_conn.commit()
            up_conn.close()
        except Exception as e:
            print(f"[BUFFER QUEUED] Exercise stored locally (Offline ID {row_id}): {e}")

    return True


def get_today_exercise_hours() -> float:
    local_now = time_manager.now()
    start_of_day_local = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    start_of_day_utc = start_of_day_local.astimezone(timezone.utc).isoformat()

    if STORAGE_MODE == "supabase" and supabase:
        try:
            res = (
                supabase.table("exercise_logs")
                .select("duration_hours")
                .gte("logged_at", start_of_day_utc)
                .execute()
            )
            rows = res.data or []
            return sum(float(r.get("duration_hours", 0.0)) for r in rows)
        except Exception as e:
            _check_supabase_error(e, "exercise_logs")

    try:
        conn = _get_sqlite_conn()
        cur = conn.cursor()
        cur.execute(
            "SELECT SUM(duration_hours) FROM exercise_logs WHERE logged_at >= ?",
            (start_of_day_utc,)
        )
        row = cur.fetchone()
        conn.close()
        return float(row[0]) if (row and row[0] is not None) else 0.0
    except Exception:
        return 0.0


def log_nap(duration_minutes: int, notes: str = "") -> bool:
    """Logs daytime power nap or recovery cycle."""
    now_utc = _get_now_utc_iso()

    try:
        conn = _get_sqlite_conn()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO nap_logs (duration_minutes, notes, logged_at, synced) VALUES (?, ?, ?, 0)",
            (duration_minutes, notes, now_utc)
        )
        row_id = cur.lastrowid
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[LOCAL DB ERROR] Failed to log nap: {e}")
        return False

    if STORAGE_MODE == "supabase" and supabase:
        try:
            supabase.table("nap_logs").insert({
                "duration_minutes": duration_minutes,
                "notes": notes,
                "logged_at": now_utc
            }).execute()

            up_conn = _get_sqlite_conn()
            up_conn.execute("UPDATE nap_logs SET synced = 1 WHERE id = ?", (row_id,))
            up_conn.commit()
            up_conn.close()
        except Exception as e:
            print(f"[BUFFER QUEUED] Nap stored locally (Offline ID {row_id}): {e}")

    return True


def get_today_naps() -> list:
    local_now = time_manager.now()
    start_of_day_local = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    start_of_day_utc = start_of_day_local.astimezone(timezone.utc).isoformat()

    if STORAGE_MODE == "supabase" and supabase:
        try:
            res = (
                supabase.table("nap_logs")
                .select("id, duration_minutes, notes, logged_at")
                .gte("logged_at", start_of_day_utc)
                .order("logged_at", desc=True)
                .execute()
            )
            return res.data or []
        except Exception as e:
            _check_supabase_error(e, "nap_logs")

    try:
        conn = _get_sqlite_conn()
        cur = conn.cursor()
        cur.execute(
            "SELECT id, duration_minutes, notes, logged_at FROM nap_logs WHERE logged_at >= ? ORDER BY logged_at DESC",
            (start_of_day_utc,)
        )
        rows = cur.fetchall()
        conn.close()
        return [
            {"id": r[0], "duration_minutes": r[1], "notes": r[2], "logged_at": r[3]}
            for r in rows
        ]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# 7. CROSS-TABLE ROLLBACK (UNDO LAST EVENT)
# ---------------------------------------------------------------------------
def undo_last_intake() -> dict:
    """Purges whichever event occurred most recently across intake, hygiene, exercise, or naps."""
    candidates = []

    if STORAGE_MODE == "supabase" and supabase:
        try:
            res_i = supabase.table("intake_logs").select("id, type, amount, tag, logged_at").order("logged_at", desc=True).limit(1).execute()
            if res_i.data:
                candidates.append((_parse_timestamp(res_i.data[0]["logged_at"]), "intake_logs", res_i.data[0]))

            res_h = supabase.table("hygiene_logs").select("id, tag, logged_at").order("logged_at", desc=True).limit(1).execute()
            if res_h.data:
                item = res_h.data[0]
                item["type"] = "hygiene"
                item["amount"] = 1.0
                candidates.append((_parse_timestamp(item["logged_at"]), "hygiene_logs", item))

            try:
                res_e = supabase.table("exercise_logs").select("id, duration_hours, intensity, logged_at").order("logged_at", desc=True).limit(1).execute()
                if res_e.data:
                    item = res_e.data[0]
                    item["type"] = "exercise"
                    item["amount"] = item.get("duration_hours", 0.0)
                    item["tag"] = f"workout ({item.get('intensity', 'moderate')})"
                    candidates.append((_parse_timestamp(item["logged_at"]), "exercise_logs", item))
            except Exception as e:
                _check_supabase_error(e, "exercise_logs")

            try:
                res_n = supabase.table("nap_logs").select("id, duration_minutes, logged_at").order("logged_at", desc=True).limit(1).execute()
                if res_n.data:
                    item = res_n.data[0]
                    item["type"] = "nap"
                    item["amount"] = item.get("duration_minutes", 0)
                    item["tag"] = "power nap"
                    candidates.append((_parse_timestamp(item["logged_at"]), "nap_logs", item))
            except Exception as e:
                _check_supabase_error(e, "nap_logs")

            if candidates:
                candidates.sort(key=lambda c: c[0], reverse=True)
                _, tbl, target = candidates[0]
                supabase.table(tbl).delete().eq("id", target["id"]).execute()
                return target
        except Exception as e:
            print(f"[SUPABASE ROLLBACK ERROR] {e}")

    conn = _get_sqlite_conn()
    cur = conn.cursor()

    cur.execute("SELECT id, type, amount, tag, logged_at FROM intake_logs ORDER BY logged_at DESC LIMIT 1")
    r_i = cur.fetchone()
    if r_i:
        candidates.append((
            _parse_timestamp(r_i[4]), "intake_logs",
            {"id": r_i[0], "type": r_i[1], "amount": r_i[2], "tag": r_i[3], "logged_at": r_i[4]}
        ))

    cur.execute("SELECT id, tag, logged_at FROM hygiene_logs ORDER BY logged_at DESC LIMIT 1")
    r_h = cur.fetchone()
    if r_h:
        candidates.append((
            _parse_timestamp(r_h[2]), "hygiene_logs",
            {"id": r_h[0], "type": "hygiene", "amount": 1.0, "tag": r_h[1], "logged_at": r_h[2]}
        ))

    cur.execute("SELECT id, duration_hours, intensity, logged_at FROM exercise_logs ORDER BY logged_at DESC LIMIT 1")
    r_e = cur.fetchone()
    if r_e:
        candidates.append((
            _parse_timestamp(r_e[3]), "exercise_logs",
            {"id": r_e[0], "type": "exercise", "amount": r_e[1], "tag": f"workout ({r_e[2]})", "logged_at": r_e[3]}
        ))

    cur.execute("SELECT id, duration_minutes, logged_at FROM nap_logs ORDER BY logged_at DESC LIMIT 1")
    r_n = cur.fetchone()
    if r_n:
        candidates.append((
            _parse_timestamp(r_n[2]), "nap_logs",
            {"id": r_n[0], "type": "nap", "amount": r_n[1], "tag": "power nap", "logged_at": r_n[2]}
        ))

    if not candidates:
        conn.close()
        return None

    candidates.sort(key=lambda c: c[0], reverse=True)
    _, tbl, target = candidates[0]

    cur.execute(f"DELETE FROM {tbl} WHERE id = ?", (target["id"],))
    conn.commit()
    conn.close()
    return target


# ---------------------------------------------------------------------------
# 8. TOTALS & TELEMETRY TIMESTAMPS
# ---------------------------------------------------------------------------
def get_today_totals() -> dict:
    local_now = time_manager.now()
    start_of_day_local = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    start_of_day_utc = start_of_day_local.astimezone(timezone.utc).isoformat()

    if STORAGE_MODE == "supabase" and supabase:
        try:
            res = supabase.table("intake_logs").select("type, amount").gte("logged_at", start_of_day_utc).execute()
            rows = res.data or []
            water_ml = sum(r["amount"] for r in rows if r["type"] == "hydration")
            # Meals count as 1.0, snacks count as 0.5
            meals_count = sum(r["amount"] for r in rows if r["type"] in ("meal", "snack"))
            return {"water_ml": water_ml, "meals_count": meals_count}
        except Exception as e:
            print(f"[SUPABASE ERROR] {e}")

    conn = _get_sqlite_conn()
    cur = conn.cursor()
    cur.execute("SELECT type, amount FROM intake_logs WHERE logged_at >= ?", (start_of_day_utc,))
    rows = cur.fetchall()
    conn.close()

    water_ml = sum(r[1] for r in rows if r[0] == "hydration")
    meals_count = sum(r[1] for r in rows if r[0] in ("meal", "snack"))
    return {"water_ml": water_ml, "meals_count": meals_count}


def get_last_intake_times() -> dict:
    last_times = {"water": None, "meal": None}
    if STORAGE_MODE == "supabase" and supabase:
        try:
            w = supabase.table("intake_logs").select("logged_at").eq("type", "hydration").order("logged_at", desc=True).limit(1).execute()
            if w.data:
                last_times["water"] = w.data[0]["logged_at"]
            m = supabase.table("intake_logs").select("logged_at").eq("type", "meal").order("logged_at", desc=True).limit(1).execute()
            if m.data:
                last_times["meal"] = m.data[0]["logged_at"]
            return last_times
        except Exception as e:
            print(f"[SUPABASE ERROR] {e}")

    conn = _get_sqlite_conn()
    cur = conn.cursor()
    cur.execute("SELECT logged_at FROM intake_logs WHERE type = 'hydration' ORDER BY logged_at DESC LIMIT 1")
    w_row = cur.fetchone()
    if w_row:
        last_times["water"] = w_row[0]

    cur.execute("SELECT logged_at FROM intake_logs WHERE type = 'meal' ORDER BY logged_at DESC LIMIT 1")
    m_row = cur.fetchone()
    if m_row:
        last_times["meal"] = m_row[0]
    conn.close()

    return last_times


def get_last_timestamps():
    times = get_last_intake_times()
    return times.get("water"), times.get("meal")


# ---------------------------------------------------------------------------
# 9. SLEEP LOGGING
# ---------------------------------------------------------------------------
def _parse_input_datetime(ts_str: str) -> datetime:
    """Parses user input sleep/wake timestamps across all supported formats."""
    clean_str = str(ts_str).strip()
    formats = (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%d/%m/%Y %I:%M %p",
        "%d/%m/%Y %I:%M%p",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y %H:%M",
        "%Y/%m/%d %H:%M",
    )
    for f in formats:
        try:
            return datetime.strptime(clean_str, f)
        except ValueError:
            continue

    try:
        iso_clean = clean_str.replace("Z", "+00:00")
        return datetime.fromisoformat(iso_clean)
    except Exception:
        pass

    raise ValueError(f"Unrecognized date format: '{clean_str}'. Supported: 'YYYY-MM-DD HH:MM' or 'DD/MM/YYYY hh:mm AM/PM'")


def log_sleep(sleep_time: str, wake_time: str, interruptions: int = 0, notes: str = "") -> float:
    """
    Logs a completed sleep cycle into both local SQLite and Supabase simultaneously.
    """
    def parse_dt(raw_val: str) -> datetime:
        clean = str(raw_val).strip()
        supported_formats = (
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%d/%m/%Y %I:%M %p",
            "%d/%m/%Y %I:%M%p",
            "%d/%m/%Y %H:%M:%S",
            "%d/%m/%Y %H:%M",
            "%Y/%m/%d %H:%M",
        )
        for pattern in supported_formats:
            try:
                return datetime.strptime(clean, pattern)
            except ValueError:
                continue

        try:
            return datetime.fromisoformat(clean.replace("Z", "+00:00"))
        except Exception:
            pass

        raise ValueError(f"Invalid timestamp format: '{clean}'")

    t_sleep_naive = parse_dt(sleep_time)
    t_wake_naive = parse_dt(wake_time)

    duration = max(0.0, (t_wake_naive - t_sleep_naive).total_seconds() / 3600.0)
    now_utc = _get_now_utc_iso()

    user_tz = time_manager.target_tz
    if t_sleep_naive.tzinfo is None:
        t_sleep_utc = t_sleep_naive.replace(tzinfo=user_tz).astimezone(timezone.utc).isoformat()
    else:
        t_sleep_utc = t_sleep_naive.astimezone(timezone.utc).isoformat()

    if t_wake_naive.tzinfo is None:
        t_wake_utc = t_wake_naive.replace(tzinfo=user_tz).astimezone(timezone.utc).isoformat()
    else:
        t_wake_utc = t_wake_naive.astimezone(timezone.utc).isoformat()

    # 1. Primary write: Local SQLite (Instant)
    try:
        conn = _get_sqlite_conn()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO sleep_logs (sleep_time, wake_time, duration_hours, interruptions, quality_notes, logged_at, synced)
            VALUES (?, ?, ?, ?, ?, ?, 0)
        """, (t_sleep_utc, t_wake_utc, round(duration, 2), interruptions, notes, now_utc))
        row_id = cur.lastrowid
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[LOCAL DB ERROR] Failed to record sleep locally: {e}")
        return duration

    # 2. Cloud mirror: Supabase
    if STORAGE_MODE == "supabase" and supabase:
        try:
            supabase.table("sleep_logs").insert({
                "sleep_time": t_sleep_utc,
                "wake_time": t_wake_utc,
                "interruptions": interruptions,
                "quality_notes": notes,
                "duration_hours": round(duration, 2),
                "logged_at": now_utc
            }).execute()

            up_conn = _get_sqlite_conn()
            up_conn.execute("UPDATE sleep_logs SET synced = 1 WHERE id = ?", (row_id,))
            up_conn.commit()
            up_conn.close()
        except Exception as e:
            print(f"[BUFFER QUEUED] Sleep stored locally (Offline ID {row_id}): {e}")

    return duration


# ---------------------------------------------------------------------------
# 10. ARCHIVES & HISTORICAL TELEMETRY FETCHERS
# ---------------------------------------------------------------------------
def get_all_intake_history(limit: int = None, days: int = None, order: str = "desc") -> list:
    descending = (order.lower() == "desc")
    cutoff_iso = None
    if days is not None:
        cutoff_dt = datetime.now(timezone.utc) - timedelta(days=days)
        cutoff_iso = cutoff_dt.isoformat()

    if STORAGE_MODE == "supabase" and supabase:
        try:
            query = supabase.table("intake_logs").select("id, type, amount, tag, logged_at")
            if cutoff_iso:
                query = query.gte("logged_at", cutoff_iso)
            query = query.order("logged_at", desc=descending)
            if limit:
                query = query.limit(limit)
            res = query.execute()
            return res.data or []
        except Exception as e:
            print(f"[SUPABASE ERROR] {e}")

    conn = _get_sqlite_conn()
    cur = conn.cursor()
    params = []
    sql = "SELECT id, type, amount, tag, logged_at FROM intake_logs"
    if cutoff_iso:
        sql += " WHERE logged_at >= ?"
        params.append(cutoff_iso)
    sql += f" ORDER BY logged_at {'DESC' if descending else 'ASC'}"
    if limit:
        sql += " LIMIT ?"
        params.append(limit)

    cur.execute(sql, tuple(params))
    rows = cur.fetchall()
    conn.close()
    return [{"id": r[0], "type": r[1], "amount": r[2], "tag": r[3], "logged_at": r[4]} for r in rows]


def get_all_exercise_history(limit: int = None, days: int = None, order: str = "desc") -> list:
    descending = (order.lower() == "desc")
    cutoff_iso = None
    if days is not None:
        cutoff_dt = datetime.now(timezone.utc) - timedelta(days=days)
        cutoff_iso = cutoff_dt.isoformat()

    if STORAGE_MODE == "supabase" and supabase:
        try:
            query = supabase.table("exercise_logs").select("id, duration_hours, intensity, notes, logged_at")
            if cutoff_iso:
                query = query.gte("logged_at", cutoff_iso)
            query = query.order("logged_at", desc=descending)
            if limit:
                query = query.limit(limit)
            res = query.execute()
            return res.data or []
        except Exception as e:
            _check_supabase_error(e, "exercise_logs")

    try:
        conn = _get_sqlite_conn()
        cur = conn.cursor()
        params = []
        sql = "SELECT id, duration_hours, intensity, notes, logged_at FROM exercise_logs"
        if cutoff_iso:
            sql += " WHERE logged_at >= ?"
            params.append(cutoff_iso)
        sql += f" ORDER BY logged_at {'DESC' if descending else 'ASC'}"
        if limit:
            sql += " LIMIT ?"
            params.append(limit)
        cur.execute(sql, tuple(params))
        rows = cur.fetchall()
        conn.close()
        return [
            {"id": r[0], "duration_hours": r[1], "intensity": r[2], "notes": r[3], "logged_at": r[4]}
            for r in rows
        ]
    except Exception:
        return []


def get_all_nap_history(limit: int = None, days: int = None, order: str = "desc") -> list:
    descending = (order.lower() == "desc")
    cutoff_iso = None
    if days is not None:
        cutoff_dt = datetime.now(timezone.utc) - timedelta(days=days)
        cutoff_iso = cutoff_dt.isoformat()

    if STORAGE_MODE == "supabase" and supabase:
        try:
            query = supabase.table("nap_logs").select("id, duration_minutes, notes, logged_at")
            if cutoff_iso:
                query = query.gte("logged_at", cutoff_iso)
            query = query.order("logged_at", desc=descending)
            if limit:
                query = query.limit(limit)
            res = query.execute()
            return res.data or []
        except Exception as e:
            _check_supabase_error(e, "nap_logs")

    try:
        conn = _get_sqlite_conn()
        cur = conn.cursor()
        params = []
        sql = "SELECT id, duration_minutes, notes, logged_at FROM nap_logs"
        if cutoff_iso:
            sql += " WHERE logged_at >= ?"
            params.append(cutoff_iso)
        sql += f" ORDER BY logged_at {'DESC' if descending else 'ASC'}"
        if limit:
            sql += " LIMIT ?"
            params.append(limit)
        cur.execute(sql, tuple(params))
        rows = cur.fetchall()
        conn.close()
        return [
            {"id": r[0], "duration_minutes": r[1], "notes": r[2], "logged_at": r[3]}
            for r in rows
        ]
    except Exception:
        return []


def get_all_sleep_history(limit: int = None, days: int = None, order: str = "desc") -> list:
    descending = (order.lower() == "desc")
    cutoff_str = None
    if days is not None:
        cutoff_dt = datetime.now(timezone.utc) - timedelta(days=days)
        cutoff_str = cutoff_dt.strftime("%Y-%m-%d")

    if STORAGE_MODE == "supabase" and supabase:
        try:
            query = supabase.table("sleep_logs").select("id, sleep_time, wake_time, duration_hours, interruptions, quality_notes, logged_at")
            if cutoff_str:
                query = query.gte("sleep_time", cutoff_str)
            query = query.order("sleep_time", desc=descending)
            if limit:
                query = query.limit(limit)
            res = query.execute()
            return res.data or []
        except Exception as e:
            print(f"[SUPABASE ERROR] {e}")

    conn = _get_sqlite_conn()
    cur = conn.cursor()
    params = []
    sql = "SELECT id, sleep_time, wake_time, duration_hours, interruptions, quality_notes, logged_at FROM sleep_logs"
    if cutoff_str:
        sql += " WHERE sleep_time >= ?"
        params.append(cutoff_str)
    sql += f" ORDER BY sleep_time {'DESC' if descending else 'ASC'}"
    if limit:
        sql += " LIMIT ?"
        params.append(limit)

    cur.execute(sql, tuple(params))
    rows = cur.fetchall()
    conn.close()
    return [
        {"id": r[0], "sleep_time": r[1], "wake_time": r[2], "duration_hours": r[3], "interruptions": r[4], "quality_notes": r[5], "logged_at": r[6]}
        for r in rows
    ]


def delete_record_by_id(table_name: str, record_id) -> bool:
    if STORAGE_MODE == "supabase" and supabase:
        try:
            supabase.table(table_name).delete().eq("id", record_id).execute()
            return True
        except Exception as e:
            print(f"[SUPABASE ERROR] {e}")

    try:
        conn = _get_sqlite_conn()
        cur = conn.cursor()
        cur.execute(f"DELETE FROM {table_name} WHERE id = ?", (record_id,))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"[LOCAL DB ERROR] {e}")
        return False