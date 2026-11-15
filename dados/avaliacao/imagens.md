# Imagens de avaliação do portão

Conjuntos usados por `scripts/avaliar_portao.py` para medir a camada de qualidade e o portão CLIP. Nenhuma imagem é versionada: as pastas ficam em `datasets/portao/`, que está no `.gitignore`. Só as métricas vão para `avaliacao/portao/metricas.json`.

## Conjuntos

| Conjunto | Resultado esperado | Origem | Licença | Recorte usado |
| --- | --- | --- | --- | --- |
| `plantvillage_teste` | Passar (`ACEITA`) | PlantVillage, cópia oficial no Hugging Face: [`mohanty/PlantVillage`](https://huggingface.co/datasets/mohanty/PlantVillage) | CC BY-SA 3.0 | Versão `color`, divisão oficial de teste (`splits/color_test.txt`), só milho, tomate e batata (4.841 imagens). É o mesmo teste do notebook de treino |
| `plantvillage_outras` | `CULTURA_FORA_DO_ESCOPO` | Mesmo repositório | CC BY-SA 3.0 | Mesma divisão de teste, só as outras 11 culturas: maçã, mirtilo, cereja, uva, laranja, pêssego, pimentão, framboesa, soja, abóbora e morango (5.868 imagens) |
| `plantdoc_outras` | `CULTURA_FORA_DO_ESCOPO` | PlantDoc, original em [`pratikkayal/PlantDoc-Dataset`](https://github.com/pratikkayal/PlantDoc-Dataset); cópia usada: [`Project-AgML/plant_doc_classification`](https://huggingface.co/datasets/Project-AgML/plant_doc_classification) | Original CC BY 4.0; a cópia do AgML declara CC BY-SA 4.0 | Todas as classes que não são de milho, tomate ou batata (1.229 de 2.569 imagens). Fotos de campo e da internet, com fundo real |
| `imagenette` | `NAO_E_PLANTA` | Imagenette, da fast.ai: [`fastai/imagenette`](https://github.com/fastai/imagenette), arquivo `imagenette2-320.tgz` | Repositório Apache 2.0. As imagens são um recorte do ImageNet e seguem os termos de acesso do ImageNet: uso não comercial, de pesquisa e ensino, sem redistribuição | Pasta `val`, só cinco classes: `n02979186` (cassette player), `n03028079` (church), `n03417042` (garbage truck), `n03425413` (gas pump) e `n03445777` (golf ball). 1.973 imagens antes do filtro de pessoas |
| `plantvillage_teste_borrada` | `IMAGEM_BORRADA` | Gerada em memória a partir de `plantvillage_teste` | Mesma do PlantVillage | Desfoque gaussiano com raio `max(2, menor lado / 48)` |
| `plantvillage_teste_escurecida` | `IMAGEM_ESCURA` | Gerada em memória a partir de `plantvillage_teste` | Mesma do PlantVillage | Brilho multiplicado por 0,15 |

Referências:

- Hughes, D. P.; Salathé, M. *An open access repository of images on plant health to enable the development of mobile disease diagnostics*. arXiv:1511.08060, 2015.
- Mohanty, S. P.; Hughes, D. P.; Salathé, M. *Using Deep Learning for Image-Based Plant Disease Detection*. Frontiers in Plant Science, 7:1419, 2016.
- Singh, D. et al. *PlantDoc: A Dataset for Visual Plant Disease Detection*. CoDS-COMAD 2020.
- Howard, J. *Imagenette*. fast.ai, 2019. Subconjunto de Deng, J. et al. *ImageNet: A Large-Scale Hierarchical Image Database*. CVPR 2009.

## Por que estes conjuntos

- **PlantVillage de teste das três culturas:** é a entrada que o portão nunca pode recusar. A taxa de falsa rejeição sai daqui.
- **PlantVillage de outras culturas:** mesma câmera e mesmo fundo do conjunto aceito. Isola a pergunta "o portão reconhece a cultura?" sem a ajuda do fundo.
- **PlantDoc de outras culturas:** fotos de campo de folhas que não são milho, tomate nem batata. Mede o caso real de um produtor que fotografa outra planta.
- **Imagenette em cinco classes:** objetos, prédios e veículos sem relação com plantas. As cinco classes evitam as que são de animais (tench, english springer) e as que costumam ter pessoas em primeiro plano (chain saw, french horn, parachute).
- **Versões degradadas:** a mesma folha que passa, borrada ou escura, tem de ser recusada pelo motivo certo. Assim o teste da camada de qualidade não depende de achar fotos ruins de verdade.

## Nenhuma imagem com pessoas

Mesmo nas cinco classes escolhidas, o Imagenette tem pessoas: frentistas e clientes no posto, golfistas, motoristas e garis junto ao caminhão. O script tira essas imagens antes de avaliar:

1. **Detector de pessoas:** Faster R-CNN MobileNetV3 do torchvision, treinado no COCO, com limite de 0,3 para a classe `person`. O limite é baixo de propósito: tirar uma imagem sem pessoa só diminui um pouco a amostra, e deixar uma com pessoa não é aceitável. Os pesos (74 MB) são baixados pelo torchvision na primeira execução.
2. **Revisão manual:** com `--revisao PASTA`, o script grava uma folha de miniaturas numeradas de cada conjunto, só com as imagens que sobraram, e um `.txt` com o nome de cada número. Quem roda a avaliação confere as folhas. Uma pessoa que o detector não achou entra em `EXCLUIDAS_NA_REVISAO`, no script, e a avaliação roda de novo.
3. **Registro:** `metricas.json` lista em `arquivosExcluidosPorPessoas` cada arquivo retirado, por conjunto.

Revisão feita em 15/11/2026 numa amostra de 75 imagens do Imagenette (as 15 primeiras de cada classe, em ordem de nome), 60 do PlantVillage de teste, 60 do PlantVillage de outras culturas e 60 do PlantDoc de outras culturas:

| Conjunto | Retiradas pelo detector | Retiradas na revisão | Pessoas na folha de revisão final |
| --- | --- | --- | --- |
| PlantVillage de teste | 3 de 60 (folhas, alarme falso) | 0 | 0 |
| PlantVillage de outras culturas | 8 de 60 (folhas, alarme falso) | 0 | 0 |
| PlantDoc de outras culturas | 4 de 60 | 0 | 0 |
| Imagenette | 19 de 75 (frentistas, clientes, golfista, mão com bola, motoristas e pedestres) | 2: `ILSVRC2012_val_00020781.JPEG` (perna de golfista) e `ILSVRC2012_val_00034001.JPEG` (motorista visível na cabine) | 0 |

Os alarmes falsos em folhas só reduzem a amostra. A avaliação completa da Etapa 2 usa outra amostra; as folhas de revisão dela precisam ser conferidas antes de publicar as métricas.

## Montagem das pastas

O script lê qualquer pasta com `.jpg`, `.jpeg`, `.png` ou `.webp`, inclusive em subpastas. Estrutura esperada:

```text
datasets/portao/
├── plantvillage_teste/      fotos do teste oficial de milho, tomate e batata
├── plantvillage_outras/     fotos do teste oficial das outras 11 culturas
├── plantdoc_outras/         fotos do PlantDoc fora das três culturas
└── imagenette/              imagenette2-320/val/<wnid>/ das cinco classes
```

1. **PlantVillage:** baixar `splits/color_test.txt` do repositório `mohanty/PlantVillage` com o `huggingface_hub` e extrair do `data.zip` (2,2 GB) só os arquivos listados ali. O zip pode ser lido por faixa com `HfFileSystem().open("datasets/mohanty/PlantVillage/data.zip")` e `zipfile.ZipFile`, sem baixar o arquivo inteiro. A cultura é o trecho antes de `___` na pasta da classe (`Corn_(maize)`, `Tomato` e `Potato` vão para `plantvillage_teste`; o resto, para `plantvillage_outras`).
2. **PlantDoc:** `datasets.load_dataset("Project-AgML/plant_doc_classification", split="train")` e salvar como JPEG as imagens cujo rótulo não começa com `Corn`, `Tomato` ou `Potato`.
3. **Imagenette:** baixar `https://s3.amazonaws.com/fast-ai-imageclas/imagenette2-320.tgz` (342 MB) e extrair só as cinco pastas de `imagenette2-320/val` listadas acima.

Comando de avaliação, com amostra fixa de 300 imagens por conjunto (semente 42):

```bash
python -m scripts.avaliar_portao \
    --aceitas plantvillage_teste=datasets/portao/plantvillage_teste \
    --fora-do-escopo plantvillage_outras=datasets/portao/plantvillage_outras \
                     plantdoc_outras=datasets/portao/plantdoc_outras \
    --nao-planta imagenette=datasets/portao/imagenette \
    --degradar plantvillage_teste \
    --maximo 300 \
    --revisao datasets/portao/revisao
```

## Limitações

- O PlantVillage é de laboratório, com fundo liso. Uma foto de milho tirada no campo pode ter brilho e nitidez diferentes; o PlantDoc cobre o campo só para as culturas de fora.
- Não há conjunto real de fotos escuras, claras ou de baixa resolução: esses motivos são medidos com degradações sintéticas, e `IMAGEM_CLARA` e `RESOLUCAO_BAIXA` só aparecem como falsa rejeição.
- O Imagenette tem fotos de objetos bem enquadrados. Fotos tiradas por engano no campo (chão, céu, mão) não estão representadas, e mãos ficam de fora pelo filtro de pessoas.
