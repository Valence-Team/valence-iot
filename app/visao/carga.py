import logging

import torch
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.config import Configuracao
from app.rotulos import carregar_rotulos
from app.visao import Classificador, Portao
from app.visao.classificador import ClassificadorTorch
from app.visao.portao import PortaoClip

logger = logging.getLogger("valence_ia.visao")


class ConfiguracaoTorch(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    visao_threads: int = Field(default=0, ge=0)


def configurar_threads() -> None:
    threads = ConfiguracaoTorch().visao_threads
    if threads > 0 and torch.get_num_threads() != threads:
        torch.set_num_threads(threads)
    logger.info("torch threads=%d", torch.get_num_threads())


def carregar_classificador(config: Configuracao) -> Classificador:
    configurar_threads()
    return ClassificadorTorch.carregar(config.modelo_visao_path, carregar_rotulos())


def carregar_portao(config: Configuracao) -> Portao:
    configurar_threads()
    return PortaoClip.carregar(config.portao_modelo)
