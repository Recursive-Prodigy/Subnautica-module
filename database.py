import json
import os
import sqlite3
from datetime import datetime, time, timezone, timedelta
from time_sync import time_manager

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "pda_config.json")
LOCAL_DB_PATH = os.path.join(os.path.dirname(__file__), "pda_local.db")

# 1. Inspect configuration
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


# 2. SQLite local tables bootstrap
def _init_local_db():
    conn = sqlite3.connect(LOCAL_DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS intake_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT NOT NULL,
            amount REAL NOT NULL,
            tag TEXT,
            logged_at TEXT NOT NULL
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS hygiene_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tag TEXT NOT NULL,
            logged_at TEXT NOT NULL
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
            logged_at TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()

if STORAGE_MODE == "local":
    _init_local_db()


# --- HELPER: ROBUST TIMESTAMP COMPARISON ---
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


# --- INTAKE LOGGING (WATER & MEALS) ---
def log_intake(intake_type: str, amount: float = 1.0, tag: str = ""):
    now_utc = datetime.now(timezone.utc).isoformat()
    if STORAGE_MODE == "supabase" and supabase:
        try:
            supabase.table("intake_logs").insert({
                "type": intake_type,
                "amount": amount,
                "tag": tag,
                "logged_at": now_utc
            }).execute()
            return
        except Exception as e:
            print(f"[SUPABASE ERROR] {e}")

    conn = sqlite3.connect(LOCAL_DB_PATH)
    cur = conn.cursor()
    cur.execute("INSERT INTO intake_logs (type, amount, tag, logged_at) VALUES (?, ?, ?, ?)",
                (intake_type, amount, tag, now_utc))
    conn.commit()
    conn.close()


def log_water(amount_ml: float = 250.0):
    log_intake("hydration", amount_ml, "Hydration Fluid")


def log_meal(tag: str = "Standard Ration"):
    log_intake("meal", 1.0, tag)


# --- HYGIENE LOGGING (BRUSHING & SHOWER) ---
def log_hygiene(tag: str = "brushing"):
    """Inserts strictly into the dedicated hygiene_logs table."""
    now_utc = datetime.now(timezone.utc).isoformat()
    if STORAGE_MODE == "supabase" and supabase:
        try:
            supabase.table("hygiene_logs").insert({
                "tag": tag,
                "logged_at": now_utc
            }).execute()
            return
        except Exception as e:
            print(f"[SUPABASE ERROR] {e}")

    conn = sqlite3.connect(LOCAL_DB_PATH)
    cur = conn.cursor()
    cur.execute("INSERT INTO hygiene_logs (tag, logged_at) VALUES (?, ?)", (tag, now_utc))
    conn.commit()
    conn.close()


def get_hygiene_today_count(tag: str = "brushing") -> int:
    """Counts entries for today strictly from hygiene_logs."""
    local_now = time_manager.now()
    start_of_day_local = datetime.combine(local_now.date(), time.min, tzinfo=local_now.tzinfo)
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

    conn = sqlite3.connect(LOCAL_DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "SELECT COUNT(*) FROM hygiene_logs WHERE tag = ? AND logged_at >= ?",
        (tag, start_of_day_utc)
    )
    count = cur.fetchone()[0]
    conn.close()
    return count


def get_last_hygiene_time(tag: str = "shower"):
    """Fetches the latest entry timestamp strictly from hygiene_logs."""
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

    conn = sqlite3.connect(LOCAL_DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "SELECT logged_at FROM hygiene_logs WHERE tag = ? ORDER BY logged_at DESC LIMIT 1",
        (tag,)
    )
    row = cur.fetchone()
    conn.close()
    return row[0] if row else None


def get_all_hygiene_history(limit: int = None, days: int = None, order: str = "desc") -> list:
    """Fetches historical records from hygiene_logs."""
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

    conn = sqlite3.connect(LOCAL_DB_PATH)
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


# --- CROSS-TABLE ROLLBACK (UNDO LAST) ---
def undo_last_intake() -> dict:
    """Purges whichever telemetry entry occurred most recently across intake_logs and hygiene_logs."""
    last_intake = None
    last_hygiene = None

    if STORAGE_MODE == "supabase" and supabase:
        try:
            res_i = supabase.table("intake_logs").select("id, type, amount, tag, logged_at").order("logged_at", desc=True).limit(1).execute()
            if res_i.data:
                last_intake = res_i.data[0]

            res_h = supabase.table("hygiene_logs").select("id, tag, logged_at").order("logged_at", desc=True).limit(1).execute()
            if res_h.data:
                last_hygiene = res_h.data[0]
                last_hygiene["type"] = "hygiene"
                last_hygiene["amount"] = 1.0

            t_i = _parse_timestamp(last_intake["logged_at"]) if last_intake else -1.0
            t_h = _parse_timestamp(last_hygiene["logged_at"]) if last_hygiene else -1.0

            if t_i < 0 and t_h < 0:
                return None

            target = last_intake if t_i >= t_h else last_hygiene
            tbl = "intake_logs" if target["type"] != "hygiene" else "hygiene_logs"
            supabase.table(tbl).delete().eq("id", target["id"]).execute()
            return target
        except Exception as e:
            print(f"[SUPABASE ERROR] {e}")
        return None

    # Local SQLite fallback
    conn = sqlite3.connect(LOCAL_DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT id, type, amount, tag, logged_at FROM intake_logs ORDER BY logged_at DESC LIMIT 1")
    row_i = cur.fetchone()
    if row_i:
        last_intake = {"id": row_i[0], "type": row_i[1], "amount": row_i[2], "tag": row_i[3], "logged_at": row_i[4]}

    cur.execute("SELECT id, tag, logged_at FROM hygiene_logs ORDER BY logged_at DESC LIMIT 1")
    row_h = cur.fetchone()
    if row_h:
        last_hygiene = {"id": row_h[0], "type": "hygiene", "amount": 1.0, "tag": row_h[1], "logged_at": row_h[2]}

    t_i = _parse_timestamp(last_intake["logged_at"]) if last_intake else -1.0
    t_h = _parse_timestamp(last_hygiene["logged_at"]) if last_hygiene else -1.0

    if t_i < 0 and t_h < 0:
        conn.close()
        return None

    target = last_intake if t_i >= t_h else last_hygiene
    tbl = "intake_logs" if target["type"] != "hygiene" else "hygiene_logs"
    cur.execute(f"DELETE FROM {tbl} WHERE id = ?", (target["id"],))
    conn.commit()
    conn.close()
    return target


# --- TOTALS & LAST TIMESTAMPS ---
def get_today_totals() -> dict:
    local_now = time_manager.now()
    start_of_day_local = datetime.combine(local_now.date(), time.min, tzinfo=local_now.tzinfo)
    start_of_day_utc = start_of_day_local.astimezone(timezone.utc).isoformat()

    if STORAGE_MODE == "supabase" and supabase:
        try:
            res = supabase.table("intake_logs").select("type, amount").gte("logged_at", start_of_day_utc).execute()
            rows = res.data or []
            water_ml = sum(r["amount"] for r in rows if r["type"] == "hydration")
            meals_count = sum(1 for r in rows if r["type"] == "meal")
            return {"water_ml": water_ml, "meals_count": meals_count}
        except Exception as e:
            print(f"[SUPABASE ERROR] {e}")

    conn = sqlite3.connect(LOCAL_DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT type, amount FROM intake_logs WHERE logged_at >= ?", (start_of_day_utc,))
    rows = cur.fetchall()
    conn.close()

    water_ml = sum(r[1] for r in rows if r[0] == "hydration")
    meals_count = sum(1 for r in rows if r[0] == "meal")
    return {"water_ml": water_ml, "meals_count": meals_count}


def get_last_intake_times() -> dict:
    last_times = {"water": None, "meal": None}
    if STORAGE_MODE == "supabase" and supabase:
        try:
            w = supabase.table("intake_logs").select("logged_at").eq("type", "hydration").order("logged_at", desc=True).limit(1).execute()
            if w.data: last_times["water"] = w.data[0]["logged_at"]
            m = supabase.table("intake_logs").select("logged_at").eq("type", "meal").order("logged_at", desc=True).limit(1).execute()
            if m.data: last_times["meal"] = m.data[0]["logged_at"]
            return last_times
        except Exception as e:
            print(f"[SUPABASE ERROR] {e}")

    conn = sqlite3.connect(LOCAL_DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT logged_at FROM intake_logs WHERE type = 'hydration' ORDER BY logged_at DESC LIMIT 1")
    w_row = cur.fetchone()
    if w_row: last_times["water"] = w_row[0]

    cur.execute("SELECT logged_at FROM intake_logs WHERE type = 'meal' ORDER BY logged_at DESC LIMIT 1")
    m_row = cur.fetchone()
    if m_row: last_times["meal"] = m_row[0]
    conn.close()

    return last_times


def get_last_timestamps():
    times = get_last_intake_times()
    return times.get("water"), times.get("meal")


# --- SLEEP LOGGING ---
def log_sleep(sleep_time: str, wake_time: str, interruptions: int = 0, notes: str = "") -> float:
    fmt = "%Y-%m-%d %H:%M"
    t_sleep = datetime.strptime(sleep_time, fmt)
    t_wake = datetime.strptime(wake_time, fmt)
    duration = max(0.0, (t_wake - t_sleep).total_seconds() / 3600.0)
    now_utc = datetime.now(timezone.utc).isoformat()

    if STORAGE_MODE == "supabase" and supabase:
        try:
            supabase.table("sleep_logs").insert({
                "sleep_time": sleep_time,
                "wake_time": wake_time,
                "interruptions": interruptions,
                "quality_notes": notes,
                "duration_hours": round(duration, 2),
                "logged_at": now_utc
            }).execute()
            return duration
        except Exception as e:
            print(f"[SUPABASE ERROR] {e}")

    conn = sqlite3.connect(LOCAL_DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO sleep_logs (sleep_time, wake_time, duration_hours, interruptions, quality_notes, logged_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (sleep_time, wake_time, round(duration, 2), interruptions, notes, now_utc))
    conn.commit()
    conn.close()
    return duration


# --- ARCHIVES & TELEMETRY VIEWER ---
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

    conn = sqlite3.connect(LOCAL_DB_PATH)
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

    conn = sqlite3.connect(LOCAL_DB_PATH)
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
    return [{"id": r[0], "sleep_time": r[1], "wake_time": r[2], "duration_hours": r[3], "interruptions": r[4], "quality_notes": r[5], "logged_at": r[6]} for r in rows]


def delete_record_by_id(table_name: str, record_id) -> bool:
    if STORAGE_MODE == "supabase" and supabase:
        try:
            supabase.table(table_name).delete().eq("id", record_id).execute()
            return True
        except Exception as e:
            print(f"[SUPABASE ERROR] {e}")

    try:
        conn = sqlite3.connect(LOCAL_DB_PATH)
        cur = conn.cursor()
        cur.execute(f"DELETE FROM {table_name} WHERE id = ?", (record_id,))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"[LOCAL DB ERROR] {e}")
        return False