import csv
import io
from datetime import date, timedelta

from maismat import stats
from maismat.db import get_db


def start(client, **config):
    res = client.post("/api/sessoes", json=config)
    assert res.status_code == 201, res.get_json()
    return res.get_json()


def answer(client, sid, p, given, time_ms=1000):
    return client.post(
        f"/api/sessoes/{sid}/respostas",
        json={"op": p["op"], "a": p["a"], "b": p["b"], "given": given, "time_ms": time_ms},
    )


def test_pages_render_empty(client):
    for url in ["/", "/historico", "/desempenho"]:
        assert client.get(url).status_code == 200


def test_full_count_session(client):
    data = start(client, mode="count", ops=["add", "mul"], difficulty="easy", count=5)
    assert len(data["problems"]) == 5
    sid = data["session_id"]

    for i, p in enumerate(data["problems"]):
        given = p["answer"] if i < 4 else p["answer"] + 1
        res = answer(client, sid, p, given).get_json()
        assert res["correct"] == (i < 4)

    res = client.post(f"/api/sessoes/{sid}/finalizar").get_json()
    assert res["redirect"] == f"/sessoes/{sid}"

    page = client.get(f"/sessoes/{sid}")
    assert page.status_code == 200
    assert "80%" in page.get_data(as_text=True)

    # Sessão encerrada não aceita mais respostas.
    assert answer(client, sid, data["problems"][0], 1).status_code == 409


def test_server_grades_answers(client):
    sid = start(client, mode="count", ops=["sub"], count=1)["session_id"]
    res = answer(client, sid, {"op": "sub", "a": 10, "b": 3}, 7).get_json()
    assert res == {"correct": True, "answer": 7}
    res = answer(client, sid, {"op": "sub", "a": 10, "b": 3}, None).get_json()
    assert res["correct"] is False


def test_invalid_config(client):
    assert client.post("/api/sessoes", json={"mode": "count", "ops": []}).status_code == 400
    assert client.post("/api/sessoes", json={"mode": "table", "tables": []}).status_code == 400
    assert client.post("/api/sessoes", json={"mode": "weak"}).status_code == 400  # sem dados ainda
    assert client.post("/api/sessoes", json={"mode": "x", "ops": ["add"]}).status_code == 400


def test_table_mode_only_mul_div(client):
    data = start(client, mode="table", ops=["add", "mul"], tables=[7], count=10)
    assert data["config"]["ops"] == ["mul"]
    assert all(p["op"] == "mul" and 7 in (p["a"], p["b"]) for p in data["problems"])


def test_empty_session_is_discarded(client, app):
    sid = start(client, mode="timed", ops=["add"], time_limit=30)["session_id"]
    assert client.post(f"/api/sessoes/{sid}/finalizar").get_json()["redirect"] == "/"
    with app.app_context():
        assert get_db().execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 0


def test_weak_facts_and_weak_mode(client, app):
    sid = start(client, mode="count", ops=["mul"], count=1)["session_id"]
    for _ in range(3):
        answer(client, sid, {"op": "mul", "a": 2, "b": 3}, 6, 800)
        answer(client, sid, {"op": "mul", "a": 3, "b": 4}, 12, 800)
    # 7×8 e 8×7 contam como o mesmo fato; erros e lentidão.
    answer(client, sid, {"op": "mul", "a": 7, "b": 8}, 54, 3000)
    answer(client, sid, {"op": "mul", "a": 8, "b": 7}, 56, 4000)

    with app.app_context():
        weak = stats.weak_facts()
    assert [(f["a"], f["b"]) for f in weak] == [(7, 8)]
    assert weak[0]["errors"] == 1

    data = start(client, mode="weak", count=5)
    assert all({p["a"], p["b"]} == {7, 8} for p in data["problems"])


def test_streak(app):
    with app.app_context():
        db = get_db()
        db.execute(
            "INSERT INTO sessions (mode, operations, difficulty, started_at) VALUES ('count','add','easy','x')"
        )
        today = date.today()
        # Ontem e anteontem bateram a meta (2), há 5 dias também; hoje só 1.
        for offset, n in [(0, 1), (1, 2), (2, 3), (5, 2)]:
            day = (today - timedelta(days=offset)).isoformat()
            for _ in range(n):
                db.execute(
                    "INSERT INTO attempts (session_id, op, a, b, answer, given, correct, time_ms, created_at)"
                    " VALUES (1, 'add', 1, 1, 2, 2, 1, 500, ?)",
                    (day + "T10:00:00",),
                )
        db.commit()
        info = stats.streak_info(goal=2, today=today)
    assert info["current"] == 2
    assert info["best"] == 2
    assert info["today"] == 1 and not info["today_met"]


def test_goal_setting(client):
    client.post("/meta", data={"daily_goal": "30"})
    assert "/30" in client.get("/").get_data(as_text=True)


def test_exports(client):
    data = start(client, mode="count", ops=["add"], count=2)
    for p in data["problems"]:
        answer(client, data["session_id"], p, p["answer"])

    js = client.get("/exportar.json").get_json()
    assert js["format"] == "maismat-export"
    assert len(js["sessions"]) == 1 and len(js["attempts"]) == 2

    rows = list(csv.DictReader(io.StringIO(client.get("/exportar/respostas.csv").get_data(as_text=True))))
    assert len(rows) == 2 and rows[0]["op"] == "add"


def test_pages_render_with_data(client):
    data = start(client, mode="count", ops=["add", "div"], count=4)
    for p in data["problems"]:
        answer(client, data["session_id"], p, p["answer"])
    client.post(f"/api/sessoes/{data['session_id']}/finalizar")
    for url in ["/", "/historico", "/desempenho", "/treinar?mode=timed&ops=add&time_limit=60"]:
        assert client.get(url).status_code == 200, url
    assert client.get("/treinar?mode=count").status_code == 302  # sem operações


def test_always_wrong_ranks_above_only_slow(client, app):
    sid = start(client, mode="count", ops=["mul"], count=1)["session_id"]
    for _ in range(3):
        answer(client, sid, {"op": "mul", "a": 2, "b": 3}, 6, 500)
        answer(client, sid, {"op": "mul", "a": 7, "b": 9}, 63, 2000)  # só lento
        answer(client, sid, {"op": "mul", "a": 7, "b": 8}, 55, 500)   # sempre erra
    with app.app_context():
        weak = stats.weak_facts()
    assert [(f["a"], f["b"]) for f in weak] == [(7, 8), (7, 9)]


def test_goal_setting_async(client):
    headers = {"X-Requested-With": "fetch"}
    res = client.post("/meta", data={"daily_goal": "25"}, headers=headers)
    assert res.status_code == 200
    data = res.get_json()
    assert "25" in data["message"] and 'id="streak"' in data["html"]
    assert client.post("/meta", data={"daily_goal": "0"}, headers=headers).status_code == 400


def test_finish_reports_goal_reached(client):
    client.post("/meta", data={"daily_goal": "2"})
    data = start(client, mode="count", ops=["add"], count=2)
    for p in data["problems"]:
        answer(client, data["session_id"], p, p["answer"])
    res = client.post(f"/api/sessoes/{data['session_id']}/finalizar").get_json()
    assert res["goal_reached"] is True and res["streak"] == 1

    # Uma segunda sessão no mesmo dia não avisa de novo.
    data = start(client, mode="count", ops=["add"], count=1)
    answer(client, data["session_id"], data["problems"][0], 0)
    res = client.post(f"/api/sessoes/{data['session_id']}/finalizar").get_json()
    assert res["goal_reached"] is False


def test_flash_messages_reach_page(client):
    page = client.get("/treinar?mode=count", follow_redirects=True).get_data(as_text=True)
    assert "Escolha pelo menos uma opera" in page and '"error"' in page


def test_calendar_and_trends(client, app):
    data = start(client, mode="count", ops=["add"], count=3)
    for p in data["problems"]:
        answer(client, data["session_id"], p, p["answer"], 1200)
    with app.app_context():
        cal = stats.streak_info(goal=3)["calendar"]
        trends = stats.op_trends()
    assert len(cal["weeks"]) == 26 and all(len(w) == 7 for w in cal["weeks"])
    today = date.today().isoformat()
    cell = next(d for w in cal["weeks"] for d in w if d["day"] == today)
    assert cell["count"] == 3 and cell["level"] == 3 and not cell["future"]
    assert [(t["op"], t["total"], t["delta_ms"]) for t in trends] == [("add", 3, None)]


def test_session_timeline(client):
    data = start(client, mode="count", ops=["add"], count=3)
    sid = data["session_id"]
    for p, ms in zip(data["problems"], [1000, 4000, 2000]):
        answer(client, sid, p, p["answer"] if ms != 4000 else p["answer"] + 1, time_ms=ms)
    client.post(f"/api/sessoes/{sid}/finalizar")

    page = client.get(f"/sessoes/{sid}").get_data(as_text=True)
    assert page.count('class="timeline-bar ok"') == 2
    assert page.count('class="timeline-bar bad"') == 1
    assert "height: 100%" in page and "height: 25%" in page
    assert page.count('class="mark ok"') == 2
    assert "✗" not in page

    assert stats.timeline([]) is None


def test_custom_time_and_count(client):
    page = client.get("/treinar?mode=count&ops=add&count=37").get_data(as_text=True)
    assert '"count": 37' in page
    page = client.get("/treinar?mode=timed&ops=add&time_limit=45").get_data(as_text=True)
    assert '"time_limit": 45' in page
    assert client.get("/treinar?mode=count&ops=add&count=501").status_code == 302
    assert client.get("/treinar?mode=timed&ops=add&time_limit=5").status_code == 302
    assert 'placeholder="outro"' in client.get("/").get_data(as_text=True)


def test_preferences(client):
    page = client.get("/").get_data(as_text=True)
    assert 'data-theme="light"' in page and 'data-confetti="off"' in page

    res = client.post("/preferencias", json={"theme": "halloween", "confetti": True},
                      headers={"X-Requested-With": "fetch"})
    assert res.get_json() == {"theme": "halloween", "confetti": True, "sound": False}
    page = client.get("/historico").get_data(as_text=True)
    assert 'data-theme="halloween"' in page and 'data-confetti="on"' in page

    res = client.post("/preferencias", json={"theme": "neon"}, headers={"X-Requested-With": "fetch"})
    assert res.status_code == 400

    # Sem JavaScript: formulário comum, checkbox desmarcado desliga o confete.
    res = client.post("/preferencias", data={"theme": "dark"})
    assert res.status_code == 302
    page = client.get("/").get_data(as_text=True)
    assert 'data-theme="dark"' in page and 'data-confetti="off"' in page


def test_sound_preference_and_manifest(client):
    client.post("/preferencias", json={"theme": "light", "sound": True}, headers={"X-Requested-With": "fetch"})
    page = client.get("/").get_data(as_text=True)
    assert 'data-sound="on"' in page and 'data-confetti="off"' in page
    assert 'rel="manifest"' in page
    assert client.get("/static/manifest.json").get_json()["short_name"] == "+mat"


def test_daily_challenge(client):
    first = start(client, mode="daily")
    second = start(client, mode="daily")
    assert first["problems"] == second["problems"]  # mesmas questões o dia todo
    assert len(first["problems"]) == stats.DAILY_COUNT
    assert {p["op"] for p in first["problems"]} <= {"add", "sub", "mul", "div"}

    for data, wrong in [(first, 2), (second, 0)]:
        for i, p in enumerate(data["problems"]):
            answer(client, data["session_id"], p, p["answer"] + (1 if i < wrong else 0), time_ms=1000)
    first_end = client.post(f"/api/sessoes/{first['session_id']}/finalizar").get_json()
    second_end = client.post(f"/api/sessoes/{second['session_id']}/finalizar").get_json()
    assert not first_end["daily_record"] and second_end["daily_record"]

    page = client.get(f"/sessoes/{second['session_id']}").get_data(as_text=True)
    assert "Desafio do dia" in page and "novo recorde do dia" in page
    page = client.get(f"/sessoes/{first['session_id']}").get_data(as_text=True)
    assert "30,00s" in page  # 20 s + 2 erros × 5 s
    assert "Seu melhor hoje: 20,00s" in client.get("/").get_data(as_text=True)
    assert "Desafio do dia" in client.get("/historico").get_data(as_text=True)


def test_spaced_review(app):
    day = date(2026, 1, 10)
    with app.app_context():
        due = lambda d: [(r["op"], r["a"], r["b"]) for r in stats.due_reviews(d)]
        stats.record_review("mul", 8, 7, False, today=day)
        assert due(day) == [] and due(day + timedelta(days=1)) == [("mul", 7, 8)]

        stats.record_review("mul", 7, 8, True, today=day)  # antes da data: não conta
        assert due(day + timedelta(days=1)) == [("mul", 7, 8)]

        for days_later, next_due in [(1, 4), (4, 11)]:
            stats.record_review("mul", 7, 8, True, today=day + timedelta(days=days_later))
            assert due(day + timedelta(days=next_due - 1)) == []
            assert due(day + timedelta(days=next_due)) == [("mul", 7, 8)]
        stats.record_review("mul", 7, 8, True, today=day + timedelta(days=11))
        assert due(day + timedelta(days=60)) == []  # passou nas três revisões

        stats.record_review("sub", 9, 4, False, today=day)
        stats.record_review("sub", 9, 4, False, today=day + timedelta(days=1))  # errou de novo: recomeça
        assert due(day + timedelta(days=2)) == [("sub", 9, 4)]


def test_wrong_answer_goes_to_review(client, app):
    data = start(client, mode="count", ops=["mul"], count=1)
    p = data["problems"][0]
    answer(client, data["session_id"], p, p["answer"] + 1)
    with app.app_context():
        tomorrow = date.today() + timedelta(days=1)
        assert len(stats.due_reviews(tomorrow)) == 1


def test_import_backup(client, app):
    data = start(client, mode="daily")
    for p in data["problems"]:
        answer(client, data["session_id"], p, p["answer"])
    client.post(f"/api/sessoes/{data['session_id']}/finalizar")
    backup = client.get("/exportar.json").get_data()

    def upload(content):
        return client.post("/importar", data={"file": (io.BytesIO(content), "maismat.json")},
                           headers={"X-Requested-With": "fetch"}, content_type="multipart/form-data")

    res = upload(backup).get_json()
    assert res["message"] == "0 sessões importadas, 1 já existia."

    with app.app_context():
        db = get_db()
        db.execute("DELETE FROM sessions")
        db.commit()
    res = upload(backup).get_json()
    assert res["message"] == "1 sessão importada." and res["redirect"] == "/historico"
    page = client.get("/historico").get_data(as_text=True)
    assert "Desafio do dia" in page and "100%" in page

    assert upload(b"nao e json").status_code == 400
    assert upload(b'{"format": "outro"}').status_code == 400
