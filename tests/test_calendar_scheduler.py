"""Test di calendario (fasce iniziate il giorno prima), pianificazione unificata,
run_rule_now e aggiornamento unico del sensore.

Eseguibili con:  python tests/test_calendar_scheduler.py   oppure   pytest tests/
"""
import asyncio
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _ha_stubs as stubs  # noqa: E402

stubs.install()
from _loader import load  # noqa: E402

const, slots, storage_mod, scheduler_mod, sensor_mod, services_mod, calendar_mod = load(
    "const", "slots", "storage", "scheduler", "sensor", "services", "calendar")
Clock = stubs.Clock
TZ = Clock.tz


def at(day_offset, hh, mm):
    """Lunedì 2 novembre 2026 + day_offset."""
    return dt.datetime(2026, 11, 2 + day_offset, hh, mm, tzinfo=TZ)


def utc(d):
    return d.astimezone(dt.timezone.utc)


def rule(title, slots_, entity="climate.a", end_service=True, rid=None):
    r = {"id": rid or title, "title": title, "enabled": True,
         "service": "climate.set_temperature", "service_data": {"temperature": 21, "entity_id": entity},
         "slots": slots_, **{k: slots_[0][k] for k in slots_[0]}}
    if end_service:
        r["end_service"] = "climate.turn_off"
        r["end_service_data"] = {"entity_id": entity}
    return r


async def setup(rules):
    stubs.FakeStore.backend.clear()
    hass = stubs.FakeHass()
    store = storage_mod.PlannerStorage(hass, "p1")
    await store.async_load()
    store.set_rules(rules)
    sched = scheduler_mod.WeeklyScheduler(hass, store, "p1")
    sensor = sensor_mod.PlannerRulesSensor("p1", "Casa")
    sensor.hass = hass
    cal = calendar_mod.EntryPlannerCalendar(hass, "p1", "Casa")
    hass.data[const.DOMAIN] = {"p1": {"name": "Casa", "storage": store, "scheduler": sched, "sensor_entity": sensor}}
    hass.states.set("climate.a")
    return hass, store, sched, sensor, cal


def run(coro):
    return asyncio.run(coro)


# --------------------------------------------------------------- calendario

def test_calendar_overnight_ongoing_after_midnight():
    async def go():
        hass, store, sched, sensor, cal = await setup([rule("Notte", [{"day": 0, "start": "22:00", "end": "06:00"}])])
        Clock.current = at(1, 3, 0)                         # martedì 03:00, iniziata lunedì 22:00
        await cal.async_update()
        assert cal.event is not None and cal.event.start == at(0, 22, 0) and cal.event.end == at(1, 6, 0)
        Clock.current = at(1, 7, 0)                         # finita: mostra la prossima (lunedì dopo)
        await cal.async_update()
        assert cal.event.start == at(7, 22, 0)
    run(go())


def test_calendar_multi_day_visible_in_middle_day():
    async def go():
        hass, store, sched, sensor, cal = await setup([rule("Lunga", [{"day": 0, "start": "09:00", "end": "09:00", "end_day": 3}])])
        evs = await cal.async_get_events(hass, at(2, 0, 0), at(2, 23, 59))      # solo il mercoledì
        assert len(evs) == 1 and evs[0].start == at(0, 9, 0) and evs[0].end == at(3, 9, 0)
    run(go())


def test_calendar_range_and_order():
    async def go():
        hass, store, sched, sensor, cal = await setup([
            rule("Sera", [{"day": 0, "start": "18:00", "end": "19:00"}], rid="s"),
            rule("Mattina", [{"day": 1, "start": "07:00", "end": "07:30"}], rid="m"),
        ])
        # l'orario finale (08:00) è prima di quello iniziale (10:00): il martedì va comunque incluso
        evs = await cal.async_get_events(hass, at(0, 10, 0), at(1, 8, 0))
        assert [e.summary for e in evs] == ["Sera", "Mattina"]
        evs = await cal.async_get_events(hass, at(0, 19, 30), at(1, 6, 0))     # nessuna sovrapposizione
        assert evs == []
    run(go())


def test_calendar_ignores_other_planners():
    async def go():
        hass, store, sched, sensor, cal = await setup([rule("A", [{"day": 0, "start": "06:00"}])])
        calls = []
        async def fake_update():
            calls.append(1)
        cal.async_update = fake_update
        await cal._on_changed(type("E", (), {"data": {"planner_id": "altro"}})())
        await cal._on_changed(type("E", (), {"data": {"planner_id": "p1"}})())
        assert len(calls) == 1
    run(go())


# --------------------------------------------------------------- scheduler

def test_schedule_start_and_end_timers():
    async def go():
        Clock.current = at(0, 12, 0)
        hass, store, sched, sensor, cal = await setup([
            rule("Notte", [{"day": 0, "start": "22:00", "end": "06:00"}], rid="n"),
            rule("SenzaFine", [{"day": 2, "start": "08:00", "end": "09:00"}], rid="x", end_service=False),
        ])
        await sched.async_reschedule_all()
        assert set(sched._unsubs) == {"n:0:start", "n:0:end", "x:0:start"}       # nessun end senza end_service
        times = [t[0] for t in hass.timers]
        assert utc(at(0, 22, 0)) in times and utc(at(1, 6, 0)) in times and utc(at(2, 8, 0)) in times
        # esecuzione di un evento: il timer dello stesso slot si ripianifica una settimana dopo
        cb = next(t[1] for t in hass.timers if t[0] == utc(at(0, 22, 0)))
        Clock.current = at(0, 22, 0)
        cb(Clock.current)
        for _ in range(5):
            await asyncio.sleep(0)
        assert utc(at(7, 22, 0)) in [t[0] for t in hass.timers]
        assert hass.services.calls[-1]["service"] == "set_temperature"
    run(go())


def test_run_rule_now_acts_even_on_held_entity():
    async def go():
        Clock.current = at(0, 12, 0)
        hass, store, sched, sensor, cal = await setup([rule("Sala", [{"day": 0, "start": "06:00", "end": "07:00"}])])
        await services_mod.async_setup_services(hass)
        await sched.async_hold(["climate.a"], None, "window")
        await hass.services.call("run_rule_now", {"id": "Sala"})
        c = hass.services.calls[-1]
        assert c["service"] == "set_temperature" and c["data"]["entity_id"] == "climate.a"
        ev = [e for e in hass.bus.events if e[0] == "chronotask_action"][-1]
        assert ev[1]["part"] == "run_now" and ev[2].id == c["context"].id
        assert store.get_hold("climate.a") is not None                  # la pausa resta
        r = rule("Rotta", [{"day": 0, "start": "06:00"}]); r["service"] = "senza_punto"
        store.set_rules(store.list_rules() + [r])
        try:
            await hass.services.call("run_rule_now", {"id": "Rotta"}); raise AssertionError("doveva fallire")
        except stubs.HomeAssistantError:
            pass
    run(go())


# --------------------------------------------------------------- sensore

def test_sensor_refreshed_once_per_change():
    async def go():
        Clock.current = at(0, 12, 0)
        hass, store, sched, sensor, cal = await setup([])
        await services_mod.async_setup_services(hass)
        sensor.written = 0
        await hass.services.call("add_rule", {"title": "Nuova", "day": 1, "start": "07:00", "service": "light.turn_on",
                                              "service_data": {"entity_id": "light.x"}})
        for _ in range(5):
            await asyncio.sleep(0)
        ev = [e for e in hass.bus.events if e[0] == "chronotask_changed"][-1]
        assert ev[1] == {"planner_id": "p1", "sensor_refreshed": True}
        await sensor._on_changed(type("E", (), {"data": ev[1]})())             # l'evento non lo ricalcola
        assert sensor.written == 1, sensor.written
        assert "light.x" in sensor.extra_state_attributes["entities"]
        await sensor._on_changed(type("E", (), {"data": {"planner_id": "p1"}})())   # evento senza flag: sì
        assert sensor.written == 2
    run(go())


if __name__ == "__main__":
    n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); n += 1; print("ok ", name)
    print(f"{n} test passati")
