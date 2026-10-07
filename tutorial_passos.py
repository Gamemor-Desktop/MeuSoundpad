"""Lógica do tutorial de primeira execução (sem interface, para poder ser testada)."""

import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

URL_VBCABLE = "https://vb-audio.com/Cable/"
NOME_EXEMPLO = "exemplo-ding.wav"


@dataclass(frozen=True)
class Passo:
    id: str
    titulo: str
    texto: str
    alvo: str | None = None      # parte da janela que fica destacada
    evento: str | None = None    # evento que o usuário precisa causar para avançar
    acoes: tuple = ()            # botões extras: (id da ação, rótulo)


PASSOS = (
    Passo(
        "boas_vindas",
        "Bem-vindo ao Meu Soundpad!",
        "Este tour rápido mostra como tocar sons no seu microfone (Discord, jogos etc.) "
        "com atalhos globais.\n\nSão só 6 passos, e você pode pular ou refazer o tour "
        "depois pelo botão \"?  Tutorial\".",
    ),
    Passo(
        "vbcable",
        "Instale o VB-Cable",
        "O VB-Cable é um microfone virtual gratuito: o app toca os sons nele e o "
        "Discord ou o jogo \"escuta\" esse microfone.\n\nBaixe o instalador, execute "
        "VBCABLE_Setup_x64.exe como administrador e reinicie o PC.",
        acoes=(("baixar", "Baixar o VB-Cable"), ("verificar", "Verificar de novo")),
    ),
    Passo(
        "adicionar",
        "Adicione um som",
        "Use o botão \"+ Adicionar sons\", ou arraste arquivos .mp3, .wav, .ogg ou "
        ".flac para a lista.\n\nPara praticar, o app traz um som de exemplo. "
        "Clique em \"Adicionar o som de exemplo\".",
        alvo="adicionar",
        evento="som_adicionado",
        acoes=(("exemplo", "Adicionar o som de exemplo"),),
    ),
    Passo(
        "tocar",
        "Toque o som",
        "Selecione o som na lista e dê dois cliques nele (ou aperte Enter, ou use o "
        "botão \"Tocar\").\n\nCom \"Ouvir nos fones\" ligado em Configurações, você "
        "também escuta o som. Toque o som agora.",
        alvo="painel",
        evento="som_tocado",
        acoes=(("tocar", "Tocar agora"),),
    ),
    Passo(
        "atalho",
        "Defina um atalho",
        "Com o som selecionado, clique em \"Definir\" e aperte uma combinação de "
        "teclas, por exemplo Ctrl+1. Esc cancela.\n\nO atalho funciona mesmo com o "
        "jogo ou o Discord em foco.",
        alvo="atalho",
        evento="atalho_definido",
        acoes=(("definir", "Definir atalho agora"),),
    ),
    Passo(
        "discord",
        "Configure o Discord ou o jogo",
        "Em \"Microfone / Dispositivo de entrada\", escolha CABLE Output (VB-Audio "
        "Virtual Cable). No Discord, desligue a supressão de ruído (Krisp).\n\n"
        "Para sua voz sair junto com os sons: na aba Gravação, abra as propriedades "
        "do seu microfone, vá em Escutar, marque \"Escutar este dispositivo\" e "
        "escolha CABLE Input.\n\nAs saídas e os volumes ficam em Configurações.",
        alvo="config",
        acoes=(("mmsys", "Abrir configurações de som"),),
    ),
)


class Roteiro:
    """Estado do tour: passo atual e quais passos já foram cumpridos."""

    def __init__(self, passos=PASSOS):
        self.passos = tuple(passos)
        self.indice = 0
        self.cumpridos = set()

    @property
    def atual(self):
        return self.passos[self.indice]

    @property
    def total(self):
        return len(self.passos)

    @property
    def primeiro(self):
        return self.indice == 0

    @property
    def ultimo(self):
        return self.indice == self.total - 1

    @property
    def cumprido(self):
        """O passo atual não exige nada ou o usuário já fez o que ele pede."""
        return self.atual.evento is None or self.atual.id in self.cumpridos

    def notificar(self, evento):
        """Registra algo que o usuário fez. Devolve True se cumpriu o passo atual."""
        if evento == self.atual.evento and self.atual.id not in self.cumpridos:
            self.cumpridos.add(self.atual.id)
            return True
        return False

    def avancar(self):
        """Vai ao próximo passo. Devolve False se o passo atual ainda não foi cumprido."""
        if not self.cumprido or self.ultimo:
            return False
        self.indice += 1
        return True

    def voltar(self):
        if self.primeiro:
            return False
        self.indice -= 1
        return True


def cabo_instalado(nomes):
    """True se algum dispositivo de saída é o VB-Cable."""
    return any("cable input" in nome.lower() for nome in nomes)


def pasta_recursos():
    """Pasta com os arquivos que acompanham o app (dentro do .exe ou ao lado do código)."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    return Path(__file__).resolve().parent


def caminho_exemplo():
    return pasta_recursos() / "exemplos" / NOME_EXEMPLO


def copiar_exemplo(pasta_sons, origem=None):
    """Copia o som de exemplo para a pasta de sons. Devolve o nome do arquivo ou None."""
    origem = Path(origem) if origem else caminho_exemplo()
    if not origem.is_file():
        return None
    destino = Path(pasta_sons) / origem.name
    if not destino.exists():
        Path(pasta_sons).mkdir(parents=True, exist_ok=True)
        shutil.copy2(origem, destino)
    return origem.name
