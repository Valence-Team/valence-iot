import io
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.concurrency import run_in_threadpool
from PIL import Image, UnidentifiedImageError

from app.dependencias import ComponentesDep, ConfigDep, respostas_erro
from app.erros import ErroApi
from app.schemas import ClassificacaoResponse, CulturaEntrada
from app.seguranca import exigir_chave_api

router = APIRouter(
    prefix="/api/v1/visao",
    tags=["Visão computacional"],
    dependencies=[Depends(exigir_chave_api)],
)

TIPOS_ACEITOS = {"image/jpeg", "image/png", "image/webp"}
TIPOS_GENERICOS = {"application/octet-stream", None, ""}
FORMATOS_ACEITOS = {"JPEG", "PNG", "WEBP"}
MENSAGEM_TIPO = "Envie uma imagem JPEG, PNG ou WebP."


# Leitura e validação da imagem
def abrir_imagem(dados: bytes) -> Image.Image:
    try:
        with Image.open(io.BytesIO(dados)) as verificada:
            verificada.verify()
        imagem = Image.open(io.BytesIO(dados))
        imagem.load()
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError, Image.DecompressionBombError):
        raise ErroApi(400, "Não foi possível ler a imagem enviada.") from None
    if imagem.format not in FORMATOS_ACEITOS:
        raise ErroApi(415, MENSAGEM_TIPO)
    return imagem.convert("RGB")


@router.post(
    "/classificar",
    response_model=ClassificacaoResponse,
    responses=respostas_erro(400, 401, 413, 415, 503),
    summary="Classifica a doença na foto da folha",
)
async def classificar(
    imagem: Annotated[UploadFile, File(description="Foto da folha em JPEG, PNG ou WebP")],
    cultura: Annotated[CulturaEntrada, Form(description="MILHO, TOMATE ou BATATA")],
    config: ConfigDep,
    componentes: ComponentesDep,
) -> ClassificacaoResponse:
    if imagem.content_type not in TIPOS_ACEITOS | TIPOS_GENERICOS:
        raise ErroApi(415, MENSAGEM_TIPO)

    limite = config.tamanho_maximo_bytes
    dados = await imagem.read(limite + 1)
    if len(dados) > limite:
        raise ErroApi(413, f"A imagem deve ter no máximo {config.tamanho_maximo_mb} MB.")

    figura = abrir_imagem(dados)

    if componentes.visao is None or componentes.portao is None:
        raise ErroApi(503, "O modelo de visão não está carregado.")

    veredito = await run_in_threadpool(componentes.portao.verificar, figura, cultura)
    if veredito.motivo is not None:
        return ClassificacaoResponse(
            imagem_valida=False,
            motivo=veredito.motivo,
            cultura_detectada=veredito.cultura_detectada,
            classes=[],
        )

    classes = await run_in_threadpool(componentes.visao.classificar, figura, cultura)
    return ClassificacaoResponse(
        imagem_valida=True,
        motivo=None,
        cultura_detectada=veredito.cultura_detectada or cultura,
        classes=classes[:3],
    )
