"""Escolhe os limites de brilho, nitidez e do portão a partir das medidas da calibração.

Uso, a partir da raiz do repositório, depois de rodar avaliar_portao.py com --medidas
nos conjuntos de datasets/portao/calibracao:

    python -m scripts.calibrar_portao --medidas avaliacao/portao/medidas_calibracao.jsonl

Simula o fluxo do serviço (resolução, brilho, nitidez e portão, nesta ordem) para cada
combinação de limites e escolhe a de maior J = média da rejeição correta por motivo
menos a falsa rejeição (laboratório e campo com o mesmo peso). Primeiro a qualidade,
depois o portão com a qualidade já escolhida. Grava avaliacao/portao/calibracao.json
e calibracao.md.
"""

import argparse
import json
import sys
from dataclasses import asdict, dataclass, replace
from itertools import product
from pathlib import Path

import numpy as np

from app.visao import portao as modulo_portao
from app.visao import qualidade

ACEITA = "ACEITA"
MOTIVOS_QUALIDADE = ("RESOLUCAO_BAIXA", "IMAGEM_ESCURA", "IMAGEM_CLARA", "IMAGEM_BORRADA")
MOTIVOS_PORTAO = ("CULTURA_FORA_DO_ESCOPO", "NAO_E_PLANTA")
FALSA_REJEICAO_MAXIMA = 0.10

GRADE_BRILHO_MINIMO = np.arange(10, 81, 5)
GRADE_BRILHO_MAXIMO = np.arange(170, 251, 5)
GRADE_NITIDEZ = np.unique(np.round(np.geomspace(2, 400, 60), 1))
GRADE_PORTAO = np.round(np.arange(0.34, 0.951, 0.01), 2)


@dataclass(frozen=True)
class Limites:
    lado_minimo: int
    brilho_minimo: float
    brilho_maximo: float
    nitidez_minima: float
    limite_outra_planta: float
    limite_nao_e_planta: float


def limites_atuais() -> Limites:
    return Limites(
        qualidade.LADO_MINIMO,
        qualidade.BRILHO_MINIMO,
        qualidade.BRILHO_MAXIMO,
        qualidade.NITIDEZ_MINIMA,
        modulo_portao.LIMITES[modulo_portao.OUTRA_PLANTA],
        modulo_portao.LIMITES[modulo_portao.NAO_E_PLANTA],
    )


class Medidas:
    def __init__(self, registros: list[dict]) -> None:
        self.esperado = np.array([r["esperado"] for r in registros])
        self.conjunto = np.array([r["conjunto"] for r in registros])
        self.lado = np.array([r["menorLado"] for r in registros])
        self.brilho = np.array([r["brilho"] for r in registros])
        self.nitidez = np.array([r["nitidez"] for r in registros])
        grupos = (
            modulo_portao.CULTURAS_DO_ESCOPO,
            modulo_portao.OUTRA_PLANTA,
            modulo_portao.NAO_E_PLANTA,
        )
        probabilidades = np.array([[r["probabilidades"][g] for g in grupos] for r in registros])
        self.vencedor = probabilidades.argmax(axis=1)
        self.prob_vencedor = probabilidades.max(axis=1)
        aceitas = self.esperado == ACEITA
        self.laboratorio = aceitas & np.char.startswith(self.conjunto.astype(str), "plantvillage")
        self.campo = aceitas & ~self.laboratorio

    def motivos(self, limites: Limites) -> np.ndarray:
        motivo = np.full(self.esperado.shape, ACEITA, dtype=object)
        livre = np.ones(self.esperado.shape, dtype=bool)
        for condicao, nome in (
            (self.lado < limites.lado_minimo, "RESOLUCAO_BAIXA"),
            (self.brilho < limites.brilho_minimo, "IMAGEM_ESCURA"),
            (self.brilho > limites.brilho_maximo, "IMAGEM_CLARA"),
            (self.nitidez < limites.nitidez_minima, "IMAGEM_BORRADA"),
            (
                (self.vencedor == 1) & (self.prob_vencedor > limites.limite_outra_planta),
                "CULTURA_FORA_DO_ESCOPO",
            ),
            (
                (self.vencedor == 2) & (self.prob_vencedor > limites.limite_nao_e_planta),
                "NAO_E_PLANTA",
            ),
        ):
            marcar = livre & condicao
            motivo[marcar] = nome
            livre &= ~marcar
        return motivo

    def avaliar(self, limites: Limites, considerar: tuple[str, ...]) -> dict:
        motivo = self.motivos(limites)
        rejeitada = motivo != ACEITA
        corretas = {
            m: float(np.mean(motivo[self.esperado == m] == m))
            for m in considerar
            if np.any(self.esperado == m)
        }
        falsa_lab = float(np.mean(rejeitada[self.laboratorio])) if self.laboratorio.any() else 0.0
        falsa_campo = float(np.mean(rejeitada[self.campo])) if self.campo.any() else 0.0
        falsa = (falsa_lab + falsa_campo) / 2 if self.campo.any() else falsa_lab
        media = float(np.mean(list(corretas.values()))) if corretas else 0.0
        return {
            "rejeicaoCorretaPorMotivo": {m: round(v, 4) for m, v in corretas.items()},
            "rejeicaoCorretaMedia": round(media, 4),
            "falsaRejeicaoLaboratorio": round(falsa_lab, 4),
            "falsaRejeicaoCampo": round(falsa_campo, 4),
            "falsaRejeicao": round(falsa, 4),
            "j": round(media - falsa, 4),
        }


def melhor(medidas: Medidas, candidatos, considerar) -> tuple[Limites, dict, list[dict]]:
    avaliados = []
    for limites in candidatos:
        resultado = medidas.avaliar(limites, considerar)
        avaliados.append((limites, resultado))
    permitidos = [
        a for a in avaliados if a[1]["falsaRejeicao"] <= FALSA_REJEICAO_MAXIMA
    ] or avaliados
    escolhido = max(permitidos, key=lambda a: (a[1]["j"], -a[1]["falsaRejeicao"]))
    fronteira = {}
    for limites, resultado in avaliados:
        chave = round(resultado["falsaRejeicao"], 2)
        if (
            chave not in fronteira
            or resultado["rejeicaoCorretaMedia"] > fronteira[chave][1]["rejeicaoCorretaMedia"]
        ):
            fronteira[chave] = (limites, resultado)
    tabela = [
        {**asdict(limites), **resultado}
        for _, (limites, resultado) in sorted(fronteira.items())
        if resultado["falsaRejeicao"] <= 0.2
    ]
    return escolhido[0], escolhido[1], tabela


def calibrar(medidas: Medidas) -> dict:
    atuais = limites_atuais()
    qualidade_candidatos = [
        replace(
            atuais,
            brilho_minimo=float(b0),
            brilho_maximo=float(b1),
            nitidez_minima=float(n),
            limite_outra_planta=1.0,
            limite_nao_e_planta=1.0,
        )
        for b0, b1, n in product(GRADE_BRILHO_MINIMO, GRADE_BRILHO_MAXIMO, GRADE_NITIDEZ)
    ]
    q, resultado_q, fronteira_q = melhor(medidas, qualidade_candidatos, MOTIVOS_QUALIDADE)

    portao_candidatos = [
        replace(q, limite_outra_planta=float(a), limite_nao_e_planta=float(b))
        for a, b in product(GRADE_PORTAO, GRADE_PORTAO)
    ]
    escolhido, resultado_p, fronteira_p = melhor(medidas, portao_candidatos, MOTIVOS_PORTAO)

    todos = MOTIVOS_QUALIDADE + MOTIVOS_PORTAO
    return {
        "criterio": (
            "J = média da rejeição correta por motivo - falsa rejeição "
            "(média de laboratório e campo), com falsa rejeição de no máximo "
            f"{FALSA_REJEICAO_MAXIMA:.0%}; qualidade primeiro, portão depois"
        ),
        "imagens": int(len(medidas.esperado)),
        "imagensPorEsperado": {
            str(k): int(v)
            for k, v in zip(*np.unique(medidas.esperado, return_counts=True), strict=True)
        },
        "limitesAnteriores": asdict(atuais),
        "resultadoAnterior": medidas.avaliar(atuais, todos),
        "limitesEscolhidos": asdict(escolhido),
        "resultadoEscolhido": medidas.avaliar(escolhido, todos),
        "etapaQualidade": {
            "escolhido": asdict(q),
            "resultado": resultado_q,
            "fronteira": fronteira_q,
        },
        "etapaPortao": {
            "escolhido": asdict(escolhido),
            "resultado": resultado_p,
            "fronteira": fronteira_p,
        },
    }


def tabela_md(calibracao: dict) -> str:
    antes, depois = calibracao["resultadoAnterior"], calibracao["resultadoEscolhido"]
    la, le = calibracao["limitesAnteriores"], calibracao["limitesEscolhidos"]
    linhas = [
        "# Calibração da qualidade e do portão",
        "",
        f"Medidas de {calibracao['imagens']} imagens dos conjuntos de calibração "
        "(validação do PlantVillage, metade do PlantDoc e do Imagenette e versões degradadas "
        "da validação). Nenhuma imagem do teste entra aqui.",
        "",
        f"Critério: {calibracao['criterio']}.",
        "",
        "## Limites",
        "",
        "| Limite | Antes | Escolhido |",
        "| --- | --- | --- |",
    ]
    nomes = {
        "lado_minimo": "Menor lado mínimo (px)",
        "brilho_minimo": "Brilho médio mínimo",
        "brilho_maximo": "Brilho médio máximo",
        "nitidez_minima": "Variância do Laplaciano mínima",
        "limite_outra_planta": "Portão: outra planta",
        "limite_nao_e_planta": "Portão: não é planta",
    }
    for chave, nome in nomes.items():
        linhas.append(f"| {nome} | {la[chave]} | {le[chave]} |")
    linhas += [
        "",
        "## Resultado na calibração",
        "",
        "| Medida | Antes | Depois |",
        "| --- | --- | --- |",
    ]
    for motivo in antes["rejeicaoCorretaPorMotivo"]:
        linhas.append(
            f"| Rejeição correta {motivo} | {antes['rejeicaoCorretaPorMotivo'][motivo]:.3f} | "
            f"{depois['rejeicaoCorretaPorMotivo'][motivo]:.3f} |"
        )
    for chave, nome in (
        ("falsaRejeicaoLaboratorio", "Falsa rejeição (PlantVillage)"),
        ("falsaRejeicaoCampo", "Falsa rejeição (PlantDoc das 3 culturas)"),
        ("j", "J"),
    ):
        linhas.append(f"| {nome} | {antes[chave]:.3f} | {depois[chave]:.3f} |")
    for etapa, titulo in (("etapaQualidade", "qualidade"), ("etapaPortao", "portão")):
        linhas += [
            "",
            f"## Fronteira da etapa de {titulo}",
            "",
            "Melhor rejeição correta média para cada nível de falsa rejeição.",
            "",
            "| Falsa rejeição | Rejeição correta média | Brilho mín. | Brilho máx. | Nitidez mín. "
            "| Outra planta | Não é planta |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
        for ponto in calibracao[etapa]["fronteira"]:
            linhas.append(
                f"| {ponto['falsaRejeicao']:.3f} | {ponto['rejeicaoCorretaMedia']:.3f} | "
                f"{ponto['brilho_minimo']} | {ponto['brilho_maximo']} | "
                f"{ponto['nitidez_minima']} | "
                f"{ponto['limite_outra_planta']} | {ponto['limite_nao_e_planta']} |"
            )
    return "\n".join(linhas) + "\n"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--medidas", type=Path, required=True)
    parser.add_argument("--saida", type=Path, default=Path("avaliacao/portao"))
    args = parser.parse_args(argv)

    registros = [
        json.loads(linha)
        for linha in args.medidas.read_text(encoding="utf-8").splitlines()
        if linha.strip()
    ]
    calibracao = calibrar(Medidas(registros))
    args.saida.mkdir(parents=True, exist_ok=True)
    (args.saida / "calibracao.json").write_text(
        json.dumps(calibracao, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (args.saida / "calibracao.md").write_text(tabela_md(calibracao), encoding="utf-8")
    print(json.dumps(calibracao["limitesEscolhidos"], indent=2), file=sys.stderr)
    print(
        json.dumps(calibracao["resultadoEscolhido"], indent=2, ensure_ascii=False), file=sys.stderr
    )


if __name__ == "__main__":
    main()
