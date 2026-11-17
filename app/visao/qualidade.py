import io
from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

from app.erros import ErroApi
from app.schemas import MotivoRecusa

# Formatos aceitos
TIPOS_ACEITOS = frozenset({"image/jpeg", "image/png", "image/webp"})
TIPOS_GENERICOS = frozenset({"application/octet-stream", ""})
FORMATOS_ACEITOS = frozenset({"JPEG", "PNG", "WEBP"})
MENSAGEM_FORMATO = "Envie uma imagem JPEG, PNG ou WebP."
MENSAGEM_ILEGIVEL = "Não foi possível ler a imagem enviada."
MEGAPIXELS_MAXIMOS = 50

# Limites de qualidade (avaliacao/portao/calibracao.md)
LADO_MINIMO = 224
BRILHO_MINIMO = 30.0
BRILHO_MAXIMO = 195.0
NITIDEZ_MINIMA = 2.6
LADO_ANALISE = 512


@dataclass(frozen=True)
class MedidasQualidade:
    menor_lado: int
    brilho: float
    nitidez: float


# Entrada
def validar_tipo(content_type: str | None) -> None:
    if content_type is None or content_type in TIPOS_ACEITOS | TIPOS_GENERICOS:
        return
    raise ErroApi(415, MENSAGEM_FORMATO)


def validar_tamanho(dados: bytes, limite_mb: int) -> None:
    if len(dados) > limite_mb * 1024 * 1024:
        raise ErroApi(413, f"A imagem deve ter no máximo {limite_mb} MB.")


def _erro_dimensoes() -> ErroApi:
    return ErroApi(413, f"A imagem deve ter no máximo {MEGAPIXELS_MAXIMOS} megapixels.")


def abrir_imagem(dados: bytes) -> Image.Image:
    try:
        with Image.open(io.BytesIO(dados)) as original:
            if original.format not in FORMATOS_ACEITOS:
                raise ErroApi(415, MENSAGEM_FORMATO)
            largura, altura = original.size
            if largura * altura > MEGAPIXELS_MAXIMOS * 1_000_000:
                raise _erro_dimensoes()
            original.load()
            orientada = ImageOps.exif_transpose(original).convert("RGB")
    except Image.DecompressionBombError:
        raise _erro_dimensoes() from None
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError):
        raise ErroApi(400, MENSAGEM_ILEGIVEL) from None
    # Cópia só com os pixels, sem EXIF, ICC nem outros metadados
    return Image.fromarray(np.asarray(orientada))


# Qualidade
def variancia_laplaciano(cinza: np.ndarray) -> float:
    if min(cinza.shape) < 3:
        return 0.0
    centro = cinza[1:-1, 1:-1]
    laplaciano = (
        cinza[:-2, 1:-1] + cinza[2:, 1:-1] + cinza[1:-1, :-2] + cinza[1:-1, 2:] - 4.0 * centro
    )
    return float(laplaciano.var())


def medir(imagem: Image.Image) -> MedidasQualidade:
    cinza = imagem.convert("L")
    menor_lado = min(cinza.size)
    if menor_lado > LADO_ANALISE:
        escala = LADO_ANALISE / menor_lado
        novo = (round(cinza.width * escala), round(cinza.height * escala))
        cinza = cinza.resize(novo, Image.Resampling.BOX)
    matriz = np.asarray(cinza, dtype=np.float32)
    return MedidasQualidade(
        menor_lado=menor_lado,
        brilho=float(matriz.mean()),
        nitidez=variancia_laplaciano(matriz),
    )


def motivo_por_medidas(medidas: MedidasQualidade) -> MotivoRecusa | None:
    if medidas.menor_lado < LADO_MINIMO:
        return MotivoRecusa.RESOLUCAO_BAIXA
    if medidas.brilho < BRILHO_MINIMO:
        return MotivoRecusa.IMAGEM_ESCURA
    if medidas.brilho > BRILHO_MAXIMO:
        return MotivoRecusa.IMAGEM_CLARA
    if medidas.nitidez < NITIDEZ_MINIMA:
        return MotivoRecusa.IMAGEM_BORRADA
    return None


def avaliar_qualidade(imagem: Image.Image) -> MotivoRecusa | None:
    return motivo_por_medidas(medir(imagem))
