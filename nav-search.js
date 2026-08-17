// Persistent nav-bar search, shared by every page (homepage hero search and
// the map sidebar search have their own richer copies of this same logic).
// Loads legends.json lazily — only once the visitor actually interacts with
// the field — so it costs nothing on the hundreds of pages that never use it.
(function () {
  var CATLABELS = {
    beast: "Beasts", ghost: "Ghosts", water: "Aquatic Legends",
    fairy: "Fae & Spirits", dragon: "Dragons", witch: "Witches",
    deity: "Deities", giant: "Giants", location: "Sacred Sites",
    hero: "Legendary Figures", pirate: "Pirates"
  };
  function catLabel(c) { return CATLABELS[c] || c || ""; }

  function slugify(name) {
    return (name || "")
      .normalize("NFKD").replace(/[̀-ͯ]/g, "")
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "") || "legend";
  }
  function articleLink(name) { return "/legends/" + slugify(name); }

  var root = document.getElementById("navSearch");
  if (!root) return;
  var toggle = document.getElementById("navSearchToggle");
  var input = document.getElementById("navSearchInput");
  var results = document.getElementById("navSearchResults");
  if (!input || !results) return;

  var LEGENDS = null; // null = not fetched yet
  var fetchPromise = null;
  var activeIdx = -1;
  var currentMatches = [];

  function ensureLoaded() {
    if (fetchPromise) return fetchPromise;
    fetchPromise = fetch("/legends.json")
      .then(function (r) { return r.json(); })
      .then(function (data) {
        LEGENDS = data.legends || [];
      })
      .catch(function () { LEGENDS = []; });
    return fetchPromise;
  }

  // Same scoring as the homepage hero search: strongest match per legend,
  // exact name > prefix > name > region > category > tag > summary.
  function scoreLegend(leg, q) {
    var name = (leg.name || "").toLowerCase();
    var region = (leg.region || "").toLowerCase();
    var cat = catLabel(leg.category).toLowerCase();
    var summary = (leg.summary || "").toLowerCase();
    var tags = leg.tags || [];

    var score = 0;
    if (name === q) score = 100;
    else if (name.indexOf(q) === 0) score = 80;
    else if (name.indexOf(q) > -1) score = 60;
    else if (region.indexOf(q) > -1) score = 45;
    else if (cat.indexOf(q) > -1) score = 35;
    else if (tags.some(function (t) { return t.toLowerCase().indexOf(q) > -1; })) score = 30;
    else if (summary.indexOf(q) > -1) score = 15;
    else return null;

    var parts = [];
    if (leg.region) parts.push(leg.region);
    if (catLabel(leg.category)) parts.push(catLabel(leg.category));
    return { score: score, reason: parts.join(" · ") };
  }

  function search(q) {
    var scored = [];
    for (var i = 0; i < LEGENDS.length; i++) {
      var r = scoreLegend(LEGENDS[i], q);
      if (r) scored.push({ leg: LEGENDS[i], score: r.score, reason: r.reason });
    }
    scored.sort(function (a, b) {
      return b.score - a.score || a.leg.name.localeCompare(b.leg.name);
    });
    return scored.slice(0, 8);
  }

  function setExpanded(open) {
    input.setAttribute("aria-expanded", open ? "true" : "false");
    results.classList.toggle("open", open);
    if (!open) input.removeAttribute("aria-activedescendant");
  }

  function renderResults(items) {
    results.innerHTML = "";
    activeIdx = -1;
    currentMatches = items;
    input.removeAttribute("aria-activedescendant");
    if (!items.length) {
      var empty = document.createElement("div");
      empty.className = "nav-search-empty";
      empty.textContent = "No legends found";
      results.appendChild(empty);
      setExpanded(true);
      return;
    }
    items.forEach(function (it, i) {
      var el = document.createElement("div");
      el.className = "nav-search-item";
      el.id = "navSearchResult-" + i;
      el.setAttribute("role", "option");
      el.setAttribute("aria-selected", "false");
      var nm = document.createElement("span");
      nm.className = "nsi-name";
      nm.textContent = it.leg.name;
      var meta = document.createElement("span");
      meta.className = "nsi-meta";
      meta.textContent = it.reason || "";
      el.appendChild(nm);
      el.appendChild(meta);
      el.addEventListener("mousedown", function (e) {
        e.preventDefault();
        goTo(it.leg.name);
      });
      results.appendChild(el);
    });
    setExpanded(true);
  }

  function setActive(idx) {
    var items = results.querySelectorAll(".nav-search-item");
    items.forEach(function (el, i) {
      var on = i === idx;
      el.classList.toggle("active", on);
      el.setAttribute("aria-selected", on ? "true" : "false");
    });
    if (idx >= 0 && items[idx]) {
      input.setAttribute("aria-activedescendant", items[idx].id);
      items[idx].scrollIntoView({ block: "nearest" });
    } else {
      input.removeAttribute("aria-activedescendant");
    }
  }

  function goTo(name) {
    setExpanded(false);
    input.value = "";
    window.location.href = articleLink(name);
  }

  function runQuery() {
    var q = input.value.trim().toLowerCase();
    if (q.length < 2) { setExpanded(false); return; }
    if (!LEGENDS) { ensureLoaded().then(runQuery); return; }
    renderResults(search(q));
  }

  input.addEventListener("focus", ensureLoaded);
  input.addEventListener("input", runQuery);

  input.addEventListener("keydown", function (e) {
    var items = results.querySelectorAll(".nav-search-item");
    if (!items.length) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      activeIdx = Math.min(activeIdx + 1, items.length - 1);
      setActive(activeIdx);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      activeIdx = Math.max(activeIdx - 1, -1);
      setActive(activeIdx);
    } else if (e.key === "Enter") {
      e.preventDefault();
      var pick = activeIdx >= 0 ? currentMatches[activeIdx] : currentMatches[0];
      if (pick) goTo(pick.leg.name);
    } else if (e.key === "Escape") {
      setExpanded(false);
      if (toggle) closeMobile();
    }
  });

  document.addEventListener("click", function (e) {
    if (!e.target.closest("#navSearch")) {
      setExpanded(false);
      if (toggle) closeMobile();
    }
  });

  // Mobile: the toggle button reveals the field as a fixed overlay bar
  // (see nav-search CSS) instead of an inline input in the scrolling nav row.
  function closeMobile() {
    root.classList.remove("open");
    if (toggle) toggle.setAttribute("aria-expanded", "false");
  }
  if (toggle) {
    toggle.addEventListener("click", function () {
      var open = !root.classList.contains("open");
      root.classList.toggle("open", open);
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
      if (open) {
        ensureLoaded();
        setTimeout(function () { input.focus(); }, 0);
      } else {
        setExpanded(false);
      }
    });
  }
})();
