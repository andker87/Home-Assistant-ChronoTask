from __future__ import annotations

from homeassistant import config_entries
import voluptuous as vol

from .const import DOMAIN, CONF_NAME


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        if user_input is not None:
            title = user_input.get(CONF_NAME) or "ChronoTask"
            return self.async_create_entry(title=title, data={CONF_NAME: title})
        data_schema = vol.Schema({vol.Optional(CONF_NAME, default="ChronoTask"): str})
        return self.async_show_form(step_id="user", data_schema=data_schema)
