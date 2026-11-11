import math
from collections import defaultdict
from datetime import datetime
import database as db
import config_manager
import dialogues
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


def _rel_midnight_hour(dt: datetime) -> float:
    """Maps clock time relative to midnight (e.g., 11:00 PM -> -1.0, 3:30 AM -> +3.5)."""
    h = dt.hour + (dt.minute / 60.0)
    return h - 24.0 if h >= 12.0 else h


def _format_hour_12h(hour_float: float) -> str:
    """Converts a 24h float (e.g., 23.5 or 3.5) into a readable 12h clock string."""
    h_mod = hour_float % 24.0
    hr = int(h_mod)
    mn = int(round((h_mod - hr) * 60))
    if mn == 60:
        hr = (hr + 1) % 24
        mn = 0
    ampm = "PM" if hr >= 12 else "AM"
    hr12 = hr % 12 or 12
    return f"{hr12}:{mn:02d} {ampm}"


def _band_for_score(score: int) -> str:
    if score >= 85:
        return "OPTIMAL"
    elif score >= 70:
        return "NOMINAL"
    elif score >= 52:
        return "DEGRADED"
    return "CRITICAL"


def calculate_biometric_readiness(scope_days: int = 7) -> dict:
    """
    Executes a sequential 4-stage physiological diagnostic:
      1. Sector 1: Metabolic Intake (Food & Water)
      2. Sector 2: Hygiene & Decontamination (Brush & Shower)
      3. Sector 3: Exertion, Rest & Circadian Architecture (Sleep, Naps & Workouts)
      4. Sector 4: 7-Day Historical Trends & Behavioral Patterns
    Compiles dual readiness indices at completion:
      - MENTAL READINESS (0-100%): Hyperfocus, study endurance, cognitive processing
      - PHYSICAL READINESS (0-100%): In-person presentability, hygiene, somatic stamina
    """
    now = time_manager.now()
    cfg = config_manager.load_config() or config_manager.DEFAULT_CONFIG

    sleep_logs = db.get_all_sleep_history(days=scope_days, order="desc") or []
    exercise_logs = db.get_all_exercise_history(days=scope_days, order="desc") or []
    nap_logs = db.get_all_nap_history(days=scope_days, order="desc") or []
    intake_logs = db.get_all_intake_history(days=scope_days, order="desc") or []

    try:
        hygiene_logs = db.get_all_hygiene_history(days=scope_days, order="desc") or []
    except AttributeError:
        hygiene_logs = [r for r in intake_logs if str(r.get("type", "")).lower() == "hygiene"]

    findings = []
    trends = []

    def register_issue(priority: int, sector: str, code: str, advisory: str, action: str, **params):
        findings.append({
            "priority": priority,
            "sector": sector,
            "code": code,
            "advisory": advisory,
            "action": action,
            "params": params
        })

    def register_trend(priority: int, code: str, terminal_note: str, **params):
        trends.append({
            "priority": priority,
            "code": code,
            "terminal_note": terminal_note,
            "params": params
        })

    # Determine elapsed hours awake from most recent wake timestamp
    last_wake_dt = _parse_ts(sleep_logs[0].get("wake_time")) if sleep_logs else None
    if last_wake_dt:
        elapsed_since_wake = (now - last_wake_dt).total_seconds() / 3600.0
        if 0.0 < elapsed_since_wake <= 24.0:
            hours_awake = max(0.5, elapsed_since_wake)
        else:
            hours_awake = max(0.5, (now.hour + now.minute / 60.0) - 8.0)
    else:
        hours_awake = max(0.5, (now.hour + now.minute / 60.0) - 8.0)

    waking_progress = min(1.0, max(0.1, hours_awake / 15.0))

    # =========================================================================
    # SECTOR 1: METABOLIC INTAKE (HYDRATION & NUTRITION)
    # =========================================================================
    totals = db.get_today_totals()
    w_ml = float(totals.get("water_ml", 0.0))
    m_cnt = float(totals.get("meals_count", 0.0))
    today_ex_hours = float(getattr(db, "get_today_exercise_hours", lambda: 0.0)())

    target_w_daily = float(cfg.get("target_water_ml", 2500)) + (today_ex_hours * 500.0)
    target_m_daily = float(cfg.get("target_meals", 4))

    expected_water = target_w_daily * waking_progress
    expected_meals = target_m_daily * waking_progress

    # Hydration vector (0-100%)
    if hours_awake < 1.0:
        hydration_pct = 95.0
    elif expected_water > 0:
        hydration_pct = min(100.0, max(10.0, (w_ml / expected_water) * 100.0))
    else:
        hydration_pct = 100.0

    if hours_awake >= 1.5 and expected_water > 0 and w_ml < (expected_water * 0.70):
        gap_ml = max(250, int(round((expected_water - w_ml) / 250.0) * 250))
        canisters = max(1, gap_ml // 250)
        register_issue(
            1, "INTAKE", "hydration_lag",
            f"HYDRATION LAG: {int(w_ml)}ml logged vs ~{int(expected_water)}ml expected after {hours_awake:.1f}h awake.",
            f"Assimilate {gap_ml}ml of fluid ({canisters} canister{'s' if canisters > 1 else ''}) immediately.",
            gap_ml=gap_ml
        )

    # Nutrition vector (0-100%)
    if hours_awake < 2.0:
        nutrition_pct = 95.0
    elif expected_meals > 0:
        nutrition_pct = min(100.0, max(15.0, (m_cnt / expected_meals) * 100.0))
    else:
        nutrition_pct = 100.0

    if hours_awake >= 3.0 and expected_meals >= 1.0 and m_cnt < (expected_meals * 0.55):
        register_issue(
            2, "INTAKE", "caloric_lag",
            f"CALORIC LAG: {m_cnt:g} rations logged after {hours_awake:.1f}h awake (expected ~{expected_meals:.1f}).",
            "Consume a full meal ration or nutrient snack now to stabilize blood glucose."
        )

    intake_score_pct = int(round((0.55 * hydration_pct) + (0.45 * nutrition_pct)))

    # =========================================================================
    # SECTOR 2: HYGIENE & DECONTAMINATION (BRUSHING & SHOWER)
    # =========================================================================
    target_brush = int(cfg.get("target_brushing", 2))
    shower_freq = str(cfg.get("shower_frequency", "Daily"))

    today_str = now.date().isoformat()
    b_cnt_today = 0
    shower_timestamps = []

    for h in hygiene_logs:
        tag = str(h.get("tag", "")).lower().strip()
        ts = _parse_ts(h.get("logged_at"))
        if tag == "brushing" and ts and ts.date().isoformat() == today_str:
            b_cnt_today += 1
        elif tag == "shower" and ts:
            shower_timestamps.append(ts)

    # Brushing score (0-100%)
    if b_cnt_today >= target_brush:
        brush_pct = 100.0
    elif b_cnt_today == 0:
        if hours_awake < 2.0:
            brush_pct = 75.0
        else:
            brush_pct = 20.0
            register_issue(
                1, "HYGIENE", "brush_overdue",
                f"ORAL NEGLECT: 0/{target_brush} brushing cycles logged after {hours_awake:.1f}h awake.",
                "Execute oral sanitation immediately before close-range human contact."
            )
    else:
        # 1/2 logged when target is 2
        if hours_awake >= 13.0:
            brush_pct = 65.0
            register_issue(
                3, "HYGIENE", "brush_partial",
                f"PARTIAL ORAL HYGIENE: {b_cnt_today}/{target_brush} brushing sessions logged late in cycle.",
                "Complete your second brushing cycle prior to sleep."
            )
        else:
            brush_pct = 88.0

    # Shower score (0-100%)
    shower_timestamps.sort(reverse=True)
    last_shower_dt = shower_timestamps[0] if shower_timestamps else None

    if not last_shower_dt:
        days_since_shower = 999
        hours_since_shower = 999.0
    else:
        hours_since_shower = max(0.0, (now - last_shower_dt).total_seconds() / 3600.0)
        days_since_shower = (now.date() - last_shower_dt.date()).days

    if shower_freq == "Daily":
        if days_since_shower == 0 or hours_since_shower <= 24.0:
            shower_pct = 100.0
            shower_status_str = "COMPLIANT (Today)"
        elif days_since_shower == 1 and hours_awake < 3.0:
            shower_pct = 75.0
            shower_status_str = "PENDING (Morning Window)"
        else:
            shower_pct = 15.0 if days_since_shower >= 2 else 30.0
            shower_status_str = f"OVERDUE ({days_since_shower}d ago)" if days_since_shower < 900 else "NO RECORD"
            register_issue(
                1, "HYGIENE", "shower_overdue",
                f"DERMAL DECONTAMINATION OVERDUE: Last shower was {days_since_shower if days_since_shower < 900 else '3+'}d ago.",
                "Take a decontamination shower immediately to restore in-person presentability.",
                days_since=min(days_since_shower, 7)
            )
    else:  # Every Alternative Day
        if days_since_shower <= 1 or hours_since_shower <= 44.0:
            shower_pct = 100.0
            shower_status_str = "COMPLIANT (Alt-Day)"
        elif days_since_shower == 2 and hours_awake < 4.0:
            shower_pct = 65.0
            shower_status_str = "DUE TODAY"
        else:
            shower_pct = 20.0
            shower_status_str = f"OVERDUE ({days_since_shower}d ago)"
            register_issue(
                1, "HYGIENE", "shower_overdue",
                f"DERMAL DECONTAMINATION OVERDUE: Alternate-day shower window breached ({days_since_shower}d elapsed).",
                "Take a decontamination shower immediately to clear accumulated bio-film.",
                days_since=min(days_since_shower, 7)
            )

    hygiene_score_pct = int(round((0.45 * brush_pct) + (0.55 * shower_pct)))

    # =========================================================================
    # SECTOR 3: EXERTION, REST & CIRCADIAN ARCHITECTURE
    # =========================================================================
    target_sleep_h = 8.0
    total_nap_mins = sum(int(r.get("duration_minutes", 0)) for r in nap_logs)
    total_nap_hours = total_nap_mins / 60.0
    total_ex_hours = sum(float(r.get("duration_hours", 0.0)) for r in exercise_logs)

    recent_sleeps = sleep_logs[:7]
    raw_durations = []

    if not recent_sleeps and total_nap_mins == 0:
        sleep_arch_pct = 50.0
        avg_night_sleep = 0.0
        effective_avg_sleep = 0.0
        sleep_debt = 0.0
        register_issue(
            1, "SLEEP", "no_sleep_data",
            "TELEMETRY GAP: Insufficient historical sleep logs recorded.",
            "Log your most recent sleep cycle via [+ SLEEP CYCLE] to calibrate baseline debt."
        )
    else:
        weights = [1.0, 0.85, 0.70, 0.55, 0.45, 0.35, 0.25]
        weighted_dur_sum = 0.0
        weight_total = 0.0

        for idx, row in enumerate(recent_sleeps):
            w = weights[idx] if idx < len(weights) else 0.25
            dur = float(row.get("duration_hours", 7.0))
            dis = int(row.get("interruptions", 0))
            raw_durations.append(dur)

            eff_dur = max(0.0, dur - (dis * 0.25))
            weighted_dur_sum += eff_dur * w
            weight_total += w

        avg_night_sleep = (sum(raw_durations) / len(raw_durations)) if raw_durations else 0.0
        weighted_night_avg = (weighted_dur_sum / weight_total) if weight_total > 0 else 0.0

        # Chronological (non-retroactive) sleep debt: oldest -> newest
        running_debt = 0.0
        for row in reversed(recent_sleeps):
            dur = float(row.get("duration_hours", 7.0))
            if dur < target_sleep_h:
                running_debt += (target_sleep_h - dur)
            else:
                recovery_credit = min(1.5, dur - target_sleep_h)
                running_debt = max(0.0, running_debt - recovery_credit)

        nap_offset_h = total_nap_hours * 0.75
        sleep_debt = max(0.0, running_debt - nap_offset_h)
        effective_avg_sleep = weighted_night_avg + (nap_offset_h / max(len(recent_sleeps), 1))

        # Sleep architecture score (0-100%)
        dur_component = min(70.0, (effective_avg_sleep / target_sleep_h) * 70.0)
        last_disruptions = int(recent_sleeps[0].get("interruptions", 0)) if recent_sleeps else 0
        total_interruptions = sum(int(r.get("interruptions", 0)) for r in recent_sleeps)
        avg_interruptions = total_interruptions / max(len(recent_sleeps), 1)

        debt_penalty = min(22.0, sleep_debt * 5.2)
        dis_penalty = min(8.0, (last_disruptions * 2.4) + (avg_interruptions * 1.6))
        resilience_component = max(0.0, 30.0 - debt_penalty - dis_penalty)

        sleep_arch_pct = min(100.0, max(10.0, dur_component + resilience_component))

        last_night_dur = raw_durations[0] if raw_durations else 8.0
        if last_night_dur < 6.5:
            sleep_arch_pct = min(sleep_arch_pct, 74.0)
            register_issue(
                1, "SLEEP", "acute_restriction",
                f"ACUTE SLEEP RESTRICTION: Last night's cycle ({last_night_dur:.1f}h) fell below 6.5h floor.",
                "Take a 25-minute power nap before mid-afternoon to clear adenosine without grogginess.",
                last_h=last_night_dur
            )
        elif last_night_dur < 7.2:
            sleep_arch_pct = min(sleep_arch_pct, 84.0)
            register_issue(
                2, "SLEEP", "mild_acute_deficit",
                f"MILD ACUTE SLEEP DEFICIT: Last night's sleep ({last_night_dur:.1f}h) leaves mild cognitive drag.",
                "Schedule a 20 to 30 minute recovery nap during your afternoon dip and add +45m to tonight's rest.",
                last_h=last_night_dur
            )

        if sleep_debt >= 1.5:
            extra_mins = min(60, int(round((sleep_debt / 2.0) * 60)))
            register_issue(
                1, "SLEEP", "active_sleep_debt",
                f"ACTIVE SLEEP DEBT: {sleep_debt:.1f}h unrecovered deficit (prior surplus nights do not erase recent loss).",
                f"Pay down debt gradually by adding +{extra_mins}m of sleep per night over the next 2 cycles.",
                debt_h=sleep_debt,
                extra_mins=extra_mins
            )

        if avg_interruptions >= 1.5 or last_disruptions >= 2:
            register_issue(
                3, "SLEEP", "fragmented_sleep",
                "FRAGMENTED SLEEP: Nightly disruptions reduced slow-wave restoration.",
                "Taper fluid intake 90 minutes before bed and minimize room light/audio triggers."
            )

    # Circadian Regularity & Phase Alignment (0-100%)
    wake_hours = []
    onset_rel_hours = []
    for item in recent_sleeps:
        w_dt = _parse_ts(item.get("wake_time"))
        s_dt = _parse_ts(item.get("sleep_time"))
        if w_dt:
            wake_hours.append(w_dt.hour + (w_dt.minute / 60.0))
        if s_dt:
            onset_rel_hours.append(_rel_midnight_hour(s_dt))

    if len(wake_hours) >= 2:
        mean_wake = sum(wake_hours) / len(wake_hours)
        variance = sum((x - mean_wake) ** 2 for x in wake_hours) / len(wake_hours)
        std_dev = math.sqrt(variance)

        reg_pct = max(0.0, min(50.0, 50.0 - (std_dev * 15.0)))
        acute_wake_jump = abs(wake_hours[0] - mean_wake)
        if acute_wake_jump >= 1.5:
            reg_pct = max(0.0, reg_pct - 8.0)
            register_issue(
                2, "CIRCADIAN", "wake_phase_shift",
                f"WAKE PHASE SHIFT: Today's wake time shifted {acute_wake_jump:.1f}h from your 7-day baseline.",
                "Get 15 minutes of bright outdoor light immediately to anchor your cortisol peak.",
                shift_h=acute_wake_jump
            )

        cfg_bed_h = float(cfg.get("sleep_start_hour", 23)) + (float(cfg.get("sleep_start_minute", 0)) / 60.0)
        target_rel_bed = cfg_bed_h - 24.0 if cfg_bed_h >= 12.0 else cfg_bed_h

        if onset_rel_hours:
            mean_onset = sum(onset_rel_hours) / len(onset_rel_hours)
            phase_delay = abs(mean_onset - target_rel_bed)
            phase_pct = max(0.0, min(50.0, 50.0 - (phase_delay * 9.0)))
            if phase_delay >= 2.0:
                step_bed_clock = _format_hour_12h(mean_onset - 0.75)
                register_issue(
                    2, "CIRCADIAN", "delayed_circadian",
                    f"DELAYED CIRCADIAN PHASE: Mean sleep onset is ~{phase_delay:.1f}h past target sleep window.",
                    f"Step bedtime earlier by 45 minutes tonight (target ~{step_bed_clock}) rather than forcing an abrupt jump.",
                    delay_h=phase_delay,
                    step_bed=step_bed_clock
                )
        else:
            phase_pct = 35.0

        if std_dev > 1.25:
            register_issue(
                3, "CIRCADIAN", "social_jetlag",
                f"SOCIAL JETLAG: Wake variance (±{std_dev:.1f}h) destabilizing melatonin onset.",
                "Lock your wake-up alarm within a 30-minute window across weekdays and weekends.",
                std_h=std_dev
            )

        circadian_pct = min(100.0, max(10.0, reg_pct + phase_pct))
    else:
        circadian_pct = 65.0

    # Exertion & Recovery Balance (0-100%)
    if total_ex_hours == 0.0:
        exertion_pct = 72.0  # Neutral baseline (no free athletic inflation)
        register_issue(
            3, "EXERTION", "sedentary_streak",
            "ZERO EXERTION LOGGED: 0.0h physical load recorded in the 7-day window.",
            "Log 30 to 45 minutes of physical exertion today to maintain cardiovascular stamina."
        )
    else:
        exertion_pct = 90.0
        if sleep_debt >= 2.0 and total_ex_hours >= 3.0:
            exertion_pct = 65.0
            register_issue(
                2, "EXERTION", "recovery_lag",
                f"RECOVERY LAG: {total_ex_hours:.1f}h physical strain logged while carrying {sleep_debt:.1f}h sleep debt.",
                "Keep today's training intensity moderate and add +500ml fluid plus a 30m recovery nap.",
                debt_h=sleep_debt
            )
        elif total_ex_hours > (scope_days * 1.3) and total_nap_mins < 45:
            exertion_pct = 70.0
            register_issue(
                3, "EXERTION", "metabolic_overreach",
                "METABOLIC OVERREACH: High training volume without compensatory daytime recovery.",
                "Schedule a 30 to 45 minute recovery nap or rest day to prevent central nervous fatigue."
            )
        elif total_nap_mins >= 30 or sleep_debt < 1.0:
            exertion_pct = 100.0

    recovery_sector_pct = int(round((0.60 * sleep_arch_pct) + (0.25 * circadian_pct) + (0.15 * exertion_pct)))

    # =========================================================================
    # DUAL READINESS COMPILATION (MENTAL VS. PHYSICAL)
    # =========================================================================
    # 1. MENTAL READINESS: Focus, Hyperfocus, Studies, Prefrontal Processing
    mental_raw = (
        (0.45 * sleep_arch_pct) +
        (0.20 * circadian_pct) +
        (0.20 * hydration_pct) +
        (0.15 * nutrition_pct)
    )
    if raw_durations and raw_durations[0] < 6.0:
        mental_raw = min(mental_raw, 72.0)
    if sleep_debt >= 3.0:
        mental_raw = min(mental_raw, 75.0)
    mental_score = int(round(min(100.0, max(5.0, mental_raw))))

    # 2. PHYSICAL READINESS: In-Person Presentability, Hygiene, Somatic Stamina
    physical_raw = (
        (0.45 * hygiene_score_pct) +
        (0.25 * exertion_pct) +
        (0.15 * sleep_arch_pct) +
        (0.15 * hydration_pct)
    )
    if shower_pct <= 35.0 or brush_pct <= 30.0:
        physical_raw = min(physical_raw, 66.0)
    physical_score = int(round(min(100.0, max(5.0, physical_raw))))

    # =========================================================================
    # SECTOR 4: 7-DAY HISTORICAL TRENDS & PATTERN DETECTION
    # =========================================================================
    # Trend A: Sleep Trajectory (Recent 3 nights vs Earlier nights)
    if len(raw_durations) >= 4:
        recent_3_avg = sum(raw_durations[:3]) / 3.0
        older_avg = sum(raw_durations[3:]) / len(raw_durations[3:])
        delta_sleep = recent_3_avg - older_avg
        if delta_sleep <= -0.7:
            register_trend(
                1, "sleep_declining",
                f"SLEEP EROSION: Last 3 nights averaged {recent_3_avg:.1f}h vs {older_avg:.1f}h earlier in the week ({delta_sleep:+.1f}h).",
                delta_h=abs(delta_sleep)
            )
        elif delta_sleep >= 0.7:
            register_trend(
                3, "sleep_improving",
                f"RECOVERY MOMENTUM: Last 3 nights averaged {recent_3_avg:.1f}h vs {older_avg:.1f}h earlier ({delta_sleep:+.1f}h).",
                delta_h=delta_sleep
            )

    # Trend B: Nocturnal Circadian Phase Lock (majority of bedtimes after 2:00 AM)
    if len(onset_rel_hours) >= 3:
        late_nights = sum(1 for h in onset_rel_hours if h >= 2.0)
        if late_nights / len(onset_rel_hours) >= 0.70:
            register_trend(
                2, "nocturnal_lock",
                f"NOCTURNAL PHASE LOCK: {late_nights}/{len(onset_rel_hours)} sleep cycles initiated after 02:00 AM."
            )

    # Trend C: Mind-Body Skew (Mental vs Physical divergence)
    if (mental_score - physical_score) >= 18:
        register_trend(
            1, "brain_in_a_jar",
            f"BRAIN-IN-A-JAR SKEW: Mental Readiness ({mental_score}%) outpaces Physical Presentability ({physical_score}%) by {mental_score - physical_score} pts."
        )
    elif (physical_score - mental_score) >= 18:
        register_trend(
            2, "somatic_over_cognitive",
            f"COGNITIVE DRAG SKEW: Physical Readiness ({physical_score}%) outpaces Mental Readiness ({mental_score}%) due to rest debt."
        )

    # Trend D: Multi-Day Hydration Pattern
    daily_water_map = defaultdict(float)
    for item in intake_logs:
        if str(item.get("type", "")).lower() == "hydration":
            dt_i = _parse_ts(item.get("logged_at"))
            if dt_i and dt_i.date().isoformat() != today_str:
                daily_water_map[dt_i.date().isoformat()] += float(item.get("amount", 0.0))
    if len(daily_water_map) >= 3:
        avg_hist_water = sum(daily_water_map.values()) / len(daily_water_map)
        base_water_tgt = float(cfg.get("target_water_ml", 2500))
        if avg_hist_water < (base_water_tgt * 0.65):
            register_trend(
                2, "chronic_underhydration",
                f"CHRONIC UNDER-HYDRATION: Prior days averaged {int(avg_hist_water)}ml/day vs {int(base_water_tgt)}ml target."
            )

    findings.sort(key=lambda item: item["priority"])
    trends.sort(key=lambda item: item["priority"])

    mental_band = _band_for_score(mental_score)
    physical_band = _band_for_score(physical_score)
    overall_score = int(round((0.55 * mental_score) + (0.45 * physical_score)))

    advisories = [f["advisory"] for f in findings] if findings else [
        "All biological vectors operating within acceptable corporate tolerances."
    ]
    suggestions = [f["action"] for f in findings] if findings else [
        "Maintain current sleep anchor, hygiene compliance, and hydration intervals."
    ]
    trend_notes = [t["terminal_note"] for t in trends] if trends else [
        "Multi-day telemetry stable; no adverse behavioral drift detected."
    ]

    voice_line = dialogues.get_full_diagnostic_voice_line(
        mental_score=mental_score,
        physical_score=physical_score,
        findings=findings,
        trends=trends
    )

    terminal_lines = [
        "==========================================================",
        f" [ALTERRA FULL BIOMETRIC DIAGNOSTIC] ({scope_days}-DAY WINDOW)",
        "==========================================================",
        f" 1. METABOLIC INTAKE   : {intake_score_pct}% [{_band_for_score(intake_score_pct)}]",
        f"    -> Hydration: {int(w_ml)}/{int(target_w_daily)}ml ({int(hydration_pct)}%) | Rations: {m_cnt:g}/{int(target_m_daily)} ({int(nutrition_pct)}%)",
        f" 2. HYGIENE & APPEARANCE: {hygiene_score_pct}% [{_band_for_score(hygiene_score_pct)}]",
        f"    -> Brushing: {b_cnt_today}/{target_brush} ({int(brush_pct)}%) | Shower: {shower_status_str} ({int(shower_pct)}%)",
        f" 3. REST & EXERTION    : {recovery_sector_pct}% [{_band_for_score(recovery_sector_pct)}]",
        f"    -> Sleep Avg: {avg_night_sleep:.1f}h | Active Debt: {sleep_debt:.1f}h | Naps: {total_nap_mins}m | Ex: {total_ex_hours:.1f}h",
        "----------------------------------------------------------",
        " 4. HISTORICAL TRENDS & PATTERNS:"
    ]
    for tn in trend_notes:
        terminal_lines.append(f"    [~] {tn}")

    terminal_lines.append("----------------------------------------------------------")
    terminal_lines.append(" DIAGNOSTIC FLAGS & ROASTS:")
    for adv in advisories:
        terminal_lines.append(f"    [!] {adv}")

    terminal_lines.append("----------------------------------------------------------")
    terminal_lines.append(" RECOMMENDED CORRECTIVE SEQUENCE:")
    for idx, sug in enumerate(suggestions, start=1):
        terminal_lines.append(f"    [{idx}] {sug}")

    terminal_lines.append("==========================================================")
    terminal_lines.append(f" >> MENTAL READINESS   : {mental_score}% [{mental_band}]  (Focus / Studies / Cognition)")
    terminal_lines.append(f" >> PHYSICAL READINESS : {physical_score}% [{physical_band}]  (Presentability / Hygiene / Stamina)")
    terminal_lines.append("==========================================================")

    return {
        "readiness_score": overall_score,
        "mental_score": mental_score,
        "physical_score": physical_score,
        "band": mental_band,
        "status_color": "#00FFFF" if mental_score >= 85 else ("#39FF14" if mental_score >= 70 else "#FFB000"),
        "advisories": advisories,
        "suggestions": suggestions,
        "trends": trend_notes,
        "avg_sleep": round(effective_avg_sleep, 2),
        "sleep_debt": round(sleep_debt, 2),
        "total_nap_mins": total_nap_mins,
        "terminal_report": "\n".join(terminal_lines),
        "voice_line": voice_line
    }