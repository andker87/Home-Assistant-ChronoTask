from __future__ import annotations

from datetime import datetime, timedelta
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
    def __init__(self, hass: HomeAssistant, storage) -> None:
        self.hass = hass
        self.storage = storage
        self._unsubs: dict[str, callable] = {}

    async def async_reschedule_all(self) -> None:
        """Cancella tutti i timer esistenti e ripianifica tutte le regole attive."""
        for unsub in list(self._unsubs.values()):
            try:
                unsub()
            except Exception:  # noqa: BLE001
                pass
        self._unsubs.clear()

        for rule in self.storage.list_rules():
            self._schedule_start(rule)
            self._schedule_end(rule)

    def _next_local_dt(self, weekday: int, hm: str) -> datetime | None:
        """Calcola il prossimo datetime locale per il giorno/orario settimanale dato."""
        now = dt_util.now()
        try:
            hh, mm = map(int, hm.split(":"))
        except (ValueError, AttributeError):
            _LOGGER.warning("ChronoTask: orario non valido '%s'", hm)
            return None

        days_ahead = (weekday - now.weekday()) % 7
        cand = now.replace(hour=hh, minute=mm, second=0, microsecond=0) + timedelta(days=days_ahead)
        if cand <= now:
            cand += timedelta(days=7)
        return cand

    def _schedule_start(self, rule: dict) -> None:
        if not rule.get(CONF_ENABLED, True):
            return
        if not rule.get(CONF_SERVICE) or not rule.get(CONF_START):
            return

        rule_id = rule.get(ATTR_ID)
        key = f"{rule_id}:start"
        next_local = self._next_local_dt(int(rule[CONF_DAY]), rule[CONF_START])
        if not next_local:
            return
        next_utc = dt_util.as_utc(next_local)

        # Cattura una copia snapshot della regola per evitare riferimenti stale
        rule_snapshot = dict(rule)

        @callback
        def _fire(_now):
            self.hass.async_create_task(
                self._execute_then_resched(rule_snapshot, part="start")
            )

        self._unsubs[key] = async_track_point_in_utc_time(self.hass, _fire, next_utc)
        _LOGGER.debug(
            "ChronoTask: pianificato START '%s' per %s",
            rule.get("title", rule_id), next_local.strftime("%a %H:%M"),
        )

    def _schedule_end(self, rule: dict) -> None:
        if not rule.get(CONF_ENABLED, True):
            return
        if not rule.get(CONF_END) or not rule.get(CONF_END_SERVICE):
            return

        rule_id = rule.get(ATTR_ID)
        end_day = int(rule.get(CONF_END_DAY, rule.get(CONF_DAY)))
        key = f"{rule_id}:end"
        next_local = self._next_local_dt(end_day, rule[CONF_END])
        if not next_local:
            return
        next_utc = dt_util.as_utc(next_local)

        rule_snapshot = dict(rule)

        @callback
        def _fire(_now):
            self.hass.async_create_task(
                self._execute_then_resched(rule_snapshot, part="end")
            )

        self._unsubs[key] = async_track_point_in_utc_time(self.hass, _fire, next_utc)
        _LOGGER.debug(
            "ChronoTask: pianificato END '%s' per %s",
            rule.get("title", rule_id), next_local.strftime("%a %H:%M"),
        )

    async def _execute_then_resched(self, rule: dict, part: str) -> None:
        """Esegue il servizio HA associato alla regola e ripianifica il prossimo trigger."""
        try:
            if part == "start":
                service_str = rule[CONF_SERVICE]
                data = rule.get(CONF_SERVICE_DATA) or {}
            else:
                service_str = rule.get(CONF_END_SERVICE)
                data = rule.get(CONF_END_SERVICE_DATA) or {}

            if not service_str or "." not in service_str:
                _LOGGER.error(
                    "ChronoTask: service non valido per regola '%s' (%s): '%s'",
                    rule.get(ATTR_ID), part, service_str,
                )
                return

            domain, service = service_str.split(".", 1)
            _LOGGER.info(
                "ChronoTask [%s] '%s': chiamo %s.%s con %s",
                part, rule.get("title", rule.get(ATTR_ID)), domain, service, data,
            )
            await self.hass.services.async_call(domain, service, data, blocking=False)

        except Exception as err:  # noqa: BLE001
            _LOGGER.error(
                "ChronoTask: errore esecuzione regola '%s' (%s): %s",
                rule.get(ATTR_ID), part, err,
            )
        finally:
            # Ri-fetch la regola da storage per avere i dati aggiornati alla prossima esecuzione
            fresh_rules = self.storage.list_rules()
            fresh = next(
                (r for r in fresh_rules if r.get(ATTR_ID) == rule.get(ATTR_ID)),
                None,
            )
            if fresh:
                if part == "start":
                    self._schedule_start(fresh)
                else:
                    self._schedule_end(fresh)
