import math
from datetime import datetime, timedelta, timezone
import database as db
from time_sync import time_manager


def _parse_ts(ts_val):
    if not ts_val:
        return None
    if isinstance(ts_val, datetime):
        return ts_val.astimezone(time_manager.target_tz) if ts_val.tzinfo else ts_val.replace(tzinfo=time_manager.target_tz)
    s = str(ts_val).strip()
    clean = s.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(clean)
        return dt.astimezone(time_manager.target_tz) if dt.tzinfo else dt.replace(tzinfo=time_manager.target_tz)
    except Exception:
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%d/%m/%Y %H:%M"):
        try:
            return datetime.strptime(s[:19], fmt).replace(tzinfo=time_manager.target_tz)
        except Exception:
            pass
    return None


def calculate_biometric_readiness(scope_days: int = 7) -> dict:
    """
    Computes a 0-100% composite Biometric Readiness Index across 4 biological pillars:
      1. Sleep Architecture & Cumulative Debt (50%) [Nocturnal + Daytime Naps]
      2. Circadian Consistency / Social Jetlag (20%)
      3. Exertion vs Nap Recovery Balance (15%)
      4. Acute Metabolic & Hydration Compliance (15%) [Coupled to Exertion Load]
    """
    now = time_manager.now()
    sleep_logs = db.get_all_sleep_history(days=scope_days, order="desc")
    exercise_logs = db.get_all_exercise_history(days=scope_days, order="desc")
    nap_logs = db.get_all_nap_history(days=scope_days, order="desc")

    advisories = []

    # ---------------------------------------------------------
    # PILLAR 1: Sleep Architecture & Cumulative Debt (50 pts)
    # ---------------------------------------------------------
    total_nap_mins = sum(int(r.get("duration_minutes", 0)) for r in nap_logs)
    total_nap_hours = total_nap_mins / 60.0

    if not sleep_logs and total_nap_mins == 0:
        sleep_score = 30.0  # Base assumption without data
        avg_night_sleep = 0.0
        effective_avg_sleep = 0.0
        sleep_debt = 0.0
        advisories.append("TELEMETRY GAP: Insufficient historical sleep logs recorded.")
    else:
        durations = [float(r.get("duration_hours", 7.0)) for r in sleep_logs]
        num_nights = max(len(durations), 1)
        night_sleep_total = sum(durations)
        avg_night_sleep = night_sleep_total / num_nights if durations else 0.0

        # Total combined sleep volume (Core nocturnal sleep + Daytime recovery)
        total_sleep_hours = night_sleep_total + total_nap_hours
        effective_avg_sleep = total_sleep_hours / num_nights

        # Debt calculation against an 8.0-hour standard
        target_total = num_nights * 8.0
        sleep_debt = max(0.0, target_total - total_sleep_hours)

        # Duration score (up to 35 pts) based on effective daily sleep
        if effective_avg_sleep >= 8.0:
            dur_pts = 35.0
        elif effective_avg_sleep >= 7.0:
            dur_pts = 30.0 + ((effective_avg_sleep - 7.0) * 5.0)
        elif effective_avg_sleep >= 6.0:
            dur_pts = 20.0 + ((effective_avg_sleep - 6.0) * 10.0)
        else:
            dur_pts = max(5.0, effective_avg_sleep * 3.3)

        # Debt penalty (deduct up to 15 pts)
        debt_penalty = min(15.0, sleep_debt * 2.5)

        # Disruption penalty
        if sleep_logs:
            total_interruptions = sum(int(r.get("interruptions", 0)) for r in sleep_logs)
            avg_interruptions = total_interruptions / len(sleep_logs)
        else:
            avg_interruptions = 0.0
        dis_penalty = min(10.0, avg_interruptions * 2.0)

        sleep_score = max(5.0, dur_pts - debt_penalty - dis_penalty + 15.0)

        if sleep_debt >= 4.0:
            advisories.append(f"CHRONIC SLEEP DEBT: Net deficit is {sleep_debt:.1f}h. Cognitive fatigue projected.")
        elif total_nap_hours >= 1.5:
            advisories.append(f"DAYTIME RECOVERY ACTIVE: {total_nap_hours:.1f}h of nap volume buffered cumulative debt.")

        if avg_interruptions >= 2.0:
            advisories.append("FRAGMENTED SLEEP: Frequent nightly disruptions degrading slow-wave recovery.")

    # ---------------------------------------------------------
    # PILLAR 2: Circadian Consistency / Social Jetlag (20 pts)
    # ---------------------------------------------------------
    wake_hours = []
    for item in sleep_logs:
        w_dt = _parse_ts(item.get("wake_time"))
        if w_dt:
            wake_hours.append(w_dt.hour + (w_dt.minute / 60.0))

    if len(wake_hours) >= 3:
        mean_wake = sum(wake_hours) / len(wake_hours)
        variance = sum((x - mean_wake) ** 2 for x in wake_hours) / len(wake_hours)
        std_dev = math.sqrt(variance)

        if std_dev <= 0.5:
            circadian_score = 20.0
        elif std_dev <= 1.0:
            circadian_score = 16.0
        elif std_dev <= 1.75:
            circadian_score = 11.0
            advisories.append("SOCIAL JETLAG: Wake-time variation is causing mild phase misalignment.")
        else:
            circadian_score = 6.0
            advisories.append("CIRCADIAN INSTABILITY: Schedule exceeds 1.75h variance. Melatonin timing disrupted.")
    else:
        circadian_score = 14.0

    # ---------------------------------------------------------
    # PILLAR 3: Exertion vs Nap Recovery Balance (15 pts)
    # ---------------------------------------------------------
    total_ex_hours = sum(float(r.get("duration_hours", 0.0)) for r in exercise_logs)
    strain_score = 15.0

    if total_ex_hours > (scope_days * 1.5):  # High training volume
        if total_nap_mins < 60 and effective_avg_sleep < 7.5:
            strain_score -= 5.0
            advisories.append("METABOLIC OVERREACH: Physical exertion exceeds current sleep-recovery capacity.")
        else:
            strain_score = 15.0
    elif total_nap_mins >= 40:
        strain_score = min(15.0, strain_score + 2.0)

    # ---------------------------------------------------------
    # PILLAR 4: Acute Metabolic & Hydration Compliance (15 pts)
    # ---------------------------------------------------------
    totals = db.get_today_totals()
    w_ml = totals.get("water_ml", 0)
    m_cnt = totals.get("meals_count", 0)
    today_ex_hours = db.get_today_exercise_hours()

    # Dynamic minimum water threshold: 1000ml baseline + 500ml per hour of workout
    min_water_target = 1000 + int(today_ex_hours * 500)

    meta_score = 15.0
    if w_ml < min_water_target and now.hour >= 14:
        meta_score -= 5.0
        if today_ex_hours > 0:
            advisories.append(f"EXERTION DEHYDRATION: Logged {today_ex_hours:.1f}h workout but fluid intake is under {min_water_target}ml.")
        else:
            advisories.append("DEHYDRATION RISK: Daytime fluid intake is below safe operating threshold.")

    if m_cnt == 0 and now.hour >= 14:
        meta_score -= 5.0
        advisories.append("CALORIC DEFICIT: Zero nutritional rations logged by mid-afternoon.")

    # ---------------------------------------------------------
    # COMPOSITE SCORE CALCULATION
    # ---------------------------------------------------------
    composite_score = int(max(5.0, min(100.0, sleep_score + circadian_score + strain_score + meta_score)))

    if composite_score >= 85:
        band = "OPTIMAL"
        status_color = "#00FFFF"
        voice_line = f"Biometric readiness is optimal at {composite_score} percent. Cognitive and metabolic parameters are within peak Alterra specifications."
    elif composite_score >= 70:
        band = "NOMINAL"
        status_color = "#39FF14"
        voice_line = f"Biometric readiness is nominal at {composite_score} percent. Moderate operational efficiency cleared."
    elif composite_score >= 50:
        band = "DEGRADED"
        status_color = "#FFB000"
        voice_line = f"Warning: Biometric readiness has degraded to {composite_score} percent. Rest debt and metabolic strain detected."
    else:
        band = "CRITICAL DEFICIT"
        status_color = "#FF3366"
        voice_line = f"Alert: Critical biological deficit. Readiness index is {composite_score} percent. Immediate recovery protocol mandatory."

    if not advisories:
        advisories.append("All biological vectors operating within acceptable corporate tolerances.")

    terminal_lines = [
        "--------------------------------------------------",
        f" [ALTERRA BIOMETRICS] COMPOSITE READINESS: {composite_score}% [{band}]",
        f" Scope: {scope_days}-Day Rolling Telemetry Window",
        "--------------------------------------------------",
        f"  * Sleep Architecture : {sleep_score:.1f} / 50.0 (Night Avg: {avg_night_sleep:.1f}h | Naps: {total_nap_mins}m | Net Debt: {sleep_debt:.1f}h)",
        f"  * Circadian Alignment: {circadian_score:.1f} / 20.0",
        f"  * Strain / Recovery  : {strain_score:.1f} / 15.0 (Ex: {total_ex_hours:.1f}h | Recovery: {total_nap_mins}m)",
        f"  * Acute Hydration    : {meta_score:.1f} / 15.0",
        "--------------------------------------------------",
        " CLINICAL ADVISORIES:"
    ]
    for adv in advisories:
        terminal_lines.append(f"  [!] {adv}")
    terminal_lines.append("--------------------------------------------------")

    return {
        "readiness_score": composite_score,
        "band": band,
        "status_color": status_color,
        "advisories": advisories,
        "avg_sleep": round(effective_avg_sleep, 2),
        "sleep_debt": round(sleep_debt, 2),
        "total_nap_mins": total_nap_mins,
        "terminal_report": "\n".join(terminal_lines),
        "voice_line": voice_line
    }