from __future__ import annotations

from homeassistant.components.diagnostics import async_redact_data

from .const import DOMAIN


async def async_get_config_entry_diagnostics(hass, entry):
    ctx = hass.data[DOMAIN][entry.entry_id]
    data = {"rules": ctx['storage'].list_rules(), "name": ctx['name']}
    return async_redact_data(data, [])
