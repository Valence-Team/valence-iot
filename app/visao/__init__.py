from dataclasses import dataclass, field
from typing import Protocol

from PIL.Image import Image

from app.schemas import ClassePrevista, Cultura, MotivoRecusa


@dataclass(frozen=True)
class VereditoPortao:
    motivo: MotivoRecusa | None
    cultura_detectada: Cultura | None


@dataclass(frozen=True)
class ResultadoClassificacao:
    motivo: MotivoRecusa | None
    cultura_detectada: Cultura | None
    classes: list[ClassePrevista] = field(default_factory=list)


class Portao(Protocol):
    def verificar(self, imagem: Image, cultura: Cultura) -> VereditoPortao: ...


class Classificador(Protocol):
    def classificar(self, imagem: Image, cultura: Cultura) -> ResultadoClassificacao: ...
