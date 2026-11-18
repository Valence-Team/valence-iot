import logging
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, Request

logger = logging.getLogger("valence_ia.requisicoes")


def configurar_logs(nivel: int = logging.INFO) -> None:
    raiz = logging.getLogger("valence_ia")
    raiz.setLevel(nivel)
    if not raiz.handlers:
        saida = logging.StreamHandler()
        saida.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
        raiz.addHandler(saida)


# Log de requisições sem corpo, imagem nem cabeçalhos
def registrar_log_requisicoes(app: FastAPI) -> None:
    @app.middleware("http")
    async def registrar(request: Request, call_next):
        id_requisicao = uuid4().hex
        inicio = perf_counter()
        status = 500
        try:
            resposta = await call_next(request)
            status = resposta.status_code
            resposta.headers["X-Request-ID"] = id_requisicao
            return resposta
        finally:
            rota = getattr(request.scope.get("route"), "path", request.url.path)
            logger.info(
                "requisicao id=%s metodo=%s rota=%s status=%d duracao_ms=%.1f",
                id_requisicao,
                request.method,
                rota,
                status,
                (perf_counter() - inicio) * 1000,
            )
