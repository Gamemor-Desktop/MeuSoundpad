"""Cores e fontes compartilhadas pela interface do Meu Soundpad."""

import customtkinter as ctk

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


def fonte(tamanho, peso="normal"):
    return ctk.CTkFont(family=FAMILIA, size=tamanho, weight=peso)
