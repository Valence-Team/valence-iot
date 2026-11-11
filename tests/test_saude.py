from fastapi.testclient import TestClient

from app.main import criar_app
from tests.conftest import CHAVE_TESTE, montar_config


def test_saude_degradada_sem_componentes(cliente_sem_modelo):
    resposta = cliente_sem_modelo.get("/health")

    assert resposta.status_code == 200
    assert resposta.json() == {
        "status": "degradado",
        "modelo": "indisponivel",
        "componentes": {
            "visao": "indisponivel",
            "portao": "indisponivel",
            "indice": "indisponivel",
            "llm": "indisponivel",
        },
    }


def test_saude_ok_com_componentes_carregados(cliente):
    corpo = cliente.get("/health").json()

    assert corpo["status"] == "ok"
    assert corpo["modelo"] == "carregado"
    assert set(corpo["componentes"].values()) == {"carregado"}


def test_saude_degradada_quando_so_o_llm_falta(criar_cliente, componentes_falsos):
    del componentes_falsos["llm"]
    corpo = criar_cliente(componentes_falsos).get("/health").json()

    assert corpo["status"] == "degradado"
    assert corpo["modelo"] == "carregado"
    assert corpo["componentes"]["llm"] == "indisponivel"


def test_saude_e_publica_mesmo_com_chave_definida(criar_cliente):
    cliente = criar_cliente(ia_api_key=CHAVE_TESTE)

    assert cliente.get("/health").status_code == 200


def test_componente_que_quebra_na_carga_nao_derruba_o_servico():
    def quebra(_config):
        raise RuntimeError("falha inesperada")

    app = criar_app(montar_config(), {"visao": quebra})
    with TestClient(app) as cliente:
        resposta = cliente.get("/health")

    assert resposta.status_code == 200
    assert resposta.json()["componentes"]["visao"] == "indisponivel"
