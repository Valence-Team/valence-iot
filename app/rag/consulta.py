import logging
from time import perf_counter

from app.rag import ClienteLlm, Indice
from app.rag.guardrails import EXPLICACAO_FIXA
from app.rag.indice import TOP_K
from app.rag.prompts import NOMES_CULTURA
from app.rotulos import Rotulo
from app.schemas import ConsultaRagResponse, Cultura
from app.seguranca import mascarar_dados_pessoais

logger = logging.getLogger("valence_ia.rag")


def texto_de_busca(cultura: Cultura, classes: list[Rotulo], sintomas: str) -> str:
    return " ".join([NOMES_CULTURA[cultura], *(c.nome for c in classes), sintomas]).strip()


# Folha saudável não ganha bônus: puxaria a ficha de monitoramento à frente de pragas
# que o modelo de visão não conhece (ver avaliacao/rag/metricas.md)
def rotulos_com_bonus(classes: list[Rotulo]) -> list[str]:
    return [c.rotulo for c in classes if not c.saudavel]


def consultar(
    cultura: Cultura,
    sintomas: str,
    classes: list[Rotulo],
    indice: Indice,
    llm: ClienteLlm | None,
) -> ConsultaRagResponse:
    # Mascaramento antes de qualquer uso, mesmo que a validação já tenha mascarado
    sintomas = mascarar_dados_pessoais(sintomas)

    inicio = perf_counter()
    trechos = indice.buscar(
        texto_de_busca(cultura, classes, sintomas),
        cultura,
        TOP_K,
        rotulos_com_bonus(classes),
    )
    busca_ms = (perf_counter() - inicio) * 1000

    if not trechos:
        logger.info("rag trechos=0 busca_ms=%.0f explicacao=fixa", busca_ms)
        return ConsultaRagResponse(trechos=[], explicacao=EXPLICACAO_FIXA, modelo_llm=None)

    explicacao = None
    if llm is not None:
        try:
            explicacao = llm.explicar(cultura, sintomas, classes, trechos)
        except Exception as exc:
            logger.warning("rag falha no LLM tipo=%s", type(exc).__name__)

    logger.info(
        "rag trechos=%d busca_ms=%.0f explicacao=%s",
        len(trechos),
        busca_ms,
        "nula" if explicacao is None else (explicacao.bloqueio or "gerada"),
    )
    return ConsultaRagResponse(
        trechos=trechos,
        explicacao=explicacao.texto if explicacao else None,
        modelo_llm=explicacao.modelo if explicacao else None,
    )
