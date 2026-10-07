"""
Meu Soundpad
------------
Toca sons no seu microfone (através do VB-Audio Virtual Cable) e, se você
quiser, também nos seus fones. Cada som pode ter um atalho global, que
funciona mesmo com o jogo ou o Discord em foco.

Como usar: veja o arquivo LEIA-ME.md.
"""

import json
import logging
import os
import queue
import shutil
import sys
import threading
import tkinter as tk
from logging.handlers import RotatingFileHandler
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import keyboard
import numpy as np
import sounddevice as sd
import soundfile as sf
import customtkinter as ctk

from audio import carregar_audio, cortar, limitar

# Opcionais: o app funciona sem eles, só perde o recurso correspondente.
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
except ImportError:
    DND_FILES = TkinterDnD = None

try:
    import pystray
    from PIL import Image, ImageDraw
except ImportError:
    pystray = None

try:
    import winreg
except ImportError:  # fora do Windows
    winreg = None

# ---------------------------------------------------------------------------
# Configurações gerais
# ---------------------------------------------------------------------------

if getattr(sys, "frozen", False):  # rodando como .exe do PyInstaller
    PASTA = Path(sys.executable).resolve().parent
else:
    PASTA = Path(__file__).resolve().parent
PASTA_SONS = PASTA / "sons"
ARQ_CONFIG = PASTA / "config.json"
ARQ_LOG = PASTA / "soundpad.log"
EXTENSOES = {".wav", ".mp3", ".ogg", ".flac"}
LIMITE_CACHE = 200 * 1024 * 1024   # bytes de áudio decodificado mantidos na memória
TEMPO_CAPTURA = 15000              # ms até desistir de capturar um atalho
REINICIAR = "Reiniciar o som"
ALTERNAR = "Alternar tocar/parar"
CHAVE_RUN = r"Software\Microsoft\Windows\CurrentVersion\Run"
NOME_RUN = "MeuSoundpad"

# Tema escuro
FUNDO = "#16171a"
PAINEL = "#202226"
BORDA = "#2f3238"
BORDA_CLARA = "#3d4148"
TEXTO_SUAVE = "#9aa0a6"
TEXTO = "#e8eaed"
ACENTO = "#3b82f6"
ACENTO_ESCURO = "#2456a8"
PERIGO = "#dc2626"
PERIGO_ESCURO = "#b91c1c"
FAMILIA = "Segoe UI"

log = logging.getLogger("soundpad")


def fonte(tamanho, peso="normal"):
    return ctk.CTkFont(family=FAMILIA, size=tamanho, weight=peso)


def configurar_log():
    log.setLevel(logging.INFO)
    try:
        arquivo = RotatingFileHandler(ARQ_LOG, maxBytes=200_000, backupCount=1,
                                      encoding="utf-8")
    except OSError:
        return
    arquivo.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    log.addHandler(arquivo)


# ---------------------------------------------------------------------------
# Iniciar com o Windows
# ---------------------------------------------------------------------------

def _comando_inicio():
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --minimizado'
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    exe = pythonw if pythonw.exists() else Path(sys.executable)
    return f'"{exe}" "{Path(__file__).resolve()}" --minimizado'


def autostart_ativo():
    if winreg is None:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, CHAVE_RUN) as chave:
            winreg.QueryValueEx(chave, NOME_RUN)
        return True
    except OSError:
        return False


def definir_autostart(ativo):
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, CHAVE_RUN, 0,
                        winreg.KEY_SET_VALUE) as chave:
        if ativo:
            winreg.SetValueEx(chave, NOME_RUN, 0, winreg.REG_SZ, _comando_inicio())
        else:
            try:
                winreg.DeleteValue(chave, NOME_RUN)
            except FileNotFoundError:
                pass


def _imagem_icone():
    imagem = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    desenho = ImageDraw.Draw(imagem)
    desenho.rounded_rectangle((4, 4, 60, 60), radius=12, fill=(37, 99, 235, 255))
    desenho.polygon([(25, 18), (25, 46), (47, 32)], fill="white")
    return imagem


# ---------------------------------------------------------------------------
# Áudio
# ---------------------------------------------------------------------------

class Tocador:
    """Toca um áudio em um dispositivo de saída específico."""

    def __init__(self, nome, dados, dispositivo, taxa, volume, loop, ao_terminar):
        self.nome = nome
        self.loop = loop
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
        total = len(self.dados)
        if self.loop:
            escrito = 0
            while escrito < frames:
                n = min(frames - escrito, total - self.pos)
                saida[escrito:escrito + n] = self.dados[self.pos:self.pos + n]
                escrito += n
                self.pos = (self.pos + n) % total
            return
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
        self._preload_agendado = None
        self._atualizando = False      # evita laços ao ajustar o volume do som
        self._icone = None             # ícone da bandeja
        self._avisos = []
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
        root.geometry("920x600")
        root.minsize(800, 480)

        self.dispositivos = self._listar_dispositivos()
        self._montar_interface()
        self._carregar_lista()

        if not any("cable input" in nome.lower() for _, nome in self.dispositivos):
            self.status("VB-Cable não encontrado. Veja o LEIA-ME para instalar.")
        elif self._avisos:
            self.status(self._avisos[0])

        root.protocol("WM_DELETE_WINDOW", self.fechar)
        self._processar_fila()

    # ----- interface ------------------------------------------------------

    def _criar_variaveis(self):
        c = self.config
        self.var_mic = tk.StringVar(value=self._escolher_inicial(c.get("saida_mic"), "cable input"))
        self.var_fone = tk.StringVar(value=self._escolher_inicial(c.get("saida_fone"), None))
        self.var_vol_mic = tk.DoubleVar(value=c.get("volume_mic", 80))
        self.var_vol_fone = tk.DoubleVar(value=c.get("volume_fone", 60))
        self.var_ouvir = tk.BooleanVar(value=c.get("ouvir", True))
        self.var_sobrepor = tk.BooleanVar(value=c.get("sobrepor", False))
        self.var_repetir = tk.StringVar(value=c.get("ao_repetir", REINICIAR))
        self.var_bandeja = tk.BooleanVar(value=c.get("bandeja", False) and pystray is not None)
        self.var_autostart = tk.BooleanVar(value=autostart_ativo())
        self.var_busca = tk.StringVar()
        self.var_vol_som = tk.DoubleVar(value=100)

        # Salva a configuração sempre que algo mudar (com um pequeno atraso)
        for var in (self.var_mic, self.var_fone, self.var_vol_mic, self.var_vol_fone,
                    self.var_ouvir, self.var_sobrepor, self.var_repetir, self.var_bandeja):
            var.trace_add("write", lambda *args: self._agendar_salvar())
        # Trocar de dispositivo muda a taxa/canais: recarrega os sons em segundo plano
        for var in (self.var_mic, self.var_fone, self.var_ouvir):
            var.trace_add("write", lambda *args: self._agendar_preload())
        self.var_busca.trace_add("write", lambda *args: self._filtrar())
        self.var_vol_som.trace_add("write", lambda *args: self._ao_mudar_volume_som())

    def _montar_interface(self):
        self._criar_variaveis()
        self._janela_config = None
        self.root.configure(fg_color=FUNDO)

        # Barra de baixo (criada primeiro para nunca ser empurrada para fora)
        rodape = ctk.CTkFrame(self.root, fg_color=PAINEL, corner_radius=0, height=48)
        rodape.pack(fill="x", side="bottom")
        self.lbl_status = ctk.CTkLabel(rodape, text="Pronto", anchor="w",
                                       text_color=TEXTO_SUAVE, font=fonte(12))
        self.lbl_status.pack(side="left", padx=16, pady=10)
        ctk.CTkButton(rodape, text="■  Parar tudo", width=120, fg_color=PERIGO,
                      hover_color=PERIGO_ESCURO, font=fonte(13, "bold"),
                      command=self.parar).pack(side="right", padx=(8, 16), pady=8)
        ctk.CTkButton(rodape, text="Limpar", width=60, fg_color=BORDA, hover_color=BORDA_CLARA,
                      command=self.limpar_atalho_parar).pack(side="right", pady=8)
        ctk.CTkButton(rodape, text="Definir", width=64, fg_color=BORDA, hover_color=BORDA_CLARA,
                      command=self.definir_atalho_parar).pack(side="right", padx=6, pady=8)
        self.lbl_parar = ctk.CTkLabel(rodape, text=self.config.get("atalho_parar") or "—",
                                      font=fonte(12, "bold"))
        self.lbl_parar.pack(side="right", padx=4)
        ctk.CTkLabel(rodape, text="Atalho para parar:", text_color=TEXTO_SUAVE,
                     font=fonte(12)).pack(side="right", padx=(0, 4))

        # Topo: busca e ações
        topo = ctk.CTkFrame(self.root, fg_color="transparent")
        topo.pack(fill="x", padx=16, pady=(16, 8))
        self.entrada_busca = ctk.CTkEntry(
            topo, height=38, font=fonte(13),
            placeholder_text="Buscar sons...  (Ctrl+F)", fg_color=PAINEL, border_color=BORDA)
        self.entrada_busca.pack(side="left", fill="x", expand=True)
        self.entrada_busca.bind(
            "<KeyRelease>", lambda e: self.var_busca.set(self.entrada_busca.get()))
        ctk.CTkButton(topo, text="⚙  Configurações", width=140, height=38, font=fonte(13),
                      fg_color=PAINEL, hover_color=BORDA, border_width=1, border_color=BORDA,
                      command=self.abrir_configuracoes).pack(side="right", padx=(8, 0))
        ctk.CTkButton(topo, text="+  Adicionar sons", width=150, height=38,
                      font=fonte(13, "bold"), fg_color=ACENTO, hover_color=ACENTO_ESCURO,
                      command=self.adicionar_sons).pack(side="right", padx=(8, 0))

        corpo = ctk.CTkFrame(self.root, fg_color="transparent")
        corpo.pack(fill="both", expand=True, padx=16, pady=(0, 12))
        corpo.columnconfigure(0, weight=1)
        corpo.rowconfigure(0, weight=1)

        # Lista de sons
        quadro_lista = ctk.CTkFrame(corpo, fg_color=PAINEL, corner_radius=10)
        quadro_lista.grid(row=0, column=0, sticky="nsew")
        estilo = ttk.Style()
        estilo.theme_use("clam")
        estilo.configure("Sons.Treeview", background=PAINEL, fieldbackground=PAINEL,
                         foreground=TEXTO, rowheight=36, borderwidth=0, relief="flat",
                         bordercolor=PAINEL, lightcolor=PAINEL, darkcolor=PAINEL,
                         font=(FAMILIA, 11))
        estilo.configure("Sons.Treeview.Heading", background=PAINEL, foreground=TEXTO_SUAVE,
                         relief="flat", borderwidth=0, font=(FAMILIA, 10, "bold"),
                         padding=(8, 8))
        estilo.map("Sons.Treeview", background=[("selected", ACENTO_ESCURO)],
                   foreground=[("selected", "white")])
        estilo.map("Sons.Treeview.Heading", background=[("active", PAINEL)])
        self.lista = ttk.Treeview(quadro_lista, columns=("som", "atalho"), show="headings",
                                  selectmode="browse", style="Sons.Treeview")
        self.lista.heading("som", text="SOM", anchor="w")
        self.lista.heading("atalho", text="ATALHO", anchor="center")
        self.lista.column("som", width=320, anchor="w")
        self.lista.column("atalho", width=140, anchor="center", stretch=False)
        self.lista.tag_configure("tocando", foreground="#7cc4ff")
        barra = ctk.CTkScrollbar(quadro_lista, command=self.lista.yview)
        self.lista.configure(yscrollcommand=barra.set)
        self.lista.pack(side="left", fill="both", expand=True, padx=(8, 0), pady=8)
        barra.pack(side="right", fill="y", padx=4, pady=8)
        self.lista.bind("<Double-1>", lambda e: self.tocar_selecionado())
        self.lista.bind("<Return>", lambda e: self.tocar_selecionado())
        self.lista.bind("<<TreeviewSelect>>", lambda e: self._ao_selecionar())
        self.root.bind("<Control-f>", lambda e: self.entrada_busca.focus_set())
        if TkinterDnD is not None:
            self.lista.drop_target_register(DND_FILES)
            self.lista.dnd_bind("<<Drop>>", self._ao_soltar)

        # Painel do som selecionado
        painel = ctk.CTkFrame(corpo, fg_color=PAINEL, corner_radius=10, width=270)
        painel.grid(row=0, column=1, sticky="ns", padx=(12, 0))
        painel.pack_propagate(False)
        self.lbl_nome_som = ctk.CTkLabel(painel, text="Selecione um som", font=fonte(15, "bold"),
                                         wraplength=230, justify="left", anchor="w")
        self.lbl_nome_som.pack(fill="x", padx=16, pady=(16, 2))
        self.lbl_atalho_som = ctk.CTkLabel(painel, text="", text_color=TEXTO_SUAVE,
                                           font=fonte(12), anchor="w")
        self.lbl_atalho_som.pack(fill="x", padx=16)

        self._controles_som = []

        linha = ctk.CTkFrame(painel, fg_color="transparent")
        linha.pack(fill="x", padx=16, pady=(14, 6))
        linha.columnconfigure((0, 1), weight=1)
        b = ctk.CTkButton(linha, text="▶  Tocar", height=38, font=fonte(14, "bold"),
                          fg_color=ACENTO, hover_color=ACENTO_ESCURO,
                          command=self.tocar_selecionado)
        b.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        self._controles_som.append(b)
        b = ctk.CTkButton(linha, text="■  Parar", height=38, font=fonte(14),
                          fg_color=BORDA, hover_color=BORDA_CLARA,
                          command=self.parar_selecionado)
        b.grid(row=0, column=1, sticky="ew", padx=(4, 0))
        self._controles_som.append(b)

        ctk.CTkLabel(painel, text="ATALHO", text_color=TEXTO_SUAVE, font=fonte(10, "bold"),
                     anchor="w").pack(fill="x", padx=16, pady=(12, 2))
        linha = ctk.CTkFrame(painel, fg_color="transparent")
        linha.pack(fill="x", padx=16)
        linha.columnconfigure((0, 1), weight=1)
        b = ctk.CTkButton(linha, text="Definir", height=32, font=fonte(12), fg_color=BORDA,
                          hover_color=BORDA_CLARA, command=self.definir_atalho_som)
        b.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        self._controles_som.append(b)
        b = ctk.CTkButton(linha, text="Limpar", height=32, font=fonte(12), fg_color=BORDA,
                          hover_color=BORDA_CLARA, command=self.limpar_atalho_som)
        b.grid(row=0, column=1, sticky="ew", padx=(4, 0))
        self._controles_som.append(b)

        cab = ctk.CTkFrame(painel, fg_color="transparent")
        cab.pack(fill="x", padx=16, pady=(14, 0))
        ctk.CTkLabel(cab, text="VOLUME DO SOM", text_color=TEXTO_SUAVE,
                     font=fonte(10, "bold")).pack(side="left")
        self.lbl_vol_som = ctk.CTkLabel(cab, text="100%", font=fonte(12, "bold"))
        self.lbl_vol_som.pack(side="right")
        self.escala_som = ctk.CTkSlider(painel, from_=0, to=200, variable=self.var_vol_som)
        self.escala_som.pack(fill="x", padx=16, pady=(4, 0))
        self._controles_som.append(self.escala_som)

        b = ctk.CTkButton(painel, text="✂  Editar som...", height=34, font=fonte(13),
                          fg_color=BORDA, hover_color=BORDA_CLARA, command=self.editar_som)
        b.pack(fill="x", padx=16, pady=(16, 0))
        self._controles_som.append(b)

        self._ao_selecionar()

    def abrir_configuracoes(self):
        if self._janela_config is not None and self._janela_config.winfo_exists():
            self._janela_config.lift()
            self._janela_config.focus()
            return
        nomes = [nome for _, nome in self.dispositivos] or [""]
        janela = ctk.CTkToplevel(self.root, fg_color=FUNDO)
        self._janela_config = janela
        janela.title("Configurações")
        janela.geometry("560x660")
        janela.minsize(520, 560)
        janela.transient(self.root)
        janela.after(200, janela.focus)

        corpo = ctk.CTkScrollableFrame(janela, fg_color="transparent")
        corpo.pack(fill="both", expand=True, padx=8, pady=8)

        def secao(titulo):
            quadro = ctk.CTkFrame(corpo, fg_color=PAINEL, corner_radius=10)
            quadro.pack(fill="x", padx=8, pady=6)
            ctk.CTkLabel(quadro, text=titulo, font=fonte(13, "bold"),
                         anchor="w").pack(fill="x", padx=16, pady=(12, 4))
            return quadro

        def menu(quadro, valores, var):
            ctk.CTkOptionMenu(quadro, values=valores, variable=var, dynamic_resizing=False,
                              fg_color=BORDA, button_color=BORDA,
                              button_hover_color=BORDA_CLARA,
                              height=32).pack(fill="x", padx=16, pady=(2, 0))

        def saida(quadro, rotulo, var_nome, var_vol):
            ctk.CTkLabel(quadro, text=rotulo, text_color=TEXTO_SUAVE, font=fonte(12),
                         anchor="w").pack(fill="x", padx=16, pady=(6, 0))
            menu(quadro, nomes, var_nome)
            linha = ctk.CTkFrame(quadro, fg_color="transparent")
            linha.pack(fill="x", padx=16, pady=(6, 0))
            ctk.CTkLabel(linha, text="Volume", font=fonte(12)).pack(side="left")
            rotulo_vol = ctk.CTkLabel(linha, text=f"{round(var_vol.get())}%", width=48,
                                      font=fonte(12, "bold"))
            rotulo_vol.pack(side="right")
            ctk.CTkSlider(linha, from_=0, to=150, variable=var_vol,
                          command=lambda v: rotulo_vol.configure(text=f"{round(v)}%")
                          ).pack(side="left", fill="x", expand=True, padx=10)

        quadro = secao("Saídas de áudio")
        saida(quadro, "Microfone virtual (CABLE Input)", self.var_mic, self.var_vol_mic)
        ctk.CTkSwitch(quadro, text="Ouvir também nos fones", variable=self.var_ouvir,
                      font=fonte(13)).pack(anchor="w", padx=16, pady=(14, 0))
        saida(quadro, "Fones", self.var_fone, self.var_vol_fone)
        ctk.CTkFrame(quadro, fg_color="transparent", height=12).pack()

        quadro = secao("Reprodução")
        ctk.CTkSwitch(quadro, text="Permitir sons sobrepostos", variable=self.var_sobrepor,
                      font=fonte(13)).pack(anchor="w", padx=16, pady=(4, 0))
        ctk.CTkLabel(quadro, text="Ao repetir o atalho", text_color=TEXTO_SUAVE,
                     font=fonte(12), anchor="w").pack(fill="x", padx=16, pady=(10, 0))
        menu(quadro, [REINICIAR, ALTERNAR], self.var_repetir)
        ctk.CTkFrame(quadro, fg_color="transparent", height=14).pack()

        quadro = secao("Programa")
        sw = ctk.CTkSwitch(quadro, text="Ao fechar, ir para a bandeja",
                           variable=self.var_bandeja, font=fonte(13))
        sw.pack(anchor="w", padx=16, pady=(4, 0))
        if pystray is None:
            sw.configure(state="disabled")
        sw = ctk.CTkSwitch(quadro, text="Iniciar com o Windows", variable=self.var_autostart,
                           command=self._alternar_autostart, font=fonte(13))
        sw.pack(anchor="w", padx=16, pady=(10, 14))
        if winreg is None:
            sw.configure(state="disabled")

        quadro = secao("Sons")
        linha = ctk.CTkFrame(quadro, fg_color="transparent")
        linha.pack(fill="x", padx=16, pady=(4, 14))
        linha.columnconfigure((0, 1), weight=1)
        ctk.CTkButton(linha, text="Abrir pasta de sons", fg_color=BORDA,
                      hover_color=BORDA_CLARA, command=self.abrir_pasta
                      ).grid(row=0, column=0, sticky="ew", padx=(0, 4))
        ctk.CTkButton(linha, text="Atualizar lista", fg_color=BORDA,
                      hover_color=BORDA_CLARA, command=self._carregar_lista
                      ).grid(row=0, column=1, sticky="ew", padx=(4, 0))

    def status(self, texto):
        self.lbl_status.configure(text=texto)

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
        if salvo:
            # O Windows trunca e às vezes muda o fim do nome: tenta pelo começo.
            for nome in nomes:
                if nome.startswith(salvo[:20]):
                    return nome
            self._avisos.append(f"Dispositivo salvo não encontrado: {salvo}")
            log.warning("Dispositivo salvo não encontrado: %s", salvo)
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
        self._filtrar()
        self._registrar_atalhos()
        if not self.sons:
            self.status("Nenhum som ainda. Use \"+ Adicionar sons\".")
        else:
            self._pre_carregar()

    def _filtrar(self):
        termo = self.var_busca.get().strip().lower()
        selecionado = self.lista.selection()
        self.lista.delete(*self.lista.get_children())
        for nome in self.sons:
            if termo in nome.lower():
                atalho = self.config["atalhos"].get(nome) or "—"
                self.lista.insert("", "end", iid=nome, values=(nome, atalho))
        self._marcar_tocando()
        if selecionado and self.lista.exists(selecionado[0]):
            self.lista.selection_set(selecionado[0])
        else:
            self._ao_selecionar()

    def _marcar_tocando(self):
        """Destaca na lista os sons que estão tocando agora."""
        tocando = {t.nome for t in self.tocadores}
        for nome in self.lista.get_children():
            self.lista.item(nome, tags=("tocando",) if nome in tocando else ())

    def _agendar_preload(self):
        if self._preload_agendado:
            self.root.after_cancel(self._preload_agendado)
        self._preload_agendado = self.root.after(800, self._pre_carregar)

    def _pre_carregar(self):
        """Decodifica os sons em segundo plano para o primeiro disparo ser instantâneo."""
        self._preload_agendado = None
        self._geracao_lista += 1
        geracao = self._geracao_lista
        try:
            specs = self._especificacoes()
        except Exception:
            log.exception("Falha ao consultar dispositivos para pré-carga")
            return
        arquivos = [PASTA_SONS / nome for nome in self.sons]

        def trabalho():
            for caminho in arquivos:
                for _, _, taxa, canais in specs:
                    if geracao != self._geracao_lista or self._cache_bytes > LIMITE_CACHE // 2:
                        return
                    try:
                        self._audio(caminho, taxa, canais)
                    except Exception:
                        log.exception("Falha ao pré-carregar %s", caminho.name)

        threading.Thread(target=trabalho, daemon=True).start()

    def _selecionado(self):
        selecao = self.lista.selection()
        if not selecao:
            self.status("Selecione um som na lista primeiro.")
            return None
        return selecao[0]

    def _ao_selecionar(self):
        selecao = self.lista.selection()
        nome = selecao[0] if selecao else None
        volume = self.config["volumes"].get(nome, 100) if nome else 100
        self._atualizando = True
        self.var_vol_som.set(volume)
        self._atualizando = False
        self.lbl_vol_som.configure(text=f"{round(volume)}%")
        self._atualizar_painel()

    def _atualizar_painel(self):
        selecao = self.lista.selection()
        nome = selecao[0] if selecao else None
        self.lbl_nome_som.configure(text=nome or "Selecione um som")
        if nome:
            atalho = self.config["atalhos"].get(nome)
            self.lbl_atalho_som.configure(text=f"Atalho: {atalho}" if atalho else "Sem atalho")
        else:
            self.lbl_atalho_som.configure(text="")
        for controle in self._controles_som:
            controle.configure(state="normal" if nome else "disabled")

    def _ao_mudar_volume_som(self):
        volume = round(self.var_vol_som.get())
        self.lbl_vol_som.configure(text=f"{volume}%")
        if self._atualizando:
            return
        selecao = self.lista.selection()
        if not selecao:
            return
        if volume == 100:
            self.config["volumes"].pop(selecao[0], None)
        else:
            self.config["volumes"][selecao[0]] = volume
        self._agendar_salvar()

    def adicionar_sons(self):
        arquivos = filedialog.askopenfilenames(
            title="Escolha os sons",
            filetypes=[("Áudio", "*.wav *.mp3 *.ogg *.flac"), ("Todos", "*.*")],
        )
        self._copiar_sons(arquivos)

    def _ao_soltar(self, evento):
        self._copiar_sons(self.root.tk.splitlist(evento.data))

    def _copiar_sons(self, arquivos):
        copiados = 0
        for arquivo in arquivos:
            origem = Path(arquivo)
            destino = PASTA_SONS / origem.name
            if (origem.is_file() and origem.suffix.lower() in EXTENSOES
                    and origem.resolve() != destino.resolve()):
                try:
                    shutil.copy2(origem, destino)
                    copiados += 1
                except OSError:
                    log.exception("Falha ao copiar %s", origem)
        self._carregar_lista()
        if copiados:
            self.status(f"{copiados} som(ns) adicionado(s).")

    def abrir_pasta(self):
        os.startfile(PASTA_SONS)

    # ----- editar som (cortar e repetir) ----------------------------------

    def editar_som(self):
        nome = self._selecionado()
        if not nome:
            return
        atual = self.config["cortes"].get(nome, {})
        try:
            duracao = sf.info(str(PASTA_SONS / nome)).duration
        except Exception:
            duracao = 0.0

        janela = ctk.CTkToplevel(self.root, fg_color=FUNDO)
        janela.title("Editar som")
        janela.transient(self.root)
        janela.resizable(False, False)
        quadro = ctk.CTkFrame(janela, fg_color=PAINEL, corner_radius=10)
        quadro.pack(padx=16, pady=16)

        ctk.CTkLabel(quadro, text=nome, font=fonte(14, "bold"), wraplength=360,
                     justify="left", anchor="w").pack(fill="x", padx=16, pady=(14, 0))
        ctk.CTkLabel(quadro, text=f"Duração do arquivo: {duracao:.2f} s",
                     text_color=TEXTO_SUAVE, font=fonte(12), anchor="w"
                     ).pack(fill="x", padx=16, pady=(0, 8))

        var_inicio = tk.StringVar(value=f"{atual.get('inicio', 0.0):g}")
        var_fim = tk.StringVar(value=f"{atual.get('fim', 0.0):g}")
        var_loop = tk.BooleanVar(value=atual.get("loop", False))

        def campo(rotulo, var):
            linha = ctk.CTkFrame(quadro, fg_color="transparent")
            linha.pack(fill="x", padx=16, pady=3)
            ctk.CTkLabel(linha, text=rotulo, font=fonte(13)).pack(side="left")
            ctk.CTkEntry(linha, textvariable=var, width=80, justify="center"
                         ).pack(side="right")

        campo("Começar em (segundos)", var_inicio)
        campo("Terminar em (0 = até o fim)", var_fim)
        ctk.CTkSwitch(quadro, text="Repetir em loop até parar", variable=var_loop,
                      font=fonte(13)).pack(anchor="w", padx=16, pady=(10, 0))

        def numero(var):
            return round(float(var.get().strip().replace(",", ".") or 0), 2)

        def salvar():
            try:
                inicio, fim = numero(var_inicio), numero(var_fim)
            except ValueError:
                messagebox.showwarning("Editar som", "Digite números válidos.", parent=janela)
                return
            if inicio < 0 or fim < 0 or (fim and fim <= inicio):
                messagebox.showwarning(
                    "Editar som", "O fim precisa ser maior que o início.", parent=janela)
                return
            if inicio == 0 and fim == 0 and not var_loop.get():
                self.config["cortes"].pop(nome, None)
            else:
                self.config["cortes"][nome] = {
                    "inicio": inicio, "fim": fim, "loop": var_loop.get()}
            self._salvar_config()
            self.status(f"Edição salva para {nome}.")
            janela.destroy()

        def remover():
            self.config["cortes"].pop(nome, None)
            self._salvar_config()
            self.status(f"Edição removida de {nome}.")
            janela.destroy()

        rodape = ctk.CTkFrame(quadro, fg_color="transparent")
        rodape.pack(fill="x", padx=16, pady=(16, 14))
        ctk.CTkButton(rodape, text="Salvar", width=90, fg_color=ACENTO,
                      hover_color=ACENTO_ESCURO, command=salvar).pack(side="right")
        ctk.CTkButton(rodape, text="Cancelar", width=90, fg_color=BORDA,
                      hover_color=BORDA_CLARA, command=janela.destroy).pack(side="right", padx=6)
        ctk.CTkButton(rodape, text="Remover edição", width=120, fg_color=BORDA,
                      hover_color=BORDA_CLARA, command=remover).pack(side="left")
        janela.after(200, janela.grab_set)
        janela.after(200, janela.focus)

    # ----- tocar ----------------------------------------------------------

    def tocar_selecionado(self):
        nome = self._selecionado()
        if nome:
            self.tocar(nome)

    def _especificacoes(self, nome=None):
        """Saídas escolhidas: lista de (dispositivo, volume, taxa, canais)."""
        volume_som = self.config["volumes"].get(nome, 100) / 100 if nome else 1.0
        saidas = []
        mic = self._indice(self.var_mic.get())
        if mic is not None:
            saidas.append((mic, self.var_vol_mic.get() / 100 * volume_som))
        if self.var_ouvir.get():
            fone = self._indice(self.var_fone.get())
            if fone is not None and fone != mic:
                saidas.append((fone, self.var_vol_fone.get() / 100 * volume_som))
        specs = []
        for indice, volume in saidas:
            info = sd.query_devices(indice)
            specs.append((indice, volume, int(info["default_samplerate"]),
                          min(2, info["max_output_channels"])))
        return specs

    def tocar(self, nome):
        if (self.var_repetir.get() == ALTERNAR
                and any(t.nome == nome for t in self.tocadores)):
            self.parar_som(nome)
            return
        if not self.var_sobrepor.get():
            self.parar()  # um som por vez, como no Soundpad
        caminho = PASTA_SONS / nome
        if not caminho.exists():
            self.status(f"Arquivo não encontrado: {nome}")
            return

        try:
            specs = self._especificacoes(nome)
        except Exception as erro:
            log.exception("Falha ao consultar dispositivos")
            self.status(f"Erro nos dispositivos de áudio: {erro}")
            return
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
            log.exception("Falha ao carregar %s", nome)
            self.na_interface(self.status, f"Erro ao carregar {nome}: {erro}")
            return
        self.na_interface(self._iniciar, nome, caminho, specs, geracao)

    def _iniciar(self, nome, caminho, specs, geracao):
        if geracao != self._geracao:
            return  # alguém mandou parar (ou tocar outro som) enquanto carregava
        corte = self.config["cortes"].get(nome, {})
        novos = []
        for indice, volume, taxa, canais in specs:
            try:
                dados = cortar(self._audio(caminho, taxa, canais), taxa,
                               corte.get("inicio", 0.0), corte.get("fim", 0.0))
                if len(dados) == 0:
                    raise ValueError("o trecho escolhido está vazio")
                novos.append(Tocador(nome, dados, indice, taxa, volume,
                                     corte.get("loop", False), self._ao_terminar))
            except Exception as erro:
                log.exception("Falha ao tocar %s", nome)
                for tocador in novos:
                    tocador.parar()
                self.status(f"Erro ao tocar {nome}: {erro}")
                return
        self.tocadores.extend(novos)
        self._marcar_tocando()
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
            self._marcar_tocando()
        tocador.fechar()

    def parar(self):
        self._geracao += 1  # cancela sons que ainda estão sendo carregados
        for tocador in self.tocadores:
            tocador.parar()
        if self.tocadores:
            self.status("Parado.")
        self.tocadores = []
        self._marcar_tocando()

    def parar_som(self, nome):
        restantes = []
        for tocador in self.tocadores:
            if tocador.nome == nome:
                tocador.parar()
            else:
                restantes.append(tocador)
        self.tocadores = restantes
        self._marcar_tocando()
        self.status(f"Parado: {nome}")

    def parar_selecionado(self):
        nome = self._selecionado()
        if nome:
            self.parar_som(nome)

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
        self.lbl_parar.configure(text=self.config.get("atalho_parar") or "—")
        self._atualizar_linhas()
        self._registrar_atalhos()
        self._salvar_config()

    def _atualizar_linhas(self):
        for nome in self.lista.get_children():
            atalho = self.config["atalhos"].get(nome) or "—"
            self.lista.item(nome, values=(nome, atalho))
        self._atualizar_painel()

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
        self.lbl_parar.configure(text="—")
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
                    log.exception("Erro em tarefa da interface")
                    self.status(f"Erro: {erro}")
        except queue.Empty:
            pass
        self.root.after(20, self._processar_fila)

    # ----- bandeja e inicialização ----------------------------------------

    def _alternar_autostart(self):
        try:
            definir_autostart(self.var_autostart.get())
        except OSError as erro:
            log.exception("Falha ao alterar a inicialização com o Windows")
            self.var_autostart.set(autostart_ativo())
            self.status(f"Não consegui alterar a inicialização: {erro}")
            return
        self.status("Vai iniciar com o Windows." if self.var_autostart.get()
                    else "Não vai mais iniciar com o Windows.")

    def _criar_bandeja(self):
        if pystray is None:
            return False
        if self._icone is not None:
            return True
        try:
            menu = pystray.Menu(
                pystray.MenuItem("Abrir", lambda icone, item: self.na_interface(self.mostrar),
                                 default=True),
                pystray.MenuItem("Parar tudo", lambda icone, item: self.na_interface(self.parar)),
                pystray.MenuItem("Sair", lambda icone, item: self.na_interface(self.sair)),
            )
            self._icone = pystray.Icon("MeuSoundpad", _imagem_icone(), "Meu Soundpad", menu)
            self._icone.run_detached()
            return True
        except Exception:
            log.exception("Falha ao criar o ícone da bandeja")
            self._icone = None
            return False

    def esconder(self):
        if self._criar_bandeja():
            self.root.withdraw()
        else:
            self.root.iconify()

    def mostrar(self):
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

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
        config.setdefault("volumes", {})
        config.setdefault("cortes", {})
        return config

    def _agendar_salvar(self):
        if self._salvar_agendado:
            self.root.after_cancel(self._salvar_agendado)
        self._salvar_agendado = self.root.after(500, self._salvar_config)

    def _salvar_config(self):
        self._salvar_agendado = None
        self.config.update({
            "saida_mic": self.var_mic.get(),
            "saida_fone": self.var_fone.get(),
            "volume_mic": round(self.var_vol_mic.get()),
            "volume_fone": round(self.var_vol_fone.get()),
            "ouvir": self.var_ouvir.get(),
            "sobrepor": self.var_sobrepor.get(),
            "ao_repetir": self.var_repetir.get(),
            "bandeja": self.var_bandeja.get(),
        })
        try:
            ARQ_CONFIG.write_text(json.dumps(self.config, indent=2, ensure_ascii=False),
                                  encoding="utf-8")
        except OSError as erro:
            log.exception("Falha ao salvar a configuração")
            messagebox.showwarning("Meu Soundpad", f"Não consegui salvar a configuração:\n{erro}")

    def fechar(self):
        """Botão X da janela: vai para a bandeja ou encerra."""
        if self.var_bandeja.get() and pystray is not None:
            self._salvar_config()
            self.esconder()
        else:
            self.sair()

    def sair(self):
        self._salvar_config()
        self.parar()
        try:
            keyboard.unhook_all()
        except Exception:
            pass
        if self._icone is not None:
            try:
                self._icone.stop()
            except Exception:
                pass
        self.root.destroy()


if TkinterDnD is not None:
    class Janela(ctk.CTk, TkinterDnD.DnDWrapper):
        """Janela do CustomTkinter com suporte a arrastar e soltar."""

        def __init__(self):
            super().__init__()
            self.TkdndVersion = TkinterDnD._require(self)
else:
    Janela = ctk.CTk


def main():
    configurar_log()
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")
    tema = ctk.ThemeManager.theme
    for widget, chaves in (("CTkSlider", ("button_color",)), ("CTkSwitch", ("progress_color",))):
        for chave in chaves:
            tema[widget][chave] = [ACENTO, ACENTO]
    for widget in ("CTkSlider", "CTkSwitch"):
        tema[widget]["button_hover_color"] = [ACENTO_ESCURO, ACENTO_ESCURO]

    root = Janela()
    root.report_callback_exception = (
        lambda tipo, valor, tb: log.error("Erro na interface", exc_info=(tipo, valor, tb)))
    app = App(root)
    if "--minimizado" in sys.argv:
        root.after(100, app.esconder)
    root.mainloop()


if __name__ == "__main__":
    main()
