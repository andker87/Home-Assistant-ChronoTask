"""Test della logica pura dello stato corrente per entità (slots.py).

Eseguibili con:  python tests/test_slots_state.py   oppure   pytest tests/
"""
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _loader import load  # noqa: E402

slots = load("const", "slots")[1]
TZ = ZoneInfo("Europe/Rome")
E = "climate.trv_bagno"


def at(y, m, d, hh, mm, ss=0):
    return datetime(y, m, d, hh, mm, ss, tzinfo=TZ)


# 2026-11-02 è un lunedì
MON, TUE, WED, SUN = 0, 1, 2, 6


def rule(title, slots_, entity=E, enabled=True, rid=None, end_service=True):
    r = {
        "id": rid or title, "title": title, "enabled": enabled,
        "service": "climate.set_temperature",
        "service_data": {"temperature": 25, "entity_id": entity},
        "slots": slots_,
    }
    if end_service:
        r["end_service"] = "climate.turn_off"
        r["end_service_data"] = {"entity_id": entity}
    return r


def state(rules, now, entity=E):
    ev = slots.current_event_for_entity(rules, entity, now)
    return (ev["part"], ev["rule"]["title"]) if ev else None


def test_normal_slot():
    r = [rule("A", [{"day": MON, "start": "06:30", "end": "07:20"}])]
    assert state(r, at(2026, 11, 2, 6, 29)) == ("end", "A")      # prima: stato della settimana scorsa (fine)
    assert state(r, at(2026, 11, 2, 6, 30)) == ("start", "A")    # esattamente all'inizio
    assert state(r, at(2026, 11, 2, 7, 19)) == ("start", "A")
    assert state(r, at(2026, 11, 2, 7, 20)) == ("end", "A")      # esattamente alla fine
    assert state(r, at(2026, 11, 4, 12, 0)) == ("end", "A")      # giorni dopo


def test_slot_without_end_stays_started():
    r = [rule("S", [{"day": MON, "start": "08:00"}], end_service=False)]
    assert state(r, at(2026, 11, 2, 7, 59)) == ("start", "S")    # è ancora quello della settimana scorsa
    assert state(r, at(2026, 11, 2, 8, 0)) == ("start", "S")
    assert state(r, at(2026, 11, 7, 23, 0)) == ("start", "S")    # resta "start" per tutta la settimana


def test_overnight_implicit_end_next_day():
    r = [rule("N", [{"day": MON, "start": "22:00", "end": "06:00"}])]
    assert state(r, at(2026, 11, 2, 23, 0)) == ("start", "N")
    assert state(r, at(2026, 11, 3, 5, 59)) == ("start", "N")    # martedì mattina ancora dentro
    assert state(r, at(2026, 11, 3, 6, 0)) == ("end", "N")


def test_explicit_end_day_multi_day():
    r = [rule("M", [{"day": MON, "start": "09:00", "end": "09:00", "end_day": WED}])]
    assert state(r, at(2026, 11, 3, 12, 0)) == ("start", "M")    # martedì: dentro
    assert state(r, at(2026, 11, 4, 8, 59)) == ("start", "M")
    assert state(r, at(2026, 11, 4, 9, 0)) == ("end", "M")       # mercoledì 09:00 fine


def test_week_wrap_sunday_to_monday():
    r = [rule("W", [{"day": SUN, "start": "23:00", "end": "01:00"}])]
    assert state(r, at(2026, 11, 1, 23, 30)) == ("start", "W")   # domenica sera
    assert state(r, at(2026, 11, 2, 0, 30)) == ("start", "W")    # lunedì 00:30: l'inizio è 'ieri'
    assert state(r, at(2026, 11, 2, 1, 0)) == ("end", "W")


def test_disabled_rules_ignored():
    r = [rule("Off", [{"day": MON, "start": "06:00", "end": "07:00"}], enabled=False)]
    assert state(r, at(2026, 11, 2, 6, 30)) is None
    r.append(rule("On", [{"day": MON, "start": "05:00", "end": "05:30"}]))
    assert state(r, at(2026, 11, 2, 6, 30)) == ("end", "On")     # conta solo la regola abilitata


def test_two_rules_same_entity_last_event_wins():
    r = [rule("Mattina", [{"day": MON, "start": "06:30", "end": "07:20"}]),
         rule("Sera", [{"day": MON, "start": "18:00", "end": "22:00"}])]
    assert state(r, at(2026, 11, 2, 12, 0)) == ("end", "Mattina")
    assert state(r, at(2026, 11, 2, 19, 0)) == ("start", "Sera")
    assert state(r, at(2026, 11, 2, 23, 0)) == ("end", "Sera")


def test_contiguous_slots_start_beats_end_at_same_time():
    r = [rule("Prima", [{"day": MON, "start": "06:00", "end": "07:00"}]),
         rule("Dopo", [{"day": MON, "start": "07:00", "end": "08:00"}])]
    assert state(r, at(2026, 11, 2, 7, 0)) == ("start", "Dopo")
    assert state(r, at(2026, 11, 2, 7, 30)) == ("start", "Dopo")


def test_multi_slot_rule():
    r = [rule("Multi", [{"day": MON, "start": "06:00", "end": "07:00"},
                        {"day": TUE, "start": "18:00", "end": "19:00"}])]
    assert state(r, at(2026, 11, 2, 6, 30)) == ("start", "Multi")
    assert state(r, at(2026, 11, 3, 12, 0)) == ("end", "Multi")
    assert state(r, at(2026, 11, 3, 18, 30)) == ("start", "Multi")


def test_unrelated_entity_returns_none():
    r = [rule("A", [{"day": MON, "start": "06:30", "end": "07:20"}])]
    assert state(r, at(2026, 11, 2, 7, 0), entity="light.altra") is None


def test_next_change():
    r = [rule("A", [{"day": MON, "start": "06:30", "end": "07:20"}])]
    nxt = slots.next_event_time_for_entity(r, E, at(2026, 11, 2, 6, 40))
    assert nxt == at(2026, 11, 2, 7, 20)
    nxt = slots.next_event_time_for_entity(r, E, at(2026, 11, 2, 7, 20))   # strettamente dopo
    assert nxt == at(2026, 11, 9, 6, 30)
    assert slots.next_event_time_for_entity([], E, at(2026, 11, 2, 7, 20)) is None


def test_target_entities_normalization():
    f = slots.target_entities
    assert f({"entity_id": "Climate.A"}) == ["climate.a"]
    assert f({"entity_id": "climate.a, climate.b"}) == ["climate.a", "climate.b"]
    assert f({"entity_id": ["climate.a", "climate.a"], "target": {"entity_id": ["climate.b"]}}) == ["climate.a", "climate.b"]
    assert f({"entity_id": "all"}) == [] and f({"entity_id": "{{ states('x') }}"}) == []
    assert f({"target": {"area_id": "bagno"}}) == [] and f(None) == [] and f({"x": 1}) == []


def test_restrict_and_strip():
    d = {"temperature": 25, "entity_id": ["climate.a", "climate.b"]}
    assert slots.restrict_entities(d, ["climate.b"]) == {"temperature": 25, "entity_id": ["climate.b"]}
    assert d["entity_id"] == ["climate.a", "climate.b"]                      # l'originale non cambia
    s = {"entity_id": "climate.a"}
    assert slots.restrict_entities(s, ["climate.a"]) == {"entity_id": "climate.a"}   # stringa resta stringa
    t = {"target": {"entity_id": ["climate.a", "climate.b"]}, "x": 1}
    assert slots.restrict_entities(t, ["climate.a"]) == {"target": {"entity_id": ["climate.a"]}, "x": 1}
    assert slots.strip_entities({"temperature": 25, "entity_id": "c.a"}) == {"temperature": 25}
    assert slots.strip_entities({"target": {"entity_id": "c.a"}, "x": 1}) == {"x": 1}


def test_entities_view():
    r = [rule("Bagno", [{"day": MON, "start": "06:30", "end": "07:20"}]),
         rule("Disattiva", [{"day": MON, "start": "01:00"}], entity="climate.sala", enabled=False)]
    holds = {E: {"until": "2026-11-02T07:45:00+01:00", "reason": "override", "since": "x"},
             "climate.fantasma": {"until": None, "reason": "away", "since": "x"}}
    v = slots.build_entities_view(r, holds, at(2026, 11, 2, 6, 40))
    b = v[E]
    assert b["scheduled"] == "start" and b["rule"] == "Bagno" and b["since"].startswith("2026-11-02T06:30")
    assert b["expected_service"] == "climate.set_temperature" and b["expected_data"] == {"temperature": 25}
    assert b["next_change"].startswith("2026-11-02T07:20")
    assert b["hold"] is True and b["hold_until"] == "2026-11-02T07:45:00+01:00" and b["hold_reason"] == "override"
    s = v["climate.sala"]                                                     # solo regola disabilitata
    assert s["scheduled"] is None and s["expected_service"] is None and s["hold"] is False
    assert v["climate.fantasma"]["hold"] is True and v["climate.fantasma"]["hold_until"] is None
    v2 = slots.build_entities_view(r, {}, at(2026, 11, 2, 7, 30))             # dopo la fine
    assert v2[E]["scheduled"] == "end" and v2[E]["expected_service"] == "climate.turn_off" and v2[E]["expected_data"] == {}


if __name__ == "__main__":
    n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); n += 1; print("ok ", name)
    print(f"{n} test passati")
