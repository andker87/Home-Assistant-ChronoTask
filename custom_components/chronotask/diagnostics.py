from __future__ import annotations

from homeassistant.components.diagnostics import async_redact_data

from .const import DOMAIN, INTEGRATION_VERSION

# Campi potenzialmente sensibili nei service_data (es. token, password, API key)
_REDACT_FIELDS = {"service_data", "end_service_data", "password", "token", "api_key", "access_token"}


async def async_get_config_entry_diagnostics(hass, entry):
    ctx = hass.data[DOMAIN][entry.entry_id]
    storage = ctx["storage"]
    rules = storage.list_rules()
    data = {
        "name": ctx["name"],
        "version": INTEGRATION_VERSION,
        "rules": rules,
        "active_rules": sum(1 for r in rules if r.get("enabled", True)),
        "holds": storage.list_holds(),
    }
    return async_redact_data(data, _REDACT_FIELDS)
