from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant

from .const import DOMAIN, PLANNER_SENSOR_SUFFIX


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities):
    planner = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([PlannerRulesSensor(entry.entry_id, planner['name'])], True)


class PlannerRulesSensor(SensorEntity):
    _attr_icon = "mdi:calendar-clock"
    _attr_should_poll = False

    def __init__(self, entry_id: str, name: str):
        self._entry_id = entry_id
        self._name = name
        self._attr_name = f"{name} Rules"
        self._attr_unique_id = f"{PLANNER_SENSOR_SUFFIX}_{entry_id}"
        self._capabilities = {"end_action": True, "tags": True}
        self._unsub = None
        self._attr_extra_state_attributes = {}

    async def async_added_to_hass(self):
        # Store reference for direct refresh from services
        try:
            self.hass.data[DOMAIN][self._entry_id]["sensor_entity"] = self
        except Exception:
            pass

        self._unsub = self.hass.bus.async_listen(f"{DOMAIN}_changed", self._on_changed)
        await self.async_update()
        self.async_write_ha_state()

    async def async_will_remove_from_hass(self):
        if self._unsub:
            self._unsub()
            self._unsub = None
        try:
            ctx = self.hass.data[DOMAIN].get(self._entry_id)
            if isinstance(ctx, dict) and ctx.get("sensor_entity") is self:
                ctx.pop("sensor_entity", None)
        except Exception:
            pass

    async def _on_changed(self, event):
        pid = event.data.get('planner_id') if event and event.data else None
        if pid and pid != self._entry_id:
            return
        await self.async_update()
        self.async_write_ha_state()

    async def async_update(self):
        storage = self.hass.data[DOMAIN][self._entry_id]['storage']
        self._attr_extra_state_attributes = {
            "rules": storage.list_rules(),
            "planner_id": self._entry_id,
            "capabilities": self._capabilities,
        }

    async def async_refresh_state(self):
        await self.async_update()
        self.async_write_ha_state()

    @property
    def native_value(self):
        return "ready"
