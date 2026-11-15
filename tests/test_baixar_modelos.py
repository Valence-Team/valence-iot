import hashlib
import json

import pytest

from scripts import baixar_modelos


@pytest.fixture
def release(monkeypatch):
    conteudo = {"visao.pt": b"pesos do modelo"}
    baixados = []

    def baixar_falso(url: str, destino):
        baixados.append(url)
        destino.write_bytes(conteudo[destino.name])

    monkeypatch.setattr(baixar_modelos, "baixar", baixar_falso)
    return conteudo, baixados


def escrever_json(conteudo, sha: str) -> None:
    conteudo["visao.json"] = json.dumps({"sha256": sha}).encode()


def test_baixa_da_release_e_confere_o_sha256(tmp_path, release):
    conteudo, baixados = release
    escrever_json(conteudo, hashlib.sha256(conteudo["visao.pt"]).hexdigest())

    baixar_modelos.baixar_classificador("modelos-v1", tmp_path)

    assert (tmp_path / "visao.pt").read_bytes() == conteudo["visao.pt"]
    assert baixados == [
        "https://github.com/Valence-Team/valence-iot/releases/download/modelos-v1/visao.json",
        "https://github.com/Valence-Team/valence-iot/releases/download/modelos-v1/visao.pt",
    ]


def test_sha256_diferente_apaga_o_arquivo_e_falha(tmp_path, release):
    conteudo, _ = release
    escrever_json(conteudo, "0" * 64)

    with pytest.raises(SystemExit, match="sha256"):
        baixar_modelos.baixar_classificador("modelos-v1", tmp_path)

    assert not (tmp_path / "visao.pt").exists()


def test_nao_baixa_de_novo_o_que_ja_existe(tmp_path, release):
    conteudo, baixados = release
    escrever_json(conteudo, hashlib.sha256(conteudo["visao.pt"]).hexdigest())
    (tmp_path / "visao.json").write_bytes(conteudo["visao.json"])
    (tmp_path / "visao.pt").write_bytes(conteudo["visao.pt"])

    baixar_modelos.baixar_classificador("modelos-v1", tmp_path)

    assert baixados == []
