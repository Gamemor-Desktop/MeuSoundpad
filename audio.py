"""Funções puras de áudio do Meu Soundpad (sem interface e sem dispositivos)."""

import numpy as np
import soundfile as sf


def carregar_audio(caminho, taxa_destino, canais_destino):
    """Lê um arquivo de áudio e o converte para a taxa e os canais da saída."""
    dados, taxa = sf.read(str(caminho), dtype="float32", always_2d=True)
    return converter(dados, taxa, taxa_destino, canais_destino)


def converter(dados, taxa, taxa_destino, canais_destino):
    """Ajusta canais (mono/estéreo) e taxa de amostragem de um array (frames, canais)."""
    if canais_destino == 1:
        dados = dados.mean(axis=1, keepdims=True)
    elif dados.shape[1] == 1:
        dados = np.repeat(dados, canais_destino, axis=1)
    else:
        dados = dados[:, :canais_destino]

    # Reamostragem linear simples
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


def cortar(dados, taxa, inicio=0.0, fim=0.0):
    """Devolve o trecho entre `inicio` e `fim` (segundos). fim <= 0 significa até o final."""
    a = max(0, int(round(inicio * taxa)))
    b = int(round(fim * taxa)) if fim and fim > 0 else len(dados)
    return dados[a:b]
