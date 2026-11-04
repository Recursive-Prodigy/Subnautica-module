import time
import sys
from datetime import datetime
from hud_state import HUDState
import dialogues
from alert_router import trigger_pda_alert

def run_daemon():
    hud = HUDState()
    print("[ALTERRA PDA] Background Biometric Monitor active.")
    print("[ALTERRA PDA] Polling cycle: every 60 seconds.")

    last_water_state = None
    last_meal_state = None

    while True:
        try:
            # Check if currently inside sleep quiet window
            if not hud.is_sleep_window():
                h_status, h_min = hud.evaluate_hydration()
                n_status, n_min = hud.evaluate_nutrition()

                # Hydration alert evaluation
                if h_status in ["DUE", "OVERDUE"]:
                    if h_status != last_water_state:
                        line = dialogues.get_hydration_due_line(h_status)
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] HYDRATION ALERT: {h_status}")
                        trigger_pda_alert(line, alert_type="water")
                        last_water_state = h_status
                else:
                    last_water_state = None

                # Nutrition alert evaluation
                if n_status in ["DUE", "OVERDUE"]:
                    if n_status != last_meal_state:
                        line = dialogues.get_meal_due_line(n_status)
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] NUTRITION ALERT: {n_status}")
                        trigger_pda_alert(line, alert_type="meal")
                        last_meal_state = n_status
                else:
                    last_meal_state = None

        except Exception as e:
            print(f"[DAEMON ERROR] Check cycle failed: {e}")

        # Sleep for 60 seconds before next check
        time.sleep(60)

if __name__ == "__main__":
    run_daemon()