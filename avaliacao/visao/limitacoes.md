# Limitações do modelo de visão

- **Laboratório x campo.** F1 macro na cultura de 0.978 no PlantVillage contra 0.250 no PlantDoc sem ajuste. A diferença de 0.727 mostra que fotos de laboratório superestimam o desempenho real.
- **Ajuste fino.** Com fotos de campo no treino, o F1 macro na cultura no PlantDoc foi para 0.534. Vai para produção o modelo com ajuste fino: o F1 macro na cultura no PlantDoc subiu de 0.2505 para 0.5340 e no PlantVillage foi de 0.9778 para 0.9682.
- **Classes mais fracas no campo:** tomate_mancha_bacteriana (F1 0.19, 22 imagens); tomate_pinta_preta (F1 0.24, 18 imagens); tomate_mofo_das_folhas (F1 0.24, 18 imagens).
- **Teste de campo pequeno.** O teste do PlantDoc tem 268 imagens. Classes sem imagem no teste: milho_saudavel, batata_saudavel, tomate_acaro_rajado, tomate_mancha_alvo. Com menos de 10: nenhuma. Os números por classe nesses casos têm variação alta.
- **Divisão do PlantVillage:** estratificada por classe no teste e estratificada por classe na validação. Sem identificador de folha, fotos da mesma folha podem estar em treino e teste, o que pode inflar o resultado de laboratório.
- **Calibração.** ECE de 0.220 para 0.013 com T = 0.480. No limite 0.6, dentro da cultura, passam 97.8% das fotos com acurácia de 96.4%; o resto vai direto para o agrônomo.
- **Cultura divergente.** No PlantDoc, 7.1% das fotos corretas seriam recusadas como CULTURA_DIVERGENTE (limite 0.7).
- **Latência.** 32.6 ms por imagem em CPU do Colab com 2 threads, só a rede. No servidor da apresentação o valor muda e precisa ser medido de novo.
- **Fora do modelo.** Pragas como cigarrinha-do-milho, lagarta-do-cartucho e traça-do-tomateiro não têm classe; o ácaro do PlantDoc foi ignorado por ter 2 imagens. Esses casos dependem do relato de sintomas (RAG) e do agrônomo.
- **Uma folha por foto.** O modelo foi treinado com uma folha centralizada; fotos de planta inteira ou de várias folhas tendem a errar mais.
- **Grad-CAM é qualitativo.** As figuras mostram 12 exemplos e servem para discussão, não como prova de que o modelo sempre olha a lesão.