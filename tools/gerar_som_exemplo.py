"""Gera exemplos/exemplo-ding.wav, o som que acompanha o tutorial.

O áudio é sintetizado aqui (sem amostras de terceiros), então não tem direitos
autorais. Rode `python tools/gerar_som_exemplo.py` para recriá-lo.
"""

from pathlib import Path

import numpy as np
import soundfile as sf

TAXA = 44100
DURACAO = 0.9
SAIDA = Path(__file__).resolve().parent.parent / "exemplos" / "exemplo-ding.wav"


def gerar():
    t = np.arange(int(TAXA * DURACAO)) / TAXA
    # Nota base (E6) com dois harmônicos que somem mais rápido, como um sininho
    parciais = ((1318.5, 1.0, 5.0), (2637.0, 0.35, 9.0), (3951.0, 0.12, 14.0))
    onda = sum(amp * np.sin(2 * np.pi * freq * t) * np.exp(-queda * t)
               for freq, amp, queda in parciais)
    ataque = np.minimum(t / 0.004, 1.0)           # evita estalo no início
    onda = onda * ataque
    return (0.8 * onda / np.max(np.abs(onda))).astype(np.float32)


if __name__ == "__main__":
    SAIDA.parent.mkdir(exist_ok=True)
    sf.write(str(SAIDA), gerar(), TAXA, subtype="PCM_16")
    print(f"Gerado: {SAIDA}")
