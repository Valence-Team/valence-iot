import hmac
import re
from typing import Annotated

from fastapi import Request, Security
from fastapi.security import APIKeyHeader

from app.erros import ErroApi

MARCADOR = "[removido]"

cabecalho_chave = APIKeyHeader(name="X-API-Key", auto_error=False)


# Chave de acesso entre a API Java e o serviço de IA
def exigir_chave_api(
    request: Request,
    chave: Annotated[str | None, Security(cabecalho_chave)],
) -> None:
    esperada = request.app.state.config.ia_api_key.get_secret_value()
    if not esperada:
        return
    recebida = chave or ""
    if not hmac.compare_digest(recebida.encode("utf-8"), esperada.encode("utf-8")):
        raise ErroApi(401)


# Mascaramento de dados pessoais
PADROES_DADOS_PESSOAIS = {
    "email": re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"),
    "par_de_coordenadas": re.compile(
        r"(?<![\w.,])[-+]?\d{1,3}[.,]\d{4,}\s*[,;/]?\s*[-+]?\d{1,3}[.,]\d{4,}(?!\d)"
    ),
    "coordenada": re.compile(r"(?<![\w.,])[-+]?\d{1,3}\.\d{4,}(?!\d)"),
    "cpf": re.compile(r"(?<!\d)\d{3}\.?\d{3}\.?\d{3}-?\d{2}(?!\d)"),
    "telefone": re.compile(
        r"(?<![\w+])(?:\+?55[\s.-]?)?(?:\(?\d{2}\)?[\s.-]?)?9?\s?\d{4}[\s.-]?\d{4}(?!\d)"
    ),
    "cep": re.compile(r"(?<!\d)\d{2}\.?\d{3}-?\d{3}(?!\d)"),
}
PADRAO_NOME = re.compile(
    r"(?i:\b(?:meu nome [ée]|me chamo|eu sou|sou|aqui [ée]|quem fala [ée])\s+(?:[oa]\s+)?)"
    r"([A-ZÀ-Ý][a-zà-ÿ]+(?:\s+(?:d[aeo]s?\s+)?[A-ZÀ-Ý][a-zà-ÿ]+)*)"
)


def _trocar_nome(encontrado: re.Match[str]) -> str:
    inicio = encontrado.start(1) - encontrado.start(0)
    return encontrado.group(0)[:inicio] + MARCADOR


def mascarar_dados_pessoais(texto: str) -> str:
    for padrao in PADROES_DADOS_PESSOAIS.values():
        texto = padrao.sub(MARCADOR, texto)
    return PADRAO_NOME.sub(_trocar_nome, texto)
