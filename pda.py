import os
from database import init_db, log_sleep, log_water, log_meal, get_today_totals
from hud_state import HUDState
import dialogues
from voice_engine import speak

hud = HUDState()

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def render_hud():
    totals = get_today_totals()
    h_status, h_min = hud.evaluate_hydration()
    n_status, n_min = hud.evaluate_nutrition()
    
    w_pct = min(100, int((totals['water_ml'] / hud.target_water_ml) * 100))
    m_pct = min(100, int((totals['meals_count'] / hud.target_meals) * 100))

    print("=" * 60)
    print("       ALTERRA PERSONAL BIOMETRIC MONITOR // ARX-10       ")
    print("=" * 60)
    
    # HYDRATION PANEL
    h_time_str = f"{h_min}m ago" if h_min != 999 else "None"
    print(f" [HYDRATION] Status: [{h_status}]")
    print(f"  Volume : {int(totals['water_ml'])} / {hud.target_water_ml} ml ({w_pct}%)")
    print(f"  Last   : {h_time_str} | Interval: {hud.hydration_interval_min}m")
    print("-" * 60)

    # NUTRITION PANEL
    n_time_str = f"{n_min}m ago" if n_min != 999 else "None"
    print(f" [NUTRITION] Status: [{n_status}]")
    print(f"  Meals  : {totals['meals_count']} / {hud.target_meals} logged today ({m_pct}%)")
    print(f"  Last   : {n_time_str} | Interval: {hud.meal_interval_min}m")
    print("-" * 60)

    # RECOVERY / SYSTEM
    mode_str = "STANDBY (SLEEP WINDOW)" if hud.is_sleep_window() else "ACTIVE MONITORING"
    print(f" [SYSTEM]    Telemetry Mode: {mode_str}")
    print("=" * 60)

def main():
    init_db()
    clear_screen()
    speak(dialogues.BOOT, mode="pda")

    while True:
        clear_screen()
        render_hud()

        # Check alerts
        if not hud.is_sleep_window():
            h_status, _ = hud.evaluate_hydration()
            n_status, _ = hud.evaluate_nutrition()
            
            if h_status in ["DUE", "OVERDUE"]:
                speak(dialogues.get_hydration_due_line(h_status), mode="pda")
            elif n_status in ["DUE", "OVERDUE"]:
                speak(dialogues.get_meal_due_line(n_status), mode="pda")

        print("\nCOMMANDS:")
        print("  [1] Log Water (Default 250ml)")
        print("  [2] Log Meal / Food Consumed")
        print("  [3] Log Sleep Session")
        print("  [4] Refresh HUD")
        print("  [5] Standby / Exit")
        
        choice = input("\nSelect Protocol > ").strip()

        if choice == "1":
            amt_input = input("Enter water volume in ml (Default 250): ").strip()
            amt = float(amt_input) if amt_input else 250.0
            log_water(amt)
            
            totals = get_today_totals()
            speak(dialogues.get_water_logged_line(amt, totals['water_ml'], hud.target_water_ml), mode="pda")

        elif choice == "2":
            tag = input("Meal tag (Breakfast / Lunch / Snack / Dinner) [Default: Meal]: ").strip() or "Meal"
            log_meal(tag)
            
            totals = get_today_totals()
            speak(dialogues.get_meal_logged_line(tag, totals['meals_count'], hud.target_meals), mode="pda")

        elif choice == "3":
            print("Timestamp format: 'YYYY-MM-DD HH:MM'")
            s_time = input("Onset time : ").strip()
            w_time = input("Wake time  : ").strip()
            disruptions = int(input("Awakenings / disruptions: ").strip() or 0)
            notes = input("Rest notes : ").strip()
            
            duration = log_sleep(s_time, w_time, disruptions, notes)
            speak(dialogues.get_sleep_eval_line(duration, disruptions), mode="pda")

        elif choice == "4":
            continue

        elif choice == "5":
            speak(dialogues.SHUTDOWN, mode="pda")
            break

if __name__ == "__main__":
    main()