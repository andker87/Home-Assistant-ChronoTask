from __future__ import annotations

import uuid
import copy

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError

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
    ATTR_ID,
    ATTR_PLANNER_ID,
)

REQ_FIELDS = [CONF_TITLE, CONF_DAY, CONF_START, CONF_SERVICE]


def _require_planner(hass: HomeAssistant, call: ServiceCall) -> str:
    planner_id = call.data.get(ATTR_PLANNER_ID)
    all_entries = hass.data.get(DOMAIN, {})
    if planner_id and planner_id in all_entries:
        return planner_id
    candidate_ids = [k for k in all_entries.keys() if k != 'listeners']
    if len(candidate_ids) == 1:
        return candidate_ids[0]
    raise HomeAssistantError("Specifica 'planner_id' perché sono presenti più planner.")


def _sanitize_service_data(service: str | None, sd: dict | None) -> dict:
    if not isinstance(sd, dict):
        return {}
    out = {k: v for k, v in sd.items() if v not in ("", None)}
    if service == "light.turn_on":
        if isinstance(out.get("brightness"), (int, float)) and out["brightness"] <= 0:
            out.pop("brightness", None)
        if isinstance(out.get("brightness_pct"), (int, float)) and out["brightness_pct"] <= 0:
            out.pop("brightness_pct", None)
    return out


def _normalize_tags(raw) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            return []
        parts = [p.strip().lower() for p in s.split(',')]
        # unique
        seen=set(); out=[]
        for p in parts:
            if p and p not in seen:
                seen.add(p); out.append(p)
        return out
    if isinstance(raw, (list, tuple, set)):
        seen=set(); out=[]
        for x in raw:
            if x is None:
                continue
            s = str(x).strip().lower()
            if s and s not in seen:
                seen.add(s); out.append(s)
        return out
    s = str(raw).strip().lower()
    return [s] if s else []


def _rule_has_tag(rule: dict, tag: str) -> bool:
    tag_norm = str(tag or '').strip().lower()
    if not tag_norm:
        return False
    tags = rule.get(CONF_TAGS)
    if isinstance(tags, str):
        tags = _normalize_tags(tags)
    if not isinstance(tags, list):
        return False
    return tag_norm in [str(t).strip().lower() for t in tags if t not in (None, '')]


def _to_bool(val, default=True):
    if val is None:
        return default
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        return bool(val)
    s = str(val).strip().lower()
    if s in ('true','1','yes','on'):
        return True
    if s in ('false','0','no','off'):
        return False
    return default


def _notify_and_refresh(hass: HomeAssistant, pid: str):
    # notify UI and refresh sensor entity (direct)
    hass.bus.async_fire(f"{DOMAIN}_changed", {"planner_id": pid})
    try:
        ent = hass.data[DOMAIN][pid].get('sensor_entity')
        if ent:
            hass.async_create_task(ent.async_refresh_state())
    except Exception:
        pass


async def async_setup_services(hass: HomeAssistant):
    async def add_rule(call: ServiceCall):
        pid = _require_planner(hass, call)
        ctx = hass.data[DOMAIN][pid]
        storage = ctx['storage']
        scheduler = ctx['scheduler']

        data = dict(call.data)
        for k in REQ_FIELDS:
            if k not in data:
                raise HomeAssistantError(f"Campo mancante: {k}")
        try:
            data[CONF_DAY] = int(data[CONF_DAY])
            if not (0 <= data[CONF_DAY] <= 6):
                raise ValueError
        except Exception as exc:
            raise HomeAssistantError("day deve essere 0..6 (0=Lun..6=Dom)") from exc

        data[CONF_ENABLED] = _to_bool(data.get(CONF_ENABLED), True)
        if data.get(CONF_END) == "":
            data.pop(CONF_END, None)
        if data.get(CONF_END_DAY) == "":
            data.pop(CONF_END_DAY, None)
        if data.get(CONF_COLOR) == "":
            data.pop(CONF_COLOR, None)
        if data.get(CONF_ICON) == "":
            data.pop(CONF_ICON, None)

        data[CONF_TAGS] = _normalize_tags(data.get(CONF_TAGS))

        data[CONF_SERVICE_DATA] = _sanitize_service_data(data.get(CONF_SERVICE), data.get(CONF_SERVICE_DATA))
        if data.get(CONF_END_SERVICE):
            data[CONF_END_SERVICE_DATA] = _sanitize_service_data(data.get(CONF_END_SERVICE), data.get(CONF_END_SERVICE_DATA))
        else:
            data.pop(CONF_END_SERVICE_DATA, None)

        data[ATTR_ID] = data.get(ATTR_ID) or str(uuid.uuid4())

        storage.upsert_rule(data)
        _notify_and_refresh(hass, pid)
        hass.async_create_task(storage.async_save())
        hass.async_create_task(scheduler.async_reschedule_all())
        return True

    async def update_rule(call: ServiceCall):
        pid = _require_planner(hass, call)
        ctx = hass.data[DOMAIN][pid]
        storage = ctx['storage']
        scheduler = ctx['scheduler']

        data = dict(call.data)
        rid = data.get(ATTR_ID)
        if not rid:
            raise HomeAssistantError("Serve id della regola")

        rules = storage.list_rules()
        idx = next((i for i,r in enumerate(rules) if r.get(ATTR_ID) == rid), None)
        if idx is None:
            raise HomeAssistantError("Regola non trovata")

        rule = rules[idx]

        if CONF_DAY in data:
            try:
                data[CONF_DAY] = int(data[CONF_DAY])
            except Exception as exc:
                raise HomeAssistantError("day deve essere 0..6 (0=Lun..6=Dom)") from exc

        for fld in (CONF_END, CONF_END_DAY, CONF_COLOR, CONF_ICON):
            if fld in data and data[fld] == "":
                data.pop(fld, None)

        if CONF_ENABLED in data:
            data[CONF_ENABLED] = _to_bool(data.get(CONF_ENABLED), rule.get(CONF_ENABLED, True))

        if CONF_TAGS in data:
            data[CONF_TAGS] = _normalize_tags(data.get(CONF_TAGS))

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

        # Build new rule immutably
        new_rule = copy.deepcopy(rule)
        for k,v in data.items():
            if k == ATTR_ID:
                continue
            new_rule[k] = v
        rules[idx] = new_rule
        storage.set_rules(rules)

        _notify_and_refresh(hass, pid)
        hass.async_create_task(storage.async_save())
        hass.async_create_task(scheduler.async_reschedule_all())
        return True

    async def remove_rule(call: ServiceCall):
        pid = _require_planner(hass, call)
        ctx = hass.data[DOMAIN][pid]
        storage = ctx['storage']
        scheduler = ctx['scheduler']

        rid = call.data.get(ATTR_ID)
        if not rid:
            raise HomeAssistantError("Serve id")
        if not storage.remove_rule(rid):
            raise HomeAssistantError("Regola non trovata")

        _notify_and_refresh(hass, pid)
        hass.async_create_task(storage.async_save())
        hass.async_create_task(scheduler.async_reschedule_all())
        return True

    async def clear_rules(call: ServiceCall):
        pid = _require_planner(hass, call)
        ctx = hass.data[DOMAIN][pid]
        storage = ctx['storage']
        scheduler = ctx['scheduler']

        storage.clear()
        _notify_and_refresh(hass, pid)
        hass.async_create_task(storage.async_save())
        hass.async_create_task(scheduler.async_reschedule_all())
        return True

    async def run_rule_now(call: ServiceCall):
        pid = _require_planner(hass, call)
        ctx = hass.data[DOMAIN][pid]
        storage = ctx['storage']

        rid = call.data.get(ATTR_ID)
        if not rid:
            raise HomeAssistantError("Serve id")
        r = next((r for r in storage.list_rules() if r.get(ATTR_ID) == rid), None)
        if not r:
            raise HomeAssistantError("Regola non trovata")
        service = r.get(CONF_SERVICE)
        if not service or '.' not in service:
            raise HomeAssistantError("Service non valido es. 'switch.turn_on'")
        domain, svc = service.split('.', 1)
        await hass.services.async_call(domain, svc, r.get(CONF_SERVICE_DATA) or {}, blocking=True)
        return True

    async def reschedule_all(call: ServiceCall):
        pid = _require_planner(hass, call)
        scheduler = hass.data[DOMAIN][pid]['scheduler']
        await scheduler.async_reschedule_all()
        return True

    async def enable_tag(call: ServiceCall):
        pid = _require_planner(hass, call)
        ctx = hass.data[DOMAIN][pid]
        storage = ctx['storage']
        scheduler = ctx['scheduler']

        tag = str(call.data.get('tag') or '').strip().lower()
        if not tag:
            raise HomeAssistantError("Serve 'tag'")

        rules = storage.list_rules()
        changed = False
        for i,r in enumerate(rules):
            if _rule_has_tag(r, tag):
                if r.get(CONF_ENABLED, True) is not True:
                    nr = copy.deepcopy(r)
                    nr[CONF_ENABLED] = True
                    rules[i] = nr
                    changed = True
        if changed:
            storage.set_rules(rules)
            _notify_and_refresh(hass, pid)
            hass.async_create_task(storage.async_save())
            hass.async_create_task(scheduler.async_reschedule_all())
        return True

    async def disable_tag(call: ServiceCall):
        pid = _require_planner(hass, call)
        ctx = hass.data[DOMAIN][pid]
        storage = ctx['storage']
        scheduler = ctx['scheduler']

        tag = str(call.data.get('tag') or '').strip().lower()
        if not tag:
            raise HomeAssistantError("Serve 'tag'")

        rules = storage.list_rules()
        changed = False
        for i,r in enumerate(rules):
            if _rule_has_tag(r, tag):
                if r.get(CONF_ENABLED, True) is not False:
                    nr = copy.deepcopy(r)
                    nr[CONF_ENABLED] = False
                    rules[i] = nr
                    changed = True
        if changed:
            storage.set_rules(rules)
            _notify_and_refresh(hass, pid)
            hass.async_create_task(storage.async_save())
            hass.async_create_task(scheduler.async_reschedule_all())
        return True

    hass.services.async_register(DOMAIN, SERVICE_ADD, add_rule)
    hass.services.async_register(DOMAIN, SERVICE_UPDATE, update_rule)
    hass.services.async_register(DOMAIN, SERVICE_REMOVE, remove_rule)
    hass.services.async_register(DOMAIN, SERVICE_CLEAR, clear_rules)
    hass.services.async_register(DOMAIN, SERVICE_RUN_NOW, run_rule_now)
    hass.services.async_register(DOMAIN, SERVICE_RESCHEDULE, reschedule_all)
    hass.services.async_register(DOMAIN, SERVICE_ENABLE_TAG, enable_tag)
    hass.services.async_register(DOMAIN, SERVICE_DISABLE_TAG, disable_tag)
