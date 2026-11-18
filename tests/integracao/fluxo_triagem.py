"""Fluxo de triagem de ponta a ponta, do jeito que a API Java chama o serviço de IA.

Uso, a partir da raiz do repositório, com os modelos em modelos/ e as chaves no .env:

    python -m tests.integracao.fluxo_triagem [--foto ARQUIVO] [--cultura TOMATE]
                                             [--sintomas TEXTO] [--sem-llm]

1. POST /api/v1/visao/classificar (multipart: imagem, cultura) com X-API-Key.
2. Se a foto for válida, as classes vão para POST /api/v1/rag/consultar; se for recusada,
   a consulta segue só com o relato, como a API Java faz.
3. Imprime cada requisição e o JSON de resposta sem nenhuma transformação.
Com --sem-llm o cliente do LLM não é carregado, simulando Groq e Gemini fora do ar.
"""

import argparse
import json
import sys
from pathlib import Path

from fastapi.testclient import TestClient

from app.componentes import CARREGADORES_PADRAO
from app.config import Configuracao
from app.erros import ComponenteIndisponivel
from app.main import criar_app

ROTA_VISAO = "/api/v1/visao/classificar"
ROTA_RAG = "/api/v1/rag/consultar"
FOTO_PADRAO = Path("dados/exemplos/milho_ferrugem_comum.jpg")
CULTURA_PADRAO = "MILHO"
SINTOMAS_PADRAO = "Pó cor de ferrugem nas duas faces da folha, que suja o dedo."
TIPOS = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}


def _llm_desligado(config: Configuracao):
    raise ComponenteIndisponivel("LLM desligado para o teste")


def criar_cliente(sem_llm: bool = False, config: Configuracao | None = None) -> TestClient:
    config = config or Configuracao()
    carregadores = dict(CARREGADORES_PADRAO)
    if sem_llm:
        carregadores["llm"] = _llm_desligado
    config = config.model_copy(update={"demo_habilitada": False})
    return TestClient(criar_app(config, carregadores), raise_server_exceptions=False)


def cabecalhos(config: Configuracao) -> dict[str, str]:
    chave = config.ia_api_key.get_secret_value()
    return {"X-API-Key": chave} if chave else {}


def executar_fluxo(cliente: TestClient, foto: Path, cultura: str, sintomas: str) -> dict[str, dict]:
    config = cliente.app.state.config
    with foto.open("rb") as arquivo:
        visao = cliente.post(
            ROTA_VISAO,
            files={"imagem": (foto.name, arquivo, TIPOS.get(foto.suffix.lower(), "image/jpeg"))},
            data={"cultura": cultura},
            headers=cabecalhos(config),
        )
    corpo_visao = visao.json()
    classes = []
    if visao.status_code == 200 and corpo_visao["imagemValida"]:
        classes = [c["rotulo"] for c in corpo_visao["classes"]]
    pedido_rag = {"cultura": cultura, "sintomas": sintomas, "classes": classes}
    rag = cliente.post(ROTA_RAG, json=pedido_rag, headers=cabecalhos(config))
    return {
        "visao": {
            "requisicao": {
                "metodo": "POST",
                "rota": ROTA_VISAO,
                "multipart": {"imagem": foto.name, "cultura": cultura},
            },
            "status": visao.status_code,
            "resposta": corpo_visao,
        },
        "rag": {
            "requisicao": {"metodo": "POST", "rota": ROTA_RAG, "json": pedido_rag},
            "status": rag.status_code,
            "resposta": rag.json(),
        },
        "saude": cliente.get("/health").json(),
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--foto", type=Path, default=FOTO_PADRAO)
    parser.add_argument("--cultura", default=CULTURA_PADRAO)
    parser.add_argument("--sintomas", default=SINTOMAS_PADRAO)
    parser.add_argument("--sem-llm", action="store_true")
    args = parser.parse_args(argv)

    with criar_cliente(args.sem_llm) as cliente:
        fluxo = executar_fluxo(cliente, args.foto, args.cultura, args.sintomas)
    json.dump(fluxo, sys.stdout, ensure_ascii=False, indent=2)
    print()


if __name__ == "__main__":
    main()
