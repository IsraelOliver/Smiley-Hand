# Smiley-Hand 0.5

[![Tests](https://github.com/IsraelOliver/Smiley-Hand/actions/workflows/tests.yml/badge.svg)](https://github.com/IsraelOliver/Smiley-Hand/actions/workflows/tests.yml)

**Controle do computador por gestos, com Python e webcam, no Linux X11 e Windows.**

O Smiley-Hand usa os landmarks e gestos do MediaPipe Tasks para mover o cursor,
clicar com o punho fechado e ajustar o volume principal. Seu objetivo é conectar
pessoas, computadores e futuros dispositivos Arduino/ESP32 por gestos simples.
O pacote interno permanece `hand_control`, preservando as importações existentes.

## Novidades da versão 0.5

- Backends separados: **X11/python-xlib** no Linux e **Win32/ctypes** no Windows.
- Cursor pelo **landmark 8**, preservando mapeamento, espelhamento e suavização
  exponencial da 0.4 validada no Arch Linux.
- **Closed_Fist** substitui a pinça: confirmação de 250 ms, clique único,
  rearmamento temporal e cursor parado durante o fechamento.
- **LED virtual desativado e oculto por padrão**, com código/testes preservados.
- Volume Linux via **wpctl** (pactl como alternativa) e Windows via **pycaw/Core Audio**.
- Padrão de **320×240, até 15 FPS**, uma mão e uma inferência por quadro.
- Interface OpenCV de aproximadamente **960×720**, redimensionável e proporcional,
  com landmarks, classificação bruta, confiança, clique, cursor e volume.
- Dependências por plataforma e testes em matriz Ubuntu/Windows, Python 3.12/3.14.

Não utiliza APIs legacy do MediaPipe, interface web, modelos de linguagem ou
novos modelos de visão. A câmera não é gravada.

## Gestos e atalhos

| Entrada | Comportamento normal |
| --- | --- |
| Movimento do indicador | Move o cursor quando o mouse estiver ativado. |
| `Open_Palm` por 200 ms | Arma inicialmente o clique; não aciona LED no modo normal. |
| `Closed_Fist` por 250 ms | Um clique esquerdo, sem mover o cursor durante a confirmação/execução. |
| `Thumb_Up` por 400 ms | Aumenta o volume em 5 pontos percentuais. |
| `Thumb_Down` por 400 ms | Diminui o volume em 5 pontos percentuais. |
| Polegar mantido | Repete o volume no máximo uma vez a cada 700 ms. |
| Gesto inválido ou confiança insuficiente | Não produz comando de clique/volume. |
| Ausência de mão | Suspende o mouse, cancela confirmação e exige nova abertura para clicar. |
| **M**, com foco na janela | Ativa/desativa o mouse. |
| **ESC**, recebido pela aplicação | Desativa o mouse e invalida os pedidos pendentes. |
| **Q**, botão de fechar ou Ctrl+C | Encerra. |

O mouse sempre inicia **DESATIVADO**. Os gestos de comando precisam alcançar
`--threshold` (padrão **0.6**, inclusive). Não há clique direito, arrastar ou
sequência de clique duplo programada.

## Requisitos e compatibilidade

- **Linux X11** com webcam V4L2, ou **Windows 10/11 x64** com webcam DirectShow.
- CPython regular de 64 bits; matriz de CI em **3.12 e 3.14**. No Arch, mantenha
  seu Python existente. No Windows, os exemplos usam o launcher com Python 3.12;
  para testar 3.14, substitua `-3.12` por `-3.14` ao criar a venv.
- Sessão gráfica local e acesso normal à câmera/áudio. Não execute como administrador.
- Internet somente para instalar dependências e baixar o modelo inicialmente.

[requirements.txt](requirements.txt) mantém MediaPipe 1.1.1 e OpenCV contrib
4.13.0.92 e aplica marcadores: `python-xlib==0.33` só no Linux;
`pycaw==20260927` e `comtypes==1.4.17` só no Windows. O pycaw traz psutil como
 dependência transitiva. Não instale outra distribuição OpenCV junto de
`opencv-contrib-python`, pois todas compartilham `cv2`.

O [pycaw fixado](https://pypi.org/project/pycaw/20260927/) declara suporte a
Python 3.10–3.14; [comtypes](https://pypi.org/project/comtypes/1.4.17/) suporta
Python >=3.9. A compatibilidade completa é verificada por instalação de wheels,
`pip check` e importações na CI. Isso não comprova funcionamento físico de câmera,
DPI ou áudio. Se uma combinação não tiver wheel, use uma venv de outra versão
suportada; não substitua o Python global nem compile bibliotecas neste notebook
como primeira tentativa.

## Instalação no Arch Linux / X11

Com Python, pip e git já disponíveis:

```bash
git clone https://github.com/IsraelOliver/Smiley-Hand.git
cd Smiley-Hand
python3 -m venv .venv
.venv/bin/python -m pip install --dry-run --only-binary=:all: -r requirements.txt
.venv/bin/python -m pip install --only-binary=:all: -r requirements.txt
.venv/bin/python -m pip check
.venv/bin/python -m hand_control --download-model
.venv/bin/python -m hand_control
```

Alternativamente, `bash scripts/setup.sh` prepara a venv, verifica e instala as
dependências e baixa o modelo. Não usa sudo/pacman e não altera pacotes globais.
O volume principal usa `wpctl` quando instalado; procura `pactl` somente se
`wpctl` não existir. O projeto não instala nem reconfigura serviços de áudio.

## Instalação no Windows PowerShell

Com CPython x64 e Git disponíveis, como usuário normal:

```powershell
git clone https://github.com/IsraelOliver/Smiley-Hand.git
cd Smiley-Hand
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --dry-run --only-binary=:all: -r requirements.txt
.\.venv\Scripts\python.exe -m pip install --only-binary=:all: -r requirements.txt
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m hand_control --download-model
.\.venv\Scripts\python.exe -m hand_control
```

Não é necessário ativar a venv nem mudar a política de execução do PowerShell.
O mouse usa `SetCursorPos` e `SendInput`, sem dependência de automação adicional.
O áudio usa o endpoint padrão do Core Audio. Bibliotecas Windows são importadas
somente ao usar seu backend, no worker correspondente.

## Primeiro uso e parâmetros

1. Inicie na sessão gráfica e dê foco à janela OpenCV.
2. Pressione **M**. Movimente o indicador dentro da região de controle desenhada.
3. Mostre `Open_Palm` por pelo menos 200 ms até aparecer **PRONTO**.
4. Feche o punho e mantenha 250 ms. O cursor para e ocorre um único clique.
5. Abra a mão por 200 ms antes de outro clique. Uma saída para outro gesto aceito
   por 200 ms também rearma depois da primeira abertura inicial.
6. Use **ESC** para desativar; **M** alterna; **Q** encerra.

Exemplos Linux (no Windows, troque o executável por `.\.venv\Scripts\python.exe`):

```bash
# Testar mouse sem alterar o volume real:
.venv/bin/python -m hand_control --no-volume-control
# Diagnóstico sem qualquer acesso ao cursor ou ao áudio:
.venv/bin/python -m hand_control --no-mouse-control --no-volume-control
# Ajustar suavização e margem, preservando a resolução padrão:
.venv/bin/python -m hand_control --mouse-smoothing 0.25 --mouse-margin 0.12
# Usar resolução maior se o equipamento permitir:
.venv/bin/python -m hand_control --width 640 --height 480 --fps 15
```

| Opção | Padrão e efeito |
| --- | --- |
| `--camera N` | `0`: índice da câmera. |
| `--width N`, `--height N` | `320`, `240`; limites 160–640 e 120–480. |
| `--fps N` | `15`, entre 1 e 30; o cursor permanece limitado a 15 Hz. |
| `--threshold N` | `0.6`, entre 0 e 1, para comandos classificados. |
| `--mouse-margin N` | `0.12`, entre 0 e 0.45, aplicada em cada borda. |
| `--mouse-smoothing N` | `0.25`, maior que 0 e até 1; menor suaviza mais e responde mais devagar. |
| `--no-mouse-control` | Não cria conexão/worker nem consulta o cursor; M não ativa. |
| `--no-volume-control` | Não cria worker de áudio nem executa leituras/escritas. |
| `--enable-virtual-led` | Modo de demonstração de LED; desabilita completamente o mouse. |
| `--model CAMINHO` | Bundle `.task` alternativo. |
| `--download-model` | Baixa/valida o bundle oficial e encerra. |

## Clique, movimento e segurança

O mapeamento do indicador permanece o mesmo da 0.4: a imagem é espelhada antes da
inferência, sem segunda inversão, e a região entre margens é mapeada à tela.
A suavização é `anterior + alpha * (alvo - anterior)`. Só uma mão é usada.

O clique utiliza o evento `Closed_Fist` já filtrado por confiança e exige 21
landmarks finitos, dentro da imagem, com palma não degenerada. Não confunde
categoria desconhecida com ausência de mão. Uma classificação `None` com tracking
válido não é uma abertura confirmada. Os limiares de detecção/presença/tracking
originais do MediaPipe Tasks permanecem em 0.5; o score de gesto é separado.

A confirmação de 250 ms precisa ser contínua: uma falha antes do clique reinicia
esse prazo. Após clicar, oscilações curtas não rearmam: é necessária uma saída
aceita durante 200 ms. A primeira armação após ativar/perder a mão exige
`Open_Palm`. Durante um punho válido e até uma saída confirmada, não há movimento;
o clique ocorre na posição atual, nunca na ponta do indicador recolhido.

Sem geometria válida, suspende imediatamente os pedidos. Após 500 ms sem mão,
reinicia também a suavização; uma lacuna superior a 500 ms entre quadros válidos
invalida a confirmação. O tempo é monotônico e não bloqueia a câmera.

Um único worker de mouse mantém no máximo um pedido. Pedidos antigos (>150 ms)
ou cancelados são descartados; uma intenção de clique ainda não enviada é
cancelada se o punho deixar de ser aceito. ESC revoga autorização imediatamente
quando recebido. O backend também consulta ESC antes de emitir: fora do foco,
mantenha a tecla pressionada até desativar. Colocar o cursor físico num canto
externo da área da tela é uma proteção adicional. Mova-o para fora e reative com M.
Nenhum mouse/teclado é capturado exclusivamente e nenhuma proteção é desabilitada.
Um clique já entregue ao sistema não pode ser desfeito pelo cancelamento.

### Particularidades do Windows

DPI por monitor é configurado para o processo **antes** do OpenCV. A área de
controle usa o retângulo virtual de todos os monitores, inclusive origens
negativas. O backend consulta a posição efetiva após mover. Após alterar o layout,
desative e reative o mouse para consultar a geometria novamente. Espaços entre
monitores podem ser limitados pelo próprio Windows.

As estruturas `INPUT`/`MOUSEINPUT` têm tipos e alinhamento compatíveis com a ABI
Win32. `SendInput` envia pressão/liberação do botão esquerdo, sem arrastar.
UIPI impede automação de janelas elevadas a partir de um aplicativo normal;
esse limite é respeitado, sem pedir execução como administrador. Área de trabalho
segura, UAC e sessões remotas/restritas não são garantidas.

## Volume

`Thumb_Up`/`Thumb_Down` exigem 400 ms contínuos e repetem no máximo a cada 700 ms.
O intervalo considera também a conclusão para impedir rajadas de backend lento.
Um worker executa no máximo uma operação por vez, sem fila de ajustes.

No Linux, lê `wpctl get-volume @DEFAULT_AUDIO_SINK@` e aplica alvo absoluto com
`wpctl set-volume -l 1.0 @DEFAULT_AUDIO_SINK@ N%`. O alvo calculado fica entre
0% e 100%. A alternativa pactl aplica o mesmo alvo em todos os canais, tomando
o maior como referência. Subprocessos usam lista de argumentos, `shell=False`
e timeout de 1 segundo por chamada.

No Windows, pycaw usa a escala percentual do endpoint padrão, sem chamadas de
shell. COM é inicializado e liberado na mesma thread. Mute não é alterado em
nenhuma plataforma. Leituras periódicas a cada 2 segundos acompanham mudanças
externas; sem backend/saída padrão, o erro é mostrado e novas leituras são
espaçadas. Leituras não impõem limite global: se outro programa passar de 100%,
a próxima ação deste projeto aplica um alvo de no máximo 100%.

## LED opcional

Por padrão não há instância do controlador, comando ou indicador de LED.
`virtual_led.py` e seus testes continuam preservados. Para demonstração:

```bash
.venv/bin/python -m hand_control --enable-virtual-led
```

Nesse modo, `Open_Palm` liga e `Closed_Fist` desliga após 300 ms, como antes.
O mouse fica indisponível para toda a execução, mesmo se M for pressionado.
O volume continua independente. Assim, nunca há clique e comando de LED pelo
mesmo punho fechado.

## Testes e CI

Linux:

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m compileall -q hand_control tests scripts
.venv/bin/python scripts/check_imports.py
.venv/bin/python -m pip check
```

Windows PowerShell:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m compileall -q hand_control tests scripts
.\.venv\Scripts\python.exe scripts/check_imports.py
.\.venv\Scripts\python.exe -m pip check
```

A suíte contém **104 testes**, com backends simulados: nunca move o cursor real,
não modifica o volume e não abre câmera/display. Inclui movimento, ABI Win32,
DPI e área virtual, clique/falhas, limites, rearmamento, confiança, perda de
tracking, LED opcional, COM, encerramento e importações isoladas.

[GitHub Actions](https://github.com/IsraelOliver/Smiley-Hand/actions/workflows/tests.yml)
instala dependências e verifica importações, sintaxe e testes em Ubuntu/Windows
com Python 3.12/3.14, sem webcam ou áudio interativo. Os testes visuais exigem
OpenCV/NumPy; sem essas bibliotecas são ignorados localmente, mas a CI as instala.

**Validação física:** o movimento da **0.4** foi testado pelo autor no Arch/X11.
Esta evolução preserva seu mapeamento e suavização. A **0.5**, especialmente o
novo clique e DPI/áudio Windows, ainda exige teste manual com hardware. Mocks e
CI Windows não provam funcionamento físico. Wayland não é suportado pelo mouse.

## Solução de problemas e limites

- **Dependências:** confira Python x64, wheels e rede. `No matching distribution`
  também pode indicar índice/DNS indisponível. Use dry-run com `-v`. Não instale
  variantes conflitantes do OpenCV. Não mude o Python global para corrigir a venv.
- **Modelo:** execute `--download-model`. O bundle não é versionado; baixa do
  endereço oficial. A validação ZIP/CRC não é verificação criptográfica.
- **Câmera Linux:** confira `/dev/video*`, permissões e programas concorrentes.
  `v4l2-ctl --list-devices` ajuda se já estiver instalado; ajuste `--camera N`.
- **Câmera Windows:** habilite acesso à câmera para aplicativos desktop nas
  configurações de privacidade; feche aplicativos concorrentes e tente outro índice.
- **X11:** confira `XDG_SESSION_TYPE` e `DISPLAY`; use a sessão do mesmo usuário.
  Não desative autenticação X11 nem use sudo. Sem XTEST, o erro só desativa o mouse.
- **Áudio:** confira saída padrão e conexão com a sessão. No Linux, use `wpctl status`;
  no Windows, confira o dispositivo padrão. Não altera serviços ou configurações.
- **Clique não arma:** mostre mão aberta aceita por 200 ms; após um clique, mantenha
  uma saída aceita por 200 ms. Confiança baixa não rearma. O painel distingue
  `PRONTO`, `CONFIRMANDO`, `CLIQUE` e `AGUARDANDO ABERTURA`.
- Não há garantia de FPS/RAM sem medição. Drivers podem ignorar resolução, FPS e
  buffer solicitados. O programa limita o tamanho antes da inferência e mantém
  uma única inferência; a exibição maior aumenta somente o trabalho de renderização.
- O worker daemon do mouse não bloqueia a saída se o servidor travar; pedidos são
  revogados. O encerramento do áudio espera sua operação corrente para liberar COM.
  Chamadas COM nativas não oferecem o mesmo timeout de subprocesso do Linux.
- Próximos passos: validação física Windows, seleção de monitor/saída de áudio,
  medições de desempenho e adaptadores Arduino/ESP32.

## Organização e privacidade

```text
hand_control/
  app.py, __main__.py     # loop e CLI
  camera.py, detector.py  # uma captura e uma inferência
  gestures.py             # eventos aceitos e diagnóstico
  mouse_control.py        # mapeamento, clique temporal e worker
  volume_control.py       # regra temporal e worker de áudio
  backends/               # seleção de plataforma, X11, Win32 e Core Audio
  virtual_led.py          # demonstração opcional
  render.py, model.py     # interface e bundle
scripts/                  # preparação e verificação de importações
models/.gitkeep
tests/
.github/workflows/tests.yml
```

O programa não grava/envia imagens. O MediaPipe possui sua própria
[política de métricas documentada](https://pypi.org/project/mediapipe/1.1.1/).
`.venv`, credenciais, configurações pessoais, caches, modelos e mídias locais
permanecem excluídos pelo `.gitignore`.

Referências: [Win32 SendInput](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-sendinput),
[pycaw](https://pypi.org/project/pycaw/20260927/),
[wpctl](https://pipewire.pages.freedesktop.org/wireplumber/man/wpctl.html).
