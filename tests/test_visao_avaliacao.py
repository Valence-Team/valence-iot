from collections import Counter
from pathlib import Path

import pytest

from app.visao.qualidade import avaliar_qualidade
from scripts.avaliar_portao import (
    ACEITA,
    Conjunto,
    Resultado,
    borrar,
    escurecer,
    ler_argumentos,
    montar_conjuntos,
    resumo_conjunto,
    resumo_por_motivo,
)
from tests.test_visao_apoio import figura_nitida


def resultado(esperado: str, **contagem: int) -> Resultado:
    return Resultado(Conjunto(esperado.lower(), esperado, Path(".")), contagem=Counter(contagem))


# Métricas por motivo
def test_rejeicao_correta_e_falsa_rejeicao_por_motivo():
    resultados = [
        resultado(ACEITA, ACEITA=8, IMAGEM_BORRADA=1, CULTURA_FORA_DO_ESCOPO=1),
        resultado("NAO_E_PLANTA", NAO_E_PLANTA=9, ACEITA=1),
        resultado("CULTURA_FORA_DO_ESCOPO", CULTURA_FORA_DO_ESCOPO=2, NAO_E_PLANTA=1, ACEITA=1),
    ]

    geral = resumo_por_motivo(resultados)

    assert geral["imagensQueDevemPassar"] == 10
    assert geral["taxaAceitacaoCorreta"] == 0.8
    nao_planta = geral["porMotivo"]["NAO_E_PLANTA"]
    assert nao_planta["rejeicaoCorreta"] == 0.9
    assert nao_planta["aceitaIndevidamente"] == 0.1
    assert nao_planta["falsaRejeicao"] == 0.0
    fora = geral["porMotivo"]["CULTURA_FORA_DO_ESCOPO"]
    assert fora["rejeicaoCorreta"] == 0.5
    assert fora["rejeicaoPorOutroMotivo"] == 0.25
    assert fora["falsaRejeicao"] == 0.1
    assert geral["porMotivo"]["IMAGEM_BORRADA"]["imagensEsperadas"] == 0
    assert geral["porMotivo"]["IMAGEM_BORRADA"]["rejeicaoCorreta"] is None
    assert geral["porMotivo"]["IMAGEM_BORRADA"]["falsaRejeicao"] == 0.1
    assert "CULTURA_DIVERGENTE" not in geral["porMotivo"]


def test_resumo_de_conjunto_vazio_nao_divide_por_zero():
    resumo = resumo_conjunto(resultado(ACEITA))

    assert resumo["avaliadas"] == 0
    assert resumo["taxaAcerto"] is None


# Conjuntos e degradações
def test_degradar_gera_versoes_borrada_e_escurecida(tmp_path):
    args = ler_argumentos(
        ["--aceitas", f"pv={tmp_path}", "--nao-planta", f"in={tmp_path}", "--degradar", "pv"]
    )

    conjuntos = {c.nome: c.esperado for c in montar_conjuntos(args)}

    assert conjuntos == {
        "pv": ACEITA,
        "in": "NAO_E_PLANTA",
        "pv_borrada": "IMAGEM_BORRADA",
        "pv_escurecida": "IMAGEM_ESCURA",
    }


def test_degradar_so_aceita_conjunto_que_deve_passar(tmp_path):
    args = ler_argumentos(["--nao-planta", f"in={tmp_path}", "--degradar", "in"])

    with pytest.raises(SystemExit):
        montar_conjuntos(args)


def test_degradacoes_caem_no_motivo_esperado():
    folha = figura_nitida((512, 512))

    assert avaliar_qualidade(folha) is None
    assert avaliar_qualidade(borrar(folha)).value == "IMAGEM_BORRADA"
    assert avaliar_qualidade(escurecer(folha)).value == "IMAGEM_ESCURA"
