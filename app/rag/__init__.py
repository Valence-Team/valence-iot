from dataclasses import dataclass
from typing import Protocol

from app.rotulos import Rotulo
from app.schemas import Cultura, Trecho


@dataclass(frozen=True)
class Explicacao:
    texto: str
    modelo: str


class Indice(Protocol):
    def buscar(self, consulta: str, cultura: Cultura, k: int) -> list[Trecho]: ...


class ClienteLlm(Protocol):
    def explicar(
        self,
        cultura: Cultura,
        sintomas: str,
        classes: list[Rotulo],
        trechos: list[Trecho],
    ) -> Explicacao | None: ...
