"use strict";
/* Thème clair / sombre : choix mémorisé, sinon celui de l'appareil. Chargé dans <head> pour éviter un flash. */
(function () {
  let saved = null;
  try { saved = localStorage.getItem("theme"); } catch { /* stockage indisponible */ }
  const prefersLight = window.matchMedia && window.matchMedia("(prefers-color-scheme: light)").matches;
  const theme = saved === "light" || saved === "dark" ? saved : (prefersLight ? "light" : "dark");
  document.documentElement.dataset.theme = theme;

  document.addEventListener("DOMContentLoaded", () => {
    const bar = document.querySelector(".topbar");
    if (!bar) return;
    const btn = document.createElement("button");
    btn.className = "theme-switch";
    const paint = () => {
      const light = document.documentElement.dataset.theme === "light";
      btn.textContent = light ? "🌙" : "☀️";
      btn.title = light ? "Thème sombre" : "Thème clair";
    };
    paint();
    btn.addEventListener("click", () => {
      const next = document.documentElement.dataset.theme === "light" ? "dark" : "light";
      document.documentElement.dataset.theme = next;
      try { localStorage.setItem("theme", next); } catch { /* stockage indisponible */ }
      paint();
    });
    const spacer = bar.querySelector(".spacer");
    if (spacer && spacer.nextSibling) bar.insertBefore(btn, spacer.nextSibling); else bar.append(btn);
  });
})();
