"""
Meu Soundpad
------------
Toca sons no seu microfone (através do VB-Audio Virtual Cable) e, se você
quiser, também nos seus fones. Cada som pode ter um atalho global, que
funciona mesmo com o jogo ou o Discord em foco.

Como usar: veja o arquivo LEIA-ME.md.
"""

import json
import os
import queue
import shutil
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import keyboard
import numpy as np
import sounddevice as sd
import soundfile as sf

# ---------------------------------------------------------------------------
# Configurações gerais
# ---------------------------------------------------------------------------

PASTA = Path(__file__).resolve().parent
PASTA_SONS = PASTA / "sons"
ARQ_CONFIG = PASTA / "config.json"
EXTENSOES = {".wav", ".mp3", ".ogg", ".flac"}
LIMITE_CACHE = 200 * 1024 * 1024   # bytes de áudio decodificado mantidos na memória
TEMPO_CAPTURA = 15000              # ms até desistir de capturar um atalho


# ---------------------------------------------------------------------------
# Áudio
# ---------------------------------------------------------------------------

def carregar_audio(caminho, taxa_destino, canais_destino):
    """Lê um arquivo de áudio e o converte para a taxa e os canais da saída."""
    dados, taxa = sf.read(str(caminho), dtype="float32", always_2d=True)

    # Ajusta o número de canais (mono/estéreo)
    if canais_destino == 1:
        dados = dados.mean(axis=1, keepdims=True)
    elif dados.shape[1] == 1:
        dados = np.repeat(dados, canais_destino, axis=1)
    else:
        dados = dados[:, :canais_destino]

    # Ajusta a taxa de amostragem (reamostragem linear simples)
    if taxa != taxa_destino and len(dados) > 1:
        n_novo = int(round(len(dados) * taxa_destino / taxa))
        t_antigo = np.arange(len(dados)) / taxa
        t_novo = np.arange(n_novo) / taxa_destino
        dados = np.stack(
            [np.interp(t_novo, t_antigo, dados[:, c]) for c in range(dados.shape[1])],
            axis=1,
        )

    return np.ascontiguousarray(dados, dtype=np.float32)


def limitar(dados, limite=0.8):
    """Limitador suave: só mexe no que passa de `limite`, sem cortar a onda."""
    amplitude = np.abs(dados)
    if amplitude.max(initial=0.0) <= 1.0:
        return dados
    folga = 1.0 - limite
    suave = limite + folga * np.tanh((amplitude - limite) / folga)
    return np.where(amplitude <= limite, dados, np.sign(dados) * suave).astype(np.float32)


class Tocador:
    """Toca um áudio em um dispositivo de saída específico."""

    def __init__(self, dados, dispositivo, taxa, volume, ao_terminar):
        self.dados = np.ascontiguousarray(limitar(dados * volume), dtype=np.float32)
        self.pos = 0
        self.stream = sd.OutputStream(
            device=dispositivo,
            samplerate=taxa,
            channels=dados.shape[1],
            dtype="float32",
            callback=self._callback,
            finished_callback=lambda: ao_terminar(self),
        )
        self.stream.start()

    def _callback(self, saida, frames, tempo, status):
        pedaco = self.dados[self.pos:self.pos + frames]
        n = len(pedaco)
        saida[:n] = pedaco
        if n < frames:
            saida[n:] = 0
            raise sd.CallbackStop
        self.pos += frames

    def parar(self):
        try:
            self.stream.abort()
        except Exception:
            pass
        self.fechar()

    def fechar(self):
        try:
            self.stream.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Aplicativo
# ---------------------------------------------------------------------------

class App:
    def __init__(self, root):
        self.root = root
        self.fila = queue.Queue()      # tarefas vindas de outras threads
        self.tocadores = []
        self.cache = {}                # (arquivo, mtime, taxa, canais) -> áudio
        self._cache_bytes = 0
        self._trava_cache = threading.Lock()
        self._geracao = 0              # muda ao parar: cancela carregamentos pendentes
        self._geracao_lista = 0        # muda ao recarregar a lista: cancela pré-carga
        self._salvar_agendado = None
        self.sons = []
        self.capturando = False
        self._captura_teclas = []
        self._ao_capturar = None
        self._token_captura = 0
        self._combos = []              # atalhos ativos: (teclas, ação)
        self._pressionadas = set()     # teclas apertadas neste momento
        self._gancho = None

        PASTA_SONS.mkdir(exist_ok=True)
        self.config = self._ler_config()

        root.title("Meu Soundpad")
        root.geometry("600x540")
        root.minsize(500, 440)

        self.dispositivos = self._listar_dispositivos()
        self._montar_interface()
        self._carregar_lista()

        if not any("cable input" in nome.lower() for _, nome in self.dispositivos):
            self.status("VB-Cable não encontrado. Veja o LEIA-ME para instalar.")

        root.protocol("WM_DELETE_WINDOW", self.fechar)
        self._processar_fila()

    # ----- interface ------------------------------------------------------

    def _montar_interface(self):
        nomes = [nome for _, nome in self.dispositivos]

        # Saídas de áudio
        quadro = ttk.LabelFrame(self.root, text="Saídas de áudio", padding=8)
        quadro.pack(fill="x", padx=10, pady=(10, 5))
        quadro.columnconfigure(1, weight=1)

        ttk.Label(quadro, text="Microfone virtual:").grid(row=0, column=0, sticky="w")
        self.var_mic = tk.StringVar(
            value=self._escolher_inicial(self.config.get("saida_mic"), "cable input"))
        ttk.Combobox(quadro, textvariable=self.var_mic, values=nomes,
                     state="readonly").grid(row=0, column=1, sticky="ew", padx=6)
        self.var_vol_mic = tk.DoubleVar(value=self.config.get("volume_mic", 80))
        ttk.Label(quadro, text="Vol.").grid(row=0, column=2)
        ttk.Scale(quadro, from_=0, to=150, variable=self.var_vol_mic,
                  length=110).grid(row=0, column=3)

        self.var_ouvir = tk.BooleanVar(value=self.config.get("ouvir", True))
        ttk.Checkbutton(quadro, text="Ouvir nos fones:",
                        variable=self.var_ouvir).grid(row=1, column=0, sticky="w", pady=(6, 0))
        self.var_fone = tk.StringVar(
            value=self._escolher_inicial(self.config.get("saida_fone"), None))
        ttk.Combobox(quadro, textvariable=self.var_fone, values=nomes,
                     state="readonly").grid(row=1, column=1, sticky="ew", padx=6, pady=(6, 0))
        self.var_vol_fone = tk.DoubleVar(value=self.config.get("volume_fone", 60))
        ttk.Label(quadro, text="Vol.").grid(row=1, column=2, pady=(6, 0))
        ttk.Scale(quadro, from_=0, to=150, variable=self.var_vol_fone,
                  length=110).grid(row=1, column=3, pady=(6, 0))

        self.var_sobrepor = tk.BooleanVar(value=self.config.get("sobrepor", False))
        ttk.Checkbutton(quadro, text="Permitir sons sobrepostos",
                        variable=self.var_sobrepor).grid(
            row=2, column=0, columnspan=2, sticky="w", pady=(6, 0))

        # Salva a configuração sempre que algo mudar (com um pequeno atraso)
        for var in (self.var_mic, self.var_fone, self.var_vol_mic,
                    self.var_vol_fone, self.var_ouvir, self.var_sobrepor):
            var.trace_add("write", lambda *args: self._agendar_salvar())

        # Lista de sons
        quadro_lista = ttk.Frame(self.root)
        quadro_lista.pack(fill="both", expand=True, padx=10, pady=5)
        self.lista = ttk.Treeview(quadro_lista, columns=("som", "atalho"),
                                  show="headings", selectmode="browse")
        self.lista.heading("som", text="Som")
        self.lista.heading("atalho", text="Atalho")
        self.lista.column("som", width=340)
        self.lista.column("atalho", width=150, anchor="center")
        barra = ttk.Scrollbar(quadro_lista, orient="vertical", command=self.lista.yview)
        self.lista.configure(yscrollcommand=barra.set)
        self.lista.pack(side="left", fill="both", expand=True)
        barra.pack(side="right", fill="y")
        self.lista.bind("<Double-1>", lambda e: self.tocar_selecionado())
        self.lista.bind("<Return>", lambda e: self.tocar_selecionado())

        # Botões
        botoes = ttk.Frame(self.root)
        botoes.pack(fill="x", padx=10, pady=5)
        linha1 = [
            ("▶ Tocar", self.tocar_selecionado),
            ("■ Parar tudo", self.parar),
            ("Definir atalho", self.definir_atalho_som),
            ("Limpar atalho", self.limpar_atalho_som),
        ]
        linha2 = [
            ("+ Adicionar sons", self.adicionar_sons),
            ("Abrir pasta de sons", self.abrir_pasta),
            ("Atualizar lista", self._carregar_lista),
        ]
        for coluna, (texto, comando) in enumerate(linha1):
            ttk.Button(botoes, text=texto, command=comando).grid(
                row=0, column=coluna, sticky="ew", padx=2, pady=2)
        for coluna, (texto, comando) in enumerate(linha2):
            ttk.Button(botoes, text=texto, command=comando).grid(
                row=1, column=coluna, sticky="ew", padx=2, pady=2)
        for coluna in range(4):
            botoes.columnconfigure(coluna, weight=1)

        # Atalho para parar
        quadro_parar = ttk.Frame(self.root)
        quadro_parar.pack(fill="x", padx=10, pady=(0, 5))
        ttk.Label(quadro_parar, text="Atalho para parar tudo:").pack(side="left")
        self.lbl_parar = ttk.Label(quadro_parar, text=self.config.get("atalho_parar") or "—",
                                   font=("Segoe UI", 9, "bold"))
        self.lbl_parar.pack(side="left", padx=6)
        ttk.Button(quadro_parar, text="Definir",
                   command=self.definir_atalho_parar).pack(side="left")
        ttk.Button(quadro_parar, text="Limpar",
                   command=self.limpar_atalho_parar).pack(side="left", padx=4)

        # Barra de status
        self.lbl_status = ttk.Label(self.root, text="Pronto", relief="sunken",
                                    anchor="w", padding=(6, 2))
        self.lbl_status.pack(fill="x", side="bottom")

    def status(self, texto):
        self.lbl_status.config(text=texto)

    # ----- dispositivos ---------------------------------------------------

    def _listar_dispositivos(self):
        # Usa só a API de áudio padrão do Windows (MME), que aceita qualquer
        # taxa de amostragem e evita dispositivos repetidos na lista.
        api = sd.default.hostapi
        return [
            (i, d["name"])
            for i, d in enumerate(sd.query_devices())
            if d["hostapi"] == api and d["max_output_channels"] > 0
        ]

    def _escolher_inicial(self, salvo, procurar):
        nomes = [nome for _, nome in self.dispositivos]
        if salvo in nomes:
            return salvo
        if procurar:
            for nome in nomes:
                if procurar in nome.lower():
                    return nome
            return ""
        padrao = sd.query_hostapis(sd.default.hostapi)["default_output_device"]
        for indice, nome in self.dispositivos:
            if indice == padrao:
                return nome
        return nomes[0] if nomes else ""

    def _indice(self, nome):
        for indice, n in self.dispositivos:
            if n == nome:
                return indice
        return None

    # ----- lista de sons --------------------------------------------------

    def _carregar_lista(self):
        self.sons = sorted(
            (p.name for p in PASTA_SONS.iterdir()
             if p.is_file() and p.suffix.lower() in EXTENSOES),
            key=str.lower,
        )
        self.lista.delete(*self.lista.get_children())
        for i, nome in enumerate(self.sons):
            atalho = self.config["atalhos"].get(nome) or "—"
            self.lista.insert("", "end", iid=str(i), values=(nome, atalho))
        self._registrar_atalhos()
        if not self.sons:
            self.status("Nenhum som ainda. Use \"+ Adicionar sons\".")
        else:
            self._pre_carregar()

    def _pre_carregar(self):
        """Decodifica os sons em segundo plano para o primeiro disparo ser instantâneo."""
        self._geracao_lista += 1
        geracao = self._geracao_lista
        specs = self._especificacoes()
        arquivos = [PASTA_SONS / nome for nome in self.sons]

        def trabalho():
            for caminho in arquivos:
                for _, _, taxa, canais in specs:
                    if geracao != self._geracao_lista or self._cache_bytes > LIMITE_CACHE // 2:
                        return
                    try:
                        self._audio(caminho, taxa, canais)
                    except Exception:
                        pass

        threading.Thread(target=trabalho, daemon=True).start()

    def _selecionado(self):
        selecao = self.lista.selection()
        if not selecao:
            self.status("Selecione um som na lista primeiro.")
            return None
        return self.sons[int(selecao[0])]

    def adicionar_sons(self):
        arquivos = filedialog.askopenfilenames(
            title="Escolha os sons",
            filetypes=[("Áudio", "*.wav *.mp3 *.ogg *.flac"), ("Todos", "*.*")],
        )
        copiados = 0
        for arquivo in arquivos:
            origem = Path(arquivo)
            destino = PASTA_SONS / origem.name
            if origem.suffix.lower() in EXTENSOES and origem.resolve() != destino.resolve():
                shutil.copy2(origem, destino)
                copiados += 1
        self._carregar_lista()
        if copiados:
            self.status(f"{copiados} som(ns) adicionado(s).")

    def abrir_pasta(self):
        os.startfile(PASTA_SONS)

    # ----- tocar ----------------------------------------------------------

    def tocar_selecionado(self):
        nome = self._selecionado()
        if nome:
            self.tocar(nome)

    def _especificacoes(self):
        """Saídas escolhidas: lista de (dispositivo, volume, taxa, canais)."""
        saidas = []
        mic = self._indice(self.var_mic.get())
        if mic is not None:
            saidas.append((mic, self.var_vol_mic.get() / 100))
        if self.var_ouvir.get():
            fone = self._indice(self.var_fone.get())
            if fone is not None and fone != mic:
                saidas.append((fone, self.var_vol_fone.get() / 100))
        specs = []
        for indice, volume in saidas:
            info = sd.query_devices(indice)
            specs.append((indice, volume, int(info["default_samplerate"]),
                          min(2, info["max_output_channels"])))
        return specs

    def tocar(self, nome):
        if not self.var_sobrepor.get():
            self.parar()  # um som por vez, como no Soundpad
        caminho = PASTA_SONS / nome
        if not caminho.exists():
            self.status(f"Arquivo não encontrado: {nome}")
            return

        specs = self._especificacoes()
        if not specs:
            self.status("Escolha pelo menos uma saída de áudio.")
            return

        geracao = self._geracao
        if all(self._chave(caminho, t, c) in self.cache for _, _, t, c in specs):
            self._iniciar(nome, caminho, specs, geracao)
        else:
            # Decodificar um arquivo grande demora: faz isso fora da interface.
            self.status(f"Carregando: {nome}...")
            threading.Thread(target=self._carregar_e_tocar,
                             args=(nome, caminho, specs, geracao), daemon=True).start()

    def _carregar_e_tocar(self, nome, caminho, specs, geracao):
        try:
            for _, _, taxa, canais in specs:
                self._audio(caminho, taxa, canais)
        except Exception as erro:
            self.na_interface(self.status, f"Erro ao carregar {nome}: {erro}")
            return
        self.na_interface(self._iniciar, nome, caminho, specs, geracao)

    def _iniciar(self, nome, caminho, specs, geracao):
        if geracao != self._geracao:
            return  # alguém mandou parar (ou tocar outro som) enquanto carregava
        novos = []
        for indice, volume, taxa, canais in specs:
            try:
                dados = self._audio(caminho, taxa, canais)
                novos.append(Tocador(dados, indice, taxa, volume, self._ao_terminar))
            except Exception as erro:
                for tocador in novos:
                    tocador.parar()
                self.status(f"Erro ao tocar {nome}: {erro}")
                return
        self.tocadores.extend(novos)
        self.status(f"Tocando: {nome}")

    @staticmethod
    def _chave(caminho, taxa, canais):
        return (str(caminho), caminho.stat().st_mtime, taxa, canais)

    def _audio(self, caminho, taxa, canais):
        chave = self._chave(caminho, taxa, canais)
        with self._trava_cache:
            dados = self.cache.get(chave)
        if dados is not None:
            return dados
        dados = carregar_audio(caminho, taxa, canais)  # lento: fora da trava
        with self._trava_cache:
            if chave not in self.cache:
                # descarta os mais antigos até caber
                while self.cache and self._cache_bytes + dados.nbytes > LIMITE_CACHE:
                    antigo = self.cache.pop(next(iter(self.cache)))
                    self._cache_bytes -= antigo.nbytes
                self.cache[chave] = dados
                self._cache_bytes += dados.nbytes
        return dados

    def _ao_terminar(self, tocador):
        # Chamado pela thread de áudio: repassa para a thread da interface.
        self.na_interface(self._remover_tocador, tocador)

    def _remover_tocador(self, tocador):
        if tocador in self.tocadores:
            self.tocadores.remove(tocador)
            if not self.tocadores:
                self.status("Pronto")
        tocador.fechar()

    def parar(self):
        self._geracao += 1  # cancela sons que ainda estão sendo carregados
        for tocador in self.tocadores:
            tocador.parar()
        if self.tocadores:
            self.status("Parado.")
        self.tocadores = []

    # ----- atalhos globais ------------------------------------------------

    # Os atalhos são verificados "na mão" em vez de usar keyboard.add_hotkey,
    # porque o add_hotkey só dispara quando APENAS as teclas do atalho estão
    # apertadas. Assim o atalho funciona mesmo segurando outra tecla, como
    # a do "aperte para falar".

    @staticmethod
    def _interpretar(combo):
        """Converte 'ctrl+1' em uma lista de conjuntos de códigos de tecla."""
        try:
            passos = keyboard.parse_hotkey(combo)
        except (ValueError, TypeError):
            return None
        if len(passos) != 1:
            return None
        return [set(codigos) for codigos in passos[0]]

    def _registrar_atalhos(self):
        combos = []
        for nome, combo in self.config["atalhos"].items():
            if combo and nome in self.sons:
                teclas = self._interpretar(combo)
                if teclas:
                    combos.append((teclas, lambda n=nome: self.na_interface(self.tocar, n)))
        combo = self.config.get("atalho_parar")
        if combo:
            teclas = self._interpretar(combo)
            if teclas:
                combos.append((teclas, lambda: self.na_interface(self.parar)))
        self._combos = combos
        if self._gancho is None:
            self._gancho = keyboard.hook(self._ao_tecla)

    def _ao_tecla(self, evento):
        # Chamado pela thread do teclado a cada tecla apertada ou solta.
        codigo = evento.scan_code
        if evento.event_type == keyboard.KEY_UP:
            self._pressionadas.discard(codigo)
            if self.capturando and self._captura_teclas and not self._pressionadas:
                # Soltou tudo: a combinação está completa.
                teclas, self._captura_teclas = self._captura_teclas, []
                self.capturando = False
                combo = keyboard.get_hotkey_name(teclas)
                self.na_interface(self._fim_captura, combo, self._ao_capturar)
            return
        if codigo in self._pressionadas:
            return  # tecla sendo segurada (repetição automática do Windows)
        self._pressionadas.add(codigo)
        if self.capturando:
            if evento.name and evento.name not in self._captura_teclas:
                self._captura_teclas.append(evento.name)
            return
        for teclas, acao in self._combos:
            # Dispara quando esta tecla completa o atalho, mesmo com outras
            # teclas extras apertadas junto.
            if any(codigo in t for t in teclas) and all(t & self._pressionadas for t in teclas):
                acao()

    def _capturar_atalho(self, ao_capturar):
        if self.capturando:
            return
        # Enquanto captura, os atalhos ficam pausados; _ao_tecla junta as teclas
        # e chama _fim_captura quando todas forem soltas.
        self._captura_teclas = []
        self._ao_capturar = ao_capturar
        self._token_captura += 1
        self.capturando = True
        self.status("Pressione a combinação de teclas... (Esc cancela)")
        self.root.after(TEMPO_CAPTURA, self._tempo_captura, self._token_captura)

    def _tempo_captura(self, token):
        if self.capturando and token == self._token_captura:
            self._captura_teclas = []
            self._fim_captura(None, self._ao_capturar)

    def _fim_captura(self, combo, ao_capturar):
        self.capturando = False
        if combo and combo != "esc":
            # Um atalho só pode pertencer a uma ação
            for nome, atual in list(self.config["atalhos"].items()):
                if atual == combo:
                    del self.config["atalhos"][nome]
            if self.config.get("atalho_parar") == combo:
                self.config["atalho_parar"] = ""
            ao_capturar(combo)
            self.status(f"Atalho definido: {combo}")
        else:
            self.status("Cancelado.")
        self.lbl_parar.config(text=self.config.get("atalho_parar") or "—")
        self._atualizar_linhas()
        self._registrar_atalhos()
        self._salvar_config()

    def _atualizar_linhas(self):
        for i, nome in enumerate(self.sons):
            atalho = self.config["atalhos"].get(nome) or "—"
            self.lista.item(str(i), values=(nome, atalho))

    def definir_atalho_som(self):
        nome = self._selecionado()
        if nome:
            self._capturar_atalho(
                lambda combo: self.config["atalhos"].__setitem__(nome, combo))

    def limpar_atalho_som(self):
        nome = self._selecionado()
        if nome and self.config["atalhos"].pop(nome, None):
            self._atualizar_linhas()
            self._registrar_atalhos()
            self._salvar_config()
            self.status(f"Atalho removido de {nome}.")

    def definir_atalho_parar(self):
        self._capturar_atalho(
            lambda combo: self.config.__setitem__("atalho_parar", combo))

    def limpar_atalho_parar(self):
        self.config["atalho_parar"] = ""
        self.lbl_parar.config(text="—")
        self._registrar_atalhos()
        self._salvar_config()

    # ----- comunicação entre threads --------------------------------------

    def na_interface(self, funcao, *args):
        """Agenda uma função para rodar na thread da interface (tkinter)."""
        self.fila.put((funcao, args))

    def _processar_fila(self):
        try:
            while True:
                funcao, args = self.fila.get_nowait()
                try:
                    funcao(*args)
                except Exception as erro:
                    self.status(f"Erro: {erro}")
        except queue.Empty:
            pass
        self.root.after(20, self._processar_fila)

    # ----- configuração ---------------------------------------------------

    def _ler_config(self):
        config = {}
        if ARQ_CONFIG.exists():
            try:
                config = json.loads(ARQ_CONFIG.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                config = {}
        config.setdefault("atalhos", {})
        config.setdefault("atalho_parar", "")
        return config

    def _agendar_salvar(self):
        if self._salvar_agendado:
            self.root.after_cancel(self._salvar_agendado)
        self._salvar_agendado = self.root.after(500, self._salvar_config)

    def _salvar_config(self):
        self._salvar_agendado = None
        self.config.update({
            "sobrepor": self.var_sobrepor.get(),
            "saida_mic": self.var_mic.get(),
            "saida_fone": self.var_fone.get(),
            "volume_mic": round(self.var_vol_mic.get()),
            "volume_fone": round(self.var_vol_fone.get()),
            "ouvir": self.var_ouvir.get(),
        })
        try:
            ARQ_CONFIG.write_text(json.dumps(self.config, indent=2, ensure_ascii=False),
                                  encoding="utf-8")
        except OSError as erro:
            messagebox.showwarning("Meu Soundpad", f"Não consegui salvar a configuração:\n{erro}")

    def fechar(self):
        self._salvar_config()
        self.parar()
        try:
            keyboard.unhook_all()
        except Exception:
            pass
        self.root.destroy()


def main():
    # Deixa o texto nítido em telas com escala (125%, 150%...)
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

    root = tk.Tk()
    try:
        ttk.Style().theme_use("vista")
    except tk.TclError:
        pass
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
