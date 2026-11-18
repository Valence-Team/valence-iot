"""Baixa os modelos que o serviço usa e confere a integridade do classificador.

Uso, a partir da raiz do repositório:

    python -m scripts.baixar_modelos [--versao modelos-v1] [--sem-hugging-face]

1. modelos/visao.json e modelos/visao.pt da release do GitHub; o sha256 do .pt
   precisa bater com o valor gravado no visao.json pelo notebook de treino.
2. CLIP do portão (PORTAO_MODELO) e modelo de embeddings (EMBEDDINGS_MODELO) do
   Hugging Face, para o serviço subir sem baixar nada na primeira requisição.
O índice das fichas (modelos/indice/) já vem no repositório.
"""

import argparse
import hashlib
import json
import sys
import urllib.request
from pathlib import Path

from app.config import Configuracao

REPOSITORIO = "Valence-Team/valence-iot"
VERSAO_PADRAO = "modelos-v1"
ARQUIVOS = ("visao.json", "visao.pt")


def url_release(versao: str, arquivo: str) -> str:
    return f"https://github.com/{REPOSITORIO}/releases/download/{versao}/{arquivo}"


def sha256(caminho: Path) -> str:
    resumo = hashlib.sha256()
    with caminho.open("rb") as arquivo:
        for bloco in iter(lambda: arquivo.read(2**20), b""):
            resumo.update(bloco)
    return resumo.hexdigest()


def baixar(url: str, destino: Path) -> None:
    temporario = destino.with_suffix(destino.suffix + ".parcial")
    with urllib.request.urlopen(url, timeout=60) as resposta, temporario.open("wb") as saida:
        while bloco := resposta.read(2**20):
            saida.write(bloco)
    temporario.replace(destino)


def baixar_classificador(versao: str, pasta: Path) -> None:
    pasta.mkdir(parents=True, exist_ok=True)
    for arquivo in ARQUIVOS:
        destino = pasta / arquivo
        if destino.exists():
            print(f"{destino} já existe", file=sys.stderr)
            continue
        print(f"Baixando {url_release(versao, arquivo)}", file=sys.stderr)
        baixar(url_release(versao, arquivo), destino)

    esperado = json.loads((pasta / "visao.json").read_text(encoding="utf-8")).get("sha256")
    obtido = sha256(pasta / "visao.pt")
    if esperado and obtido != esperado:
        (pasta / "visao.pt").unlink()
        raise SystemExit(f"sha256 de visao.pt não confere: {obtido} != {esperado}")
    print(f"visao.pt conferido (sha256 {obtido[:12]}...)", file=sys.stderr)


def baixar_hugging_face(config: Configuracao) -> None:
    from huggingface_hub import snapshot_download

    for modelo in (config.portao_modelo, config.embeddings_modelo):
        print(f"Baixando {modelo} do Hugging Face", file=sys.stderr)
        snapshot_download(modelo)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--versao", default=VERSAO_PADRAO, help="Tag da release do GitHub")
    parser.add_argument("--sem-hugging-face", action="store_true")
    args = parser.parse_args(argv)

    config = Configuracao()
    baixar_classificador(args.versao, config.modelo_visao_path.parent)
    if not args.sem_hugging_face:
        baixar_hugging_face(config)
    print("Modelos prontos.", file=sys.stderr)


if __name__ == "__main__":
    main()
