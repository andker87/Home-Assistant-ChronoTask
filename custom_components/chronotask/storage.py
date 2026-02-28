from __future__ import annotations

from typing import Any
import copy

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import STORAGE_KEY_BASE, STORAGE_VERSION


class PlannerStorage:
    def __init__(self, hass: HomeAssistant, planner_id: str):
        self._store = Store(hass, STORAGE_VERSION, f"{STORAGE_KEY_BASE}.{planner_id}")
        self._data: dict[str, Any] = {"rules": []}

    async def async_load(self):
        data = await self._store.async_load()
        if isinstance(data, dict) and "rules" in data:
            self._data = data

    async def async_save(self):
        await self._store.async_save(self._data)

    def list_rules(self) -> list[dict]:
        # Return deep copies to avoid in-place mutation side-effects with HA state caching
        return copy.deepcopy(list(self._data.get("rules", [])))

    def set_rules(self, rules: list[dict]):
        # Store deep copy
        self._data["rules"] = copy.deepcopy(list(rules or []))

    def upsert_rule(self, rule: dict):
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
        rules = list(self._data.get("rules", []))
        before = len(rules)
        rules = [r for r in rules if r.get("id") != rid]
        self._data["rules"] = rules
        return len(rules) != before

    def clear(self):
        self._data["rules"] = []
