from typing import Any

import torch
import torch.nn.functional as F
from PIL.Image import Image
from transformers import CLIPModel, CLIPProcessor

from app.schemas import Cultura, MotivoRecusa
from app.visao import VereditoPortao

# Grupos de prompts
CULTURAS_DO_ESCOPO = "culturas_do_escopo"
OUTRA_PLANTA = "outra_planta"
NAO_E_PLANTA = "nao_e_planta"

PROMPTS: dict[str, tuple[str, ...]] = {
    CULTURAS_DO_ESCOPO: (
        "a photo of a corn leaf",
        "a photo of a maize leaf",
        "a close-up photo of a diseased corn leaf",
        "a photo of a tomato leaf",
        "a close-up photo of a diseased tomato leaf",
        "a photo of a tomato plant leaf with spots",
        "a photo of a potato leaf",
        "a close-up photo of a diseased potato leaf",
    ),
    OUTRA_PLANTA: (
        "a photo of a leaf of another plant",
        "a photo of a soybean leaf",
        "a photo of a grape leaf",
        "a photo of an apple leaf",
        "a photo of a strawberry leaf",
        "a photo of a bell pepper leaf",
        "a photo of a squash leaf",
        "a photo of a citrus leaf",
        "a photo of a houseplant",
        "a photo of a flower",
    ),
    NAO_E_PLANTA: (
        "a photo of an object",
        "a photo of a machine",
        "a photo of a vehicle",
        "a photo of an animal",
        "a photo of a person",
        "a photo of a document",
        "a photo of a text page",
        "a photo of a landscape",
        "a photo of a building",
    ),
}

# Limites de decisão
LIMITES = {OUTRA_PLANTA: 0.60, NAO_E_PLANTA: 0.50}
MOTIVOS = {
    OUTRA_PLANTA: MotivoRecusa.CULTURA_FORA_DO_ESCOPO,
    NAO_E_PLANTA: MotivoRecusa.NAO_E_PLANTA,
}


def decidir(probabilidades: dict[str, float]) -> VereditoPortao:
    vencedor = max(probabilidades, key=probabilidades.__getitem__)
    limite = LIMITES.get(vencedor)
    if limite is not None and probabilidades[vencedor] > limite:
        return VereditoPortao(motivo=MOTIVOS[vencedor], cultura_detectada=None)
    return VereditoPortao(motivo=None, cultura_detectada=None)


class PortaoClip:
    def __init__(self, modelo: CLIPModel, processador: Any) -> None:
        self.modelo = modelo.eval().requires_grad_(False)
        self.processador = processador
        self.grupos = tuple(PROMPTS)
        self.escala = float(self.modelo.logit_scale.exp())
        self.embeddings_grupos = self._embeddings_dos_grupos()

    @classmethod
    def carregar(cls, nome_modelo: str) -> "PortaoClip":
        modelo = CLIPModel.from_pretrained(nome_modelo)
        processador = CLIPProcessor.from_pretrained(nome_modelo)
        return cls(modelo, processador)

    # Embeddings normalizados
    @torch.inference_mode()
    def embeddings_texto(self, prompts: list[str]) -> torch.Tensor:
        tokens = self.processador.tokenizer(prompts, padding=True, return_tensors="pt")
        saida = self.modelo.text_model(
            input_ids=tokens["input_ids"], attention_mask=tokens["attention_mask"]
        )
        return F.normalize(self.modelo.text_projection(saida.pooler_output), dim=-1)

    @torch.inference_mode()
    def embedding_imagem(self, imagem: Image) -> torch.Tensor:
        pixels = self.processador.image_processor(images=imagem, return_tensors="pt")
        saida = self.modelo.vision_model(pixel_values=pixels["pixel_values"])
        return F.normalize(self.modelo.visual_projection(saida.pooler_output), dim=-1)

    # Média dos embeddings de texto de cada grupo
    def _embeddings_dos_grupos(self) -> torch.Tensor:
        medias = [self.embeddings_texto(list(PROMPTS[g])).mean(dim=0) for g in self.grupos]
        return F.normalize(torch.stack(medias), dim=-1)

    def probabilidades(self, imagem: Image) -> dict[str, float]:
        return self.probabilidades_do_embedding(self.embedding_imagem(imagem))

    def probabilidades_do_embedding(self, embedding: torch.Tensor) -> dict[str, float]:
        logits = self.escala * embedding @ self.embeddings_grupos.T
        return dict(zip(self.grupos, logits.softmax(dim=-1)[0].tolist(), strict=True))

    def verificar(self, imagem: Image, cultura: Cultura) -> VereditoPortao:
        return decidir(self.probabilidades(imagem))
