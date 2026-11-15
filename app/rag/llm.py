import logging
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any

import openai
from openai import OpenAI

from app.config import Configuracao
from app.erros import ComponenteIndisponivel
from app.rag import Explicacao, guardrails
from app.rag.prompts import montar_mensagens
from app.rotulos import Rotulo
from app.schemas import Cultura, Trecho

logger = logging.getLogger("valence_ia.llm")

TEMPERATURA = 0.2
# Inclui os tokens de raciocínio; a resposta em si tem até 120 palavras
MAXIMO_TOKENS_SAIDA = 2048

ERROS_PROVEDOR = (
    openai.APIError,
    openai.APITimeoutError,
    openai.APIConnectionError,
    openai.RateLimitError,
)


@dataclass
class Provedor:
    nome: str
    modelo: str
    cliente: Any
    extras: dict[str, Any] = field(default_factory=dict)


class RespostaVazia(Exception):
    pass


def parametros_do_modelo(base_url: str, modelo: str) -> dict[str, Any]:
    nome = modelo.lower()
    # gpt-oss na Groq: raciocínio volta no campo "reasoning"; include_reasoning=false o omite
    if "gpt-oss" in nome:
        extras: dict[str, Any] = {"reasoning_effort": "low"}
        if "groq.com" in base_url:
            extras["extra_body"] = {"include_reasoning": False}
        return extras
    # Gemini pela camada compatível: pensamentos só voltam com include_thoughts
    if nome.startswith("gemini"):
        return {"reasoning_effort": "low"}
    return {}


def criar_provedor(nome: str, base_url: str, chave: str, modelo: str, timeout: float) -> Provedor:
    cliente = OpenAI(base_url=base_url, api_key=chave, timeout=timeout, max_retries=0)
    return Provedor(nome, modelo, cliente, parametros_do_modelo(base_url, modelo))


class ClienteLlmComReserva:
    def __init__(self, provedores: list[Provedor]) -> None:
        if not provedores:
            raise ComponenteIndisponivel("nenhum provedor de LLM configurado")
        self.provedores = provedores

    @classmethod
    def de_config(cls, config: Configuracao) -> "ClienteLlmComReserva":
        candidatos = [
            ("principal", config.llm_base_url, config.llm_api_key, config.llm_model),
            (
                "reserva",
                config.llm_fallback_base_url,
                config.llm_fallback_api_key,
                config.llm_fallback_model,
            ),
        ]
        provedores = [
            criar_provedor(nome, url, chave.get_secret_value(), modelo, config.llm_timeout_seconds)
            for nome, url, chave, modelo in candidatos
            if chave.get_secret_value()
        ]
        if not provedores:
            raise ComponenteIndisponivel("LLM_API_KEY e LLM_FALLBACK_API_KEY não definidas")
        return cls(provedores)

    def _gerar(self, provedor: Provedor, mensagens: list[dict[str, str]]) -> str:
        resposta = provedor.cliente.chat.completions.create(
            model=provedor.modelo,
            messages=mensagens,
            temperature=TEMPERATURA,
            max_completion_tokens=MAXIMO_TOKENS_SAIDA,
            **provedor.extras,
        )
        # Só o conteúdo final; o raciocínio do modelo nunca é lido
        escolha = resposta.choices[0]
        texto = guardrails.limpar(escolha.message.content)
        if not texto or escolha.finish_reason == "length":
            raise RespostaVazia(f"finish_reason={escolha.finish_reason}")
        return texto

    def explicar(
        self,
        cultura: Cultura,
        sintomas: str,
        classes: list[Rotulo],
        trechos: list[Trecho],
    ) -> Explicacao | None:
        mensagens = montar_mensagens(cultura, sintomas, classes, trechos)
        for provedor in self.provedores:
            inicio = perf_counter()
            try:
                texto = self._gerar(provedor, mensagens)
            except (*ERROS_PROVEDOR, RespostaVazia) as exc:
                logger.warning(
                    "llm provedor=%s modelo=%s falha=%s duracao_ms=%.0f",
                    provedor.nome,
                    provedor.modelo,
                    type(exc).__name__,
                    (perf_counter() - inicio) * 1000,
                )
                continue

            bloqueio = guardrails.verificar(texto, len(trechos))
            logger.info(
                "llm provedor=%s modelo=%s bloqueio=%s duracao_ms=%.0f",
                provedor.nome,
                provedor.modelo,
                bloqueio or "-",
                (perf_counter() - inicio) * 1000,
            )
            if bloqueio is not None:
                return Explicacao(guardrails.EXPLICACAO_FIXA, None, bloqueio.value)
            return Explicacao(texto, provedor.modelo)
        return None
