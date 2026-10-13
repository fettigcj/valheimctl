// Show UTC timestamps in the viewer's local time, and ask before risky buttons. No libraries.
document.addEventListener("DOMContentLoaded", function () {
  document.querySelectorAll("time[datetime]").forEach(function (t) {
    var raw = t.getAttribute("datetime");
    var d = new Date(raw.replace(" ", "T") + (/[zZ]|[+-]\d\d:?\d\d$/.test(raw) ? "" : "Z"));
    if (!isNaN(d)) { t.title = raw + " (UTC)"; t.textContent = d.toLocaleString(); }
  });
  document.querySelectorAll("button[data-confirm]").forEach(function (b) {
    b.addEventListener("click", function (e) { if (!window.confirm(b.getAttribute("data-confirm"))) { e.preventDefault(); } });
  });
});
