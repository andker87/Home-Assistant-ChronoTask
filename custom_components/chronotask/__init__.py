from __future__ import annotations

import logging

import homeassistant.helpers.config_validation as cv

from pathlib import Path

from homeassistant.components import frontend
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform

from .const import DOMAIN, CONF_NAME, URL_BASE, INTEGRATION_VERSION, FRONTEND_FILES
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

    Il file JS delle card viene riscritto ad ogni avvio con la stessa URL
    (/local/chronotask/...): chi lo carica da una risorsa Lovelace aggiunta a
    mano, senza versione nell'URL, potrebbe restare su una copia vecchia in
    cache. La route /local di default ha la cache attiva, quindi non basta.
    """
    try:
        await hass.http.async_register_static_paths(
            [StaticPathConfig(URL_BASE, static_dir, False)]
        )
        _LOGGER.debug("ChronoTask: static path no-cache registrato su %s", URL_BASE)
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning(
            "ChronoTask: impossibile registrare %s senza cache (%s): le card "
            "restano servite dalla route /local di default.",
            URL_BASE, err,
        )


def _register_frontend_modules(hass: HomeAssistant) -> None:
    """Carica le card su ogni pagina di HA, senza Lovelace Resources manuali.

    L'URL include la versione dell'integrazione: a ogni release cambia, quindi
    né la cache del browser né una CDN/proxy davanti a HA (es. Cloudflare)
    possono servire una copia vecchia. Funziona sia con dashboard in modalità
    storage sia YAML e non modifica la configurazione dell'utente. Le card
    si registrano solo se non lo sono già, quindi una risorsa aggiunta a mano
    in passato non causa errori.
    """
    for name in FRONTEND_FILES:
        url = f"{URL_BASE}/{name}?v={INTEGRATION_VERSION}"
        try:
            frontend.add_extra_js_url(hass, url)
            _LOGGER.debug("ChronoTask: modulo frontend registrato: %s", url)
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning(
                "ChronoTask: registrazione automatica di %s fallita (%s): "
                "aggiungila a mano tra le Risorse di Lovelace.", url, err,
            )


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Setup globale: copia i JS delle card (in executor) e registra la loro
    URL pubblica senza cache, così un aggiornamento è visibile subito."""

    # Copia i file JS in un thread per non bloccare l'event loop
    await hass.async_add_executor_job(_copy_frontend_files, hass)

    await _register_static_path_no_cache(hass, hass.config.path("www/chronotask"))
    _register_frontend_modules(hass)

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
