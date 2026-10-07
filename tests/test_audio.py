import numpy as np
import pytest

from audio import cortar, converter, limitar


def test_converter_mono_para_estereo_duplica_canal():
    mono = np.array([[0.1], [0.2], [0.3]], dtype=np.float32)
    saida = converter(mono, 44100, 44100, 2)
    assert saida.shape == (3, 2)
    assert np.array_equal(saida[:, 0], saida[:, 1])


def test_converter_estereo_para_mono_faz_media():
    estereo = np.array([[0.0, 1.0], [0.5, 0.5]], dtype=np.float32)
    saida = converter(estereo, 44100, 44100, 1)
    assert saida.shape == (2, 1)
    assert np.allclose(saida[:, 0], [0.5, 0.5])


def test_converter_reamostra_para_o_tamanho_certo():
    dados = np.zeros((44100, 1), dtype=np.float32)
    assert converter(dados, 44100, 48000, 1).shape == (48000, 1)
    assert converter(dados, 44100, 22050, 1).shape == (22050, 1)


def test_converter_devolve_float32_contiguo():
    dados = np.zeros((10, 2), dtype=np.float32)
    saida = converter(dados, 8000, 16000, 2)
    assert saida.dtype == np.float32
    assert saida.flags["C_CONTIGUOUS"]


def test_limitar_nao_altera_sinal_dentro_do_limite():
    dados = np.array([[0.5], [-0.9], [1.0]], dtype=np.float32)
    assert np.array_equal(limitar(dados), dados)


def test_limitar_comprime_picos_sem_passar_de_um():
    dados = np.array([[0.5], [1.5], [-3.0], [0.9]], dtype=np.float32)
    saida = limitar(dados)
    assert np.all(np.abs(saida) <= 1.0)
    assert saida[0, 0] == pytest.approx(0.5)      # abaixo do limite: intacto
    assert saida[1, 0] > 0 and saida[2, 0] < 0    # sinal preservado


def test_limitar_e_monotonico():
    rampa = np.linspace(0, 4, 200, dtype=np.float32).reshape(-1, 1)
    assert np.all(np.diff(limitar(rampa)[:, 0]) >= 0)


def test_cortar_inicio_e_fim():
    dados = np.arange(100, dtype=np.float32).reshape(-1, 1)
    assert len(cortar(dados, 100, 0.2, 0.5)) == 30
    assert cortar(dados, 100, 0.2, 0.5)[0, 0] == 20


def test_cortar_fim_zero_vai_ate_o_final():
    dados = np.arange(100, dtype=np.float32).reshape(-1, 1)
    assert len(cortar(dados, 100, 0.5, 0)) == 50


def test_cortar_alem_do_fim_devolve_vazio():
    dados = np.zeros((10, 1), dtype=np.float32)
    assert len(cortar(dados, 10, 5.0, 0)) == 0


def test_interpretar_atalhos():
    soundpad = pytest.importorskip("soundpad")
    interpretar = soundpad.App._interpretar
    assert len(interpretar("ctrl+1")) == 2
    assert len(interpretar("f5")) == 1
    assert interpretar("ctrl+1, ctrl+2") is None   # sequência não é suportada
    assert interpretar("tecla_inexistente") is None
