import logging

from app.rotulos import carregar_rotulos
from app.schemas import Cultura
from tests.conftest import gerar_imagem


class ClassificadorQuebrado:
    def classificar(self, imagem, cultura):
        raise RuntimeError("falha interna com dado sensível")


# Formato de erro
def test_404_no_formato_padrao(cliente):
    resposta = cliente.get("/rota/inexistente")

    assert resposta.status_code == 404
    corpo = resposta.json()
    assert corpo["erro"] == "Não encontrado"
    assert corpo["mensagem"] == "Recurso não encontrado."
    assert corpo["caminho"] == "/rota/inexistente"
    assert corpo["timestamp"].endswith("Z")


def test_500_no_formato_padrao_sem_vazar_detalhes(criar_cliente, componentes_falsos):
    componentes_falsos["visao"] = ClassificadorQuebrado()
    resposta = criar_cliente(componentes_falsos).post(
        "/api/v1/visao/classificar",
        files={"imagem": ("f.png", gerar_imagem(), "image/png")},
        data={"cultura": "MILHO"},
    )

    assert resposta.status_code == 500
    corpo = resposta.json()
    assert corpo["erro"] == "Erro interno"
    assert "sensível" not in corpo["mensagem"]


# Logs
def test_log_tem_id_rota_status_e_duracao_sem_dados(cliente, caplog):
    caplog.set_level(logging.INFO, logger="valence_ia")
    sintomas = "Manchas na folha perto do sítio do vizinho"

    resposta = cliente.post(
        "/api/v1/rag/consultar",
        json={"cultura": "MILHO", "sintomas": sintomas},
        headers={"X-API-Key": "segredo-no-cabecalho"},
    )

    linhas = [r.getMessage() for r in caplog.records if r.name == "valence_ia.requisicoes"]
    assert len(linhas) == 1
    linha = linhas[0]
    assert f"id={resposta.headers['X-Request-ID']}" in linha
    assert "rota=/api/v1/rag/consultar" in linha
    assert "status=200" in linha
    assert "duracao_ms=" in linha
    todos = "\n".join(r.getMessage() for r in caplog.records)
    assert sintomas not in todos
    assert "segredo-no-cabecalho" not in todos


# Rótulos
def test_rotulos_tem_17_classes_das_tres_culturas():
    rotulos = carregar_rotulos()

    assert len(rotulos) == 17
    por_cultura = {c: [r for r in rotulos.values() if r.cultura == c] for c in Cultura}
    assert {c: len(lista) for c, lista in por_cultura.items()} == {
        Cultura.MILHO: 4,
        Cultura.TOMATE: 10,
        Cultura.BATATA: 3,
    }
    for rotulo in rotulos.values():
        assert rotulo.rotulo.startswith(rotulo.cultura.lower() + "_")
        assert rotulo.saudavel == rotulo.rotulo.endswith("_saudavel")
        assert (rotulo.nome_cientifico is None) == rotulo.saudavel
    assert len({r.classe_plant_village for r in rotulos.values()}) == 17
