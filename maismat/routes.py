import csv
import io
import json

from flask import (
    Blueprint,
    Response,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)

from . import problems, stats
from .db import get_db, get_setting, now_iso, set_setting

bp = Blueprint("main", __name__)

MODES = {
    "timed": "Contra o tempo",
    "count": "N questões",
    "table": "Tabuada",
    "weak": "Pontos fracos",
}
TIMED_BUFFER = 400  # questões geradas para o modo contra o tempo


@bp.app_context_processor
def inject_names():
    return {
        "OP_NAMES": problems.OP_NAMES,
        "SYMBOLS": problems.SYMBOLS,
        "DIFFICULTY_NAMES": problems.DIFFICULTY_NAMES,
        "MODES": MODES,
    }


@bp.app_template_filter("seconds")
def fmt_seconds(ms):
    if ms is None:
        return "—"
    return f"{ms / 1000:.2f}s".replace(".", ",")


@bp.app_template_filter("pct")
def fmt_pct(value):
    if value is None:
        return "—"
    return f"{value * 100:.0f}%"


def daily_goal():
    return int(get_setting("daily_goal", stats.DEFAULT_DAILY_GOAL))


def wants_json():
    """Requisições feitas pelo app.js (navegação sem recarregar) pedem JSON."""
    return request.headers.get("X-Requested-With") == "fetch"


def parse_config(data):
    """Valida a configuração de uma sessão. Levanta ValueError com mensagem amigável."""
    mode = data.get("mode", "count")
    if mode not in MODES:
        raise ValueError("Modo inválido.")

    ops = data.get("ops") or []
    if isinstance(ops, str):
        ops = [o for o in ops.split(",") if o]
    ops = [o for o in problems.OPERATIONS if o in ops]

    difficulty = data.get("difficulty", "easy")
    if difficulty not in problems.DIFFICULTIES:
        raise ValueError("Dificuldade inválida.")

    tables = []
    if mode == "table":
        raw = data.get("tables") or []
        if isinstance(raw, str):
            raw = raw.split(",")
        tables = sorted({int(t) for t in raw if str(t).strip().isdigit() and 1 <= int(t) <= 20})
        if not tables:
            raise ValueError("Escolha pelo menos uma tabuada.")
        ops = [o for o in ops if o in ("mul", "div")] or ["mul"]
    elif mode != "weak" and not ops:
        raise ValueError("Escolha pelo menos uma operação.")

    time_limit = None
    count = None
    if mode == "timed":
        time_limit = int(data.get("time_limit") or 60)
        if not 10 <= time_limit <= 600:
            raise ValueError("O tempo deve estar entre 10 e 600 segundos.")
    else:
        count = int(data.get("count") or 20)
        if not 1 <= count <= 500:
            raise ValueError("A quantidade deve estar entre 1 e 500.")

    return {
        "mode": mode,
        "ops": ops,
        "difficulty": difficulty,
        "tables": tables,
        "time_limit": time_limit,
        "count": count,
    }


# ---------------------------------------------------------------- páginas


@bp.route("/")
def index():
    return render_template(
        "index.html",
        streak=stats.streak_info(daily_goal()),
        weak_count=len(stats.weak_facts()),
    )


@bp.route("/treinar")
def train():
    try:
        args = request.args.to_dict()
        args["ops"] = request.args.getlist("ops")
        args["tables"] = request.args.getlist("tables")
        config = parse_config(args)
    except ValueError as e:
        flash(str(e), "error")
        return redirect(url_for("main.index"))
    return render_template("train.html", config=config)


@bp.route("/sessoes/<int:session_id>")
def session_detail(session_id):
    session = get_db().execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
    if session is None:
        abort(404)
    return render_template(
        "session.html", session=session, summary=stats.session_summary(session_id)
    )


@bp.route("/historico")
def history():
    return render_template("history.html", sessions=stats.list_sessions())


@bp.route("/desempenho")
def performance():
    return render_template(
        "stats.html",
        series=stats.daily_series(),
        trends=stats.op_trends(),
        weak=stats.weak_facts(),
        streak=stats.streak_info(daily_goal()),
        totals=stats.totals(),
    )


@bp.post("/meta")
def update_goal():
    try:
        goal = int(request.form.get("daily_goal", ""))
        if not 1 <= goal <= 10000:
            raise ValueError
    except ValueError:
        if wants_json():
            return jsonify(error="Meta inválida: use um número entre 1 e 10000."), 400
        flash("Meta inválida.", "error")
        return redirect(request.referrer or url_for("main.index"))

    set_setting("daily_goal", goal)
    message = f"Meta diária atualizada para {goal} questões."
    if wants_json():
        streak = stats.streak_info(goal)
        return jsonify(message=message, html=render_template("_streak.html", streak=streak))
    flash(message, "success")
    return redirect(request.referrer or url_for("main.index"))


# ---------------------------------------------------------------- API


@bp.post("/api/sessoes")
def api_create_session():
    try:
        config = parse_config(request.get_json(force=True) or {})
    except (ValueError, TypeError) as e:
        return jsonify(error=str(e)), 400

    weak = None
    if config["mode"] == "weak":
        weak = stats.weak_facts(limit=20)
        if not weak:
            return jsonify(error="Ainda não há pontos fracos suficientes. Treine mais um pouco!"), 400
        config["ops"] = sorted({f["op"] for f in weak}, key=problems.OPERATIONS.index)

    n = TIMED_BUFFER if config["mode"] == "timed" else config["count"]
    items = problems.generate(
        config["mode"], config["ops"], config["difficulty"], n,
        tables=config["tables"], weak_facts=weak,
    )

    db = get_db()
    cur = db.execute(
        """INSERT INTO sessions (mode, operations, difficulty, time_limit_s,
                                 question_count, tables, started_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            config["mode"],
            ",".join(config["ops"]),
            config["difficulty"],
            config["time_limit"],
            config["count"],
            ",".join(map(str, config["tables"])) or None,
            now_iso(),
        ),
    )
    db.commit()
    return jsonify(session_id=cur.lastrowid, problems=items, config=config), 201


def _open_session(session_id):
    session = get_db().execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
    if session is None:
        abort(404)
    return session


@bp.post("/api/sessoes/<int:session_id>/respostas")
def api_attempt(session_id):
    session = _open_session(session_id)
    if session["ended_at"]:
        return jsonify(error="Sessão já encerrada."), 409

    data = request.get_json(force=True) or {}
    try:
        op = data["op"]
        a, b = int(data["a"]), int(data["b"])
        time_ms = max(0, int(data["time_ms"]))
        given = data.get("given")
        given = None if given in (None, "") else int(given)
        if op not in problems.OPERATIONS or (op == "div" and b == 0):
            raise ValueError
    except (KeyError, TypeError, ValueError):
        return jsonify(error="Resposta inválida."), 400

    # A correção é feita no servidor a partir da questão, não do que o cliente diz.
    answer = problems.compute(op, a, b)
    correct = int(given == answer)
    db = get_db()
    db.execute(
        """INSERT INTO attempts (session_id, op, a, b, answer, given, correct, time_ms, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (session_id, op, a, b, answer, given, correct, time_ms, now_iso()),
    )
    db.commit()
    return jsonify(correct=bool(correct), answer=answer)


@bp.post("/api/sessoes/<int:session_id>/finalizar")
def api_finish(session_id):
    session = _open_session(session_id)
    db = get_db()
    if not session["ended_at"]:
        db.execute("UPDATE sessions SET ended_at = ? WHERE id = ?", (now_iso(), session_id))
        db.commit()
    total = db.execute(
        "SELECT COUNT(*) FROM attempts WHERE session_id = ?", (session_id,)
    ).fetchone()[0]
    if total == 0:
        # Sessão abandonada sem respostas: não polui o histórico.
        db.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        db.commit()
        return jsonify(redirect=url_for("main.index"), message="Treino encerrado sem respostas, nada foi salvo.")

    # Avisa quando foi esta sessão que fez a meta do dia ser batida.
    streak = stats.streak_info(daily_goal())
    goal_reached = streak["today_met"] and streak["today"] - total < streak["goal"]
    return jsonify(
        redirect=url_for("main.session_detail", session_id=session_id),
        goal_reached=goal_reached,
        streak=streak["current"],
    )


# ---------------------------------------------------------------- exportação


@bp.route("/exportar.json")
def export_json():
    db = get_db()
    payload = {
        "format": "maismat-export",
        "version": 1,
        "exported_at": now_iso(),
        "sessions": [dict(r) for r in db.execute("SELECT * FROM sessions ORDER BY id")],
        "attempts": [dict(r) for r in db.execute("SELECT * FROM attempts ORDER BY id")],
        "settings": [dict(r) for r in db.execute("SELECT * FROM settings ORDER BY key")],
    }
    return Response(
        json.dumps(payload, ensure_ascii=False, indent=2),
        mimetype="application/json",
        headers={"Content-Disposition": "attachment; filename=maismat.json"},
    )


@bp.route("/exportar/respostas.csv")
def export_csv():
    rows = get_db().execute(
        """SELECT a.*, s.mode, s.difficulty
           FROM attempts a JOIN sessions s ON s.id = a.session_id ORDER BY a.id"""
    ).fetchall()
    buf = io.StringIO()
    writer = csv.writer(buf)
    cols = ["id", "session_id", "mode", "difficulty", "op", "a", "b", "answer",
            "given", "correct", "time_ms", "created_at"]
    writer.writerow(cols)
    for r in rows:
        writer.writerow([r[c] for c in cols])
    return Response(
        buf.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=maismat-respostas.csv"},
    )
