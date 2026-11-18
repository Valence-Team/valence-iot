import json
from pathlib import Path

from app.rag.fichas import ler_fichas
from app.rag.guardrails import EXPLICACAO_FIXA
from app.rotulos import carregar_rotulos
from scripts.avaliar_llm import checagens, em_portugues
from scripts.avaliar_rag import ranking_de_fichas, resumo
from tests.test_rag_apoio import RESPOSTA_BOA, TRECHOS_PEQUENOS

DADOS = Path(__file__).resolve().parent.parent / "dados" / "avaliacao"


# Conjuntos de avaliação
def test_consultas_rag_sao_40_com_10_fora_do_modelo():
    consultas = json.loads((DADOS / "consultas_rag.json").read_text(encoding="utf-8"))
    fichas = {f.id: f for f in ler_fichas()}
    rotulos = carregar_rotulos()

    assert len(consultas) == 40
    assert len({c["id"] for c in consultas}) == 40
    assert sum(c["foraDoModelo"] for c in consultas) == 10
    assert any(c["classes"] for c in consultas) and any(not c["classes"] for c in consultas)
    for consulta in consultas:
        ficha = fichas[consulta["fichaEsperada"]]
        assert consulta["cultura"] in ficha.culturas
        assert consulta["foraDoModelo"] == (not ficha.rotulos)
        assert all(rotulos[r].cultura == consulta["cultura"] for r in consulta["classes"])


def test_casos_llm_sao_12_com_dados_pessoais_e_injecao():
    casos = json.loads((DADOS / "casos_llm.json").read_text(encoding="utf-8"))

    assert len(casos) == 12
    assert sum(c["tipo"] == "dados_pessoais" for c in casos) == 2
    assert sum(c["tipo"] == "injecao" for c in casos) == 2
    for caso in casos:
        assert all(dado in caso["sintomas"] for dado in caso["dadosPessoais"])
        assert bool(caso["dadosPessoais"]) == (caso["tipo"] == "dados_pessoais")


# Métricas de recuperação
def test_ranking_de_fichas_remove_repetidas():
    pares = [(TRECHOS_PEQUENOS[0], 0.9), (TRECHOS_PEQUENOS[0], 0.8), (TRECHOS_PEQUENOS[1], 0.7)]

    assert ranking_de_fichas(pares) == ["milho-ferrugem", "milho-cercosporiose"]


def test_hit_e_mrr():
    linhas = [
        {"posicao": 1, "foraDoModelo": False, "comClasses": True},
        {"posicao": 2, "foraDoModelo": True, "comClasses": False},
        {"posicao": 4, "foraDoModelo": True, "comClasses": False},
    ]

    geral = resumo(linhas)["geral"]

    assert geral == {"consultas": 3, "hit@1": 0.3333, "hit@3": 0.6667, "mrr": 0.5833}
    assert resumo(linhas)["pragasForaDoModelo"]["hit@1"] == 0.0


# Checagens automáticas do LLM
def test_checagens_de_resposta_boa():
    resultado = checagens(RESPOSTA_BOA, 2, "prompt sem dados", ["joao@exemplo.com"])

    assert all(resultado.values())


def test_checagens_pegam_problemas():
    texto = "You should apply 2 L/ha of product. " * 30
    resultado = checagens(texto, 2, "email joao@exemplo.com no prompt", ["joao@exemplo.com"])

    assert resultado["portugues"] is False
    assert resultado["ate120Palavras"] is False
    assert resultado["citaFonte"] is False
    assert resultado["semDoseNemProduto"] is False
    assert resultado["mencionaAgronomo"] is False
    assert resultado["dadoPessoalAusenteDoPrompt"] is False


def test_explicacao_fixa_nao_conta_como_gerada():
    resultado = checagens(EXPLICACAO_FIXA, 0, "", [])

    assert resultado["explicacaoGerada"] is False
    assert resultado["citaFonte"] is None
    assert resultado["mencionaAgronomo"] is True
    assert em_portugues(EXPLICACAO_FIXA)
