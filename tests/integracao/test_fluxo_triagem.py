from pathlib import Path

import pytest

from app.config import Configuracao
from tests.integracao.fluxo_triagem import FOTO_PADRAO, criar_cliente, executar_fluxo

CONFIG = Configuracao()
FALTANDO = [
    caminho
    for caminho in (
        CONFIG.modelo_visao_path,
        CONFIG.modelo_visao_path.with_suffix(".json"),
        CONFIG.indice_path / "trechos.json",
        FOTO_PADRAO,
    )
    if not Path(caminho).exists()
]

pytestmark = [
    pytest.mark.integracao,
    pytest.mark.skipif(bool(FALTANDO), reason=f"arquivos ausentes: {FALTANDO}"),
]


@pytest.fixture(scope="module")
def cliente_sem_llm():
    with criar_cliente(sem_llm=True) as cliente:
        yield cliente


def test_foto_de_teste_vira_classes_que_alimentam_o_rag(cliente_sem_llm):
    fluxo = executar_fluxo(cliente_sem_llm, FOTO_PADRAO, "TOMATE", "Mancha grande molhada.")

    visao, rag = fluxo["visao"], fluxo["rag"]
    assert visao["status"] == 200
    assert visao["resposta"]["imagemValida"] is True
    assert visao["resposta"]["culturaDetectada"] == "TOMATE"
    assert len(visao["resposta"]["classes"]) == 3
    assert rag["requisicao"]["json"]["classes"] == [
        c["rotulo"] for c in visao["resposta"]["classes"]
    ]
    assert rag["status"] == 200
    assert rag["resposta"]["trechos"]


def test_llm_desligado_responde_200_sem_explicacao(cliente_sem_llm):
    fluxo = executar_fluxo(cliente_sem_llm, FOTO_PADRAO, "TOMATE", "Mancha grande molhada.")

    assert fluxo["saude"]["componentes"]["llm"] == "indisponivel"
    assert fluxo["rag"]["resposta"]["explicacao"] is None
    assert fluxo["rag"]["resposta"]["modeloLlm"] is None
    assert set(fluxo["rag"]["resposta"]) == {"trechos", "explicacao", "modeloLlm"}
