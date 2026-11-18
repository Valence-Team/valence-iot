"""Monta as pastas de calibração e de teste do portão em datasets/portao/.

Uso, a partir da raiz do repositório (dependências de requirements-dev.txt):

    python -m scripts.preparar_avaliacao [--por-conjunto 300] [--imagenette ARQUIVO.tgz]

- PlantVillage: a validação é recriada com a mesma regra do notebook de treino
  (folhas em comum com o teste saem do treino; 15% de cada classe, agrupado por folha,
  semente 42). Só as imagens sorteadas são lidas do data.zip, por faixa.
- PlantDoc e Imagenette: metade para calibração e metade para teste, semente 42.
Origem e licença de cada conjunto: dados/avaliacao/imagens.md.
"""

import argparse
import io
import json
import random
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq
from huggingface_hub import HfFileSystem, hf_hub_download, snapshot_download
from PIL import Image
from sklearn.model_selection import GroupShuffleSplit

from app.rotulos import carregar_rotulos

SEMENTE = 42
FRACAO_VALIDACAO = 0.15
REPO_PV = "mohanty/PlantVillage"
REPO_PD = "Project-AgML/plant_doc_classification"
URL_IMAGENETTE = "https://s3.amazonaws.com/fast-ai-imageclas/imagenette2-320.tgz"
CLASSES_IMAGENETTE = ("n02979186", "n03028079", "n03417042", "n03425413", "n03445777")
PREFIXOS_ESCOPO = ("Corn_(maize)___", "Potato___", "Tomato___")
CULTURAS_PD = ("corn", "tomato", "potato")
PASTAS_PLANTVILLAGE = {
    "plantvillage_validacao": ("calibracao", "plantvillage_escopo"),
    "plantvillage_teste": ("teste", "plantvillage_escopo"),
    "plantvillage_outras_calibracao": ("calibracao", "plantvillage_outras"),
    "plantvillage_outras_teste": ("teste", "plantvillage_outras"),
}


# PlantVillage: divisão igual à do notebook
def ler_split(arquivo: str) -> list[str]:
    texto = Path(arquivo).read_text(encoding="utf-8")
    return [linha.strip() for linha in texto.splitlines() if linha.strip()]


def obter_leaf_id(caminho: str, mapa: dict) -> str:
    classe, arquivo = caminho.split("/")[2], caminho.split("/")[3]
    ident = arquivo.replace("_final_masked", "")
    if "___" in ident:
        ident = ident.split("___")[-1]
    ident = ident.split("copy")[0]
    for extensao in (".jpg", ".JPG", ".png", ".PNG"):
        ident = ident.replace(extensao, "")
    ident = ident.strip()
    sugestoes = mapa.get(ident.lower().strip())
    if not sugestoes:
        return f"fallback_{ident}"
    if len(sugestoes) == 1:
        return sugestoes[0]
    for sugestao in sugestoes:
        if classe in sugestao:
            return sugestao
    return f"fallback_{ident}"


def divisao_plantvillage() -> dict[str, list[str]]:
    treino = ler_split(hf_hub_download(REPO_PV, "splits/color_train.txt", repo_type="dataset"))
    teste = ler_split(hf_hub_download(REPO_PV, "splits/color_test.txt", repo_type="dataset"))
    mapa = json.loads(
        Path(
            hf_hub_download(REPO_PV, "leaf_grouping/leaf-map.json", repo_type="dataset")
        ).read_text(encoding="utf-8")
    )
    classes_escopo = {
        c.split("/")[2] for c in treino + teste if c.split("/")[2].startswith(PREFIXOS_ESCOPO)
    }

    escopo_treino = [c for c in treino if c.split("/")[2] in classes_escopo]
    escopo_teste = [c for c in teste if c.split("/")[2] in classes_escopo]
    folhas_teste = {obter_leaf_id(c, mapa) for c in escopo_teste}
    escopo_treino = [c for c in escopo_treino if obter_leaf_id(c, mapa) not in folhas_teste]

    validacao = []
    for classe in sorted(classes_escopo):
        grupo = [c for c in escopo_treino if c.split("/")[2] == classe]
        grupos = [obter_leaf_id(c, mapa) for c in grupo]
        divisor = GroupShuffleSplit(n_splits=1, test_size=FRACAO_VALIDACAO, random_state=SEMENTE)
        _, posicoes = next(divisor.split(np.zeros(len(grupo)), groups=grupos))
        validacao.extend(grupo[i] for i in posicoes)

    return {
        "plantvillage_validacao": validacao,
        "plantvillage_teste": escopo_teste,
        "plantvillage_outras_calibracao": [
            c for c in treino if c.split("/")[2] not in classes_escopo
        ],
        "plantvillage_outras_teste": [c for c in teste if c.split("/")[2] not in classes_escopo],
    }


def amostrar(itens: list, n: int) -> list:
    return sorted(random.Random(SEMENTE).sample(itens, min(n, len(itens))))


def nome_seguro(texto: str) -> str:
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in texto)


def extrair_plantvillage(conjuntos: dict[str, list[str]], destino: Path, n: int) -> None:
    with HfFileSystem().open(f"datasets/{REPO_PV}/data.zip", "rb", block_size=2**20) as bruto:
        arquivo = zipfile.ZipFile(bruto)
        existentes = set(arquivo.namelist())
        for nome, caminhos in conjuntos.items():
            parte, pasta = PASTAS_PLANTVILLAGE[nome]
            saida = destino / parte / pasta
            saida.mkdir(parents=True, exist_ok=True)
            escolhidos = [c for c in amostrar(caminhos, n) if c in existentes]
            for caminho in escolhidos:
                classe = nome_seguro(caminho.split("/")[2])
                (saida / f"{classe}__{nome_seguro(caminho.split('/')[3])}").write_bytes(
                    arquivo.read(caminho)
                )
            print(f"{nome}: {len(escolhidos)} imagens em {saida}", file=sys.stderr)


# PlantDoc
def extrair_plantdoc(destino: Path, n: int) -> None:
    pasta = Path(snapshot_download(REPO_PD, repo_type="dataset"))
    linhas = []
    nomes = None
    for parquet in sorted((pasta / "data").glob("*.parquet")):
        tabela = pq.read_table(parquet)
        if nomes is None:
            meta = json.loads(tabela.schema.metadata[b"huggingface"])
            nomes = meta["info"]["features"]["label"]["names"]
        for linha in tabela.to_pylist():
            linhas.append((nomes[linha["label"]], linha["image"]["bytes"]))

    for escopo in (True, False):
        indices = [
            i
            for i, (rotulo, _) in enumerate(linhas)
            if rotulo.lower().startswith(CULTURAS_PD) == escopo
        ]
        random.Random(SEMENTE).shuffle(indices)
        metade = len(indices) // 2
        for parte, fatia in (("calibracao", indices[:metade]), ("teste", indices[metade:])):
            nome = "plantdoc_escopo" if escopo else "plantdoc_outras"
            saida = destino / parte / nome
            saida.mkdir(parents=True, exist_ok=True)
            for i in sorted(fatia)[:n] if len(fatia) <= n else amostrar(fatia, n):
                rotulo, dados = linhas[i]
                imagem = Image.open(io.BytesIO(dados)).convert("RGB")
                imagem.save(saida / f"{nome_seguro(rotulo)}__{i:05d}.jpg", quality=95)
            print(f"{nome} {parte}: {min(len(fatia), n)} imagens", file=sys.stderr)


# Imagenette
def extrair_imagenette(destino: Path, n: int, arquivo: Path | None) -> None:
    if arquivo is None:
        arquivo = destino / "imagenette2-320.tgz"
        if not arquivo.exists():
            urllib.request.urlretrieve(URL_IMAGENETTE, arquivo)
    with tarfile.open(arquivo, "r:gz") as tar:
        membros = [
            m
            for m in tar.getmembers()
            if m.isfile()
            and m.name.split("/")[1:3][0:1] == ["val"]
            and m.name.split("/")[2] in CLASSES_IMAGENETTE
        ]
        membros.sort(key=lambda m: m.name)
        random.Random(SEMENTE).shuffle(membros)
        metade = len(membros) // 2
        for parte, fatia in (("calibracao", membros[:metade]), ("teste", membros[metade:])):
            saida = destino / parte / "imagenette"
            saida.mkdir(parents=True, exist_ok=True)
            escolhidos = random.Random(SEMENTE).sample(fatia, min(n, len(fatia)))
            for membro in sorted(escolhidos, key=lambda m: m.name):
                wnid, nome = membro.name.split("/")[2], membro.name.split("/")[3]
                (saida / f"{wnid}__{nome}").write_bytes(tar.extractfile(membro).read())
            print(f"imagenette {parte}: {min(len(fatia), n)} imagens", file=sys.stderr)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--destino", type=Path, default=Path("datasets/portao"))
    parser.add_argument("--por-conjunto", type=int, default=300)
    parser.add_argument("--imagenette", type=Path, help="imagenette2-320.tgz já baixado")
    args = parser.parse_args(argv)

    carregar_rotulos()
    args.destino.mkdir(parents=True, exist_ok=True)
    extrair_plantvillage(divisao_plantvillage(), args.destino, args.por_conjunto)
    extrair_plantdoc(args.destino, args.por_conjunto)
    extrair_imagenette(args.destino, args.por_conjunto, args.imagenette)


if __name__ == "__main__":
    main()
