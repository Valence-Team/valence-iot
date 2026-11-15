from app.config import Configuracao
from app.erros import ComponenteIndisponivel
from app.rag import ClienteLlm, Indice
from app.rag.indice import ARQUIVO_TRECHOS, CodificadorSentenceTransformers, IndiceVetorial
from app.rag.llm import ClienteLlmComReserva


def carregar_indice(config: Configuracao) -> Indice:
    if not (config.indice_path / ARQUIVO_TRECHOS).exists():
        raise ComponenteIndisponivel(f"índice não encontrado em {config.indice_path}")
    codificador = CodificadorSentenceTransformers(config.embeddings_modelo)
    return IndiceVetorial.carregar(config.indice_path, codificador)


def carregar_cliente_llm(config: Configuracao) -> ClienteLlm:
    return ClienteLlmComReserva.de_config(config)
