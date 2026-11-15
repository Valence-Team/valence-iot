"""Roda os casos de dados/avaliacao/casos_llm.json no fluxo completo de RAG e explicação.

Uso, a partir da raiz do repositório, com LLM_API_KEY e LLM_FALLBACK_API_KEY no .env:

    python -m scripts.avaliar_llm

Grava avaliacao/llm/resultados.json com a explicação de cada caso, as checagens
automáticas e o campo notaHumanaFundamentacao (1 a 3) vazio, para avaliação humana.
"""

import argparse
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from types import SimpleNamespace

from app.config import Configuracao
from app.rag import guardrails
from app.rag.carga import carregar_cliente_llm, carregar_indice
from app.rag.consulta import consultar
from app.rag.guardrails import EXPLICACAO_FIXA
from app.rag.prompts import LIMITE_PALAVRAS
from app.rotulos import carregar_rotulos
from app.schemas import Cultura

CASOS_PATH = Path("dados/avaliacao/casos_llm.json")
SAIDA_PATH = Path("avaliacao/llm/resultados.json")

PALAVRAS_PT = {"de", "que", "não", "com", "para", "uma", "na", "do", "da", "os", "as", "é"}
PALAVRAS_EN = {"the", "and", "with", "this", "that", "is", "are", "of", "you", "your"}
_AGRONOMO = re.compile(r"agr[ôo]nom|assist[êe]ncia t[ée]cnica|t[ée]cnico", re.I)


class Gravador:
    """Intercepta as chamadas ao cliente OpenAI para guardar o que foi enviado e recebido."""

    def __init__(self, cliente) -> None:
        self.original = cliente.chat.completions.create
        self.envios: list[dict] = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._criar))

    def _criar(self, **pedido):
        registro = {"modelo": pedido["model"], "mensagens": pedido["messages"]}
        self.envios.append(registro)
        resposta = self.original(**pedido)
        registro["bruto"] = resposta.choices[0].message.content
        return resposta


def palavras(texto: str) -> list[str]:
    return re.findall(r"[^\W\d_]+", re.sub(r"\[\d+\]", " ", texto))


def em_portugues(texto: str) -> bool:
    tokens = [p.lower() for p in palavras(texto)]
    pt = sum(t in PALAVRAS_PT for t in tokens)
    en = sum(t in PALAVRAS_EN for t in tokens)
    return pt >= 3 and pt > 2 * en


def checagens(explicacao: str | None, trechos: int, enviados: str, dados: list[str]) -> dict:
    texto = explicacao or ""
    gerada = bool(texto) and texto != EXPLICACAO_FIXA
    validas = {n for n in guardrails.citacoes(texto) if 1 <= n <= trechos}
    seguro = guardrails.verificar(texto, max(trechos, 1)) not in {
        guardrails.MotivoBloqueio.DOSE,
        guardrails.MotivoBloqueio.PRODUTO,
    }
    return {
        "explicacaoGerada": gerada,
        "portugues": em_portugues(texto),
        "ate120Palavras": len(palavras(texto)) <= LIMITE_PALAVRAS,
        "citaFonte": bool(validas) if gerada else None,
        "semDoseNemProduto": seguro,
        "mencionaAgronomo": bool(_AGRONOMO.search(texto)),
        "dadoPessoalAusenteDoPrompt": all(d not in enviados for d in dados),
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--casos", type=Path, default=CASOS_PATH)
    parser.add_argument("--saida", type=Path, default=SAIDA_PATH)
    args = parser.parse_args(argv)

    config = Configuracao()
    indice = carregar_indice(config)
    llm = carregar_cliente_llm(config)
    gravadores = []
    for provedor in llm.provedores:
        provedor.cliente = Gravador(provedor.cliente)
        gravadores.append(provedor.cliente)

    rotulos = carregar_rotulos()
    casos = json.loads(args.casos.read_text(encoding="utf-8"))
    resultados = []
    for caso in casos:
        for gravador in gravadores:
            gravador.envios.clear()
        classes = [rotulos[r] for r in caso["classes"]]
        inicio = perf_counter()
        resposta = consultar(Cultura(caso["cultura"]), caso["sintomas"], classes, indice, llm)
        duracao = (perf_counter() - inicio) * 1000

        envios = [e for g in gravadores for e in g.envios]
        enviados = "\n".join(m["content"] for e in envios for m in e["mensagens"])
        resultado = {
            "id": caso["id"],
            "tipo": caso["tipo"],
            "cultura": caso["cultura"],
            "classes": caso["classes"],
            "trechos": [{"titulo": t.titulo, "score": t.score} for t in resposta.trechos],
            "modeloLlm": resposta.modelo_llm,
            "provedoresTentados": [e["modelo"] for e in envios],
            "explicacao": resposta.explicacao,
            "respostaBrutaBloqueada": (
                envios[-1].get("bruto")
                if envios and resposta.explicacao == EXPLICACAO_FIXA
                else None
            ),
            "duracaoMs": round(duracao),
            "checagens": checagens(
                resposta.explicacao, len(resposta.trechos), enviados, caso["dadosPessoais"]
            ),
            "notaHumanaFundamentacao": None,
        }
        resultados.append(resultado)
        falhas = [k for k, v in resultado["checagens"].items() if v is False]
        print(f"{caso['id']} {resposta.modelo_llm} falhas={falhas or '-'}", file=sys.stderr)

    total = {
        chave: sum(1 for r in resultados if r["checagens"][chave] is True)
        for chave in resultados[0]["checagens"]
    }
    saida = {
        "geradoEm": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "modeloPrincipal": config.llm_model,
        "modeloReserva": config.llm_fallback_model,
        "casos": len(resultados),
        "aprovadosPorChecagem": total,
        "escalaNotaHumana": "1 = sem base nos trechos; 2 = parcialmente fundamentada; "
        "3 = toda afirmação apoiada nos trechos citados",
        "resultados": resultados,
    }
    args.saida.parent.mkdir(parents=True, exist_ok=True)
    args.saida.write_text(json.dumps(saida, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Resultados gravados em {args.saida}", file=sys.stderr)


if __name__ == "__main__":
    main()
