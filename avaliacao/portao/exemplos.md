# Portão e qualidade nas fotos de exemplo

Medido em 17/11/2026 com `datasets/portao/sondar.py`, limites de `avaliacao/portao/calibracao.md` (outra planta 0.55, não é planta 0.34, nitidez mínima 2.6).

| Foto | Brilho | Nitidez | Culturas do escopo | Outra planta | Não é planta | Resultado |
| --- | --- | --- | --- | --- | --- | --- |
| `batata_pinta_preta.jpg` | 138.8 | 10389.0 | 0.8747 | 0.1252 | 0.0001 | Aceita |
| `milho_ferrugem_campo.jpg` | 100.1 | 1230.8 | 0.9182 | 0.0797 | 0.0021 | Aceita |
| `milho_ferrugem_comum.jpg` | 67.3 | 3098.7 | 0.9209 | 0.0791 | 0.0000 | Aceita |
| `tomate_borrada.jpg` | 111.6 | 2.5 | 0.0475 | 0.9214 | 0.0311 | IMAGEM_BORRADA |
| `tomate_requeima.jpg` | 111.6 | 4477.1 | 0.0995 | 0.8979 | 0.0025 | CULTURA_FORA_DO_ESCOPO |

A qualidade é avaliada antes do portão, então `tomate_borrada.jpg` é recusada como IMAGEM_BORRADA. `tomate_requeima.jpg` é uma folha de tomate real recusada pelo portão: o CLIP dá 0.90 para "outra planta", acima até do limite anterior (0.60). É um exemplo de falsa recusa.
