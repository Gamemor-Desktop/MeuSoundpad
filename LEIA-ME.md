# Meu Soundpad

Toca sons no seu microfone (Discord, jogos etc.) com atalhos globais. Funciona só no Windows.

> **Sons:** este repositório não inclui nenhum áudio. Coloque os seus próprios arquivos na pasta `sons` (veja "Uso"). Use apenas sons que você tem direito de usar.

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

## Uso

- **Adicionar sons:** use o botão **+ Adicionar sons** ou jogue arquivos `.mp3`, `.wav`, `.ogg` ou `.flac` na pasta `sons` e clique em **Atualizar lista**.
- **Tocar:** dê dois cliques no som ou selecione e aperte Enter.
- **Atalho:** selecione um som, clique em **Definir atalho** e aperte a combinação (ex.: `ctrl+1`). Use Esc para cancelar.
- **Parar tudo:** defina um atalho na parte de baixo da janela.
- **Sons sobrepostos:** por padrão só um som toca por vez. Marque **Permitir sons sobrepostos** para tocar vários ao mesmo tempo.
- **Microfone virtual** deve estar em **CABLE Input**. **Ouvir nos fones** toca o som também para você.
- As configurações ficam salvas em `config.json`.

## Problemas comuns

- **Os atalhos não funcionam dentro do jogo:** se o jogo roda como administrador, o app também precisa rodar. Clique com o botão direito em `abrir.bat` e escolha **Executar como administrador**.
- **Ninguém ouve os sons:** confira se o app está tocando em **CABLE Input** e se o Discord ou o jogo está usando **CABLE Output** como microfone.
- **"VB-Cable não encontrado":** instale o VB-Cable e reinicie o PC.
- **O som sai baixo ou estourado:** ajuste os controles de volume ao lado de cada saída.

## Licença

MIT. Veja o arquivo `LICENSE`.
