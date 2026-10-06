// Theme vor dem ersten Rendern setzen (eigene Datei, damit die CSP ohne Inline-Skripte auskommt).
try {
  var t = localStorage.getItem("sm-theme");
  if (t === "light" || t === "dark") document.documentElement.setAttribute("data-theme", t);
  else if (window.matchMedia && window.matchMedia("(prefers-color-scheme: light)").matches)
    document.documentElement.setAttribute("data-theme", "light");
} catch (e) {}
