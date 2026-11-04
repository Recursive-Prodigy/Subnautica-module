import database

def analyze_sleep_trajectory() -> dict:
    """
    Evaluates rolling historical sleep telemetry to determine recovery trajectory,
    accumulated sleep debt, disruption index, and physiological side-effects.
    """
    try:
        # Fetches up to last 7 logged sleep records via database.py
        logs = database.get_all_sleep_history(limit=7, order="desc")
    except Exception as e:
        print(f"[ANALYTICS ERROR] Unable to query sleep history: {e}")
        logs = []

    if not logs:
        return {
            "status": "INSUFFICIENT_DATA",
            "terminal_report": "Insufficient telemetry. Log consecutive sleep cycles to establish baseline.",
            "voice_line": "Sleep log registered. Telemetry database insufficient for trend projection."
        }

    latest = logs[0]
    durations = [r["duration_hours"] for r in logs if r.get("duration_hours") is not None]
    interruptions = [r.get("interruptions", 0) for r in logs]

    latest_dur = latest.get("duration_hours", 7.0)
    latest_dis = latest.get("interruptions", 0)
    avg_dur = sum(durations) / len(durations)

    # Delta against baseline (7.5h recommended minimum)
    sleep_debt = sum(max(0.0, 7.5 - d) for d in durations)

    # Trajectory slope evaluation
    is_declining = False
    if len(durations) >= 3:
        recent_avg = sum(durations[:2]) / 2.0
        prior_avg = sum(durations[2:]) / len(durations[2:])
        if recent_avg < prior_avg - 0.75:
            is_declining = True

    # Alterra diagnostic classification & side effects
    if latest_dur < 5.0 or (latest_dur < 6.0 and latest_dis >= 3):
        status = "CRITICAL_DEFICIT"
        primary_warning = "Severe biological deficit detected. Neural operating capacity compromised."
        side_effects = [
            "Frontal lobe latency & sustained brain fog",
            "Impaired working memory and syntactic retention",
            "Elevated cortisol levels and erratic dopamine regulation",
            "Metabolic efficiency down 18-25%"
        ]
        pda_voice = (
            f"Diagnostics complete. Rest duration: {latest_dur:.1f} hours with {latest_dis} interruptions. "
            "Severe biological deficit detected. Expect pronounced brainfog, impaired working memory, "
            "and compromised cognitive velocity today. Alterra suggests you avoid complex decisions."
        )

    elif latest_dur < 6.5 or is_declining:
        status = "DEGRADED"
        primary_warning = "Sub-optimal recovery trajectory. Cumulative sleep debt compounding."
        side_effects = [
            "Delayed neuromuscular reaction times",
            "Mild executive dysfunction and reduced focus endurance",
            "Micro-fatigue during afternoon metabolic troughs"
        ]
        pda_voice = (
            f"Rest cycle recorded: {latest_dur:.1f} hours. "
            f"Recovery trajectory is declining, with an accumulated debt of {sleep_debt:.1f} hours across this window. "
            "Noticeable cognitive friction and reaction latency are mathematically anticipated."
        )

    elif latest_dis >= 3:
        status = "FRAGMENTED"
        primary_warning = "Sleep architecture fractured. Slow-wave and REM continuity interrupted."
        side_effects = [
            "Incomplete cellular waste clearance (glymphatic disruption)",
            "Elevated daytime sleepiness despite baseline time-in-bed",
            "Reduced systemic stress tolerance"
        ]
        pda_voice = (
            f"Recorded {latest_dur:.1f} hours, but detected {latest_dis} disruption events. "
            "Sleep fragmentation has compromised deep slow-wave repair. Vital signs suboptimal."
        )

    else:
        status = "OPTIMAL"
        primary_warning = "Sleep continuity and recovery within ideal Alterra parameters."
        side_effects = [
            "Neural pathway consolidation nominal",
            "Executive function baseline: 100%"
        ]
        pda_voice = (
            f"Sleep cycle registered: {latest_dur:.1f} hours with nominal fragmentation. "
            "Biological architecture restored to acceptable productivity margins."
        )

    lines = [
        f"--- ALTERRA RECOVERY DIAGNOSTIC: {status} ---",
        f"Last Session: {latest_dur:.1f} hrs | Disruptions: {latest_dis} | 7-Day Avg: {avg_dur:.1f} hrs",
        f"Cumulative Debt: {sleep_debt:.1f} hrs | Trend: {'DECLINING' if is_declining else 'STABLE'}",
        f"Status: {primary_warning}",
        "Anticipated Physiological Markers:"
    ]
    for se in side_effects:
        lines.append(f"  * {se}")
    lines.append("-------------------------------------------------")

    return {
        "status": status,
        "terminal_report": "\n".join(lines),
        "voice_line": pda_voice
    }