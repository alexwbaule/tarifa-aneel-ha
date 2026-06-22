import logging
from datetime import date
from dateutil.relativedelta import relativedelta

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, CoordinatorEntity, UpdateFailed
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.event import async_track_time_change

from .const import DOMAIN, CONF_DISTRIBUIDORA, CONF_SUBCLASSE, CONF_ICMS, CONF_PIS

_LOGGER = logging.getLogger(__name__)

def _parse_valor(valor_str):
    if not valor_str or str(valor_str).strip() == "": return 0.0
    vl = str(valor_str).replace(',', '.')
    if vl.startswith('.'): vl = '0' + vl
    return float(vl)

async def async_setup_entry(hass, config_entry, async_add_entities):
    """Configura o sensor e o agendamento."""
    distribuidora = config_entry.data.get(CONF_DISTRIBUIDORA)
    subclasse = config_entry.data.get(CONF_SUBCLASSE)
    icms = config_entry.data.get(CONF_ICMS)
    pis = config_entry.data.get(CONF_PIS)
    dist_slug = distribuidora.lower().replace(' ', '_')

    session = async_get_clientsession(hass)

    async def async_update_data():
        """Busca os dados e faz a matemática (só roda no boot ou no dia 1)."""
        url = "https://dadosabertos.aneel.gov.br/api/3/action/datastore_search"
        
        # 1. Tarifa Base
        payload_tarifa = {
            "resource_id": "fcf2906c-7c32-4b9b-a637-054e7a5234f4",
            "filters": {
                "SigAgente": distribuidora, "DscSubGrupo": "B1", "DscSubClasse": subclasse,
                "DscBaseTarifaria": "Tarifa de Aplicação", "DscModalidadeTarifaria": "Convencional"
            },
            "sort": "DatInicioVigencia desc", "limit": 1
        }

        te_kwh, tusd_kwh = 0.0, 0.0
        try:
            async with session.post(url, json=payload_tarifa) as resp:
                data = await resp.json()
                if data.get('success') and data['result']['records']:
                    r = data['result']['records'][0]
                    te_kwh = _parse_valor(r.get('VlrTE', '0')) / 1000.0
                    tusd_kwh = _parse_valor(r.get('VlrTUSD', '0')) / 1000.0
        except Exception as e:
            raise UpdateFailed(f"Erro na ANEEL (Tarifa): {e}")

        # 2. Bandeira
        hoje = date.today()
        meses = [hoje.strftime("%Y-%m"), (hoje - relativedelta(months=1)).strftime("%Y-%m")]
        nome_bandeira, valor_bandeira_kwh = "Desconhecida", 0.0
        
        for anomes in meses:
            payload_bandeira = {
                "resource_id": "0591b8f6-fe54-437b-b72b-1aa2efd46e42",
                "q": anomes, "sort": "DatCompetencia desc", "limit": 1
            }
            try:
                async with session.post(url, json=payload_bandeira) as resp:
                    data = await resp.json()
                    if data.get('success') and data['result']['records']:
                        r = data['result']['records'][0]
                        nome_bandeira = r.get('NomBandeiraAcionada')
                        valor_bandeira_kwh = _parse_valor(r.get('VlrAdicionalBandeira', '0')) / 1000.0
                        break
            except Exception:
                continue

        # 3. Matemática
        custo_bruto = te_kwh + tusd_kwh + valor_bandeira_kwh
        taxa = (icms + pis) / 100.0
        custo_final = custo_bruto / (1.0 - taxa) if taxa < 1.0 else custo_bruto

        return {
            "te_kwh": round(te_kwh, 5), "tusd_kwh": round(tusd_kwh, 5),
            "bandeira_nome": nome_bandeira, "bandeira_valor": round(valor_bandeira_kwh, 5),
            "custo_bruto": round(custo_bruto, 5), "icms": icms, "pis": pis,
            "carga_tributaria": round(taxa * 100, 2), "custo_final": round(custo_final, 5)
        }

    # Desligamos o update_interval automático
    coordinator = DataUpdateCoordinator(
        hass, _LOGGER, name="sensor_tarifa_aneel",
        update_method=async_update_data, update_interval=None,
    )

    # Busca a primeira vez assim que carrega
    await coordinator.async_config_entry_first_refresh()

    # --- A MÁGICA DO DIA 1 ---
    async def atualizar_dia_um(now):
        """Verifica se é dia 1; se for, puxa os dados novos."""
        if now.day == 1:
            _LOGGER.info("Dia 1 detectado: Puxando novos dados da ANEEL.")
            await coordinator.async_request_refresh()

    # Agenda a verificação para rodar todo dia às 03:00 da manhã
    config_entry.async_on_unload(
        async_track_time_change(hass, atualizar_dia_um, hour=3, minute=0, second=0)
    )

    # Adiciona as entidades
    sensores = [
        TarifaEntity(coordinator, distribuidora, dist_slug, "Custo Final kWh", "custo_final", "R$/kWh", "mdi:flash", True),
        TarifaEntity(coordinator, distribuidora, dist_slug, "Tarifa TE", "te_kwh", "R$/kWh", "mdi:transmission-tower", False),
        TarifaEntity(coordinator, distribuidora, dist_slug, "Tarifa TUSD", "tusd_kwh", "R$/kWh", "mdi:power-plug", False),
        TarifaEntity(coordinator, distribuidora, dist_slug, "Bandeira Valor", "bandeira_valor", "R$/kWh", "mdi:flag", False),
        TarifaEntity(coordinator, distribuidora, dist_slug, "Bandeira Vigente", "bandeira_nome", None, "mdi:flag-variant", False),
        TarifaEntity(coordinator, distribuidora, dist_slug, "Custo Bruto (S/ Imposto)", "custo_bruto", "R$/kWh", "mdi:calculator", False),
        TarifaEntity(coordinator, distribuidora, dist_slug, "Carga Tributária", "carga_tributaria", "%", "mdi:percent", False),
    ]

    async_add_entities(sensores)

class TarifaEntity(CoordinatorEntity, SensorEntity):
    def __init__(self, coordinator, distribuidora, dist_slug, name, key, unit, icon, is_main):
        super().__init__(coordinator)
        self._key = key
        self._distribuidora = distribuidora
        self._dist_slug = dist_slug
        
        self._attr_name = f"{name}"
        self._attr_unique_id = f"aneel_{key}_{dist_slug}"
        self._attr_native_unit_of_measurement = unit
        self._attr_icon = icon
        
        if unit in ["R$/kWh", "%"]:
            self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def device_info(self) -> DeviceInfo:
        """Isso agrupa todas as entidades em um único Dispositivo (A 'Janelinha' nativa)."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._dist_slug)},
            name=f"Tarifa {self._distribuidora}",
            manufacturer="ANEEL",
            model="Custo de Energia",
            entry_type=None,
        )

    @property
    def native_value(self):
        return self.coordinator.data.get(self._key)
