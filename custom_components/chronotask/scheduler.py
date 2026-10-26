from __future__ import annotations

from datetime import datetime, timedelta
import logging

from homeassistant.core import Context, HomeAssistant, callback
from homeassistant.helpers.event import async_track_point_in_utc_time
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    EVENT_ACTION,
    CONF_TITLE,
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
from .slots import (
    all_target_entities,
    current_event_for_entity,
    effective_end_day,
    event_action,
    expand_rules,
    restrict_entities,
    target_entities,
)

_LOGGER = logging.getLogger(__name__)


class WeeklyScheduler:
    def __init__(self, hass: HomeAssistant, storage, planner_id: str | None = None) -> None:
        self.hass = hass
        self.storage = storage
        self.planner_id = planner_id
        self._unsubs: dict[str, callable] = {}
        # Timer di scadenza delle pause: separati da quelli delle regole, così
        # async_reschedule_all() non li tocca.
        self._hold_unsubs: dict[str, callable] = {}

    async def async_stop(self) -> None:
        """Cancella tutti i timer (regole e pause): usato allo scaricamento."""
        for unsub in list(self._unsubs.values()) + list(self._hold_unsubs.values()):
            try:
                unsub()
            except Exception:  # noqa: BLE001
                pass
        self._unsubs.clear()
        self._hold_unsubs.clear()

    async def async_reschedule_all(self) -> None:
        """Cancella tutti i timer esistenti e ripianifica tutte le regole attive."""
        for unsub in list(self._unsubs.values()):
            try:
                unsub()
            except Exception:  # noqa: BLE001
                pass
        self._unsubs.clear()

        # expand_rules "appiattisce" ogni (regola, slot) in un dict con la
        # stessa forma di prima (un day/start/end/end_day) più _slot_index,
        # così _schedule_start/_schedule_end restano quasi invariati.
        for rule in expand_rules(self.storage.list_rules()):
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
        slot_idx = rule.get("_slot_index", 0)
        key = f"{rule_id}:{slot_idx}:start"
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
        slot_idx = rule.get("_slot_index", 0)
        end_day = effective_end_day(
            rule[CONF_DAY], rule.get(CONF_START), rule[CONF_END], rule.get(CONF_END_DAY)
        )
        key = f"{rule_id}:{slot_idx}:end"
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
        """Esegue il servizio HA associato alla regola (rispettando le pause) e
        ripianifica il prossimo trigger."""
        try:
            await self._run_action(rule, part)
        except Exception as err:  # noqa: BLE001
            _LOGGER.error(
                "ChronoTask: errore esecuzione regola '%s' (%s): %s",
                rule.get(ATTR_ID), part, err,
            )
        finally:
            # Ri-fetch la regola da storage per avere i dati aggiornati alla
            # prossima esecuzione, e ripianifica solo LO SLOT che è scattato
            # (le altre fasce della stessa regola hanno i loro timer separati).
            # Se lo slot non esiste più (rimosso/riordinato nel frattempo) non
            # facciamo nulla: qualunque modifica alla regola passa comunque
            # da async_reschedule_all(), che si autoripara.
            slot_idx = rule.get("_slot_index", 0)
            fresh_rules = expand_rules(self.storage.list_rules())
            fresh = next(
                (
                    r for r in fresh_rules
                    if r.get(ATTR_ID) == rule.get(ATTR_ID) and r.get("_slot_index") == slot_idx
                ),
                None,
            )
            if fresh:
                if part == "start":
                    self._schedule_start(fresh)
                else:
                    self._schedule_end(fresh)

    # ------------------------------------------------------------------
    # Esecuzione di un'azione, rispettando le pause
    # ------------------------------------------------------------------

    async def _refresh_state(self) -> None:
        """Aggiorna il sensore (attributo 'entities') e avvisa l'UI.

        Si attende il sensore PRIMA di chiamare un servizio: così quando
        l'entità cambia stato l'attributo 'entities' mostra già lo stato atteso
        nuovo, e un'automazione che confronta stato reale e atteso non scambia
        l'avvio di una fascia per un cambio manuale."""
        try:
            ctx = self.hass.data.get(DOMAIN, {}).get(self.planner_id) if self.planner_id else None
            sensor = ctx.get("sensor_entity") if isinstance(ctx, dict) else None
            if sensor is not None:
                await sensor.async_refresh_state()
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("ChronoTask: aggiornamento sensore fallito: %s", err)
        self.hass.bus.async_fire(f"{DOMAIN}_changed", {"planner_id": self.planner_id})

    async def _run_action(
        self,
        rule: dict,
        part: str,
        only_entities: list[str] | None = None,
        label: str | None = None,
    ) -> tuple[bool, list[str]]:
        """Chiama il servizio di 'start' o 'end' di una regola.

        - only_entities None (evento pianificato): toglie le entità in pausa; se
          non ne resta nessuna il servizio non viene chiamato.
        - only_entities dato (resume/resync): restringe l'azione a quelle entità.

        Restituisce (eseguita, entità effettivamente interessate)."""
        service_str, data = event_action(rule, part)
        data = dict(data or {})
        if not service_str or "." not in service_str:
            _LOGGER.error(
                "ChronoTask: service non valido per regola '%s' (%s): '%s'",
                rule.get(ATTR_ID), part, service_str,
            )
            return False, []

        targets = target_entities(data)
        title = rule.get(CONF_TITLE, rule.get(ATTR_ID))
        if only_entities is not None:
            entity_ids = [e for e in only_entities if e in targets]
            if not entity_ids:
                return False, []
            data = restrict_entities(data, entity_ids)
        elif targets:
            held = self.storage.list_holds()
            entity_ids = [e for e in targets if e not in held]
            if not entity_ids:
                await self._refresh_state()
                _LOGGER.info(
                    "ChronoTask [%s] '%s': saltata, entità in pausa: %s",
                    part, title, ", ".join(targets),
                )
                return False, []
            if len(entity_ids) != len(targets):
                data = restrict_entities(data, entity_ids)
                _LOGGER.info(
                    "ChronoTask [%s] '%s': in pausa e quindi escluse: %s",
                    part, title, ", ".join(e for e in targets if e not in entity_ids),
                )
        else:
            entity_ids = []

        domain, service = service_str.split(".", 1)
        await self._refresh_state()
        context = Context()
        self.hass.bus.async_fire(
            EVENT_ACTION,
            {
                "planner_id": self.planner_id,
                "rule_id": rule.get(ATTR_ID),
                "title": rule.get(CONF_TITLE),
                "part": label or part,
                "entity_ids": entity_ids,
                "context_id": context.id,
            },
            context=context,
        )
        _LOGGER.info(
            "ChronoTask [%s] '%s': chiamo %s.%s con %s", label or part, title, domain, service, data,
        )
        await self.hass.services.async_call(
            domain, service, data, blocking=False, context=context
        )
        return True, entity_ids

    # ------------------------------------------------------------------
    # Stato corrente, pause (hold), resume e resync
    # ------------------------------------------------------------------

    def _entity_unavailable(self, entity_id: str) -> bool:
        state = self.hass.states.get(entity_id)
        return state is None or state.state in ("unavailable", "unknown")

    async def async_apply_current(self, entity_ids: list[str], label: str) -> dict[str, dict]:
        """Applica a ciascuna entità l'azione dello stato corrente (ultimo evento
        passato tra le regole abilitate). Salta le entità in pausa e quelle
        unavailable/unknown (solo un warning, nessun retry).

        Restituisce {entity_id: {"applied": "start"|"end"|None, "rule": titolo|None}}.
        'rule' è la regola dello stato corrente anche se non c'era nulla da applicare."""
        now = dt_util.now()
        rules = self.storage.list_rules()
        held = self.storage.list_holds()
        result: dict[str, dict] = {}
        groups: dict[tuple, tuple[dict, str, list[str]]] = {}
        for eid in entity_ids:
            ev = current_event_for_entity(rules, eid, now)
            if ev is None:
                result[eid] = {"applied": None, "rule": None}
                continue
            rule, part = ev["rule"], ev["part"]
            result[eid] = {"applied": None, "rule": rule.get(CONF_TITLE)}
            if eid in held:
                continue
            if self._entity_unavailable(eid):
                _LOGGER.warning(
                    "ChronoTask: %s non applicato a %s: entità unavailable/unknown",
                    label, eid,
                )
                continue
            groups.setdefault((rule.get(ATTR_ID), part), (rule, part, []))[2].append(eid)
        for rule, part, eids in groups.values():
            try:
                executed, done = await self._run_action(rule, part, only_entities=eids, label=label)
            except Exception as err:  # noqa: BLE001
                _LOGGER.error("ChronoTask: errore applicando lo stato a %s: %s", eids, err)
                continue
            if executed:
                for eid in done:
                    result[eid]["applied"] = part
        return result

    def _cancel_hold_timer(self, entity_id: str) -> None:
        unsub = self._hold_unsubs.pop(entity_id, None)
        if unsub:
            try:
                unsub()
            except Exception:  # noqa: BLE001
                pass

    def _schedule_hold_expiry(self, entity_id: str, until: datetime) -> None:
        self._cancel_hold_timer(entity_id)

        @callback
        def _fire(_now):
            self._hold_unsubs.pop(entity_id, None)
            self.hass.async_create_task(self._on_hold_expired(entity_id))

        self._hold_unsubs[entity_id] = async_track_point_in_utc_time(
            self.hass, _fire, dt_util.as_utc(until)
        )

    @staticmethod
    def _parse_until(value) -> datetime | None:
        if not value:
            return None
        parsed = dt_util.parse_datetime(str(value))
        return dt_util.as_local(parsed) if parsed else None

    async def _on_hold_expired(self, entity_id: str) -> None:
        hold = self.storage.get_hold(entity_id)
        if not hold:
            return
        _LOGGER.info("ChronoTask: pausa scaduta per %s: riprendo la programmazione", entity_id)
        await self.async_resume([entity_id], apply=True)

    async def async_setup_holds(self) -> None:
        """All'avvio: le pause già scadute si tolgono SENZA applicare nulla (le
        entità spesso non sono ancora disponibili: ci pensa chronotask.resync
        da un'automazione); quelle future riprendono il loro timer."""
        now = dt_util.now()
        changed = False
        for eid, hold in self.storage.list_holds().items():
            raw_until = hold.get("until")
            until = self._parse_until(raw_until)
            if raw_until and (until is None or until <= now):
                self.storage.remove_hold(eid)
                changed = True
                _LOGGER.info("ChronoTask: pausa di %s scaduta durante lo spegnimento: rimossa", eid)
            elif until:
                self._schedule_hold_expiry(eid, until)
        if changed:
            await self.storage.async_save()

    async def async_hold(self, entity_ids: list[str], until: datetime | None, reason: str | None) -> None:
        """Mette in pausa le entità (sostituisce una pausa già presente)."""
        now = dt_util.now()
        for eid in entity_ids:
            self.storage.set_hold(eid, {
                "until": until.isoformat() if until else None,
                "reason": reason,
                "since": now.isoformat(),
            })
            if until:
                self._schedule_hold_expiry(eid, until)
            else:
                self._cancel_hold_timer(eid)
        await self.storage.async_save()
        await self._refresh_state()

    async def async_resume(self, entity_ids: list[str], apply: bool = True) -> dict[str, dict]:
        """Toglie la pausa e, se apply, applica lo stato corrente."""
        for eid in entity_ids:
            self._cancel_hold_timer(eid)
            self.storage.remove_hold(eid)
        await self.storage.async_save()
        await self._refresh_state()
        if not apply:
            return {eid: {"applied": None, "rule": None} for eid in entity_ids}
        return await self.async_apply_current(entity_ids, "resume")

    async def async_resync(self, entity_ids: list[str] | None = None) -> dict[str, dict]:
        """Applica lo stato corrente alle entità non in pausa (tutte le entità
        bersaglio del planner se entity_ids è None)."""
        if entity_ids is None:
            entity_ids = all_target_entities(self.storage.list_rules())
        return await self.async_apply_current(entity_ids, "resync")
