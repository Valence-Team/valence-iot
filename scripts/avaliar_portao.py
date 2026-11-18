"""Avalia a camada de qualidade e o portão CLIP em pastas de imagens.

Uso, a partir da raiz do repositório:

    python -m scripts.avaliar_portao \
        --aceitas plantvillage_teste=datasets/portao/plantvillage_teste \
        --fora-do-escopo plantvillage_outras=datasets/portao/plantvillage_outras \
                         plantdoc_outras=datasets/portao/plantdoc_outras \
        --nao-planta imagenette=datasets/portao/imagenette \
        --degradar plantvillage_teste \
        --revisao datasets/portao/revisao

Cada conjunto de --degradar gera em memória uma versão borrada (espera IMAGEM_BORRADA)
e uma escurecida (espera IMAGEM_ESCURA). Imagens com pessoas saem antes da avaliação.
Origem, licença e preparo das pastas: dados/avaliacao/imagens.md.
O resultado vai para avaliacao/portao/metricas.json.
"""

import argparse
import json
import random
import sys
from collections import Counter
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

import numpy as np
import torch
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter
from torchvision.models import detection
from torchvision.transforms.functional import to_tensor

from app.config import Configuracao
from app.erros import ErroApi
from app.schemas import MotivoRecusa
from app.visao import portao as modulo_portao
from app.visao import qualidade
from app.visao.portao import PortaoClip

EXTENSOES = {".jpg", ".jpeg", ".png", ".webp"}
ACEITA = "ACEITA"
SEMENTE = 42

# Degradações sintéticas
FATOR_ESCURECER = 0.15
FATOR_CLAREAR = 2.8
DIVISOR_RAIO_BORRAO = 48
LADO_REDUZIDO = 160

# Filtro de pessoas (detector COCO; limite baixo porque excluir a mais não prejudica a métrica)
CLASSE_PESSOA_COCO = 1
LIMITE_PESSOA = 0.3

# Revisão manual: pessoas que o detector não encontrou
EXCLUIDAS_NA_REVISAO = frozenset(
    {
        "ILSVRC2012_val_00020781.JPEG",
        "ILSVRC2012_val_00034001.JPEG",
    }
)

# Folha de revisão
LADO_MINIATURA = 160
COLUNAS_REVISAO = 8

Transformacao = Callable[[Image.Image], Image.Image]


@dataclass
class Conjunto:
    nome: str
    esperado: str
    pasta: Path
    transformacao: Transformacao | None = None
    filtrar_pessoas: bool = True


@dataclass
class Resultado:
    conjunto: Conjunto
    contagem: Counter = field(default_factory=Counter)
    brilho: list[float] = field(default_factory=list)
    nitidez: list[float] = field(default_factory=list)
    grupos: dict[str, list[float]] = field(default_factory=dict)
    excluidas_por_pessoas: list[str] = field(default_factory=list)
    avaliadas: list[Path] = field(default_factory=list)
    ilegiveis: int = 0
    ms_qualidade: list[float] = field(default_factory=list)
    ms_portao: list[float] = field(default_factory=list)


# Degradações
def borrar(imagem: Image.Image) -> Image.Image:
    raio = max(2.0, min(imagem.size) / DIVISOR_RAIO_BORRAO)
    return imagem.filter(ImageFilter.GaussianBlur(raio))


def escurecer(imagem: Image.Image) -> Image.Image:
    return ImageEnhance.Brightness(imagem).enhance(FATOR_ESCURECER)


def clarear(imagem: Image.Image) -> Image.Image:
    return ImageEnhance.Brightness(imagem).enhance(FATOR_CLAREAR)


def reduzir(imagem: Image.Image) -> Image.Image:
    escala = LADO_REDUZIDO / min(imagem.size)
    novo = (round(imagem.width * escala), round(imagem.height * escala))
    return imagem.resize(novo, Image.Resampling.LANCZOS)


DEGRADACOES: dict[str, tuple[str, Transformacao]] = {
    "borrada": (MotivoRecusa.IMAGEM_BORRADA.value, borrar),
    "escurecida": (MotivoRecusa.IMAGEM_ESCURA.value, escurecer),
    "clareada": (MotivoRecusa.IMAGEM_CLARA.value, clarear),
    "reduzida": (MotivoRecusa.RESOLUCAO_BAIXA.value, reduzir),
}


# Leitura das pastas
def listar(pasta: Path, maximo: int | None) -> list[Path]:
    arquivos = sorted(p for p in pasta.rglob("*") if p.suffix.lower() in EXTENSOES)
    if maximo is not None and len(arquivos) > maximo:
        arquivos = sorted(random.Random(SEMENTE).sample(arquivos, maximo))
    return arquivos


def abrir(caminho: Path) -> Image.Image | None:
    try:
        return qualidade.abrir_imagem(caminho.read_bytes())
    except ErroApi:
        return None


class FiltroPessoas:
    def __init__(self) -> None:
        pesos = detection.FasterRCNN_MobileNet_V3_Large_FPN_Weights.COCO_V1
        self.detector = detection.fasterrcnn_mobilenet_v3_large_fpn(
            weights=pesos, box_score_thresh=LIMITE_PESSOA
        ).eval()
        self.cache: dict[Path, bool] = {}

    @torch.inference_mode()
    def tem_pessoa(self, caminho: Path, imagem: Image.Image) -> bool:
        if caminho.name.split("__")[-1] in EXCLUIDAS_NA_REVISAO:
            return True
        if caminho not in self.cache:
            saida = self.detector([to_tensor(imagem)])[0]
            self.cache[caminho] = bool((saida["labels"] == CLASSE_PESSOA_COCO).any())
        return self.cache[caminho]


def avaliar_conjunto(
    conjunto: Conjunto,
    arquivos: list[Path],
    portao: PortaoClip,
    filtro: FiltroPessoas | None,
    medidas_por_imagem: list[dict] | None = None,
) -> Resultado:
    resultado = Resultado(conjunto, grupos={g: [] for g in portao.grupos})
    for caminho in arquivos:
        imagem = abrir(caminho)
        if imagem is None:
            resultado.ilegiveis += 1
            continue
        if filtro and conjunto.filtrar_pessoas and filtro.tem_pessoa(caminho, imagem):
            resultado.excluidas_por_pessoas.append(caminho.name)
            continue
        resultado.avaliadas.append(caminho)
        if conjunto.transformacao is not None:
            imagem = conjunto.transformacao(imagem)

        inicio = perf_counter()
        medidas = qualidade.medir(imagem)
        motivo = qualidade.motivo_por_medidas(medidas)
        resultado.ms_qualidade.append((perf_counter() - inicio) * 1000)
        resultado.brilho.append(medidas.brilho)
        resultado.nitidez.append(medidas.nitidez)

        probabilidades = None
        if motivo is None or medidas_por_imagem is not None:
            inicio = perf_counter()
            probabilidades = portao.probabilidades(imagem)
            if motivo is None:
                motivo = modulo_portao.decidir(probabilidades).motivo
                resultado.ms_portao.append((perf_counter() - inicio) * 1000)
                for grupo, valor in probabilidades.items():
                    resultado.grupos[grupo].append(valor)

        if medidas_por_imagem is not None:
            medidas_por_imagem.append(
                {
                    "conjunto": conjunto.nome,
                    "esperado": conjunto.esperado,
                    "arquivo": caminho.name,
                    "menorLado": medidas.menor_lado,
                    "brilho": round(medidas.brilho, 3),
                    "nitidez": round(medidas.nitidez, 3),
                    "probabilidades": {g: round(v, 5) for g, v in probabilidades.items()},
                }
            )
        resultado.contagem[motivo.value if motivo else ACEITA] += 1
    return resultado


def salvar_folha_revisao(resultado: Resultado, pasta: Path) -> Path:
    arquivos = resultado.avaliadas
    linhas = max(1, -(-len(arquivos) // COLUNAS_REVISAO))
    lado = LADO_MINIATURA
    folha = Image.new("RGB", (COLUNAS_REVISAO * lado, linhas * lado), "white")
    desenho = ImageDraw.Draw(folha)
    for i, caminho in enumerate(arquivos):
        x, y = (i % COLUNAS_REVISAO) * lado, (i // COLUNAS_REVISAO) * lado
        with Image.open(caminho) as original:
            miniatura = original.convert("RGB")
            miniatura.thumbnail((lado - 4, lado - 16))
        folha.paste(miniatura, (x + 2, y + 14))
        desenho.text((x + 2, y + 1), str(i), fill="red")
    pasta.mkdir(parents=True, exist_ok=True)
    destino = pasta / f"{resultado.conjunto.nome}.jpg"
    folha.save(destino, quality=85)
    indice = "\n".join(f"{i}\t{c.name}" for i, c in enumerate(arquivos))
    destino.with_suffix(".txt").write_text(indice + "\n", encoding="utf-8")
    return destino


# Métricas
def percentis(valores: list[float]) -> dict[str, float] | None:
    if not valores:
        return None
    p5, p50, p95 = np.percentile(valores, [5, 50, 95])
    return {"p5": round(float(p5), 2), "p50": round(float(p50), 2), "p95": round(float(p95), 2)}


def media(valores: list[float]) -> float | None:
    return round(float(np.mean(valores)), 4) if valores else None


def taxa(parte: int, total: int) -> float | None:
    return round(parte / total, 4) if total else None


def resumo_conjunto(resultado: Resultado) -> dict:
    total = sum(resultado.contagem.values())
    rejeitadas = total - resultado.contagem[ACEITA]
    return {
        "esperado": resultado.conjunto.esperado,
        "avaliadas": total,
        "ilegiveis": resultado.ilegiveis,
        "excluidasPorPessoas": len(resultado.excluidas_por_pessoas),
        "arquivosExcluidosPorPessoas": resultado.excluidas_por_pessoas,
        "resultados": dict(sorted(resultado.contagem.items())),
        "taxaAcerto": taxa(resultado.contagem[resultado.conjunto.esperado], total),
        "taxaRejeicao": taxa(rejeitadas, total),
        "brilho": percentis(resultado.brilho),
        "nitidez": percentis(resultado.nitidez),
        "probabilidadeMediaPorGrupo": {g: media(v) for g, v in resultado.grupos.items()},
        "latenciaMediaMs": {
            "qualidade": media(resultado.ms_qualidade),
            "portao": media(resultado.ms_portao),
        },
    }


def resumo_por_motivo(resultados: list[Resultado]) -> dict:
    aceitas = Counter()
    for r in resultados:
        if r.conjunto.esperado == ACEITA:
            aceitas.update(r.contagem)
    total_aceitas = sum(aceitas.values())

    motivos = {}
    for motivo in MotivoRecusa:
        if motivo == MotivoRecusa.CULTURA_DIVERGENTE:
            continue
        esperadas = Counter()
        for r in resultados:
            if r.conjunto.esperado == motivo.value:
                esperadas.update(r.contagem)
        total = sum(esperadas.values())
        corretas = esperadas[motivo.value]
        motivos[motivo.value] = {
            "imagensEsperadas": total,
            "rejeicaoCorreta": taxa(corretas, total),
            "rejeicaoPorOutroMotivo": taxa(total - corretas - esperadas[ACEITA], total),
            "aceitaIndevidamente": taxa(esperadas[ACEITA], total),
            "falsaRejeicao": taxa(aceitas[motivo.value], total_aceitas),
        }
    return {
        "imagensQueDevemPassar": total_aceitas,
        "taxaAceitacaoCorreta": taxa(aceitas[ACEITA], total_aceitas),
        "porMotivo": motivos,
    }


def limites_usados() -> dict:
    return {
        "qualidade": {
            "ladoMinimo": qualidade.LADO_MINIMO,
            "brilhoMinimo": qualidade.BRILHO_MINIMO,
            "brilhoMaximo": qualidade.BRILHO_MAXIMO,
            "nitidezMinima": qualidade.NITIDEZ_MINIMA,
            "ladoAnalise": qualidade.LADO_ANALISE,
        },
        "portao": {
            "limites": modulo_portao.LIMITES,
            "prompts": {g: list(p) for g, p in modulo_portao.PROMPTS.items()},
        },
        "degradacoes": {
            "fatorEscurecer": FATOR_ESCURECER,
            "fatorClarear": FATOR_CLAREAR,
            "raioBorrao": f"max(2, menor lado / {DIVISOR_RAIO_BORRAO})",
            "ladoReduzido": LADO_REDUZIDO,
        },
        "filtroPessoas": {
            "detector": "fasterrcnn_mobilenet_v3_large_fpn (COCO_V1)",
            "limite": LIMITE_PESSOA,
            "excluidasNaRevisao": sorted(EXCLUIDAS_NA_REVISAO),
        },
    }


# Linha de comando
def pares(valores: list[str] | None) -> Iterator[tuple[str, Path]]:
    for valor in valores or []:
        nome, separador, pasta = valor.partition("=")
        if not separador or not nome or not pasta:
            raise SystemExit(f"Use NOME=PASTA, recebido: {valor}")
        caminho = Path(pasta)
        if not caminho.is_dir():
            raise SystemExit(f"Pasta não encontrada: {caminho}")
        yield nome, caminho


def montar_conjuntos(args: argparse.Namespace) -> list[Conjunto]:
    conjuntos = [Conjunto(n, ACEITA, p) for n, p in pares(args.aceitas)]
    conjuntos += [
        Conjunto(n, MotivoRecusa.CULTURA_FORA_DO_ESCOPO.value, p)
        for n, p in pares(args.fora_do_escopo)
    ]
    conjuntos += [
        Conjunto(n, MotivoRecusa.NAO_E_PLANTA.value, p) for n, p in pares(args.nao_planta)
    ]
    aceitas = {c.nome: c for c in conjuntos if c.esperado == ACEITA}
    for nome in args.degradar or []:
        if nome not in aceitas:
            raise SystemExit(f"--degradar aceita só conjuntos de --aceitas: {nome}")
        for sufixo, (esperado, transformacao) in DEGRADACOES.items():
            conjuntos.append(
                Conjunto(f"{nome}_{sufixo}", esperado, aceitas[nome].pasta, transformacao)
            )
    if not conjuntos:
        raise SystemExit("Informe ao menos um conjunto.")
    sem_filtro = set(args.sem_filtro_pessoas or [])
    for conjunto in conjuntos:
        origem = next((n for n in sem_filtro if conjunto.nome.startswith(n)), None)
        conjunto.filtrar_pessoas = origem is None
    return conjuntos


def ler_argumentos(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--aceitas", nargs="+", metavar="NOME=PASTA")
    parser.add_argument("--fora-do-escopo", nargs="+", metavar="NOME=PASTA")
    parser.add_argument("--nao-planta", nargs="+", metavar="NOME=PASTA")
    parser.add_argument("--degradar", nargs="+", metavar="NOME")
    parser.add_argument("--maximo", type=int, help="Máximo de imagens por conjunto (amostra fixa)")
    parser.add_argument("--modelo", default=Configuracao().portao_modelo)
    parser.add_argument("--revisao", type=Path, help="Pasta para as folhas de revisão visual")
    parser.add_argument(
        "--sem-filtro-pessoas",
        nargs="+",
        metavar="NOME",
        help="Conjuntos já revisados sem pessoas (fotos de laboratório); pula o detector",
    )
    parser.add_argument(
        "--medidas", type=Path, help="JSONL com brilho, nitidez e probabilidades de cada imagem"
    )
    parser.add_argument("--saida", type=Path, default=Path("avaliacao/portao/metricas.json"))
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = ler_argumentos(argv)
    conjuntos = montar_conjuntos(args)
    portao = PortaoClip.carregar(args.modelo)
    filtro = FiltroPessoas()

    resultados = []
    medidas = [] if args.medidas else None
    for conjunto in conjuntos:
        arquivos = listar(conjunto.pasta, args.maximo)
        inicio = perf_counter()
        resultado = avaliar_conjunto(conjunto, arquivos, portao, filtro, medidas)
        resultados.append(resultado)
        resumo = resumo_conjunto(resultado)
        print(
            f"{conjunto.nome}: {resumo['avaliadas']} avaliadas, acerto {resumo['taxaAcerto']}, "
            f"{resumo['excluidasPorPessoas']} excluídas por pessoas, "
            f"{perf_counter() - inicio:.0f} s",
            file=sys.stderr,
        )
        if args.revisao and conjunto.transformacao is None:
            print(f"  revisão: {salvar_folha_revisao(resultado, args.revisao)}", file=sys.stderr)

    metricas = {
        "geradoEm": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "modeloPortao": args.modelo,
        "torchThreads": torch.get_num_threads(),
        "maximoPorConjunto": args.maximo,
        "limites": limites_usados(),
        "geral": resumo_por_motivo(resultados),
        "conjuntos": {r.conjunto.nome: resumo_conjunto(r) for r in resultados},
    }
    args.saida.parent.mkdir(parents=True, exist_ok=True)
    args.saida.write_text(
        json.dumps(metricas, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Métricas gravadas em {args.saida}", file=sys.stderr)
    if medidas is not None:
        args.medidas.parent.mkdir(parents=True, exist_ok=True)
        linhas = (json.dumps(m, ensure_ascii=False) for m in medidas)
        args.medidas.write_text("\n".join(linhas) + "\n", encoding="utf-8")
        print(f"Medidas por imagem gravadas em {args.medidas}", file=sys.stderr)


if __name__ == "__main__":
    main()
