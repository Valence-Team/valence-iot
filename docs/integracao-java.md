# Integração da API Java com o serviço de IA

Guia para o cliente do serviço de IA na API Java (Spring Boot). O contrato é o da seção 7 do `03-contratos-e-integracao.md` com as atualizações de 06/11 e 15/11. Este repositório não altera o código Java.

## Configuração

| Variável no Java | Exemplo | Uso |
| --- | --- | --- |
| `IA_SERVICE_URL` | `http://localhost:8000` | Base das rotas abaixo |
| `IA_API_KEY` | (o mesmo valor de `IA_API_KEY` no serviço de IA) | Enviado no cabeçalho `X-API-Key` |
| `IA_TIMEOUT_SECONDS` | ver [Tempos medidos](#tempos-medidos) | Tempo limite de cada chamada |

Todas as rotas, menos `/health`, exigem `X-API-Key` quando o serviço tem `IA_API_KEY` definida. Sem a chave, ou com a chave errada, a resposta é 401.

## Ordem das chamadas

1. `POST /api/v1/visao/classificar` com a foto e a cultura da ocorrência.
2. `POST /api/v1/rag/consultar` com a cultura, a descrição do produtor e os rótulos das classes, ou sem classes se a foto foi recusada.
3. A Triagem do Spring AI usa as classes, os trechos e a explicação como entrada.

O fluxo completo, com o JSON exato de cada resposta, roda com `python -m tests.integracao.fluxo_triagem` (use `--sem-llm` para simular os LLMs fora do ar).

## Classificação da foto

```http
POST /api/v1/visao/classificar
X-API-Key: <IA_API_KEY>
Content-Type: multipart/form-data; boundary=...

imagem=<arquivo JPEG, PNG ou WebP, até 8 MB>
cultura=TOMATE
```

`cultura` aceita maiúsculas ou minúsculas (`MILHO`, `TOMATE`, `BATATA`).

Foto válida:

```json
{
  "imagemValida": true,
  "motivo": null,
  "culturaDetectada": "TOMATE",
  "classes": [
    { "rotulo": "tomate_requeima", "nome": "Requeima", "confianca": 0.9412 },
    { "rotulo": "tomate_pinta_preta", "nome": "Pinta-preta", "confianca": 0.0391 },
    { "rotulo": "tomate_mancha_alvo", "nome": "Mancha-alvo", "confianca": 0.0197 }
  ]
}
```

Foto recusada:

```json
{ "imagemValida": false, "motivo": "IMAGEM_BORRADA", "culturaDetectada": null, "classes": [] }
```

As confianças são calibradas (temperatura ajustada na validação) e renormalizadas dentro da cultura informada, por isso as três somam perto de 1. `culturaDetectada` é a cultura com maior probabilidade somada entre as 17 classes.

## Consulta às fichas e explicação

```http
POST /api/v1/rag/consultar
X-API-Key: <IA_API_KEY>
Content-Type: application/json

{
  "cultura": "TOMATE",
  "sintomas": "Mancha grande molhada e mofo branco embaixo da folha depois da neblina.",
  "classes": ["tomate_requeima", "tomate_pinta_preta", "tomate_mancha_alvo"]
}
```

`sintomas` tem até 1000 caracteres; `classes` é opcional, com até 3 rótulos da mesma cultura.

```json
{
  "trechos": [
    {
      "titulo": "Requeima do tomateiro",
      "texto": "Requeima do tomateiro. Sintomas: A requeima, também chamada de mela, ...",
      "fonte": "Embrapa Hortaliças. Doenças do tomateiro, 3ª edição, 2021",
      "url": "http://www.infoteca.cnptia.embrapa.br/infoteca/bitstream/doc/1135499/1/Livro-Doencas-do-Tomateiro.pdf",
      "score": 0.985
    }
  ],
  "explicacao": "A suspeita é de requeima (mela). ... procure o agrônomo imediatamente [1].",
  "modeloLlm": "openai/gpt-oss-20b"
}
```

| Situação | `trechos` | `explicacao` | `modeloLlm` |
| --- | --- | --- | --- |
| Explicação gerada | 1 a 4 | Texto com citações [n] | Nome do modelo (Groq ou Gemini) |
| Nenhum trecho relevante | `[]` | Texto fixo que encaminha ao agrônomo | `null` |
| Resposta barrada pelo guardrail (dose, produto ou sem citação) | 1 a 4 | Mesmo texto fixo | `null` |
| Groq e Gemini fora do ar | 1 a 4 | `null` | `null` |

Regra: `explicacao` preenchida com `modeloLlm` nulo é o texto fixo, nunca uma explicação gerada. Não envie o nome do produtor em `sintomas`: o serviço mascara e-mail, telefone, CPF, CEP e coordenadas, mas não reconhece nomes.

## Códigos de erro

Corpo no formato comum do Valence:

```json
{
  "timestamp": "2026-11-15T14:32:00Z",
  "status": 415,
  "erro": "Tipo de mídia não suportado",
  "mensagem": "Envie uma imagem JPEG, PNG ou WebP.",
  "caminho": "/api/v1/visao/classificar",
  "campos": []
}
```

| Status | Quando | O que a API Java faz |
| --- | --- | --- |
| 400 | Campo ausente ou inválido, cultura fora do enum, imagem que não abre, rótulo desconhecido | Erro de integração: registrar e seguir com triagem só por texto |
| 401 | `X-API-Key` ausente ou errada | Erro de configuração: alertar no log; seguir com triagem só por texto |
| 413 | Imagem acima de 8 MB ou de 50 megapixels | Validar o tamanho no app antes do envio; seguir só por texto |
| 415 | Arquivo que não é JPEG, PNG ou WebP | Validar o formato no app antes do envio; seguir só por texto |
| 422 | Classe enviada ao RAG que não pertence à cultura | Bug do cliente: enviar só classes da mesma resposta de visão |
| 500 | Erro inesperado (sem detalhes na resposta) | Ocorrência em EM_ANALISE |
| 503 | Modelo de visão ou índice não carregado | Fallback só com texto (seção 6 do `03`) |
| Tempo esgotado | Serviço lento ou fora do ar | Igual ao 503 |

## Tratamento esperado por motivo

Quando `imagemValida` é `false`, a ocorrência vai para EM_ANALISE com `encaminharAgronomo = true` e sem alerta automático. A Triagem pode ser criada só com `motivoImagem`, e o app mostra uma mensagem simples ao produtor.

| `motivo` | Mensagem sugerida para o app | Ação |
| --- | --- | --- |
| `RESOLUCAO_BAIXA` | A foto ficou pequena demais. Chegue mais perto da folha. | Pedir nova foto |
| `IMAGEM_ESCURA` | A foto ficou escura. Tire outra com a folha bem iluminada. | Pedir nova foto |
| `IMAGEM_CLARA` | A foto ficou clara demais. Evite sol direto ou flash na folha. | Pedir nova foto |
| `IMAGEM_BORRADA` | A foto ficou tremida. Segure firme e foque na folha. | Pedir nova foto |
| `NAO_E_PLANTA` | Não encontramos uma folha na foto. Fotografe a folha doente. | Pedir nova foto |
| `CULTURA_FORA_DO_ESCOPO` | A folha não parece ser de milho, tomate ou batata, as culturas atendidas. | Encaminhar ao agrônomo; o RAG segue só com o relato |
| `CULTURA_DIVERGENTE` | A folha parece ser de outra cultura. Confira a cultura escolhida. | Mostrar `culturaDetectada` e pedir confirmação ao produtor |

As mesmas mensagens estão em `app/demo.py` (`MENSAGENS_MOTIVO`).

## Tempos medidos

PREENCHER_LATENCIA
