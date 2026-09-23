from __future__ import annotations

import logging

import homeassistant.helpers.config_validation as cv

from pathlib import Path

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform

from .const import DOMAIN, CONF_NAME, URL_BASE, INTEGRATION_VERSION
from .storage import PlannerStorage
from .scheduler import WeeklyScheduler
from .services import async_setup_services


CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.CALENDAR, Platform.SENSOR]


def _copy_frontend_files(hass: HomeAssistant) -> None:
    """Copia i file JS da custom_components/chronotask/www/chronotask a /config/www/chronotask,
    sostituendo il placeholder __VERSION__ con la versione dell'integrazione.
    Questa funzione è sincrona e va eseguita in un executor thread.
    """
    src = Path(hass.config.path("custom_components/chronotask/www/chronotask"))
    dst = Path(hass.config.path("www/chronotask"))

    if not src.exists():
        _LOGGER.warning("ChronoTask: cartella sorgente JS non trovata: %s", src)
        return

    dst.mkdir(parents=True, exist_ok=True)

    for file in src.glob("*.js"):
        try:
            content = file.read_text(encoding="utf-8")
            content = content.replace("__VERSION__", INTEGRATION_VERSION)
            dest_file = dst / file.name
            dest_file.write_text(content, encoding="utf-8")
            _LOGGER.info(
                "ChronoTask: file frontend aggiornato: %s (versione %s)",
                dest_file.name, INTEGRATION_VERSION,
            )
        except Exception as e:  # noqa: BLE001
            _LOGGER.error("ChronoTask: errore copia %s: %s", file, e)


async def _register_static_path_no_cache(hass: HomeAssistant, static_dir: str) -> None:
    """Registra /local/chronotask con cache disabilitata.

    Il file JS delle card viene riscritto ad ogni avvio con la stessa
    identica URL (/local/chronotask/...): se il browser lo mette in cache
    in modo aggressivo, un utente può restare bloccato su una versione
    vecchia per mesi nonostante aggiornamenti e riavvii successivi, perché
    non c'è mai una richiesta di rete che gli faccia notare la differenza.
    Da qui l'esigenza di questa registrazione esplicita con cache_headers=False,
    anche se "frontend" già serve /local -> <config>/www di default (ma con
    cache abilitata, quindi non basta).

    HA ha rimosso/rinominato l'API sincrona hass.http.register_static_path
    in alcune versioni recenti a favore di una versione async basata su
    StaticPathConfig: proviamo prima quella, poi ripieghiamo sulla vecchia
    per le versioni di HA che non hanno ancora la nuova.
    """
    try:
        from homeassistant.components.http import StaticPathConfig
        await hass.http.async_register_static_paths(
            [StaticPathConfig(URL_BASE, static_dir, False)]
        )
        _LOGGER.debug("ChronoTask: static path no-cache registrato (async) su %s", URL_BASE)
        return
    except ImportError:
        pass  # HA senza StaticPathConfig: prova l'API legacy sotto
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning(
            "ChronoTask: registrazione static path no-cache (async) fallita per %s: %s",
            URL_BASE, err,
        )
        return

    try:
        hass.http.register_static_path(URL_BASE, static_dir, cache_headers=False)
        _LOGGER.debug("ChronoTask: static path no-cache registrato (legacy) su %s", URL_BASE)
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning(
            "ChronoTask: impossibile registrare %s senza cache (%s). "
            "I file delle card saranno serviti dalla route /local di default "
            "(con cache attiva): dopo un aggiornamento potrebbe servire uno "
            "svuotamento manuale della cache del browser.",
            URL_BASE, err,
        )


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Setup globale: copia i JS delle card (in executor) e registra la loro
    URL pubblica senza cache, così un aggiornamento è visibile subito."""

    # Copia i file JS in un thread per non bloccare l'event loop
    await hass.async_add_executor_job(_copy_frontend_files, hass)

    await _register_static_path_no_cache(hass, hass.config.path("www/chronotask"))

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

    # Registra i servizi una sola volta usando il check idiomatico di HA
    if not hass.services.has_service(DOMAIN, "add_rule"):
        await async_setup_services(hass)

    # Pianifica tutte le regole
    await scheduler.async_reschedule_all()
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload della ConfigEntry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
