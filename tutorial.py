"""Tour interativo de primeira execução: um cartão que acompanha a janela do app."""

import logging
import subprocess
import tkinter as tk
import webbrowser

import customtkinter as ctk

from tema import (ACENTO, ACENTO_ESCURO, BORDA, BORDA_CLARA, PAINEL, TEXTO, TEXTO_SUAVE,
                  fonte)
from tutorial_passos import URL_VBCABLE, Roteiro, cabo_instalado

log = logging.getLogger("soundpad")

DESTAQUE = "#facc15"
SUCESSO = "#4ade80"
ERRO = "#f87171"
ESPESSURA = 3          # largura da moldura de destaque, em pixels
LARGURA_CARTAO = 360
MARGEM = 12

# Onde o cartão fica em relação à parte destacada
POSICAO = {
    "adicionar": "abaixo",
    "config": "abaixo",
    "painel": "esquerda_base",
    "atalho": "esquerda_topo",
}


class Tutorial:
    """Mostra os passos de `Roteiro` e reage ao que o usuário faz no app.

    O app precisa oferecer: `root`, `dispositivos`, `alvos_tutorial` (nome -> widget),
    `recarregar_dispositivos()`, `adicionar_exemplo()`, `tocar_selecionado()`,
    `definir_atalho_som()` e `ao_fechar_tutorial()`.
    """

    def __init__(self, app):
        self.app = app
        self.root = app.root
        self.roteiro = Roteiro()
        self._molduras = []
        self._reposicionar_agendado = None

        self.cartao = tk.Toplevel(self.root, bg=ACENTO)
        self.cartao.overrideredirect(True)
        self.cartao.transient(self.root)
        self.corpo = None
        self._id_configure = self.root.bind("<Configure>", self._ao_mover_janela, add="+")
        self._mostrar()

    # ----- ciclo de vida --------------------------------------------------

    def notificar(self, evento):
        """Chamado pelo app quando o usuário faz algo (adicionar, tocar, atalho)."""
        if self.roteiro.notificar(evento):
            self._mostrar()

    def fechar(self):
        if self._reposicionar_agendado:
            self.root.after_cancel(self._reposicionar_agendado)
        self._limpar_molduras()
        try:
            self.root.unbind("<Configure>", self._id_configure)
        except tk.TclError:
            pass
        self.cartao.destroy()
        self.app.ao_fechar_tutorial()

    # ----- conteúdo do cartão ---------------------------------------------

    def _mostrar(self):
        passo = self.roteiro.atual
        if self.corpo is not None:
            self.corpo.destroy()
        self.corpo = ctk.CTkFrame(self.cartao, fg_color=PAINEL, corner_radius=0)
        self.corpo.pack(fill="both", expand=True, padx=2, pady=2)

        ctk.CTkLabel(self.corpo, text=f"PASSO {self.roteiro.indice + 1} DE {self.roteiro.total}",
                     text_color=TEXTO_SUAVE, font=fonte(10, "bold"),
                     anchor="w").pack(fill="x", padx=16, pady=(14, 0))
        ctk.CTkLabel(self.corpo, text=passo.titulo, text_color=TEXTO, font=fonte(16, "bold"),
                     anchor="w", justify="left", wraplength=LARGURA_CARTAO - 40
                     ).pack(fill="x", padx=16, pady=(2, 6))
        ctk.CTkLabel(self.corpo, text=passo.texto, text_color=TEXTO, font=fonte(12),
                     anchor="w", justify="left", wraplength=LARGURA_CARTAO - 40
                     ).pack(fill="x", padx=16)

        texto, cor = self._situacao()
        if texto:
            ctk.CTkLabel(self.corpo, text=texto, text_color=cor, font=fonte(12, "bold"),
                         anchor="w", justify="left", wraplength=LARGURA_CARTAO - 40
                         ).pack(fill="x", padx=16, pady=(10, 0))

        for id_acao, rotulo in passo.acoes:
            ctk.CTkButton(self.corpo, text=rotulo, height=32, font=fonte(12),
                          fg_color=BORDA, hover_color=BORDA_CLARA,
                          command=lambda i=id_acao: self._acao(i)
                          ).pack(fill="x", padx=16, pady=(8, 0))

        nav = ctk.CTkFrame(self.corpo, fg_color="transparent")
        nav.pack(fill="x", padx=16, pady=(16, 14))
        ctk.CTkButton(nav, text="Pular tour", width=80, height=30, font=fonte(12),
                      fg_color="transparent", hover_color=BORDA, text_color=TEXTO_SUAVE,
                      command=self.fechar).pack(side="left")
        proximo = ctk.CTkButton(
            nav, text="Concluir" if self.roteiro.ultimo else "Próximo", width=90, height=30,
            font=fonte(12, "bold"), fg_color=ACENTO, hover_color=ACENTO_ESCURO,
            command=self._proximo)
        proximo.pack(side="right")
        if not self.roteiro.cumprido:
            proximo.configure(state="disabled")
        if not self.roteiro.primeiro:
            ctk.CTkButton(nav, text="Voltar", width=70, height=30, font=fonte(12),
                          fg_color=BORDA, hover_color=BORDA_CLARA,
                          command=self._voltar).pack(side="right", padx=(0, 6))

        self._destacar(passo.alvo)
        self._posicionar(passo.alvo)

    def _situacao(self):
        """Texto de estado do passo atual: (texto, cor)."""
        passo = self.roteiro.atual
        if passo.id == "vbcable":
            if cabo_instalado(nome for _, nome in self.app.dispositivos):
                return "✅  VB-Cable encontrado!", SUCESSO
            return ("❌  VB-Cable não encontrado. Depois de instalar e reiniciar o PC, "
                    "clique em \"Verificar de novo\"."), ERRO
        if passo.evento:
            if self.roteiro.cumprido:
                return "✓  Feito! Clique em Próximo.", SUCESSO
            return "Faça isso para continuar.", TEXTO_SUAVE
        return "", TEXTO_SUAVE

    # ----- botões ---------------------------------------------------------

    def _proximo(self):
        if self.roteiro.ultimo:
            self.fechar()
        elif self.roteiro.avancar():
            self._mostrar()

    def _voltar(self):
        if self.roteiro.voltar():
            self._mostrar()

    def _acao(self, id_acao):
        app = self.app
        if id_acao == "baixar":
            webbrowser.open(URL_VBCABLE)
        elif id_acao == "verificar":
            app.recarregar_dispositivos()
            self._mostrar()
        elif id_acao == "exemplo":
            app.adicionar_exemplo()
        elif id_acao == "tocar":
            app.tocar_selecionado()
        elif id_acao == "definir":
            app.definir_atalho_som()
        elif id_acao == "mmsys":
            try:
                subprocess.Popen(["control", "mmsys.cpl"])
            except OSError:
                log.exception("Falha ao abrir as configurações de som")

    # ----- destaque e posição ---------------------------------------------

    def _limpar_molduras(self):
        for faixa in self._molduras:
            faixa.destroy()
        self._molduras = []

    def _destacar(self, nome):
        self._limpar_molduras()
        alvo = self.app.alvos_tutorial.get(nome)
        if alvo is None:
            return
        self.root.update_idletasks()
        x = alvo.winfo_rootx() - self.root.winfo_rootx()
        y = alvo.winfo_rooty() - self.root.winfo_rooty()
        w, h, e = alvo.winfo_width(), alvo.winfo_height(), ESPESSURA
        for fx, fy, fw, fh in ((x - e, y - e, w + 2 * e, e), (x - e, y + h, w + 2 * e, e),
                               (x - e, y, e, h), (x + w, y, e, h)):
            faixa = tk.Frame(self.root, bg=DESTAQUE)
            faixa.place(x=fx, y=fy, width=fw, height=fh)
            faixa.tkraise()
            self._molduras.append(faixa)

    def _posicionar(self, nome):
        root, cartao = self.root, self.cartao
        root.update_idletasks()
        cartao.update_idletasks()
        w, h = LARGURA_CARTAO, cartao.winfo_reqheight()
        rx, ry = root.winfo_rootx(), root.winfo_rooty()
        rw, rh = root.winfo_width(), root.winfo_height()

        alvo = self.app.alvos_tutorial.get(nome)
        if alvo is None:
            x, y = rx + (rw - w) // 2, ry + (rh - h) // 2
        else:
            ax, ay = alvo.winfo_rootx(), alvo.winfo_rooty()
            aw, ah = alvo.winfo_width(), alvo.winfo_height()
            lado = POSICAO.get(nome, "abaixo")
            if lado == "abaixo":
                x, y = ax + aw - w, ay + ah + MARGEM
            elif lado == "esquerda_topo":
                x, y = ax - w - MARGEM, ay
            else:  # esquerda_base
                x, y = ax - w - MARGEM, ay + ah - h
        x = max(rx + 8, min(x, rx + rw - w - 8))
        y = max(ry + 8, min(y, ry + rh - h - 8))
        cartao.geometry(f"{w}x{h}+{x}+{y}")
        cartao.lift()

    def _ao_mover_janela(self, evento):
        if evento.widget is not self.root:
            return
        if self._reposicionar_agendado:
            self.root.after_cancel(self._reposicionar_agendado)
        self._reposicionar_agendado = self.root.after(40, self._reposicionar)

    def _reposicionar(self):
        self._reposicionar_agendado = None
        alvo = self.roteiro.atual.alvo
        self._destacar(alvo)
        self._posicionar(alvo)
