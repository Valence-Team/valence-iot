# Arquitetura do serviço de IA

O serviço de IA é um FastAPI na porta 8000, chamado só pela API Java. O app nunca fala com ele diretamente.

## Componentes

```mermaid
flowchart LR
    subgraph Produtor
        App["App Mobile<br/>React Native + Expo"]
    end

    subgraph Java["API Java · Spring Boot · 8080"]
        Triagem["Triagem da ocorrência<br/>(Spring AI)"]
    end

    subgraph IA["Serviço de IA · FastAPI · 8000"]
        direction TB
        Chave["X-API-Key"]
        subgraph Visao["POST /api/v1/visao/classificar"]
            direction TB
            Q["1. Qualidade<br/>resolução, brilho, nitidez<br/>(Pillow + numpy)"]
            P["2. Portão<br/>CLIP ViT-B/32 zero-shot"]
            C["3. Classificador<br/>CNN treinada no PlantVillage<br/>+ temperatura"]
            Q --> P --> C
        end
        subgraph Rag["POST /api/v1/rag/consultar"]
            direction TB
            M["Mascaramento de<br/>dados pessoais"]
            I[("Índice numpy<br/>multilingual-e5-small<br/>117 trechos de 24 fichas")]
            G["Prompt + guardrail<br/>de saída"]
            M --> I --> G
        end
        Chave --> Visao
        Chave --> Rag
    end

    Groq["Groq<br/>openai/gpt-oss-20b"]
    Gemini["Gemini<br/>gemini-3.5-flash-lite<br/>(reserva)"]

    App -- "foto, cultura, relato" --> Java
    Java -- "multipart: imagem, cultura" --> Visao
    Java -- "JSON: cultura, sintomas, classes" --> Rag
    G -- "trechos + relato mascarado" --> Groq
    G -. "erro, timeout ou 429" .-> Gemini
    Java -- "triagem, explicação e fontes" --> App
```

| Componente | Onde roda | Modelo ou dado | Arquivo |
| --- | --- | --- | --- |
| Qualidade | Serviço de IA, CPU | Regras com limites calibrados | `app/visao/qualidade.py` |
| Portão | Serviço de IA, CPU | `openai/clip-vit-base-patch32` (Hugging Face, local) | `app/visao/portao.py` |
| Classificador | Serviço de IA, CPU | `modelos/visao.pt` e `modelos/visao.json` (notebook de treino) | `app/visao/classificador.py` |
| Índice | Serviço de IA, CPU | `modelos/indice/` gerado de `dados/fichas/` com `intfloat/multilingual-e5-small` | `app/rag/indice.py` |
| LLM principal | Groq (externo) | `openai/gpt-oss-20b` | `app/rag/llm.py` |
| LLM reserva | Google (externo) | `gemini-3.5-flash-lite` pelo endpoint compatível com OpenAI | `app/rag/llm.py` |

Todos os modelos são carregados uma vez no início do serviço (`lifespan`). Se um falhar, o serviço sobe assim mesmo, `/health` mostra o componente como `indisponivel` e só a rota que depende dele responde 503.

## Fluxo de uma triagem

```mermaid
sequenceDiagram
    autonumber
    participant App
    participant Java as API Java
    participant Visao as Serviço de IA<br/>visão
    participant Rag as Serviço de IA<br/>RAG
    participant LLM as Groq / Gemini

    App->>Java: foto, cultura, descrição
    Java->>Visao: imagem + cultura (X-API-Key)
    Note over Visao: qualidade → portão → classificador<br/>imagem só em memória, EXIF descartado
    Visao-->>Java: imagemValida, motivo, culturaDetectada, top 3
    Java->>Rag: cultura, sintomas, classes (vazias se a foto foi recusada)
    Note over Rag: mascara e-mail, telefone, CPF, CEP, coordenadas e nome<br/>busca local no índice
    alt há trecho acima do score mínimo
        Rag->>LLM: prompt com trechos numerados e relato mascarado
        LLM-->>Rag: explicação
        Note over Rag: guardrail: dose, produto ou sem citação<br/>vira texto fixo
    else nenhum trecho relevante
        Note over Rag: texto fixo, sem chamar o LLM
    end
    Rag-->>Java: trechos, explicação, modeloLlm
    Java-->>App: triagem com explicação e fontes
```

## O que nunca sai do serviço

| Dado | O que acontece |
| --- | --- |
| Foto da folha | Lida só em memória, nunca gravada em disco e nunca enviada a serviço externo. Qualidade, CLIP e classificador rodam localmente |
| Metadados da foto (EXIF, GPS, câmera, ICC) | Descartados ao abrir a imagem; só os pixels seguem |
| Embeddings e índice | Calculados localmente com o e5-small; nenhuma consulta vai a API de embeddings |
| E-mail, telefone, CPF, CEP, coordenadas e nome de quem se identifica no relato | Trocados por `[removido]` antes da busca e antes do prompt |
| Chaves (`IA_API_KEY`, `LLM_API_KEY`, `LLM_FALLBACK_API_KEY`) | Só no `.env` ou nas variáveis do ambiente; nunca no código, no log ou na resposta |
| Conteúdo das requisições | Os logs guardam id, rota, status, latência por camada e motivo; nunca imagem, relato ou cabeçalhos |

Sai do serviço apenas o prompt enviado ao LLM: cultura, nomes das suspeitas, relato já mascarado e os trechos das fichas. Limitação conhecida: o mascaramento usa padrões e pega o nome de quem se identifica ("sou o...", "meu nome é..."), como no caso l09 de `avaliacao/llm/resultados.json`, mas não um nome solto no meio do texto; por isso a API Java não deve incluir o nome do produtor no campo `sintomas`.

## Decisões

- **Três camadas na visão:** a qualidade é barata (cerca de 1 ms) e recusa a foto ruim antes de gastar CPU com o CLIP; o portão recusa o que está fora do que o classificador conhece; o classificador só vê folhas das três culturas.
- **numpy no lugar de banco vetorial:** 117 trechos de 384 dimensões ocupam cerca de 180 KB e a busca é um produto de matriz de menos de 1 ms. O índice é versionado e reconstruído por `scripts/construir_indice.py`.
- **Groq com Gemini de reserva:** plano gratuito nos dois. A Groq é a primeira opção porque permite ligar Zero Data Retention na organização; no plano gratuito do Gemini o conteúdo pode ser usado pelo Google, por isso ele só entra quando a Groq falha. O raciocínio do `gpt-oss` é desligado na resposta (`include_reasoning: false`).
- **Explicação fixa:** sem trecho relevante ou com resposta barrada pelo guardrail, o produtor recebe um texto seguro que encaminha ao agrônomo, e `modeloLlm` vem `null`.
