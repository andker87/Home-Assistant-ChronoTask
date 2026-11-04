from __future__ import annotations

import logging

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_point_in_utc_time
from homeassistant.util import dt as dt_util

from .const import BUS_EVENT_CHANGED, DOMAIN, PLANNER_SENSOR_SUFFIX
from .slots import build_entities_view

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities):
    planner = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([PlannerRulesSensor(entry.entry_id, planner["name"])], True)


class PlannerRulesSensor(SensorEntity):
    _attr_icon = "mdi:calendar-clock"
    _attr_should_poll = False
    _attr_native_unit_of_measurement = "regole"
    # Attributi grandi e che cambiano spesso: non servono nello storico, le
    # automazioni leggono lo stato attuale.
    _unrecorded_attributes = frozenset({"rules", "entities"})

    def __init__(self, entry_id: str, name: str) -> None:
        self._entry_id = entry_id
        self._name = name
        self._attr_name = f"{name} Rules"
        self._attr_unique_id = f"{PLANNER_SENSOR_SUFFIX}_{entry_id}"
        self._capabilities = {"end_action": True, "tags": True, "multi_slot": True, "hold": True}
        self._unsub = None
        self._unsub_next = None
        self._attr_extra_state_attributes = {}

    async def async_added_to_hass(self) -> None:
        # Registra riferimento per refresh diretto dai servizi
        try:
            self.hass.data[DOMAIN][self._entry_id]["sensor_entity"] = self
        except Exception:  # noqa: BLE001
            pass

        self._unsub = self.hass.bus.async_listen(BUS_EVENT_CHANGED, self._on_changed)
        await self.async_update()
        self.async_write_ha_state()

    async def async_will_remove_from_hass(self) -> None:
        if self._unsub:
            self._unsub()
            self._unsub = None
        if self._unsub_next:
            self._unsub_next()
            self._unsub_next = None
        try:
            ctx = self.hass.data[DOMAIN].get(self._entry_id)
            if isinstance(ctx, dict) and ctx.get("sensor_entity") is self:
                ctx.pop("sensor_entity", None)
        except Exception:  # noqa: BLE001
            pass

    async def _on_changed(self, event) -> None:
        data = event.data if event and event.data else {}
        pid = data.get("planner_id")
        if pid and pid != self._entry_id:
            return
        if data.get("sensor_refreshed"):
            return  # chi ha generato l'evento ha già aggiornato il sensore
        await self.async_update()
        self.async_write_ha_state()

    async def async_update(self) -> None:
        try:
            storage = self.hass.data[DOMAIN][self._entry_id]["storage"]
            rules = storage.list_rules()
            now = dt_util.now()
            entities = build_entities_view(rules, storage.list_holds(), now)
            self._schedule_next_refresh(entities)
            self._attr_extra_state_attributes = {
                "rules": rules,
                "entities": entities,
                "planner_id": self._entry_id,
                "capabilities": self._capabilities,
                "total_rules": len(rules),
                "active_rules": sum(1 for r in rules if r.get("enabled", True)),
            }
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("ChronoTask: errore aggiornamento sensore: %s", err)

    def _schedule_next_refresh(self, entities: dict) -> None:
        """Riaggiorna 'entities' al prossimo cambio di stato di qualunque entità,
        anche quando non scatta nessun servizio (es. fine fascia senza
        end_service): così 'scheduled' non resta indietro."""
        if self._unsub_next:
            self._unsub_next()
            self._unsub_next = None
        if getattr(self, "hass", None) is None:
            return
        times = []
        for entry in entities.values():
            parsed = dt_util.parse_datetime(entry["next_change"]) if entry.get("next_change") else None
            if parsed:
                times.append(parsed)
        if not times:
            return

        @callback
        def _fire(_now):
            self._unsub_next = None
            self.hass.async_create_task(self.async_refresh_state())

        self._unsub_next = async_track_point_in_utc_time(self.hass, _fire, dt_util.as_utc(min(times)))

    async def async_refresh_state(self) -> None:
        await self.async_update()
        self.async_write_ha_state()

    @property
    def native_value(self) -> int:
        """Restituisce il numero di regole attive — utile per automazioni."""
        rules = self._attr_extra_state_attributes.get("rules", [])
        return sum(1 for r in rules if r.get("enabled", True))
