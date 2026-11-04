"""Helpers per il multi-slot: una regola condivide un'unica azione
(service/service_data/end_service/end_service_data) su più fasce
(day, start, end?, end_day?).

Modulo puro, senza dipendenze da Home Assistant/voluptuous: usato sia dal
backend (scheduler, calendar, storage, services) sia testabile in isolamento.
"""
from __future__ import annotations

import copy
from datetime import datetime, timedelta
from typing import Any, Iterator

from .const import (
    ATTR_ID,
    CONF_DAY,
    CONF_START,
    CONF_END,
    CONF_END_DAY,
    CONF_SLOTS,
    CONF_ENABLED,
    CONF_TITLE,
    CONF_SERVICE,
    CONF_SERVICE_DATA,
    CONF_END_SERVICE,
    CONF_END_SERVICE_DATA,
)

_SLOT_KEYS = (CONF_DAY, CONF_START, CONF_END, CONF_END_DAY)


def slot_from_flat(rule: dict[str, Any]) -> dict[str, Any]:
    """Costruisce un singolo slot dai campi day/start/end/end_day di una regola."""
    slot: dict[str, Any] = {
        CONF_DAY: rule.get(CONF_DAY),
        CONF_START: rule.get(CONF_START),
    }
    if rule.get(CONF_END):
        slot[CONF_END] = rule[CONF_END]
    if rule.get(CONF_END_DAY) is not None:
        slot[CONF_END_DAY] = rule[CONF_END_DAY]
    return slot


def effective_end_day(day: int, start: str | None, end: str | None,
                      end_day: int | None = None) -> int:
    """Giorno in cui scatta l'azione di fine di una fascia.

    Se end_day è esplicito vince sempre. Altrimenti una fascia con fine
    strettamente precedente all'inizio (es. 22:00 -> 06:00) è "overnight":
    la fine cade il giorno dopo. In tutti gli altri casi è lo stesso giorno.
    Le stringhe HH:MM si confrontano correttamente in ordine lessicografico.
    """
    if end_day is not None and end_day != "":
        return int(end_day) % 7
    if end and start and str(end)[:5] < str(start)[:5]:
        return (int(day) + 1) % 7
    return int(day)


def iter_slots(rule: dict[str, Any]) -> list[dict[str, Any]]:
    """Restituisce gli slot di una regola: rule[CONF_SLOTS] se presente e non
    vuoto, altrimenti un singolo slot ricavato dai campi flat (fallback
    difensivo per regole non ancora migrate o dati incoerenti)."""
    slots = rule.get(CONF_SLOTS)
    if isinstance(slots, list) and slots:
        return slots
    return [slot_from_flat(rule)]


def mirror_flat_from_slots(rule: dict[str, Any]) -> None:
    """Allinea i campi flat day/start/end/end_day di una regola al suo
    slots[0], in place. Mantiene leggibile la regola per chi ne legge i
    campi direttamente (template, tag manager) senza dover conoscere slots."""
    slots = rule.get(CONF_SLOTS)
    first = slots[0] if isinstance(slots, list) and slots else {}
    rule[CONF_DAY] = first.get(CONF_DAY)
    rule[CONF_START] = first.get(CONF_START)
    if first.get(CONF_END):
        rule[CONF_END] = first[CONF_END]
    else:
        rule.pop(CONF_END, None)
    if first.get(CONF_END_DAY) is not None:
        rule[CONF_END_DAY] = first[CONF_END_DAY]
    else:
        rule.pop(CONF_END_DAY, None)


def expand_rules(rules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Espande una lista di regole in una lista "flat-shaped": una entry per
    ogni (regola, slot), con i campi day/start/end/end_day dello slot
    sovrascritti su una copia superficiale della regola, più "_slot_index".

    Permette a scheduler.py/calendar.py di continuare a operare su dict dalla
    stessa forma di prima (una regola = un day/start/end/end_day) invece di
    dover passare uno slot esplicito in ogni firma di funzione.
    """
    expanded: list[dict[str, Any]] = []
    for rule in rules:
        for idx, slot in enumerate(iter_slots(rule)):
            flat = {**rule, **{k: slot.get(k) for k in _SLOT_KEYS if k in slot}}
            # Uno slot senza end/end_day non deve ereditare quelli di un'altra
            # fascia della stessa regola: rimuovili se lo slot corrente non li ha.
            if CONF_END not in slot:
                flat.pop(CONF_END, None)
            if CONF_END_DAY not in slot:
                flat.pop(CONF_END_DAY, None)
            flat["_slot_index"] = idx
            expanded.append(flat)
    return expanded


# ---------------------------------------------------------------------------
# Stato "corrente" per entità (pause / resume / resync)
#
# Tutto ciò che segue è puro (nessuna dipendenza da Home Assistant): riceve le
# regole come liste di dict e un "adesso" già nel fuso locale, quindi si testa
# senza HA. Lo stato corrente di un'entità è l'ULTIMO evento passato (negli
# ultimi 7 giorni) tra le regole abilitate che la hanno come bersaglio.
# ---------------------------------------------------------------------------

_IGNORED_TARGETS = {"all", "none"}


def _split_ids(value: Any) -> list[str]:
    """Normalizza un valore entity_id (stringa con virgole o lista) a una lista
    di id in minuscolo, senza duplicati. Ignora 'all', 'none' e i template."""
    if isinstance(value, str):
        raw = value.split(",")
    elif isinstance(value, (list, tuple, set)):
        raw = []
        for item in value:
            if isinstance(item, str):
                raw.extend(item.split(","))
    else:
        return []
    out: list[str] = []
    for item in raw:
        eid = item.strip().lower()
        if not eid or eid in _IGNORED_TARGETS or "{{" in eid or "{%" in eid or "." not in eid:
            continue
        if eid not in out:
            out.append(eid)
    return out


def target_entities(data: Any) -> list[str]:
    """Entità bersaglio di un service_data: 'entity_id' e 'target.entity_id'."""
    if not isinstance(data, dict):
        return []
    out = _split_ids(data.get("entity_id"))
    target = data.get("target")
    if isinstance(target, dict):
        for eid in _split_ids(target.get("entity_id")):
            if eid not in out:
                out.append(eid)
    return out


def restrict_entities(data: dict, keep: Any) -> dict:
    """Copia di data con entity_id ristretto a 'keep', nella stessa posizione in
    cui era (entity_id e/o target.entity_id) e con la stessa forma (stringa se
    era una stringa e ne resta una sola, altrimenti lista)."""
    keep_set = {str(e).lower() for e in keep}
    out = copy.deepcopy(data)

    def _restrict(container: dict) -> None:
        if "entity_id" not in container:
            return
        original = container["entity_id"]
        ids = [e for e in _split_ids(original) if e in keep_set]
        container["entity_id"] = ids[0] if (isinstance(original, str) and len(ids) == 1) else ids

    _restrict(out)
    if isinstance(out.get("target"), dict):
        _restrict(out["target"])
    return out


def strip_entities(data: Any) -> dict:
    """Copia di data senza entity_id (né top-level né in target): i parametri
    'attesi' di un'azione, indipendenti dall'entità."""
    if not isinstance(data, dict):
        return {}
    out = copy.deepcopy(data)
    out.pop("entity_id", None)
    target = out.get("target")
    if isinstance(target, dict):
        target.pop("entity_id", None)
        if not target:
            out.pop("target", None)
    return out


def rule_targets(rule: dict[str, Any]) -> list[str]:
    """Entità bersaglio di una regola: unione di service_data e end_service_data."""
    out = target_entities(rule.get(CONF_SERVICE_DATA))
    for eid in target_entities(rule.get(CONF_END_SERVICE_DATA)):
        if eid not in out:
            out.append(eid)
    return out


def all_target_entities(rules: list[dict[str, Any]]) -> list[str]:
    """Tutte le entità bersaglio di almeno una regola (anche disabilitata)."""
    out: list[str] = []
    for rule in rules:
        for eid in rule_targets(rule):
            if eid not in out:
                out.append(eid)
    return out


def event_action(rule: dict[str, Any], part: str) -> tuple[str | None, dict]:
    """(servizio, dati) dell'azione di 'start' o 'end' di una regola."""
    if part == "start":
        return rule.get(CONF_SERVICE), rule.get(CONF_SERVICE_DATA) or {}
    return rule.get(CONF_END_SERVICE), rule.get(CONF_END_SERVICE_DATA) or {}


def parse_hm(value: Any) -> tuple[int, int] | None:
    """'HH:MM' (anche 'HH:MM:SS') -> (ore, minuti), oppure None se non valido."""
    try:
        hh, mm = str(value)[:5].split(":")
        hh, mm = int(hh), int(mm)
    except (ValueError, TypeError):
        return None
    if 0 <= hh <= 23 and 0 <= mm <= 59:
        return hh, mm
    return None


def _rule_events(rule: dict[str, Any]) -> Iterator[tuple[int, str, int, tuple[int, int]]]:
    """Eventi di una regola: (indice fascia, 'start'|'end', giorno, (hh, mm)).
    Ogni fascia ha uno start e, se ha una fine, un end (nel giorno effettivo)."""
    for idx, slot in enumerate(iter_slots(rule)):
        try:
            day = int(slot.get(CONF_DAY))
        except (TypeError, ValueError):
            continue
        start = parse_hm(slot.get(CONF_START))
        if start is None or not 0 <= day <= 6:
            continue
        yield idx, "start", day, start
        end = parse_hm(slot.get(CONF_END))
        if end is not None:
            end_day = effective_end_day(day, slot.get(CONF_START), slot.get(CONF_END), slot.get(CONF_END_DAY))
            yield idx, "end", end_day, end


def _last_occurrence(now: datetime, weekday: int, hm: tuple[int, int]) -> datetime:
    """Ultima occorrenza (<= now) di weekday/hm, al massimo 7 giorni indietro."""
    cand = now.replace(hour=hm[0], minute=hm[1], second=0, microsecond=0)
    cand -= timedelta(days=(now.weekday() - weekday) % 7)
    if cand > now:
        cand -= timedelta(days=7)
    return cand


def next_occurrence(now: datetime, weekday: int, hm: tuple[int, int]) -> datetime:
    """Prima occorrenza (> now) di weekday/hm."""
    cand = now.replace(hour=hm[0], minute=hm[1], second=0, microsecond=0)
    cand += timedelta(days=(weekday - now.weekday()) % 7)
    if cand <= now:
        cand += timedelta(days=7)
    return cand


def current_event_for_entity(
    rules: list[dict[str, Any]], entity_id: str, now: datetime
) -> dict[str, Any] | None:
    """Ultimo evento passato che riguarda entity_id tra le regole abilitate.

    Restituisce {"rule", "slot_index", "part": "start"|"end", "at"} oppure None
    se nessuna regola abilitata la ha come bersaglio. A parità di orario vince
    'start' su 'end' (fasce contigue); a parità totale, la prima regola.
    """
    eid = str(entity_id).lower()
    best: tuple[tuple[datetime, int], dict[str, Any]] | None = None
    for rule in rules:
        if not rule.get(CONF_ENABLED, True):
            continue
        if eid not in rule_targets(rule):
            continue
        for idx, part, day, hm in _rule_events(rule):
            at = _last_occurrence(now, day, hm)
            key = (at, 1 if part == "start" else 0)
            if best is None or key > best[0]:
                best = (key, {"rule": rule, "slot_index": idx, "part": part, "at": at})
    return best[1] if best else None


def next_event_time_for_entity(
    rules: list[dict[str, Any]], entity_id: str, now: datetime
) -> datetime | None:
    """Prossimo istante (> now) in cui lo stato di entity_id cambia."""
    eid = str(entity_id).lower()
    best: datetime | None = None
    for rule in rules:
        if not rule.get(CONF_ENABLED, True) or eid not in rule_targets(rule):
            continue
        for _idx, _part, day, hm in _rule_events(rule):
            at = next_occurrence(now, day, hm)
            if best is None or at < best:
                best = at
    return best


def build_entities_view(
    rules: list[dict[str, Any]], holds: dict[str, Any], now: datetime
) -> dict[str, dict[str, Any]]:
    """Attributo 'entities' del sensore: una voce per ogni entità bersaglio di
    almeno una regola (anche disabilitata) e per ogni entità in pausa."""
    holds = holds or {}
    eids = all_target_entities(rules)
    for eid in holds:
        if eid not in eids:
            eids.append(eid)
    view: dict[str, dict[str, Any]] = {}
    for eid in eids:
        ev = current_event_for_entity(rules, eid, now)
        entry: dict[str, Any] = {
            "scheduled": None, "rule": None, "rule_id": None, "since": None,
            "expected_service": None, "expected_data": None,
            "next_change": None,
            "hold": False, "hold_until": None, "hold_reason": None,
        }
        if ev:
            rule = ev["rule"]
            entry["scheduled"] = ev["part"]
            entry["rule"] = rule.get(CONF_TITLE)
            entry["rule_id"] = rule.get(ATTR_ID)
            entry["since"] = ev["at"].isoformat()
            service, data = event_action(rule, ev["part"])
            if service and eid in target_entities(data):
                entry["expected_service"] = service
                entry["expected_data"] = strip_entities(data)
        nxt = next_event_time_for_entity(rules, eid, now)
        entry["next_change"] = nxt.isoformat() if nxt else None
        hold = holds.get(eid)
        if hold is not None:
            entry["hold"] = True
            entry["hold_until"] = hold.get("until")
            entry["hold_reason"] = hold.get("reason")
        view[eid] = entry
    return view
