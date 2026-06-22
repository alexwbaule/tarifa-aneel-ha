import logging
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DOMAIN, CONF_DISTRIBUIDORA, CONF_SUBCLASSE, CONF_ICMS, CONF_PIS

_LOGGER = logging.getLogger(__name__)

# Intervalo de atualização (1 vez por dia é suficiente para a ANEEL)
SCAN_INTERVAL = timedelta(hours=12)

async def async_setup_entry(hass, config_entry, async_add_entities):
    """Configura o sensor usando os dados preenchidos no Config Flow."""
    distribuidora = config_entry.data.get(CONF_DISTRIBUIDORA)
    subclasse = config_entry.data.get(CONF_SUBCLASSE)
    icms = config_entry.data.get(CONF_ICMS)
    pis = config_entry.data.get(CONF_PIS)

    async_add_entities([TarifaAneelSensor(hass, distribuidora, subclasse, icms, pis)], True)

class TarifaAneelSensor(SensorEntity):
    def __init__(self, hass, distribuidora, subclasse, icms, pis):
        self.hass = hass
        self._distribuidora = distribuidora
        self._subclasse = subclasse
        self._icms = icms
        self._pis = pis
        
        self._attr_name = f"Custo kWh {distribuidora}"
        self._attr_unique_id = f"aneel_kwh_{distribuidora.lower().replace(' ', '_')}"
        # CORREÇÃO: Usando a string direta em vez da constante inexistente
        self._attr_native_unit_of_measurement = "R$/kWh"
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_icon = "mdi:flash"
        
        self._state = None
        self._attributes = {}

    @property
    def native_value(self):
        return self._state

    @property
    def extra_state_attributes(self):
        return self._attributes

    def _parse_valor(self, valor_str):
        if not valor_str or str(valor_str).strip() == "":
            return 0.0
        vl = str(valor_str).replace(',', '.')
        if vl.startswith('.'): vl = '0' + vl
        return float(vl)

    async def async_update(self):
        """Busca os dados na API da ANEEL assincronamente."""
        session = async_get_clientsession(self.hass)
        url = "https://dadosabertos.aneel.gov.br/api/3/action/datastore_search"
        
        # 1. Busca a Tarifa Base
        payload_tarifa = {
            "resource_id": "fcf2906c-7c32-4b9b-a637-054e7a5234f4",
            "filters": {
                "SigAgente": self._distribuidora,
                "DscSubGrupo": "B1",
                "DscSubClasse": self._subclasse,
                "DscBaseTarifaria": "Tarifa de Aplicação",
                "DscModalidadeTarifaria": "Convencional"
            },
            "sort": "DatInicioVigencia desc",
            "limit": 1
        }

        te_kwh, tusd_kwh = 0.0, 0.0
        try:
            async with session.post(url, json=payload_tarifa) as resp:
                data = await resp.json()
                if data.get('success') and data['result']['records']:
                    r = data['result']['records'][0]
                    te_kwh = self._parse_valor(r.get('VlrTE', '0')) / 1000.0
                    tusd_kwh = self._parse_valor(r.get('VlrTUSD', '0')) / 1000.0
        except Exception as e:
            _LOGGER.error(f"Erro ao buscar tarifa ANEEL: {e}")
            return

        # 2. Busca a Bandeira Tarifária
        hoje = date.today()
        meses = [hoje.strftime("%Y-%m"), (hoje - relativedelta(months=1)).strftime("%Y-%m")]
        nome_bandeira, valor_bandeira_kwh = "Desconhecida", 0.0
        
        for anomes in meses:
            payload_bandeira = {
                "resource_id": "0591b8f6-fe54-437b-b72b-1aa2efd46e42",
                "q": anomes,
                "sort": "DatCompetencia desc",
                "limit": 1
            }
            try:
                async with session.post(url, json=payload_bandeira) as resp:
                    data = await resp.json()
                    if data.get('success') and data['result']['records']:
                        r = data['result']['records'][0]
                        nome_bandeira = r.get('NomBandeiraAcionada')
                        valor_bandeira_kwh = self._parse_valor(r.get('VlrAdicionalBandeira', '0')) / 1000.0
                        break
            except Exception:
                continue

        # 3. A Matemática com Impostos Por Dentro
        custo_bruto = te_kwh + tusd_kwh + valor_bandeira_kwh
        taxa = (self._icms + self._pis) / 100.0
        custo_final = custo_bruto / (1.0 - taxa) if taxa < 1.0 else custo_bruto

        # 4. Atualiza o estado e os atributos para o Home Assistant
        self._state = round(custo_final, 5)
        self._attributes = {
            "bandeira_vigente": nome_bandeira,
            "adicional_bandeira_kwh": round(valor_bandeira_kwh, 5),
            "tarifa_energia_te": round(te_kwh, 5),
            "tarifa_uso_tusd": round(tusd_kwh, 5),
            "impostos_perc": f"{(taxa*100):.1f}%"
        }
