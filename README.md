# Controlart xPortPro para Home Assistant

Integração do Home Assistant para a central de automação **xPortPro**, da Controlart.

Ela lê o catálogo da casa direto da central (o mesmo que o aplicativo do usuário usa) e cria os dispositivos e as cenas do projeto no Home Assistant, já separados por ambiente. Funciona pela rede local, sem nuvem e sem conta. O estado chega por aviso da central, sem consulta periódica.

## O que aparece no Home Assistant

| No projeto da xPortPro | No Home Assistant |
|---|---|
| Relé de iluminação, dimmer, RGBW | Luz (liga/desliga, brilho, cor e efeitos) |
| Relé de acionamento | Interruptor |
| Cortina e persiana | Cortina (abrir, fechar, parar e posição, quando a central sabe a posição) |
| Ar-condicionado no Modo smart | Climatização (temperatura, modo e velocidade) |
| Controle marcado como TV | Reprodutor de mídia (liga/desliga) |
| Sensor de abertura, de presença e ON/OFF | Sensor binário |
| Botões de controle (IR, RF, serial) | Botão |
| Cenas | Cena |

Ainda sem suporte: Multiroom, Receiver e câmeras.

O que o instalador escondeu do aplicativo entra desativado; dá para ativar em cada entidade.

## Requisitos

- Central xPortPro na mesma rede do Home Assistant, de preferência com IP fixo ou reservado.
- Projeto sincronizado pelo xConfig PRO (a central precisa ter o catálogo em `http://<ip da central>/appdata.json`).

## Instalação

### Pelo HACS

[![Abrir no HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=fabian-rezende&repository=xportpro-homeassistant&category=integration)

Ou, à mão:

1. HACS → menu de três pontos → **Repositórios personalizados**.
2. Cole `https://github.com/fabian-rezende/xportpro-homeassistant`, tipo **Integração**, e adicione.
3. Abra **Controlart xPortPro** na lista e clique em **Baixar**.
4. Reinicie o Home Assistant.

Não tem o HACS? O passo a passo completo está em [`instalacao-hacs.html`](instalacao-hacs.html).

### Manual

Copie a pasta `custom_components/xportpro` para `<config>/custom_components/xportpro` e reinicie o Home Assistant.

## Adicionar a central

**Configurações → Dispositivos e serviços → Adicionar integração → Controlart xPortPro**, informe o IP da central e mantenha a porta `4998`.

A central também pode aparecer sozinha em "Descobertos" quando pedir endereço à rede.

Depois de um novo Sincronizar no xConfig PRO, a integração relê o catálogo sozinha em cerca de 20 segundos.

## Observações

- A integração usa uma única conexão com a central.
- O estado do ar-condicionado é o último comando que a central enviou: o controle remoto do próprio aparelho não é percebido.
- Cortina só de botões não tem posição: o Home Assistant mostra o estado como presumido.
- Na central, cortina em 0 é aberta e em 100 é fechada; no Home Assistant é o contrário, e a integração converte.
