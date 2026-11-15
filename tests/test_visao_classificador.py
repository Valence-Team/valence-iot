import json

import pytest
import torch

from app.erros import ComponenteIndisponivel
from app.rotulos import carregar_rotulos
from app.schemas import Cultura, MotivoRecusa
from app.visao import classificador as modulo
from app.visao.classificador import ClassificadorTorch
from tests.test_visao_apoio import (
    CLASSES,
    CULTURAS,
    TEMPERATURA,
    RedeMinuscula,
    figura_nitida,
    logits_fixos,
    salvar_modelo,
)


@pytest.fixture(autouse=True)
def rede_minuscula(monkeypatch):
    monkeypatch.setitem(modulo.ARQUITETURAS, "rede_minuscula", RedeMinuscula)


@pytest.fixture
def carregar(tmp_path):
    def _carregar(por_rotulo: dict[str, float], **ajustes) -> ClassificadorTorch:
        pesos = salvar_modelo(tmp_path, por_rotulo, **ajustes)
        return ClassificadorTorch.carregar(pesos, carregar_rotulos())

    return _carregar


# Carga
def test_carrega_pesos_e_metadados(carregar):
    modelo = carregar({})

    assert modelo.metadados.classes == CLASSES
    assert not modelo.rede.training
    assert modelo.metadados.temperatura == TEMPERATURA


@pytest.mark.parametrize("arquivo", ["visao.pt", "visao.json"])
def test_indisponivel_quando_falta_arquivo(carregar, tmp_path, arquivo):
    carregar({})
    (tmp_path / arquivo).unlink()

    with pytest.raises(ComponenteIndisponivel):
        ClassificadorTorch.carregar(tmp_path / "visao.pt", carregar_rotulos())


def test_indisponivel_com_arquitetura_desconhecida(carregar):
    with pytest.raises(ComponenteIndisponivel):
        carregar({}, arquitetura="resnet_inexistente")


def test_indisponivel_com_classe_sem_rotulo(carregar):
    with pytest.raises(ComponenteIndisponivel):
        carregar({}, classes=[*CLASSES[:-1], "classe_inventada"])


def test_metadados_incoerentes_falham_na_carga(carregar, tmp_path):
    carregar({})
    caminho = tmp_path / "visao.json"
    dados = json.loads(caminho.read_text(encoding="utf-8"))
    dados["culturas"] = CULTURAS[:-1]
    caminho.write_text(json.dumps(dados), encoding="utf-8")

    with pytest.raises(ValueError):
        ClassificadorTorch.carregar(tmp_path / "visao.pt", carregar_rotulos())


# Inferência
def test_softmax_com_temperatura(carregar):
    modelo = carregar({"milho_ferrugem_comum": 3.0})

    logits = modelo.logits(figura_nitida())

    assert torch.allclose(logits, logits_fixos({"milho_ferrugem_comum": 3.0}) / TEMPERATURA)


def test_cultura_detectada_e_a_de_maior_soma_e_nao_a_da_maior_classe(carregar):
    por_rotulo = {"batata_requeima": 2.0, **{r: 1.0 for r in CLASSES if r.startswith("tomate_")}}
    modelo = carregar(por_rotulo)

    resultado = modelo.classificar(figura_nitida(), Cultura.TOMATE)

    assert resultado.cultura_detectada == Cultura.TOMATE
    assert resultado.motivo is None


def test_divergencia_acima_de_07(carregar):
    resultado = carregar({"milho_ferrugem_comum": 10.0}).classificar(
        figura_nitida(), Cultura.BATATA
    )

    assert resultado.motivo == MotivoRecusa.CULTURA_DIVERGENTE
    assert resultado.cultura_detectada == Cultura.MILHO
    assert resultado.classes == []


def test_top3_renormalizado_dentro_da_cultura(carregar):
    por_rotulo = {
        "tomate_requeima": 3.0,
        "tomate_septoriose": 2.0,
        "tomate_pinta_preta": 1.0,
        "tomate_saudavel": 0.5,
        "milho_ferrugem_comum": 2.5,
    }
    modelo = carregar(por_rotulo)

    resultado = modelo.classificar(figura_nitida(), Cultura.TOMATE)

    logits = logits_fixos(por_rotulo) / TEMPERATURA
    tomate = [i for i, c in enumerate(CULTURAS) if c == "TOMATE"]
    esperado = dict(
        zip([CLASSES[i] for i in tomate], logits[tomate].softmax(0).tolist(), strict=True)
    )
    assert [c.rotulo for c in resultado.classes] == [
        "tomate_requeima",
        "tomate_septoriose",
        "tomate_pinta_preta",
    ]
    for classe in resultado.classes:
        assert classe.confianca == round(esperado[classe.rotulo], 4)
        assert classe.nome
    assert sum(esperado.values()) == pytest.approx(1.0)


def test_cultura_com_tres_classes_soma_um(carregar):
    modelo = carregar({"batata_requeima": 1.0, "batata_pinta_preta": 0.8, "batata_saudavel": 0.6})

    resultado = modelo.classificar(figura_nitida(), Cultura.BATATA)

    assert len(resultado.classes) == 3
    assert sum(c.confianca for c in resultado.classes) == pytest.approx(1.0, abs=1e-3)


def test_cultura_sem_massa_nao_gera_nan(carregar):
    modelo = carregar({"milho_ferrugem_comum": 1.0, "tomate_requeima": 1.0}, temperatura=0.05)

    resultado = modelo.classificar(figura_nitida(), Cultura.BATATA)

    assert resultado.motivo is None
    assert [c.confianca for c in resultado.classes] == [0.3333, 0.3333, 0.3333]
