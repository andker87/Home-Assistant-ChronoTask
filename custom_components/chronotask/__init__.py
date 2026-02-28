from __future__ import annotations

import logging
import shutil
from pathlib import Path

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.components import frontend
from homeassistant.const import Platform

from .const import DOMAIN, CONF_NAME, JSMODULES, URL_BASE
from .storage import PlannerStorage
from .scheduler import WeeklyScheduler
from .services import async_setup_services

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.CALENDAR, Platform.SENSOR]


def _copy_frontend_files(hass: HomeAssistant) -> None:
    """Copia i file JS da custom_components/chronotask/www/chronotask a /config/www/chronotask."""
    src = Path(hass.config.path("custom_components/chronotask/www/chronotask"))
    dst = Path(hass.config.path("www/chronotask"))

    if not src.exists():
        _LOGGER.warning("ChronoTask: cartella sorgente JS non trovata: %s", src)
        return

    dst.mkdir(parents=True, exist_ok=True)

    for file in src.glob("*.js"):
        try:
            shutil.copy(file, dst / file.name)
            _LOGGER.debug("ChronoTask: copiato %s → %s", file, dst / file.name)
        except Exception as e:
            _LOGGER.error("ChronoTask: errore copia %s: %s", file, e)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Setup globale: copia i JS, registra static path e carica i JS nel frontend."""

    # Copia i file JS in /config/www/chronotask
    _copy_frontend_files(hass)

    # Static path: /local/chronotask -> /config/www/chronotask
    try:
        hass.http.register_static_path(
            URL_BASE,
            hass.config.path("www/chronotask"),
            cache_headers=True,
        )
        _LOGGER.debug("ChronoTask: static path registrato su %s", URL_BASE)
    except Exception:
        _LOGGER.debug("ChronoTask: static path già registrato")

    # Carica i JS come extra URL (non serve comparire in Resources)
    for module in JSMODULES:
        url = f"{URL_BASE}/{module['filename']}?v={module['version']}"
        try:
            frontend.add_extra_js_url(hass, url)
            _LOGGER.debug("ChronoTask: extra JS URL registrato: %s", url)
        except Exception:
            _LOGGER.exception("ChronoTask: errore durante la registrazione di %s", url)

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Setup della singola ConfigEntry."""
    name = entry.data.get(CONF_NAME) or entry.title or "ChronoTask"

    storage = PlannerStorage(hass, entry.entry_id)
    await storage.async_load()

    scheduler = WeeklyScheduler(hass, storage)

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "name": name,
        "storage": storage,
        "scheduler": scheduler,
    }

    # Avvia le piattaforme
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Registra i servizi una sola volta
    if "listeners" not in hass.data.get(DOMAIN, {}):
        await async_setup_services(hass)
        hass.data[DOMAIN]["listeners"] = True

    # Pianifica
    await scheduler.async_reschedule_all()
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload della ConfigEntry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
