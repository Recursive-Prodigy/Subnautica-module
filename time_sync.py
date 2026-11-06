import os
import json
import zoneinfo
import threading
import urllib.request
from datetime import datetime, timezone
from config_manager import load_config, DEFAULT_CONFIG

class TimeSync:
    def __init__(self):
        self.offset_seconds = 0.0
        self.is_synced = False
        self._cached_tz_name = None
        self._target_tz = timezone.utc
        
        self.reload_timezone()
        threading.Thread(target=self.sync_time, daemon=True).start()

    def reload_timezone(self):
        """Reloads timezone setting from config with machine local fallback."""
        cfg = load_config() or DEFAULT_CONFIG
        tz_str = cfg.get("timezone", "UTC")

        if tz_str == self._cached_tz_name and self._target_tz:
            return

        try:
            self._target_tz = zoneinfo.ZoneInfo(tz_str)
            self._cached_tz_name = tz_str
            return
        except (zoneinfo.ZoneInfoNotFoundError, Exception):
            pass

        try:
            sys_tz = datetime.now().astimezone().tzinfo
            if isinstance(sys_tz, zoneinfo.ZoneInfo):
                self._target_tz = sys_tz
            else:
                local_name = getattr(sys_tz, "key", None)
                self._target_tz = zoneinfo.ZoneInfo(local_name) if local_name else (sys_tz or timezone.utc)
            self._cached_tz_name = tz_str
            return
        except Exception:
            pass

        self._target_tz = timezone.utc
        self._cached_tz_name = "UTC"

    @property
    def target_tz(self):
        self.reload_timezone()
        return self._target_tz

    def sync_time(self):
        try:
            req = urllib.request.Request(
                "http://worldtimeapi.org/api/ip",
                headers={"User-Agent": "Alterra-PDA/1.0"}
            )
            with urllib.request.urlopen(req, timeout=4) as resp:
                data = json.loads(resp.read().decode())
                network_utc = datetime.fromisoformat(data["utc_datetime"]).timestamp()
                local_utc = datetime.now(timezone.utc).timestamp()
                self.offset_seconds = network_utc - local_utc
                self.is_synced = True
        except Exception:
            self.offset_seconds = 0.0
            self.is_synced = False

    def now(self) -> datetime:
        utc_ts = datetime.now(timezone.utc).timestamp() + self.offset_seconds
        return datetime.fromtimestamp(utc_ts, tz=timezone.utc).astimezone(self.target_tz)

    def now_utc_iso(self) -> str:
        utc_ts = datetime.now(timezone.utc).timestamp() + self.offset_seconds
        dt_utc = datetime.fromtimestamp(utc_ts, tz=timezone.utc)
        return dt_utc.strftime("%Y-%m-%dT%H:%M:%SZ")

    def format_dmy(self, iso_str: str, include_time: bool = True) -> str:
        """Converts database timestamps to DD/MM/YYYY 12-Hour AM/PM format."""
        if not iso_str:
            return "--/--/----"
        ts_str = str(iso_str).strip()

        try:
            if "Z" in ts_str or "+" in ts_str[10:] or ("-" in ts_str[10:] and "T" in ts_str):
                clean = ts_str.replace("Z", "+00:00")
                dt = datetime.fromisoformat(clean)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                dt_local = dt.astimezone(self.target_tz)
            else:
                dt_local = None
                for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%d/%m/%Y %H:%M", "%Y/%m/%d %H:%M"):
                    try:
                        dt_local = datetime.strptime(ts_str[:19], fmt)
                        break
                    except Exception:
                        pass
                if not dt_local:
                    return ts_str[:19]

            if include_time:
                return dt_local.strftime("%d/%m/%Y %I:%M %p")
            return dt_local.strftime("%d/%m/%Y")
        except Exception:
            return ts_str[:19]


time_manager = TimeSync()

# Top-level direct delegates
def get_current_iso() -> str:
    return time_manager.now_utc_iso()

def format_date_dmy(iso_str: str, include_time: bool = True) -> str:
    return time_manager.format_dmy(iso_str, include_time=include_time)

def format_dmy(iso_str: str, include_time: bool = True) -> str:
    return time_manager.format_dmy(iso_str, include_time=include_time)