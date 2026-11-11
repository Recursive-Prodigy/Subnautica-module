import os
import sys
import subprocess
import threading
from datetime import datetime, time, timezone, timedelta
import tkinter as tk
from tkinter import ttk, messagebox
import sfx_manager as sfx

# System Tray & UI Graphics
import pystray
from PIL import Image, ImageDraw

# Project Backend, Config & State
import database
db = database
import config_manager
import time_sync
from time_sync import time_manager
from hud_state import HUDState

# Voice Engine & Voice Banks
import dialogues
from voice_engine import speak

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

# --- GLOBAL TIMEZONE CHOICES WITH GMT OFFSETS ---
TIMEZONE_MAP = {
    "Asia/Kolkata (GMT+05:30)": "Asia/Kolkata",
    "UTC (GMT+00:00)": "UTC",
    "Europe/London (GMT+00:00)": "Europe/London",
    "Europe/Berlin (GMT+01:00)": "Europe/Berlin",
    "Europe/Paris (GMT+01:00)": "Europe/Paris",
    "Europe/Zurich (GMT+01:00)": "Europe/Zurich",
    "Asia/Dubai (GMT+04:00)": "Asia/Dubai",
    "Asia/Singapore (GMT+08:00)": "Asia/Singapore",
    "Asia/Tokyo (GMT+09:00)": "Asia/Tokyo",
    "Australia/Sydney (GMT+10:00)": "Australia/Sydney",
    "America/New_York (GMT-05:00)": "America/New_York",
    "America/Chicago (GMT-06:00)": "America/Chicago",
    "America/Denver (GMT-07:00)": "America/Denver",
    "America/Los_Angeles (GMT-08:00)": "America/Los_Angeles",
}


def format_date_dmy(date_val, include_time: bool = True) -> str:
    """Transforms database ISO timestamps into clean DD/MM/YYYY presentation strings."""
    if not date_val:
        return "--"
    clean_str = str(date_val).replace("T", " ").strip()

    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M:%S", "%Y/%m/%d %H:%M"):
        try:
            dt = datetime.strptime(clean_str[:19], fmt)
            return dt.strftime("%d/%m/%Y %H:%M") if include_time else dt.strftime("%d/%m/%Y")
        except ValueError:
            pass

    for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
        try:
            dt = datetime.strptime(clean_str[:10], fmt)
            return dt.strftime("%d/%m/%Y")
        except ValueError:
            pass

    return clean_str


def create_tray_icon():
    """Generates a dynamic 64x64 Alterra cyan hexagon icon in memory."""
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    points = [(32, 4), (60, 20), (60, 44), (32, 60), (4, 44), (4, 20)]
    draw.polygon(points, fill=(8, 22, 32, 255), outline=(0, 240, 255, 255), width=3)
    draw.ellipse((26, 26, 38, 38), fill=(0, 240, 255, 255))
    return img


class CircularHUDGauge(tk.Canvas):
    def __init__(self, parent, size=120, ring_width=6, title="GAUGE", base_color=CYAN_BRIGHT, **kwargs):
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

        self.create_oval(x0, y0, x1, y1, fill=fill_glow, outline="#0d2838", width=1)
        self.create_arc(
            x0, y0, x1, y1,
            start=90, extent=-359.9,
            style="arc", outline="#0a202d", width=self.ring_width
        )

        extent = -359.9 * self.fraction
        if abs(extent) > 1.0:
            self.create_arc(
                x0, y0, x1, y1,
                start=90, extent=extent,
                style="arc", outline=stroke_color, width=self.ring_width
            )

        self.create_text(
            self.cx, self.cy - 12,
            text=self.title, fill="#527e8a", font=("Consolas", 8, "bold")
        )
        self.create_text(
            self.cx, self.cy + 4,
            text=self.center_text, fill=stroke_color, font=("Consolas", 9, "bold")
        )
        self.create_text(
            self.cx, self.cy + 20,
            text=self.sub_text, fill="#7aa0ab", font=("Consolas", 7)
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
        self.root.geometry("860x880")
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

        # Play Alterra boot chime
        sfx.play_sfx("bootup")

        # Initial Boot Audio
        threading.Thread(target=speak, args=(dialogues.get_dialogue("boot"), "pda"), daemon=True).start()

        self.refresh_display()
        self.poll_timers()

    def _build_header(self):
        header_frame = tk.Frame(self.root, bg=BG_DARK, pady=8, padx=20)
        header_frame.pack(fill="x")

        title_box = tk.Frame(header_frame, bg=BG_DARK)
        title_box.pack(side="left")

        tk.Label(title_box, text="ALTERRA CORPORATION", font=("Consolas", 10, "bold"), fg=CYAN_DIM, bg=BG_DARK).pack(anchor="w")
        tk.Label(title_box, text="PDA REC-01 // BIOMETRIC HUD", font=("Consolas", 15, "bold"), fg=CYAN_BRIGHT, bg=BG_DARK).pack(anchor="w")

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
        divider.pack(fill="x", padx=15, pady=(8, 4))

    def run_readiness_diagnostic(self):
        """Runs the 7-day rolling biometric diagnostic and voice advisory."""
        import readiness_engine
        report = readiness_engine.calculate_biometric_readiness(scope_days=7)

        for line in report["terminal_report"].split("\n"):
            self.log_terminal(line)

        # Trigger Alterra voice advisory asynchronously
        threading.Thread(target=speak, args=(report["voice_line"], "pda"), daemon=True).start()

    def _build_vitals_panel(self):
        panel_container = tk.Frame(self.root, bg=BG_DARK, padx=20)
        panel_container.pack(fill="x", pady=2)

        # --- VIEW 1: STAGGERED INVERTED PYRAMID GAUGES ---
        card_circles = tk.Frame(
            panel_container, bg=PANEL_BG, bd=1, relief="solid",
            highlightbackground=PANEL_BORDER, highlightthickness=1, padx=14, pady=8
        )
        card_circles.pack(fill="x", pady=3)

        c_header = tk.Frame(card_circles, bg=PANEL_BG)
        c_header.pack(fill="x", pady=(0, 4))
        tk.Label(
            c_header, text="BIOMETRIC COMPLIANCE & INTERVAL TELEMETRY",
            font=("Consolas", 9, "bold"), fg=CYAN_DIM, bg=PANEL_BG
        ).pack(side="left")
        self.lbl_vitals_summary = tk.Label(
            c_header, text="ALL PARAMETERS NOMINAL",
            font=("Consolas", 9, "bold"), fg=SUCCESS_GREEN, bg=PANEL_BG
        )
        self.lbl_vitals_summary.pack(side="right")

        # 5-Column Symmetrical Grid for Staggered Valleys
        gauges_grid = tk.Frame(card_circles, bg=PANEL_BG)
        gauges_grid.pack(fill="x", expand=True, pady=2)

        for col_idx in range(5):
            gauges_grid.columnconfigure(col_idx, weight=1)

        # --- TOP TIER: PRIMARY METABOLIC VITALS (Cols 0, 2, 4) ---
        self.gauge_water = CircularHUDGauge(gauges_grid, size=116, ring_width=6, title="WATER", base_color=CYAN_BRIGHT)
        self.gauge_water.grid(row=0, column=0, pady=2)

        self.gauge_food = CircularHUDGauge(gauges_grid, size=116, ring_width=6, title="FOOD", base_color="#28d7a0")
        self.gauge_food.grid(row=0, column=2, pady=2)

        self.gauge_sleep = CircularHUDGauge(gauges_grid, size=116, ring_width=6, title="REST", base_color="#b070ff")
        self.gauge_sleep.grid(row=0, column=4, pady=2)

        # --- SUBTLE HORIZONTAL SEPARATOR RULE ---
        sep_frame = tk.Frame(gauges_grid, bg=PANEL_BG)
        sep_frame.grid(row=1, column=0, columnspan=5, sticky="ew", pady=(6, 4))

        tk.Frame(sep_frame, height=1, bg="#0e2838").pack(fill="x", padx=40)

        # --- BOTTOM TIER: SECONDARY DECONTAMINATION (Cols 1, 3 - Inverted Pyramid Valleys) ---
        self.gauge_brush = CircularHUDGauge(gauges_grid, size=110, ring_width=6, title="BRUSH", base_color="#00c8ff")
        self.gauge_brush.grid(row=2, column=1, pady=2)

        self.gauge_shower = CircularHUDGauge(gauges_grid, size=110, ring_width=6, title="SHOWER", base_color="#00e5a3")
        self.gauge_shower.grid(row=2, column=3, pady=2)

        # --- VIEW 2: LINEAR PROGRESS BARS ---
        self.card_water = tk.Frame(panel_container, bg=PANEL_BG, bd=1, relief="solid", highlightbackground=PANEL_BORDER, highlightthickness=1, padx=12, pady=5)
        self.card_water.pack(fill="x", pady=2)
        w_header = tk.Frame(self.card_water, bg=PANEL_BG)
        w_header.pack(fill="x")
        tk.Label(w_header, text="HYDRATION INTEGRITY", font=("Consolas", 9, "bold"), fg=CYAN_BRIGHT, bg=PANEL_BG).pack(side="left")
        self.lbl_water_status = tk.Label(w_header, text="OPTIMAL", font=("Consolas", 8, "bold"), fg=SUCCESS_GREEN, bg=PANEL_BG)
        self.lbl_water_status.pack(side="right")
        self.water_bar = AlterraProgressBar(self.card_water, width=780, height=9)
        self.water_bar.pack(pady=2)
        w_stats = tk.Frame(self.card_water, bg=PANEL_BG)
        w_stats.pack(fill="x")
        self.lbl_water_vals = tk.Label(w_stats, text="0 / 2500 ml (0%)", font=("Consolas", 8), fg=TEXT_LIGHT, bg=PANEL_BG)
        self.lbl_water_vals.pack(side="left")
        self.lbl_water_timer = tk.Label(w_stats, text="Last: Never | Interval: 75m", font=("Consolas", 8), fg=TEXT_MUTED, bg=PANEL_BG)
        self.lbl_water_timer.pack(side="right")

        self.card_food = tk.Frame(panel_container, bg=PANEL_BG, bd=1, relief="solid", highlightbackground=PANEL_BORDER, highlightthickness=1, padx=12, pady=5)
        self.card_food.pack(fill="x", pady=2)
        f_header = tk.Frame(self.card_food, bg=PANEL_BG)
        f_header.pack(fill="x")
        tk.Label(f_header, text="SUSTENANCE & METABOLISM", font=("Consolas", 9, "bold"), fg=CYAN_BRIGHT, bg=PANEL_BG).pack(side="left")
        self.lbl_food_status = tk.Label(f_header, text="OPTIMAL", font=("Consolas", 8, "bold"), fg=SUCCESS_GREEN, bg=PANEL_BG)
        self.lbl_food_status.pack(side="right")
        self.food_bar = AlterraProgressBar(self.card_food, width=780, height=9)
        self.food_bar.pack(pady=2)
        f_stats = tk.Frame(self.card_food, bg=PANEL_BG)
        f_stats.pack(fill="x")
        self.lbl_food_vals = tk.Label(f_stats, text="0 / 4 Meals (0%)", font=("Consolas", 8), fg=TEXT_LIGHT, bg=PANEL_BG)
        self.lbl_food_vals.pack(side="left")
        self.lbl_food_timer = tk.Label(f_stats, text="Last: Never | Interval: 210m", font=("Consolas", 8), fg=TEXT_MUTED, bg=PANEL_BG)
        self.lbl_food_timer.pack(side="right")

    def action_log_exercise_dialog(self):
        win = tk.Toplevel(self.root)
        win.title("LOG PHYSICAL EXERTION")
        win.geometry("380x260")
        win.configure(bg=PANEL_BG)
        win.resizable(False, False)

        tk.Label(win, text="PHYSICAL LOAD TELEMETRY", font=("Consolas", 11, "bold"), fg=CYAN_BRIGHT, bg=PANEL_BG).pack(pady=10)

        f_body = tk.Frame(win, bg=PANEL_BG, padx=20)
        f_body.pack(fill="x", pady=5)

        tk.Label(f_body, text="Exertion Duration (Hours):", font=("Consolas", 9), fg=TEXT_LIGHT, bg=PANEL_BG).grid(row=0, column=0, sticky="w", pady=8)
        ent_dur = tk.Entry(f_body, font=("Consolas", 9), bg="#02070b", fg=CYAN_BRIGHT, insertbackground=CYAN_BRIGHT, insertwidth=2, width=8)
        ent_dur.insert(0, "1.0")
        ent_dur.grid(row=0, column=1, sticky="w", pady=8, padx=5)

        tk.Label(f_body, text="Exertion Intensity:", font=("Consolas", 9), fg=TEXT_LIGHT, bg=PANEL_BG).grid(row=1, column=0, sticky="w", pady=8)
        combo_int = ttk.Combobox(f_body, values=["Moderate (Gym/Cardio)", "High (Heavy Resistance)", "Extreme"], width=18, state="readonly")
        combo_int.set("Moderate (Gym/Cardio)")
        combo_int.grid(row=1, column=1, sticky="w", pady=8, padx=5)

        def save_exercise():
            try:
                hrs = float(ent_dur.get().strip())
                if hrs <= 0.0:
                    raise ValueError("Duration must be greater than zero.")
                if hrs > 16.0:
                    raise ValueError("Maximum physical exertion threshold is capped at 16.0 hours.")

                db.log_exercise(hrs, combo_int.get())
                self.log_terminal(f"TELEMETRY LOGGED: Physical exertion ({hrs:.1f}h) committed to bio-reserve.")
                self.refresh_display()
                line = "Physical exertion logged. Cellular glycogen and stamina budget updated."
                threading.Thread(target=speak, args=(line, "pda"), daemon=True).start()
                win.destroy()
            except ValueError as ve:
                messagebox.showerror("Exertion Limit", str(ve))

        btn = tk.Button(win, text="RECORD PHYSICAL LOAD", font=("Consolas", 9, "bold"), bg="#0e2838", fg=CYAN_BRIGHT, bd=1, relief="ridge", command=save_exercise, cursor="hand2")
        btn.pack(pady=15, fill="x", padx=25)

    def action_log_snack(self, tag: str = "Nutrient Snack"):
        """Logs a light ration with canonical snack audio and Alterra voice line."""
        if hasattr(database, "log_snack"):
            database.log_snack(tag)
        else:
            database.log_intake("snack", 0.5, tag)
        sfx.play_sfx("eating_snack_logged")

        self.log_terminal(f"VITAL SIGNS: Micro-ration [{tag}] assimilated (+0.5 ration).")
        self.refresh_display()

        try:
            line = dialogues.get_dialogue("snack")
        except Exception:
            line = "Micro-ration assimilated. Metabolic baseline refreshed."

        threading.Thread(target=speak, args=(line, "pda"), daemon=True).start()

    def action_log_nap_dialog(self):
        """
        Interactive recovery modal supporting flexible duration inputs
        (e.g., '20', '45m', '1.5', '1.5h', '1h 30m', '2 hrs').
        """
        import re

        win = tk.Toplevel(self.root)
        win.title("LOG RECOVERY SLEEP")
        win.geometry("400x260")
        win.configure(bg=PANEL_BG)
        win.resizable(False, False)
        win.transient(self.root)
        win.grab_set()

        def parse_duration_to_minutes(raw_str: str) -> int:
            s = str(raw_str).strip().lower()
            if not s:
                raise ValueError("Duration cannot be empty.")

            # 1. Composite formats: "1h 30m", "1hr 20min", "2 hours 15m"
            h_m = re.match(r"^(\d+(?:\.\d+)?)\s*(?:h|hr|hrs|hours?)\s*(?:and\s*)?(\d+)?\s*(?:m|min|mins|minutes?)?$", s)
            if h_m:
                h = float(h_m.group(1))
                m = float(h_m.group(2) or 0)
                return int(round(h * 60 + m))

            # 2. Minute strings: "45m", "90mins"
            m_only = re.match(r"^(\d+)\s*(?:m|min|mins|minutes?)$", s)
            if m_only:
                return int(m_only.group(1))

            # 3. Explicit hour strings: "1.5h", "2h"
            if s.endswith("h"):
                return int(round(float(s[:-1].strip()) * 60))

            # 4. Numeric input: if <= 4.0 or contains a decimal point, interpret as hours
            val = float(s)
            if "." in s or val <= 4.0:
                return int(round(val * 60))

            # Otherwise interpret integer > 4 as minutes (e.g. 15, 20, 30, 45, 90)
            return int(round(val))

        tk.Label(
            win, text="BIOLOGICAL RECOVERY LOG",
            font=("Consolas", 11, "bold"), fg=CYAN_BRIGHT, bg=PANEL_BG
        ).pack(pady=(12, 6))

        f_body = tk.Frame(win, bg=PANEL_BG, padx=20)
        f_body.pack(fill="x", pady=5)

        tk.Label(
            f_body, text="Duration (m, h, or 1h 20m):",
            font=("Consolas", 9), fg=TEXT_LIGHT, bg=PANEL_BG
        ).grid(row=0, column=0, sticky="w", pady=6)

        ent_nap = tk.Entry(
            f_body, font=("Consolas", 9), bg="#02070b",
            fg=CYAN_BRIGHT, insertbackground=CYAN_BRIGHT, insertwidth=2, width=12
        )
        ent_nap.insert(0, "30")
        ent_nap.grid(row=0, column=1, sticky="w", pady=6, padx=6)

        lbl_preview = tk.Label(
            f_body, text="Parsed: 30 mins [POWER NAP]",
            font=("Consolas", 8), fg="#00e5a3", bg=PANEL_BG
        )
        lbl_preview.grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, 6))

        tk.Label(
            f_body, text="Recovery Notes:",
            font=("Consolas", 9), fg=TEXT_LIGHT, bg=PANEL_BG
        ).grid(row=2, column=0, sticky="w", pady=6)

        ent_notes = tk.Entry(
            f_body, font=("Consolas", 9), bg="#02070b",
            fg=CYAN_BRIGHT, insertbackground=CYAN_BRIGHT, insertwidth=2, width=16
        )
        ent_notes.insert(0, "Daytime Recovery")
        ent_notes.grid(row=2, column=1, sticky="w", pady=6, padx=6)

        def update_preview(*args):
            raw = ent_nap.get().strip()
            try:
                mins = parse_duration_to_minutes(raw)
                hrs = mins / 60.0
                if mins < 15:
                    tag = "MICRO NAP (Negligible recovery)"
                    color = "#888888"
                elif mins <= 45:
                    tag = "POWER NAP (Process C Reset)"
                    color = "#00e5a3"
                elif mins <= 90:
                    tag = "FULL CYCLE (Ultradian Refresh)"
                    color = "#00c8ff"
                else:
                    tag = f"EXTENDED SLEEP ({hrs:.1f}h Debt Offset)"
                    color = "#ffb000"
                lbl_preview.configure(text=f"Parsed: {mins}m ({hrs:.1f}h) [{tag}]", fg=color)
            except Exception:
                lbl_preview.configure(text="Format error (e.g. 20, 45m, 1.5h, 1h 20m)", fg="#ff3366")

        ent_nap.bind("<KeyRelease>", update_preview)

        def save_nap():
            try:
                mins = parse_duration_to_minutes(ent_nap.get().strip())
                if mins < 5 or mins > 600:
                    raise ValueError("Recovery duration must be between 5 minutes and 10 hours.")

                notes = ent_notes.get().strip() or "Daytime Recovery"
                success = database.log_nap(duration_minutes=mins, notes=notes)

                if not success:
                    raise RuntimeError("Failed to commit recovery cycle to database.")

                sfx.play_sfx("rest_logged")

                hrs = mins / 60.0
                if mins <= 45:
                    term_msg = f"POWER NAP: {mins}m logged. Process C slump cleared."
                    voice_msg = "Rest recovery cycle recorded. Homeostatic sleep pressure partially cleared."
                elif mins <= 90:
                    term_msg = f"ULTRADIAN CYCLE: {mins}m logged. Full sleep architecture refreshed."
                    voice_msg = "Ultradian recovery completed. Rest parameters restored to nominal operating band."
                else:
                    term_msg = f"EXTENDED SLEEP: {hrs:.1f}h logged. Sleep debt neutralized; nocturnal sleep delay expected."
                    voice_msg = "Warning. Prolonged daytime sleep recorded. Sleep debt neutralized, but circadian phase delay is projected."

                self.log_terminal(term_msg)
                self.refresh_display()
                win.destroy()
                threading.Thread(target=speak, args=(voice_msg, "pda"), daemon=True).start()

            except ValueError as ve:
                messagebox.showerror("Nap Input Error", str(ve))
            except Exception as e:
                messagebox.showerror("Database Error", str(e))

        btn = tk.Button(
            win, text="COMMIT RECOVERY",
            font=("Consolas", 9, "bold"), bg="#0e2838", fg=CYAN_BRIGHT,
            activebackground=CYAN_DIM, activeforeground="#ffffff",
            bd=1, relief="ridge", command=save_nap, cursor="hand2"
        )
        btn.pack(pady=12, fill="x", padx=25)

    def _build_action_deck(self):
        deck_frame = tk.Frame(self.root, bg=BG_DARK, padx=16, pady=3)
        deck_frame.pack(fill="x")

        # -------------------------------------------------------------------
        # ROW 1: METABOLISM & CELLULAR RECOVERY PROTOCOLS
        # -------------------------------------------------------------------
        row1 = tk.Frame(deck_frame, bg=BG_DARK)
        row1.pack(fill="x", pady=2)

        # 1. Hydration (+250ml)
        btn_water = tk.Button(
            row1, text="💧 +250ml WATER", font=("Consolas", 8, "bold"),
            bg="#0e2838", fg=CYAN_BRIGHT, activebackground=CYAN_DIM, activeforeground="#ffffff",
            bd=1, relief="ridge", padx=4, pady=6, cursor="hand2", command=self.action_log_water
        )
        btn_water.pack(side="left", expand=True, fill="x", padx=2)

        # 2. Nutrient Snack (+0.5 Ration)
        btn_snack = tk.Button(
            row1, text="🥪 + SNACK", font=("Consolas", 8, "bold"),
            bg="#082230", fg="#FFAD14", activebackground=CYAN_DIM, activeforeground="#ffffff",
            bd=1, relief="ridge", padx=4, pady=6, cursor="hand2", command=self.action_log_snack
        )
        btn_snack.pack(side="left", expand=True, fill="x", padx=2)

        # 3. Full Meal Ration
        btn_meal = tk.Button(
            row1, text="🍲 + LOG MEAL", font=("Consolas", 8, "bold"),
            bg="#0e2838", fg=CYAN_BRIGHT, activebackground=CYAN_DIM, activeforeground="#ffffff",
            bd=1, relief="ridge", padx=4, pady=6, cursor="hand2", command=self.action_log_meal
        )
        btn_meal.pack(side="left", expand=True, fill="x", padx=2)

        # 4. Primary Sleep Cycle
        btn_sleep = tk.Button(
            row1, text="🌙 + SLEEP CYCLE", font=("Consolas", 8, "bold"),
            bg="#0e2838", fg=CYAN_BRIGHT, activebackground=CYAN_DIM, activeforeground="#ffffff",
            bd=1, relief="ridge", padx=4, pady=6, cursor="hand2", command=self.action_log_sleep_dialog
        )
        btn_sleep.pack(side="left", expand=True, fill="x", padx=2)

        # 5. Daytime Power Nap
        btn_nap = tk.Button(
            row1, text="💤 + RECOVERY NAP", font=("Consolas", 8, "bold"),
            bg="#0a202e", fg="#33b3ff", activebackground=CYAN_DIM, activeforeground="#ffffff",
            bd=1, relief="ridge", padx=4, pady=6, cursor="hand2", command=self.action_log_nap_dialog
        )
        btn_nap.pack(side="left", expand=True, fill="x", padx=2)

        # -------------------------------------------------------------------
        # ROW 2: HYGIENE, PHYSICAL LOAD & SYSTEM TELEMETRY
        # -------------------------------------------------------------------
        row2 = tk.Frame(deck_frame, bg=BG_DARK)
        row2.pack(fill="x", pady=2)

        # 1. Brushing Protocol
        btn_brush = tk.Button(
            row2, text="🪥 BRUSH", font=("Consolas", 8, "bold"),
            bg="#0e2838", fg=CYAN_BRIGHT, activebackground=CYAN_DIM, activeforeground="#ffffff",
            bd=1, relief="ridge", padx=4, pady=6, cursor="hand2",
            command=getattr(self, "action_log_brush", getattr(self, "action_log_brushing", None))
        )
        btn_brush.pack(side="left", expand=True, fill="x", padx=2)

        # 2. Decontamination Shower
        btn_shower = tk.Button(
            row2, text="🚿 SHOWER", font=("Consolas", 8, "bold"),
            bg="#0e2838", fg=CYAN_BRIGHT, activebackground=CYAN_DIM, activeforeground="#ffffff",
            bd=1, relief="ridge", padx=4, pady=6, cursor="hand2", command=self.action_log_shower
        )
        btn_shower.pack(side="left", expand=True, fill="x", padx=2)

        # 3. Biometric Readiness Diagnostic
        btn_readiness = tk.Button(
            row2, text="🧠 READINESS", font=("Consolas", 8, "bold"),
            bg="#0a192f", fg="#00ff00", activebackground=CYAN_DIM, activeforeground="#ffffff",
            bd=1, relief="ridge", padx=4, pady=6, cursor="hand2",
            command=self.run_readiness_diagnostic
        )
        btn_readiness.pack(side="left", expand=True, fill="x", padx=2)

        # 4. Physical Exertion / Workout Load
        btn_ex = tk.Button(
            row2, text="⚡ WORKOUT", font=("Consolas", 8, "bold"),
            bg="#211806", fg="#ffaa00", activebackground="#3d2a08", activeforeground="#ffffff",
            bd=1, relief="ridge", padx=4, pady=6, cursor="hand2", command=self.action_log_exercise_dialog
        )
        btn_ex.pack(side="left", expand=True, fill="x", padx=2)

        # 5. Multi-Table Telemetry Rollback
        btn_undo = tk.Button(
            row2, text="↺ UNDO", font=("Consolas", 8, "bold"),
            bg="#211014", fg="#ff4455", activebackground="#38151c", activeforeground="#ffffff",
            bd=1, relief="ridge", padx=6, pady=6, cursor="hand2", command=self.action_undo_intake
        )
        btn_undo.pack(side="left", expand=False, padx=2)

        # 6. Biometric Archives
        btn_archives = tk.Button(
            row2, text="📊 ARCHIVES", font=("Consolas", 8, "bold"),
            bg="#0e2838", fg=CYAN_BRIGHT, activebackground=CYAN_DIM, activeforeground="#ffffff",
            bd=1, relief="ridge", padx=6, pady=6, cursor="hand2", command=self.action_view_archives
        )
        btn_archives.pack(side="left", expand=False, padx=2)

    def _build_telemetry_terminal(self):
        term_frame = tk.Frame(self.root, bg=BG_DARK, padx=20, pady=4)
        term_frame.pack(fill="both", expand=True)

        tk.Label(term_frame, text="PDA LOG PROTOCOL OUTPUT", font=("Consolas", 8, "bold"), fg=CYAN_DIM, bg=BG_DARK).pack(anchor="w")

        self.terminal = tk.Text(
            term_frame, bg="#02070b", fg=TEXT_LIGHT, insertbackground=CYAN_BRIGHT,
            font=("Consolas", 9), height=5, bd=1, relief="solid", highlightthickness=1,
            highlightbackground=PANEL_BORDER, padx=8, pady=4
        )
        self.terminal.pack(fill="both", expand=True)
        self.log_terminal("Alterra ARX-10 Operating System Initialized.")
        self.log_terminal("Biometric telemetry online.")

    def log_terminal(self, text: str):
        now_str = time_manager.now().strftime("%I:%M:%S %p")
        self.terminal.insert("end", f"[{now_str}] > {text}\n")
        self.terminal.see("end")

    def refresh_display(self):
        cfg = config_manager.load_config() or config_manager.DEFAULT_CONFIG
        totals = database.get_today_totals()
        h_status, h_min = self.hud.evaluate_hydration()
        n_status, n_min = self.hud.evaluate_nutrition()

        w_ml = totals['water_ml']
        # Dynamic exertion scaling: pulls +500ml/hr if workout logged today
        w_tgt = self.hud.get_dynamic_hydration_target() if hasattr(self.hud, 'get_dynamic_hydration_target') else self.hud.target_water_ml
        m_cnt = totals['meals_count']
        m_tgt = self.hud.target_meals

        # Dynamic exertion interval: pulls compressed interval (~50m) if exercised in last 3h
        h_interval = self.hud.get_dynamic_hydration_interval() if hasattr(self.hud, 'get_dynamic_hydration_interval') else self.hud.hydration_interval_min

        # --- 1. CIRCULAR DECAY GAUGES ---
        # Water
        w_frac = max(0.0, 1.0 - (h_min / h_interval)) if h_min != 999 else 0.0
        w_sub = f"{max(0, h_interval - h_min)}m left" if h_min < h_interval else f"+{h_min - h_interval}m over"
        self.gauge_water.set_data(fraction=w_frac, center_val=f"{int(w_ml)}ml", sub_val=w_sub, status=h_status)

        # Food
        m_interval = self.hud.meal_interval_min
        n_frac = max(0.0, 1.0 - (n_min / m_interval)) if n_min != 999 else 0.0
        n_sub = f"{max(0, m_interval - n_min)}m left" if n_min < m_interval else f"+{n_min - m_interval}m over"
        self.gauge_food.set_data(fraction=n_frac, center_val=f"{m_cnt}/{m_tgt}", sub_val=n_sub, status=n_status)

        # --- SLEEP & BIO-ENERGY (Two-Process Bio-Energy Engine) ---
        alertness_frac, s_center, s_sub, s_status, is_dip = self.hud.evaluate_rest()
        self.gauge_sleep.set_data(
            fraction=alertness_frac,
            center_val=s_center,
            sub_val=s_sub,
            status=s_status
        )

        # --- 2. HYGIENE GAUGES (BRUSH & SHOWER) ---
        target_brush = int(cfg.get("target_brushing", 2))
        shower_freq = cfg.get("shower_frequency", "Daily")

        # Brushing
        try:
            b_cnt = database.get_hygiene_today_count("brushing")
        except AttributeError:
            intakes = database.get_today_intakes()
            b_cnt = sum(1 for r in intakes if r.get("tag") == "brushing")

        b_frac = min(1.0, b_cnt / target_brush if target_brush > 0 else 1.0)
        b_status = "OPTIMAL" if b_cnt >= target_brush else "DUE"
        b_sub = "COMPLIANT" if b_cnt >= target_brush else f"{target_brush - b_cnt} DUE"
        self.gauge_brush.set_data(fraction=b_frac, center_val=f"{b_cnt}/{target_brush}", sub_val=b_sub, status=b_status)

        # Shower
        try:
            last_shower_str = database.get_last_hygiene_time("shower")
        except AttributeError:
            intakes = database.get_all_intake_history(days=None, order="desc")
            last_shower_str = next((r.get("logged_at") for r in intakes if r.get("tag") == "shower"), None)

        if not last_shower_str:
            sh_days_ago = 999
        else:
            try:
                dt_sh = datetime.strptime(str(last_shower_str)[:10], "%Y-%m-%d")
                sh_days_ago = (datetime.now().date() - dt_sh.date()).days
            except Exception:
                sh_days_ago = 999

        if shower_freq == "Daily":
            sh_ok = (sh_days_ago == 0)
            sh_frac = 1.0 if sh_ok else 0.0
            sh_center = "1/1" if sh_ok else "0/1"
            sh_sub = "COMPLIANT" if sh_ok else "DUE TODAY"
            sh_status = "OPTIMAL" if sh_ok else "DUE"
        else:
            sh_ok = (sh_days_ago <= 1)
            sh_frac = 1.0 if sh_ok else 0.0
            sh_center = "DONE" if sh_days_ago == 0 else ("NOMINAL" if sh_days_ago == 1 else "DUE")
            sh_sub = "TODAY" if sh_days_ago == 0 else ("1d AGO" if sh_days_ago == 1 else f"{sh_days_ago}d AGO")
            sh_status = "OPTIMAL" if sh_ok else "DUE"

        self.gauge_shower.set_data(fraction=sh_frac, center_val=sh_center, sub_val=sh_sub, status=sh_status)

        # Overall summary indicator
        if "OVERDUE" in (h_status, n_status, s_status):
            self.lbl_vitals_summary.config(text="CRITICAL BIOLOGICAL DEFICIT", fg=ALERT_RED)
        elif "DUE" in (h_status, n_status, s_status, b_status, sh_status):
            self.lbl_vitals_summary.config(text="MAINTENANCE INTERVAL REQUIRED", fg=WARN_AMBER)
        else:
            self.lbl_vitals_summary.config(text="ALL PARAMETERS NOMINAL", fg=SUCCESS_GREEN)

        # --- Linear Progress Bars ---
        w_pct = int((w_ml / w_tgt) * 100) if w_tgt else 0
        ex_tag = " [EXERTION LOAD]" if w_tgt > self.hud.target_water_ml else ""
        self.lbl_water_vals.config(text=f"{int(w_ml)} / {w_tgt} ml ({w_pct}%){ex_tag}")
        self.lbl_water_status.config(text=h_status)
        h_color = SUCCESS_GREEN if h_status in ["OPTIMAL", "TARGET_REACHED"] else (WARN_AMBER if h_status == "DUE" else ALERT_RED)
        self.lbl_water_status.config(fg=h_color)
        self.water_bar.set_progress(w_ml, w_tgt, color=h_color)
        h_time_str = f"{h_min}m ago" if h_min != 999 else "Never"
        self.lbl_water_timer.config(text=f"Last: {h_time_str} | Interval: {h_interval}m")

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
            # --- CIRCADIAN TROUGH PROTOCOL (Process C Slump) ---
            _, _, _, _, is_dip = self.hud.evaluate_rest()
            if is_dip and not getattr(self, "_circadian_alerted_today", False):
                self._circadian_alerted_today = True
                dip_msg = "Notice: Physiological telemetry indicates onset of circadian slump. Anticipate transient cognitive latency."
                self.log_terminal(f"PHYSIOLOGICAL EVENT: {dip_msg}")
                threading.Thread(target=speak, args=(dip_msg, "pda"), daemon=True).start()
            elif not is_dip:
                # Reset once you pass through the 7-9h wake window
                self._circadian_alerted_today = False

            # --- METABOLIC STATUS EVALUATION ---
            h_status, _ = self.hud.evaluate_hydration()
            n_status, _ = self.hud.evaluate_nutrition()

            # 1. Hydration Monitoring
            if h_status != self._last_h_alert:
                if h_status == "OVERDUE":
                    line = dialogues.get_ultron_dialogue("hydration_critical")
                    self.log_terminal(f"CRITICAL OVERRIDE: {line}")
                    threading.Thread(target=speak, args=(line, "ultron"), daemon=True).start()
                    self._last_h_alert = h_status
                elif h_status == "DUE":
                    line = dialogues.get_dialogue("hydration_due")
                    self.log_terminal(f"TELEMETRY ALERT: {line}")
                    threading.Thread(target=speak, args=(line, "pda"), daemon=True).start()
                    self._last_h_alert = h_status
                elif h_status == "OPTIMAL":
                    self._last_h_alert = None

            # 2. Nutrition Monitoring
            if n_status != self._last_n_alert:
                if n_status == "OVERDUE":
                    line = dialogues.get_ultron_dialogue("meal_critical")
                    self.log_terminal(f"CRITICAL OVERRIDE: {line}")
                    threading.Thread(target=speak, args=(line, "ultron"), daemon=True).start()
                    self._last_n_alert = n_status
                elif n_status == "DUE":
                    line = dialogues.get_dialogue("meal_due")
                    self.log_terminal(f"TELEMETRY ALERT: {line}")
                    threading.Thread(target=speak, args=(line, "pda"), daemon=True).start()
                    self._last_n_alert = n_status
                elif n_status == "OPTIMAL":
                    self._last_n_alert = None
        else:
            # Standby window active: clear alert memory for clean morning initialization
            self._last_h_alert = None
            self._last_n_alert = None
            self._circadian_alerted_today = False

        self.root.after(60000, self.poll_timers)

    def _init_tray(self):
        menu = pystray.Menu(
            pystray.MenuItem("Open Alterra HUD", self.show_from_tray, default=True),
            pystray.MenuItem("+ Log Water (250ml)", lambda: self.root.after(0, self.action_log_water)),
            pystray.MenuItem("+ Log Snack (0.5 Ration)", lambda: self.root.after(0, self.action_log_snack)),
            pystray.MenuItem("+ Log Sustenance Meal", lambda: self.root.after(0, self.action_log_meal)),
            pystray.MenuItem("🪥 Log Brushing", lambda: self.root.after(0, self.action_log_brush)),
            pystray.MenuItem("🚿 Log Shower", lambda: self.root.after(0, self.action_log_shower)),
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
            try:
                self.tray_icon.stop()
            except Exception:
                pass

        # If shutting down during sleep window, spawn Ultron Nightwatch as a detached process
        if self.hud.is_sleep_window():
            nightwatch_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ultron_nightwatch.py")
            py_exe = sys.executable

            DETACHED_PROCESS = 0x00000008
            CREATE_NEW_PROCESS_GROUP = 0x00000200

            try:
                subprocess.Popen(
                    [py_exe, nightwatch_script],
                    creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
                    close_fds=True,
                    cwd=os.path.dirname(os.path.abspath(__file__)),
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
            except Exception as e:
                print(f"[NIGHTWATCH SPAWN ERROR] {e}")

            self.root.destroy()
        else:
            # Daytime shutdown: Alterra farewell dialogue
            shutdown_msg = dialogues.SHUTDOWN
            threading.Thread(target=speak, args=(shutdown_msg, "pda"), daemon=False).start()
            self.root.after(700, self.root.destroy)

    def action_log_water(self, amount: float = 250.0):
        """Logs standard 250ml water canister intake with acoustic and voice feedback."""
        database.log_water(amount)
        sfx.play_sfx("water_intake_logged")

        self.log_terminal(f"VITAL SIGNS: Hydration fluid (+{int(amount)}ml) assimilated.")
        self.refresh_display()

        try:
            line = dialogues.get_dialogue("water") if hasattr(dialogues, "get_dialogue") else "Vital signs nominal. Fluid intake recorded."
        except Exception:
            line = "Vital signs nominal. Fluid intake recorded."

        threading.Thread(target=speak, args=(line, "pda"), daemon=True).start()

    def action_log_meal(self, tag: str = "Standard Ration"):
        """Logs nutritional ration intake and triggers eating_food_logged.wav post-commit."""
        database.log_meal(tag)
        sfx.play_sfx("eating_food_logged")

        self.log_terminal(f"VITAL SIGNS: Caloric ration [{tag}] integrated.")
        self.refresh_display()

        try:
            totals = database.get_today_totals()
            line = dialogues.get_meal_logged_line(tag, int(totals.get("meals_count", 1)), int(self.hud.target_meals))
        except Exception:
            line = "Caloric intake recorded. Metabolic balance stabilized."

        threading.Thread(target=speak, args=(line, "pda"), daemon=True).start()

    def action_log_brush(self):
        try:
            database.log_hygiene("brushing")
        except AttributeError:
            database.log_intake("hygiene", 1.0, "brushing")
        self.log_terminal("HYGIENE LOGGED: Oral cavity sanitized.")
        self.refresh_display()
        line = "Oral hygiene protocol acknowledged. Dental degradation vectors mitigated."
        threading.Thread(target=speak, args=(line, "pda"), daemon=True).start()

    def action_log_shower(self):
        try:
            database.log_hygiene("shower")
        except AttributeError:
            database.log_intake("hygiene", 1.0, "shower")
        sfx.play_sfx("shower_logged")

        self.log_terminal("HYGIENE LOGGED: Full dermal decontamination cycle complete.")
        self.refresh_display()
        line = "Dermal decontamination confirmed. External bio-contaminant levels normalized."
        threading.Thread(target=speak, args=(line, "pda"), daemon=True).start()

    def action_undo_intake(self):
        """Purges the most recent telemetry entry across intake, hygiene, exercise, or naps."""
        deleted = database.undo_last_intake()
        if not deleted:
            self.log_terminal("UNDO NOTICE: No recent telemetry entries found to purge.")
            messagebox.showinfo("Alterra PDA", "No recent records found to rollback.")
            return

        i_type = deleted.get("type", "unknown")
        amt = deleted.get("amount", 0)
        tag = deleted.get("tag", "")

        # Format descriptive HUD terminal feedback across all operational vectors
        if i_type == "hydration":
            msg = f"Purged {int(amt)}ml fluid"
        elif i_type == "hygiene":
            msg = f"Purged hygiene protocol: {tag}"
        elif i_type == "exercise":
            msg = f"Purged exertion log: {float(amt):.1f}h {tag}"
        elif i_type == "nap":
            msg = f"Purged recovery sleep: {int(amt)}m nap"
        elif i_type == "snack":
            msg = f"Purged micro-ration: {tag}"
        else:
            msg = f"Purged nutritional ration: {tag}"

        self.log_terminal(f"TELEMETRY ROLLBACK: {msg}")
        self.refresh_display()

        # Context-aware Alterra voice line with fallback
        try:
            if hasattr(dialogues, "get_rollback_line"):
                line = dialogues.get_rollback_line(i_type, tag)
            else:
                line = dialogues.get_dialogue("undo_intake")
        except Exception:
            if i_type in ("exercise", "nap"):
                line = f"Physical telemetry rollback confirmed. {i_type.capitalize()} record purged from active memory."
            else:
                line = "Telemetry rollback confirmed. Record purged from operational memory."

        threading.Thread(target=speak, args=(line, "pda"), daemon=True).start()

    # Safety alias: guarantees tray menu & buttons work regardless of name used
    action_undo_last = action_undo_intake

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

        current_dt = time_manager.now()

        grid_frame = tk.Frame(win, bg=PANEL_BG)
        grid_frame.pack(padx=20, fill="x", pady=5)

        # Visible blinking cursor via insertbackground & insertwidth
        tk.Label(grid_frame, text="Wake Date (DD/MM/YYYY):", font=("Consolas", 9), fg=TEXT_LIGHT, bg=PANEL_BG).grid(row=0, column=0, sticky="w", pady=6)
        entry_date = tk.Entry(grid_frame, bg="#02070b", fg=CYAN_BRIGHT, insertbackground=CYAN_BRIGHT, insertwidth=2, font=("Consolas", 9), width=15)
        entry_date.insert(0, current_dt.strftime("%d/%m/%Y"))
        entry_date.grid(row=0, column=1, columnspan=2, sticky="w", pady=6, padx=5)

        tk.Label(grid_frame, text="Sleep Time (HH:MM):", font=("Consolas", 9), fg=TEXT_LIGHT, bg=PANEL_BG).grid(row=1, column=0, sticky="w", pady=6)
        entry_s_time = tk.Entry(grid_frame, bg="#02070b", fg=CYAN_BRIGHT, insertbackground=CYAN_BRIGHT, insertwidth=2, font=("Consolas", 9), width=8)
        entry_s_time.insert(0, "11:30")
        entry_s_time.grid(row=1, column=1, sticky="w", pady=6, padx=5)
        combo_s_ampm = ttk.Combobox(grid_frame, values=["PM", "AM"], width=4, state="readonly")
        combo_s_ampm.set("PM")
        combo_s_ampm.grid(row=1, column=2, sticky="w", pady=6)

        tk.Label(grid_frame, text="Wake Time (HH:MM):", font=("Consolas", 9), fg=TEXT_LIGHT, bg=PANEL_BG).grid(row=2, column=0, sticky="w", pady=6)
        entry_w_time = tk.Entry(grid_frame, bg="#02070b", fg=CYAN_BRIGHT, insertbackground=CYAN_BRIGHT, insertwidth=2, font=("Consolas", 9), width=8)
        entry_w_time.insert(0, current_dt.strftime("%I:%M").strip().lstrip("0") or "7:00")
        entry_w_time.grid(row=2, column=1, sticky="w", pady=6, padx=5)
        combo_w_ampm = ttk.Combobox(grid_frame, values=["AM", "PM"], width=4, state="readonly")
        combo_w_ampm.set(current_dt.strftime("%p"))
        combo_w_ampm.grid(row=2, column=2, sticky="w", pady=6)

        tk.Label(grid_frame, text="Disruptions:", font=("Consolas", 9), fg=TEXT_LIGHT, bg=PANEL_BG).grid(row=3, column=0, sticky="w", pady=6)
        entry_dis = tk.Entry(grid_frame, bg="#02070b", fg=CYAN_BRIGHT, insertbackground=CYAN_BRIGHT, insertwidth=2, font=("Consolas", 9), width=8)
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
                wake_date = None

                for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%Y/%m/%d"):
                    try:
                        wake_date = datetime.strptime(d_str, fmt)
                        break
                    except ValueError:
                        continue

                if not wake_date:
                    raise ValueError(f"Unrecognised date format '{d_str}'. Use DD/MM/YYYY or YYYY-MM-DD.")

                s_hr, s_mn = parse_time_component(entry_s_time.get(), combo_s_ampm.get())
                w_hr, w_mn = parse_time_component(entry_w_time.get(), combo_w_ampm.get())

                t_wake = wake_date.replace(hour=w_hr, minute=w_mn, second=0)
                t_sleep = wake_date.replace(hour=s_hr, minute=s_mn, second=0)

                # Midnight crossover adjustment: if wake <= sleep, sleep began on the previous calendar day
                if t_wake <= t_sleep:
                    t_sleep -= timedelta(days=1)

                dis_val = int(entry_dis.get().strip() or 0)

                dur = database.log_sleep(
                    t_sleep.strftime("%Y-%m-%d %H:%M"),
                    t_wake.strftime("%Y-%m-%d %H:%M"),
                    dis_val,
                    "Manual HUD Entry"
                )
                sfx.play_sfx("rest_logged")
                win.destroy()

                import sleep_analytics
                report = sleep_analytics.analyze_sleep_trajectory()

                self.log_terminal(f"Logged Sleep: {dur:.1f}h (Disruptions: {dis_val})")
                for r_line in report.get("terminal_report", "").split("\n"):
                    if r_line.strip():
                        self.log_terminal(r_line)

                self.refresh_display()
                if report.get("voice_line"):
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
        win.geometry("920x580")
        win.configure(bg=PANEL_BG)

        threading.Thread(target=speak, args=(dialogues.get_archive_viewed_line(), "pda"), daemon=True).start()

        archive_scope = {"days": 7}
        loaded_tabs = set()  # Tracks which tabs have loaded data to eliminate lag

        # --- TOP FILTER BAR ---
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

        # --- THEME INJECTION (DARK SUBNAUTICA PALETTE) ---
        style = ttk.Style()
        if "clam" in style.theme_names():
            style.theme_use("clam")

        style.configure("TNotebook", background=PANEL_BG, borderwidth=0)
        style.configure("TNotebook.Tab", background="#0c202d", foreground=TEXT_LIGHT, font=("Consolas", 9, "bold"), padding=[10, 5])
        style.map("TNotebook.Tab", background=[("selected", CYAN_DIM)], foreground=[("selected", "#ffffff")])

        # Treeview Oceanic Dark Theme
        style.configure(
            "PDA.Treeview",
            background="#06131c",
            foreground="#c8e4f0",
            fieldbackground="#040b11",
            rowheight=25,
            font=("Consolas", 9),
            borderwidth=0
        )
        style.configure(
            "PDA.Treeview.Heading",
            background="#0e2838",
            foreground=CYAN_BRIGHT,
            relief="flat",
            font=("Consolas", 9, "bold")
        )
        style.map(
            "PDA.Treeview",
            background=[("selected", "#14374a")],
            foreground=[("selected", "#ffffff")]
        )
        style.map(
            "PDA.Treeview.Heading",
            background=[("active", "#19435b")]
        )

        notebook = ttk.Notebook(win)
        notebook.pack(fill="both", expand=True, padx=12, pady=(4, 5))

        # --- TAB 1: SLEEP & REST TELEMETRY ---
        tab_sleep = tk.Frame(notebook, bg=PANEL_BG)
        notebook.add(tab_sleep, text="SLEEP CYCLES")

        s_cols = ("id", "sleep_time", "wake_time", "duration", "disruptions", "notes")
        tree_sleep = ttk.Treeview(tab_sleep, columns=s_cols, show="headings", height=13, style="PDA.Treeview")
        tree_sleep.heading("id", text="ID")
        tree_sleep.heading("sleep_time", text="Sleep Onset")
        tree_sleep.heading("wake_time", text="Wake Time")
        tree_sleep.heading("duration", text="Duration (h)")
        tree_sleep.heading("disruptions", text="Disruptions")
        tree_sleep.heading("notes", text="Diagnostic Notes")

        tree_sleep.column("id", width=45, anchor="center")
        tree_sleep.column("sleep_time", width=175, anchor="center")
        tree_sleep.column("wake_time", width=175, anchor="center")
        tree_sleep.column("duration", width=85, anchor="center")
        tree_sleep.column("disruptions", width=85, anchor="center")
        tree_sleep.column("notes", width=220, anchor="w")
        tree_sleep.pack(fill="both", expand=True, padx=6, pady=6)

        # --- TAB 2: METABOLIC INTAKE ---
        tab_intake = tk.Frame(notebook, bg=PANEL_BG)
        notebook.add(tab_intake, text="METABOLIC INTAKE")

        i_cols = ("id", "type", "amount", "tag", "logged_at")
        tree_intake = ttk.Treeview(tab_intake, columns=i_cols, show="headings", height=13, style="PDA.Treeview")
        tree_intake.heading("id", text="ID")
        tree_intake.heading("type", text="Type")
        tree_intake.heading("amount", text="Volume / Qty")
        tree_intake.heading("tag", text="Description")
        tree_intake.heading("logged_at", text="Timestamp")

        tree_intake.column("id", width=45, anchor="center")
        tree_intake.column("type", width=95, anchor="center")
        tree_intake.column("amount", width=95, anchor="center")
        tree_intake.column("tag", width=180, anchor="w")
        tree_intake.column("logged_at", width=180, anchor="center")
        tree_intake.pack(fill="both", expand=True, padx=6, pady=6)

        # --- TAB 3: HYGIENE PROTOCOLS ---
        tab_hygiene = tk.Frame(notebook, bg=PANEL_BG)
        notebook.add(tab_hygiene, text="HYGIENE PROTOCOLS")

        h_cols = ("id", "tag", "status", "logged_at")
        tree_hygiene = ttk.Treeview(tab_hygiene, columns=h_cols, show="headings", height=13, style="PDA.Treeview")
        tree_hygiene.heading("id", text="ID")
        tree_hygiene.heading("tag", text="Protocol")
        tree_hygiene.heading("status", text="Compliance")
        tree_hygiene.heading("logged_at", text="Timestamp")

        tree_hygiene.column("id", width=50, anchor="center")
        tree_hygiene.column("tag", width=160, anchor="center")
        tree_hygiene.column("status", width=140, anchor="center")
        tree_hygiene.column("logged_at", width=190, anchor="center")
        tree_hygiene.pack(fill="both", expand=True, padx=6, pady=6)

        # --- TAB 4: EXERCISE & NAPS ---
        tab_exertion = tk.Frame(notebook, bg=PANEL_BG)
        notebook.add(tab_exertion, text="EXERCISE & NAPS")

        e_cols = ("id", "type", "load", "intensity", "logged_at")
        tree_exertion = ttk.Treeview(tab_exertion, columns=e_cols, show="headings", height=13, style="PDA.Treeview")
        tree_exertion.heading("id", text="ID")
        tree_exertion.heading("type", text="Category")
        tree_exertion.heading("load", text="Duration")
        tree_exertion.heading("intensity", text="Intensity / Notes")
        tree_exertion.heading("logged_at", text="Timestamp")

        tree_exertion.column("id", width=50, anchor="center")
        tree_exertion.column("type", width=120, anchor="center")
        tree_exertion.column("load", width=95, anchor="center")
        tree_exertion.column("intensity", width=180, anchor="w")
        tree_exertion.column("logged_at", width=190, anchor="center")
        tree_exertion.pack(fill="both", expand=True, padx=6, pady=6)

        # --- TAB 5: LIFETIME SUMMARY ---
        tab_lifetime = tk.Frame(notebook, bg=PANEL_BG)
        notebook.add(tab_lifetime, text="LIFETIME SUMMARY")

        lifetime_text = tk.Text(
            tab_lifetime, bg="#040b11", fg=TEXT_LIGHT, font=("Consolas", 9),
            bd=1, relief="solid", highlightthickness=1, highlightbackground=PANEL_BORDER,
            padx=14, pady=14
        )
        lifetime_text.pack(fill="both", expand=True, padx=6, pady=6)

        # --- INDIVIDUAL TAB DATA LOADERS ---
        def populate_sleep():
            for row in tree_sleep.get_children():
                tree_sleep.delete(row)
            data = db.get_all_sleep_history(days=archive_scope["days"], order="desc")
            for r in data:
                tree_sleep.insert("", "end", values=(
                    r.get("id"),
                    time_sync.format_date_dmy(r.get("sleep_time")),
                    time_sync.format_date_dmy(r.get("wake_time")),
                    f"{float(r.get('duration_hours', 0.0)):.1f}",
                    r.get("interruptions", 0),
                    r.get("quality_notes", "")
                ))

        def populate_intake():
            for row in tree_intake.get_children():
                tree_intake.delete(row)
            data = db.get_all_intake_history(days=archive_scope["days"], order="desc")
            for r in data:
                t = str(r.get("type", "")).lower()
                if t == "hydration":
                    amt_str = f"{int(r.get('amount', 0))}ml"
                elif t == "hygiene":
                    amt_str = "Completed"
                elif t == "snack":
                    amt_str = "0.5 ration"
                else:
                    amt_str = f"{int(r.get('amount', 1))} meal"
                tree_intake.insert("", "end", values=(
                    r.get("id"),
                    t.upper(),
                    amt_str,
                    r.get("tag", ""),
                    time_sync.format_date_dmy(r.get("logged_at"))
                ))

        def populate_hygiene():
            for row in tree_hygiene.get_children():
                tree_hygiene.delete(row)
            data = db.get_all_hygiene_history(days=archive_scope["days"], order="desc")
            for r in data:
                tree_hygiene.insert("", "end", values=(
                    r.get("id"),
                    str(r.get("tag", "")).upper(),
                    "COMPLETED",
                    time_sync.format_date_dmy(r.get("logged_at"))
                ))

        def populate_exertion():
            for row in tree_exertion.get_children():
                tree_exertion.delete(row)
            ex_data = db.get_all_exercise_history(days=archive_scope["days"], order="desc")
            for r in ex_data:
                tree_exertion.insert("", "end", values=(
                    r.get("id"),
                    "WORKOUT",
                    f"{float(r.get('duration_hours', 0.0)):.1f}h",
                    f"{r.get('intensity', 'moderate')} {r.get('notes', '')}".strip(),
                    time_sync.format_date_dmy(r.get("logged_at"))
                ))
            nap_data = db.get_all_nap_history(days=archive_scope["days"], order="desc")
            for r in nap_data:
                tree_exertion.insert("", "end", values=(
                    r.get("id"),
                    "RECOVERY NAP",
                    f"{int(r.get('duration_minutes', 0))}m",
                    r.get("notes", "Daytime Recovery"),
                    time_sync.format_date_dmy(r.get("logged_at"))
                ))

        def populate_lifetime():
            try:
                import analytics_engine
                data = analytics_engine.get_lifetime_summary()
                first_day_dmy = time_sync.format_date_dmy(data.get('first_day', ''), include_time=False)
                report = (
                    "==========================================================\n"
                    "       ALTERRA CORP // LIFETIME TELEMETRY ARCHIVE          \n"
                    "==========================================================\n\n"
                    f"  * Telemetry Genesis:          {first_day_dmy}\n"
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
            except Exception as e:
                lifetime_text.delete("1.0", "end")
                lifetime_text.insert("end", f"Lifetime telemetry summary unavailable: {e}")

        # --- INSTANT LAZY LOADING DISPATCHER ---
        def load_current_tab(force=False):
            cur = notebook.index(notebook.select())
            if not force and cur in loaded_tabs:
                return
            if cur == 0:
                populate_sleep()
            elif cur == 1:
                populate_intake()
            elif cur == 2:
                populate_hygiene()
            elif cur == 3:
                populate_exertion()
            elif cur == 4:
                populate_lifetime()
            loaded_tabs.add(cur)

        def on_tab_changed(event):
            if getattr(win, "_tabs_ready", False):
                sfx.play_sfx("archive_tab_switches")
            load_current_tab()

        notebook.bind("<<NotebookTabChanged>>", on_tab_changed)

        def switch_scope(scope_days):
            archive_scope["days"] = scope_days
            loaded_tabs.clear()  # Invalidate cache
            if scope_days == 7:
                btn_scope_7d.config(bg="#0e2838", fg=CYAN_BRIGHT)
                btn_scope_all.config(bg="#0c202d", fg=TEXT_MUTED)
                lbl_scope_status.config(text="Viewing rolling 7-day operational cycle")
            else:
                btn_scope_7d.config(bg="#0c202d", fg=TEXT_MUTED)
                btn_scope_all.config(bg="#0e2838", fg=CYAN_BRIGHT)
                lbl_scope_status.config(text="Viewing all historical entries since day 1")
            load_current_tab(force=True)

        btn_scope_7d.config(command=lambda: switch_scope(7))
        btn_scope_all.config(command=lambda: switch_scope(None))

        # Initial load: only load Tab 0
        load_current_tab(force=True)
        win._tabs_ready = True

        # --- BOTTOM ACTION BAR ---
        bar_actions = tk.Frame(win, bg=PANEL_BG, pady=6, padx=12)
        bar_actions.pack(fill="x")

        def delete_selected():
            cur_tab = notebook.index(notebook.select())
            table_map = {
                0: (tree_sleep, "sleep_logs"),
                1: (tree_intake, "intake_logs"),
                2: (tree_hygiene, "hygiene_logs"),
                3: (tree_exertion, "exercise_logs")
            }

            if cur_tab not in table_map:
                messagebox.showinfo("Telemetry Summary", "The Lifetime Summary is an aggregate view. Select records from specific log tabs to delete.")
                return

            target_tree, target_table = table_map[cur_tab]
            selected = target_tree.selection()
            if not selected:
                messagebox.showwarning("Selection Required", "Select a telemetry record from the table to expunge.")
                return

            rec_id = target_tree.item(selected[0])["values"][0]
            if cur_tab == 3:
                cat = str(target_tree.item(selected[0])["values"][1]).upper()
                target_table = "nap_logs" if "NAP" in cat else "exercise_logs"

            confirm = messagebox.askyesno("Alterra Protocol Override", f"Confirm permanent deletion of record #{rec_id} from {target_table}?")
            if confirm:
                if db.delete_record_by_id(target_table, rec_id):
                    self.log_terminal(f"ARCHIVE OVERRIDE: Expunged record #{rec_id} from {target_table}.")
                    load_current_tab(force=True)
                    self.refresh_display()
                else:
                    messagebox.showerror("Deletion Error", "Could not remove record from cloud/local storage.")

        btn_del = tk.Button(
            bar_actions, text="EXPUNGE SELECTED RECORD", font=("Consolas", 8, "bold"),
            bg="#2a0d12", fg="#ff4455", activebackground="#45121c", activeforeground="#ffffff",
            bd=1, relief="ridge", padx=10, pady=5, cursor="hand2", command=delete_selected
        )
        btn_del.pack(side="left")

        btn_refresh = tk.Button(
            bar_actions, text="REFRESH DATABASE", font=("Consolas", 8, "bold"),
            bg="#0e2838", fg=CYAN_BRIGHT, activebackground=CYAN_DIM, activeforeground="#ffffff",
            bd=1, relief="ridge", padx=10, pady=5, cursor="hand2",
            command=lambda: load_current_tab(force=True)
        )
        btn_refresh.pack(side="right")

    def action_settings_dialog(self):
        cfg = config_manager.load_config() or config_manager.DEFAULT_CONFIG

        win = tk.Toplevel(self.root)
        win.title("ALTERRA CORP // BIO-PARAMETERS & SYSTEM CONFIGURATION")
        win.geometry("580x780")
        win.configure(bg=PANEL_BG)
        win.resizable(False, False)

        header = tk.Frame(win, bg=PANEL_BG, padx=16, pady=8)
        header.pack(fill="x")
        tk.Label(header, text="ALTERRA PROTOCOL CONFIGURATION CONSOLE", font=("Consolas", 11, "bold"), fg=CYAN_BRIGHT, bg=PANEL_BG).pack(anchor="w")
        tk.Label(header, text="Adjust physiological targets, sleep exclusion windows, and persistence.", font=("Consolas", 8), fg=TEXT_MUTED, bg=PANEL_BG).pack(anchor="w")

        body = tk.Frame(win, bg=PANEL_BG, padx=16, pady=4)
        body.pack(fill="both", expand=True)

        row = 0
        def add_section(text):
            nonlocal row
            lbl = tk.Label(body, text=f"--- {text} ---", font=("Consolas", 9, "bold"), fg=CYAN_DIM, bg=PANEL_BG)
            lbl.grid(row=row, column=0, columnspan=2, sticky="w", pady=(8, 3))
            row += 1

        # 1. Biological Targets & Hygiene
        add_section("BIOLOGICAL & HYGIENE TARGETS")

        tk.Label(body, text="Hydration Target (ml/day):", font=("Consolas", 9), fg=TEXT_LIGHT, bg=PANEL_BG).grid(row=row, column=0, sticky="w", pady=2)
        ent_water = tk.Entry(body, font=("Consolas", 9), bg="#02070b", fg=CYAN_BRIGHT, insertbackground=CYAN_BRIGHT, insertwidth=2, width=12)
        ent_water.insert(0, str(cfg.get("target_water_ml", 2500)))
        ent_water.grid(row=row, column=1, sticky="w", pady=2)
        row += 1

        tk.Label(body, text="Hydration Interval (minutes):", font=("Consolas", 9), fg=TEXT_LIGHT, bg=PANEL_BG).grid(row=row, column=0, sticky="w", pady=2)
        ent_h_int = tk.Entry(body, font=("Consolas", 9), bg="#02070b", fg=CYAN_BRIGHT, insertbackground=CYAN_BRIGHT, insertwidth=2, width=12)
        ent_h_int.insert(0, str(cfg.get("hydration_interval_min", 75)))
        ent_h_int.grid(row=row, column=1, sticky="w", pady=2)
        row += 1

        tk.Label(body, text="Daily Meals Target (rations):", font=("Consolas", 9), fg=TEXT_LIGHT, bg=PANEL_BG).grid(row=row, column=0, sticky="w", pady=2)
        ent_meals = tk.Entry(body, font=("Consolas", 9), bg="#02070b", fg=CYAN_BRIGHT, insertbackground=CYAN_BRIGHT, insertwidth=2, width=12)
        ent_meals.insert(0, str(cfg.get("target_meals", 4)))
        ent_meals.grid(row=row, column=1, sticky="w", pady=2)
        row += 1

        tk.Label(body, text="Meal Interval (minutes):", font=("Consolas", 9), fg=TEXT_LIGHT, bg=PANEL_BG).grid(row=row, column=0, sticky="w", pady=2)
        ent_m_int = tk.Entry(body, font=("Consolas", 9), bg="#02070b", fg=CYAN_BRIGHT, insertbackground=CYAN_BRIGHT, insertwidth=2, width=12)
        ent_m_int.insert(0, str(cfg.get("meal_interval_min", 210)))
        ent_m_int.grid(row=row, column=1, sticky="w", pady=2)
        row += 1

        # Brushing Target Dropdown
        tk.Label(body, text="Brushing Target (per day):", font=("Consolas", 9), fg=TEXT_LIGHT, bg=PANEL_BG).grid(row=row, column=0, sticky="w", pady=2)
        combo_brush = ttk.Combobox(body, values=["1", "2"], width=6, state="readonly")
        combo_brush.set(str(cfg.get("target_brushing", 2)))
        combo_brush.grid(row=row, column=1, sticky="w", pady=2)
        row += 1

        # Shower Frequency Dropdown
        tk.Label(body, text="Shower Frequency:", font=("Consolas", 9), fg=TEXT_LIGHT, bg=PANEL_BG).grid(row=row, column=0, sticky="w", pady=2)
        combo_shower = ttk.Combobox(body, values=["Daily", "Every Alternative Day"], width=16, state="readonly")
        combo_shower.set(str(cfg.get("shower_frequency", "Daily")))
        combo_shower.grid(row=row, column=1, sticky="w", pady=2)
        row += 1

        # 2. Standby / Sleep Silencing Window
        add_section("STANDBY / SLEEP SILENCING WINDOW")

        # Helper: Convert stored 24h integer to 12h string and AM/PM
        def to_12h_parts(h24: int, m: int):
            ampm = "PM" if h24 >= 12 else "AM"
            h12 = h24 % 12
            if h12 == 0:
                h12 = 12
            return f"{h12:02d}", f"{m:02d}", ampm

        # Helper: Parse 12h + AM/PM back to 24h
        def to_24h(h_str: str, m_str: str, ampm: str):
            h = int(h_str.strip())
            m = int(m_str.strip())
            if h < 1 or h > 12 or m < 0 or m > 59:
                raise ValueError("Hours must be 1-12 and minutes 0-59.")
            if ampm == "PM" and h != 12:
                h += 12
            elif ampm == "AM" and h == 12:
                h = 0
            return h, m

        # Sleep Start (e.g. 11:00 PM)
        s_h12, s_m12, s_ampm = to_12h_parts(
            cfg.get("sleep_start_hour", 23),
            cfg.get("sleep_start_minute", 0)
        )

        f_sleep_start = tk.Frame(body, bg=PANEL_BG)
        tk.Label(body, text="Sleep Inactive Start:", font=("Consolas", 9), fg=TEXT_LIGHT, bg=PANEL_BG).grid(row=row, column=0, sticky="w", pady=3)
        ent_ss_h = tk.Entry(f_sleep_start, font=("Consolas", 9), bg="#02070b", fg=CYAN_BRIGHT, insertbackground=CYAN_BRIGHT, insertwidth=2, width=4)
        ent_ss_h.insert(0, s_h12)
        ent_ss_h.pack(side="left")
        tk.Label(f_sleep_start, text=":", fg=CYAN_BRIGHT, bg=PANEL_BG).pack(side="left", padx=1)
        ent_ss_m = tk.Entry(f_sleep_start, font=("Consolas", 9), bg="#02070b", fg=CYAN_BRIGHT, insertbackground=CYAN_BRIGHT, insertwidth=2, width=4)
        ent_ss_m.insert(0, s_m12)
        ent_ss_m.pack(side="left", padx=(0, 4))
        combo_ss_ampm = ttk.Combobox(f_sleep_start, values=["PM", "AM"], width=4, state="readonly", font=("Consolas", 9))
        combo_ss_ampm.set(s_ampm)
        combo_ss_ampm.pack(side="left")
        f_sleep_start.grid(row=row, column=1, sticky="w", pady=3)
        row += 1

        # Wake Resume (e.g. 07:00 AM)
        w_h12, w_m12, w_ampm = to_12h_parts(
            cfg.get("sleep_end_hour", 7),
            cfg.get("sleep_end_minute", 0)
        )

        f_sleep_end = tk.Frame(body, bg=PANEL_BG)
        tk.Label(body, text="Wake Active Resume:", font=("Consolas", 9), fg=TEXT_LIGHT, bg=PANEL_BG).grid(row=row, column=0, sticky="w", pady=3)
        ent_se_h = tk.Entry(f_sleep_end, font=("Consolas", 9), bg="#02070b", fg=CYAN_BRIGHT, insertbackground=CYAN_BRIGHT, insertwidth=2, width=4)
        ent_se_h.insert(0, w_h12)
        ent_se_h.pack(side="left")
        tk.Label(f_sleep_end, text=":", fg=CYAN_BRIGHT, bg=PANEL_BG).pack(side="left", padx=1)
        ent_se_m = tk.Entry(f_sleep_end, font=("Consolas", 9), bg="#02070b", fg=CYAN_BRIGHT, insertbackground=CYAN_BRIGHT, insertwidth=2, width=4)
        ent_se_m.insert(0, w_m12)
        ent_se_m.pack(side="left", padx=(0, 4))
        combo_se_ampm = ttk.Combobox(f_sleep_end, values=["AM", "PM"], width=4, state="readonly", font=("Consolas", 9))
        combo_se_ampm.set(w_ampm)
        combo_se_ampm.pack(side="left")
        f_sleep_end.grid(row=row, column=1, sticky="w", pady=3)
        row += 1

        # 3. Environment & Persistence Engine
        add_section("ENVIRONMENT & PERSISTENCE ENGINE")

        # Timezone Combobox with GMT Mappings
        tk.Label(body, text="System Timezone (GMT):", font=("Consolas", 9), fg=TEXT_LIGHT, bg=PANEL_BG).grid(row=row, column=0, sticky="w", pady=2)
        current_tz = cfg.get("timezone", "UTC")
        default_label = next((k for k, v in TIMEZONE_MAP.items() if v == current_tz), "Asia/Kolkata (GMT+05:30)")

        combo_tz = ttk.Combobox(body, values=list(TIMEZONE_MAP.keys()), width=28, state="readonly")
        combo_tz.set(default_label)
        combo_tz.grid(row=row, column=1, sticky="w", pady=2)
        row += 1

        tk.Label(body, text="Storage Architecture:", font=("Consolas", 9), fg=TEXT_LIGHT, bg=PANEL_BG).grid(row=row, column=0, sticky="w", pady=2)
        combo_storage = ttk.Combobox(body, values=["local", "supabase"], width=12, state="readonly")
        combo_storage.set(cfg.get("storage_mode", "local"))
        combo_storage.grid(row=row, column=1, sticky="w", pady=2)
        row += 1

        tk.Label(body, text="Supabase URL:", font=("Consolas", 9), fg=TEXT_LIGHT, bg=PANEL_BG).grid(row=row, column=0, sticky="w", pady=2)
        ent_url = tk.Entry(body, font=("Consolas", 9), bg="#02070b", fg=CYAN_BRIGHT, insertbackground=CYAN_BRIGHT, insertwidth=2, width=28)
        ent_url.insert(0, str(cfg.get("supabase_url", "")))
        ent_url.grid(row=row, column=1, sticky="w", pady=2)
        row += 1

        tk.Label(body, text="Supabase Anon Key:", font=("Consolas", 9), fg=TEXT_LIGHT, bg=PANEL_BG).grid(row=row, column=0, sticky="w", pady=2)
        ent_key = tk.Entry(body, font=("Consolas", 9), bg="#02070b", fg=CYAN_BRIGHT, insertbackground=CYAN_BRIGHT, insertwidth=2, width=28, show="*")
        ent_key.insert(0, str(cfg.get("supabase_key", "")))
        ent_key.grid(row=row, column=1, sticky="w", pady=2)
        row += 1

        def commit_settings():
            try:
                # Parse 12-hour values back into 24-hour integers for config persistence
                ss_h, ss_m = to_24h(ent_ss_h.get(), ent_ss_m.get(), combo_ss_ampm.get())
                se_h, se_m = to_24h(ent_se_h.get(), ent_se_m.get(), combo_se_ampm.get())

                selected_tz_label = combo_tz.get()
                resolved_iana_tz = TIMEZONE_MAP.get(selected_tz_label, "UTC")

                new_cfg = {
                    "timezone": resolved_iana_tz,
                    "storage_mode": combo_storage.get().strip(),
                    "supabase_url": ent_url.get().strip(),
                    "supabase_key": ent_key.get().strip(),
                    "target_water_ml": int(ent_water.get().strip()),
                    "hydration_interval_min": int(ent_h_int.get().strip()),
                    "target_meals": int(ent_meals.get().strip()),
                    "meal_interval_min": int(ent_m_int.get().strip()),
                    "target_brushing": int(combo_brush.get().strip()),
                    "shower_frequency": combo_shower.get().strip(),
                    "sleep_start_hour": ss_h,
                    "sleep_start_minute": ss_m,
                    "sleep_end_hour": se_h,
                    "sleep_end_minute": se_m
                }

                config_manager.save_config(new_cfg)
                self.hud.reload_config()
                sfx.play_sfx("settings_updated")
                self.refresh_display()
                self.log_terminal("CONFIG OVERRIDE: Bio-parameters, 12h sleep windows, and targets committed.")
                messagebox.showinfo("Alterra PDA", "Biometric targets and system configuration saved successfully.")
                win.destroy()
            except ValueError as ve:
                messagebox.showerror("Format Error", f"Invalid time or numerical entry: {ve}")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to commit configuration: {e}")

        btn_commit = tk.Button(
            win, text="APPLY ALTERRA PROTOCOLS", font=("Consolas", 10, "bold"),
            bg="#0e2838", fg=CYAN_BRIGHT, activebackground=CYAN_DIM, activeforeground="#ffffff",
            bd=1, relief="ridge", pady=6, cursor="hand2", command=commit_settings
        )
        btn_commit.pack(fill="x", padx=16, pady=10)


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