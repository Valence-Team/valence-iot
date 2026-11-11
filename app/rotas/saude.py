from fastapi import APIRouter

from app.dependencias import ComponentesDep
from app.schemas import EstadoComponentes, SaudeResponse

router = APIRouter(tags=["Saúde"])


@router.get("/health", response_model=SaudeResponse, summary="Estado do serviço e dos componentes")
def saude(componentes: ComponentesDep) -> SaudeResponse:
    estados = componentes.estados()
    tudo_carregado = all(estado == "carregado" for estado in estados.values())
    return SaudeResponse(
        status="ok" if tudo_carregado else "degradado",
        modelo=estados["visao"],
        componentes=EstadoComponentes(**estados),
    )
