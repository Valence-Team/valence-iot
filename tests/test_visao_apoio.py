import io
import json
from pathlib import Path

import numpy as np
import torch
from PIL import Image, ImageFilter
from torch import nn

from app.rotulos import carregar_rotulos

ROTULOS = carregar_rotulos()
CLASSES = list(ROTULOS)
CULTURAS = [ROTULOS[r].cultura.value for r in CLASSES]
TEMPERATURA = 1.5


# Imagens sintéticas
def figura_nitida(tamanho: tuple[int, int] = (256, 256), semente: int = 0) -> Image.Image:
    gerador = np.random.default_rng(semente)
    base = np.array([60, 140, 70], dtype=np.float32)
    ruido = gerador.normal(0, 45, size=(tamanho[1], tamanho[0], 1)).astype(np.float32)
    pixels = np.clip(base + ruido, 0, 255).astype(np.uint8)
    return Image.fromarray(pixels)


def figura_lisa(cor: tuple[int, int, int], tamanho: tuple[int, int] = (256, 256)) -> Image.Image:
    return Image.new("RGB", tamanho, cor)


def figura_borrada(raio: float = 6.0) -> Image.Image:
    return figura_nitida().filter(ImageFilter.GaussianBlur(raio))


def para_bytes(figura: Image.Image, formato: str = "PNG", **opcoes) -> bytes:
    buffer = io.BytesIO()
    figura.save(buffer, format=formato, **opcoes)
    return buffer.getvalue()


# Modelo minúsculo no formato de modelos/visao.json
class RedeMinuscula(nn.Module):
    def __init__(self, weights=None) -> None:
        super().__init__()
        self.features = nn.Sequential(nn.Conv2d(3, 4, 3), nn.AdaptiveAvgPool2d(1), nn.Flatten())
        self.classifier = nn.Sequential(nn.Linear(4, 1000))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.classifier(self.features(x))


def metadados(**ajustes: object) -> dict:
    return {
        "arquitetura": "rede_minuscula",
        "pesosBase": "nenhum",
        "cabeca": f"classifier[-1] = Linear(in_features, {len(CLASSES)})",
        "experimento": "teste",
        "classes": CLASSES,
        "classesPlantVillage": [ROTULOS[r].classe_plant_village for r in CLASSES],
        "culturas": CULTURAS,
        "nomes": [ROTULOS[r].nome for r in CLASSES],
        "media": [0.485, 0.456, 0.406],
        "desvio": [0.229, 0.224, 0.225],
        "tamanhoEntrada": 224,
        "redimensionar": 256,
        "temperatura": TEMPERATURA,
        "modoRapido": True,
        **ajustes,
    }


def logits_fixos(por_rotulo: dict[str, float], padrao: float = -8.0) -> torch.Tensor:
    return torch.tensor([por_rotulo.get(r, padrao) for r in CLASSES], dtype=torch.float32)


def salvar_modelo(pasta: Path, por_rotulo: dict[str, float], **ajustes: object) -> Path:
    rede = RedeMinuscula()
    rede.classifier[-1] = nn.Linear(4, len(CLASSES))
    with torch.no_grad():
        rede.classifier[-1].weight.zero_()
        rede.classifier[-1].bias.copy_(logits_fixos(por_rotulo))
    pesos = pasta / "visao.pt"
    torch.save(rede.state_dict(), pesos)
    (pasta / "visao.json").write_text(
        json.dumps(metadados(**ajustes), ensure_ascii=False), encoding="utf-8"
    )
    return pesos
