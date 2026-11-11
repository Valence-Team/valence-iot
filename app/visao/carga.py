from app.config import Configuracao
from app.erros import ComponenteIndisponivel
from app.visao import Classificador, Portao


def carregar_classificador(config: Configuracao) -> Classificador:
    if not config.modelo_visao_path.exists():
        raise ComponenteIndisponivel(f"modelo não encontrado em {config.modelo_visao_path}")
    raise ComponenteIndisponivel("classificador sem implementação nesta versão")


def carregar_portao(config: Configuracao) -> Portao:
    raise ComponenteIndisponivel("portão sem implementação nesta versão")
