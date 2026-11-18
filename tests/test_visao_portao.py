import numpy as np
import pytest
import torch
from transformers import CLIPConfig, CLIPModel

from app.schemas import Cultura, MotivoRecusa
from app.visao.portao import (
    CULTURAS_DO_ESCOPO,
    NAO_E_PLANTA,
    OUTRA_PLANTA,
    PROMPTS,
    PortaoClip,
    decidir,
)
from tests.test_visao_apoio import figura_nitida


# CLIP minúsculo, sem download
class TokenizadorFalso:
    def __init__(self) -> None:
        self.chamadas = 0

    def __call__(self, textos, padding=True, return_tensors="pt"):
        self.chamadas += 1
        ids = torch.tensor([[1 + (len(t) + i) % 90 for i in range(6)] for t in textos])
        return {"input_ids": ids, "attention_mask": torch.ones_like(ids)}


class ProcessadorImagemFalso:
    def __call__(self, images, return_tensors="pt"):
        pequena = images.convert("RGB").resize((32, 32))
        pixels = torch.from_numpy(np.asarray(pequena, dtype=np.float32) / 255.0)
        return {"pixel_values": pixels.permute(2, 0, 1).unsqueeze(0)}


class ProcessadorFalso:
    def __init__(self) -> None:
        self.tokenizer = TokenizadorFalso()
        self.image_processor = ProcessadorImagemFalso()


@pytest.fixture
def portao() -> PortaoClip:
    torch.manual_seed(0)
    comum = {
        "hidden_size": 16,
        "intermediate_size": 32,
        "num_hidden_layers": 1,
        "num_attention_heads": 2,
    }
    config = CLIPConfig(
        text_config={**comum, "vocab_size": 100, "max_position_embeddings": 16},
        vision_config={**comum, "image_size": 32, "patch_size": 16},
        projection_dim=8,
    )
    return PortaoClip(CLIPModel(config), ProcessadorFalso())


# Decisão
@pytest.mark.parametrize(
    ("probabilidades", "motivo"),
    [
        ({CULTURAS_DO_ESCOPO: 0.9, OUTRA_PLANTA: 0.05, NAO_E_PLANTA: 0.05}, None),
        ({CULTURAS_DO_ESCOPO: 0.1, OUTRA_PLANTA: 0.1, NAO_E_PLANTA: 0.8}, "NAO_E_PLANTA"),
        (
            {CULTURAS_DO_ESCOPO: 0.2, OUTRA_PLANTA: 0.75, NAO_E_PLANTA: 0.05},
            "CULTURA_FORA_DO_ESCOPO",
        ),
        ({CULTURAS_DO_ESCOPO: 0.35, OUTRA_PLANTA: 0.55, NAO_E_PLANTA: 0.1}, None),
        ({CULTURAS_DO_ESCOPO: 0.33, OUTRA_PLANTA: 0.33, NAO_E_PLANTA: 0.34}, None),
    ],
)
def test_decide_pelo_grupo_vencedor_e_pelo_limite(probabilidades, motivo):
    veredito = decidir(probabilidades)

    assert veredito.motivo == (MotivoRecusa(motivo) if motivo else None)
    assert veredito.cultura_detectada is None


def test_tres_grupos_de_prompts_em_ingles():
    assert set(PROMPTS) == {CULTURAS_DO_ESCOPO, OUTRA_PLANTA, NAO_E_PLANTA}
    assert all(p.startswith("a ") for prompts in PROMPTS.values() for p in prompts)


# Portão com CLIP
def test_embeddings_de_texto_calculados_uma_vez(portao):
    assert portao.processador.tokenizer.chamadas == 3

    for semente in range(3):
        portao.verificar(figura_nitida(semente=semente), Cultura.MILHO)

    assert portao.processador.tokenizer.chamadas == 3


def test_embedding_de_cada_grupo_e_a_media_normalizada(portao):
    norma = portao.embeddings_grupos.norm(dim=-1)

    assert portao.embeddings_grupos.shape == (3, 8)
    assert torch.allclose(norma, torch.ones(3), atol=1e-5)


def test_probabilidades_dos_tres_grupos_somam_um(portao):
    probabilidades = portao.probabilidades(figura_nitida())

    assert set(probabilidades) == {CULTURAS_DO_ESCOPO, OUTRA_PLANTA, NAO_E_PLANTA}
    assert sum(probabilidades.values()) == pytest.approx(1.0, abs=1e-5)


def test_verificar_usa_os_limites(portao, monkeypatch):
    monkeypatch.setattr(
        portao,
        "probabilidades",
        lambda _i: {CULTURAS_DO_ESCOPO: 0, OUTRA_PLANTA: 0, NAO_E_PLANTA: 1},
    )

    assert portao.verificar(figura_nitida(), Cultura.TOMATE).motivo == MotivoRecusa.NAO_E_PLANTA
