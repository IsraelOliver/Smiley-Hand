# Smiley-Hand

**Controle do computador por gestos, com Python e webcam.**

O Smiley-Hand reconhece gestos das mãos em tempo real para controlar um LED
virtual e o volume do Linux. Seu objetivo é aproximar pessoas, computadores e,
futuramente, dispositivos eletrônicos como Arduino e ESP32 por uma interface
gestual simples.

A versão **0.3** prioriza baixo consumo e uma única janela do OpenCV. O projeto
se chamava Hand Control: o pacote interno permanece `hand_control` para preservar
as importações e os comandos existentes.

## Tecnologias

- **Python** para aplicação, regras temporais e integração com o sistema.
- **OpenCV** para captura da webcam e interface redimensionável.
- **MediaPipe Tasks / GestureRecognizer** para landmarks e classificação.
- **NumPy**, já utilizado pelo processamento de imagens.
- **PipeWire/WirePlumber (`wpctl`)** para controlar o volume no Arch Linux.
  `pactl` é a alternativa quando o executável `wpctl` não está disponível.

Não utiliza APIs legacy do MediaPipe, interface web ou modelos de linguagem.

## Funcionalidades da versão 0.3

- Detecção de uma mão e exibição de seus **21 landmarks**.
- Janela inicial de aproximadamente **960×720**, redimensionável, mantendo a
  proporção da câmera.
- Processamento separado da exibição: **640×480 ou inferior**, FPS configurável.
  Ampliar a janela não aumenta a resolução da inferência.
- Diagnóstico com categoria bruta, confiança, limite atual e motivo de rejeição.
- LED virtual circular com estado, confirmação temporal e progresso.
- Controle real de volume com confirmação temporal, intervalo e limite de 100%.
- Tratamento de erros da câmera e do áudio. Áudio indisponível não interrompe
  a webcam ou o LED.
- Encerramento com **Q**, botão de fechar ou **Ctrl+C**.

## Gestos

Somente gestos com confiança **maior ou igual** a `--threshold` são aceitos.
O padrão é `0.6` (60%).

| Gesto | Ação | Confirmação |
| --- | --- | --- |
| `Open_Palm` — mão aberta | Liga o LED virtual. | 300 ms contínuos. |
| `Closed_Fist` — punho fechado | Desliga o LED virtual. | 300 ms contínuos. |
| `Thumb_Up` — polegar para cima | Aumenta o volume em 5 pontos percentuais. | 400 ms; repetição após no mínimo 700 ms. |
| `Thumb_Down` — polegar para baixo | Diminui o volume em 5 pontos percentuais. | 400 ms; repetição após no mínimo 700 ms. |
| Ausência de mão, `None`, gesto desconhecido/não habilitado ou confiança insuficiente | Nenhum novo comando; mantém os estados anteriores. | Cancela a confirmação pendente. |

O LED inicia **desligado** e não repete comandos quando já está no estado pedido.
Os polegares não alteram o LED; abrir ou fechar a mão não modifica o volume.
Trocar de gesto ou perder a validade reinicia a confirmação. Os tempos usam
`time.monotonic()`, sem esperas no loop da câmera. A ação ocorre no primeiro
quadro válido após o prazo; mudanças entre dois quadros não são observadas.

## Requisitos

- Arch Linux com sessão gráfica local e webcam acessível por V4L2.
- Python, `venv` e pip. O ambiente de desenvolvimento utilizou **Python 3.14,
  Linux x86_64**.
- Internet para preparar dependências e baixar o modelo na primeira instalação.
- `wpctl` para o controle principal de áudio, ou `pactl` como alternativa.
  O projeto não instala ferramentas do sistema automaticamente.

As dependências estão em [requirements.txt](requirements.txt): MediaPipe 1.1.1,
OpenCV contrib 4.13.0.92 e NumPy. Não instale variantes `opencv-python` ou
`headless` junto de `opencv-contrib-python`: elas compartilham `cv2`, e a janela
precisa da distribuição desktop.

A compatibilidade depende de wheels para o Python/arquitetura utilizados. O
script faz um dry-run antes de instalar e aceita apenas wheels, evitando
compilações caras. Consulte as distribuições oficiais do
[MediaPipe](https://pypi.org/project/mediapipe/1.1.1/) e do
[OpenCV](https://pypi.org/project/opencv-contrib-python/4.13.0.92/).

## Instalação

```bash
git clone https://github.com/IsraelOliver/Smiley-Hand.git
cd Smiley-Hand
bash scripts/setup.sh
```

O script cria `.venv`, verifica a resolução das dependências, instala apenas
nesse ambiente, executa `pip check` e baixa o bundle oficial para
`models/gesture_recognizer.task`. Não usa sudo, pacman ou instalações globais.
Se uma etapa falhar, interrompe a preparação.

Para executar as etapas manualmente:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --dry-run --only-binary=:all: --no-cache-dir -r requirements.txt
.venv/bin/python -m pip install --only-binary=:all: --no-cache-dir -r requirements.txt
.venv/bin/python -m pip check
.venv/bin/python -m hand_control --download-model
```

O modelo binário não é versionado. O download é explícito e só precisa ser feito
uma vez. O programa valida a estrutura e o CRC do bundle; isso não é uma
verificação criptográfica de autenticidade. Também é possível baixar
[o modelo oficial, versão 1](https://storage.googleapis.com/mediapipe-models/gesture_recognizer/gesture_recognizer/float16/1/gesture_recognizer.task)
manualmente e salvá-lo no caminho indicado acima.

## Execução

Na raiz do projeto, no terminal da sessão gráfica do usuário:

```bash
.venv/bin/python -m hand_control
```

Para reduzir o consumo, mantendo a janela inicial de 960×720:

```bash
.venv/bin/python -m hand_control --width 320 --height 240 --fps 10 --threshold 0.6
```

Para testar webcam, diagnóstico e LED **sem acessar nem modificar o áudio**:

```bash
.venv/bin/python -m hand_control --no-volume-control
```

Esse modo não detecta backend, não cria a thread de áudio e não executa leituras
ou escritas de volume. Os gestos e diagnósticos continuam aparecendo.

| Opção | Descrição | Padrão |
| --- | --- | --- |
| `--camera N` | Índice de `/dev/videoN`. | `0` |
| `--width N` | Largura máxima processada, de 160 a 640. | `640` |
| `--height N` | Altura máxima processada, de 120 a 480. | `480` |
| `--fps N` | Limite de FPS, de 1 a 30. | `15` |
| `--threshold N` | Confiança mínima, de 0 a 1. | `0.6` |
| `--model CAMINHO` | Bundle `.task` alternativo. | `models/gesture_recognizer.task` |
| `--download-model` | Baixa/valida o modelo e encerra. | Desabilitado. |
| `--no-volume-control` | Desativa todo acesso ao áudio. | Controle habilitado. |

Consulte `.venv/bin/python -m hand_control --help`. Foque a janela do OpenCV e
pressione **Q** para sair.

## Diagnóstico do reconhecimento

O cabeçalho mostra estado, categoria bruta do MediaPipe, confiança e limite.
A confiança pertence à categoria classificada, não à detecção dos landmarks.

| Estado | Significado |
| --- | --- |
| `Nenhuma mao detectada` | Não existem landmarks no resultado. |
| `Mao detectada: gesto None ou desconhecido` | Há landmarks, mas a categoria está ausente, é `None` ou desconhecida. |
| `Gesto conhecido: confianca abaixo do limite` | Um gesto habilitado não alcançou o limite. |
| `Gesto conhecido: fora dos habilitados` | Foi retornado outro gesto conhecido, como `Victory`. |
| `Gesto aceito: ...` | Um dos quatro gestos habilitados alcançou o limite. |

`Bruto: Open_Palm | Confianca: 43.0%` com limite de 60% explica uma rejeição por
score baixo. Já `Bruto: None | Confianca: 91.0%` significa que o score pertence
à categoria `None`. Reduzir `--threshold` não transforma `None` em `Open_Palm`:
altera apenas a aceitação pela aplicação. Sem categoria, a confiança aparece
como `--`. Os textos da janela não usam acentos por limitação da fonte do OpenCV.

## Controle de volume

O backend prioritário é **wpctl/WirePlumber**, usando a **saída padrão** como
usuário normal. Somente se o executável não existir, procura `pactl`. Se `wpctl`
estiver instalado, uma falha de conexão é mostrada e não provoca troca automática
de backend. Não modifica configuração global, serviços ou dispositivos padrão.

Antes de cada ajuste, lê o volume, calcula um alvo absoluto entre 0% e 100%,
aplica-o e relê o resultado. Um aumento de 98% termina em 100%; uma redução de
2% termina em 0%. Nos extremos, não repete escritas sem efeito. O backend usa
comandos equivalentes a:

```bash
wpctl get-volume @DEFAULT_AUDIO_SINK@
wpctl set-volume -l 1.0 @DEFAULT_AUDIO_SINK@ 55%
```

O segundo comando é um exemplo de alvo calculado pela aplicação, não uma etapa
de instalação. `-l 1.0` limita o resultado a 100%, conforme o
[manual oficial do wpctl](https://pipewire.pages.freedesktop.org/wireplumber/man/wpctl.html).
Em `pactl`, o maior canal serve como referência e o alvo é aplicado igualmente a
todos os canais. Nenhum backend modifica mute.

Uma única thread auxiliar executa no máximo uma operação de áudio por vez,
sem fila de ajustes. Os subprocessos são sequenciais, com listas de argumentos,
`shell=False`, checagem de saída e **timeout de 1 segundo por chamada**. A câmera
não espera por eles. O intervalo considera também a conclusão da operação,
evita rajadas e pode ser maior que 700 ms.

O volume é consultado a cada 2 segundos quando o backend está livre para
acompanhar alterações externas. Leituras não modificam áudio. Se outro programa
elevar o volume acima de 100%, a próxima ação do Smiley-Hand aplica um alvo de
no máximo 100%; o projeto não impõe uma política global de volume.

O rodapé mostra volume, barra, gesto de áudio e último ajuste concluído ou erro.
Sem backend, conexão ou saída padrão, exibe `Audio indisponivel: ...` e tenta
nova leitura após 2 segundos. Ao sair, aguarda a operação limitada por timeout.

## Testes automatizados

```bash
.venv/bin/python -m unittest discover -s tests -v
```

A versão 0.3 possui **54 testes**, cobrindo eventos aceitos e diagnóstico, CLI,
limpeza da câmera, LED e temporização, geometria/renderização, seleção do backend,
limites de volume, erros, operação única e desativação do áudio. Os tempos são
simulados e os subprocessos de áudio são substituídos por doubles:
**a suíte não modifica o volume real**.

Os testes de lógica usam a biblioteca padrão. Os visuais usam OpenCV/NumPy e são
ignorados se essas bibliotecas não estiverem disponíveis. Não abrem janela nem
usam webcam. O teste manual continua necessário para avaliar câmera, iluminação,
redimensionamento e integração com o áudio da sessão.

## Solução de problemas

- **Instalação/download:** confira internet, DNS, Python e disponibilidade de
  wheels. `No matching distribution found` também pode indicar falha de índice
  ou rede. Use `-v` no dry-run para investigar. Evite compilar MediaPipe/OpenCV
  neste notebook como primeira correção. Atualizações do Python do Arch podem
  exigir recriar a `.venv`.
- **Modelo:** execute `.venv/bin/python -m hand_control --download-model`.
  Se um arquivo existente estiver inválido, remova apenas esse modelo e baixe
  novamente.
- **Webcam:** confira `ls -l /dev/video*` e, se disponível,
  `v4l2-ctl --list-devices`. Feche programas que estejam usando a câmera e escolha
  o nó de captura com `--camera N`; alguns nós contêm só metadados. Execute no
  desktop com acesso ao dispositivo.
- **Áudio:** confira, como usuário normal, `command -v wpctl pactl`,
  `wpctl get-volume @DEFAULT_AUDIO_SINK@` e `wpctl status`. Use a mesma sessão em
  que o áudio funciona. Para continuar sem integração real, use
  `--no-volume-control`.
- **Janela/bibliotecas nativas:** execute na sessão gráfica local. Erros de
  libGL, PortAudio ou Qt/xcb precisam de diagnóstico da biblioteca indicada.
  `QT_DEBUG_PLUGINS=1 .venv/bin/python -m hand_control --no-volume-control` ajuda
  a investigar Qt. Não instale outra variante do OpenCV para tentar corrigir.
  Instalações de pacotes globais devem ser avaliadas separadamente.

## Estrutura e expansão

```text
hand_control/
  __main__.py         # CLI e mensagens de erro
  app.py              # loop principal e limpeza
  camera.py           # webcam via V4L2
  detector.py         # MediaPipe Tasks GestureRecognizer
  gestures.py         # eventos aceitos, diagnóstico e GestureSink
  virtual_led.py      # estado, confirmação e comandos do LED
  volume_control.py   # backend, regras temporais e worker de áudio
  render.py           # landmarks, painéis e textos
  model.py            # download e validação do bundle
models/.gitkeep       # diretório para modelo baixado localmente
scripts/setup.sh
tests/
requirements.txt
```

Reconhecimento, apresentação e controladores são separados.
`GestureSink.handle(event)` recebe os eventos aceitos por quadro. O controlador
do LED expõe `LedOutput.send(LedCommand.ON/OFF)` para futuros adaptadores físicos,
injetados por `led_output` em `app.run(...)`. A interface lê snapshots imutáveis;
não decide comandos. A versão atual não abre portas seriais.

## Limitações e melhorias futuras

- Uma mão por vez. Posição, iluminação e oclusão podem confundir o modelo.
- Sem garantia de FPS/RAM sem medição no equipamento. O MediaPipe gerencia
  threads internas; o OpenCV usa uma thread e BLAS/OpenMP recebem limite padrão
  de uma thread quando não configurados pelo usuário.
- O driver pode ignorar resolução, FPS ou buffer solicitados. O loop limita o
  tamanho antes da inferência e o ritmo de processamento.
- A adaptação ao tamanho da janela depende do backend gráfico; sem suporte à
  consulta, mantém a última dimensão conhecida.
- O volume atua na saída padrão e não desmuta áudio. Em `pactl`, o ajuste uniforme
  pode alterar o balanço entre canais.
- Possíveis evoluções: adaptadores Arduino/ESP32, seleção de saída de áudio,
  gestos configuráveis e medições de desempenho em mais equipamentos.

## Privacidade e arquivos locais

O programa processa imagens localmente e não implementa gravação ou envio de
capturas. O MediaPipe tem sua própria
[política de métricas documentada](https://pypi.org/project/mediapipe/1.1.1/).

A `.venv`, caches, credenciais, configurações pessoais, modelos baixados e mídias
locais são excluídos pelo `.gitignore`. O repositório contém código, testes,
documentação e `models/.gitkeep`, sem capturas pessoais ou modelo binário.
