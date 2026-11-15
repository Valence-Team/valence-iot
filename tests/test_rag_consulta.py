import pytest

from app.rag.guardrails import EXPLICACAO_FIXA
from tests.test_rag_apoio import RESPOSTA_BOA, cliente_llm, erro_429, erro_500, indice_pequeno

ROTA = "/api/v1/rag/consultar"
CONSULTA = {
    "cultura": "milho",
    "sintomas": "Pústulas cor de ferrugem nas duas faces da folha.",
    "classes": ["milho_ferrugem_comum"],
}


@pytest.fixture
def montar(criar_cliente):
    def _montar(*respostas, minimo=0.2):
        llm, falsos = cliente_llm(*respostas)
        indice = indice_pequeno(minimo)
        return criar_cliente({"indice": indice, "llm": llm}), falsos, indice

    return _montar


def texto_enviado(falso) -> str:
    return "\n".join(m["content"] for m in falso.pedidos[0]["messages"])


# Caminho feliz com índice pequeno
def test_consulta_com_indice_e_llm(montar):
    cliente, (principal,), _ = montar(RESPOSTA_BOA)

    corpo = cliente.post(ROTA, json=CONSULTA).json()

    assert corpo["trechos"][0]["titulo"] == "Milho ferrugem"
    assert len(corpo["trechos"]) <= 4
    assert corpo["explicacao"] == RESPOSTA_BOA
    assert corpo["modeloLlm"] == "modelo-principal"
    assert "[1] Milho ferrugem" in texto_enviado(principal)


def test_consulta_leva_cultura_nomes_das_classes_e_sintomas_ao_indice(montar, monkeypatch):
    cliente, _, indice = montar(RESPOSTA_BOA, minimo=-1)
    chamadas = []
    buscar = indice.buscar
    monkeypatch.setattr(indice, "buscar", lambda *args: chamadas.append(args) or buscar(*args))

    cliente.post(ROTA, json={**CONSULTA, "classes": ["milho_cercosporiose"]})

    consulta, cultura, k, rotulos = chamadas[0]
    assert consulta == "milho Cercosporiose " + CONSULTA["sintomas"]
    assert cultura == "MILHO"
    assert k == 4
    assert rotulos == ["milho_cercosporiose"]


# Sem trecho relevante
def test_sem_trecho_relevante_devolve_explicacao_fixa_sem_chamar_o_llm(montar):
    cliente, (principal,), _ = montar(RESPOSTA_BOA, minimo=0.99)

    resposta = cliente.post(ROTA, json={**CONSULTA, "sintomas": "quero vender minha safra"})

    assert resposta.status_code == 200
    assert resposta.json() == {"trechos": [], "explicacao": EXPLICACAO_FIXA, "modeloLlm": None}
    assert "agrônomo" in EXPLICACAO_FIXA
    assert principal.pedidos == []


# Falhas do LLM
def test_principal_falha_e_reserva_responde(montar):
    cliente, (principal, reserva), _ = montar(erro_429(), RESPOSTA_BOA)

    corpo = cliente.post(ROTA, json=CONSULTA).json()

    assert corpo["modeloLlm"] == "modelo-reserva"
    assert len(principal.pedidos) == len(reserva.pedidos) == 1


def test_os_dois_falhando_responde_200_sem_explicacao(montar):
    cliente, _, _ = montar(erro_500(), erro_429())

    resposta = cliente.post(ROTA, json=CONSULTA)

    assert resposta.status_code == 200
    assert resposta.json()["explicacao"] is None
    assert resposta.json()["modeloLlm"] is None
    assert resposta.json()["trechos"]


def test_guardrail_troca_resposta_com_dose_pela_fixa(montar):
    cliente, _, _ = montar("Aplique 300 ml/ha do produto [1]. Procure o agrônomo.")

    corpo = cliente.post(ROTA, json=CONSULTA).json()

    assert corpo["explicacao"] == EXPLICACAO_FIXA
    assert corpo["modeloLlm"] is None
    assert corpo["trechos"]


# Dados pessoais
def test_dados_pessoais_mascarados_antes_do_prompt(montar):
    cliente, (principal,), indice = montar(RESPOSTA_BOA)
    sintomas = (
        "Ferrugem na folha. Meu email é joao.silva@exemplo.com, telefone (11) 98765-4321, "
        "CPF 123.456.789-09, sítio em -15.7801, -47.9292."
    )

    cliente.post(ROTA, json={**CONSULTA, "sintomas": sintomas})

    enviado = texto_enviado(principal)
    consultas_ao_indice = " ".join(t for _, textos in indice.codificador.chamadas for t in textos)
    for dado in ("joao.silva@exemplo.com", "98765-4321", "123.456.789-09", "-47.9292"):
        assert dado not in enviado
        assert dado not in consultas_ao_indice
    assert enviado.count("[removido]") >= 4


def test_mascara_tambem_fora_da_rota():
    from app.rag.consulta import consultar
    from app.rotulos import carregar_rotulos
    from app.schemas import Cultura

    llm, (principal,) = cliente_llm(RESPOSTA_BOA)
    classes = [carregar_rotulos()["milho_ferrugem_comum"]]

    consultar(Cultura.MILHO, "ferrugem, ligue 61 99999-8888", classes, indice_pequeno(), llm)

    assert "99999-8888" not in texto_enviado(principal)
