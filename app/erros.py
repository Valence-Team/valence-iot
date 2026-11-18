import logging
import traceback
from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("valence_ia.erros")

TITULOS = {
    400: "Requisição inválida",
    401: "Não autorizado",
    403: "Acesso negado",
    404: "Não encontrado",
    405: "Método não permitido",
    413: "Conteúdo muito grande",
    415: "Tipo de mídia não suportado",
    422: "Regra de negócio violada",
    500: "Erro interno",
    503: "Serviço indisponível",
}

MENSAGENS_PADRAO = {
    400: "A requisição não pôde ser processada.",
    401: "Credencial ausente ou inválida.",
    403: "Acesso negado a este recurso.",
    404: "Recurso não encontrado.",
    405: "Método não permitido para este recurso.",
    413: "O conteúdo enviado excede o tamanho máximo permitido.",
    415: "Tipo de arquivo não suportado.",
    422: "A requisição viola uma regra de negócio.",
    500: "Ocorreu um erro inesperado. Tente novamente mais tarde.",
    503: "O serviço está temporariamente indisponível.",
}


class ComponenteIndisponivel(Exception):
    pass


class ErroApi(Exception):
    def __init__(
        self,
        status: int,
        mensagem: str | None = None,
        campos: list[dict[str, str]] | None = None,
    ) -> None:
        self.status = status
        self.mensagem = mensagem or MENSAGENS_PADRAO.get(status, "Erro na requisição.")
        self.campos = campos or []
        super().__init__(self.mensagem)


def corpo_erro(
    status: int,
    mensagem: str,
    caminho: str,
    campos: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    return {
        "timestamp": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": status,
        "erro": TITULOS.get(status, "Erro"),
        "mensagem": mensagem,
        "caminho": caminho,
        "campos": campos or [],
    }


def resposta_erro(
    request: Request,
    status: int,
    mensagem: str,
    campos: list[dict[str, str]] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content=corpo_erro(status, mensagem, request.url.path, campos),
        headers=headers,
    )


# Tradução dos erros de validação
def _mensagem_validacao(erro: dict[str, Any]) -> str:
    tipo = erro.get("type", "")
    ctx = erro.get("ctx") or {}
    if tipo == "missing":
        return "Campo obrigatório."
    if tipo == "string_too_long":
        return f"Deve ter no máximo {ctx.get('max_length')} caracteres."
    if tipo == "string_too_short":
        return f"Deve ter no mínimo {ctx.get('min_length')} caracteres."
    if tipo == "too_long":
        return f"Deve ter no máximo {ctx.get('max_length')} itens."
    if tipo == "too_short":
        return f"Deve ter no mínimo {ctx.get('min_length')} itens."
    if tipo == "enum":
        esperado = str(ctx.get("expected", "")).replace("'", "").replace(" or ", " ou ")
        return f"Valor inválido. Use {esperado}."
    if tipo in {"string_type", "str_type"}:
        return "Deve ser um texto."
    if tipo == "list_type":
        return "Deve ser uma lista."
    if tipo == "json_invalid":
        return "JSON malformado."
    if tipo in {"model_attributes_type", "dict_type", "model_type"}:
        return "Deve ser um objeto JSON."
    if tipo == "value_error" and "error" in ctx:
        return str(ctx["error"])
    return "Valor inválido."


def _nome_campo(loc: tuple[Any, ...] | list[Any]) -> str:
    partes = [str(p) for p in loc if p not in ("body", "query", "path", "header", "form")]
    return ".".join(partes) or "corpo"


def campos_validacao(exc: RequestValidationError) -> list[dict[str, str]]:
    return [
        {"campo": _nome_campo(erro.get("loc", ())), "mensagem": _mensagem_validacao(erro)}
        for erro in exc.errors()
    ]


# Handlers
async def _tratar_erro_api(request: Request, exc: ErroApi) -> JSONResponse:
    return resposta_erro(request, exc.status, exc.mensagem, exc.campos)


async def _tratar_http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    mensagem = MENSAGENS_PADRAO.get(exc.status_code, "Erro na requisição.")
    return resposta_erro(request, exc.status_code, mensagem, headers=exc.headers)


async def _tratar_validacao(request: Request, exc: RequestValidationError) -> JSONResponse:
    return resposta_erro(
        request,
        400,
        "Um ou mais campos são inválidos.",
        campos_validacao(exc),
    )


async def _tratar_inesperado(request: Request, exc: Exception) -> JSONResponse:
    pilha = "".join(traceback.format_tb(exc.__traceback__))
    logger.error("erro inesperado tipo=%s\n%s", type(exc).__name__, pilha)
    return resposta_erro(request, 500, MENSAGENS_PADRAO[500])


def registrar_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ErroApi, _tratar_erro_api)
    app.add_exception_handler(StarletteHTTPException, _tratar_http)
    app.add_exception_handler(RequestValidationError, _tratar_validacao)
    app.add_exception_handler(Exception, _tratar_inesperado)
