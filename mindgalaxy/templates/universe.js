/*
 * Mind Galaxy -- the universe of galaxies (hosted, signed-in site only).
 *
 * Other users' galaxies float around yours with their names. Only their
 * owner can open them; strings link galaxies that are friends, partners or
 * family, and a black hole sits on the string between enemies. From here you
 * send and answer requests, chat, share view-once encrypted media, and watch
 * the black hole swallow a galaxy.
 *
 * Media is encrypted in this browser (ECDH P-256 + AES-GCM, WebCrypto) with a
 * key pair whose private half never leaves this device; the server only ever
 * stores ciphertext and deletes it once opened.
 */
(function () {
  "use strict";

  const STATUS = {
    friend: { label: "Friends", emoji: "🤝", color: 0x5ff0c8, css: "#5ff0c8" },
    partner: { label: "Life partners", emoji: "💞", color: 0xff7ab8, css: "#ff7ab8" },
    family: { label: "Family", emoji: "🏡", color: 0x8dff9e, css: "#8dff9e" },
    enemy: { label: "Enemies", emoji: "⚔️", color: 0xff4d4d, css: "#ff6b6b" },
  };
  const KIND_TEXT = {
    friend: "wants to be friends 🤝",
    enemy: "wants you to be enemies ⚔️ (a black hole will sit between you)",
    peace: "wants to make peace and be friends again 🕊️",
    partner: "asks you to be life partners 💞 (you'll see all of each other's thoughts)",
    unpartner: "asks to go back to being friends",
    family_invite: "invites you into the family",
    family_leave: "asks to leave the family",
  };
  const EMOJI = ["😀", "😂", "😍", "👍", "🙏", "🔥", "❤️", "😢", "🎉", "😮"];

  // The galaxy page can redraw itself in place (after a new thought); each
  // redraw hands over a fresh scene, and the universe re-attaches to it.
  let G = null, THREE = null, scene = null, rebind = null;
  function bind() {
    const next = window.MindGalaxy;
    if (!next || !next.owner) return;
    G = next; THREE = next.THREE; scene = next.scene;
    if (rebind) rebind(); else start();
  }

  function start() {

    injectStyles();
    const ui = buildUi();
    let data = null, dataKey = "";
    let objects = [];            // everything drawn for the universe, rebuilt on change
    let pickables = [];          // [hitSprite, galaxyInfo]
    let spinning = [];           // things that rotate each frame
    let openName = null;         // galaxy whose card is open
    let chatWith = null, chatTimer = 0, chatKey = "";

    // ------------------------------------------------------------------
    // HTTP
    // ------------------------------------------------------------------
    async function api(method, url, body) {
      const opts = { method, headers: {} };
      if (body !== undefined) {
        opts.headers["Content-Type"] = "application/json";
        opts.body = JSON.stringify(body);
      }
      const r = await fetch(url, opts);
      let out = {};
      try { out = await r.json(); } catch (e) { /* empty body */ }
      if (r.status === 401) { window.location.href = "/login"; throw new Error("Signed out"); }
      if (!r.ok) throw new Error(out.error || `Request failed (${r.status})`);
      return out;
    }

    // ------------------------------------------------------------------
    // Placement: every galaxy has a stable spot on the sky around yours
    // ------------------------------------------------------------------
    function hash(str) { let h = 2166136261; for (const ch of str) h = Math.imul(h ^ ch.charCodeAt(0), 16777619); return h >>> 0; }
    function placeOf(name) {
      const h = hash(name);
      const theta = (h % 3600) / 3600 * Math.PI * 2;
      const lift = (((h >> 12) % 200) / 200 - 0.5) * 0.7;
      const dist = 430 + ((h >> 20) % 170);
      return new THREE.Vector3(Math.cos(theta) * Math.cos(lift) * dist, Math.sin(lift) * dist, Math.sin(theta) * Math.cos(lift) * dist);
    }

    function spiralGalaxy(name, starCount) {
      const group = new THREE.Group();
      const h = hash(name);
      const hue = h % 360;
      const n = 220 + Math.min(starCount, 60) * 8;
      const R = 34 + Math.min(starCount, 60) * 0.9;
      const pos = new Float32Array(n * 3), col = new Float32Array(n * 3);
      const c = new THREE.Color();
      for (let i = 0; i < n; i++) {
        const arm = i % 2, t = Math.random();
        const ang = t * 5.2 + arm * Math.PI + (Math.random() - 0.5) * 0.5;
        const r = t * R;
        pos[i * 3] = Math.cos(ang) * r + (Math.random() - 0.5) * 2.5;
        pos[i * 3 + 1] = (Math.random() - 0.5) * 2.2 * (1 - t);
        pos[i * 3 + 2] = Math.sin(ang) * r + (Math.random() - 0.5) * 2.5;
        c.setHSL(((hue + t * 60) % 360) / 360, 0.75, 0.55 + (1 - t) * 0.3);
        col[i * 3] = c.r; col[i * 3 + 1] = c.g; col[i * 3 + 2] = c.b;
      }
      const geo = new THREE.BufferGeometry();
      geo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
      geo.setAttribute("color", new THREE.BufferAttribute(col, 3));
      group.add(new THREE.Points(geo, new THREE.PointsMaterial({
        size: 3.2, map: G.glowTex, vertexColors: true, transparent: true, opacity: 0.85,
        depthWrite: false, blending: THREE.AdditiveBlending,
      })));
      const core = new THREE.Sprite(new THREE.SpriteMaterial({
        map: G.glowTex, color: new THREE.Color().setHSL(hue / 360, 0.6, 0.85), transparent: true,
        depthWrite: false, blending: THREE.AdditiveBlending,
      }));
      core.scale.set(30, 30, 1);
      group.add(core);
      group.rotation.x = ((h >> 8) % 100) / 100 * 0.9 - 0.45;
      group.userData.spin = 0.0008 + ((h >> 4) % 10) / 10000;
      return group;
    }

    function blackHole() {
      const group = new THREE.Group();
      group.add(new THREE.Mesh(new THREE.SphereGeometry(6, 24, 16), new THREE.MeshBasicMaterial({ color: 0x000000 })));
      const cnv = document.createElement("canvas");
      cnv.width = cnv.height = 256;
      const ctx = cnv.getContext("2d");
      const grad = ctx.createRadialGradient(128, 128, 40, 128, 128, 128);
      grad.addColorStop(0, "rgba(0,0,0,0)");
      grad.addColorStop(0.35, "rgba(255,120,40,0.95)");
      grad.addColorStop(0.55, "rgba(255,200,120,0.6)");
      grad.addColorStop(1, "rgba(120,40,200,0)");
      ctx.fillStyle = grad;
      ctx.fillRect(0, 0, 256, 256);
      const ring = new THREE.Mesh(new THREE.RingGeometry(7, 20, 64), new THREE.MeshBasicMaterial({
        map: new THREE.CanvasTexture(cnv), transparent: true, side: THREE.DoubleSide,
        depthWrite: false, blending: THREE.AdditiveBlending,
      }));
      ring.rotation.x = Math.PI / 2.4;
      group.add(ring);
      const halo = new THREE.Sprite(new THREE.SpriteMaterial({
        map: G.glowTex, color: 0xff5a1f, transparent: true, opacity: 0.45, depthWrite: false, blending: THREE.AdditiveBlending,
      }));
      halo.scale.set(50, 50, 1);
      group.add(halo);
      group.userData.ring = ring;
      return group;
    }

    let tags = [];               // [domLabel, worldPosition]
    function clearUniverse() {
      objects.forEach(o => { scene.remove(o); G.disposeObject(o); });
      objects = []; pickables = []; spinning = [];
      ui.tags.innerHTML = ""; tags = [];
    }

    const projected = new THREE.Vector3();
    function placeTags() {
      const w = window.innerWidth, h = window.innerHeight;
      tags.forEach(([label, pos]) => {
        projected.copy(pos).project(G.camera);
        const visible = projected.z < 1 && Math.abs(projected.x) < 1.1 && Math.abs(projected.y) < 1.1;
        label.style.display = visible ? "block" : "none";
        if (visible) label.style.transform =
          `translate(${((projected.x + 1) / 2 * w).toFixed(1)}px, ${((1 - projected.y) / 2 * h).toFixed(1)}px) translate(-50%, -50%)`;
      });
    }

    function add(o) { scene.add(o); objects.push(o); return o; }

    function draw() {
      clearUniverse();
      data.galaxies.forEach(gx => {
        const pos = placeOf(gx.username);
        const rel = gx.status || (gx.families.length ? "family" : null);
        const galaxy = spiralGalaxy(gx.username, gx.stars);
        galaxy.position.copy(pos);
        add(galaxy); spinning.push(galaxy);
        // a screen-sized name tag that follows the galaxy (readable at any zoom)
        const label = el("button", "gx-tag", (rel ? STATUS[rel].emoji + " " : "") + gx.username);
        label.type = "button";
        label.style.borderColor = rel ? STATUS[rel].css : "rgba(142,162,255,0.5)";
        label.addEventListener("click", () => openCard(gx.username));
        ui.tags.appendChild(label);
        tags.push([label, pos.clone().add(new THREE.Vector3(0, 48, 0))]);
        const hit = new THREE.Sprite(new THREE.SpriteMaterial({ transparent: true, opacity: 0, depthWrite: false }));
        hit.scale.set(110, 110, 1);
        hit.position.copy(pos);
        add(hit);
        pickables.push([hit, gx]);
        if (rel) {
          // the string from your soul to theirs
          const geo = new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(0, 0, 0), pos]);
          const mat = rel === "enemy"
            ? new THREE.LineDashedMaterial({ color: STATUS.enemy.color, dashSize: 8, gapSize: 5, transparent: true, opacity: 0.8 })
            : new THREE.LineBasicMaterial({ color: STATUS[rel].color, transparent: true, opacity: rel === "partner" ? 0.9 : 0.6 });
          const line = new THREE.Line(geo, mat);
          if (rel === "enemy") line.computeLineDistances();
          add(line);
          if (rel === "enemy") {
            const hole = blackHole();
            hole.position.copy(pos).multiplyScalar(0.5);
            add(hole); spinning.push(hole.userData.ring);
          }
        }
      });
      ui.reqCount.textContent = data.requests_in.length ? ` (${data.requests_in.length})` : "";
      ui.reqBtn.classList.toggle("has", data.requests_in.length > 0);
    }

    function hook() {
      G.onFrame(onFrame);
      G.onClick(onClick);
    }
    rebind = () => {
      objects = []; pickables = []; spinning = []; // their old scene is already disposed
      if (swallowing) { swallowing = null; }
      hook();
      if (data) draw();
    };
    hook();

    function onFrame(t) {
      placeTags();
      spinning.forEach(o => { if (o.userData && o.userData.spin) o.rotation.y += o.userData.spin; else o.rotation.z += 0.01; });
      swallowFrame(t);
    }

    function onClick(raycaster) {
      const hits = raycaster.intersectObjects(pickables.map(p => p[0]));
      if (!hits.length) return false;
      const hit = pickables.find(p => p[0] === hits[0].object);
      openCard(hit[1].username);
      return true;
    }

    async function refresh(force) {
      try {
        const next = await api("GET", "/api/universe");
        const key = JSON.stringify([next.galaxies, next.requests_in, next.requests_out, next.families]);
        data = next;
        if (force || key !== dataKey) {
          dataKey = key;
          draw();
          // a galaxy that vanished (swallowed, or blocked you) closes its card
          if (openName && !data.galaxies.some(g => g.username === openName)) closeCard();
          if (openName) renderCard(openName);
          if (ui.reqPanel.classList.contains("open")) renderRequests();
        }
        if (next.swallows.length && !swallowing) playSwallows(next.swallows);
      } catch (e) { /* offline or signed out; try again next round */ }
    }

    // ------------------------------------------------------------------
    // UI scaffolding
    // ------------------------------------------------------------------
    function injectStyles() {
      const css = `
      #gx-tags { position: fixed; inset: 0; pointer-events: none; z-index: 5; overflow: hidden; }
      .gx-tag { position: absolute; left: 0; top: 0; pointer-events: auto; font: inherit; font-size: 12px; font-weight: 600;
        padding: 3px 10px; border-radius: 20px; border: 1px solid; background: rgba(8,10,28,0.8); color: #eef0ff; cursor: pointer; white-space: nowrap; }
      .gx-tag:hover { background: rgba(30,34,70,0.95); }
      #req-btn.has { border-color: rgba(255,210,122,0.6); color: #ffd27a; }
      .soc-panel { position: fixed; top: 66px; right: 26px; width: min(380px, calc(100vw - 32px)); max-height: calc(100vh - 170px);
        overflow-y: auto; padding: 18px; z-index: 35; display: none; }
      .soc-panel.open { display: block; }
      .soc-panel h2 { margin: 0 0 4px; font-size: 18px; font-weight: 600; }
      .soc-panel .sub { font-size: 12px; color: var(--muted); margin-bottom: 12px; }
      .soc-panel .close { position: absolute; top: 12px; right: 14px; background: none; border: none; color: var(--muted); font-size: 18px; cursor: pointer; }
      .soc-panel h3 { font-size: 10.5px; letter-spacing: 0.08em; text-transform: uppercase; color: var(--muted); margin: 16px 0 8px; }
      .soc-btn { display: block; width: 100%; text-align: left; font: inherit; font-size: 13px; padding: 9px 12px; margin-bottom: 7px;
        border-radius: 10px; border: 1px solid var(--border); background: rgba(255,255,255,0.04); color: var(--text); cursor: pointer; }
      .soc-btn:hover { background: rgba(255,255,255,0.09); }
      .soc-btn.primary { background: var(--accent); color: #0b0e21; border-color: var(--accent); font-weight: 600; }
      .soc-btn.danger { color: #ff9a9a; border-color: rgba(255,120,120,0.35); }
      .soc-row { display: flex; gap: 6px; } .soc-row .soc-btn { flex: 1; text-align: center; }
      .soc-note { font-size: 11.5px; color: var(--muted); line-height: 1.5; margin: 4px 0 8px; }
      .soc-msg { font-size: 12.5px; color: #ffd27a; margin: 8px 0; }
      .soc-input { width: 100%; font: inherit; font-size: 13px; padding: 9px 11px; border-radius: 10px; border: 1px solid var(--border);
        background: rgba(255,255,255,0.05); color: var(--text); outline: none; margin-bottom: 7px; }
      .soc-item { border: 1px solid var(--border); border-radius: 10px; padding: 9px 11px; margin-bottom: 7px; font-size: 12.5px; background: rgba(255,255,255,0.025); }
      .soc-item b { color: var(--text); }
      .soc-thought { font-size: 13px; line-height: 1.5; padding: 8px 10px; border-left: 2px solid var(--accent); margin-bottom: 8px; background: rgba(255,255,255,0.03); border-radius: 0 8px 8px 0; }
      .soc-thought small { display: block; color: var(--muted); font-size: 10.5px; margin-top: 3px; }
      #chat { position: fixed; right: 26px; bottom: 90px; width: min(360px, calc(100vw - 32px)); height: min(520px, calc(100vh - 180px));
        z-index: 40; display: none; flex-direction: column; padding: 0; }
      #chat.open { display: flex; }
      #chat header { display: flex; align-items: center; gap: 8px; padding: 12px 14px; border-bottom: 1px solid var(--border); font-weight: 600; }
      #chat header span { flex: 1; } #chat header button { background: none; border: none; color: var(--muted); font-size: 17px; cursor: pointer; }
      #chat-log { flex: 1; overflow-y: auto; padding: 12px; display: flex; flex-direction: column; gap: 6px; }
      .bubble { max-width: 80%; padding: 7px 11px; border-radius: 14px; font-size: 13px; line-height: 1.45; white-space: pre-wrap; word-break: break-word; }
      .bubble.mine { align-self: flex-end; background: rgba(142,162,255,0.25); border-bottom-right-radius: 4px; }
      .bubble.theirs { align-self: flex-start; background: rgba(255,255,255,0.07); border-bottom-left-radius: 4px; }
      .bubble button { font: inherit; background: none; border: 1px solid rgba(255,210,122,0.5); color: #ffd27a; border-radius: 8px; padding: 4px 9px; cursor: pointer; }
      .bubble .gone { color: var(--muted); font-style: italic; }
      #chat-emoji { display: flex; gap: 2px; padding: 4px 10px 0; flex-wrap: wrap; }
      #chat-emoji button { background: none; border: none; font-size: 17px; cursor: pointer; padding: 2px 4px; border-radius: 6px; }
      #chat-emoji button:hover { background: rgba(255,255,255,0.08); }
      #chat-form { display: flex; gap: 6px; padding: 8px 10px 12px; align-items: center; }
      #chat-form input[type=text] { flex: 1; font: inherit; font-size: 13px; padding: 9px 11px; border-radius: 10px; border: 1px solid var(--border);
        background: rgba(255,255,255,0.05); color: var(--text); outline: none; }
      #chat-form button, #chat-form label { font: inherit; font-size: 13px; padding: 8px 11px; border-radius: 10px; border: none; cursor: pointer; }
      #chat-form .send { background: var(--accent); color: #0b0e21; font-weight: 600; }
      #chat-form label { background: rgba(255,255,255,0.07); color: var(--text); }
      #chat-status { font-size: 11px; color: var(--muted); padding: 0 12px 4px; min-height: 14px; }
      #viewer { position: fixed; inset: 0; z-index: 120; background: rgba(0,0,0,0.92); display: none; align-items: center; justify-content: center; flex-direction: column; gap: 12px; }
      #viewer.open { display: flex; }
      #viewer img, #viewer video { max-width: 92vw; max-height: 78vh; border-radius: 10px; user-select: none; -webkit-user-drag: none; }
      #viewer .timer { font-size: 22px; font-weight: 700; color: #ffd27a; font-variant-numeric: tabular-nums; }
      #viewer .note { font-size: 12px; color: #b9bddf; }
      #toast { position: fixed; left: 50%; top: 18%; transform: translateX(-50%); z-index: 130; max-width: min(520px, calc(100vw - 32px));
        text-align: center; font-size: 16px; line-height: 1.5; padding: 16px 20px; display: none; }
      #toast.open { display: block; }
      .share-toggle { display: flex; align-items: center; gap: 8px; font-size: 12px; margin-top: 10px; color: var(--text); }
      .share-toggle small { color: var(--muted); }
      @media (max-width: 720px) {
        .soc-panel { top: auto; bottom: 84px; right: 16px; max-height: 60vh; }
        #chat { right: 16px; bottom: 84px; height: 60vh; }
      }`;
      const style = document.createElement("style");
      style.textContent = css;
      document.head.appendChild(style);
    }

    function el(tag, cls, text) { return G.el(tag, cls, text); }
    function button(text, cls, onClick) {
      const b = el("button", "soc-btn" + (cls ? " " + cls : ""), text);
      b.type = "button";
      b.addEventListener("click", onClick);
      return b;
    }

    function buildUi() {
      const row = document.querySelector("#header .title-row");
      const reqBtn = el("button", "pill-btn");
      reqBtn.id = "req-btn"; reqBtn.type = "button";
      reqBtn.appendChild(document.createTextNode("✉ Galaxies"));
      const reqCount = el("span"); reqBtn.appendChild(reqCount);
      row.insertBefore(reqBtn, document.getElementById("user-chip"));

      const card = el("div", "hud panel soc-panel"); card.id = "galaxy-card";
      const reqPanel = el("div", "hud panel soc-panel"); reqPanel.id = "req-panel";
      const chat = el("div", "hud panel"); chat.id = "chat";
      chat.innerHTML = `<header><span id="chat-title"></span><button type="button" id="chat-close" aria-label="Close chat">✕</button></header>
        <div id="chat-log" aria-live="polite"></div><div id="chat-status"></div><div id="chat-emoji"></div>
        <form id="chat-form" autocomplete="off"><label title="Send a view-once photo, audio or video">📎<input type="file" id="chat-file" accept="image/*,audio/*,video/*" hidden></label>
        <input type="text" id="chat-input" maxlength="1000" placeholder="Message…"><button type="submit" class="send">Send</button></form>`;
      const viewer = el("div"); viewer.id = "viewer";
      viewer.setAttribute("role", "dialog"); viewer.setAttribute("aria-modal", "true");
      const toast = el("div", "panel"); toast.id = "toast"; toast.setAttribute("role", "status");
      const tags = el("div"); tags.id = "gx-tags";
      [tags, card, reqPanel, chat, viewer, toast].forEach(n => document.body.appendChild(n));
      reqBtn.addEventListener("click", () => {
        const open = !reqPanel.classList.contains("open");
        closeCard();
        reqPanel.classList.toggle("open", open);
        if (open) renderRequests();
      });
      return { reqBtn, reqCount, card, reqPanel, chat, viewer, toast, tags };
    }

    let toastTimer = 0;
    function toast(msg, ms) {
      ui.toast.textContent = msg;
      ui.toast.classList.add("open");
      clearTimeout(toastTimer);
      toastTimer = setTimeout(() => ui.toast.classList.remove("open"), ms || 3500);
    }

    async function act(fn, okMsg) {
      try {
        await fn();
        if (okMsg) toast(okMsg);
        await refresh(true);
      } catch (e) { toast(e.message, 5000); }
    }

    // ------------------------------------------------------------------
    // Galaxy card
    // ------------------------------------------------------------------
    function closeCard() { openName = null; ui.card.classList.remove("open"); }

    function openCard(name) {
      G.deselect();
      ui.reqPanel.classList.remove("open");
      openName = name;
      const gx = data && data.galaxies.find(g => g.username === name);
      if (gx) G.flyTo(placeOf(name), 170);
      renderCard(name);
      ui.card.classList.add("open");
    }

    function renderCard(name) {
      const card = ui.card;
      card.innerHTML = "";
      const close = el("button", "close", "✕"); close.type = "button";
      close.setAttribute("aria-label", "Close"); close.addEventListener("click", closeCard);
      card.appendChild(close);
      const gx = (data && data.galaxies.find(g => g.username === name)) || { username: name, status: null, families: [], stars: 0 };
      const rel = gx.status || (gx.families.length ? "family" : null);
      card.appendChild(el("h2", null, (rel ? STATUS[rel].emoji + " " : "🌌 ") + name));
      const bits = [`${gx.stars} ${gx.stars === 1 ? "star" : "stars"}`];
      if (gx.status) bits.push(STATUS[gx.status].label);
      if (gx.families.length) bits.push("Family: " + gx.families.join(", "));
      card.appendChild(el("div", "sub", bits.join(" · ")));
      card.appendChild(el("div", "soc-note", "Only " + name + " can open this galaxy." +
        (gx.status === "partner" ? " As life partners you can read all of each other's thoughts." :
          gx.families.length ? " As family you see only the thoughts they choose to share." : "")));

      const incoming = data.requests_in.filter(r => r.from === name);
      const outgoing = data.requests_out.filter(r => r.to === name);
      incoming.forEach(r => {
        card.appendChild(el("div", "soc-msg", `${name} ${KIND_TEXT[r.kind] || r.kind}${r.family_name ? " “" + r.family_name + "”" : ""}`));
        const row = el("div", "soc-row");
        row.appendChild(button("Accept", "primary", () => act(() => api("POST", `/api/requests/${r.id}/respond`, { accept: true }), "Accepted")));
        row.appendChild(button("Decline", "", () => act(() => api("POST", `/api/requests/${r.id}/respond`, { accept: false }))));
        card.appendChild(row);
      });
      outgoing.forEach(r => {
        card.appendChild(el("div", "soc-note", `Waiting for ${name} to answer your ${r.kind.replace("_", " ")} request.`));
        card.appendChild(button("Cancel request", "", () => act(() => api("POST", `/api/requests/${r.id}/cancel`, {}))));
      });
      const pendingKinds = new Set(incoming.map(r => r.kind).concat(outgoing.map(r => r.kind)));
      const ask = (kind, text, cls, extra) => {
        if (pendingKinds.has(kind)) return;
        card.appendChild(button(text, cls, () => act(() => api("POST", "/api/requests", { to: name, kind, ...(extra || {}) }),
          `Request sent to ${name}`)));
      };

      if (gx.can_chat) card.appendChild(button("💬 Chat", "primary", () => openChat(name)));
      if (gx.status === "partner" || gx.families.length) {
        card.appendChild(button(gx.status === "partner" ? "📖 Read their thoughts" : "📖 Thoughts they share with family", "",
          () => showThoughts(name)));
      }
      if (!gx.status) ask("friend", "🤝 Send friend request", gx.can_chat ? "" : "primary");
      if (gx.status === "friend") {
        ask("partner", "💞 Propose life partners");
        data.families.filter(f => !f.members.includes(name)).forEach(f =>
          ask("family_invite", `🏡 Invite into family “${f.name}”`, "", { family_id: f.id }));
        ask("enemy", "⚔️ Declare enemies (they must accept)", "danger");
        card.appendChild(button("Unfriend", "", () => {
          if (confirm(`Stop being friends with ${name}?`)) act(() => api("POST", "/api/unfriend", { username: name }));
        }));
      }
      if (gx.status === "partner") ask("unpartner", "Go back to being friends (they must accept)");
      if (gx.status === "enemy") {
        card.appendChild(el("div", "soc-note",
          "Report them once a day. After 5 reports the black hole between you swallows their galaxy: you'll be cut apart for ever, and every chat, photo and request between you is destroyed."));
        card.appendChild(button("🕳️ Report to the black hole", "danger", async () => {
          try {
            const r = await api("POST", "/api/report", { username: name });
            toast(r.swallowed ? "The black hole is waking…" : `Reported (${r.reports} of ${r.needed}).`);
            await refresh(true);
          } catch (e) { toast(e.message, 5000); }
        }));
        ask("peace", "🕊️ Propose peace");
      }
      data.families.filter(f => f.members.includes(name)).forEach(f =>
        ask("family_leave", `Ask ${name} to let you leave “${f.name}”`, "", { family_id: f.id }));
      card.appendChild(button("🚫 Block", "danger", () => {
        if (confirm(`Block ${name}? This ends any status between you at once and hides chat, requests and shared thoughts. Nothing is deleted, and you can unblock later.`)) {
          act(() => api("POST", "/api/block", { username: name }), `${name} is blocked`).then(closeCard);
        }
      }));
    }

    async function showThoughts(name) {
      try {
        const r = await api("GET", `/api/galaxies/${encodeURIComponent(name)}/thoughts`);
        const card = ui.card;
        card.appendChild(el("h3", null, r.scope === "partner" ? "Their thoughts" : "Shared with family"));
        if (!r.thoughts.length) card.appendChild(el("div", "soc-note", "Nothing here yet."));
        r.thoughts.slice().reverse().forEach(t => {
          const d = el("div", "soc-thought", t.text);
          d.appendChild(el("small", null, new Date(/[zZ]$/.test(t.created_at) ? t.created_at : t.created_at + "Z").toLocaleString()));
          card.appendChild(d);
        });
        card.scrollTop = card.scrollHeight;
      } catch (e) { toast(e.message, 5000); }
    }

    // ------------------------------------------------------------------
    // Requests, families, search, blocked
    // ------------------------------------------------------------------
    function renderRequests() {
      const p = ui.reqPanel;
      p.innerHTML = "";
      const close = el("button", "close", "✕"); close.type = "button";
      close.addEventListener("click", () => p.classList.remove("open"));
      p.appendChild(close);
      p.appendChild(el("h2", null, "🌌 Galaxies"));
      p.appendChild(el("div", "sub", "Zoom out (scroll) to see every galaxy around yours."));

      p.appendChild(el("h3", null, "Find a galaxy"));
      const q = el("input", "soc-input"); q.placeholder = "Search by username…"; q.type = "text";
      const results = el("div");
      let qTimer = 0;
      q.addEventListener("input", () => {
        clearTimeout(qTimer);
        qTimer = setTimeout(async () => {
          results.innerHTML = "";
          if (q.value.trim().length < 2) return;
          try {
            const r = await api("GET", "/api/users/search?q=" + encodeURIComponent(q.value.trim()));
            if (!r.users.length) results.appendChild(el("div", "soc-note", "No galaxy by that name."));
            r.users.forEach(u => results.appendChild(button("🌌 " + u, "", () => openCard(u))));
          } catch (e) { results.appendChild(el("div", "soc-note", e.message)); }
        }, 250);
      });
      p.appendChild(q); p.appendChild(results);

      p.appendChild(el("h3", null, `Requests for you (${data.requests_in.length})`));
      if (!data.requests_in.length) p.appendChild(el("div", "soc-note", "No requests right now."));
      data.requests_in.forEach(r => {
        const item = el("div", "soc-item");
        const who = el("b", null, r.from);
        item.appendChild(who);
        item.appendChild(document.createTextNode(` ${KIND_TEXT[r.kind] || r.kind}${r.family_name ? " “" + r.family_name + "”" : ""}`));
        const row = el("div", "soc-row"); row.style.marginTop = "8px";
        row.appendChild(button("Accept", "primary", () => act(() => api("POST", `/api/requests/${r.id}/respond`, { accept: true }), "Accepted")));
        row.appendChild(button("Decline", "", () => act(() => api("POST", `/api/requests/${r.id}/respond`, { accept: false }))));
        item.appendChild(row);
        p.appendChild(item);
      });

      if (data.requests_out.length) {
        p.appendChild(el("h3", null, "Waiting on others"));
        data.requests_out.forEach(r => {
          const item = el("div", "soc-item", `${r.kind.replace("_", " ")} → ${r.to}`);
          item.appendChild(button("Cancel", "", () => act(() => api("POST", `/api/requests/${r.id}/cancel`, {}))));
          p.appendChild(item);
        });
      }

      p.appendChild(el("h3", null, "Your families"));
      p.appendChild(el("div", "soc-note",
        "Family galaxies (up to 9) see only the thoughts you switch to “Share with family”. 18+ and violent thoughts can never be shared with family."));
      data.families.forEach(f => {
        const item = el("div", "soc-item");
        item.appendChild(el("b", null, "🏡 " + f.name));
        item.appendChild(el("div", "soc-note", f.members.join(", ")));
        if (f.members.length === 1) item.appendChild(button("Delete this family", "", () =>
          act(() => api("POST", `/api/families/${f.id}/leave`, {}))));
        p.appendChild(item);
      });
      const fname = el("input", "soc-input"); fname.placeholder = "New family name"; fname.maxLength = 40; fname.type = "text";
      p.appendChild(fname);
      p.appendChild(button("Create family", "", () => {
        if (!fname.value.trim()) return toast("Give the family a name.");
        act(() => api("POST", "/api/families", { name: fname.value.trim() }), "Family created — invite friends from their galaxy card");
      }));

      if (data.blocked.length) {
        p.appendChild(el("h3", null, "Blocked"));
        data.blocked.forEach(name => {
          const item = el("div", "soc-item", name);
          item.appendChild(button("Unblock", "", () => act(() => api("POST", "/api/unblock", { username: name }), `${name} unblocked`)));
          p.appendChild(item);
        });
      }
    }

    // ------------------------------------------------------------------
    // Family sharing switch on your own stars
    // ------------------------------------------------------------------
    document.addEventListener("mindgalaxy:star", e => {
      const star = e.detail.star;
      if (!data || !data.families.length) return;
      const flags = document.getElementById("detail-flags");
      const wrap = el("label", "share-toggle");
      const box = document.createElement("input");
      box.type = "checkbox";
      box.checked = !!star.share_family;
      const rating = star.analysis && star.analysis.rating;
      const safe = rating === "everyone";
      box.disabled = !safe && !box.checked;
      wrap.appendChild(box);
      wrap.appendChild(document.createTextNode("Share with family"));
      if (!safe) wrap.appendChild(el("small", null, rating ? "— rated 18+/violent, can't be shared" : "— not checked yet"));
      box.addEventListener("change", async () => {
        try {
          await api("POST", `/api/entries/${star.id}/share`, { family: box.checked });
          star.share_family = box.checked;
          toast(box.checked ? "Shared with your family" : "No longer shared with family");
        } catch (err) { box.checked = !box.checked; toast(err.message, 5000); }
      });
      flags.appendChild(wrap);
    });

    // ------------------------------------------------------------------
    // Chat
    // ------------------------------------------------------------------
    const log = () => document.getElementById("chat-log");
    document.getElementById("chat-close").addEventListener("click", closeChat);
    EMOJI.forEach(em => {
      const b = el("button", null, em); b.type = "button";
      b.addEventListener("click", () => { const i = document.getElementById("chat-input"); i.value += em; i.focus(); });
      document.getElementById("chat-emoji").appendChild(b);
    });
    document.getElementById("chat-form").addEventListener("submit", async ev => {
      ev.preventDefault();
      const input = document.getElementById("chat-input");
      const text = input.value.trim();
      if (!text || !chatWith) return;
      input.value = "";
      try { await api("POST", `/api/chat/${encodeURIComponent(chatWith)}`, { text }); await loadChat(); }
      catch (e) { input.value = text; setChatStatus(e.message); }
    });
    document.getElementById("chat-file").addEventListener("change", async ev => {
      const file = ev.target.files[0];
      ev.target.value = "";
      if (file && chatWith) sendMedia(chatWith, file);
    });

    function setChatStatus(t) { document.getElementById("chat-status").textContent = t || ""; }

    function openChat(name) {
      closeCard();  // the chat takes the card's place on the right
      chatWith = name; chatKey = "";
      document.getElementById("chat-title").textContent = "💬 " + name;
      ui.chat.classList.add("open");
      log().innerHTML = "";
      setChatStatus("");
      loadChat();
      clearInterval(chatTimer);
      chatTimer = setInterval(() => { if (!document.hidden) loadChat(); }, 4000);
      document.getElementById("chat-input").focus();
    }
    function closeChat() { chatWith = null; clearInterval(chatTimer); ui.chat.classList.remove("open"); }

    async function loadChat() {
      const name = chatWith;
      if (!name) return;
      let r;
      try { r = await api("GET", `/api/chat/${encodeURIComponent(name)}`); }
      catch (e) { setChatStatus(e.message); return; }
      if (name !== chatWith) return;
      const key = JSON.stringify(r.messages.map(m => [m.id, m.media && m.media.waiting]));
      if (key === chatKey) return;
      chatKey = key;
      const box = log();
      const atBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 40;
      box.innerHTML = "";
      r.messages.forEach(m => {
        const b = el("div", "bubble " + (m.mine ? "mine" : "theirs"));
        if (m.media) {
          const icon = { image: "📷 Photo", audio: "🎵 Audio", video: "🎬 Video" }[m.media.kind] || "📎 Media";
          if (m.mine) b.appendChild(el("span", m.media.waiting ? "" : "gone", icon + (m.media.waiting ? " · sent, not opened yet" : " · opened")));
          else if (m.media.waiting) {
            const open = el("button", null, icon + (m.media.kind === "image" ? " · tap to view (10 s)" : " · tap to play once"));
            open.type = "button";
            open.addEventListener("click", () => openMedia(m.media));
            b.appendChild(open);
          } else b.appendChild(el("span", "gone", icon + " · opened"));
        } else {
          b.textContent = m.text;
        }
        b.title = new Date(/[zZ]$/.test(m.at) ? m.at : m.at + "Z").toLocaleString();
        box.appendChild(b);
      });
      if (!r.messages.length) box.appendChild(el("div", "soc-note", "Say hi 👋"));
      if (atBottom || box.children.length < 30) box.scrollTop = box.scrollHeight;
    }

    // ------------------------------------------------------------------
    // End-to-end encrypted, view-once media
    // ------------------------------------------------------------------
    const CURVE = { name: "ECDH", namedCurve: "P-256" };
    function b64(bytes) { let s = ""; bytes.forEach(x => (s += String.fromCharCode(x))); return btoa(s); }
    function unb64(str) { return Uint8Array.from(atob(str), c => c.charCodeAt(0)); }

    function idb() {
      return new Promise((resolve, reject) => {
        const req = indexedDB.open("mindgalaxy-keys", 1);
        req.onupgradeneeded = () => req.result.createObjectStore("keys");
        req.onsuccess = () => resolve(req.result);
        req.onerror = () => reject(req.error);
      });
    }
    async function idbGet(k) {
      const db = await idb();
      return new Promise(res => { const t = db.transaction("keys").objectStore("keys").get(k); t.onsuccess = () => res(t.result); t.onerror = () => res(null); });
    }
    async function idbPut(k, v) {
      const db = await idb();
      return new Promise(res => { const t = db.transaction("keys", "readwrite").objectStore("keys").put(v, k); t.onsuccess = () => res(); t.onerror = () => res(); });
    }

    let myKeys = null;
    async function keys() {
      if (myKeys) return myKeys;
      const slot = "user:" + G.owner;
      let pair = await idbGet(slot);
      if (!pair) {
        // the private key is non-extractable: it can be used here, never exported
        pair = await crypto.subtle.generateKey(CURVE, false, ["deriveKey"]);
        await idbPut(slot, pair);
      }
      const pub = await crypto.subtle.exportKey("jwk", pair.publicKey);
      myKeys = { priv: pair.privateKey, pubJwk: { kty: pub.kty, crv: pub.crv, x: pub.x, y: pub.y } };
      return myKeys;
    }
    async function sharedKey(theirJwk, usage) {
      const { priv } = await keys();
      const theirPub = await crypto.subtle.importKey("jwk", theirJwk, CURVE, false, []);
      return crypto.subtle.deriveKey({ name: "ECDH", public: theirPub }, priv, { name: "AES-GCM", length: 256 }, false, [usage]);
    }

    async function sendMedia(name, file) {
      const kind = (file.type || "").split("/")[0];
      if (!["image", "audio", "video"].includes(kind)) return setChatStatus("Only photos, audio and video can be sent.");
      if (file.size > 4 * 1024 * 1024 - 64) return setChatStatus("That file is over 4 MB. Try a shorter clip or smaller photo.");
      try {
        setChatStatus("Encrypting…");
        const { jwk } = await api("GET", `/api/keys/${encodeURIComponent(name)}`);
        if (!jwk) return setChatStatus(`${name} needs to open Galactic Connections once before they can receive media.`);
        const key = await sharedKey(JSON.parse(jwk), "encrypt");
        const iv = crypto.getRandomValues(new Uint8Array(12));
        const data = await crypto.subtle.encrypt({ name: "AES-GCM", iv }, key, await file.arrayBuffer());
        const { pubJwk } = await keys();
        setChatStatus("Sending…");
        const r = await fetch(`/api/chat/${encodeURIComponent(name)}/media`, {
          method: "POST", body: data,
          headers: { "Content-Type": "application/octet-stream", "X-MindGalaxy": "1", "X-Media-Kind": kind,
            "X-Media-Mime": file.type, "X-Media-IV": b64(iv), "X-Media-Key": JSON.stringify(pubJwk) },
        });
        const out = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(out.error || `Upload failed (${r.status})`);
        setChatStatus("Sent. It disappears after it's viewed.");
        await loadChat();
      } catch (e) { setChatStatus(e.message); }
    }

    async function openMedia(media) {
      const viewer = ui.viewer;
      viewer.innerHTML = "";
      viewer.classList.add("open");
      viewer.appendChild(el("div", "note", "Decrypting…"));
      let url = null, timer = 0;
      const finish = () => {
        clearInterval(timer);
        if (url) URL.revokeObjectURL(url);
        url = null;
        viewer.innerHTML = "";
        viewer.classList.remove("open");
        chatKey = "";
        loadChat();
      };
      try {
        const r = await fetch(`/api/media/${media.id}/open`, { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
        if (!r.ok) { const e = await r.json().catch(() => ({})); throw new Error(e.error || "This media is no longer available."); }
        const cipher = await r.arrayBuffer();
        const key = await sharedKey(JSON.parse(r.headers.get("X-Media-Key")), "decrypt");
        let plain;
        try { plain = await crypto.subtle.decrypt({ name: "AES-GCM", iv: unb64(r.headers.get("X-Media-IV")) }, key, cipher); }
        catch (e) { throw new Error("This was encrypted for your key on another device, so it can't be opened here. It has now been deleted."); }
        url = URL.createObjectURL(new Blob([plain], { type: r.headers.get("X-Media-Mime") }));
        viewer.innerHTML = "";
        const kind = r.headers.get("X-Media-Kind");
        const note = el("div", "note");
        if (kind === "image") {
          const img = document.createElement("img");
          img.src = url; img.alt = "View-once photo"; img.draggable = false;
          img.addEventListener("contextmenu", ev => ev.preventDefault());
          const t = el("div", "timer", "10");
          viewer.appendChild(t); viewer.appendChild(img);
          note.textContent = "View-once photo · disappears when the timer ends";
          let left = 10;
          timer = setInterval(() => { left--; t.textContent = String(left); if (left <= 0) finish(); }, 1000);
        } else {
          const media = document.createElement(kind === "video" ? "video" : "audio");
          media.src = url; media.autoplay = true; media.controls = true;
          media.setAttribute("controlsList", "nodownload noplaybackrate");
          media.disablePictureInPicture = true;
          media.addEventListener("contextmenu", ev => ev.preventDefault());
          media.addEventListener("ended", finish);
          viewer.appendChild(media);
          note.textContent = "Plays once · disappears when it ends";
        }
        viewer.appendChild(note);
        const closeBtn = el("button", "soc-btn", "Close (it's gone after this)");
        closeBtn.type = "button"; closeBtn.style.width = "auto";
        closeBtn.addEventListener("click", finish);
        viewer.appendChild(closeBtn);
      } catch (e) {
        viewer.innerHTML = "";
        viewer.appendChild(el("div", "note", e.message));
        const ok = el("button", "soc-btn", "OK"); ok.type = "button"; ok.style.width = "auto";
        ok.addEventListener("click", finish);
        viewer.appendChild(ok);
      }
    }

    // ------------------------------------------------------------------
    // The black hole swallows a galaxy
    // ------------------------------------------------------------------
    let swallowing = null;
    function playSwallows(list) {
      const s = list[0];
      const pos = placeOf(s.with);
      const victimPos = s.you_were_swallowed ? new THREE.Vector3(0, 0, 0) : pos;
      const holePos = pos.clone().multiplyScalar(0.5);
      const galaxy = spiralGalaxy(s.swallowed, 30);
      galaxy.position.copy(victimPos);
      scene.add(galaxy);
      const hole = blackHole();
      hole.position.copy(holePos);
      scene.add(hole);
      G.deselect();
      if (openName === s.with) closeCard();
      G.flyTo(holePos, 260);
      swallowing = { t0: null, galaxy, hole, from: victimPos.clone(), holePos, done: false, info: s, rest: list.slice(1) };
      toast(s.you_were_swallowed
        ? `🕳️ The black hole between you and ${s.with} has swallowed your galaxy's link to them. You're cut apart for ever.`
        : `🕳️ The black hole is swallowing ${s.swallowed}'s galaxy. You'll never be connected again.`, 6500);
    }

    function swallowFrame(t) {
      const sw = swallowing;
      if (!sw || sw.done) return;
      if (sw.t0 === null) sw.t0 = t;
      const k = Math.min(1, (t - sw.t0) / 5.5);   // 5.5 s from first tug to gone
      const ease = k * k * (3 - 2 * k);
      // spiral in: orbit the hole faster and faster while falling towards it
      const off = sw.from.clone().sub(sw.holePos);
      const ang = ease * Math.PI * 5;
      const r = 1 - ease;
      const rotated = new THREE.Vector3(off.x * Math.cos(ang) - off.z * Math.sin(ang), off.y, off.x * Math.sin(ang) + off.z * Math.cos(ang));
      sw.galaxy.position.copy(sw.holePos).add(rotated.multiplyScalar(r));
      sw.galaxy.scale.setScalar(Math.max(0.02, 1 - ease * 0.98));
      sw.galaxy.scale.x *= 1 + ease * 2.5;             // stretched by the tide
      sw.galaxy.rotation.y += 0.05 + ease * 0.3;
      sw.hole.scale.setScalar(1 + Math.sin(k * Math.PI) * 1.6);
      sw.hole.userData.ring.rotation.z += 0.04 + ease * 0.2;
      if (k >= 1) {
        sw.done = true;
        [sw.galaxy, sw.hole].forEach(o => { scene.remove(o); G.disposeObject(o); });
        swallowing = null;
        api("POST", "/api/swallows/seen", {}).catch(() => null);
        if (sw.rest.length) setTimeout(() => playSwallows(sw.rest), 800);
        else refresh(true);
      }
    }

    // ------------------------------------------------------------------
    keys().then(k => api("POST", "/api/keys", { jwk: JSON.stringify(k.pubJwk) })).catch(() => null);
    refresh(true);
    setInterval(() => { if (!document.hidden) refresh(false); }, 15000);
  }

  document.addEventListener("mindgalaxy:ready", bind);
  if (window.MindGalaxy) bind();
})();
