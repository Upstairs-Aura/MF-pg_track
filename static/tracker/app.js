// pg_trac — minimal front-end behavior
// 1) poll who's online, 2) auto-logout after 60 min idle, 3) sortable task table

(function () {
  "use strict";

  /* ---------- who's online (poll every 45s) ---------- */

  function refreshOnlineList() {
    fetch("/api/online/", { headers: { "X-Requested-With": "XMLHttpRequest" } })
      .then(function (res) { return res.ok ? res.json() : null; })
      .then(function (data) {
        if (!data) return;
        var list = document.getElementById("online-list");
        if (!list) return;
        list.innerHTML = data.managers.map(function (m) {
          return '<li class="online-badge" title="' + m.name + '">' + m.initials + "</li>";
        }).join("");
      })
      .catch(function () { /* fail quietly, board keeps showing last known state */ });
  }

  if (document.getElementById("online-list")) {
    refreshOnlineList();
    setInterval(refreshOnlineList, 45000);
  }

  /* ---------- idle auto-logout (60 minutes) ---------- */

  var IDLE_LIMIT_MS = 60 * 60 * 1000;
  var idleTimer = null;

  function resetIdleTimer() {
    if (idleTimer) clearTimeout(idleTimer);
    idleTimer = setTimeout(function () {
      window.location.href = "/logout/?reason=idle";
    }, IDLE_LIMIT_MS);
  }

  ["click", "keydown", "mousemove", "scroll"].forEach(function (evt) {
    document.addEventListener(evt, resetIdleTimer, { passive: true });
  });
  resetIdleTimer();

  /* ---------- sortable task table ---------- */

  var table = document.querySelector("[data-sortable]");
  if (table) {
    var headers = table.querySelectorAll("th[data-sort]");
    headers.forEach(function (th, colIndex) {
      th.addEventListener("click", function () {
        var tbody = table.querySelector("tbody");
        var rows = Array.prototype.slice.call(tbody.querySelectorAll("tr"));
        var asc = th.getAttribute("data-dir") !== "asc";
        headers.forEach(function (h) { h.removeAttribute("data-dir"); });
        th.setAttribute("data-dir", asc ? "asc" : "desc");

        var cellIndex = colIndex + 1; // +1 because first column is the status dot
        rows.sort(function (a, b) {
          var av = a.children[cellIndex].innerText.trim();
          var bv = b.children[cellIndex].innerText.trim();
          return asc ? av.localeCompare(bv) : bv.localeCompare(av);
        });
        rows.forEach(function (r) { tbody.appendChild(r); });
      });
    });
  }
})();
