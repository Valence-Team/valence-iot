from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Configuracao(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Visão computacional
    modelo_visao_path: Path = Path("modelos/visao.pt")
    confianca_minima: float = Field(default=0.6, ge=0.0, le=1.0)
    portao_modelo: str = "openai/clip-vit-base-patch32"

    # RAG
    embeddings_modelo: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    indice_path: Path = Path("modelos/indice")

    # LLM principal e reserva
    llm_base_url: str = "https://api.groq.com/openai/v1"
    llm_api_key: SecretStr = SecretStr("")
    llm_model: str = "openai/gpt-oss-20b"
    llm_fallback_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai/"
    llm_fallback_api_key: SecretStr = SecretStr("")
    llm_fallback_model: str = "gemini-3.5-flash-lite"
    llm_timeout_seconds: float = Field(default=4.0, gt=0)

    # Segurança e limites
    ia_api_key: SecretStr = SecretStr("")
    tamanho_maximo_mb: int = Field(default=8, gt=0)
    demo_habilitada: bool = True

    @property
    def tamanho_maximo_bytes(self) -> int:
        return self.tamanho_maximo_mb * 1024 * 1024


@lru_cache
def obter_configuracao() -> Configuracao:
    return Configuracao()
