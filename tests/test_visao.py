import pytest

from app.schemas import MotivoRecusa
from tests.conftest import PortaoFalso, gerar_imagem

ROTA = "/api/v1/visao/classificar"


def enviar(cliente, imagem=None, tipo="image/png", cultura="MILHO", nome="folha.png"):
    arquivos = {"imagem": (nome, imagem if imagem is not None else gerar_imagem(), tipo)}
    return cliente.post(ROTA, files=arquivos, data={"cultura": cultura})


def assert_formato_erro(resposta, status):
    corpo = resposta.json()
    assert resposta.status_code == status
    assert set(corpo) == {"timestamp", "status", "erro", "mensagem", "caminho", "campos"}
    assert corpo["status"] == status
    assert corpo["caminho"] == ROTA
    return corpo


def test_503_sem_modelo_carregado(cliente_sem_modelo):
    corpo = assert_formato_erro(enviar(cliente_sem_modelo), 503)

    assert corpo["erro"] == "Serviço indisponível"
    assert "modelo de visão" in corpo["mensagem"]


def test_classifica_com_componentes_carregados(cliente):
    resposta = enviar(cliente, cultura="milho")

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["imagemValida"] is True
    assert corpo["motivo"] is None
    assert corpo["culturaDetectada"] == "MILHO"
    assert len(corpo["classes"]) == 3
    assert set(corpo["classes"][0]) == {"rotulo", "nome", "confianca"}
    assert all(c["rotulo"].startswith("milho_") for c in corpo["classes"])


@pytest.mark.parametrize(("formato", "tipo"), [("JPEG", "image/jpeg"), ("WEBP", "image/webp")])
def test_aceita_jpeg_e_webp(cliente, formato, tipo):
    resposta = enviar(cliente, imagem=gerar_imagem(formato), tipo=tipo)

    assert resposta.status_code == 200


def test_foto_recusada_pelo_portao(criar_cliente, componentes_falsos):
    componentes_falsos["portao"] = PortaoFalso(MotivoRecusa.IMAGEM_BORRADA)
    resposta = enviar(criar_cliente(componentes_falsos))

    assert resposta.status_code == 200
    assert resposta.json() == {
        "imagemValida": False,
        "motivo": "IMAGEM_BORRADA",
        "culturaDetectada": None,
        "classes": [],
    }


def test_413_acima_do_tamanho_maximo(cliente_sem_modelo):
    grande = b"\x89PNG\r\n\x1a\n" + b"0" * (1024 * 1024 + 10)
    corpo = assert_formato_erro(enviar(cliente_sem_modelo, imagem=grande), 413)

    assert "1 MB" in corpo["mensagem"]


@pytest.mark.parametrize("tipo", ["text/plain", "image/gif", "application/pdf"])
def test_415_tipo_nao_suportado(cliente_sem_modelo, tipo):
    corpo = assert_formato_erro(enviar(cliente_sem_modelo, tipo=tipo), 415)

    assert corpo["erro"] == "Tipo de mídia não suportado"


def test_415_quando_o_conteudo_real_nao_e_aceito(cliente_sem_modelo):
    gif = gerar_imagem("GIF")

    assert_formato_erro(enviar(cliente_sem_modelo, imagem=gif, tipo="image/png"), 415)


def test_400_imagem_ilegivel(cliente_sem_modelo):
    corpo = assert_formato_erro(enviar(cliente_sem_modelo, imagem=b"nao e imagem"), 400)

    assert "ler a imagem" in corpo["mensagem"]


@pytest.mark.parametrize("cultura", ["SOJA", "trigo", "milho verde"])
def test_400_cultura_invalida(cliente_sem_modelo, cultura):
    corpo = assert_formato_erro(enviar(cliente_sem_modelo, cultura=cultura), 400)

    assert corpo["campos"][0]["campo"] == "cultura"
    assert "MILHO, TOMATE ou BATATA" in corpo["campos"][0]["mensagem"]


def test_400_sem_imagem(cliente_sem_modelo):
    resposta = cliente_sem_modelo.post(ROTA, data={"cultura": "TOMATE"})
    corpo = assert_formato_erro(resposta, 400)

    assert {"campo": "imagem", "mensagem": "Campo obrigatório."} in corpo["campos"]
