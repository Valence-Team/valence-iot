import logging
import tempfile

import pytest
from fastapi.testclient import TestClient

from app.main import criar_app
from app.schemas import ClassePrevista, MotivoRecusa
from app.visao import ResultadoClassificacao
from app.visao import classificador as modulo_classificador
from app.visao.carga import carregar_classificador
from tests.conftest import PortaoFalso, montar_config
from tests.test_visao_apoio import (
    RedeMinuscula,
    figura_borrada,
    figura_lisa,
    figura_nitida,
    para_bytes,
    salvar_modelo,
)

ROTA = "/api/v1/visao/classificar"
NITIDA = para_bytes(figura_nitida())


class ClassificadorFixo:
    def __init__(self) -> None:
        self.chamadas = 0

    def classificar(self, imagem, cultura) -> ResultadoClassificacao:
        self.chamadas += 1
        classes = [
            ClassePrevista(rotulo="milho_ferrugem_comum", nome="Ferrugem-comum", confianca=0.8),
            ClassePrevista(
                rotulo="milho_helmintosporiose", nome="Helmintosporiose", confianca=0.15
            ),
            ClassePrevista(rotulo="milho_cercosporiose", nome="Cercosporiose", confianca=0.05),
        ]
        return ResultadoClassificacao(None, cultura, classes)


@pytest.fixture
def componentes_falsos() -> dict[str, object]:
    return {"visao": ClassificadorFixo(), "portao": PortaoFalso()}


@pytest.fixture
def rede_minuscula(monkeypatch):
    monkeypatch.setitem(modulo_classificador.ARQUITETURAS, "rede_minuscula", RedeMinuscula)


@pytest.fixture
def cliente_com_modelo(criar_cliente, tmp_path, rede_minuscula):
    def _criar(por_rotulo: dict[str, float], portao=None) -> TestClient:
        pesos = salvar_modelo(tmp_path, por_rotulo)
        classificador = carregar_classificador(montar_config(modelo_visao_path=pesos))
        return criar_cliente({"visao": classificador, "portao": portao or PortaoFalso()})

    return _criar


def enviar(cliente, imagem=NITIDA, tipo="image/png", cultura="MILHO", nome="folha.png"):
    arquivos = {"imagem": (nome, imagem, tipo)}
    return cliente.post(ROTA, files=arquivos, data={"cultura": cultura})


def assert_formato_erro(resposta, status):
    corpo = resposta.json()
    assert resposta.status_code == status
    assert set(corpo) == {"timestamp", "status", "erro", "mensagem", "caminho", "campos"}
    assert corpo["status"] == status
    assert corpo["caminho"] == ROTA
    return corpo


def assert_recusada(resposta, motivo, cultura_detectada=None):
    assert resposta.status_code == 200
    assert resposta.json() == {
        "imagemValida": False,
        "motivo": motivo,
        "culturaDetectada": cultura_detectada,
        "classes": [],
    }


# Caminho feliz com o modelo minúsculo
def test_caminho_feliz_tres_classes_somando_um_na_cultura(cliente_com_modelo):
    cliente = cliente_com_modelo(
        {"batata_requeima": 4.0, "batata_pinta_preta": 2.0, "batata_saudavel": 0.5}
    )

    resposta = enviar(cliente, cultura="batata")

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["imagemValida"] is True
    assert corpo["motivo"] is None
    assert corpo["culturaDetectada"] == "BATATA"
    assert [c["rotulo"] for c in corpo["classes"]] == [
        "batata_requeima",
        "batata_pinta_preta",
        "batata_saudavel",
    ]
    assert [c["nome"] for c in corpo["classes"]] == ["Requeima", "Pinta-preta", "Folha saudável"]
    assert sum(c["confianca"] for c in corpo["classes"]) == pytest.approx(1.0, abs=1e-3)
    assert all(len(str(c["confianca"]).split(".")[-1]) <= 4 for c in corpo["classes"])


def test_cultura_divergente(cliente_com_modelo):
    cliente = cliente_com_modelo({"milho_ferrugem_comum": 10.0})

    assert_recusada(enviar(cliente, cultura="TOMATE"), "CULTURA_DIVERGENTE", "MILHO")


def test_divergencia_abaixo_do_limite_classifica_na_cultura_informada(cliente_com_modelo):
    cliente = cliente_com_modelo({"milho_ferrugem_comum": 0.3, "tomate_requeima": 0.0})

    corpo = enviar(cliente, cultura="TOMATE").json()

    assert corpo["imagemValida"] is True
    assert corpo["culturaDetectada"] == "MILHO"
    assert corpo["classes"][0]["rotulo"] == "tomate_requeima"
    assert all(c["rotulo"].startswith("tomate_") for c in corpo["classes"])


def test_503_quando_o_arquivo_do_modelo_falta(tmp_path):
    config = montar_config(modelo_visao_path=tmp_path / "visao.pt")
    app = criar_app(config, {"visao": carregar_classificador, "portao": lambda _c: PortaoFalso()})

    with TestClient(app, raise_server_exceptions=False) as cliente:
        corpo = assert_formato_erro(enviar(cliente), 503)
        saude = cliente.get("/health").json()

    assert "modelo de visão" in corpo["mensagem"]
    assert saude["componentes"]["visao"] == "indisponivel"


def test_503_sem_componentes(cliente_sem_modelo):
    corpo = assert_formato_erro(enviar(cliente_sem_modelo), 503)

    assert corpo["erro"] == "Serviço indisponível"


# Camada de qualidade
def test_imagem_lisa_e_escura(cliente, componentes_falsos):
    escura = para_bytes(figura_lisa((12, 14, 10)))

    assert_recusada(enviar(cliente, imagem=escura), "IMAGEM_ESCURA")
    assert componentes_falsos["visao"].chamadas == 0


def test_imagem_borrada_sintetica(cliente, componentes_falsos):
    borrada = para_bytes(figura_borrada())

    assert_recusada(enviar(cliente, imagem=borrada), "IMAGEM_BORRADA")
    assert componentes_falsos["visao"].chamadas == 0


def test_resolucao_baixa(cliente):
    pequena = para_bytes(figura_nitida((200, 300)))

    assert_recusada(enviar(cliente, imagem=pequena), "RESOLUCAO_BAIXA")


# Portão
def test_portao_falso_dizendo_nao_planta(criar_cliente, componentes_falsos):
    componentes_falsos["portao"] = PortaoFalso(MotivoRecusa.NAO_E_PLANTA)

    assert_recusada(enviar(criar_cliente(componentes_falsos)), "NAO_E_PLANTA")
    assert componentes_falsos["visao"].chamadas == 0


# Entrada
@pytest.mark.parametrize(("formato", "tipo"), [("JPEG", "image/jpeg"), ("WEBP", "image/webp")])
def test_aceita_jpeg_e_webp(cliente, formato, tipo):
    imagem = para_bytes(figura_nitida(), formato, quality=95)

    assert enviar(cliente, imagem=imagem, tipo=tipo).status_code == 200


def test_aceita_sem_tipo_declarado(cliente):
    assert enviar(cliente, tipo="application/octet-stream").status_code == 200


def test_400_arquivo_que_nao_e_imagem(cliente):
    corpo = assert_formato_erro(enviar(cliente, imagem=b"isto nao e uma imagem"), 400)

    assert "ler a imagem" in corpo["mensagem"]


def test_400_imagem_truncada(cliente):
    truncada = para_bytes(figura_nitida(), "JPEG")[:2000]

    assert_formato_erro(enviar(cliente, imagem=truncada, tipo="image/jpeg"), 400)


@pytest.mark.parametrize("tipo", ["text/plain", "image/gif", "application/pdf"])
def test_415_tipo_declarado_errado(cliente, tipo):
    corpo = assert_formato_erro(enviar(cliente, tipo=tipo), 415)

    assert corpo["erro"] == "Tipo de mídia não suportado"


@pytest.mark.parametrize("formato", ["GIF", "BMP", "TIFF"])
def test_415_conteudo_real_em_outro_formato(cliente, formato):
    imagem = para_bytes(figura_nitida(), formato)

    assert_formato_erro(enviar(cliente, imagem=imagem, tipo="image/png"), 415)


def test_413_arquivo_grande(cliente):
    grande = b"\x89PNG\r\n\x1a\n" + b"0" * (1024 * 1024 + 10)
    corpo = assert_formato_erro(enviar(cliente, imagem=grande), 413)

    assert "1 MB" in corpo["mensagem"]


def test_413_corpo_muito_acima_do_limite(cliente):
    enorme = b"0" * (3 * 1024 * 1024)

    assert_formato_erro(enviar(cliente, imagem=enorme), 413)


def test_upload_acima_de_1_mb_nao_vai_para_o_disco(criar_cliente, componentes_falsos, monkeypatch):
    def proibido(*args, **kwargs):
        raise AssertionError("upload gravado em disco")

    monkeypatch.setattr(tempfile.SpooledTemporaryFile, "rollover", proibido)
    cliente = criar_cliente(componentes_falsos, tamanho_maximo_mb=4)
    grande_valida = para_bytes(figura_nitida((800, 800)))
    assert len(grande_valida) > 1024 * 1024

    assert enviar(cliente, imagem=grande_valida).status_code == 200


@pytest.mark.parametrize("cultura", ["SOJA", "trigo", "milho verde"])
def test_400_cultura_invalida(cliente, cultura):
    corpo = assert_formato_erro(enviar(cliente, cultura=cultura), 400)

    assert corpo["campos"][0]["campo"] == "cultura"
    assert "MILHO, TOMATE ou BATATA" in corpo["campos"][0]["mensagem"]


def test_400_sem_imagem(cliente):
    corpo = assert_formato_erro(cliente.post(ROTA, data={"cultura": "TOMATE"}), 400)

    assert {"campo": "imagem", "mensagem": "Campo obrigatório."} in corpo["campos"]


def test_400_sem_campos(cliente):
    corpo = assert_formato_erro(cliente.post(ROTA), 400)

    assert {c["campo"] for c in corpo["campos"]} == {"imagem", "cultura"}


# Logs
def test_log_de_latencia_por_camada_sem_conteudo(cliente, caplog):
    caplog.set_level(logging.INFO, logger="valence_ia")

    enviar(cliente, nome="foto-do-sitio-joao.png")

    linhas = [r.getMessage() for r in caplog.records if r.name == "valence_ia.visao"]
    assert len(linhas) == 1
    for campo in ("qualidade_ms=", "portao_ms=", "classificador_ms=", "motivo=-"):
        assert campo in linhas[0]
    todos = "\n".join(r.getMessage() for r in caplog.records)
    assert "foto-do-sitio-joao" not in todos


def test_documentacao_mostra_o_multipart(cliente):
    corpo = cliente.get("/openapi.json").json()["paths"][ROTA]["post"]["requestBody"]

    esquema = corpo["content"]["multipart/form-data"]["schema"]
    assert set(esquema["required"]) == {"imagem", "cultura"}
