import database

def get_lifetime_summary() -> dict:
    """
    Aggregates full telemetry data from day 1 across hydration,
    sustenance meals, and sleep cycles.
    """
    intakes = database.get_all_intake_history(limit=None, days=None)
    sleeps = database.get_all_sleep_history(limit=None, days=None)

    total_water = sum(r["amount"] for r in intakes if r.get("type") == "hydration")
    total_meals = sum(1 for r in intakes if r.get("type") == "meal")

    sleep_durations = [r["duration_hours"] for r in sleeps if r.get("duration_hours") is not None]
    total_sleep_hours = sum(sleep_durations)
    avg_sleep_hours = (total_sleep_hours / len(sleep_durations)) if sleep_durations else 0.0

    all_dates = []
    for i in intakes:
        if i.get("logged_at"):
            all_dates.append(str(i["logged_at"])[:10])
    for s in sleeps:
        if s.get("sleep_time"):
            all_dates.append(str(s["sleep_time"])[:10])

    unique_days = sorted(list(set(all_dates)))
    days_logged = len(unique_days)
    first_day = unique_days[0] if unique_days else "N/A"

    return {
        "days_logged": days_logged,
        "first_day": first_day,
        "total_water_ml": total_water,
        "total_meals": total_meals,
        "total_sleep_cycles": len(sleeps),
        "total_sleep_hours": round(total_sleep_hours, 1),
        "avg_sleep_hours": round(avg_sleep_hours, 2),
        "avg_water_daily": round(total_water / days_logged, 1) if days_logged else 0.0,
        "avg_meals_daily": round(total_meals / days_logged, 1) if days_logged else 0.0
    }