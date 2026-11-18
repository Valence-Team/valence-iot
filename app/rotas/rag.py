from fastapi import APIRouter, Depends
from fastapi.concurrency import run_in_threadpool

from app.dependencias import ComponentesDep, RotulosDep, respostas_erro
from app.erros import ErroApi
from app.rag.consulta import consultar as executar_consulta
from app.schemas import ConsultaRagRequest, ConsultaRagResponse
from app.seguranca import exigir_chave_api

router = APIRouter(
    prefix="/api/v1/rag",
    tags=["RAG e explicação"],
    dependencies=[Depends(exigir_chave_api)],
)


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

    return await run_in_threadpool(
        executar_consulta,
        consulta.cultura,
        consulta.sintomas,
        classes,
        componentes.indice,
        componentes.llm,
    )
