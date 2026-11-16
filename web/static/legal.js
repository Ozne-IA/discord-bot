// Pages légales : version anglaise automatique, nom du bot, contact.
(() => {
  const params = new URLSearchParams(location.search);
  const isEnglishPage = params.get("lang") === "en";
  if (typeof LANG !== "undefined") {
    // Navigateur en anglais → version anglaise. Un lien explicite ?lang=en est toujours respecté.
    if (LANG === "en" && !isEnglishPage) { params.set("lang", "en"); location.replace(`${location.pathname}?${params}`); return; }
  }
  const english = isEnglishPage;
  fetch("/api/public").then((r) => (r.ok ? r.json() : Promise.reject())).then((info) => {
    document.querySelectorAll(".bot-name").forEach((el) => (el.textContent = info.name));
    if (info.avatar) document.querySelectorAll(".bot-avatar").forEach((el) => (el.src = info.avatar));
    document.querySelectorAll(".contact").forEach((el) => {
      el.textContent = "";
      if (info.contact && /^https?:\/\//.test(info.contact)) {
        const a = document.createElement("a");
        a.href = info.contact; a.textContent = info.contact; a.rel = "noopener"; a.target = "_blank";
        el.append(a);
      } else if (info.contact && info.contact.includes("@")) {
        const a = document.createElement("a");
        a.href = "mailto:" + info.contact; a.textContent = info.contact;
        el.append(a);
      } else {
        el.textContent = english
          ? "the bot owner, through the bot's direct messages or its support server"
          : "le propriétaire du bot, via le message privé du bot ou son serveur de support";
      }
    });
  }).catch(() => {});
})();
