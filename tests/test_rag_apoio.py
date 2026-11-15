import hashlib
import re
from collections.abc import Sequence
from types import SimpleNamespace

import httpx
import numpy as np
import openai

from app.rag.fichas import TrechoFicha
from app.rag.indice import IndiceVetorial
from app.rag.llm import ClienteLlmComReserva, Provedor
from app.schemas import Cultura

DIMENSAO = 256


# Codificador determinístico: saco de palavras com hashing
class CodificadorFalso:
    def __init__(self, modelo: str = "codificador-falso") -> None:
        self.modelo = modelo
        self.chamadas: list[tuple[str, tuple[str, ...]]] = []

    def codificar(self, textos: Sequence[str], papel: str) -> np.ndarray:
        self.chamadas.append((papel, tuple(textos)))
        vetores = np.zeros((len(textos), DIMENSAO), dtype=np.float32)
        for i, texto in enumerate(textos):
            for palavra in re.findall(r"\w+", texto.lower()):
                if len(palavra) < 4:
                    continue
                posicao = int(hashlib.md5(palavra.encode()).hexdigest(), 16) % DIMENSAO
                vetores[i, posicao] += 1.0
        normas = np.linalg.norm(vetores, axis=1, keepdims=True)
        return vetores / np.maximum(normas, 1e-12)


def trecho(ficha: str, texto: str, culturas=(Cultura.MILHO,), rotulos=()) -> TrechoFicha:
    titulo = ficha.replace("-", " ").capitalize()
    return TrechoFicha(
        texto=f"{titulo}. Sintomas: {texto}",
        titulo=titulo,
        culturas=tuple(culturas),
        rotulos=tuple(rotulos),
        fonte="Embrapa (teste)",
        url=f"https://www.embrapa.br/{ficha}",
        secao="Sintomas",
        ficha=ficha,
    )


TRECHOS_PEQUENOS = [
    trecho(
        "milho-ferrugem",
        "pústulas marrons de ferrugem nas duas faces da folha soltam pó cor de ferrugem",
        rotulos=("milho_ferrugem_comum",),
    ),
    trecho(
        "milho-cercosporiose",
        "manchas cinzentas retangulares paralelas às nervuras da folha",
        rotulos=("milho_cercosporiose",),
    ),
    trecho(
        "milho-cigarrinha",
        "plantas avermelhadas baixas com espigas pequenas e cigarrinhas no cartucho",
    ),
    trecho(
        "tomate-requeima",
        "manchas grandes úmidas com mofo branco nas folhas do tomate",
        culturas=(Cultura.TOMATE,),
        rotulos=("tomate_requeima",),
    ),
    trecho(
        "murcha-bacteriana",
        "plantas murchas nas horas quentes em reboleiras com vasos escuros",
        culturas=(Cultura.TOMATE, Cultura.BATATA),
    ),
]


def indice_pequeno(minimo: float = 0.2) -> IndiceVetorial:
    indice = IndiceVetorial.construir(TRECHOS_PEQUENOS, CodificadorFalso())
    indice.minimo = minimo
    return indice


# Cliente OpenAI falso
def _requisicao() -> httpx.Request:
    return httpx.Request("POST", "https://llm.teste/v1/chat/completions")


def erro_429() -> openai.RateLimitError:
    resposta = httpx.Response(429, request=_requisicao())
    return openai.RateLimitError("limite atingido", response=resposta, body=None)


def erro_timeout() -> openai.APITimeoutError:
    return openai.APITimeoutError(request=_requisicao())


def erro_500() -> openai.InternalServerError:
    resposta = httpx.Response(500, request=_requisicao())
    return openai.InternalServerError("falha", response=resposta, body=None)


class ClienteOpenAiFalso:
    def __init__(self, resposta: str | Exception | None, raciocinio: str | None = None) -> None:
        self.resposta = resposta
        self.raciocinio = raciocinio
        self.pedidos: list[dict] = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._criar))

    def _criar(self, **pedido):
        self.pedidos.append(pedido)
        if isinstance(self.resposta, Exception):
            raise self.resposta
        mensagem = SimpleNamespace(content=self.resposta, reasoning=self.raciocinio)
        return SimpleNamespace(choices=[SimpleNamespace(message=mensagem, finish_reason="stop")])


RESPOSTA_BOA = (
    "Pode ser ferrugem-comum: as pústulas cor de ferrugem nas duas faces da folha são típicas [1]. "
    "Prefira cultivares resistentes e acompanhe a lavoura [1]. É uma suspeita: procure o agrônomo "
    "para confirmar."
)


def cliente_llm(*respostas) -> tuple[ClienteLlmComReserva, list[ClienteOpenAiFalso]]:
    falsos = [ClienteOpenAiFalso(r) for r in respostas]
    nomes = ["principal", "reserva"]
    provedores = [
        Provedor(nomes[i], f"modelo-{nomes[i]}", falso, {}) for i, falso in enumerate(falsos)
    ]
    return ClienteLlmComReserva(provedores), falsos
