# +mat (MaisMat)

Sistema pessoal para treinar velocidade em operações básicas e acompanhar o desempenho.
Feito com Flask + SQLite, roda localmente.

## Como rodar

```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
flask run                        # porta 5001, definida em .flaskenv
```

Abra http://127.0.0.1:5001. O banco é criado automaticamente em `instance/maismat.sqlite`.

## Funcionalidades

**Treino**
- 4 operações (+ − × ÷), com 3 dificuldades. Subtração nunca dá negativo e divisão é sempre exata.
- **Contra o tempo**: quantas você acerta em 30s / 1 / 2 / 5 min.
- **N questões**: 10 / 20 / 50 / 100 questões, medindo o tempo de cada uma.
- **Tabuada**: escolha as tabuadas (2 a 12), com multiplicação e/ou divisão.
- **Pontos fracos**: treina só as questões em que você mais erra ou demora.
- Atalhos: `Enter` envia, `Tab` pula, `Esc` encerra. Com "Enviar automaticamente", a resposta
  é enviada assim que você digita o número de dígitos da resposta certa.

**Acompanhamento**
- Histórico de sessões e detalhe de cada questão (resposta dada, tempo).
- Gráficos de evolução diária por operação (tempo médio e precisão).
- Pontos fracos: compara o tempo de cada questão com sua média na mesma operação e
  considera a taxa de erro (7×8 e 8×7 contam como a mesma questão). Usa só as 10
  tentativas mais recentes de cada questão, então o que você já dominou sai da lista.
- Meta diária (nº de questões), sequência de dias batendo a meta, recorde e calendário.

## Dados e migração

Toda resposta é gravada individualmente na tabela `attempts` (questão, resposta dada, correção,
tempo em ms, data/hora). Todas as estatísticas são calculadas a partir dela, então nada se perde.

- **Exportar**: na página Histórico, ou direto em `/exportar.json` (tudo) e
  `/exportar/respostas.csv` (uma linha por resposta).
- **Backup**: basta copiar o arquivo `instance/maismat.sqlite`.
- O esquema está em `maismat/schema.sql`.

## Testes

```bash
pytest
```
