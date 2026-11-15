"""Avalia a recuperação de trechos das fichas técnicas.

Uso, a partir da raiz do repositório:

    python -m scripts.avaliar_rag [--modelos NOME ...]

Para cada modelo de embeddings, com e sem o bônus de classe, calcula hit@1, hit@3 e MRR
por ficha nas consultas de dados/avaliacao/consultas_rag.json. Também mede o corte por
score mínimo com consultas sem relação com as fichas. Grava avaliacao/rag/metricas.json
e avaliacao/rag/metricas.md.
"""

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from app.rag.consulta import rotulos_com_bonus, texto_de_busca
from app.rag.fichas import ler_fichas, quebrar_em_trechos
from app.rag.indice import BONUS_CLASSE, CodificadorSentenceTransformers, IndiceVetorial
from app.rotulos import carregar_rotulos
from app.schemas import Cultura

MODELOS = (
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
    "intfloat/multilingual-e5-small",
)
CONSULTAS_PATH = Path("dados/avaliacao/consultas_rag.json")
SAIDA_PATH = Path("avaliacao/rag")

# Consultas sem resposta nas fichas, para medir o corte por score mínimo
SEM_RESPOSTA = (
    ("MILHO", "qual o preço da saca de milho hoje na cooperativa"),
    ("TOMATE", "como faço pra pedir financiamento do pronaf pra estufa"),
    ("BATATA", "quero receita de nhoque de batata"),
    ("MILHO", "meu trator ta fazendo barulho no motor"),
    ("TOMATE", "qual a melhor época pra vender tomate na ceasa"),
)


def ranking_de_fichas(pares) -> list[str]:
    vistas: list[str] = []
    for trecho, _score in pares:
        if trecho.ficha not in vistas:
            vistas.append(trecho.ficha)
    return vistas


VARIANTES = {
    "semBonus": "não",
    "bonusTodasAsClasses": "sim, todas as classes",
    "bonusSemSaudavel": "sim, exceto saudável (usado no serviço)",
}


def rotulos_da_variante(classes, variante: str) -> list[str]:
    if variante == "bonusTodasAsClasses":
        return [c.rotulo for c in classes]
    return rotulos_com_bonus(classes)


def busca_de_producao(indice: IndiceVetorial, consulta: dict, rotulos, variante: str):
    cultura = Cultura(consulta["cultura"])
    classes = [rotulos[r] for r in consulta["classes"]]
    return indice.pontuar(
        texto_de_busca(cultura, classes, consulta["sintomas"]),
        cultura,
        rotulos_da_variante(classes, variante),
    )


def avaliar(indice: IndiceVetorial, consultas: list[dict], rotulos, variante: str) -> dict:
    indice.bonus = 0.0 if variante == "semBonus" else BONUS_CLASSE
    linhas = []
    for consulta in consultas:
        pares = busca_de_producao(indice, consulta, rotulos, variante)
        ranking = ranking_de_fichas(pares)
        posicao = ranking.index(consulta["fichaEsperada"]) + 1
        linhas.append(
            {
                "id": consulta["id"],
                "esperada": consulta["fichaEsperada"],
                "primeira": ranking[0],
                "posicao": posicao,
                "scoreTopo": round(pares[0][1], 4),
                "foraDoModelo": consulta["foraDoModelo"],
                "comClasses": bool(consulta["classes"]),
            }
        )
    return {"resumo": resumo(linhas), "porConsulta": linhas}


def resumo(linhas: list[dict]) -> dict:
    def metricas(grupo: list[dict]) -> dict:
        if not grupo:
            return {}
        posicoes = np.array([linha["posicao"] for linha in grupo])
        return {
            "consultas": len(grupo),
            "hit@1": round(float(np.mean(posicoes <= 1)), 4),
            "hit@3": round(float(np.mean(posicoes <= 3)), 4),
            "mrr": round(float(np.mean(1.0 / posicoes)), 4),
        }

    return {
        "geral": metricas(linhas),
        "pragasForaDoModelo": metricas([x for x in linhas if x["foraDoModelo"]]),
        "comClasses": metricas([x for x in linhas if x["comClasses"]]),
        "semClasses": metricas([x for x in linhas if not x["comClasses"]]),
    }


def avaliar_corte(indice: IndiceVetorial, consultas: list[dict], rotulos) -> dict:
    indice.bonus = BONUS_CLASSE
    variante = "bonusSemSaudavel"
    relevantes = [busca_de_producao(indice, c, rotulos, variante)[0][1] for c in consultas]
    sem_resposta = [
        busca_de_producao(
            indice, {"cultura": cultura, "classes": [], "sintomas": texto}, rotulos, variante
        )[0][1]
        for cultura, texto in SEM_RESPOSTA
    ]
    candidatos = sorted({round(x, 2) for x in np.arange(0.30, 0.96, 0.01)})
    varredura = [
        {
            "limiar": limiar,
            "relevantesAcima": round(float(np.mean(np.array(relevantes) >= limiar)), 4),
            "semRespostaCortadas": round(float(np.mean(np.array(sem_resposta) < limiar)), 4),
        }
        for limiar in candidatos
    ]
    return {
        "varredura": varredura,
        "scoreMinimo": indice.minimo,
        "consultasRelevantesAcimaDoMinimo": round(
            float(np.mean(np.array(relevantes) >= indice.minimo)), 4
        ),
        "consultasSemRespostaCortadas": round(
            float(np.mean(np.array(sem_resposta) < indice.minimo)), 4
        ),
        "scoreTopoRelevantes": {
            "min": round(min(relevantes), 4),
            "p10": round(float(np.percentile(relevantes, 10)), 4),
            "mediana": round(float(np.median(relevantes)), 4),
        },
        "scoreTopoSemResposta": {
            "max": round(max(sem_resposta), 4),
            "mediana": round(float(np.median(sem_resposta)), 4),
        },
    }


def tabela_md(resultados: dict) -> str:
    linhas = [
        "# Avaliação da recuperação (RAG)",
        "",
        f"Gerado em {resultados['geradoEm']} com {resultados['consultas']} consultas "
        f"({resultados['foraDoModelo']} sobre pragas fora do modelo de visão).",
        "",
        "| Modelo | Bônus de classe | hit@1 | hit@3 | MRR | hit@1 fora do modelo |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for modelo, por_bonus in resultados["modelos"].items():
        for chave, rotulo in VARIANTES.items():
            geral = por_bonus[chave]["resumo"]["geral"]
            fora = por_bonus[chave]["resumo"]["pragasForaDoModelo"]
            linhas.append(
                f"| `{modelo}` | {rotulo} | {geral['hit@1']:.3f} | {geral['hit@3']:.3f} | "
                f"{geral['mrr']:.3f} | {fora['hit@1']:.3f} |"
            )
    linhas += ["", "## Corte por score mínimo", ""]
    linhas += [
        "| Modelo | Score mínimo | Relevantes acima | Sem resposta cortadas |",
        "| --- | --- | --- | --- |",
    ]
    for modelo, por_bonus in resultados["modelos"].items():
        corte = por_bonus["corte"]
        linhas.append(
            f"| `{modelo}` | {corte['scoreMinimo']} | "
            f"{corte['consultasRelevantesAcimaDoMinimo']:.2f} | "
            f"{corte['consultasSemRespostaCortadas']:.2f} |"
        )
    linhas += [
        "",
        "Varredura do limiar na busca do serviço (cultura, nomes das classes, sintomas e bônus):",
        "",
        "| Modelo | Limiar | Relevantes acima | Sem resposta cortadas |",
        "| --- | --- | --- | --- |",
    ]
    for modelo, por_bonus in resultados["modelos"].items():
        anterior = None
        for ponto in por_bonus["corte"]["varredura"]:
            atual = (ponto["relevantesAcima"], ponto["semRespostaCortadas"])
            mudou, anterior = atual != anterior, atual
            if mudou and ponto["semRespostaCortadas"] > 0 and ponto["relevantesAcima"] >= 0.9:
                linhas.append(
                    f"| `{modelo}` | {ponto['limiar']:.2f} | {ponto['relevantesAcima']:.3f} | "
                    f"{ponto['semRespostaCortadas']:.2f} |"
                )
    linhas += ["", "## Erros de topo (bônus exceto saudável)", ""]
    for modelo, por_bonus in resultados["modelos"].items():
        erros = [x for x in por_bonus["bonusSemSaudavel"]["porConsulta"] if x["posicao"] > 1]
        linhas.append(
            f"- `{modelo}`: "
            + (
                ", ".join(
                    f"{x['id']} esperava {x['esperada']}, veio {x['primeira']}" for x in erros
                )
                or "nenhum"
            )
        )
    return "\n".join(linhas) + "\n"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--modelos", nargs="+", default=list(MODELOS))
    parser.add_argument("--consultas", type=Path, default=CONSULTAS_PATH)
    parser.add_argument("--saida", type=Path, default=SAIDA_PATH)
    args = parser.parse_args(argv)

    consultas = json.loads(args.consultas.read_text(encoding="utf-8"))
    rotulos = carregar_rotulos()
    trechos = [t for ficha in ler_fichas() for t in quebrar_em_trechos(ficha)]

    resultados = {
        "geradoEm": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "consultas": len(consultas),
        "foraDoModelo": sum(c["foraDoModelo"] for c in consultas),
        "trechos": len(trechos),
        "bonusClasse": BONUS_CLASSE,
        "modelos": {},
    }
    for modelo in args.modelos:
        indice = IndiceVetorial.construir(trechos, CodificadorSentenceTransformers(modelo))
        por_modelo = {v: avaliar(indice, consultas, rotulos, v) for v in VARIANTES}
        por_modelo["corte"] = avaliar_corte(indice, consultas, rotulos)
        resultados["modelos"][modelo] = por_modelo
        geral = por_modelo["bonusSemSaudavel"]["resumo"]["geral"]
        print(f"{modelo}: {geral}", file=sys.stderr)

    args.saida.mkdir(parents=True, exist_ok=True)
    (args.saida / "metricas.json").write_text(
        json.dumps(resultados, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (args.saida / "metricas.md").write_text(tabela_md(resultados), encoding="utf-8")
    print(f"Métricas gravadas em {args.saida}", file=sys.stderr)


if __name__ == "__main__":
    main()
