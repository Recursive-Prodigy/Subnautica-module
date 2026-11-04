import os
import json
from datetime import datetime

CONFIG_FILE = os.path.join(os.path.dirname(__file__), "pda_config.json")

def get_system_detected_tz() -> str:
    try:
        local_tz = datetime.now().astimezone().tzinfo
        tz_name = getattr(local_tz, "key", None) or str(local_tz)
        if tz_name and "/" in tz_name:
            return tz_name
    except Exception:
        pass
    return "UTC"

DEFAULT_CONFIG = {
    "timezone": get_system_detected_tz(),
    "storage_mode": "local",
    "supabase_url": "",
    "supabase_key": "",
    "target_water_ml": 2500,
    "target_meals": 4,
    "hydration_interval_min": 75,
    "meal_interval_min": 210,
    "sleep_start_hour": 23,
    "sleep_start_minute": 0,
    "sleep_end_hour": 7,
    "sleep_end_minute": 0
}

def load_config() -> dict:
    if not os.path.exists(CONFIG_FILE):
        return None
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            merged = DEFAULT_CONFIG.copy()
            merged.update(data)
            return merged
    except Exception:
        return DEFAULT_CONFIG.copy()

def save_config(cfg: dict) -> bool:
    try:
        merged = DEFAULT_CONFIG.copy()
        merged.update(cfg)
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(merged, f, indent=4)
        return True
    except Exception as e:
        print(f"[CONFIG SAVE ERROR] {e}")
        return False