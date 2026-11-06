import zoneinfo
import json
import urllib.request
from datetime import datetime, timezone
from config_manager import load_config, DEFAULT_CONFIG

class TimeSync:
    def __init__(self):
        cfg = load_config() or DEFAULT_CONFIG
        tz_str = cfg.get("timezone", "UTC")
        
        # Safe zoneinfo lookup with local system fallback if tzdata is absent
        try:
            self.target_tz = zoneinfo.ZoneInfo(tz_str)
        except (zoneinfo.ZoneInfoNotFoundError, Exception):
            local_tz = datetime.now().astimezone().tzinfo
            self.target_tz = local_tz if local_tz else timezone.utc

        self.offset_seconds = 0.0
        self.is_synced = False
        self.sync_time()

    def sync_time(self):
        """Attempts to sync with a public time API; falls back to system clock."""
        try:
            req = urllib.request.Request(
                "http://worldtimeapi.org/api/ip",
                headers={"User-Agent": "Alterra-PDA/1.0"}
            )
            with urllib.request.urlopen(req, timeout=3) as resp:
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

# Instantiate singleton after definition
time_manager = TimeSync()