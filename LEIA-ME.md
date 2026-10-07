# Meu Soundpad

Toca sons no seu microfone (Discord, jogos etc.) com atalhos globais. Funciona só no Windows.

> **Sons:** este repositório não inclui áudios de terceiros, só um "ding" de exemplo criado para o tutorial. Coloque os seus próprios arquivos na pasta `sons` (veja "Uso"). Use apenas sons que você tem direito de usar.

## Instalação (uma vez só)

1. **Instale o Python 3** pelo site python.org. Na primeira tela do instalador, marque **"Add python.exe to PATH"**.
2. **Instale o VB-Audio Virtual Cable** (gratuito) pelo site vb-audio.com/Cable. Execute `VBCABLE_Setup_x64.exe` como administrador e **reinicie o PC**.
3. Dê dois cliques em **`abrir.bat`**. Na primeira vez ele instala as bibliotecas e depois abre o app.

## Configuração no Discord ou no jogo

- Em **Microfone / Dispositivo de entrada**, escolha **CABLE Output (VB-Audio Virtual Cable)**.
- No Discord, **desative a supressão de ruído** (Krisp). Ela pode cortar os sons.

### Para a sua voz sair junto com os sons

1. Aperte `Win + R`, digite `mmsys.cpl` e dê Enter.
2. Na aba **Gravação**, abra as **Propriedades** do seu microfone de verdade.
3. Na aba **Escutar**, marque **"Escutar este dispositivo"** e, em "Reproduzir por este dispositivo", escolha **CABLE Input**.
4. Clique em OK.

## Tutorial

Na primeira vez que você abre o app, um tour guiado de 6 passos mostra como instalar o VB-Cable (com link para baixar e botão para verificar), adicionar o som de exemplo, tocar, definir um atalho e configurar o Discord ou o jogo. Para refazer o tour, clique em **? Tutorial** no topo da janela.

## Uso

- **Adicionar sons:** use o botão **+ Adicionar sons**, arraste arquivos para a lista, ou jogue `.mp3`, `.wav`, `.ogg` ou `.flac` na pasta `sons` e clique em **Atualizar lista** (em **Configurações**).
- **Tocar:** dê dois cliques no som ou selecione e aperte Enter.
- **Atalho:** selecione um som, clique em **Definir** (no painel à direita) e aperte a combinação (ex.: `ctrl+1`). Use Esc para cancelar.
- **Parar tudo:** botão vermelho na barra de baixo, onde também fica o atalho para parar.
- **Configurações:** o botão no topo abre a janela com as saídas de áudio (microfone virtual e fones, cada um com volume), sons sobrepostos, comportamento ao repetir o atalho, bandeja e iniciar com o Windows.
- **Sons sobrepostos:** por padrão só um som toca por vez. Marque **Permitir sons sobrepostos** para tocar vários ao mesmo tempo.
- **Parar um som só:** selecione-o e clique em **Parar** no painel do som.
- **Ao repetir o atalho:** escolha se apertar de novo **reinicia** o som ou **alterna** entre tocar e parar.
- **Buscar:** digite no campo de busca (ou aperte `Ctrl+F`) para filtrar a lista. O som que está tocando fica destacado em azul.
- **Volume por som:** selecione um som e ajuste **Volume do som** (0 a 200%).
- **Editar som:** em **✂ Editar som...** você corta o começo e o fim do arquivo e pode ativar o **loop**, que toca até você parar.
- **Bandeja:** com **Ao fechar, ir para a bandeja** ligado, o X da janela só esconde o app. Os atalhos continuam valendo. Use o ícone perto do relógio para abrir ou sair.
- **Iniciar com o Windows:** o app abre escondido na bandeja quando você liga o PC.
- **Microfone virtual** deve estar em **CABLE Input**. **Ouvir nos fones** toca o som também para você.
- As configurações ficam salvas em `config.json`.

## Versão em .exe (sem instalar Python)

- **Baixar:** pegue o `MeuSoundpad.exe` na página de Releases do repositório e coloque numa pasta sua. A pasta `sons` e o `config.json` ficam ao lado dele.
- **Gerar você mesmo:** dê dois cliques em `build.bat`. O arquivo sai em `dist\MeuSoundpad.exe`.
- **Antivírus:** alguns avisam sobre o `.exe` porque o app lê o teclado para os atalhos globais. É um falso positivo comum. Se preferir, rode pelo `abrir.bat`.

## Para quem quer mexer no código

- `soundpad.py` é a interface e `audio.py` tem as funções de áudio.
- `tutorial.py` é o cartão do tour e `tutorial_passos.py` tem os passos e a lógica (testável). `tema.py` guarda cores e fontes.
- O som de exemplo (`exemplos/exemplo-ding.wav`) é sintetizado por `tools/gerar_som_exemplo.py`.
- Testes: `pip install -r requirements-dev.txt` e depois `python -m pytest`.
- Erros ficam registrados em `soundpad.log`, ao lado do programa.

## Problemas comuns

- **Os atalhos não funcionam dentro do jogo:** se o jogo roda como administrador, o app também precisa rodar. Clique com o botão direito em `abrir.bat` e escolha **Executar como administrador**.
- **Ninguém ouve os sons:** confira se o app está tocando em **CABLE Input** e se o Discord ou o jogo está usando **CABLE Output** como microfone.
- **"VB-Cable não encontrado":** instale o VB-Cable e reinicie o PC.
- **O som sai baixo ou estourado:** ajuste o volume de cada saída em **Configurações**.

## Licença

MIT. Veja o arquivo `LICENSE`.
