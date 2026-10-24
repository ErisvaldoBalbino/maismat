(() => {
  const root = document.getElementById("trainer");
  const config = JSON.parse(root.dataset.config);
  const $ = id => document.getElementById(id);
  const el = {
    question: $("question"), answer: $("answer"), feedback: $("feedback"),
    progress: $("progress"), score: $("score"), last: $("last"), bar: $("bar"),
    auto: $("auto"), stop: $("stop"), stage: $("stage"),
  };

  const AUTO_KEY = "maismat:auto";
  try { el.auto.checked = localStorage.getItem(AUTO_KEY) !== "0"; } catch (e) { el.auto.checked = true; }
  el.auto.addEventListener("change", () => {
    try { localStorage.setItem(AUTO_KEY, el.auto.checked ? "1" : "0"); } catch (e) {}
    el.answer.focus();
  });

  let sessionId = null;
  let problems = [];
  let index = 0;
  let correct = 0;
  let answered = 0;
  let shownAt = 0;
  let startedAt = 0;
  let timerId = null;
  let finished = false;
  const pending = [];

  async function post(url, body) {
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || `Erro ${res.status}`);
    return data;
  }

  function render() {
    const p = problems[index];
    el.question.textContent = `${p.a} ${p.symbol} ${p.b}`;
    el.answer.value = "";
    el.answer.focus();
    shownAt = performance.now();
    if (config.mode !== "timed") {
      el.progress.textContent = `${index + 1}/${problems.length}`;
      el.bar.style.width = `${(100 * index) / problems.length}%`;
    }
  }

  function flash(ok, text) {
    el.stage.classList.remove("ok", "bad");
    void el.stage.offsetWidth; // reinicia a animação
    el.stage.classList.add(ok ? "ok" : "bad");
    el.feedback.textContent = text;
  }

  function submit(skip = false) {
    if (finished || !sessionId) return;
    const raw = el.answer.value.trim();
    if (!skip && raw === "") return;

    const p = problems[index];
    const timeMs = Math.round(performance.now() - shownAt);
    const given = skip ? null : Number(raw);
    const ok = given === p.answer;

    answered += 1;
    if (ok) correct += 1;
    el.score.textContent = config.mode === "timed" ? correct : `${correct}/${answered}`;
    el.last.textContent = `${(timeMs / 1000).toFixed(2)}s`;
    flash(ok, ok ? " " : `${p.a} ${p.symbol} ${p.b} = ${p.answer}`);

    pending.push(
      post(`/api/sessoes/${sessionId}/respostas`, { op: p.op, a: p.a, b: p.b, given, time_ms: timeMs })
        .catch(err => { el.feedback.textContent = `Falha ao salvar: ${err.message}`; })
    );

    index += 1;
    if (index >= problems.length) {
      finish();
    } else {
      render();
    }
  }

  async function finish() {
    if (finished) return;
    finished = true;
    clearInterval(timerId);
    el.answer.disabled = true;
    el.question.textContent = "Fim!";
    el.bar.style.width = "100%";
    if (!sessionId) { location.href = "/"; return; }
    await Promise.all(pending);
    try {
      const data = await post(`/api/sessoes/${sessionId}/finalizar`);
      location.href = data.redirect;
    } catch (err) {
      el.feedback.textContent = err.message;
    }
  }

  function tick() {
    const elapsed = (performance.now() - startedAt) / 1000;
    const left = Math.max(0, config.time_limit - elapsed);
    el.progress.textContent = `${Math.ceil(left)}s`;
    el.bar.style.width = `${(100 * elapsed) / config.time_limit}%`;
    if (left <= 0) finish();
  }

  el.answer.addEventListener("input", () => {
    el.answer.value = el.answer.value.replace(/\D/g, "");
    if (!el.auto.checked || !problems[index]) return;
    if (el.answer.value.length >= String(problems[index].answer).length) submit();
  });

  el.answer.addEventListener("keydown", e => {
    if (e.key === "Enter") { e.preventDefault(); submit(); }
    else if (e.key === "Tab") { e.preventDefault(); submit(true); }
  });
  document.addEventListener("keydown", e => { if (e.key === "Escape") finish(); });
  el.stop.addEventListener("click", finish);

  async function start() {
    try {
      const data = await post("/api/sessoes", config);
      sessionId = data.session_id;
      problems = data.problems;
    } catch (err) {
      el.question.textContent = "Não foi possível começar";
      el.feedback.textContent = err.message;
      return;
    }
    el.answer.disabled = false;
    startedAt = performance.now();
    if (config.mode === "timed") {
      el.score.textContent = "0";
      tick();
      timerId = setInterval(tick, 100);
    } else {
      el.score.textContent = "0/0";
    }
    render();
  }

  start();
})();
