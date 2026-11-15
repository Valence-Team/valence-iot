import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from app.schemas import Cultura

FICHAS_PATH = Path(__file__).resolve().parent.parent.parent / "dados" / "fichas"

SECOES = (
    "Sintomas",
    "Condições favoráveis",
    "Disseminação",
    "Manejo cultural e preventivo",
    "Quando chamar o agrônomo",
)
CAMPOS_OBRIGATORIOS = ("id", "titulo", "cultura", "rotulos", "fonte", "url", "acessadoEm")

# Tamanho dos trechos, em palavras, contando o título
PALAVRAS_MINIMAS = 60
PALAVRAS_MAXIMAS = 200

_FRONT_MATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n(.*)\Z", re.S)
_SECAO = re.compile(r"^## +(.+?)\s*$", re.M)


@dataclass(frozen=True)
class Ficha:
    id: str
    titulo: str
    culturas: tuple[Cultura, ...]
    rotulos: tuple[str, ...]
    nome_cientifico: str | None
    fonte: str
    url: str
    acessado_em: str
    secoes: dict[str, str]


@dataclass(frozen=True)
class TrechoFicha:
    texto: str
    titulo: str
    culturas: tuple[Cultura, ...]
    rotulos: tuple[str, ...]
    fonte: str
    url: str
    secao: str
    ficha: str

    def para_json(self) -> dict:
        return {
            "texto": self.texto,
            "titulo": self.titulo,
            "cultura": [c.value for c in self.culturas],
            "rotulos": list(self.rotulos),
            "fonte": self.fonte,
            "url": self.url,
            "secao": self.secao,
            "ficha": self.ficha,
        }

    @classmethod
    def de_json(cls, dados: dict) -> "TrechoFicha":
        return cls(
            texto=dados["texto"],
            titulo=dados["titulo"],
            culturas=tuple(Cultura(c) for c in dados["cultura"]),
            rotulos=tuple(dados["rotulos"]),
            fonte=dados["fonte"],
            url=dados["url"],
            secao=dados["secao"],
            ficha=dados["ficha"],
        )


# Leitura das fichas
def ler_ficha(caminho: Path) -> Ficha:
    texto = caminho.read_text(encoding="utf-8")
    partes = _FRONT_MATTER.match(texto)
    if partes is None:
        raise ValueError(f"{caminho.name}: front matter ausente")
    meta = yaml.safe_load(partes.group(1)) or {}
    faltando = [campo for campo in CAMPOS_OBRIGATORIOS if campo not in meta]
    if faltando:
        raise ValueError(f"{caminho.name}: campos ausentes: {', '.join(faltando)}")

    culturas = meta["cultura"] if isinstance(meta["cultura"], list) else [meta["cultura"]]
    secoes = _secoes(partes.group(2))
    if tuple(secoes) != SECOES:
        raise ValueError(f"{caminho.name}: seções esperadas {SECOES}, encontradas {tuple(secoes)}")
    return Ficha(
        id=str(meta["id"]),
        titulo=str(meta["titulo"]),
        culturas=tuple(Cultura(str(c).upper()) for c in culturas),
        rotulos=tuple(meta["rotulos"] or ()),
        nome_cientifico=meta.get("nomeCientifico"),
        fonte=str(meta["fonte"]),
        url=str(meta["url"]),
        acessado_em=str(meta["acessadoEm"]),
        secoes=secoes,
    )


def _secoes(corpo: str) -> dict[str, str]:
    cabecalhos = list(_SECAO.finditer(corpo))
    secoes = {}
    for i, cabecalho in enumerate(cabecalhos):
        fim = cabecalhos[i + 1].start() if i + 1 < len(cabecalhos) else len(corpo)
        secoes[cabecalho.group(1)] = " ".join(corpo[cabecalho.end() : fim].split())
    return secoes


def ler_fichas(pasta: Path = FICHAS_PATH) -> list[Ficha]:
    fichas = [ler_ficha(caminho) for caminho in sorted(pasta.glob("*.md"))]
    ids = [ficha.id for ficha in fichas]
    repetidos = {i for i in ids if ids.count(i) > 1}
    if repetidos:
        raise ValueError(f"ids repetidos: {', '.join(sorted(repetidos))}")
    return fichas


# Quebra em trechos
def _contar(texto: str) -> int:
    return len(texto.split())


def _dividir(texto: str, limite: int) -> list[str]:
    frases = re.split(r"(?<=[.!?])\s+", texto)
    partes, atual = [], []
    for frase in frases:
        if atual and _contar(" ".join([*atual, frase])) > limite:
            partes.append(" ".join(atual))
            atual = []
        atual.append(frase)
    if atual:
        partes.append(" ".join(atual))
    return partes


def quebrar_em_trechos(ficha: Ficha) -> list[TrechoFicha]:
    blocos: list[tuple[str, str]] = []
    for nome, texto in ficha.secoes.items():
        prefixo = f"{ficha.titulo}. {nome}:"
        limite = PALAVRAS_MAXIMAS - _contar(prefixo)
        for parte in _dividir(texto, limite):
            blocos.append((nome, parte))

    # Seção curta junta com a anterior da mesma ficha
    unidos: list[tuple[str, str]] = []
    for nome, texto in blocos:
        curto = _contar(f"{ficha.titulo}. {nome}: {texto}") < PALAVRAS_MINIMAS
        if curto and unidos:
            nome_anterior, texto_anterior = unidos[-1]
            junto = f"{texto_anterior} {nome}: {texto}"
            if _contar(f"{ficha.titulo}. {nome_anterior}: {junto}") <= PALAVRAS_MAXIMAS:
                unidos[-1] = (f"{nome_anterior}; {nome}", junto)
                continue
        unidos.append((nome, texto))

    return [
        TrechoFicha(
            texto=f"{ficha.titulo}. {nome}: {texto}",
            titulo=ficha.titulo,
            culturas=ficha.culturas,
            rotulos=ficha.rotulos,
            fonte=ficha.fonte,
            url=ficha.url,
            secao=nome,
            ficha=ficha.id,
        )
        for nome, texto in unidos
    ]
