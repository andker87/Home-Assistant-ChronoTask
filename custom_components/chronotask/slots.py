"""Helpers per il multi-slot: una regola condivide un'unica azione
(service/service_data/end_service/end_service_data) su più fasce
(day, start, end?, end_day?).

Modulo puro, senza dipendenze da Home Assistant/voluptuous: usato sia dal
backend (scheduler, calendar, storage, services) sia testabile in isolamento.
"""
from __future__ import annotations

from typing import Any

from .const import CONF_DAY, CONF_START, CONF_END, CONF_END_DAY, CONF_SLOTS

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
