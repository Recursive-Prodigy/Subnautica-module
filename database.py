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


# --- INTAKE LOGGING ---
def log_water(amount_ml: float = 250.0):
    now_utc = datetime.now(timezone.utc).isoformat()
    if STORAGE_MODE == "supabase" and supabase:
        try:
            supabase.table("intake_logs").insert({
                "type": "hydration",
                "amount": amount_ml,
                "tag": "Hydration Fluid",
                "logged_at": now_utc
            }).execute()
            return
        except Exception as e:
            print(f"[SUPABASE ERROR] {e}")

    conn = sqlite3.connect(LOCAL_DB_PATH)
    cur = conn.cursor()
    cur.execute("INSERT INTO intake_logs (type, amount, tag, logged_at) VALUES (?, ?, ?, ?)",
                ("hydration", amount_ml, "Hydration Fluid", now_utc))
    conn.commit()
    conn.close()


def log_meal(tag: str = "Standard Ration"):
    now_utc = datetime.now(timezone.utc).isoformat()
    if STORAGE_MODE == "supabase" and supabase:
        try:
            supabase.table("intake_logs").insert({
                "type": "meal",
                "amount": 1.0,
                "tag": tag,
                "logged_at": now_utc
            }).execute()
            return
        except Exception as e:
            print(f"[SUPABASE ERROR] {e}")

    conn = sqlite3.connect(LOCAL_DB_PATH)
    cur = conn.cursor()
    cur.execute("INSERT INTO intake_logs (type, amount, tag, logged_at) VALUES (?, ?, ?, ?)",
                ("meal", 1.0, tag, now_utc))
    conn.commit()
    conn.close()


def undo_last_intake() -> dict:
    if STORAGE_MODE == "supabase" and supabase:
        try:
            res = supabase.table("intake_logs").select("id, type, amount, tag").order("logged_at", desc=True).limit(1).execute()
            if res.data:
                latest = res.data[0]
                supabase.table("intake_logs").delete().eq("id", latest["id"]).execute()
                return latest
        except Exception as e:
            print(f"[SUPABASE ERROR] {e}")
        return None

    conn = sqlite3.connect(LOCAL_DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT id, type, amount, tag FROM intake_logs ORDER BY logged_at DESC LIMIT 1")
    row = cur.fetchone()
    if not row:
        conn.close()
        return None
    latest = {"id": row[0], "type": row[1], "amount": row[2], "tag": row[3]}
    cur.execute("DELETE FROM intake_logs WHERE id = ?", (latest["id"],))
    conn.commit()
    conn.close()
    return latest


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


# --- ARCHIVES & TELEMETRY VIEWER (WITH WINDOW & ORDER TOGGLES) ---
def get_all_intake_history(limit: int = None, days: int = None, order: str = "desc") -> list:
    """
    Fetches intake logs.
    - days: Filter by rolling days (e.g. 7). None fetches lifetime history.
    - order: 'desc' (newest first) or 'asc' (oldest first).
    - limit: Row limit. None fetches all matching records.
    """
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
    """
    Fetches sleep logs.
    - days: Filter by rolling days (e.g. 7). None fetches lifetime history.
    - order: 'desc' (newest first) or 'asc' (oldest first).
    - limit: Row limit. None fetches all matching records.
    """
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