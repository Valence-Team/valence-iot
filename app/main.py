import asyncio
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.componentes import CARREGADORES_PADRAO, Carregador, Componentes, carregar_componentes
from app.config import Configuracao, obter_configuracao
from app.erros import registrar_handlers
from app.logs import configurar_logs, registrar_log_requisicoes
from app.rotas import rag, saude, visao
from app.rotulos import carregar_rotulos

DESCRICAO = (
    "Serviço de IA do Valence: classifica doenças em fotos de folhas de milho, tomate e batata, "
    "busca trechos de fichas técnicas e gera uma explicação com IA generativa."
)


def criar_app(
    config: Configuracao | None = None,
    carregadores: Mapping[str, Carregador] | None = None,
) -> FastAPI:
    configurar_logs()
    config = config or obter_configuracao()
    carregadores = CARREGADORES_PADRAO if carregadores is None else carregadores

    # Carga dos componentes
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.componentes = await asyncio.to_thread(carregar_componentes, config, carregadores)
        yield
        app.state.componentes = Componentes()

    app = FastAPI(title="Valence IA", version="0.1.0", description=DESCRICAO, lifespan=lifespan)
    app.state.config = config
    app.state.rotulos = carregar_rotulos()
    app.state.componentes = Componentes()

    registrar_handlers(app)
    registrar_log_requisicoes(app)

    app.include_router(saude.router)
    app.include_router(visao.router)
    app.include_router(rag.router)

    # Demo Gradio em /demo
    if config.demo_habilitada:
        from app.demo import montar_demo

        app = montar_demo(app)
    return app


app = criar_app()
