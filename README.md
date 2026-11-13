# Controlart xPortPro para Home Assistant

Integração do Home Assistant para a central de automação **xPortPro**, da Controlart.

Ela lê o catálogo da casa direto da central (o mesmo que o aplicativo do usuário usa) e cria no Home Assistant **todos os dispositivos e cenas cadastrados no projeto**, já separados por ambiente. Funciona pela rede local, sem nuvem e sem conta. O estado chega por aviso da central, sem consulta periódica.

Quem define o que aparece no Home Assistant é o projeto do xConfig PRO: o que está cadastrado e sincronizado na central aparece; o que não está, não aparece. Não há nada a marcar à parte.

## O que aparece no Home Assistant

| No projeto da xPortPro | No Home Assistant |
|---|---|
| Relé na categoria Iluminação, dimmer, RGBW | Luz (liga/desliga, brilho, cor e efeitos) |
| Relé em outra categoria (bomba, portão, tomada etc.) | Interruptor |
| Cortina e persiana | Cortina (abrir, fechar, parar e posição, quando a central sabe a posição) |
| Ar-condicionado no Modo smart | Climatização (temperatura, modo e velocidade) |
| Controle marcado como TV | Reprodutor de mídia (liga/desliga) |
| Sensor de abertura, de presença e ON/OFF | Sensor binário |
| Botões de controle (IR, RF, serial) | Botão |
| Cenas | Cena |

Ainda sem suporte: Multiroom, Receiver e câmeras.

- Cada dispositivo do projeto vira um dispositivo no Home Assistant, **com o mesmo nome** do xConfig PRO.
- Cada **ambiente** do projeto vira uma **área** do Home Assistant, com o mesmo nome, e os dispositivos entram na área do seu ambiente. Se a área ainda não existir, o Home Assistant a cria.
- A central aparece como um dispositivo com o nome do projeto; as cenas ficam nele.
- O que o instalador escondeu do aplicativo do usuário entra **desativado**; dá para ativar em cada entidade.

## Requisitos

- Central xPortPro na mesma rede do Home Assistant, de preferência com IP fixo ou reservado.
- O Home Assistant alcançando a central nas portas **80** (catálogo) e **4998** (estado e comandos).
- Projeto com os dispositivos cadastrados e **sincronizado** pelo xConfig PRO (a central precisa ter o catálogo em `http://<ip da central>/appdata.json`).

## Passo 1: preparar o projeto no xConfig PRO

1. Cadastre os dispositivos da casa no projeto, cada um no seu **ambiente**. O nome do dispositivo e o do ambiente são os que o Home Assistant vai mostrar.
2. Relés que são luz ficam na categoria **Iluminação**; os de outra categoria viram interruptor.
3. Ar-condicionado: use o **Modo smart** para ter climatização com temperatura, modo e velocidade. Sem ele, os comandos aparecem como botões.
4. Controle de TV: marque o controle **como TV** para ter liga/desliga; os demais botões aparecem como botões.
5. Crie as **cenas** que devem poder ser disparadas.
6. Faça o **Sincronizar** com a central. É ele que grava o catálogo que a integração lê.

## Passo 2: instalar a integração

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

Versões novas aparecem no HACS como atualização. Depois de atualizar, reinicie o Home Assistant.

## Passo 3: adicionar a central

1. **Configurações → Dispositivos e serviços → Adicionar integração → Controlart xPortPro**.
2. Informe o IP da central e mantenha a porta `4998`.
3. No final, o Home Assistant mostra os dispositivos criados e deixa conferir as áreas.

A central também pode aparecer sozinha em **Descobertos** quando pedir endereço à rede. Nesse caso, basta confirmar.

## Depois de instalado

- **Novo Sincronizar no xConfig PRO:** a integração relê o catálogo sozinha em cerca de 20 segundos. Dispositivo e cena novos aparecem; os removidos do projeto somem.
- **Tecla na parede, cena, app ou outro assistente** mudando um dispositivo aparece no Home Assistant na hora.
- **Mudar um dispositivo de ambiente** no xConfig PRO não o muda de área no Home Assistant (a área só é sugerida quando o dispositivo é criado). Mude também no Home Assistant, na página do dispositivo.
- **Central fora da rede:** as entidades ficam indisponíveis e voltam sozinhas quando ela volta.

## Quando algo não funciona

| O que aparece | O que fazer |
|---|---|
| "A central não respondeu nesse endereço" | Confira o IP e se o Home Assistant alcança a central nas portas 80 e 4998. |
| "A central está sem o catálogo do projeto" | Faça um Sincronizar pelo xConfig PRO. |
| Dispositivo não aparece | Confira se ele está cadastrado no projeto e faça um Sincronizar. Se estiver escondido do aplicativo, ative a entidade no Home Assistant. |
| Relé aparece como interruptor e devia ser luz | Coloque-o na categoria Iluminação no xConfig PRO e sincronize. |
| Ar-condicionado só com botões | Configure o Modo smart no xConfig PRO e sincronize. |

## Observações

- A integração usa uma única conexão com a central.
- O estado do ar-condicionado é o último comando que a central enviou: o controle remoto do próprio aparelho não é percebido.
- Cortina só de botões não tem posição: o Home Assistant mostra o estado como presumido.
- Na central, cortina em 0 é aberta e em 100 é fechada; no Home Assistant é o contrário, e a integração converte.
