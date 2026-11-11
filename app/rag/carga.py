from app.config import Configuracao
from app.erros import ComponenteIndisponivel
from app.rag import ClienteLlm, Indice


def carregar_indice(config: Configuracao) -> Indice:
    if not config.indice_path.exists():
        raise ComponenteIndisponivel(f"índice não encontrado em {config.indice_path}")
    raise ComponenteIndisponivel("índice sem implementação nesta versão")


def carregar_cliente_llm(config: Configuracao) -> ClienteLlm:
    if not config.llm_api_key.get_secret_value():
        raise ComponenteIndisponivel("LLM_API_KEY não definida")
    raise ComponenteIndisponivel("cliente do LLM sem implementação nesta versão")
