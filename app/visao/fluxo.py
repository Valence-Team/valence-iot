import logging
from time import perf_counter

from PIL.Image import Image

from app.schemas import Cultura
from app.visao import Classificador, Portao, ResultadoClassificacao
from app.visao.qualidade import avaliar_qualidade

logger = logging.getLogger("valence_ia.visao")


def _ms(inicio: float) -> str:
    return f"{(perf_counter() - inicio) * 1000:.1f}"


# Qualidade, portão e classificador, nesta ordem
def executar_camadas(
    imagem: Image,
    cultura: Cultura,
    portao: Portao,
    classificador: Classificador,
) -> ResultadoClassificacao:
    tempos = {"qualidade": "-", "portao": "-", "classificador": "-"}
    resultado = ResultadoClassificacao(None, None, [])
    try:
        inicio = perf_counter()
        motivo = avaliar_qualidade(imagem)
        tempos["qualidade"] = _ms(inicio)
        if motivo is not None:
            resultado = ResultadoClassificacao(motivo, None, [])
            return resultado

        inicio = perf_counter()
        veredito = portao.verificar(imagem, cultura)
        tempos["portao"] = _ms(inicio)
        if veredito.motivo is not None:
            resultado = ResultadoClassificacao(veredito.motivo, veredito.cultura_detectada, [])
            return resultado

        inicio = perf_counter()
        resultado = classificador.classificar(imagem, cultura)
        tempos["classificador"] = _ms(inicio)
        return resultado
    finally:
        logger.info(
            "classificacao qualidade_ms=%s portao_ms=%s classificador_ms=%s motivo=%s",
            tempos["qualidade"],
            tempos["portao"],
            tempos["classificador"],
            resultado.motivo or "-",
        )
