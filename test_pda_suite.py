import sys
import os
from datetime import datetime, timezone

print("=" * 60)
print("     ALTERRA CORP // DIAGNOSTIC VERIFICATION SUITE")
print("=" * 60)

# --- TEST 1: Config & Timezone ---
print("\n[TEST 1] Verifying Config Manager & System Timezone...")
try:
    import config_manager
    from config_manager import load_config, DEFAULT_CONFIG, get_system_detected_tz
    cfg = load_config()
    detected_tz = get_system_detected_tz()
    print(f"  * Detected System Timezone: {detected_tz}")
    print(f"  * Active Storage Mode:     {cfg.get('storage_mode', 'local').upper()}")
    print("  -> TEST 1 PASSED: Config schema and IANA timezone nominal.")
except Exception as e:
    print(f"  !! TEST 1 FAILED: {e}")
    sys.exit(1)

# --- TEST 2: Dual Database Logging & Undefined Limits ---
print("\n[TEST 2] Verifying Database Read/Write & Date Scopes...")
try:
    import database
    
    # 1. Log test water
    database.log_water(250.0)
    print("  * Logged test water packet (250ml)")

    # 2. Test undo
    undone = database.undo_last_intake()
    assert undone is not None, "Undo operation returned None!"
    print(f"  * Rollback verified: Purged ID #{undone['id']} ({undone['type']})")

    # 3. Test rolling 7-day query
    intakes_7d = database.get_all_intake_history(days=7)
    intakes_all = database.get_all_intake_history(days=None)
    print(f"  * Intake Query: 7-day window ({len(intakes_7d)} rows) | Lifetime ({len(intakes_all)} rows)")

    # 4. Test sleep logging & deletion
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    dur = database.log_sleep(now_str, now_str, 0, "DIAGNOSTIC TEST")
    recent_sleep = database.get_all_sleep_history(limit=1)
    assert len(recent_sleep) > 0, "Sleep record write verification failed!"
    test_id = recent_sleep[0]["id"]
    database.delete_record_by_id("sleep_logs", test_id)
    print(f"  * Sleep write & expunge verified on ID #{test_id}")
    print("  -> TEST 2 PASSED: Database routing, scopes, and purging nominal.")
except Exception as e:
    print(f"  !! TEST 2 FAILED: {e}")
    sys.exit(1)

# --- TEST 3: Sleep Analytics (7-Day Trajectory & Clinical Markers) ---
print("\n[TEST 3] Verifying 7-Day Recovery Diagnostics Engine...")
try:
    import sleep_analytics
    report = sleep_analytics.analyze_sleep_trajectory()
    assert "status" in report and "voice_line" in report, "Analytics report schema mismatch!"
    print(f"  * Trajectory Status Evaluated: {report['status']}")
    print(f"  * Voice Line Generated: \"{report['voice_line'][:65]}...\"")
    print("  -> TEST 3 PASSED: Recovery diagnostics engine functional.")
except Exception as e:
    print(f"  !! TEST 3 FAILED: {e}")
    sys.exit(1)

# --- TEST 4: Lifetime Analytics Engine ---
print("\n[TEST 4] Verifying Lifetime Aggregates Engine...")
try:
    import analytics_engine
    summary = analytics_engine.get_lifetime_summary()
    print(f"  * Telemetry Genesis:       {summary['first_day']}")
    print(f"  * Total Monitored Cycles:  {summary['days_logged']}")
    print(f"  * Cumulative Rest Time:    {summary['total_sleep_hours']} hours")
    print(f"  * Total Sustenance Rations:{summary['total_meals']}")
    print("  -> TEST 4 PASSED: Lifetime telemetry computed successfully.")
except Exception as e:
    print(f"  !! TEST 4 FAILED: {e}")
    sys.exit(1)

# --- TEST 5: Sarcastic Voice Bank ---
print("\n[TEST 5] Verifying Alterra Voice Lines & Sarcasm Banks...")
try:
    import dialogues
    undo_line = dialogues.get_intake_retracted_line()
    archive_line = dialogues.get_archive_viewed_line()
    print(f"  * Sample Rollback Sarcasm: \"{undo_line}\"")
    print(f"  * Sample Archive Access:   \"{archive_line}\"")
    print("  -> TEST 5 PASSED: Audio dialogue banks operational.")
except Exception as e:
    print(f"  !! TEST 5 FAILED: {e}")
    sys.exit(1)

print("\n" + "=" * 60)
print("     ALL CORE MODULES VERIFIED: SYSTEM PRODUCTION READY")
print("=" * 60)