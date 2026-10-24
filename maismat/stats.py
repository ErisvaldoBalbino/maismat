"""Consultas de desempenho. Tudo é derivado da tabela `attempts`."""

from collections import defaultdict
from datetime import date, timedelta

from .db import get_db
from .problems import OPERATIONS

DEFAULT_DAILY_GOAL = 50  # questões por dia


def _summary_from_rows(rows):
    total = len(rows)
    correct = sum(r["correct"] for r in rows)
    correct_times = [r["time_ms"] for r in rows if r["correct"]]
    total_ms = sum(r["time_ms"] for r in rows)
    return {
        "total": total,
        "correct": correct,
        "wrong": total - correct,
        "accuracy": (correct / total) if total else None,
        "avg_ms": (sum(correct_times) / len(correct_times)) if correct_times else None,
        "total_ms": total_ms,
        # Acertos por minuto, usando o tempo efetivamente gasto respondendo.
        "per_minute": (correct / (total_ms / 60000)) if total_ms else None,
    }


def session_summary(session_id):
    rows = get_db().execute(
        "SELECT * FROM attempts WHERE session_id = ? ORDER BY id", (session_id,)
    ).fetchall()
    summary = _summary_from_rows(rows)
    by_op = defaultdict(list)
    for r in rows:
        by_op[r["op"]].append(r)
    summary["by_op"] = {op: _summary_from_rows(by_op[op]) for op in OPERATIONS if by_op[op]}
    summary["attempts"] = [dict(r) for r in rows]
    summary["timeline"] = timeline(summary["attempts"], summary["avg_ms"])
    return summary


def timeline(attempts, avg_ms=None):
    """Uma barra por questão, na ordem respondida, com altura proporcional ao tempo."""
    longest = max((a["time_ms"] for a in attempts), default=0)
    if not longest:
        return None
    return {
        "bars": [
            {"height": max(4, round(100 * a["time_ms"] / longest)), "attempt": a}
            for a in attempts
        ],
        "avg": round(100 * avg_ms / longest) if avg_ms else None,
        "total_ms": sum(a["time_ms"] for a in attempts),
    }


def list_sessions(limit=200):
    return get_db().execute(
        """
        SELECT s.*,
               COUNT(a.id)                                        AS total,
               COALESCE(SUM(a.correct), 0)                        AS correct,
               AVG(CASE WHEN a.correct = 1 THEN a.time_ms END)    AS avg_ms,
               COALESCE(SUM(a.time_ms), 0)                        AS total_ms
        FROM sessions s
        LEFT JOIN attempts a ON a.session_id = s.id
        GROUP BY s.id
        HAVING COUNT(a.id) > 0
        ORDER BY s.started_at DESC, s.id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()


def daily_series(days=90):
    """Evolução diária por operação: tempo médio (acertos) e precisão."""
    since = (date.today() - timedelta(days=days - 1)).isoformat()
    rows = get_db().execute(
        """
        SELECT substr(created_at, 1, 10)                       AS day,
               op,
               COUNT(*)                                        AS total,
               SUM(correct)                                    AS correct,
               AVG(CASE WHEN correct = 1 THEN time_ms END)     AS avg_ms
        FROM attempts
        WHERE substr(created_at, 1, 10) >= ?
        GROUP BY day, op
        ORDER BY day
        """,
        (since,),
    ).fetchall()

    days_list = sorted({r["day"] for r in rows})
    index = {(r["day"], r["op"]): r for r in rows}
    series = {}
    for op in OPERATIONS:
        if not any(r["op"] == op for r in rows):
            continue
        avg_ms, accuracy, total = [], [], []
        for d in days_list:
            r = index.get((d, op))
            avg_ms.append(round(r["avg_ms"]) if r and r["avg_ms"] is not None else None)
            accuracy.append(round(100 * r["correct"] / r["total"], 1) if r else None)
            total.append(r["total"] if r else 0)
        series[op] = {"avg_ms": avg_ms, "accuracy": accuracy, "total": total}

    volume = []
    for d in days_list:
        volume.append(sum(index[(d, op)]["total"] for op in OPERATIONS if (d, op) in index))
    return {"days": days_list, "series": series, "volume": volume}


def op_trends(today=None, window=7):
    """Por operação: últimos `window` dias comparados com os `window` anteriores."""
    today = today or date.today()
    start = (today - timedelta(days=window - 1)).isoformat()
    prev_start = (today - timedelta(days=2 * window - 1)).isoformat()
    rows = get_db().execute(
        """
        SELECT op,
               substr(created_at, 1, 10) >= ?                  AS recent,
               COUNT(*)                                        AS total,
               SUM(correct)                                    AS correct,
               AVG(CASE WHEN correct = 1 THEN time_ms END)     AS avg_ms
        FROM attempts
        WHERE substr(created_at, 1, 10) >= ?
        GROUP BY op, recent
        """,
        (start, prev_start),
    ).fetchall()
    data = {(r["op"], bool(r["recent"])): r for r in rows}

    trends = []
    for op in OPERATIONS:
        cur, prev = data.get((op, True)), data.get((op, False))
        if cur is None:
            continue
        trend = {
            "op": op,
            "total": cur["total"],
            "avg_ms": cur["avg_ms"],
            "accuracy": cur["correct"] / cur["total"],
            "delta_ms": None,
            "delta_accuracy": None,
        }
        if prev is not None:
            if cur["avg_ms"] is not None and prev["avg_ms"] is not None:
                trend["delta_ms"] = cur["avg_ms"] - prev["avg_ms"]
            trend["delta_accuracy"] = trend["accuracy"] - prev["correct"] / prev["total"]
        trends.append(trend)
    return trends


def _fact_key(op, a, b):
    # Adição e multiplicação são comutativas: 7×8 e 8×7 são o mesmo "fato".
    if op in ("add", "mul"):
        return (op, min(a, b), max(a, b))
    return (op, a, b)


def weak_facts(limit=15, min_attempts=2, recent=10):
    """Questões em que você mais erra ou demora, relativas à média da operação.

    Considera só as `recent` tentativas mais recentes de cada fato, para que um
    fato que você já dominou saia da lista.
    """
    rows = get_db().execute(
        "SELECT op, a, b, answer, correct, time_ms FROM attempts ORDER BY id DESC"
    ).fetchall()

    facts = defaultdict(list)
    op_times = defaultdict(list)
    for r in rows:
        key = _fact_key(r["op"], r["a"], r["b"])
        if len(facts[key]) < recent:
            facts[key].append(r)
        if r["correct"]:
            op_times[r["op"]].append(r["time_ms"])

    op_avg = {op: sum(t) / len(t) for op, t in op_times.items() if t}

    result = []
    for (op, a, b), attempts in facts.items():
        n = len(attempts)
        if n < min_attempts:
            continue
        errors = sum(1 for r in attempts if not r["correct"])
        times = [r["time_ms"] for r in attempts if r["correct"]]
        avg = sum(times) / len(times) if times else None
        # Se nunca acertou, não há tempo para comparar: trata como bem lento.
        slowness = (avg / op_avg[op]) if avg and op in op_avg else 2.0
        error_rate = errors / n
        score = slowness + 3 * error_rate
        if score <= 1.15 and errors == 0:
            continue  # está na média ou melhor: não é ponto fraco
        result.append(
            {
                "op": op,
                "a": a,
                "b": b,
                "answer": attempts[0]["answer"],
                "attempts": n,
                "errors": errors,
                "error_rate": error_rate,
                "avg_ms": avg,
                "slowness": slowness,
                "score": score,
            }
        )
    result.sort(key=lambda f: f["score"], reverse=True)
    return result[:limit]


def day_counts():
    rows = get_db().execute(
        "SELECT substr(created_at, 1, 10) AS day, COUNT(*) AS n FROM attempts GROUP BY day"
    ).fetchall()
    return {r["day"]: r["n"] for r in rows}


def streak_info(goal, today=None):
    """Sequência de dias consecutivos batendo a meta diária de questões."""
    today = today or date.today()
    counts = day_counts()
    met = {d for d, n in counts.items() if n >= goal}

    today_count = counts.get(today.isoformat(), 0)

    # Se a meta de hoje ainda não foi batida, a sequência continua viva até ontem.
    cursor = today if today.isoformat() in met else today - timedelta(days=1)
    current = 0
    while cursor.isoformat() in met:
        current += 1
        cursor -= timedelta(days=1)

    best = 0
    run = 0
    prev = None
    for d in sorted(met):
        day = date.fromisoformat(d)
        run = run + 1 if prev and day - prev == timedelta(days=1) else 1
        best = max(best, run)
        prev = day

    return {
        "goal": goal,
        "today": today_count,
        "today_met": today_count >= goal,
        "current": current,
        "best": best,
        "calendar": calendar(counts, goal, today),
    }


MONTHS = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]
WEEKDAYS = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]


def calendar(counts, goal, today, weeks=26):
    """Grade de semanas (colunas, de segunda a domingo) para o calendário de atividade."""
    start = today - timedelta(days=today.weekday() + 7 * (weeks - 1))
    columns, months = [], []
    for w in range(weeks):
        week = []
        for i in range(7):
            d = start + timedelta(days=7 * w + i)
            n = counts.get(d.isoformat(), 0)
            if n == 0:
                level = 0
            elif n < goal / 2:
                level = 1
            elif n < goal:
                level = 2
            elif n < 2 * goal:
                level = 3
            else:
                level = 4
            week.append({
                "day": d.isoformat(),
                "label": f"{WEEKDAYS[d.weekday()]}, {d.day} {MONTHS[d.month - 1]}",
                "count": n,
                "level": level,
                "future": d > today,
            })
        # Rótulo do mês na semana em que ele começa.
        first_of_month = [d for d in week if d["day"].endswith("-01")]
        if first_of_month:
            months.append({"col": w, "name": MONTHS[int(first_of_month[0]["day"][5:7]) - 1]})
        columns.append(week)
    # O mês da primeira coluna, se houver espaço antes do próximo rótulo.
    if not months or months[0]["col"] >= 3:
        months.insert(0, {"col": 0, "name": MONTHS[start.month - 1]})
    return {"weeks": columns, "months": months}


def totals():
    row = get_db().execute(
        """
        SELECT COUNT(*) AS total, COALESCE(SUM(correct), 0) AS correct,
               COUNT(DISTINCT session_id) AS sessions,
               COUNT(DISTINCT substr(created_at, 1, 10)) AS days
        FROM attempts
        """
    ).fetchone()
    return dict(row)
