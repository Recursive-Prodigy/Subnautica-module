from datetime import datetime, timezone
import database
from time_sync import time_manager
from config_manager import load_config, DEFAULT_CONFIG

class HUDState:
    def __init__(self):
        self.reload_config()

    def reload_config(self):
        cfg = load_config() or DEFAULT_CONFIG
        self.target_water_ml = int(cfg.get("target_water_ml", 2500))
        self.target_meals = int(cfg.get("target_meals", 4))
        self.hydration_interval_min = int(cfg.get("hydration_interval_min", 75))
        self.meal_interval_min = int(cfg.get("meal_interval_min", 210))
        self.sleep_start_h = int(cfg.get("sleep_start_hour", 23))
        self.sleep_start_m = int(cfg.get("sleep_start_minute", 0))
        self.sleep_end_h = int(cfg.get("sleep_end_hour", 7))
        self.sleep_end_m = int(cfg.get("sleep_end_minute", 0))

    def is_sleep_window(self) -> bool:
        now_dt = time_manager.now()
        cur_min = now_dt.hour * 60 + now_dt.minute
        start_min = self.sleep_start_h * 60 + self.sleep_start_m
        end_min = self.sleep_end_h * 60 + self.sleep_end_m

        if start_min > end_min:
            # Crosses midnight (e.g. 23:00 to 07:00)
            return cur_min >= start_min or cur_min < end_min
        return start_min <= cur_min < end_min

    def evaluate_hydration(self):
        totals = database.get_today_totals()
        w_ml = totals.get("water_ml", 0)
        times = database.get_last_intake_times()
        last_w = times.get("water")

        if w_ml >= self.target_water_ml:
            return "TARGET_REACHED", 0

        if not last_w:
            return "DUE", 999

        try:
            t_last = datetime.fromisoformat(last_w.replace("Z", "+00:00"))
            mins = int((datetime.now(timezone.utc) - t_last).total_seconds() / 60)
        except Exception:
            mins = 999

        if mins >= (self.hydration_interval_min + 45):
            return "OVERDUE", mins
        elif mins >= self.hydration_interval_min:
            return "DUE", mins
        return "OPTIMAL", mins

    def evaluate_nutrition(self):
        totals = database.get_today_totals()
        m_cnt = totals.get("meals_count", 0)
        times = database.get_last_intake_times()
        last_m = times.get("meal")

        if m_cnt >= self.target_meals:
            return "TARGET_REACHED", 0

        if not last_m:
            return "DUE", 999

        try:
            t_last = datetime.fromisoformat(last_m.replace("Z", "+00:00"))
            mins = int((datetime.now(timezone.utc) - t_last).total_seconds() / 60)
        except Exception:
            mins = 999

        if mins >= (self.meal_interval_min + 90):
            return "OVERDUE", mins
        elif mins >= self.meal_interval_min:
            return "DUE", mins
        return "OPTIMAL", mins