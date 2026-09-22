from __future__ import annotations

import uuid
import copy
import logging
import re

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
import homeassistant.helpers.config_validation as cv

from .const import (
    DOMAIN,
    SERVICE_ADD,
    SERVICE_UPDATE,
    SERVICE_REMOVE,
    SERVICE_CLEAR,
    SERVICE_RUN_NOW,
    SERVICE_RESCHEDULE,
    SERVICE_ENABLE_TAG,
    SERVICE_DISABLE_TAG,
    CONF_TITLE,
    CONF_DAY,
    CONF_START,
    CONF_END,
    CONF_END_DAY,
    CONF_SERVICE,
    CONF_SERVICE_DATA,
    CONF_END_SERVICE,
    CONF_END_SERVICE_DATA,
    CONF_ENABLED,
    CONF_TAGS,
    CONF_COLOR,
    CONF_ICON,
    CONF_SLOTS,
    ATTR_ID,
    ATTR_PLANNER_ID,
)
from .slots import slot_from_flat, mirror_flat_from_slots

_LOGGER = logging.getLogger(__name__)

REQ_FIELDS = [CONF_TITLE, CONF_DAY, CONF_START, CONF_SERVICE]

# ---------------------------------------------------------------------------
# Schemi voluptuous per validazione automatica dei servizi
# ---------------------------------------------------------------------------

_TIME_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")
_time_str = vol.All(cv.string, vol.Match(_TIME_RE, msg="Formato orario non valido, usare HH:MM"))
# Per i campi opzionali (end) una stringa vuota è ammessa: significa "non impostato"
# e viene rimossa da _strip_empty_optional_fields prima del salvataggio.
_time_str_optional = vol.Any("", _time_str)
_day_int = vol.All(vol.Coerce(int), vol.Range(min=0, max=6))

# Multi-slot: una regola può avere più fasce (day/start/end?/end_day?) invece
# di una sola. "slots" è opzionale sia su add_rule che su update_rule, per
# restare compatibile con chi chiama i servizi con i soli campi flat.
_SLOT_SCHEMA = vol.Schema({
    vol.Required(CONF_DAY): _day_int,
    vol.Required(CONF_START): _time_str,
    vol.Optional(CONF_END): _time_str_optional,
    vol.Optional(CONF_END_DAY): _day_int,
})
_slots_list = vol.All(cv.ensure_list, [_SLOT_SCHEMA], vol.Length(min=1))


def _require_day_start_or_slots(data: dict) -> dict:
    """Su add_rule: serve 'day'+'start', oppure una lista 'slots' non vuota."""
    has_flat = data.get(CONF_DAY) is not None and data.get(CONF_START)
    has_slots = isinstance(data.get(CONF_SLOTS), list) and len(data[CONF_SLOTS]) > 0
    if not has_flat and not has_slots:
        raise vol.Invalid("Specifica 'day' e 'start', oppure 'slots'.")
    return data


_BASE_PLANNER = vol.Schema({
    vol.Optional(ATTR_PLANNER_ID): cv.string,
}, extra=vol.ALLOW_EXTRA)

_RULE_ID_SCHEMA = _BASE_PLANNER.extend({
    vol.Required(ATTR_ID): cv.string,
})

_ADD_RULE_SCHEMA = vol.All(
    _BASE_PLANNER.extend({
        vol.Required(CONF_TITLE): cv.string,
        # day/start restano il modo più semplice per creare una regola con
        # una sola fascia; diventano facoltativi solo se si passa 'slots'
        # (vedi _require_day_start_or_slots).
        vol.Optional(CONF_DAY): _day_int,
        vol.Optional(CONF_START): _time_str,
        vol.Required(CONF_SERVICE): cv.string,
        vol.Optional(CONF_END): _time_str_optional,
        vol.Optional(CONF_END_DAY): _day_int,
        vol.Optional(CONF_SLOTS): _slots_list,
        vol.Optional(CONF_END_SERVICE): cv.string,
        vol.Optional(CONF_SERVICE_DATA): dict,
        vol.Optional(CONF_END_SERVICE_DATA): dict,
        vol.Optional(CONF_ENABLED, default=True): cv.boolean,
        vol.Optional(CONF_TAGS, default=[]): vol.Any(cv.string, list),
        vol.Optional(CONF_COLOR): cv.string,
        vol.Optional(CONF_ICON): cv.string,
        vol.Optional(ATTR_ID): cv.string,
    }),
    _require_day_start_or_slots,
)

_UPDATE_RULE_SCHEMA = _BASE_PLANNER.extend({
    vol.Required(ATTR_ID): cv.string,
    vol.Optional(CONF_TITLE): cv.string,
    vol.Optional(CONF_DAY): _day_int,
    vol.Optional(CONF_START): _time_str,
    vol.Optional(CONF_END): _time_str_optional,
    vol.Optional(CONF_END_DAY): _day_int,
    vol.Optional(CONF_SLOTS): _slots_list,
    vol.Optional(CONF_SERVICE): cv.string,
    vol.Optional(CONF_SERVICE_DATA): dict,
    vol.Optional(CONF_END_SERVICE): cv.string,
    vol.Optional(CONF_END_SERVICE_DATA): dict,
    vol.Optional(CONF_ENABLED): cv.boolean,
    vol.Optional(CONF_TAGS): vol.Any(cv.string, list),
    vol.Optional(CONF_COLOR): cv.string,
    vol.Optional(CONF_ICON): cv.string,
})

_TAG_SCHEMA = _BASE_PLANNER.extend({
    vol.Required("tag"): cv.string,
})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _require_planner(hass: HomeAssistant, call: ServiceCall) -> str:
    """Risolve il planner_id dalla chiamata. Errore se ambiguo o inesistente."""
    planner_id = call.data.get(ATTR_PLANNER_ID)
    all_entries = hass.data.get(DOMAIN, {})
    if planner_id:
        if planner_id in all_entries:
            return planner_id
        raise HomeAssistantError(f"Planner '{planner_id}' non trovato.")
    candidate_ids = list(all_entries)
    if len(candidate_ids) == 1:
        return candidate_ids[0]
    raise HomeAssistantError(
        "Specifica 'planner_id': sono presenti più planner o nessuno configurato."
    )


def _sanitize_service_data(service: str | None, sd: dict | None) -> dict:
    """Rimuove valori vuoti/None dai service_data. Pulizia specifica per light.turn_on."""
    if not isinstance(sd, dict):
        return {}
    out = {k: v for k, v in sd.items() if v not in ("", None)}
    if service == "light.turn_on":
        for key in ("brightness", "brightness_pct"):
            if isinstance(out.get(key), (int, float)) and out[key] <= 0:
                out.pop(key, None)
    return out


def _normalize_tags(raw) -> list[str]:
    """Normalizza tag da qualsiasi formato a lista di stringhe lowercase univoche."""
    if raw is None:
        return []
    if isinstance(raw, str):
        parts = [p.strip().lower() for p in raw.split(",")]
    elif isinstance(raw, (list, tuple, set)):
        parts = [str(x).strip().lower() for x in raw if x is not None]
    else:
        parts = [str(raw).strip().lower()]
    seen: set[str] = set()
    out: list[str] = []
    for p in parts:
        if p and p not in seen:
            seen.add(p)
            out.append(p)
    return out


def _rule_has_tag(rule: dict, tag: str) -> bool:
    tag_norm = str(tag or "").strip().lower()
    if not tag_norm:
        return False
    tags = rule.get(CONF_TAGS)
    if isinstance(tags, str):
        tags = _normalize_tags(tags)
    if not isinstance(tags, list):
        return False
    return tag_norm in [str(t).strip().lower() for t in tags if t not in (None, "")]


def _notify_and_refresh(hass: HomeAssistant, pid: str) -> None:
    """Notifica l'UI e aggiorna il sensore."""
    hass.bus.async_fire(f"{DOMAIN}_changed", {"planner_id": pid})
    try:
        ent = hass.data[DOMAIN][pid].get("sensor_entity")
        if ent:
            hass.async_create_task(ent.async_refresh_state())
    except Exception:  # noqa: BLE001
        pass


def _strip_empty_optional_fields(data: dict) -> dict:
    """Rimuove i campi opzionali con stringa vuota dal dict della regola."""
    optional_str_fields = (CONF_END, CONF_END_DAY, CONF_COLOR, CONF_ICON)
    return {k: v for k, v in data.items() if not (k in optional_str_fields and v == "")}


def _clean_slot(slot: dict) -> dict:
    """Normalizza un singolo slot: rimuove end/end_day vuoti (già validati da
    _SLOT_SCHEMA, qui si toglie solo la stringa vuota ammessa per 'end')."""
    out = {CONF_DAY: slot.get(CONF_DAY), CONF_START: slot.get(CONF_START)}
    if slot.get(CONF_END):
        out[CONF_END] = slot[CONF_END]
    if slot.get(CONF_END_DAY) is not None:
        out[CONF_END_DAY] = slot[CONF_END_DAY]
    return out


async def _set_tag_enabled(hass: HomeAssistant, call: ServiceCall, enabled: bool) -> None:
    """Logica condivisa per enable_tag e disable_tag."""
    pid = _require_planner(hass, call)
    ctx = hass.data[DOMAIN][pid]
    storage = ctx["storage"]
    scheduler = ctx["scheduler"]

    tag = str(call.data.get("tag") or "").strip().lower()
    if not tag:
        raise HomeAssistantError("Il campo 'tag' è obbligatorio.")

    rules = storage.list_rules()
    changed = False
    for i, r in enumerate(rules):
        if _rule_has_tag(r, tag) and r.get(CONF_ENABLED, True) is not enabled:
            nr = copy.deepcopy(r)
            nr[CONF_ENABLED] = enabled
            rules[i] = nr
            changed = True

    if changed:
        storage.set_rules(rules)
        _notify_and_refresh(hass, pid)
        hass.async_create_task(storage.async_save())
        hass.async_create_task(scheduler.async_reschedule_all())


# ---------------------------------------------------------------------------
# Registrazione servizi
# ---------------------------------------------------------------------------

async def async_setup_services(hass: HomeAssistant) -> None:

    async def add_rule(call: ServiceCall) -> None:
        pid = _require_planner(hass, call)
        ctx = hass.data[DOMAIN][pid]
        storage = ctx["storage"]
        scheduler = ctx["scheduler"]

        data = _strip_empty_optional_fields(dict(call.data))
        data[CONF_TAGS] = _normalize_tags(data.get(CONF_TAGS))
        data[CONF_SERVICE_DATA] = _sanitize_service_data(
            data.get(CONF_SERVICE), data.get(CONF_SERVICE_DATA)
        )
        if data.get(CONF_END_SERVICE):
            data[CONF_END_SERVICE_DATA] = _sanitize_service_data(
                data.get(CONF_END_SERVICE), data.get(CONF_END_SERVICE_DATA)
            )
        else:
            data.pop(CONF_END_SERVICE_DATA, None)

        if isinstance(data.get(CONF_SLOTS), list) and data[CONF_SLOTS]:
            data[CONF_SLOTS] = [_clean_slot(s) for s in data[CONF_SLOTS]]
            mirror_flat_from_slots(data)
        else:
            data[CONF_SLOTS] = [slot_from_flat(data)]

        data[ATTR_ID] = data.get(ATTR_ID) or str(uuid.uuid4())

        storage.upsert_rule(data)
        _notify_and_refresh(hass, pid)
        hass.async_create_task(storage.async_save())
        hass.async_create_task(scheduler.async_reschedule_all())

    async def update_rule(call: ServiceCall) -> None:
        pid = _require_planner(hass, call)
        ctx = hass.data[DOMAIN][pid]
        storage = ctx["storage"]
        scheduler = ctx["scheduler"]

        data = _strip_empty_optional_fields(dict(call.data))
        rid = data.get(ATTR_ID)

        rules = storage.list_rules()
        idx = next((i for i, r in enumerate(rules) if r.get(ATTR_ID) == rid), None)
        if idx is None:
            raise HomeAssistantError(f"Regola '{rid}' non trovata.")

        rule = rules[idx]

        if CONF_TAGS in data:
            data[CONF_TAGS] = _normalize_tags(data[CONF_TAGS])

        if CONF_SERVICE_DATA in data or CONF_SERVICE in data:
            eff_service = data.get(CONF_SERVICE, rule.get(CONF_SERVICE))
            eff_sd = data.get(CONF_SERVICE_DATA, rule.get(CONF_SERVICE_DATA))
            data[CONF_SERVICE_DATA] = _sanitize_service_data(eff_service, eff_sd)

        if CONF_END_SERVICE_DATA in data or CONF_END_SERVICE in data:
            eff_eservice = data.get(CONF_END_SERVICE, rule.get(CONF_END_SERVICE))
            eff_esd = data.get(CONF_END_SERVICE_DATA, rule.get(CONF_END_SERVICE_DATA))
            if eff_eservice:
                data[CONF_END_SERVICE_DATA] = _sanitize_service_data(eff_eservice, eff_esd)
            else:
                data.pop(CONF_END_SERVICE_DATA, None)

        # Multi-slot: "slots" sostituisce l'intera lista (e i campi flat ne
        # restano lo specchio); i campi flat day/start/end/end_day da soli
        # aggiornano l'unico slot SOLO se la regola non ne ha già più di uno
        # — altrimenti non è chiaro quale fascia modificare, meglio un
        # errore esplicito che disallineare silenziosamente slots dal mirror.
        incoming_slots = data.get(CONF_SLOTS)
        has_explicit_slots = isinstance(incoming_slots, list) and len(incoming_slots) > 0
        flat_slot_fields_in_data = any(
            k in data for k in (CONF_DAY, CONF_START, CONF_END, CONF_END_DAY)
        )

        if has_explicit_slots:
            data[CONF_SLOTS] = [_clean_slot(s) for s in incoming_slots]
        elif flat_slot_fields_in_data:
            existing_slots = rule.get(CONF_SLOTS)
            if isinstance(existing_slots, list) and len(existing_slots) > 1:
                raise HomeAssistantError(
                    f"La regola '{rid}' ha più fasce orarie: usa il campo 'slots' "
                    "per modificarla invece dei singoli campi day/start/end/end_day."
                )

        new_rule = copy.deepcopy(rule)
        for k, v in data.items():
            if k == ATTR_ID:
                continue
            new_rule[k] = v

        if has_explicit_slots:
            mirror_flat_from_slots(new_rule)
        elif flat_slot_fields_in_data:
            new_rule[CONF_SLOTS] = [slot_from_flat(new_rule)]

        rules[idx] = new_rule
        storage.set_rules(rules)

        _notify_and_refresh(hass, pid)
        hass.async_create_task(storage.async_save())
        hass.async_create_task(scheduler.async_reschedule_all())

    async def remove_rule(call: ServiceCall) -> None:
        pid = _require_planner(hass, call)
        ctx = hass.data[DOMAIN][pid]
        storage = ctx["storage"]
        scheduler = ctx["scheduler"]

        rid = call.data.get(ATTR_ID)
        if not storage.remove_rule(rid):
            raise HomeAssistantError(f"Regola '{rid}' non trovata.")

        _notify_and_refresh(hass, pid)
        hass.async_create_task(storage.async_save())
        hass.async_create_task(scheduler.async_reschedule_all())

    async def clear_rules(call: ServiceCall) -> None:
        pid = _require_planner(hass, call)
        ctx = hass.data[DOMAIN][pid]
        storage = ctx["storage"]
        scheduler = ctx["scheduler"]

        storage.clear()
        _notify_and_refresh(hass, pid)
        hass.async_create_task(storage.async_save())
        hass.async_create_task(scheduler.async_reschedule_all())

    async def run_rule_now(call: ServiceCall) -> None:
        pid = _require_planner(hass, call)
        ctx = hass.data[DOMAIN][pid]
        storage = ctx["storage"]

        rid = call.data.get(ATTR_ID)
        rule = next((r for r in storage.list_rules() if r.get(ATTR_ID) == rid), None)
        if not rule:
            raise HomeAssistantError(f"Regola '{rid}' non trovata.")

        service = rule.get(CONF_SERVICE)
        if not service or "." not in service:
            raise HomeAssistantError(
                f"Service non valido nella regola '{rid}'. Usa il formato 'dominio.servizio'."
            )
        domain, svc = service.split(".", 1)
        await hass.services.async_call(
            domain, svc, rule.get(CONF_SERVICE_DATA) or {}, blocking=True
        )

    async def reschedule_all(call: ServiceCall) -> None:
        pid = _require_planner(hass, call)
        scheduler = hass.data[DOMAIN][pid]["scheduler"]
        await scheduler.async_reschedule_all()

    async def enable_tag(call: ServiceCall) -> None:
        await _set_tag_enabled(hass, call, enabled=True)

    async def disable_tag(call: ServiceCall) -> None:
        await _set_tag_enabled(hass, call, enabled=False)

    hass.services.async_register(DOMAIN, SERVICE_ADD, add_rule, schema=_ADD_RULE_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_UPDATE, update_rule, schema=_UPDATE_RULE_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_REMOVE, remove_rule, schema=_RULE_ID_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_CLEAR, clear_rules, schema=_BASE_PLANNER)
    hass.services.async_register(DOMAIN, SERVICE_RUN_NOW, run_rule_now, schema=_RULE_ID_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_RESCHEDULE, reschedule_all, schema=_BASE_PLANNER)
    hass.services.async_register(DOMAIN, SERVICE_ENABLE_TAG, enable_tag, schema=_TAG_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_DISABLE_TAG, disable_tag, schema=_TAG_SCHEMA)

    _LOGGER.debug("ChronoTask: %d servizi registrati", 8)
