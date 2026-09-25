/*
 * Galactic Connections -- audio & video calls (hosted, signed-in site only).
 *
 * Calls are peer-to-peer WebRTC: audio and video go straight between the
 * browsers, always encrypted, and are never recorded or stored anywhere.
 * A PeerJS "switchboard" only passes the short set-up messages; each page
 * session uses a random, unguessable id that our server reveals only to
 * people allowed to call it.
 *
 * Who may be in a call is decided by the server when the call is created
 * (everyone must know everyone; audio up to 10, video up to 4). Each
 * browser also double-checks with the server before accepting a stream.
 */
(function () {
  "use strict";

  const PEERJS = "https://cdnjs.cloudflare.com/ajax/libs/peerjs/1.5.5/peerjs.min.js";
  const PEERJS_SRI = "sha384-x0YgkOr/3UOZP2CRDxGW9e0Q+2Qjyr3uJrm4xU32Y7ZCNAo7Cc7bjhrZMi/dwczu";
  const RING_SECONDS = 45;

  let GC = null, peer = null, iceServers = null;
  let call = null;      // { room, kind, stream, conns: Map(peerId -> {mc, name}), poll, started }
  let ringing = null;   // { room, conn, timer, tone }

  function loadPeerJs() {
    return new Promise((resolve, reject) => {
      if (window.Peer) return resolve();
      const s = document.createElement("script");
      s.src = PEERJS; s.integrity = PEERJS_SRI; s.crossOrigin = "anonymous";
      s.onload = resolve; s.onerror = () => reject(new Error("Couldn't load the calling library."));
      document.head.appendChild(s);
    });
  }

  function randomId() {
    const a = new Uint8Array(18);
    crypto.getRandomValues(a);
    return "gc-" + Array.from(a, b => b.toString(16).padStart(2, "0")).join("");
  }

  async function start() {
    GC = window.GC;
    window.gcBusy = () => !!call || !!ringing;  // keeps the idle sign-out away during calls
    injectStyles();
    buildUi();
    document.addEventListener("gc:card", e => addCardButtons(e.detail));
    document.addEventListener("gc:panel", e => addGroupBuilder(e.detail.panel));
    try { iceServers = (await GC.api("GET", "/api/calls/ice")).iceServers; }
    catch (e) { iceServers = [{ urls: ["stun:stun.l.google.com:19302"] }]; }
    try { await loadPeerJs(); } catch (e) { return; }  // calls simply stay unavailable
    connectPeer();
    setInterval(() => {
      if (!document.hidden && peer && peer.open) GC.api("POST", "/api/presence", { peer_id: peer.id }).catch(() => null);
    }, 60000);
    window.addEventListener("beforeunload", () => { if (call) navigator.sendBeacon && leaveBeacon(); });
  }

  function connectPeer() {
    peer = new window.Peer(randomId(), { config: { iceServers }, debug: 0 });
    peer.on("open", id => GC.api("POST", "/api/presence", { peer_id: id }).catch(() => null));
    peer.on("connection", handleData);
    peer.on("call", handleIncomingMedia);
    peer.on("disconnected", () => { try { peer.reconnect(); } catch (e) { /* will retry */ } });
    peer.on("error", err => {
      if (err && err.type === "unavailable-id") { peer.destroy(); connectPeer(); }
    });
  }

  // ------------------------------------------------------------------
  // Placing calls
  // ------------------------------------------------------------------
  function addCardButtons({ name, gx, card }) {
    if (!gx.can_chat) return;
    const row = GC.el("div", "soc-row");
    row.appendChild(GC.button("📞 Audio call", "", () => startCall([name], "audio")));
    row.appendChild(GC.button("🎥 Video call", "", () => startCall([name], "video")));
    card.appendChild(row);
    if (!gx.online) card.appendChild(GC.el("div", "soc-note", `${name} isn't online right now, so a call won't ring.`));
  }

  function addGroupBuilder(panel) {
    const contacts = (GC.data.galaxies || []).filter(g => g.can_chat);
    if (!contacts.length) return;
    panel.appendChild(GC.el("h3", null, "Group call"));
    panel.appendChild(GC.el("div", "soc-note",
      "Everyone in a call must know everyone else. Audio up to 10 people, video up to 4."));
    const picked = new Set();
    const list = GC.el("div", "call-pick");
    const msg = GC.el("div", "soc-note");
    contacts.forEach(g => {
      const lab = document.createElement("label");
      const box = document.createElement("input");
      box.type = "checkbox";
      box.addEventListener("change", () => { box.checked ? picked.add(g.username) : picked.delete(g.username); check(); });
      lab.appendChild(box);
      lab.appendChild(GC.logoImg(g.username, 16));
      lab.appendChild(document.createTextNode(" " + g.username + (g.online ? " ●" : "")));
      list.appendChild(lab);
    });
    panel.appendChild(list);
    panel.appendChild(msg);
    const row = GC.el("div", "soc-row");
    const audio = GC.button("📞 Audio group call", "", () => startCall([...picked], "audio"));
    const video = GC.button("🎥 Video group call", "", () => startCall([...picked], "video"));
    row.appendChild(audio); row.appendChild(video);
    panel.appendChild(row);
    let token = 0;
    async function check() {
      const t = ++token;
      if (!picked.size) { msg.textContent = ""; return; }
      const results = await Promise.all(["audio", "video"].map(kind =>
        GC.api("POST", "/api/calls/check", { usernames: [...picked], kind }).then(() => "", e => e.message)));
      if (t !== token) return;
      audio.disabled = !!results[0]; video.disabled = !!results[1];
      msg.textContent = results[0] || results[1] || `${picked.size + 1} people can call together.`;
    }
  }

  async function getMedia(kind) {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      throw new Error("This browser can't make calls.");
    }
    try {
      return await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true },
        video: kind === "video" ? { width: { ideal: 640 }, height: { ideal: 480 }, facingMode: "user" } : false,
      });
    } catch (e) {
      throw new Error(kind === "video" ? "Allow the camera and microphone to make a video call." :
        "Allow the microphone to make a call.");
    }
  }

  async function startCall(usernames, kind) {
    if (call) return GC.toast("You're already in a call.");
    if (!peer || !peer.open) return GC.toast("Calling isn't connected yet — try again in a moment.");
    if (!usernames.length) return GC.toast("Pick someone to call.");
    let stream = null;
    try {
      await GC.api("POST", "/api/calls/check", { usernames, kind });
      stream = await getMedia(kind);
      const room = await GC.api("POST", "/api/calls", { usernames, kind });
      begin(room, kind, stream);
      const joined = await GC.api("POST", `/api/calls/${room.id}/join`, { peer_id: peer.id });
      call.room = joined;
      renderTiles();
      ring(joined);
    } catch (e) {
      if (stream) stream.getTracks().forEach(t => t.stop());
      if (call) end(true);
      GC.toast(e.message, 5000);
    }
  }

  function ring(room) {
    room.members.filter(m => !m.me && !m.joined).forEach(m => {
      if (!m.ring_peer_id) { setStatus(m.username, "offline"); return; }
      setStatus(m.username, "ringing…");
      const conn = peer.connect(m.ring_peer_id, { reliable: true });
      conn.on("open", () => conn.send({ type: "ring", room: room.id }));
      conn.on("data", msg => {
        if (msg && msg.type === "decline") setStatus(m.username, msg.reason === "busy" ? "busy" : "declined");
      });
    });
  }

  // ------------------------------------------------------------------
  // Receiving calls
  // ------------------------------------------------------------------
  function handleData(conn) {
    conn.on("data", async msg => {
      if (!msg || msg.type !== "ring" || typeof msg.room !== "string") return;
      if (call || ringing) { conn.send({ type: "decline", reason: "busy" }); return; }
      let room;
      try { room = await GC.api("GET", `/api/calls/${encodeURIComponent(msg.room)}`); }
      catch (e) { return; } // not a call we're part of
      const caller = room.members.find(m => m.joined && m.peer_id === conn.peer);
      if (!caller) return;   // only a real member of this call can ring us
      showRinging(room, caller.username, conn);
    });
  }

  function showRinging(room, from, conn) {
    const box = document.getElementById("ring");
    box.innerHTML = "";
    const card = GC.el("div", "panel ring-card");
    card.appendChild(GC.logoImg(from, 72, "gx-logo big ring-logo"));
    card.appendChild(GC.el("h2", null, from));
    const others = room.members.filter(m => !m.me && m.username !== from).map(m => m.username);
    card.appendChild(GC.el("div", "soc-note", `${room.kind === "video" ? "🎥 Video" : "📞 Audio"} call` +
      (others.length ? ` with ${others.join(", ")}` : "")));
    const row = GC.el("div", "soc-row");
    row.appendChild(GC.button("Decline", "danger", () => { conn.send({ type: "decline" }); stopRinging(); }));
    row.appendChild(GC.button("Answer", "primary", () => { stopRinging(); answer(room); }));
    card.appendChild(row);
    box.appendChild(card);
    box.classList.add("open");
    ringing = { room, conn, tone: ringTone(), timer: setTimeout(() => { conn.send({ type: "decline" }); stopRinging(); }, RING_SECONDS * 1000) };
  }

  function stopRinging() {
    if (!ringing) return;
    clearTimeout(ringing.timer);
    ringing.tone();
    ringing = null;
    document.getElementById("ring").classList.remove("open");
  }

  function ringTone() {
    let ctx = null, timer = 0;
    try {
      ctx = new (window.AudioContext || window.webkitAudioContext)();
      const beep = () => {
        [0, 0.25].forEach(offset => {
          const o = ctx.createOscillator(), g = ctx.createGain();
          o.frequency.value = 660; o.connect(g); g.connect(ctx.destination);
          g.gain.setValueAtTime(0.0001, ctx.currentTime + offset);
          g.gain.exponentialRampToValueAtTime(0.15, ctx.currentTime + offset + 0.02);
          g.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + offset + 0.2);
          o.start(ctx.currentTime + offset); o.stop(ctx.currentTime + offset + 0.22);
        });
      };
      beep(); timer = setInterval(beep, 2000);
    } catch (e) { /* no audio: the popup still shows */ }
    if (navigator.vibrate) navigator.vibrate([400, 200, 400]);
    return () => { clearInterval(timer); if (ctx) ctx.close().catch(() => null); };
  }

  async function answer(room) {
    let stream = null;
    try {
      stream = await getMedia(room.kind);
      begin(room, room.kind, stream);
      const joined = await GC.api("POST", `/api/calls/${room.id}/join`, { peer_id: peer.id });
      call.room = joined;
      renderTiles();
      // the newcomer connects to everyone already in the call
      joined.members.filter(m => !m.me && m.joined && m.peer_id).forEach(m => dial(m.peer_id, m.username));
    } catch (e) {
      if (stream) stream.getTracks().forEach(t => t.stop());
      if (call) end(true);
      GC.toast(e.message, 5000);
    }
  }

  function dial(peerId, name) {
    if (!call || call.conns.has(peerId)) return;
    attach(peer.call(peerId, call.stream, { metadata: { room: call.room.id } }), name);
  }

  async function handleIncomingMedia(mc) {
    if (!call || !mc.metadata || mc.metadata.room !== call.room.id) { mc.close(); return; }
    let room;
    try { room = await GC.api("GET", `/api/calls/${encodeURIComponent(call.room.id)}`); }
    catch (e) { mc.close(); return; }
    const member = room.members.find(m => m.joined && m.peer_id === mc.peer);
    if (!member) { mc.close(); return; }   // only streams from members of this very call
    call.room = room;
    mc.answer(call.stream);
    attach(mc, member.username);
  }

  function attach(mc, name) {
    call.conns.set(mc.peer, { mc, name });
    setStatus(name, "connecting…");
    mc.on("stream", remote => showStream(name, remote));
    mc.on("close", () => { if (call) { call.conns.delete(mc.peer); setStatus(name, "left"); dropTile(name); } });
    mc.on("error", () => { if (call) setStatus(name, "connection lost"); });
  }

  // ------------------------------------------------------------------
  // The call screen
  // ------------------------------------------------------------------
  function begin(room, kind, stream) {
    call = { room, kind, stream, conns: new Map(), started: Date.now() };
    const ui = document.getElementById("call");
    ui.classList.add("open");
    ui.classList.toggle("audio", kind === "audio");
    document.getElementById("call-mic").textContent = "🎙️ Mute";
    document.getElementById("call-cam").style.display = kind === "video" ? "" : "none";
    const self = document.getElementById("call-self");
    self.srcObject = stream;
    self.style.display = kind === "video" ? "" : "none";
    renderTiles();
    call.poll = setInterval(pollRoom, 4000);
    call.clock = setInterval(() => {
      const s = Math.floor((Date.now() - call.started) / 1000);
      document.getElementById("call-time").textContent = `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
    }, 1000);
  }

  async function pollRoom() {
    if (!call) return;
    try {
      const room = await GC.api("GET", `/api/calls/${encodeURIComponent(call.room.id)}`);
      const allowed = new Set(room.members.map(m => m.username));
      // anyone blocked or swallowed since the call began is cut off at once
      call.conns.forEach((c, pid) => { if (!allowed.has(c.name)) { c.mc.close(); call.conns.delete(pid); dropTile(c.name); } });
      call.room = room;
      renderTiles();
      const others = room.members.filter(m => !m.me);
      const waiting = Date.now() - call.started < RING_SECONDS * 1000;
      const alone = !call.conns.size && !others.some(m => m.joined);
      if (alone && call.everConnected) {
        end(true);
        GC.toast("Everyone has left the call.");
      } else if (alone && !waiting) {
        end(true);
        GC.toast("Nobody answered.");
      }
    } catch (e) {
      if (/ended|not part/.test(e.message)) end(true);
    }
  }

  const statuses = {};
  function setStatus(name, text) { statuses[name] = text; renderTiles(); }

  function tileFor(name) {
    const grid = document.getElementById("call-grid");
    let tile = grid.querySelector(`[data-name="${CSS.escape(name)}"]`);
    if (!tile) {
      tile = GC.el("div", "call-tile");
      tile.dataset.name = name;
      tile.appendChild(GC.logoImg(name, 64, "gx-logo big"));
      const v = document.createElement("video");
      v.autoplay = true; v.playsInline = true;
      tile.appendChild(v);
      tile.appendChild(GC.el("div", "call-name", name));
      tile.appendChild(GC.el("div", "call-status"));
      grid.appendChild(tile);
    }
    return tile;
  }

  function renderTiles() {
    if (!call) return;
    const title = document.getElementById("call-title");
    title.textContent = (call.kind === "video" ? "🎥 " : "📞 ") + call.room.members.filter(m => !m.me).map(m => m.username).join(", ");
    call.room.members.filter(m => !m.me).forEach(m => {
      const tile = tileFor(m.username);
      const connected = [...call.conns.values()].some(c => c.name === m.username && c.live);
      tile.querySelector(".call-status").textContent = connected ? "" : (statuses[m.username] || (m.joined ? "connecting…" : "ringing…"));
    });
  }

  function showStream(name, remote) {
    const tile = tileFor(name);
    const v = tile.querySelector("video");
    v.srcObject = remote;
    tile.classList.toggle("has-video", call.kind === "video" && remote.getVideoTracks().length > 0);
    call.conns.forEach(c => { if (c.name === name) c.live = true; });
    call.everConnected = true;
    statuses[name] = "";
    renderTiles();
  }

  function dropTile(name) {
    const t = document.querySelector(`#call-grid [data-name="${CSS.escape(name)}"]`);
    if (t) {
      const v = t.querySelector("video");
      if (v) v.srcObject = null;
      t.classList.remove("has-video");
    }
    renderTiles();
  }

  function leaveBeacon() {
    try {
      navigator.sendBeacon(`/api/calls/${encodeURIComponent(call.room.id)}/leave`,
        new Blob(["{}"], { type: "application/json" }));
    } catch (e) { /* best effort */ }
  }

  function end(silent) {
    if (!call) return;
    const c = call;
    call = null;
    clearInterval(c.poll); clearInterval(c.clock);
    c.conns.forEach(x => { try { x.mc.close(); } catch (e) { /* already closed */ } });
    c.stream.getTracks().forEach(t => t.stop());
    if (c.room && c.room.id) GC.api("POST", `/api/calls/${encodeURIComponent(c.room.id)}/leave`, {}).catch(() => null);
    document.getElementById("call-self").srcObject = null;
    document.getElementById("call-grid").innerHTML = "";
    Object.keys(statuses).forEach(k => delete statuses[k]);
    document.getElementById("call").classList.remove("open");
    if (!silent) GC.toast("Call ended.");
  }

  // ------------------------------------------------------------------
  function buildUi() {
    const ui = document.createElement("div");
    ui.id = "call";
    ui.setAttribute("role", "dialog"); ui.setAttribute("aria-label", "Call");
    ui.innerHTML = `<div class="call-top"><span id="call-title"></span><span id="call-time">0:00</span></div>
      <div id="call-grid"></div>
      <video id="call-self" autoplay playsinline muted></video>
      <div class="call-bar">
        <button type="button" id="call-mic">🎙️ Mute</button>
        <button type="button" id="call-cam">📷 Camera off</button>
        <button type="button" id="call-hang" class="hang">Hang up</button>
      </div>
      <div class="call-note">🔒 Peer-to-peer and encrypted · never recorded</div>`;
    document.body.appendChild(ui);
    const ring = document.createElement("div");
    ring.id = "ring";
    ring.setAttribute("role", "alertdialog"); ring.setAttribute("aria-label", "Incoming call");
    document.body.appendChild(ring);
    document.getElementById("call-hang").addEventListener("click", () => end());
    document.getElementById("call-mic").addEventListener("click", e => {
      if (!call) return;
      const tracks = call.stream.getAudioTracks();
      const on = !tracks.every(t => t.enabled);
      tracks.forEach(t => (t.enabled = on));
      e.target.textContent = on ? "🎙️ Mute" : "🔇 Unmute";
    });
    document.getElementById("call-cam").addEventListener("click", e => {
      if (!call) return;
      const tracks = call.stream.getVideoTracks();
      const on = !tracks.every(t => t.enabled);
      tracks.forEach(t => (t.enabled = on));
      e.target.textContent = on ? "📷 Camera off" : "📷 Camera on";
    });
  }

  function injectStyles() {
    const st = document.createElement("style");
    st.textContent = `
      .call-pick { display: flex; flex-direction: column; gap: 4px; margin-bottom: 8px; max-height: 180px; overflow-y: auto; }
      .call-pick label { display: flex; align-items: center; gap: 6px; font-size: 12.5px; cursor: pointer; }
      .soc-btn:disabled { opacity: 0.45; cursor: default; }
      #call { position: fixed; inset: 0; z-index: 140; display: none; flex-direction: column; background: radial-gradient(ellipse at 50% 30%, #1a1440, #05060f 75%); color: #eef0ff; }
      #call.open { display: flex; }
      .call-top { display: flex; justify-content: space-between; padding: 16px 20px; font-weight: 600; }
      #call-time { color: #9aa0d0; font-variant-numeric: tabular-nums; }
      #call-grid { flex: 1; display: grid; gap: 10px; padding: 0 16px; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); align-content: center; }
      .call-tile { position: relative; min-height: 180px; border-radius: 16px; background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1);
        display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 8px; overflow: hidden; }
      .call-tile video { display: none; position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; }
      .call-tile.has-video video { display: block; }
      .call-tile.has-video .gx-logo { display: none; }
      #call.audio .call-tile video { display: block; width: 0; height: 0; }   /* audio still plays */
      .call-name { position: relative; font-weight: 600; text-shadow: 0 1px 4px #000; }
      .call-tile.has-video .call-name { position: absolute; left: 12px; bottom: 10px; }
      .call-status { position: relative; font-size: 12px; color: #b9bddf; }
      #call-self { position: absolute; right: 18px; bottom: 96px; width: 150px; border-radius: 12px; border: 2px solid rgba(255,255,255,0.3); transform: scaleX(-1); background: #000; }
      .call-bar { display: flex; gap: 10px; justify-content: center; padding: 16px; }
      .call-bar button { font: inherit; font-size: 14px; padding: 12px 18px; border-radius: 30px; border: none; background: rgba(255,255,255,0.12); color: #fff; cursor: pointer; }
      .call-bar button.hang { background: #e5484d; font-weight: 600; }
      .call-note { text-align: center; font-size: 11px; color: #8b8fb8; padding-bottom: 12px; }
      #ring { position: fixed; inset: 0; z-index: 150; display: none; align-items: center; justify-content: center; background: rgba(3,4,12,0.6); padding: 16px; }
      #ring.open { display: flex; }
      .ring-card { width: min(320px, 100%); padding: 24px; text-align: center; display: flex; flex-direction: column; align-items: center; gap: 6px; }
      .ring-card h2 { margin: 4px 0 0; font-size: 20px; }
      .ring-card .soc-row { width: 100%; margin-top: 12px; }
      .ring-logo { animation: ringpulse 1.2s ease-in-out infinite; }
      @keyframes ringpulse { 50% { transform: scale(1.12); box-shadow: 0 0 30px rgba(160,140,255,0.8); } }
      @media (max-width: 720px) { #call-grid { grid-template-columns: 1fr; } #call-self { width: 96px; bottom: 90px; } }`;
    document.head.appendChild(st);
  }

  if (window.GC) start();
  else document.addEventListener("gc:ready", start, { once: true });
})();
