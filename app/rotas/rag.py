import logging

from fastapi import APIRouter, Depends
from fastapi.concurrency import run_in_threadpool

from app.dependencias import ComponentesDep, RotulosDep, respostas_erro
from app.erros import ErroApi
from app.schemas import ConsultaRagRequest, ConsultaRagResponse
from app.seguranca import exigir_chave_api

logger = logging.getLogger("valence_ia.rag")

router = APIRouter(
    prefix="/api/v1/rag",
    tags=["RAG e explicação"],
    dependencies=[Depends(exigir_chave_api)],
)

TRECHOS_POR_CONSULTA = 3


@router.post(
    "/consultar",
    response_model=ConsultaRagResponse,
    responses=respostas_erro(400, 401, 422, 503),
    summary="Busca trechos de fichas técnicas e gera a explicação",
)
async def consultar(
    consulta: ConsultaRagRequest,
    componentes: ComponentesDep,
    rotulos: RotulosDep,
) -> ConsultaRagResponse:
    desconhecidos = [rotulo for rotulo in consulta.classes if rotulo not in rotulos]
    if desconhecidos:
        raise ErroApi(
            400,
            "Um ou mais campos são inválidos.",
            [{"campo": "classes", "mensagem": f"Rótulo desconhecido: {', '.join(desconhecidos)}."}],
        )

    classes = [rotulos[rotulo] for rotulo in consulta.classes]
    de_outra_cultura = [c.rotulo for c in classes if c.cultura != consulta.cultura]
    if de_outra_cultura:
        raise ErroApi(
            422,
            f"As classes {', '.join(de_outra_cultura)} não pertencem à cultura {consulta.cultura}.",
        )

    if componentes.indice is None:
        raise ErroApi(503, "O índice de fichas técnicas não está carregado.")

    texto_busca = " ".join([consulta.sintomas, *(c.nome for c in classes)])
    trechos = await run_in_threadpool(
        componentes.indice.buscar, texto_busca, consulta.cultura, TRECHOS_POR_CONSULTA
    )

    explicacao = None
    if componentes.llm is not None:
        try:
            explicacao = await run_in_threadpool(
                componentes.llm.explicar, consulta.cultura, consulta.sintomas, classes, trechos
            )
        except Exception as exc:
            logger.warning("falha no LLM tipo=%s", type(exc).__name__)

    return ConsultaRagResponse(
        trechos=trechos,
        explicacao=explicacao.texto if explicacao else None,
        modelo_llm=explicacao.modelo if explicacao else None,
    )
