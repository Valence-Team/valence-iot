from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.exceptions import RequestValidationError
from pydantic import TypeAdapter, ValidationError
from starlette.datastructures import UploadFile
from starlette.formparsers import MultiPartException, MultiPartParser

from app.dependencias import ComponentesDep, ConfigDep, respostas_erro
from app.erros import ErroApi
from app.schemas import ClassificacaoResponse, Cultura, CulturaEntrada
from app.seguranca import exigir_chave_api
from app.visao.fluxo import executar_camadas
from app.visao.qualidade import abrir_imagem, validar_tamanho, validar_tipo

router = APIRouter(
    prefix="/api/v1/visao",
    tags=["Visão computacional"],
    dependencies=[Depends(exigir_chave_api)],
)

MARGEM_MULTIPART = 64 * 1024
VALIDADOR_CULTURA = TypeAdapter(CulturaEntrada)

CORPO_OPENAPI: dict[str, Any] = {
    "requestBody": {
        "required": True,
        "content": {
            "multipart/form-data": {
                "schema": {
                    "type": "object",
                    "required": ["imagem", "cultura"],
                    "properties": {
                        "imagem": {
                            "type": "string",
                            "format": "binary",
                            "description": "Foto da folha em JPEG, PNG ou WebP",
                        },
                        "cultura": {
                            "type": "string",
                            "enum": [cultura.value for cultura in Cultura],
                            "description": "MILHO, TOMATE ou BATATA; aceita minúsculas",
                        },
                    },
                }
            }
        },
    }
}


@dataclass(frozen=True)
class Formulario:
    dados: bytes
    tipo: str | None
    cultura: Cultura


# Leitura do multipart só em memória
async def ler_corpo(request: Request, limite_mb: int) -> bytes:
    limite = limite_mb * 1024 * 1024 + MARGEM_MULTIPART
    excedeu = ErroApi(413, f"A imagem deve ter no máximo {limite_mb} MB.")
    declarado = request.headers.get("content-length", "")
    if declarado.isdigit() and int(declarado) > limite:
        raise excedeu
    corpo = bytearray()
    async for pedaco in request.stream():
        corpo.extend(pedaco)
        if len(corpo) > limite:
            raise excedeu
    return bytes(corpo)


async def _repetir(corpo: bytes) -> AsyncIterator[bytes]:
    yield corpo


def _ausente(campo: str) -> dict[str, Any]:
    return {"type": "missing", "loc": ("body", campo), "msg": "Field required", "input": None}


async def ler_formulario(request: Request, limite_mb: int) -> Formulario:
    corpo = await ler_corpo(request, limite_mb)
    campos: dict[str, Any] = {}
    if request.headers.get("content-type", "").startswith("multipart/form-data"):
        parser = MultiPartParser(request.headers, _repetir(corpo), max_files=1, max_fields=4)
        parser.spool_max_size = len(corpo) + 1
        try:
            formulario = await parser.parse()
        except MultiPartException:
            raise ErroApi(400, "O corpo multipart está malformado.") from None
        campos = dict(formulario)

    erros: list[dict[str, Any]] = []
    imagem = campos.get("imagem")
    if not isinstance(imagem, UploadFile):
        erros.append(_ausente("imagem"))
    cultura = None
    if not isinstance(campos.get("cultura"), str):
        erros.append(_ausente("cultura"))
    else:
        try:
            cultura = VALIDADOR_CULTURA.validate_python(campos["cultura"])
        except ValidationError as exc:
            erros.extend({**e, "loc": ("body", "cultura", *e["loc"])} for e in exc.errors())
    if erros:
        raise RequestValidationError(erros)

    dados = await imagem.read()
    tipo = imagem.content_type
    await imagem.close()
    return Formulario(dados=dados, tipo=tipo, cultura=cultura)


@router.post(
    "/classificar",
    response_model=ClassificacaoResponse,
    responses=respostas_erro(400, 401, 413, 415, 503),
    summary="Classifica a doença na foto da folha",
    openapi_extra=CORPO_OPENAPI,
)
async def classificar(
    request: Request,
    config: ConfigDep,
    componentes: ComponentesDep,
) -> ClassificacaoResponse:
    formulario = await ler_formulario(request, config.tamanho_maximo_mb)
    validar_tipo(formulario.tipo)
    validar_tamanho(formulario.dados, config.tamanho_maximo_mb)
    figura = await run_in_threadpool(abrir_imagem, formulario.dados)

    if componentes.visao is None or componentes.portao is None:
        raise ErroApi(503, "O modelo de visão não está carregado.")

    resultado = await run_in_threadpool(
        executar_camadas, figura, formulario.cultura, componentes.portao, componentes.visao
    )
    return ClassificacaoResponse(
        imagem_valida=resultado.motivo is None,
        motivo=resultado.motivo,
        cultura_detectada=resultado.cultura_detectada,
        classes=resultado.classes,
    )
