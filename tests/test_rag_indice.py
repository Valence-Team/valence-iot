import json
from pathlib import Path

import numpy as np
import pytest

from app.erros import ComponenteIndisponivel
from app.rag import fichas as modulo_fichas
from app.rag.fichas import SECOES, ler_ficha, ler_fichas, quebrar_em_trechos
from app.rag.indice import BONUS_CLASSE, IndiceVetorial, usa_prefixo_e5
from app.rotulos import carregar_rotulos
from app.schemas import Cultura
from tests.test_rag_apoio import TRECHOS_PEQUENOS, CodificadorFalso, indice_pequeno

FICHA_EXEMPLO = """---
id: exemplo
titulo: Ficha de exemplo
cultura: [TOMATE, BATATA]
rotulos: []
nomeCientifico: null
fonte: Embrapa
url: https://www.embrapa.br/exemplo
acessadoEm: 2026-11-15
---

## Sintomas

{longo}

## Condições favoráveis

Calor e umidade favorecem o problema na lavoura durante o verão.

## Disseminação

{medio}

## Manejo cultural e preventivo

{medio}

## Quando chamar o agrônomo

Procure o agrônomo.
"""


# Corpus versionado
def test_corpus_tem_as_24_fichas_e_cobre_todos_os_rotulos():
    fichas = ler_fichas()
    rotulos = carregar_rotulos()

    assert len(fichas) == 24
    cobertos = {r for ficha in fichas for r in ficha.rotulos}
    assert cobertos == set(rotulos)
    fora_do_modelo = [f for f in fichas if not f.rotulos]
    assert len(fora_do_modelo) == 7


def test_fichas_seguem_o_formato():
    for ficha in ler_fichas():
        assert tuple(ficha.secoes) == SECOES
        assert ficha.url.startswith(("http://", "https://"))
        assert "embrapa" in ficha.url
        assert ficha.acessado_em == "2026-11-15"


def test_trechos_do_corpus_tem_60_a_200_palavras_com_titulo():
    for ficha in ler_fichas():
        for trecho in quebrar_em_trechos(ficha):
            assert trecho.texto.startswith(ficha.titulo)
            assert 60 <= len(trecho.texto.split()) <= 200, (ficha.id, trecho.secao)


# Leitura e quebra
def test_secao_curta_junta_com_a_anterior_e_longa_e_dividida(tmp_path):
    longo = " ".join(["Frase longa com várias palavras sobre a doença na folha."] * 30)
    medio = " ".join(["Frase média sobre o manejo da lavoura."] * 12)
    caminho = tmp_path / "exemplo.md"
    caminho.write_text(FICHA_EXEMPLO.format(longo=longo, medio=medio), encoding="utf-8")

    ficha = ler_ficha(caminho)
    trechos = quebrar_em_trechos(ficha)

    assert ficha.culturas == (Cultura.TOMATE, Cultura.BATATA)
    assert [t.secao for t in trechos] == [
        "Sintomas",
        "Sintomas; Condições favoráveis",
        "Disseminação",
        "Manejo cultural e preventivo; Quando chamar o agrônomo",
    ]
    assert all(len(t.texto.split()) <= 200 for t in trechos)


def test_ficha_sem_secao_obrigatoria_falha(tmp_path):
    texto = FICHA_EXEMPLO.format(longo="a", medio="b").replace("## Disseminação", "## Outra")
    caminho = tmp_path / "ruim.md"
    caminho.write_text(texto, encoding="utf-8")

    with pytest.raises(ValueError, match="seções"):
        ler_ficha(caminho)


def test_ficha_sem_url_falha(tmp_path):
    texto = FICHA_EXEMPLO.format(longo="a", medio="b").replace(
        "url: https://www.embrapa.br/exemplo\n", ""
    )
    caminho = tmp_path / "sem_url.md"
    caminho.write_text(texto, encoding="utf-8")

    with pytest.raises(ValueError, match="url"):
        ler_ficha(caminho)


# Busca
def test_filtra_pela_cultura():
    resultado = indice_pequeno(minimo=-1).buscar("manchas na folha", Cultura.BATATA, 4)

    assert [t.titulo for t in resultado] == ["Murcha bacteriana"]


def test_trecho_de_duas_culturas_aparece_nas_duas():
    indice = indice_pequeno(minimo=-1)

    assert "Murcha bacteriana" in [t.titulo for t in indice.buscar("murchas", Cultura.TOMATE, 4)]


def test_ordena_por_similaridade():
    resultado = indice_pequeno().buscar("pústulas cor de ferrugem na folha", Cultura.MILHO, 4)

    assert resultado[0].titulo == "Milho ferrugem"
    assert [t.score for t in resultado] == sorted((t.score for t in resultado), reverse=True)


def test_bonus_fixo_para_trechos_das_classes_recebidas():
    indice = indice_pequeno(minimo=-1)
    consulta = "manchas na folha"

    sem = {t.titulo: t.score for t in indice.buscar(consulta, Cultura.MILHO, 4)}
    com = {
        t.titulo: t.score
        for t in indice.buscar(consulta, Cultura.MILHO, 4, ["milho_cercosporiose"])
    }

    assert com["Milho cercosporiose"] == pytest.approx(sem["Milho cercosporiose"] + BONUS_CLASSE)
    assert com["Milho ferrugem"] == pytest.approx(sem["Milho ferrugem"])


def test_top_k_e_corte_pelo_score_minimo():
    indice = indice_pequeno(minimo=-1)
    assert len(indice.buscar("folha", Cultura.MILHO, 2)) == 2

    indice.minimo = 0.99
    assert indice.buscar("algo sem relação nenhuma", Cultura.MILHO, 4) == []


def test_consulta_usa_papel_query_e_trechos_usam_passage():
    codificador = CodificadorFalso()
    indice = IndiceVetorial.construir(TRECHOS_PEQUENOS, codificador)

    indice.buscar("ferrugem", Cultura.MILHO, 4)

    assert [papel for papel, _ in codificador.chamadas] == ["passage", "query"]


@pytest.mark.parametrize(
    ("modelo", "esperado"),
    [
        ("intfloat/multilingual-e5-small", True),
        ("sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2", False),
    ],
)
def test_prefixos_so_para_modelos_e5(modelo, esperado):
    assert usa_prefixo_e5(modelo) is esperado


# Persistência
def test_salvar_e_carregar(tmp_path):
    indice = indice_pequeno()
    indice.salvar(tmp_path)

    dados = json.loads((tmp_path / "trechos.json").read_text(encoding="utf-8"))
    carregado = IndiceVetorial.carregar(tmp_path, CodificadorFalso())

    assert dados["modelo"] == "codificador-falso"
    assert set(dados["trechos"][0]) == {
        "texto",
        "titulo",
        "cultura",
        "rotulos",
        "fonte",
        "url",
        "secao",
        "ficha",
    }
    assert np.load(tmp_path / "embeddings.npy").shape == (len(TRECHOS_PEQUENOS), 256)
    assert carregado.buscar("ferrugem", Cultura.MILHO, 1)[0].titulo == "Milho ferrugem"


def test_indisponivel_quando_o_modelo_do_indice_e_outro(tmp_path):
    indice_pequeno().salvar(tmp_path)

    with pytest.raises(ComponenteIndisponivel, match="EMBEDDINGS_MODELO"):
        IndiceVetorial.carregar(tmp_path, CodificadorFalso("outro-modelo"))


def test_indisponivel_sem_arquivos(tmp_path):
    with pytest.raises(ComponenteIndisponivel):
        IndiceVetorial.carregar(tmp_path, CodificadorFalso())


def test_indice_versionado_bate_com_as_fichas():
    pasta = Path(modulo_fichas.FICHAS_PATH).parent.parent / "modelos" / "indice"
    dados = json.loads((pasta / "trechos.json").read_text(encoding="utf-8"))
    esperados = [t.texto for f in ler_fichas() for t in quebrar_em_trechos(f)]

    assert [t["texto"] for t in dados["trechos"]] == esperados
    assert np.load(pasta / "embeddings.npy").shape[0] == len(esperados)
