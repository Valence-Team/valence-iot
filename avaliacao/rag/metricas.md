# Avaliação da recuperação (RAG)

Gerado em 2026-11-15T16:11:31Z com 40 consultas (10 sobre pragas fora do modelo de visão).

| Modelo | Bônus de classe | hit@1 | hit@3 | MRR | hit@1 fora do modelo |
| --- | --- | --- | --- | --- | --- |
| `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` | não | 0.375 | 0.600 | 0.538 | 0.200 |
| `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` | sim, todas as classes | 0.450 | 0.700 | 0.610 | 0.200 |
| `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` | sim, exceto saudável (usado no serviço) | 0.450 | 0.700 | 0.610 | 0.200 |
| `intfloat/multilingual-e5-small` | não | 0.875 | 0.950 | 0.913 | 0.800 |
| `intfloat/multilingual-e5-small` | sim, todas as classes | 0.850 | 0.950 | 0.905 | 0.600 |
| `intfloat/multilingual-e5-small` | sim, exceto saudável (usado no serviço) | 0.900 | 0.950 | 0.930 | 0.800 |

## Corte por score mínimo

| Modelo | Score mínimo | Relevantes acima | Sem resposta cortadas |
| --- | --- | --- | --- |
| `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` | 0.5 | 1.00 | 0.40 |
| `intfloat/multilingual-e5-small` | 0.85 | 1.00 | 0.20 |

Varredura do limiar na busca do serviço (cultura, nomes das classes, sintomas e bônus):

| Modelo | Limiar | Relevantes acima | Sem resposta cortadas |
| --- | --- | --- | --- |
| `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` | 0.38 | 1.000 | 0.20 |
| `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` | 0.49 | 1.000 | 0.40 |
| `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` | 0.51 | 0.975 | 0.60 |
| `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` | 0.53 | 0.975 | 0.80 |
| `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` | 0.61 | 0.950 | 0.80 |
| `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` | 0.63 | 0.925 | 1.00 |
| `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` | 0.64 | 0.900 | 1.00 |
| `intfloat/multilingual-e5-small` | 0.85 | 1.000 | 0.20 |
| `intfloat/multilingual-e5-small` | 0.86 | 1.000 | 0.40 |
| `intfloat/multilingual-e5-small` | 0.87 | 0.925 | 0.80 |

## Erros de topo (bônus exceto saudável)

- `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`: c04 esperava milho-ferrugem-comum, veio milho-monitoramento, c05 esperava milho-ferrugem-comum, veio milho-cercosporiose, c07 esperava milho-helmintosporiose, veio milho-monitoramento, c09 esperava tomate-pinta-preta, veio tomate-mancha-alvo, c10 esperava tomate-pinta-preta, veio tomate-monitoramento, c13 esperava tomate-septoriose, veio tomate-pinta-preta, c14 esperava tomate-septoriose, veio murcha-bacteriana, c17 esperava tomate-mancha-alvo, veio tomate-monitoramento, c19 esperava tomate-mancha-bacteriana, veio tomate-mancha-alvo, c20 esperava tomate-begomovirose, veio tomate-mosaico, c21 esperava tomate-begomovirose, veio tomate-monitoramento, c23 esperava tomate-mosaico, veio tomate-monitoramento, c28 esperava batata-requeima, veio murcha-bacteriana, c29 esperava batata-pinta-preta, veio murcha-bacteriana, c31 esperava milho-cigarrinha-enfezamentos, veio milho-monitoramento, c32 esperava milho-cigarrinha-enfezamentos, veio milho-cercosporiose, c34 esperava milho-lagarta-do-cartucho, veio milho-monitoramento, c35 esperava tomate-traca-do-tomateiro, veio tomate-monitoramento, c36 esperava tomate-mosca-branca, veio tomate-monitoramento, c37 esperava tomate-vira-cabeca, veio tomate-acaro-rajado, c38 esperava batata-canela-preta, veio murcha-bacteriana, c40 esperava murcha-bacteriana, veio batata-monitoramento
- `intfloat/multilingual-e5-small`: c23 esperava tomate-mosaico, veio tomate-mofo-das-folhas, c25 esperava tomate-acaro-rajado, veio tomate-mancha-alvo, c31 esperava milho-cigarrinha-enfezamentos, veio milho-monitoramento, c36 esperava tomate-mosca-branca, veio tomate-begomovirose
