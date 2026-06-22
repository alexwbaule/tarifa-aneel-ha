# Integração Tarifa ANEEL - Home Assistant ⚡

Esta integração extrai a tarifa base (TE + TUSD) e a Bandeira Tarifária vigente diretamente dos dados abertos da ANEEL, aplicando o cálculo de impostos (ICMS e PIS/COFINS "por dentro") para fornecer o custo real do kWh na sua conta de luz.

Ideal para calcular o custo de recarga de Veículos Elétricos ou o gasto do seu medidor de energia no painel *Energy* do Home Assistant.

## 🛠️ Como instalar via HACS

1. Abra o HACS no seu Home Assistant.
2. Clique nos 3 pontos no canto superior direito e selecione **Repositórios Personalizados (Custom repositories)**.
3. Cole a URL deste repositório: `https://github.com/seu-usuario/seu-repositorio`
4. Na categoria, escolha **Integração (Integration)** e clique em Adicionar.
5. Feche a janela, pesquise por "Tarifa ANEEL" no HACS e clique em **Download**.
6. Reinicie o Home Assistant.

## ⚙️ Configuração

Após reiniciar, vá em **Configurações > Dispositivos e Serviços > Adicionar Integração**.
Pesquise por **Tarifa de Energia ANEEL**.

Uma interface gráfica pedirá os seguintes dados:
* **Distribuidora:** Nome exato da sua concessão (ex: ELETROPAULO, ENEL RJ, CEMIG).
* **Subclasse:** Residencial, Residencial Baixa Renda, etc.
* **ICMS (%):** Alíquota do seu estado.
* **PIS/COFINS (%):** Média mensal da sua fatura.
