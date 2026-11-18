import pytest

from app.seguranca import mascarar_dados_pessoais
from tests.conftest import CHAVE_TESTE, gerar_imagem

CONSULTA = {"cultura": "BATATA", "sintomas": "Manchas escuras nas folhas."}


@pytest.fixture
def cliente_com_chave(criar_cliente, componentes_falsos):
    return criar_cliente(componentes_falsos, ia_api_key=CHAVE_TESTE)


# Autenticação por chave
@pytest.mark.parametrize("cabecalhos", [{}, {"X-API-Key": "errada"}, {"X-API-Key": ""}])
def test_401_sem_chave_ou_com_chave_errada(cliente_com_chave, cabecalhos):
    resposta = cliente_com_chave.post("/api/v1/rag/consultar", json=CONSULTA, headers=cabecalhos)

    assert resposta.status_code == 401
    corpo = resposta.json()
    assert corpo["erro"] == "Não autorizado"
    assert corpo["mensagem"] == "Credencial ausente ou inválida."
    assert corpo["campos"] == []


def test_401_na_visao_antes_de_validar_a_entrada(cliente_com_chave):
    resposta = cliente_com_chave.post(
        "/api/v1/visao/classificar",
        files={"imagem": ("f.png", gerar_imagem(), "image/png")},
        data={"cultura": "SOJA"},
    )

    assert resposta.status_code == 401


def test_200_com_chave_correta(cliente_com_chave):
    resposta = cliente_com_chave.post(
        "/api/v1/rag/consultar", json=CONSULTA, headers={"X-API-Key": CHAVE_TESTE}
    )

    assert resposta.status_code == 200


def test_sem_chave_configurada_nao_ha_checagem(cliente):
    assert cliente.post("/api/v1/rag/consultar", json=CONSULTA).status_code == 200


# Mascaramento de dados pessoais
@pytest.mark.parametrize(
    "dado",
    [
        "maria.silva@exemplo.com.br",
        "(11) 98765-4321",
        "11987654321",
        "+55 61 3333-4444",
        "3333-4444",
        "123.456.789-09",
        "12345678909",
        "01310-100",
        "70.040-010",
        "-23.550520, -46.633308",
        "-15,7801 -47,9292",
        "-23.5505",
    ],
)
def test_mascara_dado_pessoal(dado):
    texto = f"Minha lavoura, contato {dado}, está com manchas."

    mascarado = mascarar_dados_pessoais(texto)

    assert dado not in mascarado
    assert "[removido]" in mascarado
    assert mascarado.startswith("Minha lavoura, contato ")
    assert mascarado.endswith(", está com manchas.")


@pytest.mark.parametrize(
    "texto",
    [
        "Pústulas marrons há 3 dias em 20% das plantas.",
        "Apliquei 2,5 L por hectare em 2026.",
        "Folhas com manchas de 0.5 cm e halo amarelo.",
    ],
)
def test_preserva_texto_sem_dado_pessoal(texto):
    assert mascarar_dados_pessoais(texto) == texto


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("Sou o José da Silva, meu tomate tem mancha.", "Sou o [removido], meu tomate tem mancha."),
        ("Meu nome é Maria Aparecida e o milho secou.", "Meu nome é [removido] e o milho secou."),
        ("Bom dia, me chamo Antônio. Folha com pó.", "Bom dia, me chamo [removido]. Folha com pó."),
        ("Aqui é a Ana dos Santos, batata murcha.", "Aqui é a [removido], batata murcha."),
    ],
)
def test_mascara_nome_de_quem_se_identifica(texto, esperado):
    assert mascarar_dados_pessoais(texto) == esperado


@pytest.mark.parametrize(
    "texto",
    [
        "Sou produtor de Goiás e a folha amarelou.",
        "Sou de Minas, o tomate tem mancha.",
        "A Embrapa recomenda rotação de culturas.",
    ],
)
def test_nao_mascara_texto_sem_nome_de_pessoa(texto):
    assert mascarar_dados_pessoais(texto) == texto
