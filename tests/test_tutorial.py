import soundfile as sf

from tutorial_passos import (NOME_EXEMPLO, PASSOS, Roteiro, cabo_instalado,
                             caminho_exemplo, copiar_exemplo)


def ir_ate_passo_com_evento(roteiro):
    while roteiro.atual.evento is None:
        assert roteiro.avancar()


def test_ids_dos_passos_sao_unicos():
    ids = [p.id for p in PASSOS]
    assert len(ids) == len(set(ids))


def test_passo_sem_evento_avanca_direto():
    roteiro = Roteiro()
    assert roteiro.cumprido
    assert roteiro.avancar()
    assert roteiro.indice == 1


def test_passo_com_evento_so_avanca_depois_de_cumprido():
    roteiro = Roteiro()
    ir_ate_passo_com_evento(roteiro)
    assert not roteiro.cumprido
    assert not roteiro.avancar()
    assert roteiro.notificar(roteiro.atual.evento)
    assert roteiro.avancar()


def test_evento_errado_nao_cumpre_o_passo():
    roteiro = Roteiro()
    ir_ate_passo_com_evento(roteiro)
    assert not roteiro.notificar("outra_coisa")
    assert not roteiro.cumprido


def test_evento_repetido_so_conta_uma_vez():
    roteiro = Roteiro()
    ir_ate_passo_com_evento(roteiro)
    assert roteiro.notificar(roteiro.atual.evento)
    assert not roteiro.notificar(roteiro.atual.evento)


def test_voltar_mantem_passos_cumpridos():
    roteiro = Roteiro()
    ir_ate_passo_com_evento(roteiro)
    passo = roteiro.atual
    roteiro.notificar(passo.evento)
    roteiro.voltar()
    roteiro.avancar()
    assert roteiro.atual is passo and roteiro.cumprido


def test_roteiro_completo_ate_o_fim():
    roteiro = Roteiro()
    assert roteiro.primeiro and not roteiro.voltar()
    while not roteiro.ultimo:
        if roteiro.atual.evento:
            roteiro.notificar(roteiro.atual.evento)
        assert roteiro.avancar()
    assert roteiro.indice == roteiro.total - 1
    assert not roteiro.avancar()


def test_cabo_instalado():
    assert cabo_instalado(["Alto-falantes", "CABLE Input (VB-Audio Virtual C"])
    assert not cabo_instalado(["Alto-falantes"])
    assert not cabo_instalado([])


def test_copiar_exemplo(tmp_path):
    sons = tmp_path / "sons"
    assert copiar_exemplo(sons) == NOME_EXEMPLO
    assert (sons / NOME_EXEMPLO).is_file()
    # Já existe: não sobrescreve nem falha
    (sons / NOME_EXEMPLO).write_bytes(b"meu")
    assert copiar_exemplo(sons) == NOME_EXEMPLO
    assert (sons / NOME_EXEMPLO).read_bytes() == b"meu"


def test_copiar_exemplo_sem_origem(tmp_path):
    assert copiar_exemplo(tmp_path / "sons", origem=tmp_path / "nao-existe.wav") is None


def test_som_de_exemplo_e_valido():
    dados, taxa = sf.read(str(caminho_exemplo()), dtype="float32")
    assert 0.3 < len(dados) / taxa < 3
    assert 0.2 < abs(dados).max() <= 1.0
