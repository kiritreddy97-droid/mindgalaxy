/*
 * Galactic Connections -- the welcome tour.
 *
 * Runs once, the first time a new user signs in (the server remembers when
 * it's done), and can be replayed any time from the "?" button. Each step
 * spotlights one part of the screen and says what it's for.
 */
(function () {
  "use strict";

  function steps(me) {
    return [
      { title: `Welcome to Galactic Connections, ${me}! ✨`,
        text: "This is your own private galaxy. Every thought you write becomes a star in it. Let's take a quick look around — it takes about a minute." },
      { target: "soul", title: "Your soul",
        text: "This bright star at the centre is your soul, named after you. Click your name above it any time to open the story of your galaxy." },
      { target: "#composer-wrap", title: "Add a thought",
        text: "Write anything on your mind here — “I love noodles”, “my knee hurts”, “1+1” — and press Enter. A new star forms from it." },
      { title: "Stars and gas clouds",
        text: "Click any star to open its gas cloud: everything about that thought, level by level — kinds, uses, which countries, history, recipes… Pick an option to go deeper. Lines between stars show thoughts that are truly related." },
      { target: "#legend", title: "Constellations",
        text: "Thoughts about similar things gather into constellations. Click one here to hide or show it." },
      { target: "#history-btn", title: "History",
        text: "A calendar of your thoughts. Pick a day to see only what you wrote then." },
      { target: "#search-box", title: "Search", text: "Find any thought by a word in it." },
      { target: "#req-btn", title: "Galaxies — other people",
        text: "Find people by username, answer requests, make families, and start group calls. Your galaxy symbol is unique to you; every user has their own." },
      { target: "universe", title: "The universe",
        text: "Zoom out to see everyone else's galaxies around yours. Click a name to send a friend request. Friends, life partners and family can chat, share view-once photos, and make audio or video calls. Nobody can open your galaxy but you." },
      { target: "#controls-hint", title: "Moving around",
        text: "It works like a map: drag to move, scroll or pinch to zoom, right-drag or twist with two fingers to rotate, and click or tap to select.",
        mobileText: "It works like a map: slide one finger to move, pinch to zoom, twist two fingers to rotate, and tap to select." },
      { target: "#user-chip", title: "Private and safe",
        text: "You're signed out automatically after a few quiet minutes. Calls are peer-to-peer and never recorded; photos in chat disappear after viewing." },
      { title: "You're all set 🌌",
        text: "Start by writing your first thought below. You can replay this tour any time from the ? button at the top." },
    ];
  }

  let box = null, hole = null, card = null, index = 0, list = [], onKey = null;

  function start() {
    injectStyles();
    addHelpButton();
    fetch("/api/me").then(r => r.ok ? r.json() : null).then(me => {
      if (me && me.username && !me.tour_done) setTimeout(() => run(me.username), 900);
    }).catch(() => null);
  }

  function addHelpButton() {
    const row = document.querySelector("#header .title-row");
    if (!row || document.getElementById("tour-btn")) return;
    const b = document.createElement("button");
    b.type = "button"; b.id = "tour-btn"; b.className = "pill-btn";
    b.textContent = "?"; b.title = "Take the tour"; b.setAttribute("aria-label", "Take the tour");
    b.addEventListener("click", () => {
      const name = (document.getElementById("user-name") || {}).textContent || "";
      run(name);
    });
    row.appendChild(b);
  }

  function run(me) {
    list = steps(me);
    index = 0;
    box = document.createElement("div");
    box.id = "tour";
    box.setAttribute("role", "dialog"); box.setAttribute("aria-modal", "true"); box.setAttribute("aria-live", "polite");
    hole = document.createElement("div"); hole.className = "tour-hole";
    card = document.createElement("div"); card.className = "panel tour-card";
    box.appendChild(hole); box.appendChild(card);
    document.body.appendChild(box);
    onKey = e => {
      const actions = { Escape: finish, ArrowRight: () => go(1), ArrowLeft: () => go(-1) };
      if (!actions[e.key] && !e.key.startsWith("Arrow") && e.key !== "+" && e.key !== "-") return;
      // the tour owns these keys while it's open (they'd otherwise move the map)
      e.preventDefault();
      e.stopImmediatePropagation();
      if (actions[e.key]) actions[e.key]();
    };
    window.addEventListener("keydown", onKey, true);
    window.addEventListener("resize", show);
    show();
  }

  function go(d) {
    const next = index + d;
    if (next < 0) return;
    if (next >= list.length) return finish();
    index = next;
    show();
  }

  function rectFor(target) {
    const G = window.MindGalaxy;
    if (target === "soul" || target === "universe") {
      if (G) G.flyTo(new G.THREE.Vector3(0, 0, 0), target === "universe" ? 1000 : 110);
      const w = window.innerWidth, h = window.innerHeight;
      const r = target === "universe" ? Math.min(w, h) * 0.42 : 90;
      return { left: w / 2 - r, top: h / 2 - r, width: r * 2, height: r * 2, round: true };
    }
    const el = target && document.querySelector(target);
    if (!el) return null;
    const b = el.getBoundingClientRect();
    if (!b.width || !b.height) return null;     // hidden on this screen size
    return { left: b.left - 8, top: b.top - 8, width: b.width + 16, height: b.height + 16 };
  }

  function show() {
    if (!box) return;
    const s = list[index];
    const r = rectFor(s.target);
    const mobile = window.innerWidth <= 720;
    if (r) {
      Object.assign(hole.style, { left: r.left + "px", top: r.top + "px", width: r.width + "px", height: r.height + "px",
        borderRadius: r.round ? "50%" : "14px", opacity: 1 });
    } else {
      Object.assign(hole.style, { left: window.innerWidth / 2 + "px", top: window.innerHeight / 2 + "px", width: "0px", height: "0px", opacity: 1 });
    }
    card.innerHTML = "";
    const count = document.createElement("div"); count.className = "tour-count";
    count.textContent = `${index + 1} of ${list.length}`;
    const h = document.createElement("h2"); h.textContent = s.title;
    const p = document.createElement("p"); p.textContent = (mobile && s.mobileText) || s.text;
    const row = document.createElement("div"); row.className = "tour-row";
    const skip = mk("Skip tour", "tour-skip", finish);
    const back = mk("Back", "", () => go(-1));
    const next = mk(index === list.length - 1 ? "Start exploring" : "Next", "primary", () => go(1));
    back.disabled = index === 0;
    row.append(skip, back, next);
    card.append(count, h, p, row);
    // place the card beside the spotlight, or centred
    const cw = Math.min(360, window.innerWidth - 32);
    card.style.width = cw + "px";
    let left = window.innerWidth / 2 - cw / 2, top = window.innerHeight / 2 - 110;
    if (r && !mobile) {
      const below = r.top + r.height + 14, above = r.top - 14;
      left = Math.min(Math.max(16, r.left + r.width / 2 - cw / 2), window.innerWidth - cw - 16);
      top = below + 220 < window.innerHeight ? below : Math.max(16, above - 220);
      if (s.target === "soul" || s.target === "universe") top = Math.min(window.innerHeight - 240, r.top + r.height + 14);
    } else if (mobile) {
      top = r && r.top > window.innerHeight / 2 ? 16 : window.innerHeight - 250;
    }
    card.style.left = left + "px";
    card.style.top = Math.max(16, top) + "px";
    next.focus({ preventScroll: true });
  }

  function mk(text, cls, fn) {
    const b = document.createElement("button");
    b.type = "button"; b.textContent = text;
    if (cls) b.className = cls;
    b.addEventListener("click", fn);
    return b;
  }

  function finish() {
    if (!box) return;
    box.remove(); box = null;
    window.removeEventListener("keydown", onKey, true);
    window.removeEventListener("resize", show);
    const G = window.MindGalaxy;
    if (G) G.flyTo(new G.THREE.Vector3(0, 0, 0), 130);
    fetch("/api/tour/done", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" }).catch(() => null);
    const input = document.getElementById("composer-input");
    if (input) input.focus();
  }

  function injectStyles() {
    const st = document.createElement("style");
    st.textContent = `
      #tour { position: fixed; inset: 0; z-index: 160; }
      .tour-hole { position: fixed; box-shadow: 0 0 0 9999px rgba(3,4,12,0.74), 0 0 0 2px rgba(199,182,255,0.9), 0 0 30px rgba(160,140,255,0.6);
        transition: all 0.35s ease; pointer-events: none; }
      .tour-card { position: fixed; padding: 18px 18px 14px; transition: top 0.35s ease, left 0.35s ease; }
      .tour-card h2 { margin: 2px 0 6px; font-size: 17px; }
      .tour-card p { margin: 0 0 14px; font-size: 13.5px; line-height: 1.55; color: #d7d9f2; }
      .tour-count { font-size: 11px; color: var(--muted); letter-spacing: 0.06em; }
      .tour-row { display: flex; gap: 8px; align-items: center; }
      .tour-row button { font: inherit; font-size: 13px; padding: 8px 14px; border-radius: 10px; border: 1px solid var(--border);
        background: rgba(255,255,255,0.05); color: var(--text); cursor: pointer; }
      .tour-row button:disabled { opacity: 0.35; cursor: default; }
      .tour-row button.primary { background: var(--accent); color: #0b0e21; border-color: var(--accent); font-weight: 600; }
      .tour-row .tour-skip { margin-right: auto; background: none; border: none; color: var(--muted); padding-left: 0; }
      #tour-btn { font-weight: 700; width: 28px; justify-content: center; }
      @media (prefers-reduced-motion: reduce) { .tour-hole, .tour-card { transition: none; } }`;
    document.head.appendChild(st);
  }

  if (window.GC) start();
  else document.addEventListener("gc:ready", start, { once: true });
})();
