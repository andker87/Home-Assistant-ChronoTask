from __future__ import annotations

import re
import logging

from homeassistant import config_entries
from homeassistant.core import callback
import voluptuous as vol

from .const import DOMAIN, CONF_NAME

_LOGGER = logging.getLogger(__name__)


def _slugify(text: str) -> str:
    """Crea uno slug semplice dal nome del planner per l'unique_id."""
    t = str(text or "planner").strip().lower()
    t = re.sub(r"[^a-z0-9]+", "_", t)
    t = t.strip("_")
    return t or "planner"


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors: dict[str, str] = {}

        if user_input is not None:
            title = (user_input.get(CONF_NAME) or "ChronoTask").strip()
            unique_id = _slugify(title)

            # Evita duplicati con lo stesso nome
            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()

            return self.async_create_entry(title=title, data={CONF_NAME: title})

        data_schema = vol.Schema({
            vol.Optional(CONF_NAME, default="ChronoTask"): str,
        })
        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return OptionsFlowHandler(config_entry)


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Permette di rinominare il planner dopo la creazione."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(self, user_input=None):
        errors: dict[str, str] = {}

        if user_input is not None:
            new_name = (user_input.get(CONF_NAME) or "ChronoTask").strip()
            # Aggiorna il titolo dell'entry
            self.hass.config_entries.async_update_entry(
                self._config_entry,
                title=new_name,
                data={**self._config_entry.data, CONF_NAME: new_name},
            )
            return self.async_create_entry(title=new_name, data={})

        current_name = self._config_entry.data.get(CONF_NAME, self._config_entry.title)
        data_schema = vol.Schema({
            vol.Optional(CONF_NAME, default=current_name): str,
        })
        return self.async_show_form(
            step_id="init",
            data_schema=data_schema,
            errors=errors,
        )
