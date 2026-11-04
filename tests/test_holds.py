"""Test di pause / resume / resync con storage, scheduler, servizi e sensore veri
(Home Assistant simulato da tests/_ha_stubs.py).

Eseguibili con:  python tests/test_holds.py   oppure   pytest tests/
"""
import asyncio
import datetime as dt
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _ha_stubs as stubs  # noqa: E402

stubs.install()
from _loader import load  # noqa: E402

const, slots, storage_mod, scheduler_mod, sensor_mod, services_mod = load(
    "const", "slots", "storage", "scheduler", "sensor", "services")
Clock = stubs.Clock
TZ = Clock.tz
HomeAssistantError = stubs.HomeAssistantError


def at(d, hh, mm, day_offset=0):
    """Lunedì 2 novembre 2026 + day_offset, all'ora data."""
    return dt.datetime(2026, 11, 2 + day_offset, hh, mm, tzinfo=TZ)


def rule(title, entities, day=0, start="06:30", end="07:20", rid=None, enabled=True, slots_=None):
    eid = entities if len(entities) > 1 else entities[0]
    return {
        "id": rid or title, "title": title, "enabled": enabled,
        "service": "climate.set_temperature",
        "service_data": {"temperature": 25, "hvac_mode": "heat", "entity_id": list(eid) if isinstance(eid, (list, tuple)) else eid},
        "end_service": "climate.turn_off",
        "end_service_data": {"entity_id": list(eid) if isinstance(eid, (list, tuple)) else eid},
        "slots": slots_ or [{"day": day, "start": start, "end": end}],
        "day": day, "start": start, "end": end,
    }


async def setup(rules, planner="p1", states=None, fresh_store=True):
    """Crea hass + storage + scheduler + sensore per un planner."""
    if fresh_store:
        stubs.FakeStore.backend.clear()
    hass = stubs.FakeHass()
    store = storage_mod.PlannerStorage(hass, planner)
    await store.async_load()
    store.set_rules(rules)
    await store.async_save()
    sched = scheduler_mod.WeeklyScheduler(hass, store, planner)
    sensor = sensor_mod.PlannerRulesSensor(planner, "Termosifoni")
    sensor.hass = hass
    hass.data[const.DOMAIN] = {planner: {"name": "Termosifoni", "storage": store,
                                         "scheduler": sched, "sensor_entity": sensor}}
    await sensor.async_refresh_state()
    for eid in (states or []):
        hass.states.set(eid, "heat")
    return hass, store, sched, sensor


def ent_attr(sensor, eid):
    return sensor.extra_state_attributes["entities"][eid]


def utc(d):
    return d.astimezone(dt.timezone.utc)


def timer_times(hass):
    return [t[0] for t in hass.timers]


def run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------

def test_scheduled_event_skips_held_and_restricts():
    async def go():
        Clock.current = at(0, 6, 30)
        hass, store, sched, sensor = await setup([rule("Bagni", ["climate.a", "climate.b"])], states=["climate.a", "climate.b"])
        seen = {}
        hass.services.on_call = lambda d, s, data: seen.update(sched_at_call=ent_attr(sensor, "climate.b")["scheduled"])
        await sched.async_hold(["climate.a"], None, "override")
        r = store.list_rules()[0]
        await sched._execute_then_resched(r, "start")
        calls = hass.services.calls
        assert len(calls) == 1 and calls[0]["data"]["entity_id"] == ["climate.b"], calls
        assert calls[0]["data"]["temperature"] == 25 and calls[0]["service"] == "set_temperature"
        assert seen["sched_at_call"] == "start"                  # il sensore era GIÀ aggiornato quando è partita la chiamata
        ev = [e for e in hass.bus.events if e[0] == "chronotask_action"]
        assert len(ev) == 1 and ev[0][1]["entity_ids"] == ["climate.b"] and ev[0][1]["part"] == "start"
        assert ev[0][1]["context_id"] == ev[0][2].id == calls[0]["context"].id     # stesso contesto
        assert ev[0][1]["rule_id"] == "Bagni" and ev[0][1]["planner_id"] == "p1"
    run(go())


def test_scheduled_event_all_held_not_called_but_state_refreshed():
    async def go():
        Clock.current = at(0, 6, 30)
        hass, store, sched, sensor = await setup([rule("Sala", ["climate.a"])], states=["climate.a"])
        await sched.async_hold(["climate.a"], None, "window")
        await sched._execute_then_resched(store.list_rules()[0], "start")
        assert hass.services.calls == []
        assert not [e for e in hass.bus.events if e[0] == "chronotask_action"]
        assert ent_attr(sensor, "climate.a")["scheduled"] == "start"       # 'scheduled' avanza anche in pausa
        assert ent_attr(sensor, "climate.a")["hold"] is True
    run(go())


def test_rule_without_entity_runs_unrestricted():
    async def go():
        Clock.current = at(0, 6, 30)
        r = rule("Area", ["climate.a"])
        r["service_data"] = {"temperature": 22, "target": {"area_id": "bagno"}}
        hass, store, sched, sensor = await setup([r])
        await sched._execute_then_resched(store.list_rules()[0], "start")
        assert len(hass.services.calls) == 1 and hass.services.calls[0]["data"]["target"] == {"area_id": "bagno"}
    run(go())


def test_resume_applies_current_state_restricted():
    async def go():
        Clock.current = at(0, 7, 0)                                # dentro la fascia 06:30-07:20
        hass, store, sched, sensor = await setup([rule("Bagni", ["climate.a", "climate.b"])], states=["climate.a", "climate.b"])
        await sched.async_hold(["climate.a"], None, "override")
        res = await sched.async_resume(["climate.a"], apply=True)
        assert res == {"climate.a": {"applied": "start", "rule": "Bagni"}}, res
        c = hass.services.calls
        assert len(c) == 1 and c[0]["data"]["entity_id"] == ["climate.a"] and c[0]["service"] == "set_temperature"
        assert [e for e in hass.bus.events if e[0] == "chronotask_action"][-1][1]["part"] == "resume"
        assert store.get_hold("climate.a") is None
        assert ent_attr(sensor, "climate.a")["hold"] is False
    run(go())


def test_resume_after_end_applies_end_action():
    async def go():
        Clock.current = at(0, 9, 0)                                # fascia finita
        hass, store, sched, sensor = await setup([rule("Sala", ["climate.a"])], states=["climate.a"])
        await sched.async_hold(["climate.a"], None, "away")
        res = await sched.async_resume(["climate.a"])
        assert res["climate.a"]["applied"] == "end"
        assert hass.services.calls[0]["service"] == "turn_off" and hass.services.calls[0]["data"] == {"entity_id": "climate.a"}
    run(go())


def test_resume_no_rule_removes_hold_does_nothing():
    async def go():
        hass, store, sched, sensor = await setup([rule("Sala", ["climate.a"], enabled=False)], states=["climate.a", "light.x"])
        await sched.async_hold(["climate.a", "light.x"], None, None)
        res = await sched.async_resume(["climate.a", "light.x"])
        assert res == {"climate.a": {"applied": None, "rule": None}, "light.x": {"applied": None, "rule": None}}
        assert hass.services.calls == [] and store.list_holds() == {}
    run(go())


def test_resume_apply_false_only_removes_hold():
    async def go():
        Clock.current = at(0, 7, 0)
        hass, store, sched, sensor = await setup([rule("Sala", ["climate.a"])], states=["climate.a"])
        await sched.async_hold(["climate.a"], None, None)
        res = await sched.async_resume(["climate.a"], apply=False)
        assert res["climate.a"] == {"applied": None, "rule": None} and hass.services.calls == []
        assert store.get_hold("climate.a") is None
    run(go())


def test_resume_unavailable_entity_warns_no_retry(caplog=None):
    async def go():
        Clock.current = at(0, 7, 0)
        hass, store, sched, sensor = await setup([rule("Sala", ["climate.a", "climate.b"])])
        hass.states.set("climate.a", "unavailable"); hass.states.set("climate.b", "heat")
        records = []
        h = logging.Handler(); h.emit = lambda rec: records.append(rec)
        logging.getLogger().addHandler(h)
        try:
            await sched.async_hold(["climate.a", "climate.b"], None, None)
            res = await sched.async_resume(["climate.a", "climate.b"])
        finally:
            logging.getLogger().removeHandler(h)
        assert res["climate.a"]["applied"] is None and res["climate.b"]["applied"] == "start"
        assert store.list_holds() == {}                                           # la pausa si toglie comunque
        assert [c["data"]["entity_id"] for c in hass.services.calls] == [["climate.b"]]
        warns = [r for r in records if r.levelno == logging.WARNING and "climate.a" in r.getMessage()]
        assert len(warns) == 1, [r.getMessage() for r in records]
        await asyncio.sleep(0)                                                    # nessun retry in coda
        assert sched._hold_unsubs == {}
    run(go())


def test_hold_minutes_expiry_timer_and_auto_resume():
    async def go():
        Clock.current = at(0, 7, 0)
        hass, store, sched, sensor = await setup([rule("Sala", ["climate.a"], end="08:00")], states=["climate.a"])
        await services_mod.async_setup_services(hass)
        await hass.services.call("hold", {"entity_id": "climate.a", "minutes": 15, "reason": "override"})
        h = store.get_hold("climate.a")
        assert h["reason"] == "override" and h["until"].startswith("2026-11-02T07:15")
        assert list(sched._hold_unsubs) == ["climate.a"] and utc(at(0, 7, 15)) in timer_times(hass)
        assert ent_attr(sensor, "climate.a")["hold_until"] == h["until"]
        # sostituzione: una nuova pausa cancella il vecchio timer
        await hass.services.call("hold", {"entity_id": "climate.a", "minutes": 30, "reason": "window"})
        assert list(sched._hold_unsubs) == ["climate.a"] and store.get_hold("climate.a")["reason"] == "window"
        assert utc(at(0, 7, 30)) in timer_times(hass) and utc(at(0, 7, 15)) not in timer_times(hass)   # il vecchio timer è stato cancellato
        # senza scadenza: il timer della pausa sparisce
        await hass.services.call("hold", {"entity_id": "climate.a"})
        assert sched._hold_unsubs == {} and utc(at(0, 7, 30)) not in timer_times(hass)
        assert store.get_hold("climate.a")["until"] is None
        # di nuovo con scadenza, poi la scadenza scatta -> resume automatico
        await hass.services.call("hold", {"entity_id": "climate.a", "until": "2026-11-02T07:40:00+01:00"})
        cb = next(t[1] for t in hass.timers if t[0] == utc(at(0, 7, 40)))
        Clock.current = at(0, 7, 40)
        cb(Clock.current)
        for _ in range(5):
            await asyncio.sleep(0)
        assert store.get_hold("climate.a") is None and sched._hold_unsubs == {}
        assert [c["service"] for c in hass.services.calls] == ["set_temperature"]       # ripresa la fascia in corso
    run(go())


def test_hold_service_errors():
    async def go():
        Clock.current = at(0, 7, 0)
        hass, store, sched, sensor = await setup([rule("Sala", ["climate.a"])], states=["climate.a"])
        await services_mod.async_setup_services(hass)
        for bad in ({"entity_id": "light.sconosciuta", "minutes": 5},                      # nessun planner la gestisce
                    {"entity_id": "climate.a", "until": "2026-11-02T06:00:00+01:00"},       # nel passato
                    {"entity_id": "climate.a", "planner_id": "nope"}):
            try:
                await hass.services.call("hold", bad); raise AssertionError("doveva fallire: %s" % bad)
            except HomeAssistantError as e:
                assert str(e)
        import voluptuous as vol
        try:
            await hass.services.call("hold", {"entity_id": "climate.a", "minutes": 5, "until": "2026-11-02T08:00:00+01:00"})
            raise AssertionError("minutes+until doveva essere rifiutato")
        except vol.Invalid:
            pass
        await hass.services.call("hold", {"entity_id": "light.libera", "planner_id": "p1"})  # planner esplicito: ok
        assert store.get_hold("light.libera") is not None
    run(go())


def test_holds_persist_and_startup_cleanup():
    async def go():
        Clock.current = at(0, 7, 0)
        hass, store, sched, sensor = await setup([rule("Sala", ["climate.a", "climate.b", "climate.c"])], states=["climate.a"])
        await sched.async_hold(["climate.a"], at(0, 8, 0), "override")      # futura
        await sched.async_hold(["climate.b"], at(0, 7, 10), "override")     # scadrà durante lo spegnimento
        await sched.async_hold(["climate.c"], None, "away")                 # senza scadenza
        # "riavvio": nuovo storage/scheduler sullo stesso file, dopo le 07:10
        Clock.current = at(0, 7, 30)
        hass2 = stubs.FakeHass()
        store2 = storage_mod.PlannerStorage(hass2, "p1"); await store2.async_load()
        assert set(store2.list_holds()) == {"climate.a", "climate.b", "climate.c"}     # persistite
        assert len(store2.list_rules()) == 1                                           # le regole non si perdono
        sched2 = scheduler_mod.WeeklyScheduler(hass2, store2, "p1")
        await sched2.async_setup_holds()
        assert set(store2.list_holds()) == {"climate.a", "climate.c"}                  # la scaduta è sparita
        assert hass2.services.calls == []                                              # e NON è stato applicato nulla
        assert len(hass2.timers) == 1 and hass2.timers[0][0] == at(0, 8, 0).astimezone(dt.timezone.utc)
        store3 = storage_mod.PlannerStorage(stubs.FakeHass(), "p1"); await store3.async_load()
        assert set(store3.list_holds()) == {"climate.a", "climate.c"}                  # anche su disco
        # un file vecchio senza "holds" si carica senza errori
        stubs.FakeStore.backend["chronotask.rules.old"] = {"rules": []}
        old = storage_mod.PlannerStorage(stubs.FakeHass(), "old"); await old.async_load()
        assert old.list_holds() == {}
        # rules.clear() non cancella le pause
        store3.clear(); assert set(store3.list_holds()) == {"climate.a", "climate.c"}
    run(go())


def test_resync_all_skips_held_and_reports():
    async def go():
        Clock.current = at(0, 7, 0)
        rules = [rule("Bagno", ["climate.bagno"]),                          # in fascia -> start
                 rule("Notte", ["climate.notte"], start="01:00", end="02:00"),   # finita -> end
                 rule("Spenta", ["climate.spenta"], enabled=False),        # solo disabilitata -> niente
                 rule("Ferma", ["climate.ferma"])]                          # in pausa
        hass, store, sched, sensor = await setup(rules, states=["climate.bagno", "climate.notte", "climate.spenta", "climate.ferma"])
        await sched.async_hold(["climate.ferma"], None, "window")
        await services_mod.async_setup_services(hass)
        res = await hass.services.call("resync", {})
        assert res["climate.bagno"] == {"applied": "start", "rule": "Bagno"}
        assert res["climate.notte"] == {"applied": "end", "rule": "Notte"}
        assert res["climate.spenta"] == {"applied": None, "rule": None}
        assert res["climate.ferma"]["applied"] is None                        # in pausa: intatta
        done = sorted((c["service"], str(c["data"]["entity_id"])) for c in hass.services.calls)
        assert done == [("set_temperature", "['climate.bagno']"), ("turn_off", "['climate.notte']")] or \
               done == [("set_temperature", "climate.bagno"), ("turn_off", "climate.notte")], done
        # resync su entità specifica via servizio
        hass.services.calls.clear()
        res = await hass.services.call("resync", {"entity_id": ["climate.bagno"]})
        assert res == {"climate.bagno": {"applied": "start", "rule": "Bagno"}} and len(hass.services.calls) == 1
    run(go())


def test_resync_groups_calls_by_rule_and_part():
    async def go():
        Clock.current = at(0, 7, 0)
        hass, store, sched, sensor = await setup([rule("Piano", ["climate.a", "climate.b", "climate.c"])],
                                                 states=["climate.a", "climate.b", "climate.c"])
        await sched.async_resync(None)
        c = hass.services.calls
        assert len(c) == 1 and sorted(c[0]["data"]["entity_id"]) == ["climate.a", "climate.b", "climate.c"]
    run(go())


def test_sensor_attributes_and_next_refresh_timer():
    async def go():
        Clock.current = at(0, 7, 0)
        hass, store, sched, sensor = await setup([rule("Sala", ["climate.a"])], states=["climate.a"])
        a = sensor.extra_state_attributes
        assert a["capabilities"]["hold"] is True and "entities" in a and "rules" in a
        assert "rules" in sensor._unrecorded_attributes and "entities" in sensor._unrecorded_attributes
        e = a["entities"]["climate.a"]
        assert e["scheduled"] == "start" and e["expected_service"] == "climate.set_temperature"
        assert e["expected_data"] == {"temperature": 25, "hvac_mode": "heat"} and e["next_change"].startswith("2026-11-02T07:20")
        # il sensore pianifica da solo il riaggiornamento al prossimo cambio (anche senza servizio da chiamare)
        sensor_timers = [t for t in hass.timers if t[0] == at(0, 7, 20).astimezone(dt.timezone.utc)]
        assert len(sensor_timers) == 1
        Clock.current = at(0, 7, 20)
        sensor_timers[0][1](Clock.current)
        for _ in range(5):
            await asyncio.sleep(0)
        assert sensor.extra_state_attributes["entities"]["climate.a"]["scheduled"] == "end"
    run(go())


def test_two_planners_each_handles_its_entities():
    async def go():
        Clock.current = at(0, 7, 0)
        stubs.FakeStore.backend.clear()
        hass = stubs.FakeHass()
        for pid, ent in (("p1", "climate.a"), ("p2", "light.b")):
            store = storage_mod.PlannerStorage(hass, pid); await store.async_load()
            store.set_rules([rule("R-" + pid, [ent])]); await store.async_save()
            sensor = sensor_mod.PlannerRulesSensor(pid, pid); sensor.hass = hass
            hass.data.setdefault(const.DOMAIN, {})[pid] = {"name": pid, "storage": store, "sensor_entity": sensor,
                                                          "scheduler": scheduler_mod.WeeklyScheduler(hass, store, pid)}
            await sensor.async_refresh_state()
        hass.states.set("climate.a"); hass.states.set("light.b")
        await services_mod.async_setup_services(hass)
        await hass.services.call("hold", {"entity_id": ["climate.a", "light.b"], "minutes": 10})
        assert hass.data[const.DOMAIN]["p1"]["storage"].get_hold("climate.a") and not hass.data[const.DOMAIN]["p1"]["storage"].get_hold("light.b")
        assert hass.data[const.DOMAIN]["p2"]["storage"].get_hold("light.b")
        res = await hass.services.call("resume", {"entity_id": ["climate.a", "light.b", "switch.nessuno"]})
        assert res["climate.a"]["applied"] == "start" and res["light.b"]["applied"] == "start"
        assert res["switch.nessuno"] == {"applied": None, "rule": None}
    run(go())


if __name__ == "__main__":
    n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); n += 1; print("ok ", name)
    print(f"{n} test passati")
