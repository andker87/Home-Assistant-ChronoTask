from __future__ import annotations

from datetime import timedelta
from typing import Optional
import logging

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_point_in_utc_time
from homeassistant.util import dt as dt_util

from .const import (
    CONF_DAY,
    CONF_START,
    CONF_SERVICE,
    CONF_SERVICE_DATA,
    CONF_ENABLED,
    ATTR_ID,
    CONF_END,
    CONF_END_DAY,
    CONF_END_SERVICE,
    CONF_END_SERVICE_DATA,
)

_LOGGER = logging.getLogger(__name__)


class WeeklyScheduler:
    def __init__(self, hass: HomeAssistant, storage):
        self.hass = hass
        self.storage = storage
        self._unsubs: dict[str, callable] = {}

    async def async_reschedule_all(self):
        for u in list(self._unsubs.values()):
            try:
                u()
            except Exception:
                pass
        self._unsubs.clear()
        for rule in self.storage.list_rules():
            self._schedule_start(rule)
            self._schedule_end(rule)

    def _next_local_dt(self, weekday: int, hm: str) -> Optional[dt_util.datetime]:
        now = dt_util.now()
        try:
            hh, mm = map(int, hm.split(":"))
        except Exception:
            return None
        days_ahead = (weekday - now.weekday()) % 7
        cand = now.replace(hour=hh, minute=mm, second=0, microsecond=0) + timedelta(days=days_ahead)
        if cand <= now:
            cand += timedelta(days=7)
        return cand

    def _schedule_start(self, rule: dict):
        if not rule.get(CONF_ENABLED, True):
            return
        if not rule.get(CONF_SERVICE) or not rule.get(CONF_START):
            return
        key = f"{rule.get(ATTR_ID)}:start"
        next_local = self._next_local_dt(int(rule[CONF_DAY]), rule[CONF_START])
        if not next_local:
            return
        next_utc = dt_util.as_utc(next_local)

        @callback
        def _fire(_):
            self.hass.async_create_task(self._execute_then_resched(rule, part="start"))

        self._unsubs[key] = async_track_point_in_utc_time(self.hass, _fire, next_utc)

    def _schedule_end(self, rule: dict):
        if not rule.get(CONF_ENABLED, True):
            return
        if not rule.get(CONF_END) or not rule.get(CONF_END_SERVICE):
            return
        end_day = int(rule.get(CONF_END_DAY, rule.get(CONF_DAY)))
        key = f"{rule.get(ATTR_ID)}:end"
        next_local = self._next_local_dt(end_day, rule[CONF_END])
        if not next_local:
            return
        next_utc = dt_util.as_utc(next_local)

        @callback
        def _fire(_):
            self.hass.async_create_task(self._execute_then_resched(rule, part="end"))

        self._unsubs[key] = async_track_point_in_utc_time(self.hass, _fire, next_utc)

    async def _execute_then_resched(self, rule: dict, part: str):
        try:
            if part == "start":
                service_str = rule[CONF_SERVICE]
                data = rule.get(CONF_SERVICE_DATA) or {}
            else:
                service_str = rule.get(CONF_END_SERVICE)
                data = rule.get(CONF_END_SERVICE_DATA) or {}
            if not service_str or "." not in service_str:
                _LOGGER.error("Service non valido per rule %s (%s)", rule.get(ATTR_ID), part)
                return
            domain, service = service_str.split('.', 1)
            _LOGGER.info("ChronoTask %s: %s.%s %s", part, domain, service, data)
            await self.hass.services.async_call(domain, service, data, blocking=False)
        finally:
            if part == "start":
                self._schedule_start(rule)
            else:
                self._schedule_end(rule)
