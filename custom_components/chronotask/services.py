from __future__ import annotations

import uuid
import copy
import logging
import re
from datetime import timedelta

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import HomeAssistantError
import homeassistant.helpers.config_validation as cv
from homeassistant.util import dt as dt_util

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
    SERVICE_EXPORT,
    SERVICE_IMPORT,
    SERVICE_HOLD,
    SERVICE_RESUME,
    SERVICE_RESYNC,
    EXPORT_FORMAT,
    EXPORT_VERSION,
    INTEGRATION_VERSION,
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
from .slots import all_target_entities, slot_from_flat, mirror_flat_from_slots

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

_IMPORT_SCHEMA = _BASE_PLANNER.extend({
    vol.Required("rules"): list,
    vol.Optional("mode", default="merge"): vol.In(["merge", "replace"]),
})

# Campi di una regola che l'import accetta dal file; il resto viene ignorato.
_IMPORT_KEYS = (
    ATTR_ID, CONF_TITLE, CONF_DAY, CONF_START, CONF_END, CONF_END_DAY, CONF_SLOTS,
    CONF_SERVICE, CONF_SERVICE_DATA, CONF_END_SERVICE, CONF_END_SERVICE_DATA,
    CONF_ENABLED, CONF_TAGS, CONF_COLOR, CONF_ICON,
)

_HOLD_SCHEMA = vol.All(
    _BASE_PLANNER.extend({
        vol.Required("entity_id"): cv.entity_ids,
        vol.Optional("minutes"): vol.All(vol.Coerce(int), vol.Range(min=1)),
        vol.Optional("until"): cv.datetime,
        vol.Optional("reason"): cv.string,
    }),
    cv.has_at_most_one_key("minutes", "until"),
)

_RESUME_SCHEMA = _BASE_PLANNER.extend({
    vol.Required("entity_id"): cv.entity_ids,
    vol.Optional("apply", default=True): cv.boolean,
})

_RESYNC_SCHEMA = _BASE_PLANNER.extend({
    vol.Optional("entity_id"): cv.entity_ids,
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


def _planners_for_entities(
    hass: HomeAssistant, call: ServiceCall, entity_ids: list[str]
) -> dict[str, list[str]]:
    """{planner_id: [entità che quel planner gestisce]}.

    Con 'planner_id' esplicito si usa solo quel planner (tutte le entità
    richieste). Senza, ogni planner prende le entità che ha come bersaglio di
    una regola o che ha in pausa; le entità di nessun planner non compaiono."""
    all_entries = hass.data.get(DOMAIN, {})
    pid = call.data.get(ATTR_PLANNER_ID)
    if pid:
        if pid not in all_entries:
            raise HomeAssistantError(f"Planner '{pid}' non trovato.")
        return {pid: list(entity_ids)}
    out: dict[str, list[str]] = {}
    for p, ctx in all_entries.items():
        storage = ctx["storage"]
        managed = set(all_target_entities(storage.list_rules())) | set(storage.list_holds())
        mine = [e for e in entity_ids if e in managed]
        if mine:
            out[p] = mine
    return out


def _prepare_rule(raw: dict) -> dict:
    """Normalizza una regola già validata dallo schema (add_rule e import):
    campi vuoti rimossi, tag normalizzati, service_data ripulito, fasce
    allineate ai campi flat e id garantito."""
    data = _strip_empty_optional_fields(dict(raw))
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
    return data


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

        data = _prepare_rule(call.data)

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

    async def export_rules(call: ServiceCall) -> dict:
        """Restituisce tutte le regole del planner in un documento JSON
        riutilizzabile da import_rules (backup, copia su un'altra istanza)."""
        pid = _require_planner(hass, call)
        ctx = hass.data[DOMAIN][pid]
        return {
            "format": EXPORT_FORMAT,
            "version": EXPORT_VERSION,
            "integration_version": INTEGRATION_VERSION,
            "exported_at": dt_util.utcnow().isoformat(),
            "planner_name": ctx.get("name"),
            "rules": ctx["storage"].list_rules(),
        }

    async def import_rules(call: ServiceCall) -> dict:
        """Importa regole da un export. merge: le aggiunge a quelle esistenti
        (un id già presente non sovrascrive mai: la regola importata ne riceve
        uno nuovo). replace: sostituisce tutte le regole, ma solo se almeno una
        è valida, così un file sbagliato non svuota il planner."""
        pid = _require_planner(hass, call)
        ctx = hass.data[DOMAIN][pid]
        storage = ctx["storage"]
        scheduler = ctx["scheduler"]
        mode = call.data["mode"]

        used_ids = {r.get(ATTR_ID) for r in storage.list_rules()} if mode == "merge" else set()
        imported: list[dict] = []
        skipped: list[dict] = []
        renamed = 0

        for idx, raw in enumerate(call.data["rules"]):
            title = raw.get(CONF_TITLE) if isinstance(raw, dict) else None
            try:
                if not isinstance(raw, dict):
                    raise vol.Invalid("la regola non è un oggetto")
                clean = {k: v for k, v in raw.items() if k in _IMPORT_KEYS}
                rule = _prepare_rule(_ADD_RULE_SCHEMA(clean))
            except (vol.Invalid, vol.MultipleInvalid) as err:
                skipped.append({"index": idx, "title": title, "error": str(err)})
                continue
            if rule[ATTR_ID] in used_ids:
                rule[ATTR_ID] = str(uuid.uuid4())
                renamed += 1
            used_ids.add(rule[ATTR_ID])
            imported.append(rule)

        if mode == "replace":
            if not imported:
                raise HomeAssistantError(
                    "Nessuna regola valida nel file: le regole esistenti non sono state toccate."
                )
            storage.set_rules(imported)
        else:
            for rule in imported:
                storage.upsert_rule(rule)

        await storage.async_save()
        _notify_and_refresh(hass, pid)
        hass.async_create_task(scheduler.async_reschedule_all())
        return {
            "mode": mode,
            "imported": len(imported),
            "skipped": skipped,
            "renamed_ids": renamed,
            "total": len(storage.list_rules()),
        }

    async def hold(call: ServiceCall) -> None:
        """Mette in pausa una o più entità: le regole non le toccano finché non
        scade la pausa o si chiama resume. Una pausa nuova sostituisce la vecchia."""
        entity_ids = list(call.data["entity_id"])
        now = dt_util.now()
        until = None
        if call.data.get("minutes") is not None:
            until = now + timedelta(minutes=call.data["minutes"])
        elif call.data.get("until") is not None:
            until = dt_util.as_local(call.data["until"])
            if until <= now:
                raise HomeAssistantError("'until' è nel passato: nessuna pausa creata.")
        mapping = _planners_for_entities(hass, call, entity_ids)
        missing = [e for e in entity_ids if not any(e in v for v in mapping.values())]
        if missing:
            raise HomeAssistantError(
                "Nessun planner ha regole per: " + ", ".join(missing)
                + ". Specifica 'planner_id' per metterle comunque in pausa."
            )
        for pid, ents in mapping.items():
            await hass.data[DOMAIN][pid]["scheduler"].async_hold(ents, until, call.data.get("reason"))

    def _merge_results(into: dict, new: dict) -> None:
        for eid, res in new.items():
            if eid not in into or (res.get("applied") and not into[eid].get("applied")):
                into[eid] = res

    async def resume(call: ServiceCall) -> dict:
        """Toglie la pausa e, con apply (default), applica lo stato corrente."""
        entity_ids = list(call.data["entity_id"])
        apply = call.data["apply"]
        result: dict = {e: {"applied": None, "rule": None} for e in entity_ids}
        for pid, ents in _planners_for_entities(hass, call, entity_ids).items():
            _merge_results(result, await hass.data[DOMAIN][pid]["scheduler"].async_resume(ents, apply))
        return result

    async def resync(call: ServiceCall) -> dict:
        """Applica lo stato corrente alle entità non in pausa."""
        entity_ids = call.data.get("entity_id")
        result: dict = {}
        if entity_ids is None:
            pid = call.data.get(ATTR_PLANNER_ID)
            if pid and pid not in hass.data.get(DOMAIN, {}):
                raise HomeAssistantError(f"Planner '{pid}' non trovato.")
            pids = [pid] if pid else list(hass.data.get(DOMAIN, {}))
            for p in pids:
                _merge_results(result, await hass.data[DOMAIN][p]["scheduler"].async_resync(None))
            return result
        entity_ids = list(entity_ids)
        result = {e: {"applied": None, "rule": None} for e in entity_ids}
        for pid, ents in _planners_for_entities(hass, call, entity_ids).items():
            _merge_results(result, await hass.data[DOMAIN][pid]["scheduler"].async_resync(ents))
        return result

    hass.services.async_register(DOMAIN, SERVICE_ADD, add_rule, schema=_ADD_RULE_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_UPDATE, update_rule, schema=_UPDATE_RULE_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_REMOVE, remove_rule, schema=_RULE_ID_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_CLEAR, clear_rules, schema=_BASE_PLANNER)
    hass.services.async_register(DOMAIN, SERVICE_RUN_NOW, run_rule_now, schema=_RULE_ID_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_RESCHEDULE, reschedule_all, schema=_BASE_PLANNER)
    hass.services.async_register(DOMAIN, SERVICE_ENABLE_TAG, enable_tag, schema=_TAG_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_DISABLE_TAG, disable_tag, schema=_TAG_SCHEMA)
    hass.services.async_register(
        DOMAIN, SERVICE_EXPORT, export_rules, schema=_BASE_PLANNER,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_IMPORT, import_rules, schema=_IMPORT_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )

    hass.services.async_register(DOMAIN, SERVICE_HOLD, hold, schema=_HOLD_SCHEMA)
    hass.services.async_register(
        DOMAIN, SERVICE_RESUME, resume, schema=_RESUME_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_RESYNC, resync, schema=_RESYNC_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )

    _LOGGER.debug("ChronoTask: %d servizi registrati", 13)
