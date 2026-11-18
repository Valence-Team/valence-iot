import pytest

from tests.conftest import LlmFalso

ROTA = "/api/v1/rag/consultar"
CONSULTA = {
    "cultura": "milho",
    "sintomas": "Pústulas marrons nas duas faces da folha.",
    "classes": ["milho_ferrugem_comum"],
}


def test_503_sem_indice(cliente_sem_modelo):
    resposta = cliente_sem_modelo.post(ROTA, json=CONSULTA)

    assert resposta.status_code == 503
    assert resposta.json()["erro"] == "Serviço indisponível"


def test_consulta_com_componentes_carregados(cliente):
    resposta = cliente.post(ROTA, json=CONSULTA)

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert set(corpo) == {"trechos", "explicacao", "modeloLlm"}
    assert set(corpo["trechos"][0]) == {"titulo", "texto", "fonte", "url", "score"}
    assert corpo["explicacao"] == "Explicação de teste."
    assert corpo["modeloLlm"] == "modelo-falso"


def test_classes_e_opcional(cliente):
    consulta = {"cultura": "TOMATE", "sintomas": "Folhas amareladas."}

    assert cliente.post(ROTA, json=consulta).status_code == 200


@pytest.mark.parametrize("ausente", ["sem_llm", "llm_falha"])
def test_explicacao_nula_quando_o_llm_falha(criar_cliente, componentes_falsos, ausente):
    if ausente == "sem_llm":
        del componentes_falsos["llm"]
    else:
        componentes_falsos["llm"] = LlmFalso(falhar=True)
    resposta = criar_cliente(componentes_falsos).post(ROTA, json=CONSULTA)

    assert resposta.status_code == 200
    assert resposta.json()["explicacao"] is None
    assert resposta.json()["modeloLlm"] is None
    assert len(resposta.json()["trechos"]) == 1


def test_400_cultura_invalida(cliente):
    resposta = cliente.post(ROTA, json={**CONSULTA, "cultura": "SOJA"})

    assert resposta.status_code == 400
    campo = resposta.json()["campos"][0]
    assert campo["campo"] == "cultura"
    assert campo["mensagem"] == "Valor inválido. Use MILHO, TOMATE ou BATATA."


def test_400_sintomas_acima_de_1000_caracteres(cliente):
    resposta = cliente.post(ROTA, json={**CONSULTA, "sintomas": "a" * 1001})

    assert resposta.status_code == 400
    assert resposta.json()["campos"] == [
        {"campo": "sintomas", "mensagem": "Deve ter no máximo 1000 caracteres."}
    ]


def test_400_mais_de_3_classes(cliente):
    classes = ["milho_cercosporiose", "milho_ferrugem_comum", "milho_saudavel", "milho_x"]
    resposta = cliente.post(ROTA, json={**CONSULTA, "classes": classes})

    assert resposta.status_code == 400
    assert resposta.json()["campos"][0]["mensagem"] == "Deve ter no máximo 3 itens."


def test_400_rotulo_desconhecido(cliente):
    resposta = cliente.post(ROTA, json={**CONSULTA, "classes": ["milho_inexistente"]})

    assert resposta.status_code == 400
    assert resposta.json()["campos"][0]["campo"] == "classes"


def test_422_classe_de_outra_cultura(cliente):
    resposta = cliente.post(ROTA, json={**CONSULTA, "classes": ["tomate_requeima"]})

    assert resposta.status_code == 422
    assert resposta.json()["erro"] == "Regra de negócio violada"


def test_400_json_malformado(cliente):
    resposta = cliente.post(
        ROTA, content=b"{cultura:", headers={"Content-Type": "application/json"}
    )

    assert resposta.status_code == 400
    assert resposta.json()["mensagem"] == "Um ou mais campos são inválidos."


def test_sintomas_chegam_mascarados_ao_indice_e_ao_llm(cliente, componentes_falsos):
    sintomas = "Manchas desde ontem. Falar com joao@exemplo.com ou (11) 98765-4321."
    cliente.post(ROTA, json={**CONSULTA, "sintomas": sintomas})

    consulta_indice = componentes_falsos["indice"].consultas[0]
    sintomas_llm = componentes_falsos["llm"].sintomas_recebidos[0]
    for texto in (consulta_indice, sintomas_llm):
        assert "joao@exemplo.com" not in texto
        assert "98765-4321" not in texto
        assert texto.count("[removido]") == 2
