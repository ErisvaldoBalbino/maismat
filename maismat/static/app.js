// MaisMat no navegador: navegação sem recarregar a página, notificações e
// o código de cada página (configuração do treino, treino, gráficos).
(() => {
  "use strict";

  const $ = (sel, root = document) => root.querySelector(sel);
  const FETCH_HEADERS = { "X-Requested-With": "fetch" };

  // ---------------------------------------------------------------- notificações

  const TOAST_ICONS = { success: "✓", error: "!", info: "i" };

  function toast(message, type = "info", timeout = type === "error" ? 6000 : 3500) {
    const box = document.createElement("div");
    box.className = `toast ${type}`;
    box.setAttribute("role", type === "error" ? "alert" : "status");
    box.innerHTML = `<span class="toast-icon" aria-hidden="true"></span><span class="toast-text"></span>` +
      `<button type="button" class="toast-close" aria-label="Fechar">×</button>`;
    $(".toast-icon", box).textContent = TOAST_ICONS[type] || TOAST_ICONS.info;
    $(".toast-text", box).textContent = message;

    const stack = $("#toasts");
    stack.append(box);
    // Mantém no máximo 4 na tela.
    while (stack.children.length > 4) stack.firstElementChild.remove();

    let timer = null;
    const close = () => {
      clearTimeout(timer);
      box.classList.add("leaving");
      box.addEventListener("animationend", () => box.remove(), { once: true });
    };
    const arm = () => { timer = setTimeout(close, timeout); };
    box.addEventListener("mouseenter", () => clearTimeout(timer));
    box.addEventListener("mouseleave", arm);
    $(".toast-close", box).addEventListener("click", close);
    arm();
  }

  function showFlashes(root) {
    const node = $("script.flashes", root);
    if (!node) return;
    try {
      for (const [category, message] of JSON.parse(node.textContent)) {
        toast(message, ["success", "error"].includes(category) ? category : "info");
      }
    } catch (e) {}
    node.remove();
  }

  // ---------------------------------------------------------------- navegação

  let cleanup = null;
  let navController = null;

  async function visit(url, { push = true, replace = false } = {}) {
    navController?.abort();
    navController = new AbortController();
    document.body.classList.add("loading");
    try {
      const res = await fetch(url, { headers: FETCH_HEADERS, signal: navController.signal });
      const html = await res.text();
      const doc = new DOMParser().parseFromString(html, "text/html");
      if (!(res.headers.get("content-type") || "").includes("text/html") || !$("#main", doc)) {
        location.href = url; // não é uma página do app (ex.: erro do servidor): carrega normalmente
        return;
      }
      if (replace) history.replaceState(null, "", res.url);
      else if (push) history.pushState(null, "", res.url);
      swap(doc);
      window.scrollTo(0, 0);
    } catch (err) {
      if (err.name !== "AbortError") {
        toast("Não foi possível carregar a página. O servidor está rodando?", "error");
      }
    } finally {
      document.body.classList.remove("loading");
    }
  }

  function swap(doc) {
    unmount();
    document.title = doc.title;
    $("#nav").replaceWith($("#nav", doc));
    $("#main").replaceWith($("#main", doc));
    mount();
  }

  function mount() {
    const main = $("#main");
    showFlashes(main);
    const init = PAGES[main.dataset.page];
    cleanup = (init && init(main)) || null;
  }

  function unmount() {
    if (cleanup) cleanup();
    cleanup = null;
  }

  document.addEventListener("click", e => {
    if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;

    // Linhas de tabela clicáveis (histórico).
    const row = e.target.closest("tr[data-href]");
    if (row && !e.target.closest("a")) {
      visit(row.dataset.href);
      return;
    }

    const link = e.target.closest("a[href]");
    if (!link || link.target || link.hasAttribute("download")) return;
    const url = new URL(link.href, location.href);
    if (url.origin !== location.origin || url.pathname.startsWith("/static/")) return;
    if (url.pathname === location.pathname && url.search === location.search && url.hash) return;
    e.preventDefault();
    visit(url.href);
  });

  document.addEventListener("submit", async e => {
    if (e.defaultPrevented) return; // a página já tratou (ex.: validação)
    const form = e.target;
    e.preventDefault();

    if ((form.getAttribute("method") || "get").toLowerCase() === "get") {
      const url = new URL(form.action, location.href);
      url.search = new URLSearchParams(new FormData(form)).toString();
      visit(url.href);
      return;
    }

    const button = e.submitter || $("button[type=submit]", form);
    if (button) button.disabled = true;
    try {
      const res = await fetch(form.action, { method: "POST", body: new FormData(form), headers: FETCH_HEADERS });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        toast(data.error || `Erro ${res.status}`, "error");
        return;
      }
      if (data.message) toast(data.message, "success");
      const target = form.dataset.target && document.getElementById(form.dataset.target);
      if (target && data.html) {
        const tpl = document.createElement("template");
        tpl.innerHTML = data.html.trim();
        target.replaceWith(tpl.content);
      }
    } catch (err) {
      toast("Não foi possível salvar. O servidor está rodando?", "error");
    } finally {
      if (button && button.isConnected) button.disabled = false;
    }
  });

  window.addEventListener("popstate", () => visit(location.href, { push: false }));

  async function postJSON(url, body) {
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...FETCH_HEADERS },
      body: JSON.stringify(body || {}),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || `Erro ${res.status}`);
    return data;
  }

  // ---------------------------------------------------------------- página: configurar treino

  const SETUP_KEY = "maismat:setup";

  function initSetup(main) {
    const form = $("#setup", main);
    if (!form) return;

    // Mostra só os campos relevantes ao modo escolhido.
    function update() {
      const mode = form.mode.value;
      form.querySelectorAll("fieldset[data-show]").forEach(fs => {
        const on = fs.dataset.show.split(" ").includes(mode);
        fs.hidden = !on;
        fs.disabled = !on;
      });
      // Na tabuada só fazem sentido multiplicação e divisão.
      form.querySelectorAll(".chips [data-op]").forEach(l => {
        const hide = mode === "table" && !["mul", "div"].includes(l.dataset.op);
        l.hidden = hide;
        $("input", l).disabled = hide;
      });
    }

    // As escolhas são salvas a cada mudança, então sobrevivem à troca de página.
    function save() {
      const data = {};
      for (const el of form.querySelectorAll("input[name]")) {
        data[el.name] ??= [];
        if (el.checked) data[el.name].push(el.value);
      }
      try { localStorage.setItem(SETUP_KEY, JSON.stringify(data)); } catch (e) {}
    }

    try {
      const saved = JSON.parse(localStorage.getItem(SETUP_KEY) || "null");
      if (saved) {
        for (const [name, values] of Object.entries(saved)) {
          form.querySelectorAll(`[name="${name}"]`).forEach(el => {
            if (el.disabled) return;
            el.checked = values.includes(el.value);
          });
        }
      }
    } catch (e) {}
    if (!form.mode.value) $('[name="mode"]', form).checked = true;

    // "Outro": o número digitado vira o valor do rádio ao lado, que é o que vai no formulário.
    const customs = [...form.querySelectorAll("[data-custom]")].map(radio => {
      const field = $('input[type="number"]', radio.parentNode);
      return { radio, field, min: +field.min, max: +field.max };
    });
    try {
      const saved = JSON.parse(localStorage.getItem(SETUP_KEY) || "null") || {};
      for (const { radio, field } of customs) {
        const [value] = saved[radio.name] || [];
        if (value && !form.querySelector(`[name="${radio.name}"][value="${value}"]`)) {
          radio.value = field.value = value;
          radio.checked = true;
        }
      }
    } catch (e) {}
    for (const { radio, field } of customs) {
      field.addEventListener("focus", () => { radio.checked = true; update(); });
      field.addEventListener("input", () => {
        radio.value = field.value;
        radio.checked = true;
        save();
      });
    }

    form.addEventListener("change", () => { update(); save(); });
    form.addEventListener("submit", e => {
      const mode = form.mode.value;
      let error = null;
      if (mode !== "weak" && mode !== "table" && !$('[name="ops"]:checked', form)) {
        error = "Escolha pelo menos uma operação.";
      } else if (mode === "table" && !$('[name="tables"]:checked', form)) {
        error = "Escolha pelo menos uma tabuada.";
      } else {
        const bad = customs.find(c => c.radio.checked && !c.radio.matches(":disabled") &&
          !(Number.isInteger(+c.field.value) && c.field.value !== "" && +c.field.value >= c.min && +c.field.value <= c.max));
        if (bad) {
          error = bad.radio.name === "time_limit"
            ? `O tempo deve ficar entre ${bad.min} e ${bad.max} segundos.`
            : `A quantidade deve ficar entre ${bad.min} e ${bad.max} questões.`;
          bad.field.focus();
        }
      }
      if (error) {
        e.preventDefault();
        toast(error, "error");
        return;
      }
      save();
    });
    update();
  }

  // ---------------------------------------------------------------- página: treino

  const AUTO_KEY = "maismat:auto";

  function initTrain(main) {
    const root = $("#trainer", main);
    const config = JSON.parse(root.dataset.config);
    const el = {};
    for (const id of ["question", "answer", "feedback", "progress", "score", "last", "bar", "auto", "stop", "stage"]) {
      el[id] = $(`#${id}`, root);
    }

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
    let saveFailed = false;
    const pending = [];

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
      if (document.documentElement.dataset.sound === "on") beep(ok);
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
        postJSON(`/api/sessoes/${sessionId}/respostas`, { op: p.op, a: p.a, b: p.b, given, time_ms: timeMs })
          .catch(err => {
            // Um aviso só, mesmo que várias respostas falhem seguidas.
            if (!saveFailed) toast(`Falha ao salvar resposta: ${err.message}`, "error");
            saveFailed = true;
          })
      );

      index += 1;
      if (index >= problems.length) finish();
      else render();
    }

    async function finish() {
      if (finished) return;
      finished = true;
      clearInterval(timerId);
      el.answer.disabled = true;
      el.question.textContent = "Fim!";
      el.bar.style.width = "100%";
      if (!sessionId) { visit("/"); return; }
      await Promise.all(pending);
      try {
        const data = await postJSON(`/api/sessoes/${sessionId}/finalizar`);
        if (data.message) toast(data.message, "info");
        if (data.goal_reached) {
          const dias = data.streak === 1 ? "1 dia" : `${data.streak} dias`;
          toast(`Meta do dia batida! Sequência: ${dias}.`, "success", 6000);
        }
        if (!data.message && document.documentElement.dataset.confetti === "on") confetti();
        // Substitui o histórico: voltar não recomeça um treino por engano.
        visit(data.redirect, { replace: true });
      } catch (err) {
        toast(`Não foi possível encerrar: ${err.message}`, "error");
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
    const onEscape = e => { if (e.key === "Escape") finish(); };
    document.addEventListener("keydown", onEscape);
    el.stop.addEventListener("click", finish);

    // Saiu da página no meio do treino: encerra a sessão para não ficar aberta.
    function abandon() {
      if (finished || !sessionId) return;
      finished = true;
      navigator.sendBeacon(`/api/sessoes/${sessionId}/finalizar`);
      if (answered) toast(`Treino interrompido: ${answered} respostas salvas no histórico.`, "info");
    }
    window.addEventListener("pagehide", abandon);

    (async () => {
      try {
        const data = await postJSON("/api/sessoes", config);
        sessionId = data.session_id;
        problems = data.problems;
      } catch (err) {
        el.question.textContent = "Não foi possível começar";
        toast(err.message, "error");
        return;
      }
      if (!root.isConnected) { abandon(); return; } // a página mudou enquanto carregava
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
    })();

    return () => {
      clearInterval(timerId);
      document.removeEventListener("keydown", onEscape);
      window.removeEventListener("pagehide", abandon);
      abandon();
    };
  }

  // ---------------------------------------------------------------- página: desempenho

  let chartLib = null;
  function loadChartLib() {
    chartLib ??= new Promise((resolve, reject) => {
      const s = document.createElement("script");
      s.src = "/static/chart.umd.js";
      s.onload = () => resolve(window.Chart);
      s.onerror = () => { chartLib = null; reject(new Error("chart.js")); };
      document.head.append(s);
    });
    return chartLib;
  }

  const MONTHS = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];
  const fmtDay = d => `${Number(d.slice(8, 10))} ${MONTHS[Number(d.slice(5, 7)) - 1]}`;
  const fmtNum = (v, digits) => v.toLocaleString("pt-BR", { minimumFractionDigits: digits, maximumFractionDigits: digits });

  const METRICS = {
    avg_ms: {
      hint: "Tempo médio por acerto, em segundos (média dos últimos 7 dias de treino). Quanto menor, melhor.",
      smooth: true,
      value: v => v / 1000,
      tick: v => `${fmtNum(v, 1)}s`,
      label: v => `${fmtNum(v, 2)}s`,
      y: { beginAtZero: true },
    },
    accuracy: {
      hint: "Porcentagem de acertos (média dos últimos 7 dias de treino).",
      smooth: true,
      value: v => v,
      tick: v => `${v}%`,
      label: v => `${fmtNum(v, 0)}%`,
      y: { suggestedMin: 50, max: 100 },
    },
    total: {
      hint: "Questões respondidas por dia.",
      value: v => v,
      tick: v => v,
      label: v => `${v} ${v === 1 ? "questão" : "questões"}`,
      y: { beginAtZero: true, stacked: true },
      bar: true,
    },
  };

  // Dica flutuante para qualquer elemento com data-tip="detalhe|destaque" (o destaque vai em negrito).
  function initTips(main) {
    const tip = document.createElement("div");
    tip.className = "tip";
    tip.hidden = true;
    document.body.append(tip);
    const show = e => {
      const cell = e.target.closest("[data-tip]");
      if (!cell) { tip.hidden = true; return; }
      const [detail, title] = cell.dataset.tip.split("|");
      tip.innerHTML = "<strong></strong><span></span>";
      tip.firstChild.textContent = title;
      tip.lastChild.textContent = detail;
      const r = cell.getBoundingClientRect();
      tip.style.left = `${r.left + r.width / 2}px`;
      tip.style.top = `${r.top}px`;
      tip.hidden = false;
    };
    const hide = () => { tip.hidden = true; };
    main.addEventListener("mouseover", show);
    main.addEventListener("mouseleave", hide);
    window.addEventListener("scroll", hide, { passive: true });
    return () => {
      tip.remove();
      window.removeEventListener("scroll", hide);
    };
  }

  function initStats(main) {
    const removeTips = initTips(main);
    const node = $("#chart-data", main);
    if (!node) return removeTips;

    const { series: data, names } = JSON.parse(node.textContent);
    const css = getComputedStyle(document.documentElement);
    const color = name => css.getPropertyValue(name).trim();
    const labels = data.days.map(fmtDay);
    const tabs = $("#chart-tabs", main);
    const hint = $("#chart-hint", main);
    let chart = null;
    let alive = true;

    // Média móvel ponderada pelo nº de questões: suaviza a oscilação de um dia para o outro.
    function smooth(values, weights, size = 7) {
      return values.map((v, i) => {
        if (v === null) return null;
        let sum = 0, total = 0;
        for (let j = Math.max(0, i - size + 1); j <= i; j++) {
          if (values[j] === null || !weights[j]) continue;
          sum += values[j] * weights[j];
          total += weights[j];
        }
        return total ? sum / total : v;
      });
    }
    const OPS = ["add", "sub", "mul", "div"].filter(op => op in data.series);

    function draw(Chart, metric) {
      const m = METRICS[metric];
      chart?.destroy();
      hint.textContent = m.hint;
      const few = labels.length < 12;
      chart = new Chart($("#chart", main), {
        type: m.bar ? "bar" : "line",
        data: {
          labels,
          datasets: OPS.map(op => ({
            label: names[op],
            data: (m.smooth ? smooth(data.series[op][metric], data.series[op].total) : data.series[op][metric])
              .map(v => (v === null ? null : m.value(v))),
            borderColor: color(`--op-${op}`),
            backgroundColor: color(`--op-${op}`),
            spanGaps: true,
            cubicInterpolationMode: "monotone",
            borderWidth: 2.5,
            pointRadius: few ? 3 : 0,
            pointHoverRadius: 5,
            pointHoverBorderWidth: 2,
            pointHoverBorderColor: color("--card"),
            borderRadius: 3,
            maxBarThickness: 18,
          })),
        },
        options: {
          maintainAspectRatio: false,
          animation: { duration: 300 },
          interaction: { mode: "index", intersect: false },
          layout: { padding: { top: 4 } },
          scales: {
            x: {
              stacked: !!m.bar,
              grid: { display: false },
              border: { display: false },
              ticks: { maxRotation: 0, autoSkipPadding: 18 },
            },
            y: {
              ...m.y,
              grid: { color: color("--line") },
              border: { display: false },
              ticks: { callback: m.tick, maxTicksLimit: 6, padding: 8 },
            },
          },
          plugins: {
            legend: {
              position: "bottom",
              labels: { usePointStyle: true, pointStyle: "circle", boxWidth: 7, boxHeight: 7, padding: 18 },
            },
            tooltip: {
              backgroundColor: color("--ink"),
              titleColor: color("--on-ink"),
              bodyColor: color("--on-ink"),
              titleFont: { family: css.getPropertyValue("--font-display"), weight: "600", size: 13 },
              bodyFont: { size: 13 },
              padding: 10,
              cornerRadius: 10,
              boxPadding: 5,
              usePointStyle: true,
              filter: item => item.raw !== null && !(m.bar && item.raw === 0),
              callbacks: { label: item => ` ${item.dataset.label}: ${m.label(item.raw)}` },
            },
          },
        },
      });
    }

    loadChartLib().then(Chart => {
      if (!alive) return;
      Chart.defaults.font.family = css.getPropertyValue("--font-body");
      Chart.defaults.font.size = 12;
      Chart.defaults.color = color("--muted");
      draw(Chart, "avg_ms");
      tabs.addEventListener("click", e => {
        const btn = e.target.closest("[data-metric]");
        if (!btn) return;
        tabs.querySelectorAll("[data-metric]").forEach(b => b.setAttribute("aria-selected", b === btn));
        draw(Chart, btn.dataset.metric);
      });
    }).catch(() => toast("Não foi possível carregar os gráficos.", "error"));

    return () => {
      alive = false;
      chart?.destroy();
      removeTips();
    };
  }

  const PAGES = { index: initSetup, train: initTrain, session: initTips, stats: initStats };

  // ---------------------------------------------------------------- preferências

  const HALLOWEEN_KEY = "maismat:halloween";

  // O painel fica no topo, fora do #main, então vive enquanto a página estiver aberta.
  function initPrefs() {
    const root = document.documentElement;
    const button = $("#prefs-toggle");
    const panel = $("#prefs-panel");
    if (!button || !panel) return;

    const open = show => {
      panel.hidden = !show;
      button.setAttribute("aria-expanded", show);
    };
    button.addEventListener("click", () => open(panel.hidden));
    document.addEventListener("click", e => {
      if (!panel.hidden && !e.target.closest(".prefs")) open(false);
    });
    document.addEventListener("keydown", e => {
      if (e.key === "Escape" && !panel.hidden) { open(false); button.focus(); }
    });

    panel.addEventListener("change", async () => {
      const theme = panel.theme.value;
      const confettiOn = panel.confetti.checked;
      const soundOn = panel.sound.checked;
      const themeChanged = root.dataset.theme !== theme;
      root.dataset.theme = theme;
      root.dataset.confetti = confettiOn ? "on" : "off";
      root.dataset.sound = soundOn ? "on" : "off";
      // Os gráficos leem as cores na hora de desenhar: remonta a página para pegar o tema novo.
      if (themeChanged && $("#main").dataset.page === "stats") { unmount(); mount(); }
      try {
        await postJSON(panel.action, { theme, confetti: confettiOn, sound: soundOn });
      } catch (err) {
        toast(`Não foi possível salvar: ${err.message}`, "error");
      }
    });
    panel.addEventListener("submit", e => e.preventDefault());

    // Em outubro, avisa uma vez por ano que existe o tema de Halloween.
    const year = new Date().getFullYear();
    if (new Date().getMonth() === 9 && root.dataset.theme !== "halloween") {
      try {
        if (localStorage.getItem(HALLOWEEN_KEY) !== String(year)) {
          localStorage.setItem(HALLOWEEN_KEY, year);
          setTimeout(() => toast("É mês de Halloween! Experimente o tema 🎃 no botão de preferências, no topo.", "info", 9000), 800);
        }
      } catch (e) {}
    }
  }

  // Sons de máquina de escrever, gerados na hora: ruído curto e filtrado em vez de notas.
  // Acerto é um "tac" seguido de um "ding" suave; erro são dois baques graves e abafados.
  let audio = null;
  let noise = null;
  function beep(ok) {
    try {
      audio ??= new AudioContext();
      if (!noise) {
        noise = audio.createBuffer(1, audio.sampleRate * 0.1, audio.sampleRate);
        const data = noise.getChannelData(0);
        for (let i = 0; i < data.length; i++) data[i] = Math.random() * 2 - 1;
      }
      const now = audio.currentTime;
      if (ok) {
        hit(now, { filter: "bandpass", freq: 1800, q: 1.2, volume: 0.3, length: 0.03 });
        thump(now, 140, 0.1);
        ding(now + 0.03);
      } else {
        for (const t of [now, now + 0.09]) {
          hit(t, { filter: "lowpass", freq: 500, q: 0.7, volume: 0.5, length: 0.07 });
          thump(t, 90, 0.2);
        }
      }
    } catch (e) {}
  }

  // Estalo: ruído passando por um filtro, com volume caindo rápido.
  function hit(t, { filter, freq, q, volume, length }) {
    const src = audio.createBufferSource();
    src.buffer = noise;
    const bq = audio.createBiquadFilter();
    bq.type = filter;
    bq.frequency.value = freq;
    bq.Q.value = q;
    const gain = audio.createGain();
    gain.gain.setValueAtTime(volume, t);
    gain.gain.exponentialRampToValueAtTime(0.0001, t + length);
    src.connect(bq).connect(gain).connect(audio.destination);
    src.start(t);
    src.stop(t + length + 0.02);
  }

  // Campainha: dó e sol agudos juntos, abafados por um filtro e sumindo devagar.
  function ding(t) {
    const soft = audio.createBiquadFilter();
    soft.type = "lowpass";
    soft.frequency.value = 2400;
    soft.connect(audio.destination);
    [[1047, 0.09], [1568, 0.05]].forEach(([freq, volume]) => {
      const osc = audio.createOscillator();
      osc.frequency.setValueAtTime(freq * 0.98, t);
      osc.frequency.exponentialRampToValueAtTime(freq, t + 0.03);
      const gain = audio.createGain();
      gain.gain.setValueAtTime(0.0001, t);
      gain.gain.exponentialRampToValueAtTime(volume, t + 0.008);
      gain.gain.exponentialRampToValueAtTime(0.0001, t + 0.35);
      osc.connect(gain).connect(soft);
      osc.start(t);
      osc.stop(t + 0.4);
    });
  }

  // Baque: uma onda grave que despenca de frequência, dando o "corpo" da tecla.
  function thump(t, freq, volume) {
    const osc = audio.createOscillator();
    osc.frequency.setValueAtTime(freq, t);
    osc.frequency.exponentialRampToValueAtTime(freq / 2, t + 0.05);
    const gain = audio.createGain();
    gain.gain.setValueAtTime(volume, t);
    gain.gain.exponentialRampToValueAtTime(0.0001, t + 0.06);
    osc.connect(gain).connect(audio.destination);
    osc.start(t);
    osc.stop(t + 0.08);
  }

  // Confete feito à mão num canvas: cerca de 3 segundos e some sozinho.
  function confetti() {
    if (matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const canvas = document.createElement("canvas");
    canvas.className = "confetti";
    document.body.append(canvas);
    const ctx = canvas.getContext("2d");
    const dpr = window.devicePixelRatio || 1;
    const w = innerWidth, h = innerHeight;
    canvas.width = w * dpr;
    canvas.height = h * dpr;
    ctx.scale(dpr, dpr);

    const css = getComputedStyle(document.documentElement);
    const colors = ["--op-add", "--op-sub", "--op-mul", "--op-div", "--accent"].map(v => css.getPropertyValue(v).trim());
    // Dois jatos, dos cantos de baixo em direção ao centro.
    const pieces = Array.from({ length: 160 }, (_, i) => {
      const left = i % 2 === 0;
      const angle = (left ? -60 : -120) * Math.PI / 180 + (Math.random() - .5) * .9;
      const speed = 9 + Math.random() * 9;
      return {
        x: left ? -10 : w + 10,
        y: h * .75,
        vx: Math.cos(angle) * speed,
        vy: Math.sin(angle) * speed,
        size: 6 + Math.random() * 6,
        rot: Math.random() * Math.PI,
        spin: (Math.random() - .5) * .3,
        color: colors[i % colors.length],
      };
    });

    const start = performance.now();
    function frame(now) {
      const t = now - start;
      ctx.clearRect(0, 0, w, h);
      ctx.globalAlpha = Math.max(0, 1 - Math.max(0, t - 2200) / 800);
      for (const p of pieces) {
        p.vy += .32;
        p.vx *= .985;
        p.vy *= .985;
        p.x += p.vx;
        p.y += p.vy;
        p.rot += p.spin;
        ctx.save();
        ctx.translate(p.x, p.y);
        ctx.rotate(p.rot);
        ctx.fillStyle = p.color;
        ctx.fillRect(-p.size / 2, -p.size / 4, p.size, p.size / 2 * Math.abs(Math.cos(p.rot * 2)) + 1);
        ctx.restore();
      }
      if (t < 3000) requestAnimationFrame(frame);
      else canvas.remove();
    }
    requestAnimationFrame(frame);
  }

  initPrefs();
  mount();
})();
