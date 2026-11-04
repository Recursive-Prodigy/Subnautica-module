import sqlite3
import json
import os
from supabase import create_client

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "pda_config.json")
LOCAL_DB_PATH = os.path.join(os.path.dirname(__file__), "pda_local.db")

def sync_local_to_supabase():
    if not os.path.exists(CONFIG_PATH):
        print("[ERROR] pda_config.json not found.")
        return

    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    url = cfg.get("supabase_url")
    key = cfg.get("supabase_key")

    if not url or not key:
        print("[ERROR] Missing Supabase URL or Key in pda_config.json.")
        return

    print("Establishing connection to Alterra Supabase Cloud Cluster...")
    client = create_client(url, key)

    conn = sqlite3.connect(LOCAL_DB_PATH)
    cur = conn.cursor()

    # 1. Sync Intake Logs
    print("\nExtracting local intake logs...")
    cur.execute("SELECT type, amount, tag, logged_at FROM intake_logs")
    intake_rows = cur.fetchall()
    
    intake_payload = [
        {"type": r[0], "amount": r[1], "tag": r[2], "logged_at": r[3]}
        for r in intake_rows
    ]

    if intake_payload:
        try:
            client.table("intake_logs").insert(intake_payload).execute()
            print(f"-> Successfully uploaded {len(intake_payload)} intake entries to Supabase.")
        except Exception as e:
            print(f"[FAIL] Could not upload intake logs: {e}")
    else:
        print("-> No local intake logs to migrate.")

    # 2. Sync Sleep Logs
    print("\nExtracting local sleep logs...")
    cur.execute("SELECT sleep_time, wake_time, duration_hours, interruptions, quality_notes, logged_at FROM sleep_logs")
    sleep_rows = cur.fetchall()

    sleep_payload = [
        {
            "sleep_time": r[0],
            "wake_time": r[1],
            "duration_hours": r[2],
            "interruptions": r[3],
            "quality_notes": r[4],
            "logged_at": r[5]
        }
        for r in sleep_rows
    ]

    if sleep_payload:
        try:
            client.table("sleep_logs").insert(sleep_payload).execute()
            print(f"-> Successfully uploaded {len(sleep_payload)} sleep records to Supabase.")
        except Exception as e:
            print(f"[FAIL] Could not upload sleep logs: {e}")
    else:
        print("-> No local sleep records to migrate.")

    conn.close()
    print("\n[COMPLETE] Telemetry sync finished. You can now switch storage_mode to 'supabase'.")

if __name__ == "__main__":
    sync_local_to_supabase()