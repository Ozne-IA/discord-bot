"use strict";
/* Panel de configuration — aucune dépendance externe.
   Tout le DOM est construit avec h() (textContent) : aucun texte venant de Discord n'est injecté en HTML. */

const app = document.getElementById("app");
const savebar = document.getElementById("savebar");
let state = { me: null, guild: null, cfg: null, original: "", section: "overview" };

// ------------------------------------------------------------------ outils
function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") el.className = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k === "value") el.value = v;
    else if (k === "checked") el.checked = v;
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const c of children.flat()) {
    if (c === null || c === undefined || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return el;
}

async function api(method, path, body) {
  const res = await fetch(path, {
    method,
    headers: { "Content-Type": "application/json", "X-Requested-With": "dashboard" },
    body: body === undefined ? undefined : JSON.stringify(body),
    credentials: "same-origin",
  });
  let data = {};
  try { data = await res.json(); } catch { /* vide */ }
  if (res.status === 401) { renderLogin(); throw new Error(data.error || "Non connecté"); }
  if (!res.ok) throw new Error(data.error || `Erreur ${res.status}`);
  return data;
}

function toast(message, kind = "ok") {
  const el = h("div", { class: `toast ${kind}` }, message);
  document.body.append(el);
  setTimeout(() => el.remove(), kind === "err" ? 7000 : 4000);
}

const get = (obj, path) => path.split(".").reduce((o, k) => (o == null ? undefined : o[k]), obj);
function set(obj, path, value) {
  const keys = path.split(".");
  let cur = obj;
  for (const k of keys.slice(0, -1)) cur = cur[k] ??= {};
  cur[keys.at(-1)] = value;
  markDirty();
}
const clone = (o) => JSON.parse(JSON.stringify(o));
const initials = (name) => name.split(/\s+/).map((w) => w[0]).join("").slice(0, 3).toUpperCase();

function guildIcon(g, cls = "guild-icon") {
  return g.icon ? h("img", { class: cls, src: g.icon, alt: "" }) : h("div", { class: cls }, initials(g.name));
}

function markDirty() {
  const dirty = state.cfg && JSON.stringify(state.cfg) !== state.original;
  savebar.classList.toggle("show", !!dirty);
  updatePreviews();
  updateDirtyDots();
}

/* Point orange à côté des onglets qui ont des modifications non enregistrées. */
function sectionDirty(section) {
  if (!section.fields || !state.cfg || !state.original) return false;
  const orig = JSON.parse(state.original);
  return section.fields.some((f) => JSON.stringify(get(state.cfg, f.path)) !== JSON.stringify(get(orig, f.path)));
}
function updateDirtyDots() {
  if (typeof SECTIONS === "undefined") return;
  for (const btn of document.querySelectorAll(".nav-item[data-id]")) {
    const s = SECTIONS.find((x) => x.id === btn.dataset.id);
    const dirty = s && sectionDirty(s);
    const dot = btn.querySelector(".dirty");
    if (dirty && !dot) btn.append(h("span", { class: "dirty", title: "Modifications non enregistrées" }));
    if (!dirty && dot) dot.remove();
  }
}

// ------------------------------------------------------------------ aperçu en direct (rendu façon Discord)
let previews = [];  // [{ el, kind }] — recréé à chaque affichage de section

const SAMPLE = () => ({
  mention: LANG === "en" ? "@NewMember" : "@Nouveau", name: LANG === "en" ? "NewMember" : "Nouveau",
  server: state.guild?.guild.name || "Serveur", count: String(state.guild?.guild.member_count ?? 42), level: "5",
});

/* Texte Discord → éléments DOM (gras, italique, souligné, code, mentions) sans innerHTML. */
function mdNodes(text) {
  const out = [];
  const sample = SAMPLE();
  const filled = String(text ?? "").replace(/\{(\w+)\}/g, (m, k) => (k in sample ? sample[k] : m));
  const re = /(\*\*[^*\n]+\*\*|__[^_\n]+__|\*[^*\n]+\*|`[^`\n]+`|@[\wÀ-ÿ-]+|<#\d+>|<@&\d+>)/g;
  let last = 0;
  for (const m of filled.matchAll(re)) {
    if (m.index > last) out.push(document.createTextNode(filled.slice(last, m.index)));
    const t = m[0];
    if (t.startsWith("**")) out.push(h("strong", {}, t.slice(2, -2)));
    else if (t.startsWith("__")) out.push(h("u", {}, t.slice(2, -2)));
    else if (t.startsWith("*")) out.push(h("em", {}, t.slice(1, -1)));
    else if (t.startsWith("`")) out.push(h("code", {}, t.slice(1, -1)));
    else if (t.startsWith("<@&")) {
      const role = state.guild?.roles.find((r) => r.id === t.slice(3, -1));
      out.push(h("span", { class: "dc-mention" }, "@" + (role ? role.name : "rôle")));
    } else if (t.startsWith("<#")) {
      const ch = state.guild?.channels.find((c) => c.id === t.slice(2, -1));
      out.push(h("span", { class: "dc-mention" }, "#" + (ch ? ch.name : "salon")));
    } else out.push(h("span", { class: "dc-mention" }, t));
    last = m.index + t.length;
  }
  if (last < filled.length) out.push(document.createTextNode(filled.slice(last)));
  return out;
}

function discordMessage({ content, embed, components = [], dm = false }) {
  const bot = state.botInfo || { name: "Bot", avatar: null };
  const color = state.guild && (state.guild.premium.active || !isPremiumPath("brand.color"))
    ? (get(state.cfg, "brand.color") || "#5865f2") : "#5865f2";
  const footer = state.guild && state.guild.premium.active ? get(state.cfg, "brand.footer") : "";
  return h("div", { class: "dc-msg" + (dm ? " dc-dm" : "") },
    bot.avatar ? h("img", { class: "dc-avatar", src: bot.avatar, alt: "" }) : h("div", { class: "dc-avatar" }),
    h("div", { class: "dc-body" },
      h("div", { class: "dc-head" }, h("b", {}, bot.name), h("span", { class: "dc-tag" }, "BOT"),
        h("span", { class: "dc-time" }, LANG === "en" ? "Today" : "Aujourd'hui")),
      content ? h("div", { class: "dc-content" }, mdNodes(content)) : null,
      embed ? h("div", { class: "dc-embed", style: `border-left-color:${color}` },
        h("div", { class: "dc-embed-main" },
          embed.title ? h("div", { class: "dc-embed-title" }, mdNodes(embed.title)) : null,
          embed.description ? h("div", { class: "dc-embed-desc" }, mdNodes(embed.description)) : null,
          embed.fields ? h("div", { class: "dc-fields" }, embed.fields.map((f) =>
            h("div", { class: "dc-field" }, h("div", { class: "dc-field-name" }, f[0]), h("div", {}, mdNodes(f[1]))))) : null,
          footer ? h("div", { class: "dc-footer" }, footer) : null),
        embed.thumbnail ? h("div", { class: "dc-thumb" }) : null) : null,
      components.length ? h("div", { class: "dc-components" }, components.map((c) => c.type === "select"
        ? h("div", { class: "dc-select" }, c.label, h("span", {}, "⌄"))
        : h("span", { class: `dc-button ${c.style || "grey"}` }, c.label))) : null));
}

/* Valeur réellement utilisée par le bot : en version gratuite, les réglages 💎 reprennent la valeur par défaut. */
function effective(path) {
  if (state.guild.premium.active || !isPremiumPath(path)) return get(state.cfg, path);
  return get(state.guild.defaults, path);
}

const PREVIEWS = {
  welcome: () => discordMessage({ content: SAMPLE().mention, embed: {
    title: "👋 Nouveau membre !", description: effective("welcome.message"), thumbnail: true,
    fields: [["Compte créé", "il y a 2 ans"], ["Membre n°", SAMPLE().count]] } }),
  dm: () => discordMessage({ dm: true, embed: { title: `Bienvenue sur ${SAMPLE().server} !`, description: effective("welcome.dm_message") } }),
  goodbye: () => discordMessage({ embed: { description: effective("welcome.goodbye_message") } }),
  levelup: () => discordMessage({ embed: { description: effective("leveling.level_up_message") } }),
  birthday: () => discordMessage({ content: SAMPLE().mention, embed: { title: "🎂 Joyeux anniversaire !",
    description: effective("birthdays.message"), thumbnail: true } }),
  rules: () => discordMessage({
    embed: { title: `📜 Règles de ${SAMPLE().server}`, description: ((get(state.cfg, "verification.rules") || [])
      .map((r, i) => `**${i + 1}.** ${r}`).join("\n") || "Respecte tout le monde.") +
      "\n\nClique sur le bouton ci-dessous pour accepter les règles et accéder au serveur." },
    components: [{ label: "✅ J'accepte les règles", style: "green" }] }),
  notifications: () => {
    const names = Object.entries(get(state.cfg, "roles.notifications") || {}).map(([, id]) =>
      `• <@&${id}>`).join("\n");
    return discordMessage({ embed: { title: "🔔 Rôles de notification",
      description: "Sélectionne dans le menu les sujets pour lesquels tu veux être mentionné(e).\n" +
        "Désélectionne un sujet pour ne plus recevoir ses notifications." + (names ? "\n\n" + names : "") },
      components: [{ type: "select", label: "🔔 Choisis tes notifications…" }] });
  },
  tickets: () => discordMessage({ embed: { title: "📩 Besoin d'aide ?",
    description: "Choisis le type de demande dans le menu ci-dessous. Un salon privé sera créé avec le staff.\n\n" +
      Object.values(get(state.cfg, "tickets.types") || {}).map((t) => `${t.emoji || "🎫"} **${t.label}** — ${t.description || ""}`).join("\n") },
    components: [{ type: "select", label: "📩 Choisis le type de ticket…" }] }),
};

function updatePreviews() {
  for (const p of previews) {
    if (!p.el.isConnected) continue;
    try { p.el.replaceChildren(PREVIEWS[p.kind]()); } catch { /* aperçu indisponible */ }
  }
  previews = previews.filter((p) => p.el.isConnected);
}

window.addEventListener("beforeunload", (e) => {
  if (savebar.classList.contains("show")) { e.preventDefault(); e.returnValue = ""; }
});

// ------------------------------------------------------------------ connexion
function renderLogin(message) {
  savebar.classList.remove("show");
  document.getElementById("user-chip").hidden = true;
  app.replaceChildren(h("div", { class: "panel center", style: "max-width:520px;margin:60px auto;padding:40px" },
    h("h1", {}, "Panel de configuration"),
    h("p", { class: "muted" }, "Connecte-toi avec ton compte Discord pour configurer les serveurs que tu gères."),
    message ? h("div", { class: "notice warn" }, message) : null,
    h("a", { class: "btn primary big", href: "/login" }, "Se connecter avec Discord"),
    h("p", { class: "muted", style: "font-size:13px;margin-top:20px" },
      "Le panel ne voit que ton pseudo et la liste de tes serveurs. Il ne peut ni lire tes messages ni agir en ton nom.")));
}

// ------------------------------------------------------------------ liste des serveurs
function renderGuildList() {
  savebar.classList.remove("show");
  state.guild = null; state.cfg = null;
  const guilds = state.me.guilds;
  const refresh = h("button", { class: "btn ghost small", onclick: async () => {
    refresh.disabled = true;
    try { state.me.guilds = (await api("POST", "/api/me/refresh")).guilds; renderGuildList(); }
    catch (e) { toast(e.message, "err"); refresh.disabled = false; }
  } }, "🔄 Actualiser");

  const cards = guilds.map((g) => h("div", { class: "guild-card" },
    guildIcon(g), h("div", { class: "name" }, g.name),
    g.premium ? h("span", { class: "badge-premium" }, "💎 Premium") : null,
    g.limited ? h("span", { class: "muted", style: "font-size:12px" }, "👮 Accès limité") : null,
    g.bot_in
      ? h("a", { class: "btn primary small", href: `#/guild/${g.id}` }, "⚙️ Configurer")
      : h("a", { class: "btn ghost small", href: g.invite, target: "_blank", rel: "noopener" }, "➕ Ajouter le bot")));

  app.replaceChildren(
    h("div", { class: "page-title" }, h("div", {}, h("h1", {}, "Mes serveurs"),
      h("p", { class: "muted", style: "margin:0" }, "Seuls les serveurs où tu as la permission « Gérer le serveur » apparaissent.")), refresh),
    guilds.length ? h("div", { class: "guild-grid" }, cards)
      : h("div", { class: "panel center" }, h("p", {}, "Aucun serveur à gérer."),
        h("p", { class: "muted" }, "Crée un serveur ou demande la permission « Gérer le serveur », puis clique sur Actualiser.")));
}

// ------------------------------------------------------------------ champs du formulaire
function channelOptions(kind) {
  const g = state.guild;
  if (kind === "category") return g.categories.map((c) => ({ id: c.id, label: c.name }));
  if (kind === "voice") return (g.voice_channels || []).map((c) => ({ id: c.id, label: `🔊 ${c.name}` + (c.category ? `  (${c.category})` : "") }));
  return g.channels.map((c) => ({ id: c.id, label: `#${c.name}` + (c.category ? `  (${c.category})` : "") }));
}
function roleOptions() {
  return state.guild.roles.map((r) => ({ id: r.id, label: `@${r.name}` + (r.manageable ? "" : "  ⚠️ au-dessus du bot") }));
}

function selectId(options, value, onchange, emptyLabel = "— Aucun —") {
  const val = String(value ?? "0");
  const sel = h("select", { onchange: (e) => onchange(e.target.value === "0" ? 0 : e.target.value) },
    h("option", { value: "0" }, emptyLabel),
    options.map((o) => h("option", { value: o.id }, o.label)));
  sel.value = options.some((o) => o.id === val) ? val : "0";
  if (val !== "0" && !options.some((o) => o.id === val)) {
    sel.prepend(h("option", { value: val }, "⚠️ Introuvable (supprimé ?)"));
    sel.value = val;
  }
  return sel;
}

function multiIds(options, values, onchange) {
  const list = (values || []).map(String);
  const box = h("div");
  const draw = () => {
    const chips = h("div", { class: "chips" }, list.map((id) => {
      const opt = options.find((o) => o.id === id);
      return h("span", { class: "chip" }, opt ? opt.label : id,
        h("button", { title: "Retirer", onclick: () => { list.splice(list.indexOf(id), 1); onchange([...list]); draw(); } }, "×"));
    }));
    const add = h("select", { onchange: (e) => {
      if (e.target.value !== "0" && !list.includes(e.target.value)) { list.push(e.target.value); onchange([...list]); draw(); }
    } }, h("option", { value: "0" }, "➕ Ajouter…"), options.filter((o) => !list.includes(o.id)).map((o) => h("option", { value: o.id }, o.label)));
    box.replaceChildren(list.length ? chips : "", add);
  };
  draw();
  return box;
}

function lineList(values, onchange, placeholder) {
  return h("textarea", { rows: 6, placeholder, value: (values || []).join("\n"),
    oninput: (e) => onchange(e.target.value.split("\n").map((s) => s.trim()).filter(Boolean)) });
}

/* Éditeur de dictionnaire { clé: valeur }. Chaque ligne reçoit :
   update(fn, redraw)  → fn([clé, valeur]) renvoie la nouvelle paire (lue au moment du changement)
   del()               → supprime la ligne */
function mapEditor(path, rowFactory, newItem, addLabel) {
  const wrap = h("div", { class: "rows" });
  // L'ordre est gardé dans une liste locale : renommer une clé ne fait pas sauter les lignes.
  let entries = Object.entries(get(state.cfg, path) || {});
  const save = () => {
    const obj = {};
    for (const [k, v] of entries) if (String(k).trim() && !(k in obj)) obj[k] = v;
    set(state.cfg, path, obj);
  };
  const draw = () => {
    wrap.replaceChildren(
      ...entries.map(([key, value], i) => rowFactory(key, value,
        (fn, redraw = false) => { entries[i] = fn(entries[i]); save(); if (redraw) draw(); },
        () => { entries.splice(i, 1); save(); draw(); })),
      h("div", {}, h("button", { class: "btn ghost small", onclick: () => { entries.push(newItem(entries)); save(); draw(); } }, addLabel)));
  };
  draw();
  return wrap;
}
const removeBtn = (onclick) => h("button", { class: "btn ghost small", title: "Supprimer", onclick }, "🗑️");

function control(f) {
  const value = get(state.cfg, f.path);
  const update = (v) => set(state.cfg, f.path, v);
  switch (f.type) {
    case "text": return h("input", { type: "text", value: value ?? "", placeholder: f.placeholder || "", maxlength: 2000, oninput: (e) => update(e.target.value) });
    case "textarea": return h("textarea", { rows: 3, value: value ?? "", placeholder: f.placeholder || "", oninput: (e) => update(e.target.value) });
    case "number": return h("input", { type: "number", value: value ?? 0, min: f.min ?? 0, max: f.max, step: f.step ?? 1,
      oninput: (e) => update(f.step && f.step < 1 ? parseFloat(e.target.value || "0") : parseInt(e.target.value || "0", 10)) });
    case "toggle": return h("label", { class: "switch" }, h("input", { type: "checkbox", checked: !!value, onchange: (e) => update(e.target.checked) }), h("span"));
    case "color": return h("input", { type: "color", value: value || "#5865f2", oninput: (e) => update(e.target.value) });
    case "select": { const s = h("select", { onchange: (e) => update(e.target.value) }, f.options.map(([v, l]) => h("option", { value: v }, l))); s.value = value; return s; }
    case "channel": return selectId(channelOptions("text"), value, update, f.empty);
    case "category": return selectId(channelOptions("category"), value, update, f.empty);
    case "role": return selectId(roleOptions(), value, update, f.empty);
    case "channels": return multiIds(channelOptions("text"), value, update);
    case "roles": return multiIds(roleOptions(), value, update);
    case "lines": return lineList(value, update, f.placeholder);
    case "ids": return lineList((value || []).map(String), update, "Un ID d'utilisateur par ligne");
    case "notifications": return mapEditor(f.path, (k, v, update, del) => h("div", { class: "row" },
      h("input", { type: "text", value: k, maxlength: 50, placeholder: "Nom affiché", oninput: (e) => update(([, ov]) => [e.target.value, ov]) }),
      selectId(roleOptions(), v, (nv) => update(([ok]) => [ok, nv]), "— Choisir un rôle —"), removeBtn(del)),
      (list) => [`Notification ${list.length + 1}`, 0], "➕ Ajouter une notification");
    case "level_roles": return mapEditor(f.path, (k, v, update, del) => h("div", { class: "row" },
      h("input", { type: "number", class: "narrow", min: 1, value: k, title: "Niveau", oninput: (e) => update(([, ov]) => [e.target.value, ov]) }),
      selectId(roleOptions(), v, (nv) => update(([ok]) => [ok, nv]), "— Choisir un rôle —"), removeBtn(del)),
      (list) => [String(Math.max(0, ...list.map(([k]) => +k || 0)) + 5), 0], "➕ Ajouter un palier");
    case "escalation": return mapEditor(f.path, (k, v, update, del) => {
      const action = h("select", { onchange: (e) => update(([ok, ov]) => [ok, { ...ov, action: e.target.value }], true) },
        h("option", { value: "timeout" }, "🔇 Mute"), h("option", { value: "kick" }, "👢 Expulsion"), h("option", { value: "ban" }, "🔨 Bannissement"));
      action.value = v.action;
      return h("div", { class: "row" },
        h("input", { type: "number", class: "narrow", min: 1, value: k, title: "Nombre de warns", oninput: (e) => update(([, ov]) => [e.target.value, ov]) }),
        h("span", { class: "narrow muted" }, "warns →"), action,
        h("input", { type: "number", class: "narrow", min: 0, value: v.minutes || 0, title: "Minutes (mute)", disabled: v.action !== "timeout",
          oninput: (e) => update(([ok, ov]) => [ok, { ...ov, minutes: parseInt(e.target.value || "0", 10) }]) }),
        removeBtn(del));
    }, (list) => [String(Math.max(0, ...list.map(([k]) => +k || 0)) + 2), { action: "timeout", minutes: 60 }], "➕ Ajouter une étape");
    case "ticket_types": return mapEditor(f.path, (k, v, update, del) => h("div", { class: "row" },
      h("input", { type: "text", class: "narrow", value: v.emoji || "", maxlength: 20, title: "Emoji", oninput: (e) => update(([ok, ov]) => [ok, { ...ov, emoji: e.target.value }]) }),
      h("input", { type: "text", value: v.label || "", maxlength: 80, placeholder: "Nom (ex : Support)", oninput: (e) => update(([ok, ov]) => [ok, { ...ov, label: e.target.value }]) }),
      h("input", { type: "text", value: v.description || "", maxlength: 100, placeholder: "Description courte", oninput: (e) => update(([ok, ov]) => [ok, { ...ov, description: e.target.value }]) }),
      h("input", { type: "text", value: (v.questions || []).join(" | "), maxlength: 240, placeholder: "💎 Questions du formulaire (séparées par |)",
        title: "💎 Premium : jusqu'à 5 questions posées à l'ouverture du ticket",
        oninput: (e) => update(([ok, ov]) => [ok, { ...ov, questions: e.target.value.split("|").map((q) => q.trim()).filter(Boolean).slice(0, 5) }]) }),
      removeBtn(del)),
      (list) => [`type${Date.now().toString(36)}`, { label: "Nouveau type", emoji: "🎫", description: "" }], "➕ Ajouter un type");
    case "ticket_replies": return objectList(f.path, [
      { key: "name", type: "text", placeholder: "Nom (ex : Merci d'attendre)" },
      { key: "content", type: "textarea", placeholder: "Bonjour {user}, merci pour ta patience…", wide: true },
    ], { name: "", content: "" }, "➕ Ajouter une réponse", 50);
    case "twitch_commands": return objectList(f.path, [
      { key: "trigger", type: "text", placeholder: "!discord" },
      { key: "response", type: "text", placeholder: "Rejoins le Discord : https://discord.gg/… ({user})", wide: true },
    ], { trigger: "", response: "" }, "➕ Ajouter une commande", 50);
    case "alerts_twitch": return objectList(f.path, [
      { key: "login", type: "text", placeholder: "Pseudo Twitch (ex : zerator)" },
      { key: "channel", type: "channel" },
      { key: "message", type: "text", placeholder: "Message (vide = message par défaut)" },
    ], { login: "", channel: 0, message: "" }, "➕ Ajouter une chaîne Twitch");
    case "alerts_youtube": return objectList(f.path, [
      { key: "source", type: "text", placeholder: "@pseudo, lien ou ID de chaîne (UC…)" },
      { key: "channel", type: "channel" },
      { key: "message", type: "text", placeholder: "Message (vide = message par défaut)" },
    ], { source: "", channel: 0, message: "" }, "➕ Ajouter une chaîne YouTube");
    case "alerts_kick": return objectList(f.path, [
      { key: "login", type: "text", placeholder: "Pseudo Kick (ex : kick.com/pseudo)" },
      { key: "channel", type: "channel" },
      { key: "message", type: "text", placeholder: "Message (vide = message par défaut)" },
    ], { login: "", channel: 0, message: "" }, "➕ Ajouter une chaîne Kick");
    case "alerts_tiktok": return objectList(f.path, [
      { key: "login", type: "text", placeholder: "@pseudo TikTok" },
      { key: "channel", type: "channel" },
      { key: "message", type: "text", placeholder: "Message des lives (vide = par défaut)" },
    ], { login: "", channel: 0, message: "" }, "➕ Ajouter un compte TikTok");
    case "alerts_rss": return objectList(f.path, [
      { key: "url", type: "text", placeholder: "Adresse du flux (https://…/rss.xml)" },
      { key: "channel", type: "channel" },
      { key: "message", type: "text", placeholder: "Message (vide = message par défaut)" },
    ], { url: "", channel: 0, message: "" }, "➕ Ajouter un flux RSS");
    case "panel_access": return objectList(f.path, [
      { key: "role", type: "role", empty: "— Choisir un rôle —", rowClass: "row-access" },
      ...ACCESS_GROUPS.map(([key, label]) => ({ key, type: "checkbox", placeholder: label })),
    ], () => Object.fromEntries([["role", 0], ...ACCESS_GROUPS.map(([k]) => [k, false])]), "➕ Ajouter un rôle", 10);
    case "shop": return objectList(f.path, [
      { key: "name", type: "text", placeholder: "Nom de l'objet (ex : VIP)" },
      { key: "price", type: "number", placeholder: "Prix" },
      { key: "role", type: "role", empty: "— Pas de rôle —" },
      { key: "description", type: "text", placeholder: "Description" },
    ], { name: "", price: 500, role: 0, description: "" }, "➕ Ajouter un objet");
    case "voice": return selectId(channelOptions("voice"), value, update, f.empty);
    case "counters": return objectList(f.path, [
      { key: "type", type: "select", options: [["members", "👥 Membres"], ["humans", "🙂 Humains"], ["bots", "🤖 Bots"],
        ["online", "🟢 En ligne"], ["boosts", "💎 Boosts"], ["channels", "# Salons"], ["roles", "🎭 Rôles"]] },
      { key: "channel", type: "voice" },
      { key: "template", type: "text", placeholder: "Texte, {} = le nombre (ex : 👥 Membres : {})", max: 100 },
    ], { type: "members", channel: 0, template: "👥 Membres : {}" }, "➕ Ajouter un compteur", 5);
    case "custom_commands": return objectList(f.path, [
      { key: "trigger", type: "text", placeholder: "Déclencheur (ex : !regles)", max: 50 },
      { key: "mode", type: "select", options: [["exact", "Message exact"], ["contains", "Contient le mot"]] },
      { key: "response", type: "textarea", placeholder: "Réponse du bot ({mention} {name} {server} {count})", wide: true },
      { key: "embed", type: "checkbox", placeholder: "Encadré" },
    ], { trigger: "", mode: "exact", response: "", embed: false }, "➕ Ajouter une commande", 50);
    case "scheduled": return objectList(f.path, [
      { key: "channel", type: "channel", empty: "— Salon —" },
      { key: "at", type: "datetime" },
      { key: "repeat", type: "select", options: [["none", "Une fois"], ["daily", "Chaque jour"], ["weekly", "Chaque semaine"]] },
      { key: "mention", type: "select", options: [["none", "Sans mention"], ["here", "@here"], ["everyone", "@everyone"]] },
      { key: "title", type: "text", placeholder: "Titre", max: 256 },
      { key: "message", type: "textarea", placeholder: "Message", max: 4000, wide: true },
    ], () => ({ id: Math.random().toString(36).slice(2, 10), channel: 0, at: "", repeat: "none", mention: "none", title: "", message: "" }),
    "➕ Programmer un message");
    case "role_menus": return roleMenusEditor(f.path);
    default: return h("span", {}, "?");
  }
}

/* Éditeur des menus de rôles : un bloc par menu, avec ses rôles, un aperçu et un bouton Publier. */
function roleMenusEditor(path) {
  const wrap = h("div", { class: "rows" });
  const limit = state.guild.limits?.role_menus ?? 2;
  const draw = () => {
    const menus = get(state.cfg, path) || [];
    const save = () => set(state.cfg, path, menus.map((m) => ({ ...m, roles: [...m.roles] })));
    wrap.replaceChildren(
      ...menus.map((menu, i) => {
        const preview = h("div", { class: "dc-preview" });
        const renderPreview = () => preview.replaceChildren(discordMessage({
          embed: { title: menu.title || "🎭 Rôles", description: [menu.description, menu.roles.map((r) =>
            `${r.emoji || "•"} <@&${r.role}>${r.label ? " — " + r.label : ""}`).join("\n")].filter(Boolean).join("\n\n") },
          components: menu.style === "select" ? [{ type: "select", label: "Choisis tes rôles…" }]
            : menu.roles.map((r) => ({ label: `${r.emoji ? r.emoji + " " : ""}${r.label || (state.guild.roles.find((x) => x.id === String(r.role))?.name ?? "rôle")}` })),
        }));
        const change = (patch, redraw = false) => { Object.assign(menu, patch); save(); renderPreview(); if (redraw) draw(); };
        const styleSel = h("select", { onchange: (e) => change({ style: e.target.value }) },
          h("option", { value: "buttons" }, "Boutons"), h("option", { value: "select" }, "Menu déroulant"));
        styleSel.value = menu.style || "buttons";
        const rolesBox = h("div", { class: "rows menu-roles" },
          menu.roles.map((r, j) => h("div", { class: "row" },
            h("input", { type: "text", class: "narrow", value: r.emoji || "", placeholder: "Emoji", maxlength: 20,
              oninput: (e) => { r.emoji = e.target.value; change({}); } }),
            selectId(roleOptions(), r.role, (v) => { r.role = v; change({}); }, "— Choisir un rôle —"),
            h("input", { type: "text", value: r.label || "", placeholder: "Texte (facultatif)", maxlength: 80,
              oninput: (e) => { r.label = e.target.value; change({}); } }),
            removeBtn(() => { menu.roles.splice(j, 1); change({}, true); }))),
          h("div", {}, h("button", { class: "btn ghost small", onclick: () => {
            if (menu.roles.length >= 25) return toast("25 maximum.", "err");
            menu.roles.push({ role: 0, label: "", emoji: "" }); change({}, true);
          } }, "➕ Ajouter un rôle")));
        const publish = h("button", { class: "btn primary small", onclick: async () => {
          if (savebar.classList.contains("show")) return toast("Enregistre tes modifications d'abord.", "err");
          publish.disabled = true;
          try { const r = await api("POST", `/api/guilds/${state.guild.guild.id}/rolemenus/${menu.id}/publish`); toast(`✅ Menu publié dans #${r.channel}`); }
          catch (e) { toast(e.message, "err"); }
          publish.disabled = false;
        } }, "📤 Publier / mettre à jour");
        renderPreview();
        return h("div", { class: "menu-block" + (i >= limit ? " over-limit" : "") },
          i >= limit ? h("div", { class: "notice warn" }, `💎 Ce menu dépasse la limite de ta version (${limit}). Il ne fonctionnera qu'avec Premium.`) : null,
          h("div", { class: "row" },
            h("input", { type: "text", value: menu.title || "", placeholder: "Titre du menu (ex : 🎮 Tes jeux)", maxlength: 100,
              oninput: (e) => change({ title: e.target.value }) }),
            selectId(channelOptions("text"), menu.channel, (v) => change({ channel: v }), "— Salon —"),
            styleSel, removeBtn(() => { menus.splice(i, 1); save(); draw(); })),
          h("textarea", { rows: 2, value: menu.description || "", placeholder: "Description (facultatif)", maxlength: 1000,
            oninput: (e) => change({ description: e.target.value }) }),
          h("label", { class: "inline-check" }, h("input", { type: "checkbox", checked: menu.multiple !== false,
            onchange: (e) => change({ multiple: e.target.checked }) }), "Plusieurs rôles possibles"),
          rolesBox,
          h("div", { class: "help preview-label" }, "👁️ Aperçu en direct"), preview,
          h("div", { class: "actions-row" }, publish));
      }),
      h("div", {}, h("button", { class: "btn ghost small", onclick: () => {
        if (menus.length >= 15) return toast("15 maximum.", "err");
        menus.push({ id: Math.random().toString(36).slice(2, 10), channel: 0, title: "", description: "", style: "buttons",
          multiple: true, roles: [] });
        save(); draw();
      } }, `➕ Créer un menu (${menus.length}/${limit})`)));
  };
  draw();
  return wrap;
}

// ------------------------------------------------------------------ envoyer un message
function renderMessages() {
  const g = state.guild;
  const draft = state.draft ||= { channel: 0, title: "", message: "", mention: "none" };
  const preview = h("div", { class: "dc-preview" });
  const refresh = () => preview.replaceChildren(discordMessage({
    content: draft.mention !== "none" ? `@${draft.mention}` : "",
    embed: draft.title || draft.message ? { title: draft.title, description: draft.message } : null }));
  const mention = h("select", { onchange: (e) => { draft.mention = e.target.value; refresh(); } },
    h("option", { value: "none" }, "Sans mention"), h("option", { value: "here" }, "@here"), h("option", { value: "everyone" }, "@everyone"));
  mention.value = draft.mention;
  const send = h("button", { class: "btn primary", onclick: async () => {
    send.disabled = true;
    try { const r = await api("POST", `/api/guilds/${g.guild.id}/send`, draft); toast(`✅ Message envoyé dans #${r.channel}`); }
    catch (e) { toast(e.message, "err"); }
    send.disabled = false;
  } }, "📨 Envoyer maintenant");
  refresh();
  const scheduled = SECTIONS.find((s) => s.id === "messages").fields.map(field);
  return [
    h("div", { class: "panel" }, h("h2", {}, "📨 ", "Envoyer un message"),
      h("p", { class: "desc" }, "Rédige un message encadré aux couleurs du serveur et envoie-le tout de suite dans un salon."),
      h("div", { class: "rows" },
        h("div", { class: "row" }, selectId(channelOptions("text"), draft.channel, (v) => { draft.channel = v; }, "— Salon —"), mention),
        h("input", { type: "text", value: draft.title, placeholder: "Titre", maxlength: 256, oninput: (e) => { draft.title = e.target.value; refresh(); } }),
        h("textarea", { rows: 5, value: draft.message, placeholder: "Message (gras **texte**, italique *texte*, mentions <@&ID>…)", maxlength: 4000,
          oninput: (e) => { draft.message = e.target.value; refresh(); } })),
      h("div", { class: "help preview-label" }, "👁️ Aperçu en direct"), preview,
      h("div", { class: "actions-row" }, send)),
    h("div", { class: "panel" }, h("h2", {}, "⏰ ", "Messages programmés"),
      h("p", { class: "desc" }, "Envoyés automatiquement à la date choisie (fuseau horaire de l'onglet Anniversaires), une fois, chaque jour ou chaque semaine. Pense à enregistrer."),
      !g.premium.active ? h("div", { class: "notice warn" }, "💎 Les messages programmés sont réservés aux serveurs Premium : tu peux les préparer dès maintenant.") : null,
      scheduled),
  ];
}

// ------------------------------------------------------------------ sauvegarde
function renderBackup() {
  const g = state.guild;
  const input = h("input", { type: "file", accept: ".json,application/json", style: "display:none", onchange: async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    let data;
    try { data = JSON.parse(await file.text()); } catch { return toast("Ce fichier n'est pas une sauvegarde valide.", "err"); }
    if (!confirm("Remplacer toute la configuration de ce serveur par celle du fichier ?")) return;
    try {
      const res = await api("POST", `/api/guilds/${g.guild.id}/import`, data);
      loadGuildData(res); renderGuild();
      toast(`✅ Configuration importée (${res.changed} réglage(s) modifié(s)). Vérifie le diagnostic : les salons et rôles d'un autre serveur n'existent pas ici.`);
    } catch (err) { toast(err.message, "err"); }
  } });
  return [h("div", { class: "panel" }, h("h2", {}, "💾 ", "Sauvegarde de la configuration"),
    h("p", { class: "desc" }, "Télécharge toute la configuration de ce serveur dans un fichier, pour la restaurer plus tard ou la copier sur un autre serveur."),
    h("div", { class: "actions-row" },
      h("a", { class: "btn primary", href: `/api/guilds/${g.guild.id}/export`, download: "" }, "⬇️ Télécharger la sauvegarde"),
      h("button", { class: "btn", onclick: () => input.click() }, "⬆️ Importer une sauvegarde"), input),
    h("p", { class: "muted", style: "font-size:13px;margin-top:14px" },
      "L'import remplace la configuration actuelle et apparaît dans l'historique. Les XP, sanctions, tickets et l'économie ne sont pas concernés."))];
}

/* Liste d'objets (alertes) : chaque ligne = plusieurs champs. */
function objectList(path, columns, blank, addLabel, max = 25) {
  const wrap = h("div", { class: "rows" });
  const draw = () => {
    const list = get(state.cfg, path) || [];
    wrap.replaceChildren(
      ...list.map((item, i) => h("div", { class: "row" + (columns.some((c) => c.wide) ? " row-wide" : "")
        + (columns.find((c) => c.rowClass)?.rowClass ? " " + columns.find((c) => c.rowClass).rowClass : "") },
        columns.map((col) => {
          const put = (v) => { list[i] = { ...list[i], [col.key]: v }; set(state.cfg, path, [...list]); };
          if (col.type === "channel") return selectId(channelOptions("text"), item[col.key], put, col.empty || "— Salon d'annonce —");
          if (col.type === "voice") return selectId(channelOptions("voice"), item[col.key], put, "— Salon vocal —");
          if (col.type === "role") return selectId(roleOptions(), item[col.key], put, col.empty || "— Aucun rôle —");
          if (col.type === "select") {
            const s = h("select", { onchange: (e) => put(e.target.value) }, col.options.map(([v, l]) => h("option", { value: v }, l)));
            s.value = item[col.key] ?? col.options[0][0];
            return s;
          }
          if (col.type === "checkbox") return h("label", { class: "inline-check", title: col.placeholder },
            h("input", { type: "checkbox", checked: !!item[col.key], onchange: (e) => put(e.target.checked) }), col.placeholder);
          if (col.type === "datetime") return h("input", { type: "datetime-local", value: item[col.key] || "", oninput: (e) => put(e.target.value) });
          if (col.type === "number") return h("input", { type: "number", class: "narrow", min: 0, value: item[col.key] ?? 0,
            title: col.placeholder, oninput: (e) => put(parseInt(e.target.value || "0", 10)) });
          if (col.type === "textarea") return h("textarea", { rows: 2, value: item[col.key] || "", placeholder: col.placeholder,
            maxlength: col.max || 2000, oninput: (e) => put(e.target.value) });
          return h("input", { type: "text", value: item[col.key] || "", placeholder: col.placeholder, maxlength: col.max || 300,
            class: col.narrow ? "narrow" : null, oninput: (e) => put(e.target.value) });
        }),
        removeBtn(() => { list.splice(i, 1); set(state.cfg, path, [...list]); draw(); }))),
      h("div", {}, h("button", { class: "btn ghost small", onclick: () => {
        if (list.length >= max) return toast(`${max} maximum.`, "err");
        set(state.cfg, path, [...list, typeof blank === "function" ? blank() : { ...blank }]); draw();
      } }, addLabel)));
  };
  draw();
  return wrap;
}

const RESETTABLE = ["text", "textarea", "number", "toggle", "select", "color", "lines"];
const TEST_KINDS = ["welcome", "dm", "goodbye", "levelup", "birthday"];

/* 🧪 Envoie le message (tel qu'il est enregistré) dans Discord pour le voir en vrai. */
function testButton(kind) {
  const btn = h("button", { class: "btn ghost small", onclick: async () => {
    if (savebar.classList.contains("show")) return toast("Enregistre d'abord tes modifications : le test utilise la configuration enregistrée.", "err");
    btn.disabled = true;
    try {
      const res = await api("POST", `/api/guilds/${state.guild.guild.id}/test`, { kind });
      toast(res.where === "MP" ? "✅ Test envoyé en message privé." : `✅ Test envoyé dans ${res.where}.`);
    } catch (e) { toast(e.message, "err"); }
    setTimeout(() => { btn.disabled = false; }, 5000);
  } }, kind === "dm" ? "🧪 M'envoyer le test en MP" : "🧪 Tester dans Discord");
  return btn;
}

const isPremiumPath = (path) => state.guild.premium.paths.some((p) => path === p || path.startsWith(p + "."));

function field(f) {
  const locked = isPremiumPath(f.path);
  let preview = null;
  if (f.preview) {
    const el = h("div", { class: "dc-preview" });
    previews.push({ el, kind: f.preview });
    try { el.append(PREVIEWS[f.preview]()); } catch { /* aperçu indisponible */ }
    preview = h("div", {}, h("div", { class: "help preview-label" },
      locked && !state.guild.premium.active ? "👁️ Aperçu (version gratuite : texte par défaut)" : "👁️ Aperçu en direct"), el,
      TEST_KINDS.includes(f.preview) ? h("div", { class: "field-tools" }, testButton(f.preview)) : null);
  }
  // ↺ Remettre la valeur par défaut (réglages simples uniquement)
  const def = get(state.guild.defaults, f.path);
  const resettable = RESETTABLE.includes(f.type) && def !== undefined
    && JSON.stringify(get(state.cfg, f.path)) !== JSON.stringify(def);
  const reset = resettable ? h("button", { class: "reset-btn", title: "Remettre la valeur par défaut", onclick: () => {
    set(state.cfg, f.path, clone(def)); state.focusPath = f.path; renderContent();
  } }, "↺ par défaut") : null;
  return h("div", { class: "field" + (locked && !state.guild.premium.active ? " locked" : ""), "data-path": f.path },
    h("div", {},
      h("label", { class: "title" }, f.label, locked ? h("span", { class: "badge-premium small" }, "💎 Premium") : null, reset),
      f.help ? h("div", { class: "help" }, f.help) : null,
      locked && !state.guild.premium.active
        ? h("div", { class: "help premium-note" }, "Tu peux le régler dès maintenant : il s'appliquera dès que le serveur sera Premium.")
        : null),
    h("div", { class: "control" }, control(f), preview));
}

// ------------------------------------------------------------------ accès limité (rôles autorisés par les admins)
const ACCESS_GROUPS = [["community", "Communauté"], ["moderation", "Modération"], ["tickets", "Tickets & modmail"],
  ["alerts", "Alertes & événements"], ["messages", "Messages"], ["stats", "Statistiques"]];
const SECTION_GROUP = { welcome: "community", roles: "community", levels: "community", economy: "community",
  engagement: "community", games: "community", birthdays: "community", tempvoice: "community", community: "community",
  counters: "community", commands: "community", rolemenus: "community", moderation: "moderation", automod: "moderation",
  security: "moderation", tickets: "tickets", modmail: "tickets", alerts: "alerts", events: "alerts",
  messages: "messages", stats: "stats", audit: "stats", agenda: "community", ai: "community", msglog: "moderation",
  twitch: "moderation" };
const fullAccess = () => !state.guild.access || state.guild.access.full;
const canSee = (id) => id === "overview" || id === "premium" || id === "news" || fullAccess()
  || state.guild.access.groups.includes(SECTION_GROUP[id]) || (id === "stats" && state.guild.access.groups.includes("moderation"));

// ------------------------------------------------------------------ sections
const VARS ="Variables : {mention} {name} {server} {count}";
const TWITCH_ACTIONS = [["off", "Désactivé"], ["delete", "Supprimer le message"], ["timeout", "Timeout"], ["ban", "Bannir"]];
const SECTIONS = [
  { id: "overview", icon: "🏠", title: "Vue d'ensemble" },
  { id: "news", icon: "🆕", title: "Nouveautés" },
  { id: "stats", icon: "📊", title: "Statistiques" },
  { id: "general", icon: "⚙️", title: "Général", desc: "Apparence des messages et salons de logs.", fields: [
    { path: "general.language", type: "select", label: "Langue du bot sur ce serveur", help: "Textes par défaut des panneaux et messages automatiques.",
      options: [["fr", "🇫🇷 Français"], ["en", "🇬🇧 English"]] },
    { path: "brand.color", type: "color", label: "Couleur des messages" },
    { path: "brand.footer", type: "text", label: "Pied de page", placeholder: "Ex : Mon Serveur • Bot officiel" },
    { path: "roles.staff", type: "role", label: "Rôle Staff", help: "Voit et gère les tickets, ignoré par l'automod." },
    { path: "channels.logs", type: "channel", label: "Salon de logs", help: "Privé, réservé au staff. Reçoit tout le journal." },
    { path: "channels.mod_logs", type: "channel", label: "Logs de modération", help: "Sanctions, automod, sécurité. Vide = salon de logs.", empty: "— Salon de logs —" },
  ] },
  { id: "welcome", icon: "👋", title: "Accueil", desc: "Ce qui se passe quand quelqu'un rejoint ou quitte le serveur.", fields: [
    { path: "welcome.enabled", type: "toggle", label: "Activer les messages de bienvenue" },
    { path: "channels.welcome", type: "channel", label: "Salon de bienvenue" },
    { path: "welcome.message", type: "textarea", label: "Message de bienvenue", help: VARS, preview: "welcome" },
    { path: "welcome.image", type: "toggle", label: "Carte de bienvenue en image", help: "Avatar, pseudo et numéro de membre aux couleurs du serveur." },
    { path: "welcome.send_dm", type: "toggle", label: "Envoyer aussi un message privé" },
    { path: "welcome.dm_message", type: "textarea", label: "Message privé", help: VARS, preview: "dm" },
    { path: "channels.goodbye", type: "channel", label: "Salon d'au revoir", help: "Facultatif." },
    { path: "welcome.goodbye_message", type: "textarea", label: "Message d'au revoir", help: VARS, preview: "goodbye" },
  ] },
  { id: "verify", icon: "✅", title: "Vérification", desc: "Les nouveaux reçoivent « Non vérifié », puis « Membre » quand ils acceptent les règles.", fields: [
    { path: "panels.verify", type: "channel", label: "Salon des règles", help: "Le panneau avec le bouton y sera publié." },
    { path: "roles.unverified", type: "role", label: "Rôle Non vérifié", help: "Donné automatiquement à l'arrivée." },
    { path: "roles.member", type: "role", label: "Rôle Membre", help: "Donné quand la personne clique sur « J'accepte »." },
    { path: "verification.rules", type: "lines", label: "Règles", help: "Une règle par ligne.", placeholder: "Respecte tout le monde.", preview: "rules" },
    { path: "verification.discord_rules", type: "toggle", label: "Rôle quand on accepte les règles de Discord", help: "Si l'écran de règles de Discord est activé (Paramètres du serveur → Accès / Sécurité), le bot donne le rôle Membre dès que le nouveau venu accepte. Pas besoin du bouton « J'accepte ». Ignoré si le captcha est activé (le captcha reste obligatoire)." },
    { path: "verification.captcha", type: "toggle", label: "Captcha anti-robot", help: "Avant d'obtenir le rôle, il faut recopier un code affiché dans une image." },
  ] },
  { id: "roles", icon: "🔔", title: "Notifications", desc: "Un menu où chacun choisit les sujets pour lesquels il veut être mentionné.", fields: [
    { path: "panels.notifications", type: "channel", label: "Salon du menu" },
    { path: "roles.notifications", type: "notifications", label: "Choix proposés", help: "Nom affiché dans le menu → rôle donné.", preview: "notifications" },
  ] },
  { id: "tickets", icon: "🎫", title: "Tickets", desc: "Un panneau où les membres ouvrent un salon privé avec le staff.", fields: [
    { path: "panels.tickets", type: "channel", label: "Salon du panneau" },
    { path: "channels.ticket_category", type: "category", label: "Catégorie des tickets", help: "Les salons de tickets y sont créés." },
    { path: "channels.ticket_logs", type: "channel", label: "Logs des tickets", help: "Reçoit les transcripts. Vide = salon de logs.", empty: "— Salon de logs —" },
    { path: "tickets.types", type: "ticket_types", label: "Types de tickets", help: "25 maximum. 💎 Premium : chaque type peut avoir son propre formulaire (jusqu'à 5 questions, séparées par |).", preview: "tickets" },
    { path: "tickets.max_open_per_user", type: "number", label: "Tickets ouverts max par membre", min: 1, max: 10 },
    { path: "tickets.inactive_close_hours", type: "number", label: "Fermeture auto après (heures)", help: "Sans aucun message. 0 = jamais.", max: 2000 },
    { path: "tickets.inactive_warning", type: "toggle", label: "Prévenir avant la fermeture auto", help: "Le membre est mentionné dans le ticket peu avant (jusqu'à 12 h avant) : un nouveau message annule la fermeture." },
    { path: "tickets.unclaimed_alert_minutes", type: "number", label: "Relance si personne ne prend en charge (minutes)", help: "Le rôle Staff est mentionné dans le ticket et un message part dans les logs des tickets. 0 = jamais.", max: 10080 },
    { path: "tickets.saved_replies", type: "ticket_replies", label: "Réponses enregistrées", help: "Le staff les envoie avec /ticket reponse (la liste s'affiche en tapant). Variables : {user} (le membre), {staff} (toi), {number} (n° du ticket). 5 réponses (💎 50)." },
    { path: "tickets.transcripts", type: "toggle", label: "Transcript HTML", help: "Copie de la conversation envoyée dans les logs et au membre à la fermeture." },
    { path: "tickets.feedback", type: "toggle", label: "Avis ⭐ après fermeture", help: "Le membre note le support de 1 à 5." },
  ] },
  { id: "levels", icon: "📈", title: "Niveaux", desc: "Les membres gagnent de l'XP en discutant.", fields: [
    { path: "leveling.enabled", type: "toggle", label: "Activer les niveaux" },
    { path: "channels.level_up", type: "channel", label: "Salon des annonces", help: "Vide = dans le salon où la personne a parlé.", empty: "— Même salon —" },
    { path: "leveling.level_up_message", type: "text", label: "Message de passage de niveau", help: "Variables : {mention} {name} {level}", preview: "levelup" },
    { path: "roles.level_roles", type: "level_roles", label: "Rôles de récompense", help: "Niveau atteint → rôle donné." },
    { path: "leveling.xp_min", type: "number", label: "XP minimum par message", max: 1000 },
    { path: "leveling.xp_max", type: "number", label: "XP maximum par message", max: 1000 },
    { path: "leveling.cooldown_seconds", type: "number", label: "Délai entre deux gains (s)", help: "Empêche de farmer en spammant.", max: 3600 },
    { path: "leveling.booster_multiplier", type: "number", label: "Bonus des boosters", help: "1.5 = +50 % d'XP.", step: 0.1, max: 10 },
    { path: "leveling.ignored_channels", type: "channels", label: "Salons sans XP", help: "Texte et vocal." },
    { path: "leveling.rank_card", type: "toggle", label: "Carte de rang en image", help: "/rank affiche une belle carte aux couleurs du serveur." },
    { path: "leveling.voice_enabled", type: "toggle", label: "XP en vocal", help: "Gagné chaque minute en vocal (pas seul, pas muet, pas AFK)." },
    { path: "leveling.voice_xp_per_minute", type: "number", label: "XP vocal par minute", max: 500 },
  ] },
  { id: "economy", icon: "💰", title: "Économie", desc: "Monnaie du serveur : /daily, /work, /pay, /balance, /richest. Boutique 💎 : /shop, /buy, /inventory.", fields: [
    { path: "economy.enabled", type: "toggle", label: "Activer l'économie" },
    { path: "economy.currency_name", type: "text", label: "Nom de la monnaie", placeholder: "pièces" },
    { path: "economy.currency_emoji", type: "text", label: "Emoji de la monnaie", placeholder: "🪙" },
    { path: "economy.daily_amount", type: "number", label: "Gain de /daily", max: 1000000 },
    { path: "economy.daily_streak_bonus", type: "number", label: "Bonus par jour de série", help: "Ajouté pour chaque jour consécutif (série max 30).", max: 100000 },
    { path: "economy.work_min", type: "number", label: "Gain minimum de /work", max: 1000000 },
    { path: "economy.work_max", type: "number", label: "Gain maximum de /work", max: 1000000 },
    { path: "economy.work_cooldown_minutes", type: "number", label: "Délai entre deux /work (minutes)", max: 10080 },
    { path: "economy.bank_enabled", type: "toggle", label: "Banque", help: "/banque deposer et /banque retirer : l'argent placé rapporte des intérêts chaque jour." },
    { path: "economy.bank_interest", type: "number", label: "Intérêts par jour (%)", help: "Entre 0 et 10 %. Version gratuite : 1 %.", step: 0.1, max: 10 },
    { path: "economy.bank_max", type: "number", label: "Plafond de la banque", help: "Au-delà, plus de dépôt ni d'intérêts. 0 = pas de plafond.", max: 1000000000 },
    { path: "economy.vote_reward", type: "number", label: "Récompense de vote (top.gg)", help: "Donnée avec /vote après avoir voté pour le bot sur top.gg (doublée le week-end). 0 = pas de récompense.", max: 1000000 },
    { path: "economy.shop", type: "shop", label: "Boutique", help: "Un objet peut donner un rôle quand on l'achète (place le rôle sous celui du bot)." },
  ] },
  { id: "engagement", icon: "🏅", title: "Succès & quêtes", desc: "Fait revenir les membres : 19 succès à débloquer (badges + récompenses), 3 quêtes par jour, séries d'activité. Commandes : /profil, /succes, /quetes.", fields: [
    { path: "engagement.enabled", type: "toggle", label: "Activer l'engagement" },
    { path: "engagement.achievements", type: "toggle", label: "Succès et badges", help: "Messages, niveaux, fortune, séries, invitations, quêtes, mini-jeux. Chaque succès donne une récompense." },
    { path: "engagement.quests", type: "toggle", label: "Quêtes du jour", help: "3 quêtes tirées au sort chaque jour (les mêmes pour tout le serveur)." },
    { path: "engagement.quest_reward", type: "number", label: "Récompense par quête du jour", max: 1000000 },
    { path: "engagement.weekly_quests", type: "toggle", label: "Quête de la semaine", help: "Une quête plus difficile, renouvelée chaque lundi." },
    { path: "engagement.weekly_reward", type: "number", label: "Récompense de la quête de la semaine", max: 10000000 },
    { path: "engagement.announce", type: "toggle", label: "Annoncer les succès et quêtes terminées" },
    { path: "engagement.channel", type: "channel", label: "Salon des annonces", help: "Vide = dans le salon de l'action (message effacé après 1 minute).", empty: "— Même salon —" },
  ] },
  { id: "agenda", icon: "📅", title: "Événements & tournois", desc: "Événements avec inscription et rappel (/evenement creer), tournois à élimination directe avec tableau tiré au sort (/tournoi creer, lancer, resultat). 16 joueurs en gratuit, 💎 64 en Premium.", fields: [
    { path: "events.enabled", type: "toggle", label: "Activer les événements et tournois" },
    { path: "events.manager_role", type: "role", label: "Rôle gestionnaire", help: "Peut créer et gérer les événements et tournois (en plus de « Gérer le serveur »)." },
    { path: "events.reminder_minutes", type: "number", label: "Rappel avant le début (minutes)", help: "Les inscrits sont mentionnés dans le salon de l'événement.", min: 1, max: 1440 },
  ] },
  { id: "ai", icon: "🤖", title: "Assistant IA", desc: "Le bot répond aux questions des membres à partir de tes règles et de ta FAQ (/ia, salon dédié ou mention), résume les tickets pour le staff (/resume-ticket) et rédige des annonces (/annonce-ia).", fields: [
    { path: "ai.enabled", type: "toggle", label: "Activer l'assistant IA" },
    { path: "ai.mode", type: "select", label: "Ce que l'IA peut faire", options: [["friendly", "💬 Discussion libre : blagues, culture générale, jeux, et l'aide sur le serveur"], ["server", "📘 Serveur uniquement : ne répond qu'aux questions sur le serveur"]], help: "Dans les deux cas, l'IA n'invente jamais les règles, liens ou dates du serveur : elle utilise la FAQ ci-dessous." },
    { path: "ai.personality", type: "textarea", label: "Personnalité (facultatif)", help: "Comment l'IA parle et se présente. 600 caractères max.", placeholder: "Tu es Cerbère, le chien de garde à trois têtes du serveur : drôle, un peu taquin, tu tutoies tout le monde et tu adores les jeux vidéo." },
    { path: "ai.knowledge", type: "textarea", label: "FAQ et informations du serveur", help: "Tout ce que l'IA doit savoir : horaires, liens, comment devenir staff, IP du serveur de jeu… 8 000 caractères max. Les règles (onglet Vérification) sont ajoutées automatiquement.", placeholder: "Q : Comment devenir modérateur ?\nR : Les candidatures ouvrent chaque mois, ouvre un ticket « Rejoindre la team »." },
    { path: "ai.channel", type: "channel", label: "Salon d'aide IA", help: "Le bot répond à toutes les questions posées dans ce salon. Facultatif.", empty: "— Aucun —" },
    { path: "ai.answer_mentions", type: "toggle", label: "Répondre quand on mentionne le bot", help: "Dans n'importe quel salon." },
    { path: "ai.daily_limit", type: "number", label: "Questions maximum par jour", help: "Pour tout le serveur (1 à 1000).", min: 1, max: 1000 },
  ] },
  { id: "games", icon: "🎮", title: "Mini-jeux", desc: "Jeux avec la monnaie du serveur : /pileouface, /des, /devine, /quiz. Casino 💎 : /roulette, /blackjack.", fields: [
    { path: "games.enabled", type: "toggle", label: "Activer les mini-jeux", help: "Nécessite l'économie activée." },
    { path: "games.max_bet", type: "number", label: "Mise maximum", help: "0 = pas de limite.", max: 1000000000 },
    { path: "games.quiz_reward", type: "number", label: "Gain du /quiz", max: 1000000 },
    { path: "games.guess_reward", type: "number", label: "Gain max de /devine", help: "Diminue à chaque essai raté.", max: 1000000 },
  ] },
  { id: "birthdays", icon: "🎂", title: "Anniversaires & rappels", desc: "Les membres enregistrent leur date avec /anniversaire definir ; le bot la fête automatiquement. /rappel permet de programmer des rappels.", fields: [
    { path: "birthdays.enabled", type: "toggle", label: "Activer les anniversaires" },
    { path: "birthdays.channel", type: "channel", label: "Salon des annonces" },
    { path: "birthdays.message", type: "textarea", label: "Message d'anniversaire", help: VARS, preview: "birthday" },
    { path: "birthdays.role", type: "role", label: "Rôle « anniversaire » (24 h)", help: "Donné le jour J, retiré le lendemain." },
    { path: "birthdays.timezone", type: "select", label: "Fuseau horaire", options: [["Europe/Paris", "Europe/Paris (France, Belgique, Suisse)"],
      ["America/Montreal", "America/Montreal (Québec)"], ["Africa/Casablanca", "Africa/Casablanca (Maroc)"], ["Africa/Algiers", "Africa/Algiers (Algérie)"],
      ["Africa/Abidjan", "Africa/Abidjan (Afrique de l'Ouest)"], ["Indian/Reunion", "Indian/Reunion (La Réunion)"], ["UTC", "UTC"]] },
    { path: "reminders.enabled", type: "toggle", label: "Activer /rappel", help: "3 rappels actifs par membre en gratuit, 25 en Premium." },
  ] },
  { id: "events", icon: "🎉", title: "Giveaways & sondages", premium: true,
    desc: "Lance des concours (/giveaway start) et des sondages à boutons (/sondage creer) directement dans Discord.", fields: [
    { path: "giveaways.manager_role", type: "role", label: "Rôle gestionnaire des giveaways", help: "En plus des personnes qui ont « Gérer le serveur »." },
  ] },
  { id: "alerts", icon: "📺", title: "Alertes", premium: true,
    desc: "Annonce automatique des lives, des nouvelles vidéos et des articles (vérification toutes les 3 minutes). Variables : {name} {title} {url} {game}. Tu peux mettre @everyone ou mentionner un rôle dans le message.", fields: [
    { path: "alerts.youtube", type: "alerts_youtube", label: "Chaînes YouTube", help: "Ex : @MrBeast ou https://youtube.com/@MrBeast" },
    { path: "alerts.twitch", type: "alerts_twitch", label: "Chaînes Twitch", help: "Le pseudo tel qu'il apparaît dans twitch.tv/pseudo" },
    { path: "alerts.kick", type: "alerts_kick", label: "Chaînes Kick", help: "Le pseudo tel qu'il apparaît dans kick.com/pseudo" },
    { path: "alerts.tiktok", type: "alerts_tiktok", label: "Comptes TikTok", help: "Lives (toutes les 3 min) et nouvelles vidéos (toutes les 15 min). TikTok n'a pas d'API publique : fonctionne via le site, peut parfois être en retard." },
    { path: "alerts.rss", type: "alerts_rss", label: "Flux RSS", help: "Sites d'actu, blogs, patch notes de jeux… Tout flux RSS ou Atom public. Variables : {name} (nom du site) {title} {url}" },
  ] },
  { id: "moderation", icon: "🔨", title: "Modération", desc: "Sanctions automatiques selon le nombre d'avertissements actifs (/warn).", fields: [
    { path: "moderation.warn_expiry_days", type: "number", label: "Expiration des avertissements (jours)", help: "Un avertissement plus ancien ne compte plus pour les sanctions automatiques. 0 = jamais.", max: 3650 },
    { path: "moderation.escalation", type: "escalation", label: "Sanctions automatiques", help: "Minutes : durée du mute." },
    { path: "reports.enabled", type: "toggle", label: "Signalements", help: "Clic droit sur un message → Applications → « Signaler le message ». Le staff reçoit le signalement avec des boutons (supprimer, muter 10 min, traité). /signalements liste ceux en attente." },
    { path: "reports.channel", type: "channel", label: "Salon des signalements", help: "Vide = logs de modération.", empty: "— Logs de modération —" },
    { path: "message_log.enabled", type: "toggle", label: "Journal des messages", help: "Garde les messages modifiés et supprimés pour les consulter dans l'onglet « Journal des messages ». Désactivé = rien n'est gardé." },
    { path: "message_log.days", type: "number", label: "Durée de conservation (jours)", help: "7 jours en gratuit, jusqu'à 30 en Premium. Les messages plus anciens sont effacés automatiquement.", min: 1, max: 30 },
  ] },
  { id: "twitch", icon: "🟣", title: "Modération Twitch", desc: "Le bot modère le chat de ta chaîne Twitch et écrit chaque sanction dans un salon Discord, avec des boutons pour débannir ou bannir sans ouvrir Twitch. Le streamer, les modos et les VIP ne sont jamais sanctionnés.", fields: [
    { path: "twitch_mod.log_channel", type: "channel", label: "Salon du journal Twitch", help: "Vide = salon des logs de modération.", empty: "— Salon des logs de modération —" },
    { path: "twitch_mod.phishing_action", type: "select", options: TWITCH_ACTIONS, label: "Liens d'arnaque", help: "Plus de 20 000 sites d'arnaque connus, et leurs imitations." },
    { path: "twitch_mod.words_action", type: "select", options: TWITCH_ACTIONS, label: "Mots interdits" },
    { path: "twitch_mod.banned_words", type: "lines", label: "Liste des mots interdits", help: "Un mot ou une expression par ligne (majuscules ignorées).", placeholder: "mot interdit" },
    { path: "twitch_mod.links_action", type: "select", options: TWITCH_ACTIONS, label: "Liens", help: "Tous les liens, sauf les sites autorisés ci-dessous." },
    { path: "twitch_mod.allowed_domains", type: "lines", label: "Sites autorisés", help: "Un domaine par ligne (ex : twitch.tv). Les sous-domaines sont inclus.", placeholder: "twitch.tv" },
    { path: "twitch_mod.caps_action", type: "select", options: TWITCH_ACTIONS, label: "Trop de majuscules" },
    { path: "twitch_mod.caps_min_length", type: "number", label: "Majuscules : longueur minimum", help: "Les messages plus courts (en lettres) sont ignorés.", min: 5, max: 500 },
    { path: "twitch_mod.caps_percent", type: "number", label: "Majuscules : pourcentage", help: "À partir de ce pourcentage de lettres en majuscules.", min: 50, max: 100 },
    { path: "twitch_mod.repeat_action", type: "select", options: TWITCH_ACTIONS, label: "Message répété", help: "Le même message plusieurs fois en une minute." },
    { path: "twitch_mod.repeat_count", type: "number", label: "Répétitions avant sanction", min: 2, max: 10 },
    { path: "twitch_mod.timeout_minutes", type: "number", label: "Durée du timeout (minutes)", help: "Pour l'automod et le bouton Timeout du journal (max 14 jours).", min: 1, max: 20160 },
    { path: "twitch_mod.warn_in_chat", type: "toggle", label: "Prévenir dans le chat", help: "Le bot écrit « @pseudo message retiré (raison) » après une suppression ou un timeout." },
    { path: "twitch_mod.exempt_subscribers", type: "toggle", label: "Ne pas sanctionner les abonnés" },
    { path: "twitch_mod.commands", type: "twitch_commands", label: "Commandes du chat", help: "Quand quelqu'un écrit la commande dans le chat Twitch, le bot répond. Variables : {user} (pseudo), {channel} (chaîne). 5 commandes (💎 50)." },
    { path: "twitch_mod.command_cooldown", type: "number", label: "Délai entre deux réponses (secondes)", help: "Pour une même commande, évite que le bot réponde en boucle.", min: 0, max: 3600 },
  ] },
  { id: "automod", icon: "🤖", title: "Automod", desc: "Filtre automatique des messages. Le staff est toujours ignoré.", fields: [
    { path: "automod.enabled", type: "toggle", label: "Activer l'automod" },
    { path: "automod.block_phishing", type: "toggle", label: "Bloquer les liens dangereux", help: "Phishing, faux Nitro, faux Steam : liste de +20 000 arnaques connues + détection des imitations. Le compte qui l'envoie est mis en sourdine 10 min (souvent piraté)." },
    { path: "automod.allowed_domains", type: "lines", label: "Sites autorisés", help: "Un domaine par ligne (ex : monsite.fr), jamais considéré comme dangereux.", placeholder: "monsite.fr" },
    { path: "automod.block_invites", type: "toggle", label: "Bloquer les invitations Discord" },
    { path: "automod.max_mentions", type: "number", label: "Mentions max par message", help: "0 = pas de limite.", max: 100 },
    { path: "automod.spam_messages", type: "number", label: "Anti-spam : messages", help: "Au-delà : suppression + mute 5 min. 0 = désactivé.", max: 50 },
    { path: "automod.spam_seconds", type: "number", label: "Anti-spam : en secondes", max: 60 },
    { path: "automod.banned_words", type: "lines", label: "Mots interdits", help: "Un par ligne. Les variantes (1d10t, i.d.i.o.t) sont aussi détectées.", placeholder: "mot1" },
    { path: "automod.exempt_roles", type: "roles", label: "Rôles ignorés" },
    { path: "automod.auto_slowmode", type: "toggle", label: "Ralenti automatique", help: "Si un salon s'emballe, le mode lent s'active quelques minutes puis se retire tout seul." },
    { path: "automod.slowmode_messages", type: "number", label: "Messages en 10 secondes avant ralenti", min: 3, max: 200 },
    { path: "automod.slowmode_seconds", type: "number", label: "Délai du mode lent (secondes)", min: 1, max: 600 },
    { path: "automod.slowmode_minutes", type: "number", label: "Durée du ralenti (minutes)", min: 1, max: 120 },
  ] },
  { id: "security", icon: "🛡️", title: "Sécurité", desc: "Protection contre les raids (faux comptes en masse) et les nukes (destruction du serveur).", fields: [
    { path: "anti_raid.enabled", type: "toggle", label: "Anti-raid" },
    { path: "anti_raid.min_account_age_days", type: "number", label: "Âge minimum du compte (jours)", help: "0 = pas de limite.", max: 365 },
    { path: "anti_raid.max_joins", type: "number", label: "Arrivées avant alerte raid", min: 2, max: 100 },
    { path: "anti_raid.joins_window_seconds", type: "number", label: "… en combien de secondes", min: 1, max: 300 },
    { path: "anti_raid.action", type: "select", label: "Action sur un compte suspect", options: [["kick", "👢 Expulser"], ["ban", "🔨 Bannir"]] },
    { path: "anti_raid.auto_lockdown", type: "toggle", label: "Lockdown automatique en cas de raid", help: "Refuse toutes les arrivées pendant 5 minutes." },
    { path: "anti_raid.whitelist", type: "ids", label: "Whitelist anti-raid" },
    { path: "anti_nuke.enabled", type: "toggle", label: "Anti-nuke" },
    { path: "anti_nuke.window_seconds", type: "number", label: "Fenêtre de surveillance (s)", min: 1, max: 300 },
    { path: "anti_nuke.max_channel_deletes", type: "number", label: "Suppressions de salons tolérées", min: 1, max: 50 },
    { path: "anti_nuke.max_role_deletes", type: "number", label: "Suppressions de rôles tolérées", min: 1, max: 50 },
    { path: "anti_nuke.max_bans", type: "number", label: "Bans manuels tolérés", min: 1, max: 50 },
    { path: "anti_nuke.max_channel_creates", type: "number", label: "Créations de salons tolérées", min: 1, max: 50 },
    { path: "anti_nuke.action", type: "select", label: "Sanction", options: [["ban", "🔨 Bannir"], ["strip", "🎭 Retirer tous ses rôles"]] },
    { path: "anti_nuke.whitelist", type: "ids", label: "Whitelist anti-nuke", help: "Le propriétaire du serveur est toujours ignoré." },
  ] },
  { id: "modmail", icon: "📬", title: "Modmail & invitations", desc: "Modmail : un membre écrit au bot en message privé, une conversation s'ouvre dans un salon privé du staff (catégorie des tickets). Invitations : le bot retient qui a invité qui (/invitations voir, /invitations classement).", fields: [
    { path: "modmail.enabled", type: "toggle", label: "Activer le modmail", help: "Nécessite la catégorie des tickets (onglet Tickets)." },
    { path: "modmail.anonymous_staff", type: "toggle", label: "Réponses anonymes du staff", help: "Le membre voit « Staff de serveur » au lieu du pseudo." },
    { path: "modmail.greeting", type: "textarea", label: "Message de confirmation", help: "Envoyé au membre à l'ouverture. {server} {name}" },
    { path: "invites.enabled", type: "toggle", label: "Suivre les invitations", help: "Il me faut la permission « Gérer le serveur » pour lire les invitations." },
    { path: "invites.channel", type: "channel", label: "Salon des annonces d'invitation", help: "Facultatif : annonce qui a invité chaque nouveau membre." },
    { path: "invites.message", type: "text", label: "Message d'annonce", help: "{mention} {name} {inviter} {count} {server}" },
    { path: "invites.referral_reward", type: "number", label: "Récompense de parrainage", help: "Argent donné à celui qui invite quand son invité reste assez longtemps. 0 = désactivé.", max: 10000000 },
    { path: "invites.referral_days", type: "number", label: "… après combien de jours", help: "Évite les faux comptes qui rejoignent puis repartent.", max: 90 },
  ] },
  { id: "tempvoice", icon: "🔊", title: "Vocaux temporaires", desc: "Rejoindre le salon « créer » donne à chacun son propre vocal, supprimé automatiquement quand il est vide. Le propriétaire le gère avec /vocal (renommer, limite, verrouiller, inviter, donner).", fields: [
    { path: "temp_voice.enabled", type: "toggle", label: "Activer les vocaux temporaires" },
    { path: "temp_voice.creator_channel", type: "voice", label: "Salon « ➕ Créer un salon »", help: "Le vocal à rejoindre pour créer le sien.", empty: "— Choisir un vocal —" },
    { path: "temp_voice.category", type: "category", label: "Catégorie des vocaux créés", help: "Vide = même catégorie que le salon « créer ».", empty: "— Même catégorie —" },
    { path: "temp_voice.name_template", type: "text", label: "Nom des salons", help: "{name} = pseudo du propriétaire." },
    { path: "temp_voice.default_limit", type: "number", label: "Places par défaut", help: "0 = illimité.", max: 99 },
  ] },
  { id: "community", icon: "💡", title: "Suggestions & starboard", desc: "/suggestion publie une idée avec des votes 👍/👎 ; le staff l'accepte ou la refuse. Le starboard met en avant les messages qui reçoivent assez d'étoiles.", fields: [
    { path: "suggestions.enabled", type: "toggle", label: "Activer les suggestions" },
    { path: "suggestions.channel", type: "channel", label: "Salon des suggestions" },
    { path: "starboard.enabled", type: "toggle", label: "Activer le starboard" },
    { path: "starboard.channel", type: "channel", label: "Salon du starboard" },
    { path: "starboard.emoji", type: "text", label: "Emoji", help: "Réaction qui compte (ex : ⭐ ou 🔥)." },
    { path: "starboard.threshold", type: "number", label: "Réactions nécessaires", min: 1, max: 100 },
  ] },
  { id: "counters", icon: "📊", title: "Compteurs", desc: "Des salons vocaux dont le nom affiche un nombre (membres, en ligne, boosts…), mis à jour toutes les 10 minutes. Astuce : crée des vocaux que personne ne peut rejoindre.", fields: [
    { path: "counters", type: "counters", label: "Compteurs", help: "2 en version gratuite, 5 en 💎 Premium." },
  ] },
  { id: "commands", icon: "💬", title: "Commandes perso", desc: "Le bot répond automatiquement quand un message correspond au déclencheur (ex : « !regles », « !ip »).", fields: [
    { path: "custom_commands", type: "custom_commands", label: "Commandes", help: "5 en version gratuite, 50 en 💎 Premium. Anti-spam : 5 s entre deux réponses." },
  ] },
  { id: "rolemenus", icon: "🎭", title: "Menus de rôles", desc: "Crée tes propres panneaux de rôles (couleurs, jeux, régions…) à boutons ou en menu déroulant, puis publie-les.", fields: [
    { path: "role_menus", type: "role_menus", label: "Menus", help: "2 en version gratuite, 15 en 💎 Premium. Enregistre avant de publier." },
  ] },
  { id: "messages", icon: "📨", title: "Messages", fields: [
    { path: "scheduled", type: "scheduled", label: "Messages programmés" },
  ] },
  { id: "msglog", icon: "🕵️", title: "Journal des messages" },
  { id: "access", icon: "👮", title: "Accès au panel", premium: true,
    desc: "Donne à certains rôles (ex : Modérateurs) un accès limité au panel, sans leur donner « Gérer le serveur ». Ils ne voient et ne modifient que les parties cochées. Les admins ont toujours accès à tout.", fields: [
    { path: "panel_access", type: "panel_access", label: "Rôles autorisés", help: "10 rôles maximum. La création automatique, les modèles, la sauvegarde et cet onglet restent réservés aux admins." },
  ] },
  { id: "backup", icon: "💾", title: "Sauvegarde" },
  { id: "audit", icon: "📜", title: "Historique" },
  { id: "premium", icon: "💎", title: "Premium" },
];

// ------------------------------------------------------------------ graphiques (SVG, sans librairie)
const CHART_COLORS = { joins: "#3ba55d", leaves: "#ed4245", messages: "#5865f2", voice_minutes: "#eb459e",
  tickets: "#f0b232", cases: "#e67e22", members: "#7983f5" };

function svgEl(tag, attrs = {}, ...children) {
  const el = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
  for (const c of children) el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  return el;
}

/* Barres groupées (ou ligne si type = "line"). datasets : [{ key, label, values }] */
function chart(labels, datasets, type = "bar") {
  const W = 640, H = 200, padL = 36, padB = 22, padT = 10;
  const values = datasets.flatMap((d) => d.values.filter((v) => v != null));
  const max = Math.max(1, ...values);
  // Les courbes (ex. nombre de membres) partent du minimum pour qu'on voie les variations
  const minVal = type === "line" && values.length ? Math.min(...values) : 0;
  const span = Math.max(1, max - minVal);
  const nice = Math.pow(10, Math.floor(Math.log10(span)));
  const lo = type === "line" ? Math.max(0, Math.floor((minVal - span * 0.2) / nice) * nice) : 0;
  const top = Math.max(lo + nice, Math.ceil(max / nice) * nice);
  const plotW = W - padL - 6, plotH = H - padB - padT;
  const x = (i) => padL + (plotW * (i + 0.5)) / labels.length;
  const y = (v) => padT + plotH - (plotH * ((v ?? lo) - lo)) / (top - lo);
  const svg = svgEl("svg", { viewBox: `0 0 ${W} ${H}`, class: "chart", role: "img" });
  for (let i = 0; i <= 4; i++) {
    const v = lo + ((top - lo) * i) / 4, yy = y(v);
    svg.append(svgEl("line", { x1: padL, x2: W - 6, y1: yy, y2: yy, class: "grid" }),
      svgEl("text", { x: padL - 6, y: yy + 4, class: "axis", "text-anchor": "end" }, v >= 1000 ? `${Math.round(v / 100) / 10}k` : Math.round(v)));
  }
  const step = Math.max(1, Math.ceil(labels.length / 8));
  labels.forEach((l, i) => { if (i % step === 0 || i === labels.length - 1)
    svg.append(svgEl("text", { x: x(i), y: H - 6, class: "axis", "text-anchor": "middle" }, l.slice(8, 10) + "/" + l.slice(5, 7))); });
  if (type === "line") {
    for (const d of datasets) {
      const pts = d.values.map((v, i) => (v == null ? null : `${x(i)},${y(v)}`)).filter(Boolean);
      if (pts.length) svg.append(svgEl("polyline", { points: pts.join(" "), fill: "none", stroke: CHART_COLORS[d.key], "stroke-width": 2.5 }));
      d.values.forEach((v, i) => { if (v != null) svg.append(svgEl("circle", { cx: x(i), cy: y(v), r: 3, fill: CHART_COLORS[d.key] },
        svgEl("title", {}, `${labels[i]} : ${v} ${d.label}`))); });
    }
  } else {
    const groupW = (plotW / labels.length) * 0.8, barW = groupW / datasets.length;
    datasets.forEach((d, j) => d.values.forEach((v, i) => {
      const x0 = x(i) - groupW / 2 + j * barW, yy = y(v);
      svg.append(svgEl("rect", { x: x0, y: yy, width: Math.max(1, barW - 1), height: padT + plotH - yy, rx: 2, fill: CHART_COLORS[d.key] },
        svgEl("title", {}, `${labels[i]} : ${v} ${d.label}`)));
    }));
  }
  const legend = h("div", { class: "legend" }, datasets.map((d) =>
    h("span", {}, h("i", { style: `background:${CHART_COLORS[d.key]}` }), d.label)));
  return h("div", { class: "chart-wrap" }, svg, legend);
}

function renderStats() {
  const g = state.guild;
  const box = h("div", {}, h("div", { class: "spinner" }));
  const days = state.statsDays || 7;
  const tabs = h("div", { class: "actions-row", style: "margin:0 0 16px" }, [7, 30, 90].map((d) =>
    h("button", { class: "btn small" + (d === days ? " primary" : " ghost"), onclick: () => {
      if (d > 7 && !g.premium.active) { state.section = "premium"; renderGuild(); return toast("Les statistiques sur 30 et 90 jours sont Premium 💎", "err"); }
      state.statsDays = d; renderGuild();
    } }, `${d} jours`, d > 7 && !g.premium.active ? " 💎" : "")));
  const staff = renderStaffStats(days);
  if (!fullAccess() && !g.access.groups.includes("stats")) {
    return [h("div", { class: "panel" }, h("h2", {}, "📊 Statistiques"), tabs), staff];
  }
  api("GET", `/api/guilds/${g.guild.id}/stats?days=${days}`).then((s) => {
    const t = s.totals, L = s.labels, S = s.series;
    box.replaceChildren(
      h("div", { class: "cards" },
        h("div", { class: "stat" }, h("b", {}, `+${t.joins}`), h("span", {}, "arrivées")),
        h("div", { class: "stat" }, h("b", {}, `-${t.leaves}`), h("span", {}, "départs")),
        h("div", { class: "stat" }, h("b", {}, t.messages.toLocaleString("fr-FR")), h("span", {}, "messages")),
        h("div", { class: "stat" }, h("b", {}, `${Math.round(t.voice_minutes / 60)} h`), h("span", {}, "en vocal"))),
      h("div", { class: "panel" }, h("h2", {}, "👥 Membres"),
        chart(L, [{ key: "members", label: "membres", values: s.members }], "line"),
        chart(L, [{ key: "joins", label: "arrivées", values: S.joins }, { key: "leaves", label: "départs", values: S.leaves }])),
      h("div", { class: "panel" }, h("h2", {}, "💬 Activité"),
        chart(L, [{ key: "messages", label: "messages", values: S.messages }]),
        chart(L, [{ key: "voice_minutes", label: "minutes en vocal", values: S.voice_minutes }])),
      h("div", { class: "panel" }, h("h2", {}, "🎫 Tickets et modération"),
        chart(L, [{ key: "tickets", label: "tickets ouverts", values: S.tickets }, { key: "cases", label: "sanctions", values: S.cases }])),
      h("p", { class: "muted", style: "font-size:13px" }, "Les statistiques sont collectées depuis l'arrivée de cette version du bot (dates en UTC)."));
    translateDom(box);
  }).catch((e) => box.replaceChildren(h("div", { class: "notice warn" }, e.message)));
  return [h("div", { class: "panel" }, h("h2", {}, "📊 Statistiques"),
    h("p", { class: "desc" }, "L'évolution de ton serveur jour par jour."), tabs), box, staff];
}

/* Activité du staff : sanctions par type, tickets pris en charge, notes. */
const ACTION_LABELS = { warn: "⚠️", mute: "🔇", timeout: "🔇", kick: "👢", ban: "🔨", tempban: "⏳", softban: "🧹", unban: "🔓", unmute: "🔊" };
function renderStaffStats(days) {
  const box = h("div", { class: "panel" }, h("h2", {}, "👮 Activité du staff"), h("div", { class: "spinner" }));
  api("GET", `/api/guilds/${state.guild.guild.id}/staffstats?days=${days}`).then(({ staff }) => {
    const rows = staff.map((s) => h("tr", {},
      h("td", {}, h("span", { class: "staff-name" }, s.avatar ? h("img", { src: s.avatar, alt: "" }) : null, s.name)),
      h("td", {}, h("b", {}, s.total)),
      h("td", {}, Object.entries(s.actions).sort((a, b) => b[1] - a[1]).map(([a, n]) => `${ACTION_LABELS[a] || "📝"} ${n}`).join("  ") || "—"),
      h("td", {}, s.tickets || "—"), h("td", {}, s.notes || "—")));
    box.replaceChildren(h("h2", {}, "👮 Activité du staff"),
      h("p", { class: "desc" }, `Sur les ${days} derniers jours : sanctions données, tickets pris en charge et notes écrites. Aussi dans Discord avec /modstats.`),
      staff.length ? h("div", { class: "table-wrap" }, h("table", { class: "staff-table" },
        h("thead", {}, h("tr", {}, h("th", {}, "Membre du staff"), h("th", {}, "Total"), h("th", {}, "Sanctions"),
          h("th", {}, "Tickets"), h("th", {}, "Notes"))), h("tbody", {}, rows)))
        : h("p", { class: "muted" }, "Aucune activité du staff sur cette période."));
    translateDom(box);
  }).catch((e) => box.replaceChildren(h("div", { class: "notice warn" }, e.message)));
  return box;
}

/* Journal des messages modifiés / supprimés, avec filtres. */
function renderMessageLog() {
  const g = state.guild;
  const filters = state.logFilters ||= { user: "", channel: "0", action: "", q: "" };
  const box = h("div", {}, h("div", { class: "spinner" }));
  const channelSel = selectId(channelOptions("text"), filters.channel, (v) => { filters.channel = String(v); load(); }, "Tous les salons");
  const actionSel = h("select", { onchange: (e) => { filters.action = e.target.value; load(); } },
    h("option", { value: "" }, "Modifiés et supprimés"), h("option", { value: "edit" }, "✏️ Modifiés"), h("option", { value: "delete" }, "🗑️ Supprimés"));
  actionSel.value = filters.action;
  const userInput = h("input", { type: "text", placeholder: "ID du membre", value: filters.user, class: "narrow",
    onchange: (e) => { filters.user = e.target.value.trim(); load(); } });
  const search = h("input", { type: "text", placeholder: "Rechercher un mot…", value: filters.q,
    onchange: (e) => { filters.q = e.target.value.trim(); load(); } });
  function load() {
    const params = new URLSearchParams();
    if (filters.user) params.set("user", filters.user);
    if (filters.channel && filters.channel !== "0") params.set("channel", filters.channel);
    if (filters.action) params.set("action", filters.action);
    if (filters.q) params.set("q", filters.q);
    box.replaceChildren(h("div", { class: "spinner" }));
    api("GET", `/api/guilds/${g.guild.id}/messagelog?${params}`).then(({ enabled, entries }) => {
      box.replaceChildren(
        enabled ? "" : h("div", { class: "notice warn" }, "Le journal est désactivé : active-le dans l'onglet Modération (rien n'est enregistré tant qu'il est désactivé)."),
        entries.length ? h("ul", { class: "diag msglog" }, entries.map((e) => h("li", { class: e.action === "delete" ? "error" : "warn" },
          h("span", {}, e.action === "delete" ? "🗑️" : "✏️"),
          h("div", {},
            h("b", {}, e.author), h("span", { class: "muted" }, ` · #${e.channel} · ${new Date(e.at * 1000).toLocaleString(LANG === "en" ? "en-GB" : "fr-FR")} · `),
            h("a", { href: e.link, target: "_blank", rel: "noopener" }, "Aller au message"),
            h("div", { class: "msg-before" }, e.before || "—"),
            e.action === "edit" ? h("div", { class: "msg-after" }, "→ ", e.after || "—") : null))))
          : h("p", { class: "muted" }, "Aucun message dans le journal pour ces filtres."));
      translateDom(box);
    }).catch((err) => box.replaceChildren(h("div", { class: "notice warn" }, err.message)));
  }
  load();
  return [h("div", { class: "panel" }, h("h2", {}, "🕵️ Journal des messages"),
    h("p", { class: "desc" }, "Les messages modifiés et supprimés (200 derniers), gardés le temps choisi dans l'onglet Modération puis effacés automatiquement."),
    h("div", { class: "actions-row log-filters" }, channelSel, actionSel, userInput, search)), h("div", { class: "panel" }, box)];
}

const AUDIT_LABELS = { config: "a modifié la configuration", autocreate: "a lancé la création automatique",
  panels: "a publié les panneaux", send: "a envoyé un message", rolemenu: "a publié un menu de rôles", import: "a importé une sauvegarde",
  template: "a appliqué un modèle", trial: "a démarré l'essai Premium", ai_key: "a branché une IA",
  ai_key_delete: "a supprimé la clé IA", twitch_connect: "a relié une chaîne Twitch",
  twitch_disconnect: "a délié une chaîne Twitch", patreon: "a activé Premium avec Patreon",
  patreon_remove: "a retiré son Premium Patreon" };
// (l'onglet Statistiques est visible avec l'accès « Statistiques » ou « Modération »)

function renderAudit() {
  const g = state.guild;
  const box = h("div", { class: "panel" }, h("div", { class: "spinner" }));
  api("GET", `/api/guilds/${g.guild.id}/audit`).then(({ entries }) => {
    box.replaceChildren(h("h2", {}, "📜 Historique du panel"),
      h("p", { class: "desc" }, "Qui a modifié quoi dans le panel (100 dernières actions)."),
      entries.length ? h("ul", { class: "diag" }, entries.map((e) => h("li", { class: "ok" },
        h("div", {},
          h("b", {}, e.username), " ", AUDIT_LABELS[e.action] || e.action, " · ",
          h("span", { class: "muted" }, new Date(e.at * 1000).toLocaleString(LANG === "en" ? "en-GB" : "fr-FR")),
          e.details.length ? h("div", { class: "help" }, e.details.join(" · ")) : null))))
        : h("p", { class: "muted" }, "Aucune modification pour l'instant."));
    translateDom(box);
  }).catch((err) => box.replaceChildren(h("div", { class: "notice warn" }, err.message)));
  return [box];
}

const PREMIUM_FEATURES = [
  ["🎉", "Giveaways et sondages", "Concours avec tirage automatique, sondages à boutons avec résultats en direct."],
  ["🔐", "Captcha de vérification", "Bloque les comptes robots avant qu'ils accèdent au serveur."],
  ["🎙️", "Niveaux avancés", "XP en vocal, carte de rang en image, classements de la semaine et du mois."],
  ["📺", "Alertes Twitch et YouTube", "Annonce automatique des lives et des nouvelles vidéos."],
  ["🎨", "Personnalisation complète", "Couleur, pied de page, messages de bienvenue, d'au revoir et de niveau."],
  ["📄", "Tickets avancés", "Transcripts HTML et avis ⭐ après chaque ticket."],
  ["💥", "Sécurité avancée", "Anti-nuke, lockdown automatique en cas de raid, alertes au propriétaire."],
  ["🎵", "Alertes Kick, TikTok et RSS", "Lives Kick et TikTok, nouvelles vidéos TikTok, articles de n'importe quel site."],
  ["🏆", "Quête de la semaine", "Une grosse quête chaque semaine en plus des 3 quêtes du jour, et intérêts de banque réglables."],
  ["🤖", "IA incluse", "Sans clé à fournir : répond aux questions avec ta FAQ, résume les tickets et rédige tes annonces."],
  ["👮", "Accès au panel par rôle", "Tes modérateurs gèrent leur partie du panel sans avoir « Gérer le serveur »."],
];

function renderPremium() {
  const p = state.guild.premium;
  const status = p.active
    ? h("div", { class: "notice premium-on" }, "💎 Ce serveur est Premium",
        p.source === "grant" ? " (accès offert)" : p.source === "patreon" ? " (abonnement Patreon)" : " (abonnement Discord)",
        p.expires_at ? ` jusqu'au ${new Date(p.expires_at * 1000).toLocaleDateString("fr-FR")}` : "", ". Merci !")
    : h("div", { class: "notice warn" }, "Ce serveur utilise la version gratuite. Les réglages 💎 sont enregistrés mais inactifs.");
  const trial = !p.active && p.trial === "available" && fullAccess()
    ? h("div", { class: "notice" }, h("strong", {}, `🎁 Essai gratuit de ${p.trial_days} jours`),
        " : toutes les fonctions 💎, sans paiement, une seule fois par serveur. ",
        h("button", { class: "btn primary", onclick: async (e) => {
          if (JSON.stringify(state.cfg) !== state.original && !confirm("Tu as des modifications non enregistrées : elles seront perdues. Continuer ?")) return;
          e.target.disabled = true;
          try {
            await api("POST", `/api/guilds/${state.guild.guild.id}/trial`);
            loadGuildData(await api("GET", `/api/guilds/${state.guild.guild.id}`));
            state.section = "premium"; renderGuild();
            toast("🎁 Essai Premium activé !");
          } catch (err) { e.target.disabled = false; toast(err.message, "err"); }
        } }, "Démarrer l'essai"))
    : null;
  const cta = p.active ? null : p.store_url
    ? h("a", { class: "btn primary big", href: p.store_url, target: "_blank", rel: "noopener" }, "💎 Passer à Premium")
    : p.patreon_url ? null
    : h("p", { class: "muted" }, "Pour activer Premium, contacte le propriétaire du bot (ou tape /premium dans Discord).");
  return [h("div", { class: "panel" }, h("h2", {}, "💎 Premium"), status, renderPatreon(p), trial,
    h("div", { class: "premium-grid" },
      PREMIUM_FEATURES.map(([icon, title, text]) => h("div", { class: "feature" },
        h("div", { class: "icon" }, icon), h("h3", {}, title), h("p", {}, text)))),
    cta)];
}

// Premium payé sur Patreon : relier son compte, puis choisir le serveur qui en profite
function renderPatreon(p) {
  if (!p.patreon_url) return null;
  const gid = state.guild.guild.id;
  const box = h("div", { class: "notice patreon-box" }, h("div", { class: "spinner" }));
  const reloadGuild = async (msg) => {
    loadGuildData(await api("GET", `/api/guilds/${gid}`));
    state.section = "premium"; renderGuild();
    if (msg) toast(msg);
  };
  const action = (label, cls, fn) => h("button", { class: `btn ${cls}`, onclick: async (e) => {
    e.target.disabled = true;
    try { await fn(); } catch (err) { e.target.disabled = false; toast(err.message, "err"); }
  } }, label);
  const subscribe = h("a", { class: "btn primary", href: p.patreon_url, target: "_blank", rel: "noopener" },
    "💳 S'abonner sur Patreon");
  const unlink = action("Délier mon compte Patreon", "ghost small", async () => {
    if (!confirm("Délier ton compte Patreon ? Le serveur qui profite de ton abonnement perdra Premium.")) return;
    await api("DELETE", "/api/patreon");
    await reloadGuild("Compte Patreon délié.");
  });
  const fmtDate = (t) => new Date(t * 1000).toLocaleDateString(LANG === "en" ? "en-GB" : "fr-FR");
  const fill = (me) => {
    const title = h("strong", {}, "💳 Premium avec Patreon");
    let body;
    if (!me.linked) {
      body = [h("p", {}, "Abonne-toi sur Patreon (mensuel ou annuel), puis relie ton compte : le Premium s'active sur ce serveur."),
        h("div", { class: "row-actions" }, subscribe,
          fullAccess() ? h("a", { class: "btn", href: `/patreon/connect/${gid}` }, "🔗 Relier mon compte Patreon") : null)];
    } else if (!me.active) {
      body = [h("p", {}, `Compte Patreon relié${me.name ? ` (${me.name})` : ""}, mais aucun abonnement actif pour l'instant. `
          + "Si tu viens de payer, attends une minute puis actualise."),
        h("div", { class: "row-actions" }, subscribe,
          action("🔄 Actualiser", "", async () => {
            const res = await api("POST", "/api/patreon/refresh");
            res.active ? await reloadGuild("Abonnement trouvé !") : (fill(res), toast("Toujours aucun abonnement actif.", "err"));
          }), unlink)];
    } else if (me.guild_id === gid) {
      body = [h("p", {}, "💎 Ton abonnement Patreon rend ce serveur Premium. Merci !"),
        h("div", { class: "row-actions" },
          action("Retirer de ce serveur", "ghost small", async () => {
            if (!confirm("Retirer ton Premium de ce serveur ? Tu ne pourras le mettre sur un autre serveur que dans 7 jours.")) return;
            await api("DELETE", `/api/guilds/${gid}/patreon`);
            await reloadGuild("Premium retiré de ce serveur.");
          }), unlink)];
    } else {
      const elsewhere = me.guild_id ? `Ton abonnement est utilisé sur « ${me.guild_name || me.guild_id} ». ` : "Ton abonnement Patreon est actif. ";
      const wait = me.can_move_at ? h("p", { class: "muted" }, `Changement de serveur possible à partir du ${fmtDate(me.can_move_at)}.`) : null;
      body = [h("p", {}, elsewhere + "Un abonnement = un serveur Premium (changement possible une fois par semaine)."), wait,
        h("div", { class: "row-actions" },
          fullAccess() && !me.can_move_at ? action(me.guild_id ? "💎 Utiliser mon Premium ici à la place" : "💎 Activer Premium sur ce serveur", "primary", async () => {
            if (me.guild_id && !confirm(`« ${me.guild_name || me.guild_id} » perdra Premium. Continuer ?`)) return;
            await api("PUT", `/api/guilds/${gid}/patreon`);
            await reloadGuild("💎 Premium activé sur ce serveur !");
          }) : null, unlink)];
    }
    box.replaceChildren(title, ...body.filter(Boolean));
    translateDom(box);
  };
  api("GET", "/api/patreon").then(fill).catch((err) => box.replaceChildren(err.message));
  return box;
}


// ------------------------------------------------------------------ IA du serveur (clé propre)
const AI_KEY_HELP = {
  openai: "platform.openai.com → API keys → Create new secret key. Il faut ajouter un peu de crédit (l'abonnement ChatGPT Plus ne suffit pas).",
  mistral: "console.mistral.ai → API Keys → Create new key. Une offre gratuite (limitée) existe.",
  gemini: "aistudio.google.com → Get API key → Create API key. Une offre gratuite (limitée) existe.",
  anthropic: "platform.claude.com → API Keys → Create Key. Il faut ajouter un peu de crédit (l'abonnement Claude Pro ne suffit pas).",
};
function renderAiKey() {
  const g = state.guild;
  if (!fullAccess()) return null;
  const current = g.ai_key;
  const providers = g.ai_providers || [];
  const ui = { provider: current ? current.provider : (providers[0] || {}).id, models: [], model: current ? current.model : "" };
  const box = h("div", { class: "panel ai-key" });
  const nameOf = (id) => (providers.find((p) => p.id === id) || {}).name || id;
  const busy = (btn, on) => { btn.disabled = on; };
  const draw = () => {
    const keyInput = h("input", { type: "password", autocomplete: "off", spellcheck: "false",
      placeholder: ui.pendingKey ? "✅ Clé testée : choisis le modèle puis enregistre" : current && current.provider === ui.provider ?`Clé enregistrée (${current.key_hint}) — laisse vide pour la garder` : "Colle ta clé d'API ici" });
    const providerSelect = h("select", { onchange: (e) => { ui.provider = e.target.value; ui.models = []; ui.model = ""; draw(); } },
      providers.map((p) => h("option", { value: p.id, selected: p.id === ui.provider }, p.name)));
    const modelSelect = ui.models.length
      ? h("select", { onchange: (e) => { ui.model = e.target.value; } },
          ui.models.map((m) => h("option", { value: m, selected: m === ui.model }, m)))
      : null;
    const testBtn = h("button", { class: "btn ghost", onclick: async () => {
      busy(testBtn, true);
      try {
        const r = await api("POST", `/api/guilds/${g.guild.id}/ai-key/models`, { provider: ui.provider, key: keyInput.value.trim() });
        ui.models = r.models;
        if (!ui.models.includes(ui.model)) ui.model = ui.models[0];
        ui.pendingKey = keyInput.value.trim();
        toast(`✅ Clé valide : ${r.models.length} modèle(s) disponible(s)`);
        draw();
      } catch (err) { toast(err.message, "err"); busy(testBtn, false); }
    } }, "🔌 Tester la clé");
    const saveBtn = ui.models.length ? h("button", { class: "btn primary", onclick: async () => {
      busy(saveBtn, true);
      try {
        const r = await api("PUT", `/api/guilds/${g.guild.id}/ai-key`, { provider: ui.provider, key: ui.pendingKey || keyInput.value.trim(), model: ui.model });
        g.ai_key = r.ai_key; ui.pendingKey = ""; ui.models = [];
        toast("✅ IA enregistrée : elle répond maintenant sur ce serveur");
        renderContent();
      } catch (err) { toast(err.message, "err"); busy(saveBtn, false); }
    } }, "💾 Enregistrer cette IA") : null;
    const deleteBtn = current ? h("button", { class: "btn ghost", onclick: async () => {
      if (!confirm("Supprimer la clé IA de ce serveur ? L'assistant ne pourra plus répondre avec ton IA.")) return;
      try { await api("DELETE", `/api/guilds/${g.guild.id}/ai-key`); g.ai_key = null; toast("Clé supprimée"); renderContent(); }
      catch (err) { toast(err.message, "err"); }
    } }, "🗑️ Supprimer ma clé") : null;
    const keyUrl = (providers.find((p) => p.id === ui.provider) || {}).key_url;
    box.replaceChildren(...[
      h("h2", {}, "🔑 Ton IA"),
      h("p", { class: "desc" }, "Branche ta propre IA : c'est gratuit avec le bot, tu paies seulement ton fournisseur (certains ont une offre gratuite). Ta clé est chiffrée et n'est jamais réaffichée."),
      !g.ai_keys_ready ? h("div", { class: "notice warn" }, "Le propriétaire du bot doit d'abord activer cette fonction (variable AI_KEYS_SECRET).") : null,
      current
        ? h("div", { class: "notice" }, `✅ IA active : ${nameOf(current.provider)} · modèle ${current.model} · clé ${current.key_hint}`)
        : h("div", { class: "notice" }, g.premium.active && g.premium.ai_ready
          ? "Aucune clé : l'IA incluse avec Premium répond. Tu peux brancher la tienne à la place."
          : "Aucune IA branchée pour l'instant."),
      h("div", { class: "field" }, h("div", {}, h("label", { class: "title" }, "Fournisseur"),
        h("div", { class: "help" }, AI_KEY_HELP[ui.provider] || "", " ", keyUrl ? h("a", { href: keyUrl, target: "_blank", rel: "noopener" }, "Créer ma clé →") : null)),
        h("div", { class: "control" }, providerSelect)),
      h("div", { class: "field" }, h("div", {}, h("label", { class: "title" }, "Clé d'API"),
        h("div", { class: "help" }, "Ne la partage jamais ailleurs. Un abonnement (ChatGPT Plus, Claude Pro…) ne suffit pas : il faut une clé d'API.")),
        h("div", { class: "control" }, keyInput)),
      modelSelect ? h("div", { class: "field" }, h("div", {}, h("label", { class: "title" }, "Modèle"),
        h("div", { class: "help" }, "Les modèles « mini », « flash » ou « small » sont plus rapides et moins chers.")),
        h("div", { class: "control" }, modelSelect)) : null,
      h("div", { class: "row" }, testBtn, saveBtn, deleteBtn)].filter(Boolean));
    translateDom(box);
  };
  draw();
  return box;
}


// ------------------------------------------------------------------ Twitch : connexion des chaînes
function renderTwitch() {
  const g = state.guild;
  const box = h("div", { class: "panel twitch-box" }, h("h2", {}, "🔗 Chaînes Twitch"), h("div", { class: "spinner" }));
  api("GET", `/api/guilds/${g.guild.id}/twitch`).then((t) => {
    const items = [h("h2", {}, "🔗 Chaînes Twitch")];
    if (t.problem) items.push(h("div", { class: "notice warn" }, t.problem));
    if (!t.bot) {
      items.push(h("div", { class: "notice warn" }, "Le compte Twitch du bot n'est pas encore connecté par le propriétaire du bot."));
      if (t.is_owner && !t.problem) items.push(h("p", {}, h("a", { class: "btn primary", href: "/twitch/bot" }, "🤖 Connecter le compte Twitch du bot (propriétaire)")));
    } else {
      items.push(h("p", { class: "desc" }, `Compte du bot : ${t.bot.login}. `,
        t.is_owner ? h("a", { href: "/twitch/bot" }, "Changer de compte (propriétaire)") : null));
    }
    if (!t.channels.length) items.push(h("p", { class: "muted" }, "Aucune chaîne reliée pour l'instant."));
    for (const ch of t.channels) {
      const status = ch.is_mod === true ? "✅ le bot est modérateur"
        : ch.is_mod === false ? `⚠️ tape « /mod ${t.bot ? t.bot.login : "nomdubot"} » dans ton chat Twitch`
        : "❔ statut de modérateur inconnu";
      items.push(h("div", { class: "row twitch-channel" },
        h("a", { href: `https://twitch.tv/${ch.login}`, target: "_blank", rel: "noopener" }, `🟣 ${ch.login}`),
        h("span", { class: ch.is_mod === false ? "warn-text" : "muted" }, status, ch.active ? "" : " · inactive (limite gratuite : 1 chaîne)"),
        fullAccess() ? h("button", { class: "btn ghost small", onclick: async () => {
          if (!confirm(`Délier la chaîne ${ch.login} ? Le bot arrêtera de la modérer.`)) return;
          try { await api("DELETE", `/api/guilds/${g.guild.id}/twitch/${ch.id}`); toast("Chaîne déliée"); renderContent(); }
          catch (err) { toast(err.message, "err"); }
        } }, "Délier") : null));
    }
    if (fullAccess() && !t.problem && t.bot) {
      items.push(t.channels.length < t.limit
        ? h("p", {}, h("a", { class: "btn primary", href: `/twitch/connect/${g.guild.id}` }, "🟣 Connecter ma chaîne Twitch"))
        : h("p", { class: "muted" }, `Limite atteinte (${t.limit} chaîne${t.limit > 1 ? "s" : ""}). 💎 Premium : jusqu'à 5 chaînes.`));
      items.push(h("p", { class: "help" }, "Connecte-toi avec le compte Twitch du streamer. Ensuite, tape /mod suivi du nom du bot dans le chat pour qu'il puisse modérer."));
    }
    box.replaceChildren(...items.filter(Boolean));
    translateDom(box);
  }).catch((err) => { box.replaceChildren(h("h2", {}, "🔗 Chaînes Twitch"), h("div", { class: "notice warn" }, err.message)); });
  return box;
}

// ------------------------------------------------------------------ nouveautés
const CHANGELOG = [
  ["15.1", "Assistant IA plus vivant", ["💬 Mode discussion libre : blagues, culture générale, jeux (ou « serveur uniquement »)",
    "🎭 Personnalité de l'IA réglable", "↩️ Réponds à un message de l'IA pour continuer la conversation"]],
  ["15.0", "Premium avec Patreon", ["💳 Abonne-toi sur Patreon (mensuel ou annuel), relie ton compte dans l'onglet 💎 Premium : le serveur passe Premium tout de suite",
    "🔁 Un abonnement = un serveur, à changer une fois par semaine", "📱 Barre du haut du panel corrigée sur téléphone"]],
  ["14.11", "Contact plus visible", ["📬 Nouvelle page Contact sur le site, accessible depuis le menu et l'accueil",
    "💬 Le bot rappelle /contact à son arrivée sur un serveur et quand une erreur survient"]],
  ["14.10", "Nous contacter", ["📬 /contact : signale un module qui ne marche pas ou propose une idée, le message arrive directement au créateur",
    "📧 Lien Contact sur le site et dans le panel"]],
  ["14.9", "Prêt pour les grands nombres", ["🧩 Le bot se découpe tout seul en shards au-delà de 2 500 serveurs",
    "📡 Shards visibles sur la page Statut et dans /ping"]],
  ["14.8", "Tickets plus rapides", ["🎫 Réponses enregistrées : /ticket reponse (5, 💎 50), avec {user}, {staff} et {number}",
    "⏰ Relance du staff si personne ne prend un ticket en charge", "⏳ Le membre est prévenu avant la fermeture automatique d'un ticket inactif"]],
  ["14.7", "Tes données", ["/mes-donnees voir et /mes-donnees effacer pour chaque membre",
    "Données d'un serveur effacées 30 jours après le départ du bot (gardées s'il revient)", "Vieilles statistiques et journaux effacés automatiquement"]],
  ["14.6", "Commandes du chat Twitch", ["💬 Commandes du chat Twitch (!discord, !reseaux…) réglées dans l'onglet Modération Twitch, avec {user} et {channel}"]],
  ["14.5", "Modération Twitch", ["🟣 Nouvel onglet Modération Twitch : connecte ta chaîne, le bot modère le chat (arnaques, mots interdits, liens, majuscules, répétitions)",
    "Journal des sanctions Twitch dans Discord, avec boutons Débannir / Timeout / Bannir", "Les bans et timeouts des modos Twitch sont aussi journalisés"]],
  ["14.4", "Ton IA, gratuitement", ["🔑 Branche ta propre IA (ChatGPT, Mistral, Gemini ou Claude) dans l'onglet Assistant IA : l'assistant devient gratuit",
    "Ta clé est chiffrée et n'est jamais réaffichée", "💎 Premium garde l'IA incluse, sans clé"]],
  ["14.3", "Règles de Discord", ["Rôle Membre donné automatiquement quand un nouveau venu accepte l'écran de règles de Discord (onglet Vérification)"]],
  ["14.2", "Essai Premium, votes et fiabilité", ["🎁 Essai Premium gratuit de 7 jours (une fois par serveur)",
    "🗳️ /vote : vote pour le bot sur top.gg et gagne de la monnaie (récompense réglable dans Économie)",
    "Site mieux protégé contre les abus", "Sauvegardes automatiques chaque nuit"]],
  ["14", "Panel et site plus pratiques", ["Menu par catégories et recherche dans tous les réglages", "Checklist de configuration avec barre de progression",
    "Boutons « Tester dans Discord » et « ↺ par défaut »", "Thème clair / sombre, changement rapide de serveur, Ctrl+S pour enregistrer",
    "Site : nouvelles pages Commandes, Premium et Statut"]],
  ["13", "Événements, IA et modération avancée", ["Événements avec inscription et rappel, tournois à élimination directe", "Parrainage récompensé",
    "💎 Assistant IA : FAQ, résumé de ticket, rédaction d'annonces", "Signalements par clic droit, ralenti automatique, journal des messages"]],
  ["12", "Engagement et staff", ["19 succès, quêtes du jour (💎 quête de la semaine), séries d'activité, banque", "Activité du staff et /modstats par période",
    "💎 Accès au panel par rôle", "💎 Alertes Kick, TikTok et RSS"]],
  ["11", "Sécurité et prise en main", ["Avertissements qui expirent, blocage des liens d'arnaque", "Modmail, suivi des invitations",
    "💎 Formulaires de ticket", "Modèles de configuration et assistant de démarrage"]],
  ["10", "Communauté", ["Vocaux temporaires, suggestions, starboard", "Compteurs, commandes perso, menus de rôles", "Messages programmés et sauvegarde de la configuration"]],
  ["9", "Jeux et aperçu", ["Mini-jeux et casino", "Aperçu en direct des messages", "Bot entièrement disponible en anglais"]],
  ["8", "Économie et statistiques", ["Économie et boutique", "Rappels et anniversaires", "Statistiques en graphiques et historique du panel"]],
];

function renderNews() {
  return [h("div", { class: "panel" }, h("h2", {}, "🆕 ", "Nouveautés"),
    h("p", { class: "desc" }, "Ce qui a été ajouté au bot, version par version."),
    h("ul", { class: "news" }, CHANGELOG.map(([v, title, items], i) => h("li", {},
      h("h3", {}, `v${v} · `, title, i === 0 ? h("span", { class: "badge-new" }, "Nouveau") : null),
      h("ul", {}, items.map((t) => h("li", {}, t)))))))];
}

// ------------------------------------------------------------------ checklist de configuration
function checklist() {
  const g = state.guild, c = state.cfg;
  const id = (p) => String(get(c, p) || "0") !== "0";
  const published = Object.values(g.panels || {}).some(Boolean);
  return [
    { done: g.bot.can_manage, label: "Me donner les permissions « Gérer les rôles » et « Gérer les salons »", hint: "Paramètres du serveur → Rôles" },
    { done: id("roles.staff"), label: "Choisir le rôle Staff", go: ["general", "roles.staff"] },
    { done: id("channels.logs"), label: "Choisir un salon de logs (privé)", go: ["general", "channels.logs"] },
    { done: id("channels.welcome"), label: "Choisir le salon de bienvenue", go: ["welcome", "channels.welcome"] },
    { done: id("panels.verify") && id("roles.member"), label: "Configurer la vérification (salon des règles + rôle Membre)", go: ["verify", "panels.verify"] },
    { done: id("channels.ticket_category") && id("panels.tickets"), label: "Configurer les tickets (catégorie + salon du panneau)", go: ["tickets", "panels.tickets"] },
    { done: published, label: "Publier les panneaux (règles, notifications, tickets)", action: "panels" },
    { done: !!get(c, "automod.enabled"), label: "Activer l'automod", go: ["automod", "automod.enabled"] },
  ];
}

function renderChecklist() {
  const items = checklist();
  const done = items.filter((i) => i.done).length;
  const pct = Math.round((100 * done) / items.length);
  return h("div", { class: "panel" },
    h("h2", {}, done === items.length ? "✅ Configuration terminée" : `📋 Configuration : ${done}/${items.length}`),
    h("div", { class: "progress" }, h("i", { style: `width:${pct}%` })),
    h("ul", { class: "checklist" }, items.map((i) => h("li", { class: i.done ? "done" : "" },
      h("span", {}, i.done ? "✅" : "⬜"), h("span", { class: "t" }, i.label),
      !i.done && i.go ? h("button", { class: "btn ghost small", onclick: () => goTo(i.go[0], i.go[1]) }, "Régler →") : null,
      !i.done && i.hint ? h("span", { class: "muted", style: "margin-left:auto;font-size:12px" }, i.hint) : null,
      !i.done && i.action === "panels" ? h("button", { class: "btn ghost small", onclick: () => document.getElementById("publish-panels")?.click() }, "Publier →") : null))));
}

// ------------------------------------------------------------------ vue d'ensemble
function renderOverview() {
  const g = state.guild;
  const errors = g.diagnostic.filter((d) => d.status === "error").length;
  const icon = { ok: "✅", warn: "⚠️", error: "❌" };

  const autoBtn = h("button", { class: "btn primary", onclick: async () => {
    if (savebar.classList.contains("show")) return toast("Enregistre ou annule tes modifications d'abord.", "err");
    if (!confirm("Créer automatiquement tous les rôles et salons manquants (règles, rôles, support, logs, catégorie Tickets, rôles Staff/Membre/Non vérifié, notifications, niveaux) ?")) return;
    autoBtn.disabled = true; autoBtn.textContent = "Création en cours…";
    try {
      const data = await api("POST", `/api/guilds/${g.guild.id}/autocreate`, { notifications: true, levels: true });
      loadGuildData(data);
      toast(data.created.length ? "Créé :\n• " + data.created.join("\n• ") : "Rien à créer, tout existe déjà 👍");
    } catch (e) { toast(e.message, "err"); }
    renderGuild();
  } }, "✨ Tout créer automatiquement");

  const panelBtn = h("button", { class: "btn", id: "publish-panels", onclick: async () => {
    if (savebar.classList.contains("show")) return toast("Enregistre tes modifications d'abord.", "err");
    panelBtn.disabled = true; panelBtn.textContent = "Publication…";
    try {
      const data = await api("POST", `/api/guilds/${g.guild.id}/panels`);
      loadGuildData(data);
      const labels = { verify: "Règles", notifications: "Notifications", tickets: "Tickets" };
      toast(Object.entries(data.published).map(([k, v]) => `${labels[k]} : ${v}`).join("\n"));
    } catch (e) { toast(e.message, "err"); }
    renderGuild();
  } }, "📤 Publier / mettre à jour les panneaux");

  const head = [
    h("div", { class: "notice" + (g.premium.active ? " premium-on" : "") },
      g.premium.active ? "💎 Serveur Premium : toutes les fonctionnalités sont actives." : "Version gratuite. ",
      g.premium.active ? null : h("a", { href: "#", onclick: (e) => { e.preventDefault(); state.section = "premium"; renderGuild(); } },
        "Découvrir Premium →")),
    h("div", { class: "cards" },
      h("div", { class: "stat" }, h("b", {}, g.stats.members.toLocaleString("fr-FR")), h("span", {}, "membres")),
      h("div", { class: "stat" }, h("b", {}, g.stats.open_tickets), h("span", {}, "tickets ouverts")),
      h("div", { class: "stat" }, h("b", {}, g.stats.cases), h("span", {}, "sanctions")),
      h("div", { class: "stat" }, h("b", {}, g.stats.ranked), h("span", {}, "membres classés")))];
  if (!fullAccess()) {
    const names = Object.fromEntries(ACCESS_GROUPS);
    return [...head, h("div", { class: "panel" }, h("h2", {}, "👮 ", "Accès limité"),
      h("p", { class: "desc" }, "Un admin t'a donné accès à une partie du panel. Tu peux modifier :"),
      h("ul", { class: "diag" }, g.access.groups.map((k) => h("li", { class: "ok" }, h("span", {}, "✅"), h("span", {}, names[k] || k)))))];
  }
  return [...head, renderChecklist(),
    h("div", { class: "panel" },
      h("h2", {}, "🚀 Installation rapide"),
      h("p", { class: "desc" }, "1. Crée automatiquement ce qui manque → 2. Ajuste les réglages dans le menu → 3. Publie les panneaux."),
      !g.bot.can_manage ? h("div", { class: "notice warn" }, "Il me manque les permissions « Gérer les rôles » et « Gérer les salons ».") : null,
      h("div", { class: "notice" }, `Pense à placer mon rôle (@${g.bot.top_role}) tout en haut de la liste dans Paramètres du serveur → Rôles, sinon je ne pourrai pas donner les rôles.`),
      h("div", { class: "actions-row" }, autoBtn, panelBtn,
        h("button", { class: "btn ghost", onclick: openWizard }, "🪄 Lancer l'assistant"))),
    h("div", { class: "panel" },
      h("h2", {}, "🧩 ", "Modèles de configuration"),
      h("p", { class: "desc" }, "Applique en un clic des réglages adaptés à ton type de serveur (textes, règles, types de tickets, modules activés). Tes salons et rôles déjà choisis sont conservés."),
      h("div", { class: "premium-grid" }, (g.templates || []).map((t) => h("div", { class: "feature" },
        h("h3", {}, t.name), h("p", {}, t.description),
        h("button", { class: "btn small", style: "margin-top:10px", onclick: () => applyTemplate(t) }, "Appliquer"))))),
    h("div", { class: "panel" },
      h("h2", {}, errors ? `🩺 Diagnostic : ${errors} problème(s)` : "🩺 Diagnostic : tout est bon ✅"),
      h("ul", { class: "diag" }, g.diagnostic.map((d) => h("li", { class: d.status }, h("span", {}, icon[d.status]), h("span", {}, d.text))))),
  ];
}

// ------------------------------------------------------------------ modèles et assistant de démarrage
async function applyTemplate(t, silent = false) {
  if (savebar.classList.contains("show")) { toast("Enregistre ou annule tes modifications d'abord.", "err"); return false; }
  if (!silent && !confirm(`Appliquer le modèle « ${t.name} » ? Les textes et réglages correspondants seront remplacés.`)) return false;
  try {
    loadGuildData(await api("POST", `/api/guilds/${state.guild.guild.id}/template`, { template: t.id }));
    if (!silent) { renderGuild(); toast(`✅ Modèle « ${t.name} » appliqué.`); }
    return true;
  } catch (e) { toast(e.message, "err"); return false; }
}

const WIZARD_FEATURES = [
  ["welcome.enabled", "👋 Messages de bienvenue"], ["leveling.enabled", "📈 Niveaux et XP"], ["economy.enabled", "💰 Économie"],
  ["games.enabled", "🎮 Mini-jeux"], ["automod.enabled", "🤖 Automod"], ["anti_raid.enabled", "🛡️ Anti-raid"],
  ["temp_voice.enabled", "🔊 Vocaux temporaires"], ["suggestions.enabled", "💡 Suggestions"], ["birthdays.enabled", "🎂 Anniversaires"],
  ["modmail.enabled", "📬 Modmail"],
];

function openWizard() {
  if (savebar.classList.contains("show")) return toast("Enregistre ou annule tes modifications d'abord.", "err");
  const g = () => state.guild;
  let step = 0;
  const overlay = h("div", { class: "wizard-overlay" });
  const box = h("div", { class: "wizard" });
  overlay.append(box);
  const close = () => { overlay.remove(); renderGuild(); };
  const nav = (...buttons) => h("div", { class: "actions-row wizard-nav" }, h("button", { class: "btn ghost", onclick: close }, "Fermer"), ...buttons);
  const busy = async (btn, fn) => { btn.disabled = true; try { await fn(); } catch (e) { toast(e.message, "err"); } btn.disabled = false; };

  const steps = [
    () => [h("h2", {}, "🪄 ", "Bienvenue dans l'assistant"),
      h("p", { class: "desc" }, "En 4 étapes, ton serveur sera prêt : type de serveur, fonctions, création des salons et rôles, publication des panneaux."),
      h("h3", {}, "1. Quel type de serveur ?"),
      h("div", { class: "premium-grid" }, (g().templates || []).map((t) => h("button", { class: "feature wizard-choice", onclick: async (e) => {
        const ok = await applyTemplate(t, true);
        if (ok) { toast(`✅ ${t.name}`); step = 1; draw(); }
      } }, h("h3", {}, t.name), h("p", {}, t.description)))),
      nav(h("button", { class: "btn", onclick: () => { step = 1; draw(); } }, "Passer cette étape →"))],
    () => {
      const lang = h("select", {}, h("option", { value: "fr" }, "🇫🇷 Français"), h("option", { value: "en" }, "🇬🇧 English"));
      lang.value = get(state.cfg, "general.language") || "fr";
      const checks = WIZARD_FEATURES.map(([path, label]) => {
        const input = h("input", { type: "checkbox", checked: !!get(state.cfg, path) });
        return { path, input, el: h("label", { class: "inline-check wizard-check" }, input, label) };
      });
      const next = h("button", { class: "btn primary", onclick: () => busy(next, async () => {
        set(state.cfg, "general.language", lang.value);
        for (const c of checks) set(state.cfg, c.path, c.input.checked);
        loadGuildData(await api("PUT", `/api/guilds/${g().guild.id}/config`, state.cfg));
        step = 2; draw();
      }) }, "Enregistrer et continuer →");
      return [h("h2", {}, "2. ", "Langue et fonctions"),
        h("div", { class: "field" }, h("label", { class: "title" }, "Langue du bot sur ce serveur"), lang),
        h("p", { class: "desc" }, "Coche ce que tu veux activer (tout reste modifiable ensuite) :"),
        h("div", { class: "wizard-checks" }, checks.map((c) => c.el)), nav(next)];
    },
    () => {
      const create = h("button", { class: "btn primary", onclick: () => busy(create, async () => {
        const data = await api("POST", `/api/guilds/${g().guild.id}/autocreate`, { notifications: true, levels: true });
        loadGuildData(data);
        toast(data.created.length ? "Créé :\n• " + data.created.join("\n• ") : "Rien à créer, tout existe déjà 👍");
        step = 3; draw();
      }) }, "✨ Créer les salons et rôles");
      return [h("h2", {}, "3. ", "Salons et rôles"),
        h("p", { class: "desc" }, "Je crée ce qui manque : règles, rôles, support, logs privés, catégorie Tickets, suggestions, rôles Staff / Membre / Non vérifié, notifications et niveaux. Rien n'est créé en double."),
        !g().bot.can_manage ? h("div", { class: "notice warn" }, "Il me manque les permissions « Gérer les rôles » et « Gérer les salons ».") : null,
        nav(h("button", { class: "btn", onclick: () => { step = 3; draw(); } }, "Passer →"), create)];
    },
    () => {
      const publish = h("button", { class: "btn primary", onclick: () => busy(publish, async () => {
        const data = await api("POST", `/api/guilds/${g().guild.id}/panels`);
        loadGuildData(data);
        step = 4; draw();
      }) }, "📤 Publier les panneaux");
      return [h("h2", {}, "4. ", "Publier les panneaux"),
        h("p", { class: "desc" }, "Je poste le panneau des règles (avec le bouton de vérification), le menu des notifications et le panneau de tickets dans leurs salons."),
        nav(h("button", { class: "btn", onclick: () => { step = 4; draw(); } }, "Passer →"), publish)];
    },
    () => [h("h2", {}, "🎉 ", "C'est prêt !"),
      h("ul", { class: "diag" },
        h("li", { class: "warn" }, `⚠️ Dernière chose, dans Discord : Paramètres du serveur → Rôles, glisse mon rôle (@${g().bot.top_role}) tout en haut de la liste.`),
        h("li", { class: "ok" }, "Retire « Voir les salons » à @everyone et donne-la au rôle Membre : les nouveaux ne verront que les règles avant de se vérifier."),
        h("li", { class: "ok" }, "Tout se règle ensuite dans les onglets du panel, avec aperçu en direct.")),
      h("div", { class: "actions-row wizard-nav" }, h("button", { class: "btn primary", onclick: close }, "Terminer"))],
  ];
  const draw = () => {
    box.replaceChildren(h("div", { class: "wizard-progress" }, [0, 1, 2, 3, 4].map((i) => h("span", { class: i <= step ? "on" : "" }))), ...steps[step]());
    translateDom(box);
  };
  draw();
  document.body.append(overlay);
}

// ------------------------------------------------------------------ page serveur
function loadGuildData(data) {
  state.guild = data;
  state.cfg = clone(data.config);
  state.original = JSON.stringify(state.cfg);
  markDirty();
}

/* Menu de gauche regroupé par catégories (repliables, état mémorisé). */
const NAV_GROUPS = [
  ["Démarrage", ["overview", "news", "stats", "general"]],
  ["Accueil", ["welcome", "verify", "roles", "rolemenus", "modmail"]],
  ["Communauté", ["levels", "engagement", "economy", "games", "agenda", "events", "birthdays", "community", "tempvoice"]],
  ["Modération", ["moderation", "automod", "twitch", "security", "msglog"]],
  ["Support & IA", ["tickets", "ai"]],
  ["Outils", ["alerts", "messages", "counters", "commands"]],
  ["Gestion", ["access", "backup", "audit", "premium"]],
];
const loadSet = (key) => { try { return new Set(JSON.parse(localStorage.getItem(key) || "[]")); } catch { return new Set(); } };
const saveSet = (key, set) => { try { localStorage.setItem(key, JSON.stringify([...set])); } catch { /* stockage indisponible */ } };

function goTo(sectionId, path) {
  state.section = sectionId; state.search = ""; state.focusPath = path || null;
  renderGuild();
  if (!path) window.scrollTo({ top: 0 });
}

function renderNav() {
  const g = state.guild;
  const errors = g.diagnostic.filter((d) => d.status === "error").length;
  const closed = loadSet("navClosed");
  const newsUnseen = (() => { try { return localStorage.getItem("seenVersion") !== CHANGELOG[0][0]; } catch { return false; } })();
  const item = (s) => h("button", { class: "nav-item" + (state.section === s.id && !state.search ? " active" : ""), "data-id": s.id,
    onclick: () => goTo(s.id) },
    h("span", {}, s.icon), s.title,
    s.premium && !g.premium.active ? h("span", { class: "lock", title: "Premium" }, "💎") : null,
    s.id === "overview" && errors ? h("span", { class: "dot", title: `${errors} problème(s)` }) : null,
    s.id === "news" && newsUnseen ? h("span", { class: "badge-new" }, "Nouveau") : null,
    sectionDirty(s) ? h("span", { class: "dirty", title: "Modifications non enregistrées" }) : null);
  const placed = new Set(NAV_GROUPS.flatMap(([, ids]) => ids));
  const groups = NAV_GROUPS.map(([name, ids]) => [name, ids.concat(name === "Gestion" ? SECTIONS.map((s) => s.id).filter((id) => !placed.has(id)) : [])]);
  const search = h("input", { type: "text", class: "nav-search", placeholder: "🔎 Rechercher un réglage…", value: state.search || "",
    oninput: (e) => { state.search = e.target.value; renderContent(); } });
  const guilds = (state.me?.guilds || []).filter((x) => x.bot_in);
  const switcher = guilds.length > 1 ? h("select", { class: "guild-switch", title: "Changer de serveur",
    onchange: (e) => { location.hash = `#/guild/${e.target.value}`; } },
  guilds.map((x) => h("option", { value: x.id }, x.name))) : null;
  if (switcher) switcher.value = g.guild.id;
  return h("nav", { class: "sidebar" },
    h("div", { class: "guild-head" }, guildIcon(g.guild), h("div", {}, h("b", {}, g.guild.name), switcher)),
    h("a", { class: "nav-item", href: "#/" }, "← Mes serveurs"),
    search,
    groups.map(([name, ids]) => {
      const list = ids.map((id) => SECTIONS.find((s) => s.id === id)).filter((s) => s && canSee(s.id));
      if (!list.length) return null;
      const open = !closed.has(name) || list.some((s) => s.id === state.section);
      const wrap = h("div", { class: "nav-group" + (open ? "" : " closed") },
        h("button", { onclick: () => {
          if (closed.has(name)) closed.delete(name); else closed.add(name);
          saveSet("navClosed", closed); wrap.classList.toggle("closed");
        } }, name, h("span", { class: "chev" }, "▾")),
        h("div", { class: "nav-items" }, list.map(item)));
      return wrap;
    }));
}

/* Recherche dans tous les réglages (titre, aide, onglet). */
const norm = (s) => String(s || "").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");
function renderSearch(query) {
  const q = norm(query.trim());
  const results = [];
  for (const s of SECTIONS) {
    if (!canSee(s.id)) continue;
    if (norm(s.title).includes(q) || norm(translateText(s.title)).includes(q)) results.push({ s, label: s.title, sub: s.desc || "" });
    for (const f of s.fields || []) {
      const text = [f.label, f.help, f.placeholder, translateText(f.label || ""), translateText(f.help || "")].map(norm).join(" ");
      if (text.includes(q)) results.push({ s, f, label: f.label, sub: f.help || "" });
    }
  }
  return [h("div", { class: "panel" }, h("h2", {}, "🔎 ", "Résultats de recherche"),
    results.length ? h("ul", { class: "search-results" }, results.slice(0, 40).map((r) => h("li", {},
      h("button", { onclick: () => goTo(r.s.id, r.f?.path) },
        h("b", {}, `${r.s.icon} ${translateText(r.s.title)}`, r.f ? ` › ${translateText(r.label)}` : ""),
        r.sub ? h("small", {}, translateText(r.sub).slice(0, 160)) : null))))
      : h("p", { class: "muted" }, "Aucun réglage ne correspond. Essaie un autre mot (ex : bienvenue, ticket, xp, logs)."))];
}

function renderGuild() {
  const nav = renderNav();
  app.replaceChildren(h("div", { class: "layout" }, nav, h("div", { id: "content" })));
  renderContent();
}

function renderContent() {
  const g = state.guild;
  const holder = document.getElementById("content");
  if (!holder) return;
  previews = [];
  if (state.search && state.search.trim().length >= 2) {
    holder.replaceChildren(...renderSearch(state.search));
    translateDom(holder);
    return;
  }
  const section = SECTIONS.find((s) => s.id === state.section && canSee(s.id)) || SECTIONS[0];
  if (section.id === "news") { try { localStorage.setItem("seenVersion", CHANGELOG[0][0]); } catch { /* ignore */ } }
  let content;
  if (section.id === "overview") content = renderOverview();
  else if (section.id === "news") content = renderNews();
  else if (section.id === "premium") content = renderPremium();
  else if (section.id === "messages") content = renderMessages();
  else if (section.id === "backup") content = renderBackup();
  else if (section.id === "stats") content = renderStats();
  else if (section.id === "audit") content = renderAudit();
  else if (section.id === "msglog") content = renderMessageLog();
  else {
    content = [h("div", { class: "panel" }, h("h2", {}, `${section.icon} `, section.title),
      section.desc ? h("p", { class: "desc" }, section.desc) : null,
      section.premium && !g.premium.active
        ? h("div", { class: "notice warn" }, "💎 Module Premium : tu peux le préparer, il s'activera avec Premium. ",
            h("a", { href: "#", onclick: (e) => { e.preventDefault(); state.section = "premium"; renderGuild(); } }, "Voir Premium →"))
        : null,
      section.id === "ai" && !g.ai_key && !(g.premium.active && g.premium.ai_ready)
        ? h("div", { class: "notice warn" }, "Pour que l'assistant réponde, branche ton IA ci-dessous (gratuit) ou passe en 💎 Premium pour l'IA incluse.")
        : null,
      section.id === "alerts" && !g.premium.twitch_enabled
        ? h("div", { class: "notice warn" }, "Les alertes Twitch ne sont pas encore activées sur ce bot (le propriétaire doit ajouter les clés Twitch). YouTube fonctionne.")
        : null,
      section.fields.map(field)),
      section.id === "ai" ? renderAiKey() : null,
      section.id === "twitch" ? renderTwitch() : null];
  }

  holder.replaceChildren(...[content].flat(Infinity).filter((c) => c !== null && c !== undefined && c !== false));
  if (state.focusPath) {
    const target = holder.querySelector(`.field[data-path="${CSS.escape(state.focusPath)}"]`);
    state.focusPath = null;
    if (target) {
      target.scrollIntoView({ behavior: "smooth", block: "center" });
      target.classList.add("flash");
      target.querySelector("input, select, textarea")?.focus({ preventScroll: true });
    }
  }
}

async function openGuild(id, section) {
  app.replaceChildren(h("div", { class: "spinner" }));
  try {
    loadGuildData(await api("GET", `/api/guilds/${id}`));
    state.section = section === "premium" ? "premium" : "overview";
    renderGuild();
    // Serveur jamais configuré : l'assistant s'ouvre tout seul (une fois par visite)
    state.wizardShown ||= new Set();
    if (fullAccess() && !state.guild.configured && !state.wizardShown.has(id)) { state.wizardShown.add(id); openWizard(); }
  } catch (e) {
    app.replaceChildren(h("div", { class: "panel center" }, h("p", {}, e.message), h("a", { class: "btn", href: "#/" }, "← Mes serveurs")));
  }
}

document.getElementById("save").addEventListener("click", async (e) => {
  const btn = e.currentTarget;
  btn.disabled = true;
  try {
    loadGuildData(await api("PUT", `/api/guilds/${state.guild.guild.id}/config`, state.cfg));
    renderGuild();
    toast("✅ Configuration enregistrée. Pense à republier les panneaux si tu as modifié règles, notifications ou tickets.");
  } catch (err) { toast(err.message, "err"); }
  btn.disabled = false;
});
// Ctrl+S (ou Cmd+S) : enregistrer
document.addEventListener("keydown", (e) => {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s" && state.guild) {
    e.preventDefault();
    if (savebar.classList.contains("show")) document.getElementById("save").click();
    else toast("Rien à enregistrer.");
  }
});
document.getElementById("reset").addEventListener("click", () => {
  state.cfg = JSON.parse(state.original); markDirty(); renderGuild();
});
document.getElementById("logout").addEventListener("click", async () => {
  await api("POST", "/logout").catch(() => {});
  location.href = "/";
});

// ------------------------------------------------------------------ routeur
async function route() {
  const hash = location.hash || "#/";
  if (hash === "#/login-error") return renderLogin("La connexion a échoué. Réessaie.");
  if (hash === "#/setup-error") return renderLogin("La connexion Discord n'est pas encore configurée sur ce bot (PUBLIC_URL / DISCORD_CLIENT_SECRET).");
  if (!state.me) {
    try { state.me = await api("GET", "/api/me"); } catch { return; }
    document.getElementById("user-chip").hidden = false;
    document.getElementById("user-avatar").src = state.me.user.avatar;
    document.getElementById("user-name").textContent = state.me.user.name;
  }
  const m = hash.match(/^#\/guild\/(\d+)(?:\/(\w+))?/);
  if (m) return openGuild(m[1], m[2]);
  renderGuildList();
}

window.addEventListener("hashchange", () => {
  if (savebar.classList.contains("show") && !confirm("Quitter sans enregistrer tes modifications ?")) return;
  route();
});

fetch("/api/public").then((r) => (r.ok ? r.json() : Promise.reject())).then((info) => {
  state.botInfo = { name: info.name, avatar: info.avatar };
  document.getElementById("bot-name").textContent = info.name;
  updatePreviews();
  if (info.avatar) document.getElementById("bot-avatar").src = info.avatar;
}).catch(() => {});
route();
