"""Test di export_rules / import_rules e del refactor di add_rule (services.py).

Eseguibili con:  python tests/test_import_export.py   oppure   pytest tests/
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _ha_stubs as stubs  # noqa: E402

stubs.install()
from _loader import load  # noqa: E402

const, slots, storage_mod, scheduler_mod, services = load("const", "slots", "storage", "scheduler", "services")[0:5]
HomeAssistantError = stubs.HomeAssistantError


async def make():
    stubs.FakeStore.backend.clear()
    hass = stubs.FakeHass()
    store = storage_mod.PlannerStorage(hass, "p1")
    await store.async_load()
    store.set_rules([{"id": "A", "title": "Esistente", "day": 0, "start": "08:00", "service": "light.turn_on",
                      "slots": [{"day": 0, "start": "08:00"}], "tags": ["casa"], "enabled": True}])
    hass.data[const.DOMAIN] = {"p1": {"name": "Casa", "storage": store,
                                      "scheduler": scheduler_mod.WeeklyScheduler(hass, store, "p1")}}
    await services.async_setup_services(hass)
    return hass, store


def test_export_import_roundtrip_and_validation():
    async def go():
        hass, st = await make()
        doc = await hass.services.call("export_rules", {})
        assert doc["format"] == "chronotask-export" and doc["planner_name"] == "Casa" and doc["rules"][0]["id"] == "A"
        json.dumps(doc)
        payload = [
            {"id": "A", "title": "Collide con A", "slots": [{"day": 1, "start": "22:00", "end": "06:00"}],
             "service": "climate.set_temperature", "service_data": {"temperature": 19}, "tags": "notte"},
            {"title": "Multi-giorno", "day": 0, "start": "09:00", "end": "09:00", "end_day": 3, "service": "switch.turn_on"},
            {"title": "Senza servizio", "day": 2, "start": "10:00"},
            {"title": "Giorno sbagliato", "day": 9, "start": "10:00", "service": "a.b"},
            "non-un-oggetto",
            {"id": "Z", "title": "Extra", "day": 4, "start": "07:30", "service": "fan.turn_on", "sconosciuto": 1, "planner_id": "xx"},
        ]
        r = await hass.services.call("import_rules", {"rules": payload, "mode": "merge"})
        assert (r["imported"], r["renamed_ids"], r["total"], len(r["skipped"])) == (3, 1, 4, 3), r
        rules = st.list_rules()
        assert next(x for x in rules if x["id"] == "A")["title"] == "Esistente"        # non sovrascritta
        assert next(x for x in rules if x["title"] == "Multi-giorno")["slots"] == [{"day": 0, "start": "09:00", "end": "09:00", "end_day": 3}]
        notte = next(x for x in rules if x["title"] == "Collide con A")
        assert notte["tags"] == ["notte"] and notte["end"] == "06:00" and notte["id"] != "A"
        extra = next(x for x in rules if x["id"] == "Z")
        assert "sconosciuto" not in extra and "planner_id" not in extra
        # round trip in replace
        doc2 = await hass.services.call("export_rules", {})
        titles = sorted(x["title"] for x in st.list_rules())
        r2 = await hass.services.call("import_rules", {"rules": doc2["rules"], "mode": "replace"})
        assert r2["imported"] == 4 and r2["skipped"] == [] and r2["renamed_ids"] == 0
        assert sorted(x["title"] for x in st.list_rules()) == titles
        # replace con file tutto invalido: errore e regole intatte
        try:
            await hass.services.call("import_rules", {"rules": [{"title": "x"}], "mode": "replace"})
            raise AssertionError("doveva fallire")
        except HomeAssistantError:
            assert len(st.list_rules()) == 4
    asyncio.run(go())


def test_add_rule_unchanged_after_refactor():
    async def go():
        hass, st = await make()
        await hass.services.call("add_rule", {"title": "Nuova", "day": 3, "start": "12:00", "service": "light.turn_off", "tags": "a, b"})
        nuova = next(x for x in st.list_rules() if x["title"] == "Nuova")
        assert nuova["slots"] == [{"day": 3, "start": "12:00"}] and nuova["tags"] == ["a", "b"] and nuova["id"]
        await hass.services.call("add_rule", {"title": "Slots", "service": "light.turn_on",
                                              "slots": [{"day": 1, "start": "07:00", "end": "08:00"}, {"day": 2, "start": "09:00"}]})
        s = next(x for x in st.list_rules() if x["title"] == "Slots")
        assert len(s["slots"]) == 2 and s["day"] == 1 and s["end"] == "08:00"           # specchio dei campi flat
    asyncio.run(go())


if __name__ == "__main__":
    n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); n += 1; print("ok ", name)
    print(f"{n} test passati")
