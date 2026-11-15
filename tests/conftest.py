import io
from collections.abc import Callable, Iterator, Sequence

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.config import Configuracao
from app.erros import ComponenteIndisponivel
from app.main import criar_app
from app.rag import Explicacao
from app.rotulos import Rotulo, carregar_rotulos
from app.schemas import ClassePrevista, Cultura, MotivoRecusa, Trecho
from app.visao import VereditoPortao

CHAVE_TESTE = "chave-de-teste-123"


# Implementações falsas das interfaces
class PortaoFalso:
    def __init__(self, motivo: MotivoRecusa | None = None) -> None:
        self.motivo = motivo

    def verificar(self, imagem: Image.Image, cultura: Cultura) -> VereditoPortao:
        if self.motivo is not None:
            return VereditoPortao(motivo=self.motivo, cultura_detectada=None)
        return VereditoPortao(motivo=None, cultura_detectada=cultura)


class ClassificadorFalso:
    def __init__(self) -> None:
        self.rotulos = carregar_rotulos()

    def classificar(self, imagem: Image.Image, cultura: Cultura) -> list[ClassePrevista]:
        da_cultura = [r for r in self.rotulos.values() if r.cultura == cultura]
        confiancas = [0.8, 0.15, 0.05, 0.0]
        return [
            ClassePrevista(rotulo=r.rotulo, nome=r.nome, confianca=c)
            for r, c in zip(da_cultura, confiancas, strict=False)
        ]


class IndiceFalso:
    def __init__(self) -> None:
        self.consultas: list[str] = []

    def buscar(
        self, consulta: str, cultura: Cultura, k: int, rotulos: Sequence[str] = ()
    ) -> list[Trecho]:
        self.consultas.append(consulta)
        return [
            Trecho(
                titulo="Doenças foliares",
                texto="Trecho de ficha técnica.",
                fonte="Embrapa",
                url="https://www.embrapa.br/",
                score=0.91,
            )
        ][:k]


class LlmFalso:
    def __init__(self, falhar: bool = False) -> None:
        self.falhar = falhar
        self.sintomas_recebidos: list[str] = []

    def explicar(
        self,
        cultura: Cultura,
        sintomas: str,
        classes: list[Rotulo],
        trechos: list[Trecho],
    ) -> Explicacao | None:
        self.sintomas_recebidos.append(sintomas)
        if self.falhar:
            raise TimeoutError("tempo esgotado")
        return Explicacao(texto="Explicação de teste.", modelo="modelo-falso")


def indisponivel(config: Configuracao) -> None:
    raise ComponenteIndisponivel("indisponível no teste")


# Fixtures
AJUSTES_PADRAO = {"ia_api_key": "", "llm_api_key": "", "tamanho_maximo_mb": 1}


def montar_config(**ajustes: object) -> Configuracao:
    return Configuracao(_env_file=None, **{**AJUSTES_PADRAO, **ajustes})


@pytest.fixture
def componentes_falsos() -> dict[str, object]:
    return {
        "visao": ClassificadorFalso(),
        "portao": PortaoFalso(),
        "indice": IndiceFalso(),
        "llm": LlmFalso(),
    }


@pytest.fixture
def criar_cliente() -> Iterator[Callable[..., TestClient]]:
    clientes: list[TestClient] = []

    def _criar(
        componentes: dict[str, object] | None = None,
        **ajustes: object,
    ) -> TestClient:
        componentes = componentes or {}
        carregadores = {
            nome: (lambda _c, obj=componentes[nome]: obj) if nome in componentes else indisponivel
            for nome in ("visao", "portao", "indice", "llm")
        }
        app = criar_app(montar_config(**ajustes), carregadores)
        cliente = TestClient(app, raise_server_exceptions=False)
        cliente.__enter__()
        clientes.append(cliente)
        return cliente

    yield _criar
    for cliente in clientes:
        cliente.__exit__(None, None, None)


@pytest.fixture
def cliente(criar_cliente, componentes_falsos) -> TestClient:
    return criar_cliente(componentes_falsos)


@pytest.fixture
def cliente_sem_modelo(criar_cliente) -> TestClient:
    return criar_cliente()


def gerar_imagem(formato: str = "PNG", tamanho: tuple[int, int] = (64, 64)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", tamanho, (40, 140, 60)).save(buffer, format=formato)
    return buffer.getvalue()
