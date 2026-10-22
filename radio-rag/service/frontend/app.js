/* Radio Mar'ef RAG — frontend logic. Talks to the backend on the same origin
   via /api (the radio frontend nginx proxies /api/ to radio_api:8003). */
(function () {
  "use strict";

  const messagesEl = document.getElementById("messages");
  const form = document.getElementById("form");
  const input = document.getElementById("input");
  const sendBtn = document.getElementById("send");
  const healthEl = document.getElementById("health");
  const examplesEl = document.getElementById("examples");
  const nameEl = document.getElementById("site-name");
  const taglineEl = document.getElementById("site-tagline");

  const EXAMPLE_FALLBACK = [
    "حکم وضو و شرایط صحیح نماز چیست؟",
    "مبانی ولایت فقیه در اندیشه اسلامی چه هستند؟",
    "نقش خانواده و تربیت فرزند در برنامه‌های رادیو چگونه بیان شده؟",
    "روش فهم و تفسیر قرآن از زبان برنامه‌ها چیست؟",
  ];

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[c]));
  }

  function addMsg(role, html) {
    const wrap = document.createElement("div");
    wrap.className = "msg " + role;
    const avatar = role === "bot" ? "📻" : "🧑";
    wrap.innerHTML =
      '<div class="avatar">' + avatar +
      '</div><div class="bubble">' + html + "</div>";
    messagesEl.appendChild(wrap);
    messagesEl.scrollTop = messagesEl.scrollHeight;
    return wrap.querySelector(".bubble");
  }

  function renderSources(sources) {
    if (!sources || !sources.length) return "";
    let html = '<div class="sources"><div class="sources-title">منابع پاسخ</div>';
    sources.forEach((s) => {
      const date = s.air_date || "نامشخص";
      const time = s.time ? ' · ' + esc(s.time) : "";
      const prog = s.program_name ? esc(s.program_name) : "برنامه";
      html +=
        '<div class="src" title="session_id: ' + esc(s.session_id) + '">' +
        '<span class="src-i">' + s.index + "</span> " +
        "<strong>" + prog + "</strong>" +
        ' <span class="src-meta">' + esc(date) + time +
        (s.channel ? " · " + esc(s.channel) : "") + "</span>" +
        (s.score != null ? ' <span class="src-score">' + (s.score * 100).toFixed(0) + "%</span>" : "") +
        (s.text ? '<div class="src-text">' + esc(s.text) + "</div>" : "") +
        "</div>";
    });
    html += "</div>";
    return html;
  }

  function setBusy(b) {
    sendBtn.disabled = b;
    sendBtn.textContent = b ? "در حال پاسخ…" : "ارسال ↑";
  }

  async function ask(question) {
    addMsg("user", esc(question));
    const bubble = addMsg("bot", '<span class="typing">در حال جستجو در آرشیو رادیو…</span>');
    setBusy(true);
    let acc = "";

    try {
      const res = await fetch("/api/chat/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: question, stream: true }),
      });
      if (!res.ok || !res.body) throw new Error("HTTP " + res.status);

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buf = "";
      let sources = null;

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        let idx;
        while ((idx = buf.indexOf("\n\n")) !== -1) {
          const raw = buf.slice(0, idx);
          buf = buf.slice(idx + 2);
          const line = raw.trim();
          if (!line.startsWith("data:")) continue;
          let ev;
          try { ev = JSON.parse(line.slice(5)); } catch (e) { continue; }
          if (ev.type === "delta") { acc += ev.content; bubble.innerHTML = esc(acc); messagesEl.scrollTop = messagesEl.scrollHeight; }
          else if (ev.type === "sources") sources = ev.sources;
          else if (ev.type === "error") throw new Error(ev.error || "error");
        }
      }
      if (sources) bubble.innerHTML += renderSources(sources);
      if (!acc) bubble.innerHTML = esc("پاسخی دریافت نشد.");
    } catch (e) {
      bubble.innerHTML = '<span class="err">خطا: ' + esc(e.message) + "</span>";
    } finally {
      setBusy(false);
      messagesEl.scrollTop = messagesEl.scrollHeight;
    }
  }

  form.addEventListener("submit", (e) => {
    e.preventDefault();
    const q = input.value.trim();
    if (!q) return;
    input.value = "";
    autoresize();
    ask(q);
  });

  function autoresize() {
    input.style.height = "auto";
    input.style.height = Math.min(input.scrollHeight, 140) + "px";
  }
  input.addEventListener("input", autoresize);
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      form.requestSubmit();
    }
  });

  function renderExamples(list) {
    examplesEl.innerHTML = "";
    (list && list.length ? list : EXAMPLE_FALLBACK).forEach((q) => {
      const chip = document.createElement("button");
      chip.type = "button";
      chip.className = "ex";
      chip.textContent = q;
      chip.addEventListener("click", () => ask(q));
      examplesEl.appendChild(chip);
    });
  }

  async function loadSite() {
    try {
      const r = await fetch("/api/site");
      const d = await r.json();
      if (d.name) { nameEl.textContent = d.name; document.title = d.name; }
      if (d.tagline) taglineEl.textContent = d.tagline;
      renderExamples(d.examples);
    } catch (e) {
      renderExamples([]);
    }
  }

  async function pollHealth() {
    try {
      const r = await fetch("/api/health");
      const d = await r.json();
      const ok = d.status === "ok";
      healthEl.className = "health " + (ok ? "ok" : "bad");
      healthEl.textContent = ok ? "● آنلاین" : "● در حال اتصال…";
      healthEl.title = JSON.stringify(d);
    } catch (e) {
      healthEl.className = "health bad";
      healthEl.textContent = "● آفلاین";
    }
  }

  loadSite();
  pollHealth();
  setInterval(pollHealth, 20000);
})();
