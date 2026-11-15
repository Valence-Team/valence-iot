"""Mede a latência de cada etapa do serviço com os componentes reais, em CPU.

Uso, a partir da raiz do repositório:

    python -m scripts.medir_latencia [--fotos PASTA] [--repeticoes 20] [--chamadas-llm 3]

Etapas: abertura da imagem, qualidade, portão, classificador (se modelos/visao.pt existir),
busca no índice e LLM. Grava avaliacao/latencia.json com mediana e p95 de cada etapa.
"""

import argparse
import json
import platform
import sys
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

import numpy as np
import torch

from app.config import Configuracao
from app.erros import ComponenteIndisponivel
from app.rag.carga import carregar_cliente_llm, carregar_indice
from app.rag.consulta import rotulos_com_bonus, texto_de_busca
from app.rag.indice import TOP_K
from app.rotulos import carregar_rotulos
from app.schemas import Cultura
from app.visao.carga import carregar_classificador, carregar_portao
from app.visao.qualidade import abrir_imagem, avaliar_qualidade

SINTOMAS = "mancha grande molhada e mofo branco embaixo da folha depois da neblina"


def resumo(tempos: list[float]) -> dict | None:
    if not tempos:
        return None
    return {
        "amostras": len(tempos),
        "medianaMs": round(float(np.median(tempos)), 1),
        "p95Ms": round(float(np.percentile(tempos, 95)), 1),
    }


def medir(funcao, repeticoes: int) -> list[float]:
    tempos = []
    for _ in range(repeticoes):
        inicio = perf_counter()
        funcao()
        tempos.append((perf_counter() - inicio) * 1000)
    return tempos


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--fotos", type=Path, default=Path("dados/exemplos"))
    parser.add_argument("--repeticoes", type=int, default=20)
    parser.add_argument("--chamadas-llm", type=int, default=3)
    parser.add_argument("--saida", type=Path, default=Path("avaliacao/latencia.json"))
    args = parser.parse_args(argv)

    config = Configuracao()
    fotos = sorted(p for p in args.fotos.glob("*.jpg"))
    dados = [p.read_bytes() for p in fotos]
    figuras = [abrir_imagem(d) for d in dados]
    etapas: dict[str, list[float]] = {
        k: [] for k in ("abertura", "qualidade", "portao", "classificador", "busca", "llm")
    }

    portao = carregar_portao(config)
    try:
        classificador = carregar_classificador(config)
    except ComponenteIndisponivel as exc:
        classificador = None
        print(f"classificador indisponível: {exc}", file=sys.stderr)

    for d, figura in zip(dados, figuras, strict=True):
        etapas["abertura"] += medir(lambda d=d: abrir_imagem(d), args.repeticoes)
        etapas["qualidade"] += medir(lambda f=figura: avaliar_qualidade(f), args.repeticoes)
        portao.verificar(figura, Cultura.TOMATE)
        etapas["portao"] += medir(
            lambda f=figura: portao.verificar(f, Cultura.TOMATE), args.repeticoes
        )
        if classificador is not None:
            classificador.classificar(figura, Cultura.TOMATE)
            etapas["classificador"] += medir(
                lambda f=figura: classificador.classificar(f, Cultura.TOMATE), args.repeticoes
            )

    rotulos = carregar_rotulos()
    classes = [rotulos["tomate_requeima"], rotulos["tomate_pinta_preta"]]
    indice = carregar_indice(config)
    busca = texto_de_busca(Cultura.TOMATE, classes, SINTOMAS)
    indice.buscar(busca, Cultura.TOMATE, TOP_K, rotulos_com_bonus(classes))
    etapas["busca"] = medir(
        lambda: indice.buscar(busca, Cultura.TOMATE, TOP_K, rotulos_com_bonus(classes)),
        args.repeticoes * 5,
    )
    trechos = indice.buscar(busca, Cultura.TOMATE, TOP_K, rotulos_com_bonus(classes))

    modelos_llm = []
    try:
        llm = carregar_cliente_llm(config)
        for _ in range(args.chamadas_llm):
            inicio = perf_counter()
            explicacao = llm.explicar(Cultura.TOMATE, SINTOMAS, classes, trechos)
            etapas["llm"].append((perf_counter() - inicio) * 1000)
            modelos_llm.append(explicacao.modelo if explicacao else None)
    except ComponenteIndisponivel as exc:
        print(f"LLM indisponível: {exc}", file=sys.stderr)

    resultado = {
        "geradoEm": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "ambiente": {
            "processador": platform.processor() or platform.machine(),
            "sistema": platform.platform(),
            "torchThreads": torch.get_num_threads(),
            "dispositivo": "cpu",
        },
        "fotos": [p.name for p in fotos],
        "modelosLlmQueResponderam": modelos_llm,
        "etapas": {nome: resumo(tempos) for nome, tempos in etapas.items()},
    }
    args.saida.parent.mkdir(parents=True, exist_ok=True)
    args.saida.write_text(
        json.dumps(resultado, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(resultado["etapas"], indent=2), file=sys.stderr)


if __name__ == "__main__":
    main()
