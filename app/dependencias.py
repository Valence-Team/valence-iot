from typing import Annotated

from fastapi import Depends, Request

from app.componentes import Componentes
from app.config import Configuracao
from app.rotulos import Rotulo
from app.schemas import ErroResponse


def obter_config(request: Request) -> Configuracao:
    return request.app.state.config


def obter_componentes(request: Request) -> Componentes:
    return request.app.state.componentes


def obter_rotulos(request: Request) -> dict[str, Rotulo]:
    return request.app.state.rotulos


ConfigDep = Annotated[Configuracao, Depends(obter_config)]
ComponentesDep = Annotated[Componentes, Depends(obter_componentes)]
RotulosDep = Annotated[dict[str, Rotulo], Depends(obter_rotulos)]


def respostas_erro(*codigos: int) -> dict[int | str, dict]:
    return {codigo: {"model": ErroResponse} for codigo in codigos}
