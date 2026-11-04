import sys
import tkinter as tk
from tkinter import ttk, messagebox
import threading
from datetime import datetime, time, timezone, timedelta
import pystray
from PIL import Image, ImageDraw

import database
from hud_state import HUDState
import dialogues
from voice_engine import speak
import config_manager

# --- ALTERRA PALETTE CONSTANTS ---
BG_DARK = "#040b11"
PANEL_BG = "#081620"
PANEL_BORDER = "#14374a"
CYAN_BRIGHT = "#00f0ff"
CYAN_DIM = "#008a99"
TEXT_LIGHT = "#d4f7ff"
TEXT_MUTED = "#527e8a"
WARN_AMBER = "#ffaa00"
ALERT_RED = "#ff3344"
SUCCESS_GREEN = "#00ff88"


def create_tray_icon():
    """Generates a dynamic 64x64 Alterra cyan hexagon icon in memory."""
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    points = [(32, 4), (60, 20), (60, 44), (32, 60), (4, 44), (4, 20)]
    draw.polygon(points, fill=(8, 22, 32, 255), outline=(0, 240, 255, 255), width=3)
    draw.ellipse((26, 26, 38, 38), fill=(0, 240, 255, 255))
    return img


class CircularHUDGauge(tk.Canvas):
    def __init__(self, parent, size=135, ring_width=7, title="GAUGE", base_color=CYAN_BRIGHT, **kwargs):
        super().__init__(parent, width=size, height=size, bg=PANEL_BG, bd=0, highlightthickness=0, **kwargs)
        self.size = size
        self.ring_width = ring_width
        self.title = title
        self.base_color = base_color
        
        self.cx = size / 2
        self.cy = size / 2
        self.radius = (size / 2) - ring_width - 4

        self.fraction = 1.0
        self.center_text = "--"
        self.sub_text = title
        self.status = "OPTIMAL"

        self.blink_state = False
        self.is_blinking = False
        self._blink_job = None

        self._draw_gauge()

    def set_data(self, fraction: float, center_val: str, sub_val: str, status: str = "OPTIMAL"):
        self.fraction = max(0.0, min(1.0, fraction))
        self.center_text = center_val
        self.sub_text = sub_val
        self.status = status

        if status in ("OVERDUE", "CRITICAL"):
            if not self.is_blinking:
                self.is_blinking = True
                self._run_blink()
        else:
            self.is_blinking = False
            if self._blink_job:
                self.after_cancel(self._blink_job)
                self._blink_job = None
            self.blink_state = False

        self._draw_gauge()

    def _run_blink(self):
        if not self.is_blinking:
            return
        self.blink_state = not self.blink_state
        self._draw_gauge()
        self._blink_job = self.after(550, self._run_blink)

    def _draw_gauge(self):
        self.delete("all")

        if self.status in ("OVERDUE", "CRITICAL"):
            stroke_color = ALERT_RED if not self.blink_state else "#450c12"
            fill_glow = "#21090d"
        elif self.status == "DUE":
            stroke_color = WARN_AMBER
            fill_glow = "#1a1304"
        else:
            stroke_color = self.base_color
            fill_glow = "#04141e"

        r = self.radius
        x0, y0 = self.cx - r, self.cy - r
        x1, y1 = self.cx + r, self.cy + r

        # Background circular body
        self.create_oval(x0, y0, x1, y1, fill=fill_glow, outline="#0d2838", width=1)

        # Unfilled track
        self.create_arc(
            x0, y0, x1, y1,
            start=90, extent=-359.9,
            style="arc", outline="#0a202d", width=self.ring_width
        )

        # Progress sweep arc
        extent = -359.9 * self.fraction
        if abs(extent) > 1.0:
            self.create_arc(
                x0, y0, x1, y1,
                start=90, extent=extent,
                style="arc", outline=stroke_color, width=self.ring_width
            )

        # Center and sub readouts
        self.create_text(
            self.cx, self.cy - 12,
            text=self.title, fill="#527e8a", font=("Consolas", 8, "bold")
        )
        self.create_text(
            self.cx, self.cy + 5,
            text=self.center_text, fill=stroke_color, font=("Consolas", 10, "bold")
        )
        self.create_text(
            self.cx, self.cy + 22,
            text=self.sub_text, fill="#7aa0ab", font=("Consolas", 8)
        )


class AlterraProgressBar(tk.Canvas):
    def __init__(self, parent, width=320, height=14, **kwargs):
        super().__init__(parent, width=width, height=height, bg=PANEL_BG, highlightthickness=1, highlightbackground=PANEL_BORDER, **kwargs)
        self.w = width
        self.h = height

    def set_progress(self, current, target, color=CYAN_BRIGHT):
        self.delete("all")
        frac = max(0.0, min(1.0, current / target if target > 0 else 0.0))
        fill_width = int(self.w * frac)
        self.create_rectangle(0, 0, self.w, self.h, fill="#05121b", outline="")
        segment_width = 8
        spacing = 3
        x = 2
        while x < fill_width - 2:
            seg_end = min(x + segment_width, fill_width - 2)
            self.create_rectangle(x, 2, seg_end, self.h - 2, fill=color, outline="")
            x += segment_width + spacing


class SubnauticaPDAGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("ALTERRA CORP // PERSONAL BIOMETRIC MONITOR (ARX-10)")
        self.root.geometry("860x780")
        self.root.configure(bg=BG_DARK)
        self.root.resizable(False, False)

        self.hud = HUDState()
        self._last_h_alert = None
        self._last_n_alert = None

        self._build_header()
        self._build_vitals_panel()
        self._build_action_deck()
        self._build_telemetry_terminal()

        self.root.protocol("WM_DELETE_WINDOW", self.hide_to_tray)

        self.tray_icon = None
        self._init_tray()

        # Initial Boot Audio
        threading.Thread(target=speak, args=(dialogues.get_dialogue("boot"), "pda"), daemon=True).start()

        self.refresh_display()
        self.poll_timers()

    def _build_header(self):
        header_frame = tk.Frame(self.root, bg=BG_DARK, pady=10, padx=20)
        header_frame.pack(fill="x")
        
        title_box = tk.Frame(header_frame, bg=BG_DARK)
        title_box.pack(side="left")

        tk.Label(title_box, text="ALTERRA CORPORATION", font=("Consolas", 10, "bold"), fg=CYAN_DIM, bg=BG_DARK).pack(anchor="w")
        tk.Label(title_box, text="PDA REC-01 // BIOMETRIC HUD", font=("Consolas", 16, "bold"), fg=CYAN_BRIGHT, bg=BG_DARK).pack(anchor="w")

        right_box = tk.Frame(header_frame, bg=BG_DARK)
        right_box.pack(side="right", anchor="e")

        self.lbl_system_mode = tk.Label(right_box, text="[ TELEMETRY ACTIVE ]", font=("Consolas", 10, "bold"), fg=SUCCESS_GREEN, bg=BG_DARK)
        self.lbl_system_mode.pack(side="top", anchor="e", pady=(0, 4))

        btn_header_settings = tk.Button(
            right_box, text="⚙ SETTINGS", font=("Consolas", 8, "bold"),
            bg="#0e2838", fg=CYAN_BRIGHT, activebackground=CYAN_DIM, activeforeground="#ffffff",
            bd=1, relief="ridge", padx=8, pady=2, cursor="hand2", command=self.action_settings_dialog
        )
        btn_header_settings.pack(side="top", anchor="e")

        divider = tk.Frame(self.root, height=2, bg=CYAN_DIM)
        divider.pack(fill="x", padx=15, pady=(10, 6))

    def _build_vitals_panel(self):
        panel_container = tk.Frame(self.root, bg=BG_DARK, padx=20)
        panel_container.pack(fill="x", pady=2)

        # --- VIEW 1: CIRCULAR DECAY METERS ---
        card_circles = tk.Frame(panel_container, bg=PANEL_BG, bd=1, relief="solid", highlightbackground=PANEL_BORDER, highlightthickness=1, padx=12, pady=10)
        card_circles.pack(fill="x", pady=4)

        c_header = tk.Frame(card_circles, bg=PANEL_BG)
        c_header.pack(fill="x", pady=(0, 4))
        tk.Label(c_header, text="VITAL SIGNS INTERVAL TELEMETRY", font=("Consolas", 10, "bold"), fg=CYAN_DIM, bg=PANEL_BG).pack(side="left")
        self.lbl_vitals_summary = tk.Label(c_header, text="ALL PARAMETERS NOMINAL", font=("Consolas", 9, "bold"), fg=SUCCESS_GREEN, bg=PANEL_BG)
        self.lbl_vitals_summary.pack(side="right")

        gauges_row = tk.Frame(card_circles, bg=PANEL_BG)
        gauges_row.pack(fill="x", expand=True, pady=2)

        self.gauge_water = CircularHUDGauge(gauges_row, size=135, ring_width=7, title="WATER", base_color=CYAN_BRIGHT)
        self.gauge_water.pack(side="left", expand=True)

        self.gauge_food = CircularHUDGauge(gauges_row, size=135, ring_width=7, title="FOOD", base_color="#28d7a0")
        self.gauge_food.pack(side="left", expand=True)

        self.gauge_sleep = CircularHUDGauge(gauges_row, size=135, ring_width=7, title="REST", base_color="#b070ff")
        self.gauge_sleep.pack(side="left", expand=True)

        # --- VIEW 2: PROGRESS LINES ---
        # Hydration Progress Bar
        self.card_water = tk.Frame(panel_container, bg=PANEL_BG, bd=1, relief="solid", highlightbackground=PANEL_BORDER, highlightthickness=1, padx=15, pady=8)
        self.card_water.pack(fill="x", pady=3)
        w_header = tk.Frame(self.card_water, bg=PANEL_BG)
        w_header.pack(fill="x")
        tk.Label(w_header, text="HYDRATION INTEGRITY", font=("Consolas", 10, "bold"), fg=CYAN_BRIGHT, bg=PANEL_BG).pack(side="left")
        self.lbl_water_status = tk.Label(w_header, text="OPTIMAL", font=("Consolas", 9, "bold"), fg=SUCCESS_GREEN, bg=PANEL_BG)
        self.lbl_water_status.pack(side="right")
        self.water_bar = AlterraProgressBar(self.card_water, width=780, height=12)
        self.water_bar.pack(pady=5)
        w_stats = tk.Frame(self.card_water, bg=PANEL_BG)
        w_stats.pack(fill="x")
        self.lbl_water_vals = tk.Label(w_stats, text="0 / 2500 ml (0%)", font=("Consolas", 9), fg=TEXT_LIGHT, bg=PANEL_BG)
        self.lbl_water_vals.pack(side="left")
        self.lbl_water_timer = tk.Label(w_stats, text="Last: Never | Interval: 75m", font=("Consolas", 9), fg=TEXT_MUTED, bg=PANEL_BG)
        self.lbl_water_timer.pack(side="right")

        # Sustenance Progress Bar
        self.card_food = tk.Frame(panel_container, bg=PANEL_BG, bd=1, relief="solid", highlightbackground=PANEL_BORDER, highlightthickness=1, padx=15, pady=8)
        self.card_food.pack(fill="x", pady=3)
        f_header = tk.Frame(self.card_food, bg=PANEL_BG)
        f_header.pack(fill="x")
        tk.Label(f_header, text="SUSTENANCE & METABOLISM", font=("Consolas", 10, "bold"), fg=CYAN_BRIGHT, bg=PANEL_BG).pack(side="left")
        self.lbl_food_status = tk.Label(f_header, text="OPTIMAL", font=("Consolas", 9, "bold"), fg=SUCCESS_GREEN, bg=PANEL_BG)
        self.lbl_food_status.pack(side="right")
        self.food_bar = AlterraProgressBar(self.card_food, width=780, height=12)
        self.food_bar.pack(pady=5)
        f_stats = tk.Frame(self.card_food, bg=PANEL_BG)
        f_stats.pack(fill="x")
        self.lbl_food_vals = tk.Label(f_stats, text="0 / 4 Meals (0%)", font=("Consolas", 9), fg=TEXT_LIGHT, bg=PANEL_BG)
        self.lbl_food_vals.pack(side="left")
        self.lbl_food_timer = tk.Label(f_stats, text="Last: Never | Interval: 210m", font=("Consolas", 9), fg=TEXT_MUTED, bg=PANEL_BG)
        self.lbl_food_timer.pack(side="right")

    def _build_action_deck(self):
        deck_frame = tk.Frame(self.root, bg=BG_DARK, padx=20, pady=4)
        deck_frame.pack(fill="x")

        btn_water = tk.Button(
            deck_frame, text="+ LOG HYDRATION (250ml)", font=("Consolas", 10, "bold"),
            bg="#0e2838", fg=CYAN_BRIGHT, activebackground=CYAN_DIM, activeforeground="#ffffff",
            bd=1, relief="ridge", padx=10, pady=8, cursor="hand2", command=self.action_log_water
        )
        btn_water.pack(side="left", expand=True, fill="x", padx=3)

        btn_meal = tk.Button(
            deck_frame, text="+ LOG SUSTENANCE MEAL", font=("Consolas", 10, "bold"),
            bg="#0e2838", fg=CYAN_BRIGHT, activebackground=CYAN_DIM, activeforeground="#ffffff",
            bd=1, relief="ridge", padx=10, pady=8, cursor="hand2", command=self.action_log_meal
        )
        btn_meal.pack(side="left", expand=True, fill="x", padx=3)

        btn_sleep = tk.Button(
            deck_frame, text="+ LOG SLEEP CYCLE", font=("Consolas", 10, "bold"),
            bg="#0e2838", fg=CYAN_BRIGHT, activebackground=CYAN_DIM, activeforeground="#ffffff",
            bd=1, relief="ridge", padx=10, pady=8, cursor="hand2", command=self.action_log_sleep_dialog
        )
        btn_sleep.pack(side="left", expand=True, fill="x", padx=3)

        btn_undo = tk.Button(
            deck_frame, text="↺ UNDO LAST", font=("Consolas", 10, "bold"),
            bg="#211014", fg="#ff4455", activebackground="#38151c", activeforeground="#ffffff",
            bd=1, relief="ridge", padx=10, pady=8, cursor="hand2", command=self.action_undo_intake
        )
        btn_undo.pack(side="left", expand=False, padx=3)

        btn_archives = tk.Button(
            deck_frame, text="📊 ARCHIVES", font=("Consolas", 10, "bold"),
            bg="#0e2838", fg=CYAN_BRIGHT, activebackground=CYAN_DIM, activeforeground="#ffffff",
            bd=1, relief="ridge", padx=10, pady=8, cursor="hand2", command=self.action_view_archives
        )
        btn_archives.pack(side="left", expand=False, padx=3)

    def _build_telemetry_terminal(self):
        term_frame = tk.Frame(self.root, bg=BG_DARK, padx=20, pady=6)
        term_frame.pack(fill="both", expand=True)

        tk.Label(term_frame, text="PDA LOG PROTOCOL OUTPUT", font=("Consolas", 9, "bold"), fg=CYAN_DIM, bg=BG_DARK).pack(anchor="w")

        self.terminal = tk.Text(
            term_frame, bg="#02070b", fg=TEXT_LIGHT, insertbackground=CYAN_BRIGHT,
            font=("Consolas", 9), height=6, bd=1, relief="solid", highlightthickness=1,
            highlightbackground=PANEL_BORDER, padx=10, pady=6
        )
        self.terminal.pack(fill="both", expand=True)
        self.log_terminal("Alterra ARX-10 Operating System Initialized.")
        self.log_terminal("Biometric telemetry online.")

    def log_terminal(self, text: str):
        now_str = datetime.now().strftime("%H:%M:%S")
        self.terminal.insert("end", f"[{now_str}] > {text}\n")
        self.terminal.see("end")

    def refresh_display(self):
        totals = database.get_today_totals()
        h_status, h_min = self.hud.evaluate_hydration()
        n_status, n_min = self.hud.evaluate_nutrition()

        w_ml = totals['water_ml']
        w_tgt = self.hud.target_water_ml
        m_cnt = totals['meals_count']
        m_tgt = self.hud.target_meals

        # --- 1. CIRCULAR DECAY GAUGES ---
        h_interval = self.hud.hydration_interval_min
        w_frac = max(0.0, 1.0 - (h_min / h_interval)) if h_min != 999 else 0.0
        w_sub = f"{max(0, h_interval - h_min)}m left" if h_min < h_interval else f"+{h_min - h_interval}m over"
        self.gauge_water.set_data(
            fraction=w_frac,
            center_val=f"{int(w_ml)}ml",
            sub_val=w_sub,
            status=h_status
        )

        m_interval = self.hud.meal_interval_min
        n_frac = max(0.0, 1.0 - (n_min / m_interval)) if n_min != 999 else 0.0
        n_sub = f"{max(0, m_interval - n_min)}m left" if n_min < m_interval else f"+{n_min - m_interval}m over"
        self.gauge_food.set_data(
            fraction=n_frac,
            center_val=f"{m_cnt}/{m_tgt}",
            sub_val=n_sub,
            status=n_status
        )

        sleep_history = database.get_all_sleep_history(limit=1)
        if sleep_history:
            last_wake_str = sleep_history[0].get("wake_time", "")
            try:
                t_wake = datetime.strptime(last_wake_str, "%Y-%m-%d %H:%M")
                hours_awake = (datetime.now() - t_wake).total_seconds() / 3600.0
            except Exception:
                hours_awake = 8.0
        else:
            hours_awake = 8.0

        alertness_frac = max(0.0, min(1.0, 1.0 - (hours_awake / 16.0)))
        s_status = "OPTIMAL" if hours_awake < 14.0 else ("DUE" if hours_awake < 17.0 else "OVERDUE")
        s_sub = f"{hours_awake:.1f}h awake"
        self.gauge_sleep.set_data(
            fraction=alertness_frac,
            center_val=f"{int(alertness_frac * 100)}%",
            sub_val=s_sub,
            status=s_status
        )

        # Overall summary indicator
        if "OVERDUE" in (h_status, n_status, s_status):
            self.lbl_vitals_summary.config(text="CRITICAL BIOLOGICAL DEFICIT", fg=ALERT_RED)
        elif "DUE" in (h_status, n_status, s_status):
            self.lbl_vitals_summary.config(text="MAINTENANCE INTERVAL REQUIRED", fg=WARN_AMBER)
        else:
            self.lbl_vitals_summary.config(text="ALL PARAMETERS NOMINAL", fg=SUCCESS_GREEN)

        # --- 2. LINEAR PROGRESS BARS ---
        w_pct = int((w_ml / w_tgt) * 100) if w_tgt else 0
        self.lbl_water_vals.config(text=f"{int(w_ml)} / {w_tgt} ml ({w_pct}%)")
        self.lbl_water_status.config(text=h_status)
        h_color = SUCCESS_GREEN if h_status in ["OPTIMAL", "TARGET_REACHED"] else (WARN_AMBER if h_status == "DUE" else ALERT_RED)
        self.lbl_water_status.config(fg=h_color)
        self.water_bar.set_progress(w_ml, w_tgt, color=h_color)
        h_time_str = f"{h_min}m ago" if h_min != 999 else "Never"
        self.lbl_water_timer.config(text=f"Last: {h_time_str} | Interval: {self.hud.hydration_interval_min}m")

        m_pct = int((m_cnt / m_tgt) * 100) if m_tgt else 0
        self.lbl_food_vals.config(text=f"{m_cnt} / {m_tgt} Meals ({m_pct}%)")
        self.lbl_food_status.config(text=n_status)
        n_color = SUCCESS_GREEN if n_status in ["OPTIMAL", "TARGET_REACHED"] else (WARN_AMBER if n_status == "DUE" else ALERT_RED)
        self.lbl_food_status.config(fg=n_color)
        self.food_bar.set_progress(m_cnt, m_tgt, color=n_color)
        n_time_str = f"{n_min}m ago" if n_min != 999 else "Never"
        self.lbl_food_timer.config(text=f"Last: {n_time_str} | Interval: {self.hud.meal_interval_min}m")

        if self.hud.is_sleep_window():
            self.lbl_system_mode.config(text="[ STANDBY - SLEEP CYCLE ]", fg=TEXT_MUTED)
        else:
            self.lbl_system_mode.config(text="[ TELEMETRY ACTIVE ]", fg=SUCCESS_GREEN)

    def poll_timers(self):
        self.refresh_display()

        if not self.hud.is_sleep_window():
            h_status, _ = self.hud.evaluate_hydration()
            n_status, _ = self.hud.evaluate_nutrition()

            if h_status in ["DUE", "OVERDUE"] and self._last_h_alert != h_status:
                self._last_h_alert = h_status
                cat = "hydration_overdue" if h_status == "OVERDUE" else "hydration_due"
                line = dialogues.get_dialogue(cat)
                self.log_terminal(f"TELEMETRY ALERT: {line}")
                threading.Thread(target=speak, args=(line, "pda"), daemon=True).start()
            elif h_status == "OPTIMAL":
                self._last_h_alert = None

            if n_status in ["DUE", "OVERDUE"] and self._last_n_alert != n_status:
                self._last_n_alert = n_status
                cat = "meal_overdue" if n_status == "OVERDUE" else "meal_due"
                line = dialogues.get_dialogue(cat)
                self.log_terminal(f"TELEMETRY ALERT: {line}")
                threading.Thread(target=speak, args=(line, "pda"), daemon=True).start()
            elif n_status == "OPTIMAL":
                self._last_n_alert = None

        self.root.after(60000, self.poll_timers)

    def _init_tray(self):
        menu = pystray.Menu(
            pystray.MenuItem("Open Alterra HUD", self.show_from_tray, default=True),
            pystray.MenuItem("+ Log Water (250ml)", lambda: self.root.after(0, self.action_log_water)),
            pystray.MenuItem("+ Log Sustenance Meal", lambda: self.root.after(0, self.action_log_meal)),
            pystray.MenuItem("↺ Undo Last Entry", lambda: self.root.after(0, self.action_undo_intake)),
            pystray.MenuItem("📊 View Telemetry Archives", lambda: self.root.after(0, self.action_view_archives)),
            pystray.MenuItem("⚙ Settings & Bio-Parameters", lambda: self.root.after(0, self.action_settings_dialog)),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Exit Alterra PDA", self.quit_application)
        )
        self.tray_icon = pystray.Icon("AlterraPDA", create_tray_icon(), "Alterra PDA ARX-10", menu)
        threading.Thread(target=self.tray_icon.run, daemon=True).start()

    def hide_to_tray(self):
        self.root.withdraw()
        if self.tray_icon:
            try:
                self.tray_icon.notify("Alterra ARX-10 active in background telemetry mode.", "PDA Standby")
            except Exception:
                pass

    def show_from_tray(self, icon=None, item=None):
        self.root.after(0, self._restore_window)

    def _restore_window(self):
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()
        self.refresh_display()

    def quit_application(self, icon=None, item=None):
        if self.tray_icon:
            self.tray_icon.stop()
        shutdown_msg = dialogues.SHUTDOWN
        threading.Thread(target=speak, args=(shutdown_msg, "pda"), daemon=False).start()
        self.root.after(600, self.root.destroy)

    def action_log_water(self):
        amount = 250.0
        database.log_water(amount)
        totals = database.get_today_totals()
        line = dialogues.get_water_logged_line(amount, totals['water_ml'], self.hud.target_water_ml)
        self.log_terminal(f"Logged 250ml water. Today: {int(totals['water_ml'])}ml")
        self.refresh_display()
        threading.Thread(target=speak, args=(line, "pda"), daemon=True).start()

    def action_log_meal(self):
        database.log_meal(tag="Standard Ration")
        totals = database.get_today_totals()
        line = dialogues.get_meal_logged_line("Sustenance ration", totals['meals_count'], self.hud.target_meals)
        self.log_terminal(f"Logged sustenance. Count today: {totals['meals_count']}")
        self.refresh_display()
        threading.Thread(target=speak, args=(line, "pda"), daemon=True).start()

    def action_undo_intake(self):
        deleted = database.undo_last_intake()
        if not deleted:
            self.log_terminal("UNDO ERROR: No recent telemetry entries found to purge.")
            return

        i_type = deleted.get("type", "unknown")
        amt = deleted.get("amount", 0)
        tag = deleted.get("tag", "")

        msg = f"Purged {int(amt)}ml water" if i_type == "hydration" else f"Purged meal entry ({tag})"
        self.log_terminal(f"TELEMETRY ROLLBACK: {msg}")
        self.refresh_display()

        line = dialogues.get_intake_retracted_line()
        threading.Thread(target=speak, args=(line, "pda"), daemon=True).start()

    def action_log_sleep_dialog(self):
        win = tk.Toplevel(self.root)
        win.title("LOG SLEEP CYCLE")
        win.geometry("460x340")
        win.configure(bg=PANEL_BG)
        win.resizable(False, False)

        tk.Label(
            win, text="REST RECOVERY TELEMETRY",
            font=("Consolas", 11, "bold"), fg=CYAN_BRIGHT, bg=PANEL_BG
        ).pack(pady=10)

        from time_sync import time_manager
        current_dt = time_manager.now()

        grid_frame = tk.Frame(win, bg=PANEL_BG)
        grid_frame.pack(padx=20, fill="x", pady=5)

        tk.Label(grid_frame, text="Wake Date (YYYY-MM-DD):", font=("Consolas", 9), fg=TEXT_LIGHT, bg=PANEL_BG).grid(row=0, column=0, sticky="w", pady=6)
        entry_date = tk.Entry(grid_frame, bg="#02070b", fg=CYAN_BRIGHT, font=("Consolas", 9), width=15)
        entry_date.insert(0, current_dt.strftime("%Y-%m-%d"))
        entry_date.grid(row=0, column=1, columnspan=2, sticky="w", pady=6, padx=5)

        tk.Label(grid_frame, text="Sleep Time (HH:MM):", font=("Consolas", 9), fg=TEXT_LIGHT, bg=PANEL_BG).grid(row=1, column=0, sticky="w", pady=6)
        entry_s_time = tk.Entry(grid_frame, bg="#02070b", fg=CYAN_BRIGHT, font=("Consolas", 9), width=8)
        entry_s_time.insert(0, "11:30")
        entry_s_time.grid(row=1, column=1, sticky="w", pady=6, padx=5)
        combo_s_ampm = ttk.Combobox(grid_frame, values=["PM", "AM"], width=4, state="readonly")
        combo_s_ampm.set("PM")
        combo_s_ampm.grid(row=1, column=2, sticky="w", pady=6)

        tk.Label(grid_frame, text="Wake Time (HH:MM):", font=("Consolas", 9), fg=TEXT_LIGHT, bg=PANEL_BG).grid(row=2, column=0, sticky="w", pady=6)
        entry_w_time = tk.Entry(grid_frame, bg="#02070b", fg=CYAN_BRIGHT, font=("Consolas", 9), width=8)
        entry_w_time.insert(0, current_dt.strftime("%I:%M").strip().lstrip("0") or "7:00")
        entry_w_time.grid(row=2, column=1, sticky="w", pady=6, padx=5)
        combo_w_ampm = ttk.Combobox(grid_frame, values=["AM", "PM"], width=4, state="readonly")
        combo_w_ampm.set(current_dt.strftime("%p"))
        combo_w_ampm.grid(row=2, column=2, sticky="w", pady=6)

        tk.Label(grid_frame, text="Disruptions:", font=("Consolas", 9), fg=TEXT_LIGHT, bg=PANEL_BG).grid(row=3, column=0, sticky="w", pady=6)
        entry_dis = tk.Entry(grid_frame, bg="#02070b", fg=CYAN_BRIGHT, font=("Consolas", 9), width=8)
        entry_dis.insert(0, "0")
        entry_dis.grid(row=3, column=1, sticky="w", pady=6, padx=5)

        def parse_time_component(time_str: str, ampm: str):
            parts = time_str.strip().split(":")
            if len(parts) != 2:
                raise ValueError("Format must be HH:MM")
            hr = int(parts[0])
            mn = int(parts[1])
            if hr < 1 or hr > 12 or mn < 0 or mn > 59:
                raise ValueError("Invalid hour or minute")
            if ampm.upper() == "PM" and hr != 12:
                hr += 12
            elif ampm.upper() == "AM" and hr == 12:
                hr = 0
            return hr, mn

        def save_and_close():
            try:
                d_str = entry_date.get().strip()
                wake_date = datetime.strptime(d_str, "%Y-%m-%d")

                s_hr, s_mn = parse_time_component(entry_s_time.get(), combo_s_ampm.get())
                w_hr, w_mn = parse_time_component(entry_w_time.get(), combo_w_ampm.get())

                t_wake = wake_date.replace(hour=w_hr, minute=w_mn, second=0)
                t_sleep = wake_date.replace(hour=s_hr, minute=s_mn, second=0)

                if t_wake <= t_sleep:
                    t_sleep -= timedelta(days=1)

                dis_val = int(entry_dis.get().strip() or 0)

                dur = database.log_sleep(
                    t_sleep.strftime("%Y-%m-%d %H:%M"),
                    t_wake.strftime("%Y-%m-%d %H:%M"),
                    dis_val,
                    "Manual HUD Entry"
                )
                win.destroy()

                import sleep_analytics
                report = sleep_analytics.analyze_sleep_trajectory()

                self.log_terminal(f"Logged Sleep: {dur:.1f}h (Disruptions: {dis_val})")
                for r_line in report["terminal_report"].split("\n"):
                    self.log_terminal(r_line)

                self.refresh_display()
                threading.Thread(target=speak, args=(report["voice_line"], "pda"), daemon=True).start()

            except ValueError as ve:
                messagebox.showerror("Time Error", f"Invalid time or date input: {ve}")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to record sleep cycle: {e}")

        btn_save = tk.Button(
            win, text="CONFIRM RECOVERY", font=("Consolas", 10, "bold"),
            bg="#0e2838", fg=CYAN_BRIGHT, activebackground=CYAN_DIM,
            bd=1, relief="ridge", pady=6, cursor="hand2", command=save_and_close
        )
        btn_save.pack(pady=15, fill="x", padx=20)

    def action_view_archives(self):
        win = tk.Toplevel(self.root)
        win.title("ALTERRA CORP // BIOMETRIC ARCHIVES & TELEMETRY LOGS")
        win.geometry("860x560")
        win.configure(bg=PANEL_BG)

        threading.Thread(target=speak, args=(dialogues.get_archive_viewed_line(), "pda"), daemon=True).start()

        archive_scope = {"days": 7}

        header_bar = tk.Frame(win, bg=PANEL_BG, padx=12, pady=8)
        header_bar.pack(fill="x")

        lbl_filter = tk.Label(header_bar, text="TELEMETRY SCOPE:", font=("Consolas", 9, "bold"), fg=TEXT_MUTED, bg=PANEL_BG)
        lbl_filter.pack(side="left", padx=(0, 10))

        btn_scope_7d = tk.Button(
            header_bar, text="[ LAST 7 DAYS ]", font=("Consolas", 9, "bold"),
            bg="#0e2838", fg=CYAN_BRIGHT, activebackground=CYAN_DIM, activeforeground="#ffffff",
            bd=1, relief="ridge", padx=10, pady=3, cursor="hand2"
        )
        btn_scope_7d.pack(side="left", padx=3)

        btn_scope_all = tk.Button(
            header_bar, text="[ LIFETIME ARCHIVE ]", font=("Consolas", 9, "bold"),
            bg="#0c202d", fg=TEXT_MUTED, activebackground=CYAN_DIM, activeforeground="#ffffff",
            bd=1, relief="ridge", padx=10, pady=3, cursor="hand2"
        )
        btn_scope_all.pack(side="left", padx=3)

        lbl_scope_status = tk.Label(header_bar, text="Viewing rolling 7-day operational cycle", font=("Consolas", 8, "italic"), fg=CYAN_DIM, bg=PANEL_BG)
        lbl_scope_status.pack(side="right", padx=5)

        style = ttk.Style()
        style.theme_use("default")
        style.configure("TNotebook", background=PANEL_BG, borderwidth=0)
        style.configure("TNotebook.Tab", background="#0c202d", foreground=TEXT_LIGHT, font=("Consolas", 10, "bold"), padding=[12, 5])
        style.map("TNotebook.Tab", background=[("selected", CYAN_DIM)], foreground=[("selected", "#ffffff")])

        notebook = ttk.Notebook(win)
        notebook.pack(fill="both", expand=True, padx=12, pady=(4, 5))

        # TAB 1: SLEEP LOGS
        tab_sleep = tk.Frame(notebook, bg=PANEL_BG)
        notebook.add(tab_sleep, text="SLEEP TELEMETRY")

        s_cols = ("id", "sleep_time", "wake_time", "duration", "disruptions", "notes")
        tree_sleep = ttk.Treeview(tab_sleep, columns=s_cols, show="headings", height=13)
        tree_sleep.heading("id", text="ID")
        tree_sleep.heading("sleep_time", text="Sleep Onset")
        tree_sleep.heading("wake_time", text="Wake Time")
        tree_sleep.heading("duration", text="Duration (h)")
        tree_sleep.heading("disruptions", text="Disruptions")
        tree_sleep.heading("notes", text="Diagnostic Notes")

        tree_sleep.column("id", width=50, anchor="center")
        tree_sleep.column("sleep_time", width=140, anchor="center")
        tree_sleep.column("wake_time", width=140, anchor="center")
        tree_sleep.column("duration", width=90, anchor="center")
        tree_sleep.column("disruptions", width=90, anchor="center")
        tree_sleep.column("notes", width=220, anchor="w")
        tree_sleep.pack(fill="both", expand=True, padx=8, pady=8)

        # TAB 2: INTAKE LOGS
        tab_intake = tk.Frame(notebook, bg=PANEL_BG)
        notebook.add(tab_intake, text="INTAKE TELEMETRY")

        i_cols = ("id", "type", "amount", "tag", "logged_at")
        tree_intake = ttk.Treeview(tab_intake, columns=i_cols, show="headings", height=13)
        tree_intake.heading("id", text="ID")
        tree_intake.heading("type", text="Type")
        tree_intake.heading("amount", text="Amount")
        tree_intake.heading("tag", text="Description")
        tree_intake.heading("logged_at", text="Timestamp (UTC)")

        tree_intake.column("id", width=50, anchor="center")
        tree_intake.column("type", width=90, anchor="center")
        tree_intake.column("amount", width=80, anchor="center")
        tree_intake.column("tag", width=160, anchor="w")
        tree_intake.column("logged_at", width=200, anchor="center")
        tree_intake.pack(fill="both", expand=True, padx=8, pady=8)

        # TAB 3: LIFETIME TELEMETRY OVERVIEW
        tab_lifetime = tk.Frame(notebook, bg=PANEL_BG)
        notebook.add(tab_lifetime, text="LIFETIME SUMMARY")

        lifetime_text = tk.Text(
            tab_lifetime, bg="#02070b", fg=TEXT_LIGHT, font=("Consolas", 10),
            bd=1, relief="solid", highlightthickness=1, highlightbackground=PANEL_BORDER,
            padx=16, pady=16
        )
        lifetime_text.pack(fill="both", expand=True, padx=8, pady=8)

        def populate_sleep():
            for row in tree_sleep.get_children():
                tree_sleep.delete(row)
            sleep_data = database.get_all_sleep_history(days=archive_scope["days"], order="desc")
            for r in sleep_data:
                tree_sleep.insert("", "end", values=(
                    r.get("id"),
                    r.get("sleep_time"),
                    r.get("wake_time"),
                    f"{r.get('duration_hours', 0.0):.1f}",
                    r.get("interruptions", 0),
                    r.get("quality_notes", "")
                ))

        def populate_intake():
            for row in tree_intake.get_children():
                tree_intake.delete(row)
            intake_data = database.get_all_intake_history(days=archive_scope["days"], order="desc")
            for r in intake_data:
                amt_str = f"{int(r.get('amount', 0))}ml" if r.get("type") == "hydration" else f"{r.get('amount', 1)} meal"
                tree_intake.insert("", "end", values=(
                    r.get("id"),
                    r.get("type", "").upper(),
                    amt_str,
                    r.get("tag", ""),
                    str(r.get("logged_at", ""))[:19].replace("T", " ")
                ))

        def populate_lifetime():
            import analytics_engine
            data = analytics_engine.get_lifetime_summary()
            report = (
                "==========================================================\n"
                "       ALTERRA CORP // LIFETIME TELEMETRY ARCHIVE         \n"
                "==========================================================\n\n"
                f"  * Telemetry Genesis:          {data['first_day']}\n"
                f"  * Total Active Days Monitored:{data['days_logged']} cycles\n\n"
                "  [ HYDRATION COMPLIANCE ]\n"
                f"  * Total Volume Assimilated:   {int(data['total_water_ml'])} ml\n"
                f"  * Mean Daily Hydration:       {data['avg_water_daily']} ml / day\n\n"
                "  [ NUTRITIONAL TELEMETRY ]\n"
                f"  * Total Meals Logged:         {data['total_meals']} rations\n"
                f"  * Mean Daily Sustenance:      {data['avg_meals_daily']} meals / day\n\n"
                "  [ CELLULAR REST & REPAIR ]\n"
                f"  * Total Rest Cycles Recorded: {data['total_sleep_cycles']}\n"
                f"  * Total Time Unconscious:     {data['total_sleep_hours']} hours\n"
                f"  * Lifetime Average Duration:  {data['avg_sleep_hours']} hours / cycle\n\n"
                "==========================================================\n"
                "Status: Historical archives synchronized to terminal baseline.\n"
            )
            lifetime_text.delete("1.0", "end")
            lifetime_text.insert("end", report)

        def switch_scope(scope_days):
            archive_scope["days"] = scope_days
            if scope_days == 7:
                btn_scope_7d.config(bg="#0e2838", fg=CYAN_BRIGHT)
                btn_scope_all.config(bg="#0c202d", fg=TEXT_MUTED)
                lbl_scope_status.config(text="Viewing rolling 7-day operational cycle")
            else:
                btn_scope_7d.config(bg="#0c202d", fg=TEXT_MUTED)
                btn_scope_all.config(bg="#0e2838", fg=CYAN_BRIGHT)
                lbl_scope_status.config(text="Viewing all historical entries since day 1")
            populate_sleep()
            populate_intake()

        btn_scope_7d.config(command=lambda: switch_scope(7))
        btn_scope_all.config(command=lambda: switch_scope(None))

        populate_sleep()
        populate_intake()
        populate_lifetime()

        bar_actions = tk.Frame(win, bg=PANEL_BG, pady=8, padx=12)
        bar_actions.pack(fill="x")

        def delete_selected():
            cur_tab = notebook.index(notebook.select())
            if cur_tab == 2:
                messagebox.showinfo("Telemetry Summary", "The Lifetime Summary is an aggregate view. Delete entries from Sleep or Intake tabs.")
                return

            target_tree = tree_sleep if cur_tab == 0 else tree_intake
            target_table = "sleep_logs" if cur_tab == 0 else "intake_logs"

            selected = target_tree.selection()
            if not selected:
                messagebox.showwarning("Selection Required", "Select a telemetry record from the table to delete.")
                return

            rec_id = target_tree.item(selected[0])["values"][0]
            confirm = messagebox.askyesno("Alterra Protocol Override", f"Confirm permanent deletion of record ID #{rec_id} from {target_table}?")
            if confirm:
                if database.delete_record_by_id(target_table, rec_id):
                    self.log_terminal(f"ARCHIVE OVERRIDE: Expunged record ID #{rec_id} from {target_table}.")
                    populate_sleep()
                    populate_intake()
                    populate_lifetime()
                    self.refresh_display()
                else:
                    messagebox.showerror("Deletion Error", "Could not remove record from cloud/local storage.")

        btn_del = tk.Button(
            bar_actions, text="EXPUNGE SELECTED RECORD", font=("Consolas", 9, "bold"),
            bg="#2a0d12", fg="#ff4455", activebackground="#45121c", activeforeground="#ffffff",
            bd=1, relief="ridge", padx=10, pady=5, cursor="hand2", command=delete_selected
        )
        btn_del.pack(side="left")

        btn_refresh = tk.Button(
            bar_actions, text="REFRESH DATABASE", font=("Consolas", 9, "bold"),
            bg="#0e2838", fg=CYAN_BRIGHT, activebackground=CYAN_DIM, activeforeground="#ffffff",
            bd=1, relief="ridge", padx=10, pady=5, cursor="hand2",
            command=lambda: (populate_sleep(), populate_intake(), populate_lifetime())
        )
        btn_refresh.pack(side="right")

    def action_settings_dialog(self):
        cfg = config_manager.load_config() or config_manager.DEFAULT_CONFIG

        win = tk.Toplevel(self.root)
        win.title("ALTERRA CORP // BIO-PARAMETERS & SYSTEM CONFIGURATION")
        win.geometry("560x640")
        win.configure(bg=PANEL_BG)
        win.resizable(False, False)

        header = tk.Frame(win, bg=PANEL_BG, padx=16, pady=10)
        header.pack(fill="x")
        tk.Label(header, text="ALTERRA PROTOCOL CONFIGURATION CONSOLE", font=("Consolas", 11, "bold"), fg=CYAN_BRIGHT, bg=PANEL_BG).pack(anchor="w")
        tk.Label(header, text="Adjust physiological targets, sleep exclusion windows, and persistence.", font=("Consolas", 8), fg=TEXT_MUTED, bg=PANEL_BG).pack(anchor="w")

        body = tk.Frame(win, bg=PANEL_BG, padx=16, pady=6)
        body.pack(fill="both", expand=True)

        row = 0
        def add_section(text):
            nonlocal row
            lbl = tk.Label(body, text=f"--- {text} ---", font=("Consolas", 9, "bold"), fg=CYAN_DIM, bg=PANEL_BG)
            lbl.grid(row=row, column=0, columnspan=2, sticky="w", pady=(10, 4))
            row += 1

        # 1. Biological Targets
        add_section("BIOLOGICAL TARGETS & INTERVALS")

        tk.Label(body, text="Hydration Target (ml/day):", font=("Consolas", 9), fg=TEXT_LIGHT, bg=PANEL_BG).grid(row=row, column=0, sticky="w", pady=3)
        ent_water = tk.Entry(body, font=("Consolas", 9), bg="#02070b", fg=CYAN_BRIGHT, insertbackground=CYAN_BRIGHT, width=12)
        ent_water.insert(0, str(cfg.get("target_water_ml", 2500)))
        ent_water.grid(row=row, column=1, sticky="w", pady=3)
        row += 1

        tk.Label(body, text="Hydration Interval (minutes):", font=("Consolas", 9), fg=TEXT_LIGHT, bg=PANEL_BG).grid(row=row, column=0, sticky="w", pady=3)
        ent_h_int = tk.Entry(body, font=("Consolas", 9), bg="#02070b", fg=CYAN_BRIGHT, insertbackground=CYAN_BRIGHT, width=12)
        ent_h_int.insert(0, str(cfg.get("hydration_interval_min", 75)))
        ent_h_int.grid(row=row, column=1, sticky="w", pady=3)
        row += 1

        tk.Label(body, text="Daily Meals Target (rations):", font=("Consolas", 9), fg=TEXT_LIGHT, bg=PANEL_BG).grid(row=row, column=0, sticky="w", pady=3)
        ent_meals = tk.Entry(body, font=("Consolas", 9), bg="#02070b", fg=CYAN_BRIGHT, insertbackground=CYAN_BRIGHT, width=12)
        ent_meals.insert(0, str(cfg.get("target_meals", 4)))
        ent_meals.grid(row=row, column=1, sticky="w", pady=3)
        row += 1

        tk.Label(body, text="Meal Interval (minutes):", font=("Consolas", 9), fg=TEXT_LIGHT, bg=PANEL_BG).grid(row=row, column=0, sticky="w", pady=3)
        ent_m_int = tk.Entry(body, font=("Consolas", 9), bg="#02070b", fg=CYAN_BRIGHT, insertbackground=CYAN_BRIGHT, width=12)
        ent_m_int.insert(0, str(cfg.get("meal_interval_min", 210)))
        ent_m_int.grid(row=row, column=1, sticky="w", pady=3)
        row += 1

        # 2. Standby / Sleep Silencing Window
        add_section("STANDBY / SLEEP SILENCING WINDOW (24H HH:MM)")

        f_sleep_start = tk.Frame(body, bg=PANEL_BG)
        tk.Label(body, text="Sleep Inactive Start:", font=("Consolas", 9), fg=TEXT_LIGHT, bg=PANEL_BG).grid(row=row, column=0, sticky="w", pady=3)
        ent_ss_h = tk.Entry(f_sleep_start, font=("Consolas", 9), bg="#02070b", fg=CYAN_BRIGHT, width=4)
        ent_ss_h.insert(0, f"{cfg.get('sleep_start_hour', 23):02d}")
        ent_ss_h.pack(side="left")
        tk.Label(f_sleep_start, text=":", fg=CYAN_BRIGHT, bg=PANEL_BG).pack(side="left")
        ent_ss_m = tk.Entry(f_sleep_start, font=("Consolas", 9), bg="#02070b", fg=CYAN_BRIGHT, width=4)
        ent_ss_m.insert(0, f"{cfg.get('sleep_start_minute', 0):02d}")
        ent_ss_m.pack(side="left")
        f_sleep_start.grid(row=row, column=1, sticky="w", pady=3)
        row += 1

        f_sleep_end = tk.Frame(body, bg=PANEL_BG)
        tk.Label(body, text="Wake Active Resume:", font=("Consolas", 9), fg=TEXT_LIGHT, bg=PANEL_BG).grid(row=row, column=0, sticky="w", pady=3)
        ent_se_h = tk.Entry(f_sleep_end, font=("Consolas", 9), bg="#02070b", fg=CYAN_BRIGHT, width=4)
        ent_se_h.insert(0, f"{cfg.get('sleep_end_hour', 7):02d}")
        ent_se_h.pack(side="left")
        tk.Label(f_sleep_end, text=":", fg=CYAN_BRIGHT, bg=PANEL_BG).pack(side="left")
        ent_se_m = tk.Entry(f_sleep_end, font=("Consolas", 9), bg="#02070b", fg=CYAN_BRIGHT, width=4)
        ent_se_m.insert(0, f"{cfg.get('sleep_end_minute', 0):02d}")
        ent_se_m.pack(side="left")
        f_sleep_end.grid(row=row, column=1, sticky="w", pady=3)
        row += 1

        # 3. Environment & Storage Architecture
        add_section("ENVIRONMENT & PERSISTENCE ENGINE")

        tk.Label(body, text="System IANA Timezone:", font=("Consolas", 9), fg=TEXT_LIGHT, bg=PANEL_BG).grid(row=row, column=0, sticky="w", pady=3)
        ent_tz = tk.Entry(body, font=("Consolas", 9), bg="#02070b", fg=CYAN_BRIGHT, insertbackground=CYAN_BRIGHT, width=24)
        ent_tz.insert(0, str(cfg.get("timezone", "UTC")))
        ent_tz.grid(row=row, column=1, sticky="w", pady=3)
        row += 1

        tk.Label(body, text="Storage Architecture:", font=("Consolas", 9), fg=TEXT_LIGHT, bg=PANEL_BG).grid(row=row, column=0, sticky="w", pady=3)
        combo_storage = ttk.Combobox(body, values=["local", "supabase"], width=12, state="readonly")
        combo_storage.set(cfg.get("storage_mode", "local"))
        combo_storage.grid(row=row, column=1, sticky="w", pady=3)
        row += 1

        tk.Label(body, text="Supabase URL:", font=("Consolas", 9), fg=TEXT_LIGHT, bg=PANEL_BG).grid(row=row, column=0, sticky="w", pady=3)
        ent_url = tk.Entry(body, font=("Consolas", 9), bg="#02070b", fg=CYAN_BRIGHT, insertbackground=CYAN_BRIGHT, width=28)
        ent_url.insert(0, str(cfg.get("supabase_url", "")))
        ent_url.grid(row=row, column=1, sticky="w", pady=3)
        row += 1

        tk.Label(body, text="Supabase Anon/Service Key:", font=("Consolas", 9), fg=TEXT_LIGHT, bg=PANEL_BG).grid(row=row, column=0, sticky="w", pady=3)
        ent_key = tk.Entry(body, font=("Consolas", 9), bg="#02070b", fg=CYAN_BRIGHT, insertbackground=CYAN_BRIGHT, width=28, show="*")
        ent_key.insert(0, str(cfg.get("supabase_key", "")))
        ent_key.grid(row=row, column=1, sticky="w", pady=3)
        row += 1

        def commit_settings():
            try:
                new_cfg = {
                    "timezone": ent_tz.get().strip() or "UTC",
                    "storage_mode": combo_storage.get().strip(),
                    "supabase_url": ent_url.get().strip(),
                    "supabase_key": ent_key.get().strip(),
                    "target_water_ml": int(ent_water.get().strip()),
                    "hydration_interval_min": int(ent_h_int.get().strip()),
                    "target_meals": int(ent_meals.get().strip()),
                    "meal_interval_min": int(ent_m_int.get().strip()),
                    "sleep_start_hour": int(ent_ss_h.get().strip()),
                    "sleep_start_minute": int(ent_ss_m.get().strip()),
                    "sleep_end_hour": int(ent_se_h.get().strip()),
                    "sleep_end_minute": int(ent_se_m.get().strip())
                }

                config_manager.save_config(new_cfg)
                self.hud.reload_config()
                self.refresh_display()
                self.log_terminal("CONFIG OVERRIDE: Bio-parameters and system targets updated.")
                messagebox.showinfo("Alterra PDA", "Biometric targets and system configuration saved successfully.")
                win.destroy()
            except ValueError as ve:
                messagebox.showerror("Format Error", f"Numeric value invalid: {ve}")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to commit configuration: {e}")

        btn_commit = tk.Button(
            win, text="APPLY ALTERRA PROTOCOLS", font=("Consolas", 10, "bold"),
            bg="#0e2838", fg=CYAN_BRIGHT, activebackground=CYAN_DIM, activeforeground="#ffffff",
            bd=1, relief="ridge", pady=6, cursor="hand2", command=commit_settings
        )
        btn_commit.pack(fill="x", padx=16, pady=12)


if __name__ == "__main__":
    root = tk.Tk()
    root.withdraw()

    cfg = config_manager.load_config()
    if cfg is None:
        cfg = config_manager.run_first_launch_wizard(root)

    app = SubnauticaPDAGUI(root)

    if "--autostart" not in sys.argv:
        root.deiconify()

    root.mainloop()