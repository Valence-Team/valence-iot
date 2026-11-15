from fastapi.testclient import TestClient

from app.componentes import Componentes
from app.demo import (
    MENSAGENS_MOTIVO,
    confiancas,
    executar_triagem,
    respostas_api,
    texto_explicacao,
    texto_trechos,
    texto_validade,
)
from app.main import criar_app
from app.rag import Explicacao
from app.rotulos import carregar_rotulos
from app.schemas import ClassePrevista, Cultura, MotivoRecusa
from app.visao import ResultadoClassificacao
from tests.conftest import IndiceFalso, LlmFalso, PortaoFalso, indisponivel, montar_config
from tests.test_visao_apoio import figura_lisa, figura_nitida, para_bytes

ROTULOS = carregar_rotulos()


class ClassificadorFixo:
    def classificar(self, imagem, cultura) -> ResultadoClassificacao:
        classes = [
            ClassePrevista(rotulo="tomate_requeima", nome="Requeima", confianca=0.9),
            ClassePrevista(rotulo="tomate_pinta_preta", nome="Pinta-preta", confianca=0.07),
            ClassePrevista(rotulo="tomate_septoriose", nome="Septoriose", confianca=0.03),
        ]
        return ResultadoClassificacao(None, cultura, classes)


def componentes(**ajustes) -> Componentes:
    base = {
        "visao": ClassificadorFixo(),
        "portao": PortaoFalso(),
        "indice": IndiceFalso(),
        "llm": LlmFalso(),
    }
    return Componentes(**{**base, **ajustes})


def triar(comp: Componentes, dados: bytes | None, sintomas="mancha molhada"):
    return executar_triagem(comp, ROTULOS, dados, Cultura.TOMATE, sintomas, 8)


def test_foto_valida_leva_as_classes_ao_rag():
    comp = componentes()

    resultado = triar(comp, para_bytes(figura_nitida()))

    assert resultado.visao.imagem_valida is True
    assert "Requeima" in comp.indice.consultas[0]
    assert confiancas(resultado) == {"Requeima": 0.9, "Pinta-preta": 0.07, "Septoriose": 0.03}
    assert texto_validade(resultado).startswith("**Foto válida.**")
    assert "[Embrapa](https://www.embrapa.br/)" in texto_trechos(resultado)
    assert texto_explicacao(resultado) == ("Explicação de teste.", "modelo-falso")


def test_foto_recusada_segue_sem_classes():
    comp = componentes()

    resultado = triar(comp, para_bytes(figura_lisa((10, 12, 8))))

    assert resultado.visao.motivo == MotivoRecusa.IMAGEM_ESCURA
    assert "Requeima" not in comp.indice.consultas[0]
    assert MENSAGENS_MOTIVO[MotivoRecusa.IMAGEM_ESCURA] in texto_validade(resultado)
    assert confiancas(resultado) == {}


def test_sem_modelo_de_visao_mostra_503_e_consulta_o_rag():
    resultado = triar(componentes(visao=None), para_bytes(figura_nitida()))

    assert resultado.erro_visao.startswith("503")
    assert resultado.rag is not None


def test_sem_llm_mostra_explicacao_nula():
    resultado = triar(componentes(llm=None), None)

    assert texto_explicacao(resultado)[0].startswith("Os dois LLMs falharam")


def test_texto_fixo_e_identificado():
    class LlmFixo:
        def explicar(self, *args):
            return Explicacao("texto fixo", None, "DOSE")

    resultado = triar(componentes(llm=LlmFixo()), None)

    assert texto_explicacao(resultado)[1].startswith("texto fixo")


def test_json_da_api_em_camel_case():
    resultado = triar(componentes(), para_bytes(figura_nitida()))

    corpo = respostas_api(resultado)

    assert set(corpo["visao"]) == {"imagemValida", "motivo", "culturaDetectada", "classes"}
    assert set(corpo["rag"]) == {"trechos", "explicacao", "modeloLlm"}


def test_mensagem_para_cada_motivo():
    assert set(MENSAGENS_MOTIVO) == set(MotivoRecusa)


def test_demo_montada_em_demo_so_quando_habilitada():
    carregadores = {nome: indisponivel for nome in ("visao", "portao", "indice", "llm")}
    com = criar_app(montar_config(demo_habilitada=True), carregadores)
    sem = criar_app(montar_config(demo_habilitada=False), carregadores)

    with TestClient(com) as cliente:
        assert cliente.get("/demo/").status_code == 200
    assert not any(getattr(r, "path", "").startswith("/demo") for r in sem.routes)
