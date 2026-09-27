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
    family_link: "(an elder) asks to link their family",
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

    // ------------------------------------------------------------------
    // Every galaxy has its own symbol, derived from its owner's name: a
    // galaxy type (spiral, barred, ring, elliptical, lenticular, irregular,
    // grand design), arm count, two colours and a tilt. The same symbol is
    // drawn in 3D in the universe and as a small logo on tags, cards,
    // chats and calls.
    // ------------------------------------------------------------------
    const TYPES = ["spiral", "barred", "ring", "elliptical", "lenticular", "irregular", "grand"];
    function symbolOf(name) {
      const h = hash(name), h2 = hash(name + "*");
      return {
        type: TYPES[h % TYPES.length],
        arms: 2 + (h2 % 4),                 // 2-5 arms
        hue: (h >> 8) % 360,
        hue2: ((h >> 8) % 360 + 40 + (h2 % 140)) % 360,
        twist: 3.5 + ((h2 >> 6) % 30) / 10, // how tightly the arms wind
        tilt: ((h >> 16) % 100) / 100 * 0.9 - 0.45,
        seed: h2,
      };
    }
    function rng(seed) { let x = seed || 1; return () => ((x = Math.imul(x ^ (x >>> 15), 2246822507) ^ Math.imul(x ^ (x >>> 13), 3266489909)) >>> 0) / 4294967296; }

    // points (x, y in -1..1, t = distance from centre 0..1) for a symbol
    function symbolPoints(sym, n) {
      const r = rng(sym.seed), pts = [];
      for (let i = 0; i < n; i++) {
        const t = Math.pow(r(), 0.8);
        let x, y;
        switch (sym.type) {
          case "elliptical": {
            const a = r() * Math.PI * 2, d = Math.pow(r(), 1.6);
            x = Math.cos(a) * d; y = Math.sin(a) * d * 0.62;
            pts.push([x, y, d]); continue;
          }
          case "lenticular": {
            const a = r() * Math.PI * 2, d = Math.pow(r(), 1.3);
            x = Math.cos(a) * d; y = Math.sin(a) * d * 0.28;
            pts.push([x, y, d]); continue;
          }
          case "ring": {
            if (r() < 0.25) { const a = r() * 6.283, d = r() * 0.22; pts.push([Math.cos(a) * d, Math.sin(a) * d, d]); continue; }
            const a = r() * Math.PI * 2, d = 0.72 + (r() - 0.5) * 0.18;
            pts.push([Math.cos(a) * d, Math.sin(a) * d, d]); continue;
          }
          case "irregular": {
            const c = Math.floor(r() * 4), cr = rng(sym.seed + c * 97);
            const cx = cr() * 1.2 - 0.6, cy = cr() * 1.2 - 0.6, d = Math.pow(r(), 0.7) * 0.45, a = r() * 6.283;
            pts.push([cx + Math.cos(a) * d, cy + Math.sin(a) * d, Math.hypot(cx, cy)]); continue;
          }
          case "barred": {
            if (t < 0.35) { const bx = (r() - 0.5) * 0.9; pts.push([bx, (r() - 0.5) * 0.12, Math.abs(bx)]); continue; }
            break;
          }
        }
        // spiral families: arms winding out from the centre
        const arms = sym.type === "grand" ? 2 : sym.arms;
        const arm = i % arms;
        const start = sym.type === "barred" ? 0.35 : 0;
        const tt = start + t * (1 - start);
        const spread = sym.type === "grand" ? 0.12 : 0.28;
        const ang = tt * sym.twist + (arm / arms) * Math.PI * 2 + (r() - 0.5) * spread;
        x = Math.cos(ang) * tt + (r() - 0.5) * 0.06;
        y = Math.sin(ang) * tt + (r() - 0.5) * 0.06;
        pts.push([x, y, tt]);
      }
      return pts;
    }

    function spiralGalaxy(name, starCount) {
      const sym = symbolOf(name);
      const group = new THREE.Group();
      const n = 260 + Math.min(starCount, 60) * 8;
      const R = 34 + Math.min(starCount, 60) * 0.9;
      const pos = new Float32Array(n * 3), col = new Float32Array(n * 3);
      const c = new THREE.Color(), c1 = new THREE.Color().setHSL(sym.hue / 360, 0.8, 0.7), c2 = new THREE.Color().setHSL(sym.hue2 / 360, 0.8, 0.6);
      const r = rng(sym.seed + 7);
      symbolPoints(sym, n).forEach(([x, y, t], i) => {
        pos[i * 3] = x * R;
        pos[i * 3 + 1] = (r() - 0.5) * 3 * (1 - Math.min(1, t));
        pos[i * 3 + 2] = y * R;
        c.copy(c1).lerp(c2, Math.min(1, t)).multiplyScalar(0.75 + (1 - Math.min(1, t)) * 0.5);
        col[i * 3] = c.r; col[i * 3 + 1] = c.g; col[i * 3 + 2] = c.b;
      });
      const geo = new THREE.BufferGeometry();
      geo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
      geo.setAttribute("color", new THREE.BufferAttribute(col, 3));
      group.add(new THREE.Points(geo, new THREE.PointsMaterial({
        size: 3.2, map: G.glowTex, vertexColors: true, transparent: true, opacity: 0.85,
        depthWrite: false, blending: THREE.AdditiveBlending,
      })));
      const core = new THREE.Sprite(new THREE.SpriteMaterial({
        map: G.glowTex, color: new THREE.Color().setHSL(sym.hue / 360, 0.6, 0.85), transparent: true,
        depthWrite: false, blending: THREE.AdditiveBlending,
      }));
      const coreSize = sym.type === "ring" ? 14 : sym.type === "irregular" ? 18 : 30;
      core.scale.set(coreSize, coreSize, 1);
      group.add(core);
      group.rotation.x = sym.tilt;
      group.userData.spin = 0.0008 + (sym.seed % 10) / 10000;
      return group;
    }

    // the same symbol as a small round logo (data: URL, cached)
    const logoCache = {};
    function symbolLogo(name, size) {
      size = size || 64;
      const key = name + "@" + size;
      if (logoCache[key]) return logoCache[key];
      const sym = symbolOf(name);
      const cnv = document.createElement("canvas");
      cnv.width = cnv.height = size;
      const ctx = cnv.getContext("2d");
      const g = ctx.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2);
      g.addColorStop(0, `hsl(${sym.hue},55%,18%)`);
      g.addColorStop(1, "#05060f");
      ctx.fillStyle = g;
      ctx.beginPath(); ctx.arc(size / 2, size / 2, size / 2, 0, 6.283); ctx.fill();
      ctx.save();
      ctx.translate(size / 2, size / 2);
      ctx.rotate(sym.tilt * 2);
      ctx.globalCompositeOperation = "lighter";
      const R = size * 0.42, dot = Math.max(0.6, size / 70);
      symbolPoints(sym, Math.round(size * 7)).forEach(([x, y, t]) => {
        ctx.fillStyle = `hsla(${t < 0.5 ? sym.hue : sym.hue2},85%,${75 - t * 25}%,0.55)`;
        ctx.fillRect(x * R, y * R, dot, dot);
      });
      const core = ctx.createRadialGradient(0, 0, 0, 0, 0, size * 0.14);
      core.addColorStop(0, "rgba(255,250,235,0.95)");
      core.addColorStop(1, "rgba(255,250,235,0)");
      ctx.fillStyle = core;
      ctx.beginPath(); ctx.arc(0, 0, size * 0.14, 0, 6.283); ctx.fill();
      ctx.restore();
      return (logoCache[key] = cnv.toDataURL());
    }
    function logoImg(name, size, cls) {
      const img = document.createElement("img");
      img.src = symbolLogo(name, (size || 20) * 2);
      img.width = img.height = size || 20;
      img.alt = "";
      img.className = cls || "gx-logo";
      return img;
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
        // people you're connected with show whether they're online: offline
        // galaxies keep their shape and colours but lose their glow
        if (gx.can_text && !gx.online) {
          galaxy.children.forEach(o => { if (o.material) o.material.opacity *= o.isPoints ? 0.28 : 0.2; });
          galaxy.userData.spin *= 0.3;
        }
        add(galaxy); spinning.push(galaxy);
        // a screen-sized name tag that follows the galaxy (readable at any zoom)
        const label = el("button", "gx-tag");
        label.type = "button";
        label.appendChild(logoImg(gx.username, 18));
        label.appendChild(document.createTextNode((rel ? STATUS[rel].emoji + " " : "") + gx.username));
        if (gx.online) label.appendChild(el("span", "gx-online", "●"));
        label.style.borderColor = rel ? STATUS[rel].css : "rgba(142,162,255,0.5)";
        if (gx.can_text && !gx.online) { label.classList.add("offline"); label.title = gx.username + " is offline"; }
        if (unreadFrom(gx.username)) label.appendChild(el("span", "gx-unread", "💬 " + unreadFrom(gx.username)));
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
      renderCounter();
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
        collectNotifications(next);
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
      .gx-tag { display: flex; align-items: center; gap: 6px; }
      .gx-logo { border-radius: 50%; vertical-align: middle; flex-shrink: 0; box-shadow: 0 0 8px rgba(160,140,255,0.35); }
      .gx-logo.big { box-shadow: 0 0 16px rgba(160,140,255,0.5); }
      .gx-title { display: flex; align-items: center; gap: 10px; }
      .gx-online { color: #5ff08a; font-size: 10px; }
      #chat-title { display: flex; align-items: center; gap: 6px; }
      .gx-tag.offline { opacity: 0.55; filter: saturate(0.6); }
      .gx-unread { background: #ff6b8a; color: #fff; border-radius: 10px; padding: 0 6px; font-size: 10.5px; }
      #bell-btn { position: relative; }
      .bell-count { position: absolute; top: -6px; right: -6px; min-width: 17px; height: 17px; padding: 0 4px; border-radius: 9px;
        background: #ff5a6e; color: #fff; font-size: 10px; font-weight: 700; display: flex; align-items: center; justify-content: center; }
      #bell-panel { position: fixed; top: 62px; right: 26px; width: min(360px, calc(100vw - 32px)); max-height: 70vh; overflow-y: auto;
        padding: 12px; z-index: 60; display: none; }
      #bell-panel.open { display: block; }
      .np-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
      .np-link { font: inherit; font-size: 11.5px; background: none; border: none; color: var(--accent); cursor: pointer; }
      .np-item { display: flex; gap: 9px; align-items: flex-start; width: 100%; text-align: left; font: inherit; color: var(--text);
        background: transparent; border: none; border-radius: 10px; padding: 8px; cursor: pointer; }
      .np-item:hover { background: rgba(255,255,255,0.06); }
      .np-item.unread { background: rgba(142,162,255,0.1); }
      .np-text { font-size: 13px; line-height: 1.4; }
      .np-time { font-size: 10.5px; color: var(--muted); margin-top: 2px; }
      #notif-pop { position: fixed; top: 64px; right: 26px; z-index: 170; display: flex; gap: 10px; align-items: center; padding: 12px 14px;
        max-width: min(360px, calc(100vw - 32px)); cursor: pointer; transform: translateY(-16px); opacity: 0; pointer-events: none;
        transition: transform 0.3s ease, opacity 0.3s ease; }
      #notif-pop.open { transform: none; opacity: 1; pointer-events: auto; }
      .perm-ask { position: fixed; right: 26px; top: 130px; z-index: 70; width: min(360px, calc(100vw - 24px)); padding: 14px; }
      .perm-ask .soc-row { margin-top: 10px; }
      #friend-counter { position: fixed; right: 26px; bottom: 76px; z-index: 12; display: flex; gap: 12px; padding: 8px 14px;
        font: inherit; font-size: 13px; color: var(--text); cursor: pointer; }
      @media (max-width: 720px) {
        #bell-panel, #notif-pop { right: 12px; left: 12px; width: auto; top: 128px; z-index: 60; }
        #friend-counter { right: 16px; bottom: 150px; font-size: 13px; gap: 10px; }
      }
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
      const bell = el("button", "pill-btn"); bell.id = "bell-btn"; bell.type = "button";
      bell.setAttribute("aria-label", "Notifications");
      bell.appendChild(document.createTextNode("🔔"));
      const bellCount = el("span", "bell-count"); bell.appendChild(bellCount);
      row.insertBefore(bell, document.getElementById("user-chip"));
      const bellPanel = el("div", "hud panel"); bellPanel.id = "bell-panel";
      const pop = el("div", "panel"); pop.id = "notif-pop"; pop.setAttribute("role", "status");
      const counter = el("button", "hud panel"); counter.id = "friend-counter"; counter.type = "button";
      counter.title = "Your connections";
      counter.addEventListener("click", () => reqBtn.click());
      const tags = el("div"); tags.id = "gx-tags";
      [tags, card, reqPanel, chat, viewer, toast, bellPanel, pop, counter].forEach(n => document.body.appendChild(n));
      reqBtn.addEventListener("click", () => {
        const open = !reqPanel.classList.contains("open");
        closeCard();
        reqPanel.classList.toggle("open", open);
        if (open) renderRequests();
      });
      return { reqBtn, reqCount, card, reqPanel, chat, viewer, toast, tags, bell, bellCount, bellPanel, pop, counter };
    }

    let toastTimer = 0;
    function toast(msg, ms) {
      ui.toast.textContent = msg;
      ui.toast.classList.add("open");
      clearTimeout(toastTimer);
      toastTimer = setTimeout(() => ui.toast.classList.remove("open"), ms || 3500);
    }

    function roleSelect(value) {
      const sel = document.createElement("select");
      sel.className = "soc-input";
      (data.roles || []).forEach(r => {
        const o = document.createElement("option");
        o.value = r; o.textContent = r.charAt(0).toUpperCase() + r.slice(1);
        if (r === (value || "other")) o.selected = true;
        sel.appendChild(o);
      });
      return sel;
    }
    function describe(r) {
      let t = `${KIND_TEXT[r.kind] || r.kind}`;
      if (r.kind === "family_link") t += ` “${r.family_name}” with your family “${r.family2_name}”`;
      else if (r.family_name) t += ` “${r.family_name}”`;
      return t;
    }
    function acceptRow(r) {
      const wrap = el("div");
      let sel = null;
      if (r.kind === "family_invite") {
        wrap.appendChild(el("div", "soc-note", "Your role in this family:"));
        sel = roleSelect("other");
        wrap.appendChild(sel);
      }
      const row = el("div", "soc-row"); row.style.marginTop = "6px";
      row.appendChild(button("Accept", "primary", () => act(() => api("POST", `/api/requests/${r.id}/respond`,
        { accept: true, role: sel ? sel.value : undefined }), "Accepted")));
      row.appendChild(button("Decline", "", () => act(() => api("POST", `/api/requests/${r.id}/respond`, { accept: false }))));
      wrap.appendChild(row);
      return wrap;
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
      const title = el("h2", "gx-title");
      title.appendChild(logoImg(name, 34, "gx-logo big"));
      title.appendChild(document.createTextNode((rel ? STATUS[rel].emoji + " " : "") + name));
      card.appendChild(title);
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
        card.appendChild(el("div", "soc-msg", `${name} ${describe(r)}`));
        card.appendChild(acceptRow(r));
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

      if (gx.can_text) card.appendChild(button(gx.can_chat ? "💬 Chat" : "💬 Chat (words only)", "primary", () => openChat(name)));
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
      // calls.js adds its call buttons here
      document.dispatchEvent(new CustomEvent("gc:card", { detail: { name, gx, card } }));
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
        const who = el("b");
        who.appendChild(logoImg(r.from, 18));
        who.appendChild(document.createTextNode(" " + r.from));
        item.appendChild(who);
        item.appendChild(document.createTextNode(" " + describe(r)));
        item.appendChild(acceptRow(r));
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
        const list = el("div", "soc-note");
        f.members.forEach((m, k) => {
          if (k) list.appendChild(document.createTextNode(" · "));
          list.appendChild(logoImg(m, 14));
          list.appendChild(document.createTextNode(` ${m} (${(f.roles && f.roles[m]) || "other"})`));
        });
        item.appendChild(list);
        item.appendChild(el("div", "soc-note", "Your role:"));
        const sel = roleSelect(f.my_role);
        sel.addEventListener("change", () => act(() => api("POST", `/api/families/${f.id}/role`, { role: sel.value }), "Role updated"));
        item.appendChild(sel);
        (f.links || []).forEach(link => {
          item.appendChild(el("div", "soc-note", `🔗 Linked with family “${link.name}”: ` +
            link.members.map(m => `${m.username} (${m.role})`).join(", ")));
        });
        if (f.i_am_elder) {
          const who = el("input", "soc-input"); who.type = "text";
          who.placeholder = "Link with another family — an elder's username";
          item.appendChild(who);
          item.appendChild(button("🔗 Send family link request", "", () => {
            if (!who.value.trim()) return toast("Type the username of a parent or grandparent in the other family.");
            act(() => api("POST", "/api/family-links", { family_id: f.id, to: who.value.trim().toLowerCase() }),
              "Family link request sent");
          }));
        } else {
          item.appendChild(el("div", "soc-note", "Only a parent, step-parent, parent-in-law or grandparent can link this family with another family."));
        }
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

      // calls.js adds the group-call builder here
      document.dispatchEvent(new CustomEvent("gc:panel", { detail: { panel: p } }));

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
    // Notifications: a bell with everything that happened, pop-ups with a
    // chime, and (if allowed) the device's own notifications when the tab
    // is in the background. Kept per user on this device.
    // ------------------------------------------------------------------
    const NKEY = "gc-notifs:" + G.owner, SKEY = "gc-seen:" + G.owner;
    const load = (k, d) => { try { return JSON.parse(localStorage.getItem(k)) || d; } catch (e) { return d; } };
    const save = (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) { /* private mode */ } };
    let notes = load(NKEY, []);
    let seen = load(SKEY, null);
    const unread = {};   // username -> unread message count

    function unreadFrom(name) { return unread[name] || 0; }
    function markRead(name) {
      if (!unread[name]) return;
      delete unread[name];
      notes.forEach(n => { if (n.kind === "message" && n.name === name) n.read = true; });
      save(NKEY, notes);
      renderBell();
      if (data) draw();
    }

    function chime() {
      try {
        const ctx = new (window.AudioContext || window.webkitAudioContext)();
        [[880, 0], [1320, 0.12]].forEach(([f, t]) => {
          const o = ctx.createOscillator(), g = ctx.createGain();
          o.type = "sine"; o.frequency.value = f; o.connect(g); g.connect(ctx.destination);
          g.gain.setValueAtTime(0.0001, ctx.currentTime + t);
          g.gain.exponentialRampToValueAtTime(0.18, ctx.currentTime + t + 0.02);
          g.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + t + 0.35);
          o.start(ctx.currentTime + t); o.stop(ctx.currentTime + t + 0.4);
        });
        setTimeout(() => ctx.close().catch(() => null), 900);
      } catch (e) { /* sound not allowed yet */ }
    }

    function runAction(n) {
      if (n.kind === "sky") { if (window.MindGalaxy && window.MindGalaxy.openBody) window.MindGalaxy.openBody(n.body); return; }
      if (n.name && n.kind === "message") openChat(n.name);
      else if (n.name) openCard(n.name);
      else ui.reqBtn.click();
    }

    let popTimer = 0;
    function notify(n) {
      n = Object.assign({ id: Date.now() + Math.random(), at: new Date().toISOString(), read: false, popup: true }, n);
      notes.unshift(n);
      notes = notes.slice(0, 80);
      save(NKEY, notes);
      renderBell();
      if (!n.popup) return;
      chime();
      if (navigator.vibrate) navigator.vibrate(60);
      const pop = ui.pop;
      pop.innerHTML = "";
      if (n.name) pop.appendChild(logoImg(n.name, 28));
      pop.appendChild(el("div", "np-text", `${n.icon || "🔔"} ${n.text}`));
      pop.onclick = () => { pop.classList.remove("open"); runAction(n); };
      pop.classList.add("open");
      clearTimeout(popTimer);
      popTimer = setTimeout(() => pop.classList.remove("open"), 5500);
      if (["message", "call", "request"].includes(n.kind)) askAlertsOnce();
      if (document.hidden && "Notification" in window && Notification.permission === "granted") {
        try {
          const dn = new Notification("Galactic Connections", { body: `${n.icon || ""} ${n.text}`, icon: "/icon-192.png", tag: String(n.kind) + (n.name || "") });
          dn.onclick = () => { window.focus(); runAction(n); dn.close(); };
        } catch (e) { /* not supported here */ }
      }
    }
    window.GC_notify = notify;

    // The first time something important arrives, offer to turn on alerts
    // (browsers only allow the question after a tap). Asked at most once a week.
    function askAlertsOnce() {
      if (!("Notification" in window) || Notification.permission !== "default") return;
      const key = "gc-alerts-asked:" + G.owner;
      try { if (Date.now() - Number(localStorage.getItem(key) || 0) < 7 * 864e5) return; localStorage.setItem(key, String(Date.now())); } catch (e) { return; }
      const box = el("div", "hud panel perm-ask");
      box.appendChild(el("div", "np-text", "🔔 Turn on alerts so you never miss a message or call, even when this tab is in the background?"));
      const row = el("div", "soc-row");
      row.appendChild(button("Not now", "", () => box.remove()));
      row.appendChild(button("Turn on", "primary", async () => { try { await Notification.requestPermission(); } catch (e) { /* ignored */ } box.remove(); }));
      box.appendChild(row);
      document.body.appendChild(box);
      setTimeout(() => box.remove(), 20000);
    }   // calls.js and the galaxy page report here too

    function collectNotifications(u) {
      const first = !seen;
      seen = seen || { msg: 0, req: [] };
      const newest = Math.max(seen.msg, ...u.inbox.map(m => m.id), 0);
      if (!first) {
        u.inbox.filter(m => m.id > seen.msg).reverse().forEach(m => {
          const open = chatWith === m.from && ui.chat.classList.contains("open") && !document.hidden;
          if (!open) unread[m.from] = (unread[m.from] || 0) + 1;
          notify({ kind: "message", icon: "💬", name: m.from, text: `${m.from}: ${m.preview}`, popup: !open });
          if (open) loadChat();
        });
        u.requests_in.filter(r => !seen.req.includes(r.id)).forEach(r =>
          notify({ kind: "request", icon: "✉️", name: r.from, text: `${r.from} ${describe(r)}` }));
      }
      seen = { msg: newest, req: u.requests_in.map(r => r.id) };
      save(SKEY, seen);
      if (Object.keys(unread).length) draw();
    }

    function renderBell() {
      const count = notes.filter(n => !n.read).length;
      ui.bellCount.textContent = count ? String(Math.min(count, 99)) : "";
      ui.bellCount.style.display = count ? "" : "none";
      if (ui.bellPanel.classList.contains("open")) renderNotes();
    }
    function renderNotes() {
      const p = ui.bellPanel;
      p.innerHTML = "";
      const head = el("div", "np-head");
      head.appendChild(el("b", null, "Notifications"));
      const clear = el("button", "np-link", "Mark all read");
      clear.type = "button";
      clear.onclick = () => { notes.forEach(n => (n.read = true)); Object.keys(unread).forEach(k => delete unread[k]); save(NKEY, notes); renderBell(); renderNotes(); draw(); };
      head.appendChild(clear);
      p.appendChild(head);
      if ("Notification" in window && Notification.permission === "default") {
        const ask = button("🔔 Also notify me when this tab is in the background", "", async () => {
          try { await Notification.requestPermission(); } catch (e) { /* ignored */ }
          renderNotes();
        });
        p.appendChild(ask);
      } else if ("Notification" in window && Notification.permission === "denied") {
        p.appendChild(el("div", "soc-note", "🔕 Alerts are turned off for this site, so you'll only see messages and calls while it's open. " +
          "To turn them on: tap the 🔒 (or ⓘ) next to the address → Site settings → Notifications → Allow."));
      }
      if (!notes.length) p.appendChild(el("div", "soc-note", "Nothing yet. Messages, requests, calls and cosmic events show up here."));
      notes.forEach(n => {
        const row = el("button", "np-item" + (n.read ? "" : " unread"));
        row.type = "button";
        if (n.name) row.appendChild(logoImg(n.name, 22));
        const body = el("div");
        body.appendChild(el("div", "np-text", `${n.icon || "🔔"} ${n.text}`));
        body.appendChild(el("div", "np-time", new Date(n.at).toLocaleString()));
        row.appendChild(body);
        row.onclick = () => { n.read = true; save(NKEY, notes); renderBell(); p.classList.remove("open"); runAction(n); };
        p.appendChild(row);
      });
    }
    ui.bell.addEventListener("click", () => {
      const open = !ui.bellPanel.classList.contains("open");
      ui.bellPanel.classList.toggle("open", open);
      if (open) renderNotes();
    });
    // a tap anywhere else closes it
    document.addEventListener("pointerdown", e => {
      if (ui.bellPanel.classList.contains("open") && !ui.bellPanel.contains(e.target) && !ui.bell.contains(e.target)) {
        ui.bellPanel.classList.remove("open");
      }
    }, true);
    renderBell();

    // your connections, counted in the bottom-right corner
    function renderCounter() {
      const count = st => data.galaxies.filter(g => g.status === st).length;
      const family = new Set(data.families.flatMap(f => f.members)).size;
      const parts = [["🤝", count("friend"), "friends"], ["💞", count("partner"), "life partner"],
                     ["🏡", Math.max(0, family - (family ? 1 : 0)), "family"], ["⚔️", count("enemy"), "enemies"]];
      ui.counter.innerHTML = "";
      parts.forEach(([icon, n, label]) => {
        const sp = el("span", null, `${icon} ${n}`);
        sp.title = `${n} ${label}`;
        ui.counter.appendChild(sp);
      });
    }

    // instant "you've got a message" nudge through the call switchboard
    function notifyPeer(name) { if (window.gcNudge) window.gcNudge(name); }
    window.gcOnNudge = () => refresh(false);

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
      try { await api("POST", `/api/chat/${encodeURIComponent(chatWith)}`, { text }); notifyPeer(chatWith); await loadChat(); }
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
      const ct = document.getElementById("chat-title");
      ct.textContent = "";
      ct.appendChild(logoImg(name, 22));
      ct.appendChild(document.createTextNode(" " + name));
      ui.chat.classList.add("open");
      log().innerHTML = "";
      setChatStatus("");
      loadChat();
      clearInterval(chatTimer);
      chatTimer = setInterval(() => { if (!document.hidden) loadChat(); }, 4000);
      const gx = data && data.galaxies.find(g => g.username === name);
      // enemies can talk, but can't send photos or media
      document.querySelector("#chat-form label").style.display = gx && gx.can_chat ? "" : "none";
      document.getElementById("chat-input").focus();
      markRead(name);
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

    // Each device keeps its own key pair (private half non-extractable) and a
    // random device id; the server stores up to 6 public keys per user.
    let myKeys = null;
    async function keys() {
      if (myKeys) return myKeys;
      const slot = "device:" + G.owner;
      let rec = await idbGet(slot);
      if (!rec) {
        const old = await idbGet("user:" + G.owner);   // key from before devices had ids
        const pair = old || await crypto.subtle.generateKey(CURVE, false, ["deriveKey"]);
        const id = new Uint8Array(12);
        crypto.getRandomValues(id);
        rec = { pair, deviceId: "dev-" + Array.from(id, b => b.toString(16).padStart(2, "0")).join("") };
        await idbPut(slot, rec);
      }
      const pub = await crypto.subtle.exportKey("jwk", rec.pair.publicKey);
      myKeys = { priv: rec.pair.privateKey, deviceId: rec.deviceId,
                 pubJwk: { kty: pub.kty, crv: pub.crv, x: pub.x, y: pub.y } };
      return myKeys;
    }
    async function sharedKey(theirJwk, usage) {
      const { priv } = await keys();
      const theirPub = await crypto.subtle.importKey("jwk", theirJwk, CURVE, false, []);
      return crypto.subtle.deriveKey({ name: "ECDH", public: theirPub }, priv, { name: "AES-GCM", length: 256 }, false, [usage]);
    }

    // Big phone photos are shrunk (max 2560 px, JPEG) before encrypting, so
    // they fit the 4 MB limit and send quickly. Anything the browser can't
    // decode (e.g. HEIC outside Safari) is sent as it is.
    async function shrinkImage(file) {
      if (!file.type.startsWith("image/") || file.type === "image/gif" || file.size < 1.5 * 1024 * 1024) return file;
      try {
        const bmp = await createImageBitmap(file);
        const scale = Math.min(1, 2560 / Math.max(bmp.width, bmp.height));
        const c = document.createElement("canvas");
        c.width = Math.round(bmp.width * scale); c.height = Math.round(bmp.height * scale);
        c.getContext("2d").drawImage(bmp, 0, 0, c.width, c.height);
        const blob = await new Promise(res => c.toBlob(res, "image/jpeg", 0.88));
        return blob && blob.size < file.size ? new File([blob], "photo.jpg", { type: "image/jpeg" }) : file;
      } catch (e) { return file; }
    }

    async function sendMedia(name, original) {
      const kind = (original.type || "").split("/")[0];
      if (!["image", "audio", "video"].includes(kind)) return setChatStatus("Only photos, audio and video can be sent.");
      try {
        setChatStatus(kind === "image" ? "Preparing photo…" : "Encrypting…");
        const file = await shrinkImage(original);
        if (file.size > 4 * 1024 * 1024 - 64) {
          return setChatStatus("That file is over 4 MB. Try a shorter clip or a smaller photo.");
        }
        const { devices } = await api("GET", `/api/keys/${encodeURIComponent(name)}`);
        if (!devices || !devices.length) {
          return setChatStatus(`${name} needs to open Galactic Connections once before they can receive media.`);
        }
        // one random content key, wrapped separately for each of their devices
        const content = await crypto.subtle.generateKey({ name: "AES-GCM", length: 256 }, true, ["encrypt"]);
        const iv = crypto.getRandomValues(new Uint8Array(12));
        const data = await crypto.subtle.encrypt({ name: "AES-GCM", iv }, content, await file.arrayBuffer());
        const raw = new Uint8Array(await crypto.subtle.exportKey("raw", content));
        const wrapped = {};
        for (const d of devices.slice(0, 6)) {
          const k = await sharedKey(JSON.parse(d.jwk), "encrypt");
          const wiv = crypto.getRandomValues(new Uint8Array(12));
          wrapped[d.device_id] = { w: b64(new Uint8Array(await crypto.subtle.encrypt({ name: "AES-GCM", iv: wiv }, k, raw))), iv: b64(wiv) };
        }
        const { pubJwk } = await keys();
        setChatStatus("Sending…");
        const r = await fetch(`/api/chat/${encodeURIComponent(name)}/media`, {
          method: "POST", body: data,
          headers: { "Content-Type": "application/octet-stream", "X-MindGalaxy": "1", "X-Media-Kind": kind,
            "X-Media-Mime": file.type, "X-Media-IV": b64(iv),
            "X-Media-Key": JSON.stringify({ v: 2, sender: pubJwk, keys: wrapped }) },
        });
        const out = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(out.error || `Upload failed (${r.status})`);
        setChatStatus("Sent. It disappears after it's viewed.");
        notifyPeer(name);
        await loadChat();
      } catch (e) { setChatStatus(e.message); }
    }

    async function decryptMedia(r, cipher) {
      const env = JSON.parse(r.headers.get("X-Media-Key"));
      const iv = unb64(r.headers.get("X-Media-IV"));
      if (env && env.v === 2) {
        const k = await sharedKey(env.sender, "decrypt");
        const raw = await crypto.subtle.decrypt({ name: "AES-GCM", iv: unb64(env.wrapped.iv) }, k, unb64(env.wrapped.w));
        const content = await crypto.subtle.importKey("raw", raw, { name: "AES-GCM" }, false, ["decrypt"]);
        return crypto.subtle.decrypt({ name: "AES-GCM", iv }, content, cipher);
      }
      return crypto.subtle.decrypt({ name: "AES-GCM", iv }, await sharedKey(env, "decrypt"), cipher);   // older media
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
        const { deviceId } = await keys();
        const r = await fetch(`/api/media/${media.id}/open`, { method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ device_id: deviceId }) });
        if (!r.ok) { const e = await r.json().catch(() => ({})); throw new Error(e.error || "This media is no longer available."); }
        const cipher = await r.arrayBuffer();
        let plain;
        try { plain = await decryptMedia(r, cipher); }
        catch (e) { throw new Error("This couldn't be decrypted on this device."); }
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
      notify({ kind: "swallow", icon: "🕳️", text: s.you_were_swallowed
        ? `The black hole cut you apart from ${s.with} for ever.` : `The black hole swallowed ${s.swallowed}'s galaxy.`, popup: false });
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

    // your own symbol next to your name in the header
    const chip = document.getElementById("user-name");
    if (chip && !chip.previousElementSibling) chip.parentNode.insertBefore(logoImg(G.owner, 18), chip);

    // shared with calls.js and tour.js
    window.GC = {
      api, toast, logoImg, symbolLogo, openCard, openChat, el: (t, c, x) => el(t, c, x), button,
      get data() { return data; }, refresh: () => refresh(true),
      placeOf: name => placeOf(name),
    };
    document.dispatchEvent(new Event("gc:ready"));

    // ------------------------------------------------------------------
    keys().then(k => api("POST", "/api/keys", { jwk: JSON.stringify(k.pubJwk), device_id: k.deviceId })).catch(() => null);
    refresh(true);
    setInterval(() => { if (!document.hidden) refresh(false); }, 15000);
  }

  document.addEventListener("mindgalaxy:ready", bind);
  if (window.MindGalaxy) bind();
})();
