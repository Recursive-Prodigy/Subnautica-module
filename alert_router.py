import requests
import threading
from voice_engine import speak
from config_manager import load_config

cfg = load_config() or {}
NTFY_TOPIC = cfg.get("ntfy_topic", "alterra_pda_user_vault")  # Custom private topic name
ENABLE_VOICE = cfg.get("enable_pc_voice", True)
ENABLE_PHONE = cfg.get("enable_phone_push", True)

def send_phone_notification(title: str, message: str, action_type: str = "water"):
    """Sends a native push notification to your phone with quick action buttons."""
    if not ENABLE_PHONE:
        return

    # Dynamic action buttons depending on alert type
    actions = []
    if action_type == "water":
        actions = [
            {"action": "http", "label": "+250ml Water", "url": f"{cfg.get('webhook_url', '')}/log-water", "method": "POST"}
        ]
    elif action_type == "meal":
        actions = [
            {"action": "http", "label": "+Log Meal", "url": f"{cfg.get('webhook_url', '')}/log-meal", "method": "POST"}
        ]

    try:
        requests.post(
            f"https://ntfy.sh/{NTFY_TOPIC}",
            data=message.encode("utf-8"),
            headers={
                "Title": title,
                "Priority": "high",
                "Tags": "warning,droplet" if action_type == "water" else "warning,fork_and_knife"
            },
            timeout=5
        )
    except Exception as e:
        print(f"[ALERT ROUTER] Push notification error: {e}")

def trigger_pda_alert(line: str, alert_type: str = "water"):
    """Fires voice on PC and push notification to phone in parallel."""
    # 1. PC Voice
    if ENABLE_VOICE:
        threading.Thread(target=speak, args=(line, "pda"), daemon=True).start()

    # 2. Mobile Push Notification
    title = "ALTERRA PDA // VITAL ALERT"
    threading.Thread(target=send_phone_notification, args=(title, line, alert_type), daemon=True).start()