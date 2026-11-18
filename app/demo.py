import logging
from dataclasses import dataclass
from pathlib import Path

import gradio as gr
from fastapi import FastAPI

from app.componentes import Componentes
from app.erros import ErroApi
from app.rag.consulta import consultar
from app.rotulos import Rotulo
from app.schemas import ClassificacaoResponse, ConsultaRagResponse, Cultura, MotivoRecusa
from app.visao.fluxo import executar_camadas
from app.visao.qualidade import abrir_imagem, validar_tamanho

logger = logging.getLogger("valence_ia.demo")

EXEMPLOS_PATH = Path(__file__).resolve().parent.parent / "dados" / "exemplos"
LIMITE_SINTOMAS = 1000

MENSAGENS_MOTIVO = {
    MotivoRecusa.RESOLUCAO_BAIXA: "A foto ficou pequena demais. Chegue mais perto da folha.",
    MotivoRecusa.IMAGEM_ESCURA: "A foto ficou escura. Tire outra com a folha bem iluminada.",
    MotivoRecusa.IMAGEM_CLARA: "A foto ficou clara demais. Evite sol direto ou flash na folha.",
    MotivoRecusa.IMAGEM_BORRADA: "A foto ficou tremida. Segure firme e foque na folha.",
    MotivoRecusa.NAO_E_PLANTA: "Não encontramos uma folha na foto. Fotografe a folha doente.",
    MotivoRecusa.CULTURA_FORA_DO_ESCOPO: (
        "A folha não parece ser de milho, tomate ou batata, as culturas atendidas."
    ),
    MotivoRecusa.CULTURA_DIVERGENTE: (
        "A folha parece ser de outra cultura. Confira a cultura escolhida."
    ),
}


@dataclass(frozen=True)
class ResultadoTriagem:
    visao: ClassificacaoResponse | None
    erro_visao: str | None
    rag: ConsultaRagResponse | None
    erro_rag: str | None


# Mesma sequência que a API Java segue, chamando as funções internas
def classificar_foto(
    componentes: Componentes, dados: bytes, cultura: Cultura, limite_mb: int
) -> ClassificacaoResponse:
    if componentes.visao is None or componentes.portao is None:
        raise ErroApi(503, "O modelo de visão não está carregado.")
    validar_tamanho(dados, limite_mb)
    figura = abrir_imagem(dados)
    resultado = executar_camadas(figura, cultura, componentes.portao, componentes.visao)
    return ClassificacaoResponse(
        imagem_valida=resultado.motivo is None,
        motivo=resultado.motivo,
        cultura_detectada=resultado.cultura_detectada,
        classes=resultado.classes,
    )


def executar_triagem(
    componentes: Componentes,
    rotulos: dict[str, Rotulo],
    dados: bytes | None,
    cultura: Cultura,
    sintomas: str,
    limite_mb: int,
) -> ResultadoTriagem:
    visao, erro_visao = None, None
    if dados is not None:
        try:
            visao = classificar_foto(componentes, dados, cultura, limite_mb)
        except ErroApi as exc:
            erro_visao = f"{exc.status}: {exc.mensagem}"

    classes = [rotulos[c.rotulo] for c in visao.classes] if visao and visao.imagem_valida else []
    rag, erro_rag = None, None
    if componentes.indice is None:
        erro_rag = "503: O índice de fichas técnicas não está carregado."
    else:
        rag = consultar(
            cultura, sintomas[:LIMITE_SINTOMAS], classes, componentes.indice, componentes.llm
        )
    return ResultadoTriagem(visao, erro_visao, rag, erro_rag)


# Formatação da tela
def texto_validade(resultado: ResultadoTriagem) -> str:
    if resultado.erro_visao:
        return f"**Foto não analisada.** {resultado.erro_visao}"
    if resultado.visao is None:
        return "Sem foto: a triagem usa só o relato."
    if resultado.visao.imagem_valida:
        cultura = resultado.visao.cultura_detectada
        return f"**Foto válida.** Cultura detectada: {cultura.value if cultura else '-'}."
    motivo = resultado.visao.motivo
    return f"**Foto recusada: `{motivo.value}`.** {MENSAGENS_MOTIVO[motivo]}"


def confiancas(resultado: ResultadoTriagem) -> dict[str, float]:
    if resultado.visao is None:
        return {}
    return {c.nome: c.confianca for c in resultado.visao.classes}


def texto_trechos(resultado: ResultadoTriagem) -> str:
    if resultado.erro_rag:
        return resultado.erro_rag
    if not resultado.rag.trechos:
        return "Nenhum trecho das fichas passou do score mínimo."
    return "\n".join(
        f"{i}. **{t.titulo}** (score {t.score:.3f}). Fonte: [{t.fonte}]({t.url})"
        for i, t in enumerate(resultado.rag.trechos, 1)
    )


def texto_explicacao(resultado: ResultadoTriagem) -> tuple[str, str]:
    if resultado.rag is None:
        return "", "-"
    explicacao = resultado.rag.explicacao or "Os dois LLMs falharam; a explicação ficou nula."
    if resultado.rag.explicacao and resultado.rag.modelo_llm is None:
        return explicacao, "texto fixo (sem trecho relevante ou resposta barrada pelo guardrail)"
    return explicacao, resultado.rag.modelo_llm or "-"


def respostas_api(resultado: ResultadoTriagem) -> dict:
    return {
        "visao": resultado.visao.model_dump(by_alias=True, mode="json")
        if resultado.visao
        else None,
        "rag": resultado.rag.model_dump(by_alias=True, mode="json") if resultado.rag else None,
    }


def exemplos() -> list[list]:
    casos = [
        ("milho_ferrugem_comum.jpg", "MILHO", "Bolinhas cor de ferrugem nas duas faces da folha."),
        ("tomate_requeima.jpg", "TOMATE", "Mancha grande molhada depois da neblina."),
        ("batata_pinta_preta.jpg", "BATATA", "Manchas escuras com anéis nas folhas de baixo."),
        ("milho_ferrugem_campo.jpg", "MILHO", "Pó cor de ferrugem nas folhas da roça."),
        ("tomate_borrada.jpg", "TOMATE", "Folha com manchas, foto tirada às pressas."),
        ("milho_ferrugem_comum.jpg", "TOMATE", "Manchas na folha."),
    ]
    return [
        [str(EXEMPLOS_PATH / arquivo), cultura, sintomas]
        for arquivo, cultura, sintomas in casos
        if (EXEMPLOS_PATH / arquivo).exists()
    ]


def criar_demo(app: FastAPI) -> gr.Blocks:
    def triar(caminho: str | None, cultura: str, sintomas: str):
        dados = Path(caminho).read_bytes() if caminho else None
        resultado = executar_triagem(
            app.state.componentes,
            app.state.rotulos,
            dados,
            Cultura(cultura),
            sintomas or "",
            app.state.config.tamanho_maximo_mb,
        )
        explicacao, modelo = texto_explicacao(resultado)
        return (
            texto_validade(resultado),
            confiancas(resultado),
            texto_trechos(resultado),
            explicacao,
            modelo,
            respostas_api(resultado),
        )

    with gr.Blocks(title="Valence: triagem fitossanitária") as demo:
        gr.Markdown(
            "# Valence: triagem fitossanitária\n"
            "Foto da folha, cultura e relato do produtor. O resultado é uma **suspeita** para "
            "triagem; o diagnóstico é sempre do agrônomo."
        )
        with gr.Row():
            with gr.Column():
                foto = gr.Image(type="filepath", label="Foto da folha", sources=["upload"])
                cultura = gr.Radio(
                    [c.value for c in Cultura], value=Cultura.MILHO.value, label="Cultura"
                )
                sintomas = gr.Textbox(label="Sintomas descritos pelo produtor", lines=3)
                botao = gr.Button("Fazer triagem", variant="primary")
            with gr.Column():
                validade = gr.Markdown(label="Validade da foto")
                top3 = gr.Label(label="Top 3 na cultura informada", num_top_classes=3)
                modelo = gr.Textbox(label="Modelo de linguagem usado", interactive=False)
        explicacao = gr.Markdown(label="Explicação")
        trechos = gr.Markdown(label="Trechos das fichas técnicas")
        with gr.Accordion("JSON como a API Java recebe", open=False):
            json_api = gr.JSON()

        saidas = [validade, top3, trechos, explicacao, modelo, json_api]
        botao.click(triar, inputs=[foto, cultura, sintomas], outputs=saidas)
        casos = exemplos()
        if casos:
            gr.Examples(casos, inputs=[foto, cultura, sintomas], label="Exemplos")
    return demo


def montar_demo(app: FastAPI) -> FastAPI:
    return gr.mount_gradio_app(app, criar_demo(app), path="/demo", footer_links=[])
