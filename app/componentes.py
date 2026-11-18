import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass, fields
from time import perf_counter
from typing import Any

from app.config import Configuracao
from app.rag import ClienteLlm, Indice
from app.rag.carga import carregar_cliente_llm, carregar_indice
from app.visao import Classificador, Portao
from app.visao.carga import carregar_classificador, carregar_portao

logger = logging.getLogger("valence_ia.componentes")

Carregador = Callable[[Configuracao], Any]


@dataclass
class Componentes:
    visao: Classificador | None = None
    portao: Portao | None = None
    indice: Indice | None = None
    llm: ClienteLlm | None = None

    def estados(self) -> dict[str, str]:
        return {
            campo.name: "carregado" if getattr(self, campo.name) is not None else "indisponivel"
            for campo in fields(self)
        }


CARREGADORES_PADRAO: dict[str, Carregador] = {
    "visao": carregar_classificador,
    "portao": carregar_portao,
    "indice": carregar_indice,
    "llm": carregar_cliente_llm,
}


def carregar_componentes(
    config: Configuracao,
    carregadores: Mapping[str, Carregador] = CARREGADORES_PADRAO,
) -> Componentes:
    componentes = Componentes()
    for nome, carregar in carregadores.items():
        inicio = perf_counter()
        try:
            setattr(componentes, nome, carregar(config))
        except Exception as exc:
            logger.warning(
                "componente=%s estado=indisponivel motivo=%s: %s",
                nome,
                type(exc).__name__,
                exc,
            )
            continue
        duracao = (perf_counter() - inicio) * 1000
        logger.info("componente=%s estado=carregado duracao_ms=%.0f", nome, duracao)
    return componentes
