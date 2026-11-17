# Calibração da qualidade e do portão

Medidas de 1272 imagens dos conjuntos de calibração (validação do PlantVillage, metade do PlantDoc e do Imagenette e versões degradadas da validação). Nenhuma imagem do teste entra aqui.

Critério: J = média da rejeição correta por motivo - falsa rejeição (média de laboratório e campo), com falsa rejeição de no máximo 10%; qualidade primeiro, portão depois.

## Limites

| Limite | Antes | Escolhido |
| --- | --- | --- |
| Menor lado mínimo (px) | 224 | 224 |
| Brilho médio mínimo | 40.0 | 30.0 |
| Brilho médio máximo | 220.0 | 195.0 |
| Variância do Laplaciano mínima | 60.0 | 2.6 |
| Portão: outra planta | 0.6 | 0.55 |
| Portão: não é planta | 0.5 | 0.34 |

## Resultado na calibração

| Medida | Antes | Depois |
| --- | --- | --- |
| Rejeição correta RESOLUCAO_BAIXA | 1.000 | 1.000 |
| Rejeição correta IMAGEM_ESCURA | 1.000 | 1.000 |
| Rejeição correta IMAGEM_CLARA | 0.813 | 0.953 |
| Rejeição correta IMAGEM_BORRADA | 1.000 | 1.000 |
| Rejeição correta CULTURA_FORA_DO_ESCOPO | 0.289 | 0.299 |
| Rejeição correta NAO_E_PLANTA | 0.935 | 0.953 |
| Falsa rejeição (PlantVillage) | 0.080 | 0.087 |
| Falsa rejeição (PlantDoc das 3 culturas) | 0.107 | 0.107 |
| J | 0.746 | 0.771 |

## Fronteira da etapa de qualidade

Melhor rejeição correta média para cada nível de falsa rejeição.

| Falsa rejeição | Rejeição correta média | Brilho mín. | Brilho máx. | Nitidez mín. | Outra planta | Não é planta |
| --- | --- | --- | --- | --- | --- | --- |
| 0.034 | 0.933 | 30.0 | 225.0 | 2.6 | 1.0 | 1.0 |
| 0.042 | 0.970 | 30.0 | 215.0 | 2.6 | 1.0 | 1.0 |
| 0.053 | 0.988 | 30.0 | 190.0 | 2.6 | 1.0 | 1.0 |
| 0.064 | 0.992 | 30.0 | 170.0 | 2.6 | 1.0 | 1.0 |
| 0.067 | 0.992 | 30.0 | 170.0 | 27.0 | 1.0 | 1.0 |
| 0.082 | 0.992 | 30.0 | 170.0 | 46.3 | 1.0 | 1.0 |
| 0.085 | 0.992 | 30.0 | 170.0 | 50.7 | 1.0 | 1.0 |
| 0.095 | 0.992 | 30.0 | 170.0 | 66.4 | 1.0 | 1.0 |
| 0.114 | 0.992 | 30.0 | 170.0 | 79.4 | 1.0 | 1.0 |
| 0.121 | 0.992 | 30.0 | 170.0 | 86.9 | 1.0 | 1.0 |
| 0.128 | 0.992 | 30.0 | 170.0 | 95.1 | 1.0 | 1.0 |
| 0.139 | 0.992 | 30.0 | 170.0 | 149.0 | 1.0 | 1.0 |
| 0.150 | 0.992 | 30.0 | 170.0 | 163.0 | 1.0 | 1.0 |
| 0.161 | 0.990 | 30.0 | 180.0 | 178.3 | 1.0 | 1.0 |
| 0.165 | 0.992 | 30.0 | 170.0 | 178.3 | 1.0 | 1.0 |
| 0.180 | 0.992 | 30.0 | 170.0 | 213.3 | 1.0 | 1.0 |
| 0.188 | 0.992 | 30.0 | 170.0 | 233.4 | 1.0 | 1.0 |

## Fronteira da etapa de portão

Melhor rejeição correta média para cada nível de falsa rejeição.

| Falsa rejeição | Rejeição correta média | Brilho mín. | Brilho máx. | Nitidez mín. | Outra planta | Não é planta |
| --- | --- | --- | --- | --- | --- | --- |
| 0.053 | 0.507 | 30.0 | 195.0 | 2.6 | 0.72 | 0.34 |
| 0.063 | 0.529 | 30.0 | 195.0 | 2.6 | 0.68 | 0.34 |
| 0.073 | 0.591 | 30.0 | 195.0 | 2.6 | 0.6 | 0.34 |
| 0.076 | 0.598 | 30.0 | 195.0 | 2.6 | 0.58 | 0.34 |
| 0.093 | 0.612 | 30.0 | 195.0 | 2.6 | 0.56 | 0.34 |
| 0.103 | 0.630 | 30.0 | 195.0 | 2.6 | 0.54 | 0.34 |
| 0.111 | 0.637 | 30.0 | 195.0 | 2.6 | 0.53 | 0.34 |
| 0.117 | 0.661 | 30.0 | 195.0 | 2.6 | 0.51 | 0.34 |
| 0.128 | 0.665 | 30.0 | 195.0 | 2.6 | 0.34 | 0.34 |
