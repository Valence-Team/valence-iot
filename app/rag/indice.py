import json
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, Protocol

import numpy as np

from app.erros import ComponenteIndisponivel
from app.rag.fichas import TrechoFicha
from app.schemas import Cultura, Trecho

ARQUIVO_EMBEDDINGS = "embeddings.npy"
ARQUIVO_TRECHOS = "trechos.json"

# Busca
TOP_K = 4
BONUS_CLASSE = 0.1
# Limiares calibrados em avaliacao/rag/metricas.md, com folga para consultas relevantes
# sem classe da foto (caso l03 de avaliacao/llm/resultados.json, score 0,8587)
SCORE_MINIMO_PADRAO = 0.50
SCORES_MINIMOS = {
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2": 0.50,
    "intfloat/multilingual-e5-small": 0.85,
}

Papel = Literal["query", "passage"]


def score_minimo(modelo: str) -> float:
    return SCORES_MINIMOS.get(modelo, SCORE_MINIMO_PADRAO)


def usa_prefixo_e5(modelo: str) -> bool:
    return "e5" in modelo.lower().split("/")[-1]


# Codificação de textos
class Codificador(Protocol):
    modelo: str

    def codificar(self, textos: Sequence[str], papel: Papel) -> np.ndarray: ...


class CodificadorSentenceTransformers:
    def __init__(self, modelo: str) -> None:
        from sentence_transformers import SentenceTransformer

        self.modelo = modelo
        self.rede = SentenceTransformer(modelo, device="cpu")
        self.prefixo = usa_prefixo_e5(modelo)

    def codificar(self, textos: Sequence[str], papel: Papel) -> np.ndarray:
        if self.prefixo:
            textos = [f"{papel}: {texto}" for texto in textos]
        vetores = self.rede.encode(
            list(textos), normalize_embeddings=True, convert_to_numpy=True, batch_size=32
        )
        return np.asarray(vetores, dtype=np.float32)


def normalizar(vetores: np.ndarray) -> np.ndarray:
    normas = np.linalg.norm(vetores, axis=1, keepdims=True)
    return (vetores / np.maximum(normas, 1e-12)).astype(np.float32)


# Índice em memória
class IndiceVetorial:
    def __init__(
        self,
        trechos: list[TrechoFicha],
        embeddings: np.ndarray,
        codificador: Codificador,
        minimo: float | None = None,
        bonus: float = BONUS_CLASSE,
    ) -> None:
        if embeddings.shape[0] != len(trechos):
            raise ComponenteIndisponivel("número de embeddings diferente do número de trechos")
        self.trechos = trechos
        self.embeddings = normalizar(embeddings)
        self.codificador = codificador
        self.minimo = score_minimo(codificador.modelo) if minimo is None else minimo
        self.bonus = bonus

    @classmethod
    def construir(cls, trechos: list[TrechoFicha], codificador: Codificador) -> "IndiceVetorial":
        embeddings = codificador.codificar([t.texto for t in trechos], "passage")
        return cls(trechos, embeddings, codificador)

    @classmethod
    def carregar(cls, pasta: Path, codificador: Codificador) -> "IndiceVetorial":
        caminho_trechos = pasta / ARQUIVO_TRECHOS
        caminho_embeddings = pasta / ARQUIVO_EMBEDDINGS
        for caminho in (caminho_trechos, caminho_embeddings):
            if not caminho.exists():
                raise ComponenteIndisponivel(f"arquivo não encontrado: {caminho}")
        dados = json.loads(caminho_trechos.read_text(encoding="utf-8"))
        if dados.get("modelo") != codificador.modelo:
            raise ComponenteIndisponivel(
                f"índice gerado com {dados.get('modelo')}, mas EMBEDDINGS_MODELO é "
                f"{codificador.modelo}; rode scripts/construir_indice.py"
            )
        trechos = [TrechoFicha.de_json(item) for item in dados["trechos"]]
        embeddings = np.load(caminho_embeddings, allow_pickle=False)
        return cls(trechos, embeddings, codificador)

    def salvar(self, pasta: Path) -> None:
        pasta.mkdir(parents=True, exist_ok=True)
        np.save(pasta / ARQUIVO_EMBEDDINGS, self.embeddings, allow_pickle=False)
        dados = {
            "modelo": self.codificador.modelo,
            "dimensao": int(self.embeddings.shape[1]),
            "prefixoE5": usa_prefixo_e5(self.codificador.modelo),
            "geradoEm": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "quantidade": len(self.trechos),
            "trechos": [trecho.para_json() for trecho in self.trechos],
        }
        (pasta / ARQUIVO_TRECHOS).write_text(
            json.dumps(dados, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    # Busca
    def pontuar(
        self, consulta: str, cultura: Cultura, rotulos: Sequence[str] = ()
    ) -> list[tuple[TrechoFicha, float]]:
        vetor = self.codificador.codificar([consulta], "query")[0]
        similaridades = self.embeddings @ normalizar(vetor[None, :])[0]
        classes = set(rotulos)
        resultado = []
        for trecho, similaridade in zip(self.trechos, similaridades.tolist(), strict=True):
            if cultura not in trecho.culturas:
                continue
            bonus = self.bonus if classes.intersection(trecho.rotulos) else 0.0
            resultado.append((trecho, similaridade + bonus))
        resultado.sort(key=lambda par: par[1], reverse=True)
        return resultado

    def buscar(
        self,
        consulta: str,
        cultura: Cultura,
        k: int = TOP_K,
        rotulos: Sequence[str] = (),
    ) -> list[Trecho]:
        return [
            Trecho(
                titulo=trecho.titulo,
                texto=trecho.texto,
                fonte=trecho.fonte,
                url=trecho.url,
                score=round(score, 4),
            )
            for trecho, score in self.pontuar(consulta, cultura, rotulos)[:k]
            if score >= self.minimo
        ]
