"""Moduli 'homeassistant' minimi per far girare services/scheduler/storage/sensor
nei test senza Home Assistant. Non simulano HA: solo l'API che ChronoTask usa."""
import asyncio
import datetime as _dt
import sys
import types
import uuid

import voluptuous as vol


def _mod(name, **attrs):
    m = types.ModuleType(name)
    m.__dict__.update(attrs)
    sys.modules[name] = m
    return m


class HomeAssistantError(Exception):
    pass


class SupportsResponse:
    ONLY = "only"
    OPTIONAL = "optional"


class Context:
    def __init__(self):
        self.id = uuid.uuid4().hex


class ServiceCall:
    def __init__(self, data):
        self.data = data


class Clock:
    """Orologio controllabile dai test (fuso Europe/Rome)."""
    from zoneinfo import ZoneInfo
    tz = ZoneInfo("Europe/Rome")
    current = _dt.datetime(2026, 11, 2, 12, 0, tzinfo=tz)


class FakeStore:
    """Sostituisce homeassistant.helpers.storage.Store con un dizionario condiviso."""
    backend: dict = {}

    def __init__(self, hass, version, key):
        self.key = key

    async def async_load(self):
        import copy
        return copy.deepcopy(FakeStore.backend.get(self.key))

    async def async_save(self, data):
        import copy
        FakeStore.backend[self.key] = copy.deepcopy(data)


def _entity_ids(value):
    if isinstance(value, str):
        value = value.split(",")
    return [str(v).strip().lower() for v in value if str(v).strip()]


def _datetime(value):
    if isinstance(value, _dt.datetime):
        return value
    return _dt.datetime.fromisoformat(str(value))


def _has_at_most_one_key(*keys):
    def check(obj):
        if sum(1 for k in keys if k in obj) > 1:
            raise vol.Invalid("Solo una chiave tra: " + ", ".join(keys))
        return obj
    return check


def install():
    _mod("homeassistant")
    _mod("homeassistant.core", HomeAssistant=object, ServiceCall=ServiceCall,
         SupportsResponse=SupportsResponse, Context=Context, callback=lambda f: f)
    _mod("homeassistant.exceptions", HomeAssistantError=HomeAssistantError)
    cv = _mod("homeassistant.helpers.config_validation",
              string=str, boolean=bool, ensure_list=lambda v: v if isinstance(v, list) else [v],
              entity_ids=_entity_ids, datetime=_datetime, has_at_most_one_key=_has_at_most_one_key)

    def track(hass, cb, when):
        item = (when, cb)
        hass.timers.append(item)
        return lambda: hass.timers.remove(item) if item in hass.timers else None

    ev = _mod("homeassistant.helpers.event", async_track_point_in_utc_time=track)
    st = _mod("homeassistant.helpers.storage", Store=FakeStore)
    _mod("homeassistant.helpers", config_validation=cv, event=ev, storage=st)

    def parse(s):
        return _dt.datetime.fromisoformat(str(s))

    def as_local(d):
        if d.tzinfo is None:
            d = d.replace(tzinfo=Clock.tz)
        return d.astimezone(Clock.tz)

    dt = _mod("homeassistant.util.dt", now=lambda: Clock.current,
              utcnow=lambda: Clock.current.astimezone(_dt.timezone.utc),
              as_utc=lambda d: d.astimezone(_dt.timezone.utc), as_local=as_local, parse_datetime=parse)
    _mod("homeassistant.util", dt=dt)

    class SensorEntity:
        hass = None

        @property
        def extra_state_attributes(self):
            return getattr(self, "_attr_extra_state_attributes", None)

        def async_write_ha_state(self):
            self.written = getattr(self, "written", 0) + 1

    _mod("homeassistant.components")
    _mod("homeassistant.components.sensor", SensorEntity=SensorEntity)

    class CalendarEvent:
        def __init__(self, start, end, summary, uid=None):
            self.start, self.end, self.summary, self.uid = start, end, summary, uid

    class CalendarEntity:
        hass = None

        def async_write_ha_state(self):
            self.written = getattr(self, "written", 0) + 1

    _mod("homeassistant.components.calendar", CalendarEntity=CalendarEntity, CalendarEvent=CalendarEvent)
    _mod("homeassistant.helpers.entity", DeviceInfo=dict)


class FakeBus:
    def __init__(self):
        self.events = []

    def async_fire(self, name, data=None, context=None):
        self.events.append((name, data, context))


class FakeState:
    def __init__(self, state):
        self.state = state


class FakeStates:
    def __init__(self):
        self._s = {}

    def set(self, eid, state="heat"):
        self._s[eid] = FakeState(state)

    def get(self, eid):
        return self._s.get(eid)


class FakeServices:
    def __init__(self, hass):
        self.hass = hass
        self.registered = {}
        self.calls = []
        self.on_call = None

    def async_register(self, domain, name, fn, schema=None, supports_response=None):
        self.registered[name] = (fn, schema, supports_response)

    async def async_call(self, domain, service, data, blocking=False, context=None):
        self.calls.append({"domain": domain, "service": service, "data": data, "context": context})
        if self.on_call:
            self.on_call(domain, service, data)

    async def call(self, name, data):
        """Chiama un servizio ChronoTask come farebbe HA: validazione + handler."""
        fn, schema, _ = self.registered[name]
        validated = schema(data) if schema else data
        return await fn(ServiceCall(validated))


class FakeHass:
    def __init__(self):
        self.data = {}
        self.bus = FakeBus()
        self.states = FakeStates()
        self.services = FakeServices(self)
        self.timers = []

    def async_create_task(self, coro):
        return asyncio.ensure_future(coro)
