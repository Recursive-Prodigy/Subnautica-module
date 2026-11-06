import os
import math
from datetime import datetime, timedelta, timezone
import database as db
import config_manager
import time_sync
from time_sync import time_manager

def _parse_db_timestamp(ts_val):
    """
    Safely parses database timestamps with auto-healing for Supabase UTC drift.
    """
    if not ts_val:
        return None
    if isinstance(ts_val, datetime):
        return ts_val.astimezone(time_manager.target_tz) if ts_val.tzinfo else ts_val.replace(tzinfo=time_manager.target_tz)

    ts_str = str(ts_val).strip()

    # Case A: ISO with explicit timezone offset or UTC indicator
    if "Z" in ts_str or "+" in ts_str[10:] or ("-" in ts_str[10:] and "T" in ts_str):
        clean = ts_str.replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(clean)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            
            local_dt = dt.astimezone(time_manager.target_tz)
            now = time_manager.now()

            # Auto-healing: If Supabase treated naive local time as UTC, local_dt will be in the future!
            if local_dt > now and (local_dt - now).total_seconds() < 21600:
                naive_part = ts_str[:19].replace("T", " ")
                for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
                    try:
                        return datetime.strptime(naive_part, fmt).replace(tzinfo=time_manager.target_tz)
                    except Exception:
                        pass

            return local_dt
        except Exception:
            pass

    # Case B: Local wall-clock naive string
    formats = (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y %H:%M"
    )
    for fmt in formats:
        try:
            dt = datetime.strptime(ts_str[:19], fmt)
            return dt.replace(tzinfo=time_manager.target_tz)
        except Exception:
            pass

    return None


class HUDState:
    def __init__(self):
        self.reload_config()

    def reload_config(self):
        self.cfg = config_manager.load_config() or config_manager.DEFAULT_CONFIG
        time_sync.time_manager.reload_timezone()

        self.target_water_ml = int(self.cfg.get("target_water_ml", 2500))
        self.hydration_interval_min = int(self.cfg.get("hydration_interval_min", 75))
        self.target_meals = int(self.cfg.get("target_meals", 4))
        self.meal_interval_min = int(self.cfg.get("meal_interval_min", 210))
        self.target_brushing = int(self.cfg.get("target_brushing", 2))
        self.shower_frequency = str(self.cfg.get("shower_frequency", "Daily"))

        self.sleep_start_hour = int(self.cfg.get("sleep_start_hour", 23))
        self.sleep_start_minute = int(self.cfg.get("sleep_start_minute", 0))
        self.sleep_end_hour = int(self.cfg.get("sleep_end_hour", 7))
        self.sleep_end_minute = int(self.cfg.get("sleep_end_minute", 0))

    def is_sleep_window(self) -> bool:
        now = time_manager.now()
        cur_min = now.hour * 60 + now.minute
        start_min = self.sleep_start_hour * 60 + self.sleep_start_minute
        end_min = self.sleep_end_hour * 60 + self.sleep_end_minute

        if start_min < end_min:
            return start_min <= cur_min < end_min
        else:
            return cur_min >= start_min or cur_min < end_min

    def evaluate_hydration(self):
        now = time_manager.now()
        last_dt = None
        try:
            records = db.get_all_intake_history(days=2, order="desc")
            for r in records:
                t = (r.get("type") or r.get("intake_type") or "").lower()
                tag = (r.get("tag") or "").lower()
                if t in ("water", "hydration") or tag == "water":
                    raw_ts = r.get("logged_at") or r.get("created_at")
                    last_dt = _parse_db_timestamp(raw_ts)
                    if last_dt:
                        break
        except Exception:
            pass

        if not last_dt:
            wake_anchor = now.replace(hour=self.sleep_end_hour, minute=self.sleep_end_minute, second=0, microsecond=0)
            last_dt = wake_anchor if now >= wake_anchor else wake_anchor - timedelta(days=1)

        elapsed_min = max(0, int((now - last_dt).total_seconds() / 60.0))
        status = "OVERDUE" if elapsed_min >= (self.hydration_interval_min * 2) else ("DUE" if elapsed_min >= self.hydration_interval_min else "OPTIMAL")
        return status, elapsed_min

    def evaluate_nutrition(self):
        now = time_manager.now()
        last_dt = None
        try:
            records = db.get_all_intake_history(days=2, order="desc")
            for r in records:
                t = (r.get("type") or r.get("intake_type") or "").lower()
                tag = (r.get("tag") or "").lower()
                if t in ("meal", "nutrition", "food") or tag in ("meal", "food"):
                    raw_ts = r.get("logged_at") or r.get("created_at")
                    last_dt = _parse_db_timestamp(raw_ts)
                    if last_dt:
                        break
        except Exception:
            pass

        if not last_dt:
            wake_anchor = now.replace(hour=self.sleep_end_hour, minute=self.sleep_end_minute, second=0, microsecond=0)
            last_dt = wake_anchor if now >= wake_anchor else wake_anchor - timedelta(days=1)

        elapsed_min = max(0, int((now - last_dt).total_seconds() / 60.0))
        status = "OVERDUE" if elapsed_min >= (self.meal_interval_min * 1.5) else ("DUE" if elapsed_min >= self.meal_interval_min else "OPTIMAL")
        return status, elapsed_min

    def calculate_bio_budget(self):
        now = time_manager.now()
        wake_dt = None
        sleep_dt = None
        sleep_dur = 8.0
        disruptions = 0

        # 1. Primary Sleep Extraction
        try:
            recent_sleep = db.get_all_sleep_history(days=7, order="desc")
            if recent_sleep:
                latest = recent_sleep[0]
                raw_wake = latest.get("wake_time")
                raw_sleep = latest.get("sleep_time")
                parsed_wake = _parse_db_timestamp(raw_wake)
                parsed_sleep = _parse_db_timestamp(raw_sleep)

                if parsed_wake and parsed_wake <= now:
                    diff_sec = (now - parsed_wake).total_seconds()
                    if diff_sec <= 86400:
                        wake_dt = parsed_wake
                        sleep_dt = parsed_sleep
                        sleep_dur = float(latest.get("duration_hours", 8.0))
                        disruptions = int(latest.get("interruptions", 0))
        except Exception:
            pass

        if not wake_dt:
            wake_anchor = now.replace(hour=self.sleep_end_hour, minute=self.sleep_end_minute, second=0, microsecond=0)
            wake_dt = wake_anchor if now >= wake_anchor else wake_anchor - timedelta(days=1)

        base_budget = 16.0

        # Duration Delta
        if sleep_dur < 8.0:
            dur_mod = (sleep_dur - 8.0) * 1.25
        else:
            dur_mod = min(1.5, (sleep_dur - 8.0) * 0.5)

        # Disruption Penalty (-0.5h per wake event)
        dis_mod = -(disruptions * 0.5)

        # Circadian Phase Misalignment
        circadian_mod = 0.0
        if sleep_dt:
            target_h = self.sleep_start_hour
            onset_h = sleep_dt.hour + (sleep_dt.minute / 60.0)
            effective_onset = onset_h + 24.0 if onset_h < 12.0 else onset_h
            effective_target = target_h if target_h >= 12.0 else target_h + 24.0
            shift_delay = max(0.0, effective_onset - effective_target)

            if shift_delay > 1.5:
                circadian_mod = -min(2.0, (shift_delay - 1.5) * 0.4)

        # Sleep Regularity / Social Jetlag
        jetlag_mod = 0.0
        try:
            history = db.get_all_sleep_history(days=7, order="desc")
            wake_hours = []
            for item in history:
                w_time = _parse_db_timestamp(item.get("wake_time"))
                if w_time:
                    wake_hours.append(w_time.hour + (w_time.minute / 60.0))
            if len(wake_hours) >= 3:
                mean_w = sum(wake_hours) / len(wake_hours)
                variance = sum((x - mean_w) ** 2 for x in wake_hours) / len(wake_hours)
                std_dev = math.sqrt(variance)
                if std_dev > 1.5:
                    jetlag_mod = -min(1.5, (std_dev - 1.5) * 0.6)
        except Exception:
            pass

        # Physical Exertion Drag
        exercise_mod = 0.0
        try:
            ex_hours = db.get_today_exercise_hours()
            if ex_hours > 0:
                exercise_mod = -min(2.5, ex_hours * 0.75)
        except Exception:
            pass

        # Nap Modifier
        nap_mod = 0.0
        try:
            naps = db.get_today_naps()
            total_nap_min = sum(int(n.get("duration_minutes", 0)) for n in naps)
            if 0 < total_nap_min <= 45:
                nap_mod = min(1.2, total_nap_min * 0.025)
            elif 45 < total_nap_min <= 90:
                nap_mod = 1.2
            elif total_nap_min > 90:
                nap_mod = 1.4
                circadian_mod -= min(1.5, (total_nap_min - 90) / 60.0 * 0.5)
        except Exception:
            pass

        # 7-Day Sleep Debt
        debt_mod = 0.0
        try:
            import sleep_analytics
            report = sleep_analytics.analyze_sleep_trajectory()
            debt = report.get("sleep_debt", 0.0)
            if debt > 3.0:
                debt_mod = -min(2.0, (debt - 3.0) * 0.3)
        except Exception:
            pass

        # Metabolic Modifiers
        meta_mod = 0.0
        h_status, _ = self.evaluate_hydration()
        n_status, _ = self.evaluate_nutrition()
        if h_status == "OVERDUE":
            meta_mod -= 0.5
        if n_status == "OVERDUE":
            meta_mod -= 0.5

        total_budget = max(8.0, min(18.0, base_budget + dur_mod + dis_mod + circadian_mod + jetlag_mod + exercise_mod + nap_mod + debt_mod + meta_mod))
        return wake_dt, total_budget, sleep_dur, disruptions

    def evaluate_rest(self):
        now = time_manager.now()
        wake_dt, total_budget, sleep_dur, disruptions = self.calculate_bio_budget()

        hours_awake = max(0.0, (now - wake_dt).total_seconds() / 3600.0)
        remaining_hours = total_budget - hours_awake

        # Linear biological decay anchor
        alertness_frac = max(0.0, min(1.0, 1.0 - (hours_awake / total_budget)))

        # Process C Afternoon Dip (7.0 - 9.0 hours post-wake)
        is_circadian_dip = (7.0 <= hours_awake <= 9.0)
        if is_circadian_dip:
            dip_penalty = 0.08 * (1.0 - abs(hours_awake - 8.0))
            alertness_frac = max(0.0, alertness_frac - dip_penalty)

        if is_circadian_dip:
            s_sub = "CIRCADIAN DIP"
            s_status = "DUE"
        elif alertness_frac <= 0.05 or remaining_hours <= 0:
            s_status = "OVERDUE"
            s_sub = f"+{abs(total_budget - hours_awake):.1f}h over"
        elif alertness_frac <= 0.25:
            s_status = "DUE"
            s_sub = f"{remaining_hours:.1f}h left"
        else:
            s_status = "OPTIMAL"
            s_sub = f"{remaining_hours:.1f}h left"

        s_center = f"{int(alertness_frac * 100)}%"
        return alertness_frac, s_center, s_sub, s_status, is_circadian_dip