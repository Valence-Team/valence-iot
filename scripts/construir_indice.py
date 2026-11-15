"""Constrói o índice de busca a partir das fichas técnicas.

Uso, a partir da raiz do repositório:

    python -m scripts.construir_indice [--modelo NOME] [--saida modelos/indice]

Sem --modelo, usa EMBEDDINGS_MODELO da configuração. O serviço só carrega o índice
se o modelo gravado em trechos.json for o mesmo de EMBEDDINGS_MODELO.
"""

import argparse
import sys
from collections import Counter
from pathlib import Path

from app.config import Configuracao
from app.rag.fichas import FICHAS_PATH, ler_fichas, quebrar_em_trechos
from app.rag.indice import CodificadorSentenceTransformers, IndiceVetorial
from app.rotulos import carregar_rotulos


def validar_rotulos(fichas) -> None:
    conhecidos = carregar_rotulos()
    cobertos = Counter()
    for ficha in fichas:
        for rotulo in ficha.rotulos:
            if rotulo not in conhecidos:
                raise SystemExit(f"{ficha.id}: rótulo desconhecido {rotulo}")
            if conhecidos[rotulo].cultura not in ficha.culturas:
                raise SystemExit(f"{ficha.id}: rótulo {rotulo} de outra cultura")
            cobertos[rotulo] += 1
    faltando = sorted(set(conhecidos) - set(cobertos))
    if faltando:
        raise SystemExit(f"Rótulos sem ficha: {', '.join(faltando)}")


def ler_argumentos(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--modelo", help="Modelo de embeddings (padrão: EMBEDDINGS_MODELO)")
    parser.add_argument("--fichas", type=Path, default=FICHAS_PATH)
    parser.add_argument("--saida", type=Path, help="Pasta do índice (padrão: INDICE_PATH)")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = ler_argumentos(argv)
    config = Configuracao()
    modelo = args.modelo or config.embeddings_modelo
    saida = args.saida or config.indice_path

    fichas = ler_fichas(args.fichas)
    validar_rotulos(fichas)
    trechos = [trecho for ficha in fichas for trecho in quebrar_em_trechos(ficha)]
    tamanhos = [len(t.texto.split()) for t in trechos]

    indice = IndiceVetorial.construir(trechos, CodificadorSentenceTransformers(modelo))
    indice.salvar(saida)
    print(
        f"{len(fichas)} fichas, {len(trechos)} trechos ({min(tamanhos)} a {max(tamanhos)} "
        f"palavras), modelo {modelo}, gravado em {saida}",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
