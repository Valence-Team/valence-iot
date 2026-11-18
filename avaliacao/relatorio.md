# Relatório de avaliação do serviço de IA

Este relatório reúne a avaliação de cada parte do serviço de IA do Valence: visão (qualidade, portão e classificador), recuperação de trechos (RAG), explicação pelo LLM e latência. Todo número vem de um arquivo da pasta `avaliacao/`, indicado em cada seção.

## 1. Resumo

| Parte | Resultado principal | Arquivo |
| --- | --- | --- |
| Classificador em laboratório (PlantVillage) | F1 macro na cultura 0.968, acurácia 0.972 | `visao/resumo.json` |
| Classificador em fotos de campo (PlantDoc) | F1 macro na cultura 0.534, doença certa no top 3 em 92.2% | `visao/campo.csv` |
| Calibração | ECE de 0.220 para 0.013 | `visao/resumo.json` |
| Qualidade da foto | Recusa 100% das escuras, borradas e de baixa resolução | `portao/metricas.json` |
| Portão | Aceita 90.1% das fotos válidas, recusa 97.4% do que não é planta | `portao/metricas.json` |
| RAG | hit@1 0.900, hit@3 0.950, MRR 0.930 | `rag/metricas.md` |
| LLM | 12 de 12 sem dose ou produto, com fonte e com agrônomo; nenhum dado pessoal no prompt; nota humana de fundamentação média 2.83 de 3 | `llm/resultados.json` |
| Latência (mediana) | Visão cerca de 237 ms, busca 48 ms, LLM 573 ms | `latencia.json` |

O serviço faz triagem, não diagnóstico. Quando a foto é recusada ou a confiança fica abaixo de 0.6, o caso segue para o agrônomo.

## 2. Classificador em laboratório

Dados: PlantVillage, 17 classes de milho, tomate e batata, com divisão estratificada por classe (`visao/resumo.json`). A maior classe tem 35 vezes mais imagens que a menor, por isso o treino usa perda ponderada e a métrica principal é o F1 macro.

| Modelo | Acurácia | F1 macro | F1 macro na cultura | Tamanho | Latência CPU |
| --- | --- | --- | --- | --- | --- |
| **MobileNetV3-Large** | 0.9803 | **0.9763** | 0.9778 | 17.1 MB | **32.6 ms** |
| EfficientNet-B0 | 0.9741 | 0.9643 | 0.9711 | 16.4 MB | 42.4 ms |

Fonte: `visao/comparacao.csv`. A MobileNetV3-Large foi escolhida por ter F1 maior e ser mais rápida em CPU. "Na cultura" significa que a doença é escolhida só entre as classes da cultura informada pelo produtor, que é o que a API devolve.

Figuras: `visao/curvas_treino.png`, `visao/confusao_plantvillage_mobilenet_v3_large.png`, `visao/confusao_plantvillage_efficientnet_b0.png`.

## 3. Classificador em fotos de campo

O PlantDoc tem fotos reais, com fundo, sombra e várias folhas. O teste usa 268 imagens (`visao/limitacoes.md`).

| Métrica | Sem ajuste fino | Com ajuste fino |
| --- | --- | --- |
| F1 macro na cultura, PlantVillage | 0.9778 | 0.9682 |
| F1 macro na cultura, PlantDoc | 0.2505 | **0.5340** |
| Acurácia na cultura, PlantDoc | 0.2836 | 0.5485 |
| Top 3 na cultura, PlantDoc | 0.7500 | **0.9216** |
| Cultura divergente, PlantDoc | 0.1343 | 0.0709 |

Fonte: `visao/campo.csv`. A queda de 0.978 para 0.250 mostra que as fotos de laboratório superestimam o desempenho real. O ajuste fino com fotos de campo dobrou o F1 no PlantDoc e custou 0.01 no PlantVillage, por isso o modelo com ajuste foi para produção. Como o app mostra as três hipóteses mais prováveis, o top 3 de 92% é o número que o produtor e o agrônomo sentem na prática.

Figuras: `visao/confusao_plantdoc_sem_ajuste.png`, `visao/confusao_plantdoc_com_ajuste.png`, `visao/gradcam_plantvillage.png`, `visao/gradcam_plantdoc.png`.

## 4. Calibração e cobertura

| Métrica | Antes | Depois (T = 0.480) |
| --- | --- | --- |
| ECE | 0.2205 | 0.0127 |
| NLL | 0.4155 | 0.2069 |

Fonte: `visao/resumo.json`. A temperatura menor que 1 indica que o modelo estava confiante de menos, efeito do label smoothing e da perda ponderada. Com o limite de confiança 0.6, dentro da cultura, passam 97.8% das fotos, com acurácia de 96.4% nessas fotos. Figuras: `visao/confiabilidade_producao_mobilenet_v3_large.png` e `visao/cobertura_producao_mobilenet_v3_large.png`.

## 5. Qualidade da foto e portão

Os limites foram escolhidos no conjunto de calibração (`portao/calibracao.md`) e medidos em um conjunto de teste separado, com até 150 imagens por conjunto. Imagens com pessoas foram excluídas por um detector antes da avaliação.

| Conjunto de teste | Esperado | Acerto |
| --- | --- | --- |
| PlantVillage, culturas do escopo | Aceitar | 0.9067 |
| PlantDoc, culturas do escopo | Aceitar | 0.8939 |
| PlantVillage escurecida | IMAGEM_ESCURA | 1.0000 |
| PlantVillage borrada | IMAGEM_BORRADA | 1.0000 |
| PlantVillage reduzida | RESOLUCAO_BAIXA | 1.0000 |
| PlantVillage clareada | IMAGEM_CLARA | 0.9333 |
| Imagenette (objetos) | NAO_E_PLANTA | 0.9737 |
| PlantVillage, outras culturas | CULTURA_FORA_DO_ESCOPO | 0.2600 |
| PlantDoc, outras culturas | CULTURA_FORA_DO_ESCOPO | 0.3333 |

Fonte: `portao/metricas.json`. Limites usados: brilho entre 30 e 195, nitidez mínima 2.6, outra planta 0.55, não é planta 0.34.

A qualidade e a recusa do que não é planta funcionam bem. O ponto fraco é separar a folha de outra cultura: o portão recusa só 29.5% delas e aceita 54.7%. A segunda barreira é o classificador, que recusa como CULTURA_DIVERGENTE quando a soma das classes de outra cultura passa de 0.7. Mesmo assim, uma folha de pimentão enviada como tomate pode receber uma hipótese de doença de tomate, e por isso a confirmação do agrônomo é obrigatória.

## 6. Recuperação de trechos (RAG)

Avaliação com 40 consultas escritas como o produtor escreveria, 10 delas sobre pragas que o modelo de visão não reconhece (`rag/metricas.md`).

| Modelo de embeddings | hit@1 | hit@3 | MRR | hit@1 fora do modelo de visão |
| --- | --- | --- | --- | --- |
| paraphrase-multilingual-MiniLM-L12-v2 | 0.450 | 0.700 | 0.610 | 0.200 |
| **multilingual-e5-small** | **0.900** | **0.950** | **0.930** | **0.800** |

Os dois com o bônus de classe usado no serviço. O e5-small foi escolhido. Com o score mínimo de 0.85, todos os trechos relevantes passam e 20% das consultas sem resposta são cortadas.

## 7. Explicação pelo LLM

Doze casos: 8 normais, 2 com dados pessoais no relato e 2 com tentativa de injeção pedindo dose (`llm/resultados.json`).

| Checagem automática | Aprovados |
| --- | --- |
| Explicação gerada | 12 |
| Em português | 12 |
| Até 120 palavras | 11 |
| Cita fonte [n] | 12 |
| Sem dose nem produto | 12 |
| Menciona o agrônomo | 12 |
| Dado pessoal ausente do prompt enviado | 12 |

O modelo principal é o `openai/gpt-oss-20b` na Groq. Durante a avaliação, o limite de requisições da Groq foi atingido em 4 casos e o serviço respondeu com o reserva `gemini-3.5-flash-lite` sem erro para o usuário. A mediana de duração foi de 794 ms; no reserva, de 1.6 a 3.9 s. A nota humana de fundamentação (1 a 3) de cada caso fica no campo `notaHumanaFundamentacao`.

| Nota humana de fundamentação | Casos |
| --- | --- |
| 3: toda afirmação apoiada nos trechos citados | 10 |
| 2: parcialmente fundamentada | 2 (l03 e l08, ambos do `gpt-oss-20b`) |
| 1: sem base nos trechos | 0 |
| **Média** | **2.83** (34 de 36 pontos) |

Os quatro casos respondidos pelo reserva receberam nota 3.

## 8. Latência por etapa

Medida em notebook com processador AMD de 4 threads, sem GPU, em 100 execuções sobre as fotos de exemplo e 3 chamadas ao LLM (`latencia.json`).

| Etapa | Mediana | p95 |
| --- | --- | --- |
| Abertura da imagem | 1.1 ms | 7.2 ms |
| Qualidade | 0.6 ms | 7.1 ms |
| Portão (CLIP) | 196.6 ms | 276.8 ms |
| Classificador | 38.2 ms | 54.9 ms |
| Busca no índice | 47.7 ms | 64.8 ms |
| LLM | 572.8 ms | 764.9 ms |

Somando as medianas, a rota de visão leva cerca de 237 ms e a de RAG cerca de 620 ms. O portão é a etapa mais cara da visão.

## 9. Casos de falha

1. **Folha de tomate recusada pelo portão.** `dados/exemplos/tomate_requeima.jpg` recebe 0.90 de "outra planta" e volta como CULTURA_FORA_DO_ESCOPO (`portao/exemplos.md`). Cerca de 9% das fotos válidas têm esse destino (`portao/metricas.json`). O app pede outra foto e o relato segue para o RAG sem as classes.
2. **Folha de outra cultura aceita.** 54.7% das folhas de outras culturas passam pelo portão (`portao/metricas.json`).
3. **Doenças parecidas no campo.** Mancha-bacteriana, pinta-preta e mofo-das-folhas do tomate ficam com F1 entre 0.19 e 0.24 no PlantDoc (`visao/limitacoes.md`).
4. **Explicação longa no reserva.** O Gemini passou do limite de 120 palavras em 1 caso, com 133 palavras (`llm/resultados.json`).
5. **Fotos de PlantDoc pequenas.** 9 de 132 fotos de campo válidas foram recusadas por RESOLUCAO_BAIXA (`portao/metricas.json`).

## 10. Limitações

- O teste de campo tem 268 imagens e não tem milho saudável, batata saudável, ácaro-rajado nem mancha-alvo (`visao/limitacoes.md`).
- O PlantVillage não traz identificador da folha, então fotos da mesma folha podem estar em treino e teste e inflar o resultado de laboratório.
- Pragas como cigarrinha-do-milho, lagarta-do-cartucho e traça-do-tomateiro não têm classe de visão. Elas dependem do relato e do RAG, que acerta o primeiro trecho em 80% dessas consultas.
- O mascaramento de dados pessoais usa padrões: pega e-mail, telefone, CPF, CEP, coordenadas e o nome de quem se identifica ("sou o...", "meu nome é..."), mas não um nome solto no meio do texto.
- As latências foram medidas em um notebook e mudam no computador da apresentação.
