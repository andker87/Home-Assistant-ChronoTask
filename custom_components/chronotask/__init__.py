from __future__ import annotations

import logging

import homeassistant.helpers.config_validation as cv

from pathlib import Path

from homeassistant.components import frontend
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform

from .const import (
    DOMAIN,
    CONF_NAME,
    URL_BASE,
    FRONTEND_DIR,
    FRONTEND_URL,
    FRONTEND_FILES,
    FRONTEND_COMMON,
)
from .storage import PlannerStorage
from .scheduler import WeeklyScheduler
from .services import async_setup_services


CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.CALENDAR, Platform.SENSOR]


def _remove_legacy_copies(hass: HomeAssistant) -> None:
    """Fino alla 1.7.1-beta1 le card venivano copiate in <config>/www/chronotask.
    Ora sono servite dalla cartella dell'integrazione: si cancellano le vecchie
    copie (solo i file di ChronoTask) e la cartella, se resta vuota.
    Sincrona: va eseguita in un executor thread."""
    legacy = Path(hass.config.path("www/chronotask"))
    if not legacy.is_dir():
        return
    removed = []
    for name in (*FRONTEND_FILES, FRONTEND_COMMON):
        file = legacy / name
        try:
            if file.is_file():
                file.unlink()
                removed.append(name)
        except OSError as err:
            _LOGGER.warning("ChronoTask: impossibile cancellare la vecchia copia %s: %s", file, err)
    try:
        legacy.rmdir()  # riesce solo se la cartella è vuota
        folder_removed = True
    except OSError:
        folder_removed = False
    if removed or folder_removed:
        _LOGGER.info(
            "ChronoTask: rimosse le vecchie copie delle card da %s: %s%s",
            legacy, ", ".join(removed) or "-", " (cartella eliminata)" if folder_removed else "",
        )


async def _register_frontend(hass: HomeAssistant) -> None:
    """Serve le card dalla cartella dell'integrazione e le fa caricare a HA su
    ogni pagina, senza risorse Lovelace manuali e senza copiare file.

    - FRONTEND_URL (/chronotask/<versione>/...): usato dal caricamento
      automatico. Cambia a ogni release, quindi può stare in cache; anche il
      modulo comune importato dalle card segue la stessa versione.
    - URL_BASE (/local/chronotask/...): compatibilità per le vecchie risorse
      aggiunte a mano; stessa cartella, senza cache.
    """
    static_dir = str(FRONTEND_DIR)
    try:
        await hass.http.async_register_static_paths([
            StaticPathConfig(FRONTEND_URL, static_dir, True),
            StaticPathConfig(URL_BASE, static_dir, False),
        ])
    except Exception as err:  # noqa: BLE001
        _LOGGER.error("ChronoTask: impossibile servire i file delle card (%s)", err)
        return
    for name in FRONTEND_FILES:
        url = f"{FRONTEND_URL}/{name}"
        try:
            frontend.add_extra_js_url(hass, url)
            _LOGGER.debug("ChronoTask: card registrata: %s", url)
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning(
                "ChronoTask: registrazione automatica di %s fallita (%s): "
                "aggiungila a mano tra le Risorse di Lovelace.", url, err,
            )


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Setup globale: rimuove le vecchie copie delle card e le serve dalla
    cartella dell'integrazione."""
    await hass.async_add_executor_job(_remove_legacy_copies, hass)
    await _register_frontend(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Setup della singola ConfigEntry."""
    name = entry.data.get(CONF_NAME) or entry.title or "ChronoTask"

    storage = PlannerStorage(hass, entry.entry_id)
    await storage.async_load()

    scheduler = WeeklyScheduler(hass, storage, entry.entry_id)

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "name": name,
        "storage": storage,
        "scheduler": scheduler,
    }

    # Avvia le piattaforme
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Registra i servizi una sola volta usando il check idiomatico di HA
    if not hass.services.has_service(DOMAIN, "add_rule"):
        await async_setup_services(hass)

    # Pause (hold): quelle scadute durante lo spegnimento si tolgono senza
    # applicare nulla, le altre riprendono il loro timer di scadenza.
    await scheduler.async_setup_holds()

    # Pianifica tutte le regole
    await scheduler.async_reschedule_all()

    # Rinomina dalle opzioni: ricarica l'entry così nomi di sensore, calendario
    # e dispositivo si aggiornano subito, senza riavviare Home Assistant.
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    return True


async def _async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload della ConfigEntry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        ctx = hass.data[DOMAIN].pop(entry.entry_id, None)
        if isinstance(ctx, dict) and ctx.get("scheduler"):
            await ctx["scheduler"].async_stop()
    return unload_ok
