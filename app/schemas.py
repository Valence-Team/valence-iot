from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import AfterValidator, BaseModel, BeforeValidator, ConfigDict, Field
from pydantic.alias_generators import to_camel

from app.seguranca import mascarar_dados_pessoais


# Enumerações
class Cultura(StrEnum):
    MILHO = "MILHO"
    TOMATE = "TOMATE"
    BATATA = "BATATA"


class MotivoRecusa(StrEnum):
    RESOLUCAO_BAIXA = "RESOLUCAO_BAIXA"
    IMAGEM_ESCURA = "IMAGEM_ESCURA"
    IMAGEM_CLARA = "IMAGEM_CLARA"
    IMAGEM_BORRADA = "IMAGEM_BORRADA"
    NAO_E_PLANTA = "NAO_E_PLANTA"
    CULTURA_FORA_DO_ESCOPO = "CULTURA_FORA_DO_ESCOPO"
    CULTURA_DIVERGENTE = "CULTURA_DIVERGENTE"


def normalizar_cultura(valor: Any) -> Any:
    if isinstance(valor, str):
        return valor.strip().upper()
    return valor


CulturaEntrada = Annotated[Cultura, BeforeValidator(normalizar_cultura)]


class Contrato(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        validate_by_name=True,
        validate_by_alias=True,
        serialize_by_alias=True,
    )


# Visão computacional
class ClassePrevista(Contrato):
    rotulo: str
    nome: str
    confianca: float = Field(ge=0.0, le=1.0)


class ClassificacaoResponse(Contrato):
    imagem_valida: bool
    motivo: MotivoRecusa | None = None
    cultura_detectada: Cultura | None = None
    classes: list[ClassePrevista] = Field(default_factory=list, max_length=3)


# RAG e explicação
class ConsultaRagRequest(Contrato):
    cultura: CulturaEntrada
    sintomas: Annotated[
        str,
        Field(min_length=1, max_length=1000),
        AfterValidator(mascarar_dados_pessoais),
    ]
    classes: list[Annotated[str, Field(max_length=64)]] = Field(default_factory=list, max_length=3)


class Trecho(Contrato):
    titulo: str
    texto: str
    fonte: str
    url: str
    score: float


class ConsultaRagResponse(Contrato):
    trechos: list[Trecho]
    explicacao: str | None = None
    modelo_llm: str | None = None


# Saúde
EstadoComponente = Literal["carregado", "indisponivel"]


class EstadoComponentes(Contrato):
    visao: EstadoComponente
    portao: EstadoComponente
    indice: EstadoComponente
    llm: EstadoComponente


class SaudeResponse(Contrato):
    status: Literal["ok", "degradado"]
    modelo: EstadoComponente
    componentes: EstadoComponentes


# Erros
class CampoErro(BaseModel):
    campo: str
    mensagem: str


class ErroResponse(BaseModel):
    timestamp: str
    status: int
    erro: str
    mensagem: str
    caminho: str
    campos: list[CampoErro] = Field(default_factory=list)
