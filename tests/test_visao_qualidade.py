import numpy as np
import pytest
from PIL import Image

from app.erros import ErroApi
from app.schemas import MotivoRecusa
from app.visao import qualidade
from app.visao.qualidade import abrir_imagem, avaliar_qualidade, medir, variancia_laplaciano
from tests.test_visao_apoio import figura_borrada, figura_lisa, figura_nitida, para_bytes


# Abertura da imagem
def test_aplica_orientacao_exif_e_descarta_metadados():
    original = figura_nitida((300, 240))
    exif = Image.Exif()
    exif[0x0112] = 6
    exif[0x010F] = "Fabricante"
    dados = para_bytes(original, "JPEG", exif=exif.tobytes(), quality=95)

    aberta = abrir_imagem(dados)

    assert aberta.size == (240, 300)
    assert aberta.mode == "RGB"
    assert aberta.info == {}
    assert len(aberta.getexif()) == 0


@pytest.mark.parametrize("formato", ["PNG", "JPEG", "WEBP"])
def test_abre_formatos_aceitos(formato):
    assert abrir_imagem(para_bytes(figura_nitida(), formato)).size == (256, 256)


def test_converte_png_com_transparencia_para_rgb():
    rgba = figura_nitida().convert("RGBA")

    assert abrir_imagem(para_bytes(rgba)).mode == "RGB"


@pytest.mark.parametrize("dados", [b"", b"texto qualquer", b"\x89PNG\r\n\x1a\nquebrado"])
def test_400_quando_nao_abre(dados):
    with pytest.raises(ErroApi) as erro:
        abrir_imagem(dados)

    assert erro.value.status == 400


def test_415_formato_fora_da_lista():
    with pytest.raises(ErroApi) as erro:
        abrir_imagem(para_bytes(figura_nitida(), "GIF"))

    assert erro.value.status == 415


def test_413_dimensoes_acima_do_limite(monkeypatch):
    monkeypatch.setattr(qualidade, "MEGAPIXELS_MAXIMOS", 0.01)

    with pytest.raises(ErroApi) as erro:
        abrir_imagem(para_bytes(figura_nitida()))

    assert erro.value.status == 413


# Medidas e motivos
def test_variancia_laplaciano_de_imagem_lisa_e_zero():
    cinza = np.asarray(figura_lisa((90, 90, 90)).convert("L"), dtype=np.float32)

    assert variancia_laplaciano(cinza) == 0.0


def test_borrar_reduz_a_nitidez():
    assert medir(figura_borrada()).nitidez < medir(figura_nitida()).nitidez / 10


def test_medidas_de_imagem_grande_usam_versao_reduzida():
    medidas = medir(figura_nitida((1600, 1200)))

    assert medidas.menor_lado == 1200
    assert medidas.nitidez > qualidade.NITIDEZ_MINIMA


@pytest.mark.parametrize(
    ("figura", "motivo"),
    [
        (figura_nitida(), None),
        (figura_nitida((223, 400)), MotivoRecusa.RESOLUCAO_BAIXA),
        (figura_lisa((10, 12, 8)), MotivoRecusa.IMAGEM_ESCURA),
        (figura_lisa((250, 250, 245)), MotivoRecusa.IMAGEM_CLARA),
        (figura_lisa((60, 140, 70)), MotivoRecusa.IMAGEM_BORRADA),
        (figura_borrada(), MotivoRecusa.IMAGEM_BORRADA),
    ],
)
def test_motivo_por_tipo_de_imagem(figura, motivo):
    assert avaliar_qualidade(figura) == motivo


def test_resolucao_e_checada_antes_do_brilho():
    assert avaliar_qualidade(figura_lisa((5, 5, 5), (100, 100))) == MotivoRecusa.RESOLUCAO_BAIXA
