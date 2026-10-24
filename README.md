![+mat](docs/banner.png)

Treino de velocidade nas quatro operações, com acompanhamento de desempenho.
Flask + SQLite, roda localmente.

## Rodando

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
flask run
```

Abra http://127.0.0.1:5001.

## Recursos

- **Modos:** contra o tempo, N questões, tabuada e pontos fracos, em três dificuldades.
- **Desempenho:** calendário de atividade, resumo da semana, gráficos de evolução e linha do tempo de cada sessão.
- **Metas:** meta diária com sequência de dias e recorde.
- **Temas:** claro, escuro e Halloween, com confete opcional ao terminar.
- **Dados:** exportação em JSON e CSV; backup é copiar `instance/maismat.sqlite`.

Atalhos no treino: `Enter` envia, `Tab` pula, `Esc` encerra.

## Testes

```bash
pytest
```
