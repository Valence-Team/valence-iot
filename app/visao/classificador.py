from collections.abc import Callable
from pathlib import Path

import torch
from PIL.Image import Image
from pydantic import Field, model_validator
from torch import nn
from torchvision import models, transforms

from app.erros import ComponenteIndisponivel
from app.rotulos import Rotulo
from app.schemas import ClassePrevista, Contrato, Cultura, MotivoRecusa
from app.visao import ResultadoClassificacao

LIMITE_DIVERGENCIA = 0.7
CLASSES_NA_RESPOSTA = 3
CASAS_DECIMAIS = 4

ARQUITETURAS: dict[str, Callable[..., nn.Module]] = {
    "mobilenet_v3_large": models.mobilenet_v3_large,
    "efficientnet_b0": models.efficientnet_b0,
}


# Metadados gerados pelo notebook de treino (modelos/visao.json)
class MetadadosModelo(Contrato):
    arquitetura: str
    classes: list[str] = Field(min_length=2)
    culturas: list[Cultura]
    media: list[float] = Field(min_length=3, max_length=3)
    desvio: list[float] = Field(min_length=3, max_length=3)
    tamanho_entrada: int = Field(gt=0)
    redimensionar: int = Field(gt=0)
    temperatura: float = Field(gt=0)

    @model_validator(mode="after")
    def _coerente(self) -> "MetadadosModelo":
        if len(self.classes) != len(self.culturas):
            raise ValueError("classes e culturas precisam ter o mesmo tamanho")
        if len(set(self.classes)) != len(self.classes):
            raise ValueError("classes repetidas")
        return self


def criar_rede(arquitetura: str, num_classes: int) -> nn.Module:
    construtor = ARQUITETURAS.get(arquitetura)
    if construtor is None:
        raise ComponenteIndisponivel(f"arquitetura desconhecida: {arquitetura}")
    rede = construtor(weights=None)
    ultima = rede.classifier[-1]
    rede.classifier[-1] = nn.Linear(ultima.in_features, num_classes)
    return rede


class ClassificadorTorch:
    def __init__(self, rede: nn.Module, metadados: MetadadosModelo, rotulos: dict[str, Rotulo]):
        self.rede = rede.eval()
        self.metadados = metadados
        self.preparo = transforms.Compose(
            [
                transforms.Resize(metadados.redimensionar),
                transforms.CenterCrop(metadados.tamanho_entrada),
                transforms.ToTensor(),
                transforms.Normalize(metadados.media, metadados.desvio),
            ]
        )
        self.nomes = {}
        for rotulo, cultura in zip(metadados.classes, metadados.culturas, strict=True):
            conhecido = rotulos.get(rotulo)
            if conhecido is None or conhecido.cultura != cultura:
                raise ComponenteIndisponivel(f"classe sem rótulo correspondente: {rotulo}")
            self.nomes[rotulo] = conhecido.nome
        self.indices = {
            cultura: torch.tensor(
                [i for i, c in enumerate(metadados.culturas) if c == cultura], dtype=torch.long
            )
            for cultura in Cultura
        }
        if any(len(indices) == 0 for indices in self.indices.values()):
            raise ComponenteIndisponivel("o modelo não cobre as três culturas")

    @classmethod
    def carregar(cls, caminho_pesos: Path, rotulos: dict[str, Rotulo]) -> "ClassificadorTorch":
        caminho_metadados = caminho_pesos.with_suffix(".json")
        for caminho in (caminho_pesos, caminho_metadados):
            if not caminho.exists():
                raise ComponenteIndisponivel(f"arquivo não encontrado: {caminho}")
        metadados = MetadadosModelo.model_validate_json(
            caminho_metadados.read_text(encoding="utf-8")
        )
        rede = criar_rede(metadados.arquitetura, len(metadados.classes))
        rede.load_state_dict(torch.load(caminho_pesos, map_location="cpu", weights_only=True))
        return cls(rede, metadados, rotulos)

    @torch.inference_mode()
    def logits(self, imagem: Image) -> torch.Tensor:
        entrada = self.preparo(imagem).unsqueeze(0)
        return self.rede(entrada)[0].float() / self.metadados.temperatura

    def classificar(self, imagem: Image, cultura: Cultura) -> ResultadoClassificacao:
        return self.decidir(self.logits(imagem), cultura)

    def decidir(self, logits: torch.Tensor, cultura: Cultura) -> ResultadoClassificacao:
        probabilidades = logits.softmax(dim=0)
        somas = {c: float(probabilidades[i].sum()) for c, i in self.indices.items()}
        detectada = max(somas, key=somas.__getitem__)
        if detectada != cultura and somas[detectada] > LIMITE_DIVERGENCIA:
            return ResultadoClassificacao(MotivoRecusa.CULTURA_DIVERGENTE, detectada, [])

        # Distribuição renormalizada dentro da cultura informada
        indices = self.indices[cultura]
        na_cultura = logits[indices].softmax(dim=0)
        quantidade = min(CLASSES_NA_RESPOSTA, len(indices))
        valores, posicoes = na_cultura.topk(quantidade)
        classes = []
        for valor, posicao in zip(valores.tolist(), posicoes.tolist(), strict=True):
            rotulo = self.metadados.classes[int(indices[posicao])]
            classes.append(
                ClassePrevista(
                    rotulo=rotulo,
                    nome=self.nomes[rotulo],
                    confianca=round(valor, CASAS_DECIMAIS),
                )
            )
        return ResultadoClassificacao(None, detectada, classes)
