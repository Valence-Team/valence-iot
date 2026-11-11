from dataclasses import dataclass
from typing import Protocol

from PIL.Image import Image

from app.schemas import ClassePrevista, Cultura, MotivoRecusa


@dataclass(frozen=True)
class VereditoPortao:
    motivo: MotivoRecusa | None
    cultura_detectada: Cultura | None


class Portao(Protocol):
    def verificar(self, imagem: Image, cultura: Cultura) -> VereditoPortao: ...


class Classificador(Protocol):
    def classificar(self, imagem: Image, cultura: Cultura) -> list[ClassePrevista]: ...
