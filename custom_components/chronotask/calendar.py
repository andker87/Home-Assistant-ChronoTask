from __future__ import annotations

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


async def async_setup_entry(hass, entry, async_add_entities):
    planner = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([EntryPlannerCalendar(hass, entry.entry_id, planner['name'])], True)


class EntryPlannerCalendar(CalendarEntity):
    def __init__(self, hass: HomeAssistant, entry_id: str, name: str):
        self.hass = hass
        self._entry_id = entry_id
        self._name = name
        self._attr_name = f"{name}"
        self._attr_unique_id = f"{PLANNER_CALENDAR_SUFFIX}_{entry_id}"
        self._event = None
        self._unsub = hass.bus.async_listen(f"{DOMAIN}_changed", self._on_changed)

    async def async_will_remove_from_hass(self):
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

    async def _on_changed(self, _):
        await self.async_update()
        self.async_write_ha_state()

    async def async_update(self) -> None:
        planner = self.hass.data[DOMAIN][self._entry_id]
        storage = planner['storage']
        rules = [r for r in storage.list_rules() if r.get(CONF_ENABLED, True)]
        now = dt_util.now()
        look_ahead_end = now + timedelta(days=7)
        ongoing = None
        next_ev = None
        next_start = None
        cur = now
        while cur <= look_ahead_end:
            wd = cur.weekday()
            for r in rules:
                try:
                    if int(r[CONF_DAY]) != wd:
                        continue
                    sh, sm = [int(x) for x in (r[CONF_START][:5]).split(":", 1)]
                    s = cur.replace(hour=sh, minute=sm, second=0, microsecond=0)
                    e = s
                    if r.get(CONF_END):
                        eh, em = [int(x) for x in (r[CONF_END][:5]).split(":", 1)]
                        eday = int(r.get(CONF_END_DAY, r[CONF_DAY]))
                        delta_days = (eday - wd) % 7
                        e = (cur + timedelta(days=delta_days)).replace(hour=eh, minute=em, second=0, microsecond=0)
                        if e < s:
                            e = s
                    if e < now and s < now:
                        continue
                    if s <= now <= e:
                        ongoing = CalendarEvent(start=s, end=e, summary=r.get(CONF_TITLE) or "Action", uid=f"{r.get(ATTR_ID)}-{s.date()}")
                        break
                    if s > now and (next_start is None or s < next_start):
                        next_ev = CalendarEvent(start=s, end=e, summary=r.get(CONF_TITLE) or "Action", uid=f"{r.get(ATTR_ID)}-{s.date()}")
                        next_start = s
                except Exception:
                    continue
            if ongoing:
                break
            cur += timedelta(days=1)
        self._event = ongoing or next_ev

    async def async_get_events(self, hass, start_date, end_date) -> Iterable[CalendarEvent]:
        planner = self.hass.data[DOMAIN][self._entry_id]
        storage = planner['storage']
        events = []
        rules = [r for r in storage.list_rules() if r.get(CONF_ENABLED, True)]
        cur = dt_util.as_local(start_date)
        while cur <= end_date:
            wd = cur.weekday()
            for r in rules:
                try:
                    if int(r[CONF_DAY]) != wd:
                        continue
                    sh, sm = [int(x) for x in (r[CONF_START][:5]).split(":", 1)]
                    start = cur.replace(hour=sh, minute=sm, second=0, microsecond=0)
                    end = start
                    if r.get(CONF_END):
                        eh, em = [int(x) for x in (r[CONF_END][:5]).split(":", 1)]
                        eday = int(r.get(CONF_END_DAY, r[CONF_DAY]))
                        delta_days = (eday - wd) % 7
                        end = (cur + timedelta(days=delta_days)).replace(hour=eh, minute=em, second=0, microsecond=0)
                        if end < start:
                            end = start
                    if end < start_date or start > end_date:
                        continue
                    events.append(CalendarEvent(start=start, end=end, summary=r.get(CONF_TITLE), uid=f"{r.get(ATTR_ID)}-{start.date()}"))
                except Exception:
                    continue
            cur += timedelta(days=1)
        return events
