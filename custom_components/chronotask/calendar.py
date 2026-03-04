from __future__ import annotations

import logging
from datetime import timedelta
from typing import Iterable

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.util import dt as dt_util

from .const import (
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

_LOGGER = logging.getLogger(__name__)


def _parse_hm(hm: str) -> tuple[int, int] | None:
    """Parsa una stringa HH:MM e restituisce (ore, minuti) o None se non valida."""
    try:
        parts = hm[:5].split(":")
        return int(parts[0]), int(parts[1])
    except (ValueError, IndexError, AttributeError):
        return None


def _build_event(rule: dict, base_date, now) -> CalendarEvent | None:
    """Costruisce un CalendarEvent dalla regola per il giorno base_date dato."""
    try:
        start_hm = _parse_hm(rule.get(CONF_START, ""))
        if not start_hm:
            return None

        sh, sm = start_hm
        start = base_date.replace(hour=sh, minute=sm, second=0, microsecond=0)
        end = start

        if rule.get(CONF_END):
            end_hm = _parse_hm(rule[CONF_END])
            if end_hm:
                eh, em = end_hm
                wd = base_date.weekday()
                eday = int(rule.get(CONF_END_DAY, rule[CONF_DAY]))
                delta_days = (eday - wd) % 7
                end = (base_date + timedelta(days=delta_days)).replace(
                    hour=eh, minute=em, second=0, microsecond=0
                )
                if end < start:
                    end = start

        return CalendarEvent(
            start=start,
            end=end,
            summary=rule.get(CONF_TITLE) or "Action",
            uid=f"{rule.get(ATTR_ID)}-{start.date()}",
        )
    except Exception:  # noqa: BLE001
        return None


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
        self._unsub = hass.bus.async_listen(f"{DOMAIN}_changed", self._on_changed)

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

    async def _on_changed(self, _) -> None:
        await self.async_update()
        self.async_write_ha_state()

    async def async_update(self) -> None:
        planner = self.hass.data[DOMAIN][self._entry_id]
        rules = [r for r in planner["storage"].list_rules() if r.get(CONF_ENABLED, True)]

        now = dt_util.now()
        look_ahead_end = now + timedelta(days=7)

        ongoing = None
        next_ev = None
        next_start = None

        cur = now
        while cur <= look_ahead_end:
            wd = cur.weekday()
            for r in rules:
                if int(r[CONF_DAY]) != wd:
                    continue
                ev = _build_event(r, cur, now)
                if not ev:
                    continue
                if ev.end < now and ev.start < now:
                    continue
                if ev.start <= now <= ev.end:
                    ongoing = ev
                    break
                if ev.start > now and (next_start is None or ev.start < next_start):
                    next_ev = ev
                    next_start = ev.start
            if ongoing:
                break
            cur += timedelta(days=1)

        self._event = ongoing or next_ev

    async def async_get_events(
        self, hass: HomeAssistant, start_date, end_date
    ) -> Iterable[CalendarEvent]:
        planner = self.hass.data[DOMAIN][self._entry_id]
        rules = [r for r in planner["storage"].list_rules() if r.get(CONF_ENABLED, True)]

        events: list[CalendarEvent] = []
        cur = dt_util.as_local(start_date)

        while cur <= end_date:
            wd = cur.weekday()
            for r in rules:
                if int(r[CONF_DAY]) != wd:
                    continue
                ev = _build_event(r, cur, None)
                if not ev:
                    continue
                if ev.end < start_date or ev.start > end_date:
                    continue
                events.append(ev)
            cur += timedelta(days=1)

        return events
