from __future__ import annotations

from pathlib import Path
import json
from typing import Final

# Versione letta dal manifest (così non la duplichi)
_MANIFEST_PATH = Path(__file__).parent / "manifest.json"
with _MANIFEST_PATH.open(encoding="utf-8") as f:
    INTEGRATION_VERSION: Final[str] = json.load(f).get("version", "0.0.0")

# URL base pubblico (pulito)
URL_BASE = "/local/chronotask"

# Moduli JS da registrare in Lovelace Resources

JSMODULES = [
    {"filename": "chronotask-tag-manager.js", "version": "0.1"},
    {"filename": "chronotask-weekly-card.js", "version": "0.1"},
]



DOMAIN = "chronotask"
PLANNER_CALENDAR_SUFFIX = "chronotask"
PLANNER_SENSOR_SUFFIX = "chronotask_rules"
STORAGE_KEY_BASE = "chronotask.rules"
STORAGE_VERSION = 1

# Config fields
CONF_NAME = "name"

# Rule fields (start)
CONF_TITLE = "title"
CONF_DAY = "day"          # 0=Mon..6=Sun
CONF_START = "start"      # HH:MM
CONF_SERVICE = "service"
CONF_SERVICE_DATA = "service_data"

# Visual end (duration)
CONF_END = "end"          # HH:MM (optional)

# End action (native)
CONF_END_DAY = "end_day"   # optional weekday for end action, 0..6
CONF_END_SERVICE = "end_service"
CONF_END_SERVICE_DATA = "end_service_data"

# Tags
CONF_TAGS = "tags"         # list[str]

# Common
CONF_ENABLED = "enabled"
CONF_COLOR = "color"
CONF_ICON = "icon"

ATTR_ID = "id"
ATTR_PLANNER_ID = "planner_id"

# Services
SERVICE_ADD = "add_rule"
SERVICE_UPDATE = "update_rule"
SERVICE_REMOVE = "remove_rule"
SERVICE_CLEAR = "clear_rules"
SERVICE_RUN_NOW = "run_rule_now"
SERVICE_RESCHEDULE = "reschedule_all"
SERVICE_ENABLE_TAG = "enable_tag"
SERVICE_DISABLE_TAG = "disable_tag"

BUS_EVENT_CHANGED = DOMAIN + "_changed"


