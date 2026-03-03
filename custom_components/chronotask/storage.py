from __future__ import annotations

import logging
from typing import Any
import copy

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import STORAGE_KEY_BASE, STORAGE_VERSION

_LOGGER = logging.getLogger(__name__)

# Campi obbligatori minimi per considerare valida una regola
_REQUIRED_RULE_FIELDS = {"id", "title", "day", "start", "service"}


def _validate_rule(rule: Any) -> bool:
    """Restituisce True se la regola ha i campi minimi necessari."""
    if not isinstance(rule, dict):
        return False
    for field in _REQUIRED_RULE_FIELDS:
        if field not in rule or rule[field] in (None, ""):
            return False
    try:
        day = int(rule["day"])
        if not (0 <= day <= 6):
            return False
    except (ValueError, TypeError):
        return False
    return True


class PlannerStorage:
    def __init__(self, hass: HomeAssistant, planner_id: str):
        self._store = Store(hass, STORAGE_VERSION, f"{STORAGE_KEY_BASE}.{planner_id}")
        self._data: dict[str, Any] = {"rules": []}

    async def async_load(self) -> None:
        data = await self._store.async_load()
        if isinstance(data, dict) and "rules" in data:
            raw_rules = data.get("rules", [])
            if isinstance(raw_rules, list):
                valid_rules = []
                for i, rule in enumerate(raw_rules):
                    if _validate_rule(rule):
                        valid_rules.append(rule)
                    else:
                        _LOGGER.warning(
                            "ChronoTask: regola %d ignorata (dati non validi): %s",
                            i, rule,
                        )
                self._data = {"rules": valid_rules}
            else:
                _LOGGER.warning("ChronoTask: formato storage non valido, reset.")
                self._data = {"rules": []}

    async def async_save(self) -> None:
        await self._store.async_save(self._data)

    def list_rules(self) -> list[dict]:
        """Restituisce copie profonde delle regole per evitare mutazioni accidentali."""
        return copy.deepcopy(list(self._data.get("rules", [])))

    def set_rules(self, rules: list[dict]) -> None:
        """Sostituisce tutte le regole con una copia profonda."""
        self._data["rules"] = copy.deepcopy(list(rules or []))

    def upsert_rule(self, rule: dict) -> None:
        """Inserisce o aggiorna una regola per id."""
        rules = list(self._data.get("rules", []))
        rid = (rule or {}).get("id")
        new_rule = copy.deepcopy(rule)
        for i, r in enumerate(rules):
            if r.get("id") == rid:
                rules[i] = new_rule
                self._data["rules"] = rules
                return
        rules.append(new_rule)
        self._data["rules"] = rules

    def remove_rule(self, rid: str) -> bool:
        """Rimuove una regola per id. Restituisce True se trovata e rimossa."""
        rules = list(self._data.get("rules", []))
        before = len(rules)
        rules = [r for r in rules if r.get("id") != rid]
        self._data["rules"] = rules
        return len(rules) != before

    def clear(self) -> None:
        """Rimuove tutte le regole."""
        self._data["rules"] = []
