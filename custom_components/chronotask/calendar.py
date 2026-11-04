from __future__ import annotations

import logging
from datetime import timedelta
from typing import Iterable

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.util import dt as dt_util

from .const import (
    BUS_EVENT_CHANGED,
    DOMAIN,
    PLANNER_CALENDAR_SUFFIX,
    CONF_TITLE,
    CONF_DAY,
    CONF_START,
    CONF_END,
    CONF_ENABLED,
    ATTR_ID,
    CONF_END_DAY,
)
from .slots import effective_end_day, expand_rules, parse_hm

_LOGGER = logging.getLogger(__name__)


def _build_event(rule: dict, base_date) -> CalendarEvent | None:
    """CalendarEvent di una fascia (regola espansa) che inizia nel giorno base_date."""
    try:
        start_hm = parse_hm(rule.get(CONF_START))
        if not start_hm:
            return None

        sh, sm = start_hm
        start = base_date.replace(hour=sh, minute=sm, second=0, microsecond=0)
        end = start

        if rule.get(CONF_END):
            end_hm = parse_hm(rule[CONF_END])
            if end_hm:
                eh, em = end_hm
                eday = effective_end_day(
                    rule[CONF_DAY], rule.get(CONF_START), rule[CONF_END], rule.get(CONF_END_DAY)
                )
                delta_days = (eday - base_date.weekday()) % 7
                end = (base_date + timedelta(days=delta_days)).replace(
                    hour=eh, minute=em, second=0, microsecond=0
                )
                if end < start:
                    end = start

        return CalendarEvent(
            start=start,
            end=end,
            summary=rule.get(CONF_TITLE) or "Action",
            uid=f"{rule.get(ATTR_ID)}-{rule.get('_slot_index', 0)}-{start.date()}",
        )
    except Exception:  # noqa: BLE001
        return None


def _events_between(rules: list[dict], start, end) -> list[CalendarEvent]:
    """Eventi che si sovrappongono a [start, end], ordinati per inizio.

    Si parte da 7 giorni prima di 'start' (una fascia dura al massimo una
    settimana), così compaiono anche le fasce iniziate prima: notturne
    (22:00 -> 06:00) e di più giorni (lunedì -> giovedì)."""
    events: list[CalendarEvent] = []
    day = dt_util.as_local(start).replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=7)
    last = dt_util.as_local(end)
    while day <= last:
        weekday = day.weekday()
        for rule in rules:
            if int(rule[CONF_DAY]) != weekday:
                continue
            ev = _build_event(rule, day)
            if ev is None or ev.end < start or ev.start > end:
                continue
            events.append(ev)
        day += timedelta(days=1)
    events.sort(key=lambda e: e.start)
    return events


async def async_setup_entry(hass, entry, async_add_entities):
    planner = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [EntryPlannerCalendar(hass, entry.entry_id, planner["name"])], True
    )


class EntryPlannerCalendar(CalendarEntity):
    def __init__(self, hass: HomeAssistant, entry_id: str, name: str) -> None:
        self.hass = hass
        self._entry_id = entry_id
        self._name = name
        self._attr_name = name
        self._attr_unique_id = f"{PLANNER_CALENDAR_SUFFIX}_{entry_id}"
        self._event = None
        self._unsub = None

    async def async_added_to_hass(self) -> None:
        self._unsub = self.hass.bus.async_listen(BUS_EVENT_CHANGED, self._on_changed)

    async def async_will_remove_from_hass(self) -> None:
        if self._unsub:
            self._unsub()
            self._unsub = None

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry_id)},
            name=self._name,
            manufacturer="Custom",
            model="ChronoTask",
        )

    @property
    def event(self):
        return self._event

    async def _on_changed(self, event) -> None:
        pid = event.data.get("planner_id") if event and event.data else None
        if pid and pid != self._entry_id:
            return
        await self.async_update()
        self.async_write_ha_state()

    def _enabled_rules(self) -> list[dict]:
        storage = self.hass.data[DOMAIN][self._entry_id]["storage"]
        return [r for r in expand_rules(storage.list_rules()) if r.get(CONF_ENABLED, True)]

    async def async_update(self) -> None:
        now = dt_util.now()
        events = _events_between(self._enabled_rules(), now, now + timedelta(days=7))
        ongoing = next((e for e in events if e.start <= now <= e.end), None)
        upcoming = next((e for e in events if e.start > now), None)
        self._event = ongoing or upcoming

    async def async_get_events(
        self, hass: HomeAssistant, start_date, end_date
    ) -> Iterable[CalendarEvent]:
        return _events_between(self._enabled_rules(), start_date, end_date)
