import voluptuous as vol
from homeassistant import config_entries
import homeassistant.helpers.config_validation as cv
from .const import DOMAIN, CONF_DISTRIBUIDORA, CONF_SUBCLASSE, CONF_ICMS, CONF_PIS

class AneelConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Gera o menu de configuração na interface do Home Assistant."""
    VERSION = 1

    async def async_step_user(self, user_input=None):
        if user_input is not None:
            # Salva os dados e cria a entidade
            return self.async_create_entry(title=f"Tarifa {user_input[CONF_DISTRIBUIDORA]}", data=user_input)

        # O Formulário que aparecerá na tela
        schema = vol.Schema({
            vol.Required(CONF_DISTRIBUIDORA, default="ELETROPAULO"): str,
            vol.Required(CONF_SUBCLASSE, default="Residencial"): vol.In(["Residencial", "Residencial Baixa Renda", "Rural"]),
            vol.Required(CONF_ICMS, default=18.0): vol.Coerce(float),
            vol.Required(CONF_PIS, default=7.5): vol.Coerce(float),
        })

        return self.async_show_form(step_id="user", data_schema=schema)
