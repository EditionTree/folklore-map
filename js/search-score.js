// Search relevance scoring: the single source of truth for how a query is
// matched against a legend.
//
// This existed in THREE places (js/map.js, js/home.js, nav-search.js) and they
// drifted. By 2026-09-01 the map scored on the controlled `period_slug` while
// the nav search box, which ships on 829 of 831 pages, had no period tier at
// all: searching "stuart" returned 49 legends on the map and nothing anywhere
// else. Same failure mode as the category labels in js/categories.js, and the
// same fix. scripts/search_parity_audit.py now fails the build if a second
// copy of scoreLegend reappears.
//
// Written in ES5 to match nav-search.js, which is the most widely loaded
// consumer and was deliberately kept free of modern syntax.
//
// Loaded with data-cfasync="false" so Cloudflare Rocket Loader cannot reorder
// it after its consumers. See project notes on Rocket Loader before changing
// how this is included.
(function (global) {
  "use strict";

  // Fallback labels only. js/categories.js is canonical and wins whenever it
  // is present; it is not loaded on legend pages, which is why a copy exists
  // here at all. search_parity_audit.py fails if the two disagree.
  var FALLBACK_LABELS = {
    beast: "Beasts",
    ghost: "Ghosts",
    water: "Aquatic Legends",
    fairy: "Fae & Spirits",
    dragon: "Dragons",
    witch: "Witches",
    deity: "Deities",
    giant: "Giants",
    location: "Sacred Sites",
    hero: "Legendary Figures",
    pirate: "Pirates & Smugglers"
  };

  function catLabel(key) {
    var canon = global.FF_CATEGORIES;
    if (canon && canon[key] && canon[key].label) return canon[key].label;
    return FALLBACK_LABELS[key] || key || "";
  }

  // One insertion, deletion or substitution apart. Used to forgive a single
  // typo in a query, never to match short words where one edit changes the
  // meaning entirely.
  function closeMatch(a, b) {
    if (a === b) return true;
    if (Math.abs(a.length - b.length) > 1) return false;
    var i = 0, j = 0, mismatches = 0;
    while (i < a.length && j < b.length) {
      if (a[i] === b[j]) { i++; j++; continue; }
      mismatches++;
      if (mismatches > 1) return false;
      if (a.length > b.length) i++;
      else if (b.length > a.length) j++;
      else { i++; j++; }
    }
    return true;
  }

  function fuzzyWordMatch(query, text) {
    if (!text) return false;
    var words = String(text).toLowerCase().split(/[^a-z0-9]+/);
    for (var i = 0; i < words.length; i++) {
      var w = words[i];
      if (w && w.length >= 4 && query.length >= 4 && closeMatch(query, w)) return true;
    }
    return false;
  }

  function lowerList(arr) {
    var out = [];
    for (var i = 0; i < (arr || []).length; i++) {
      if (arr[i]) out.push(String(arr[i]).toLowerCase());
    }
    return out;
  }

  function anyIncludes(list, q) {
    for (var i = 0; i < list.length; i++) if (list[i].indexOf(q) > -1) return true;
    return false;
  }

  function anyEquals(list, q) {
    for (var i = 0; i < list.length; i++) if (list[i] === q) return true;
    return false;
  }

  /**
   * Score one legend against a lowercased query. 0 means no match.
   *
   * collectionTitles is optional and only the map passes it, because only the
   * map has collection membership loaded. Its absence lowers recall on that
   * one tier rather than changing any other score.
   */
  function score(leg, q, collectionTitles) {
    if (!leg || !q) return 0;
    var name = String(leg.name || "").toLowerCase();
    var label = catLabel(leg.category).toLowerCase();
    var region = String(leg.region || "").toLowerCase();
    var summary = String(leg.summary || "").toLowerCase();
    var tags = lowerList(leg.tags);
    var altNames = lowerList(leg.alt_names);
    var period = String(leg.period || "").toLowerCase();
    // The controlled Explore Through Time period, matched in words rather than
    // as a slug: "stuart-britain" becomes "stuart britain", so a search for
    // "stuart" finds the legends actually SET then. The free-text `period`
    // stays in the same tier deliberately. It mixes setting with when a legend
    // was written down, so it matches things the slug cannot, and dropping it
    // would lose the entries that correctly have no slug at all.
    var periodSlug = String(leg.period_slug || "").toLowerCase().replace(/-/g, " ");
    var tradition = String(leg.cultural_tradition || "").toLowerCase();
    var cols = lowerList(collectionTitles);

    if (name === q) return 100;
    if (anyEquals(altNames, q)) return 95;
    if (name.indexOf(q) === 0) return 90;
    if (name.indexOf(q) > -1) return 80;
    if (anyIncludes(altNames, q)) return 75;
    if (anyEquals(tags, q) || anyIncludes(tags, q)) return 65;
    if (label.indexOf(q) > -1) return 60;
    if (region.indexOf(q) > -1) return 55;
    if (anyIncludes(cols, q)) return 45;
    if (period.indexOf(q) > -1 || periodSlug.indexOf(q) > -1 || tradition.indexOf(q) > -1) return 40;
    if (summary.indexOf(q) > -1) return 25;
    if (fuzzyWordMatch(q, leg.name)) return 20;
    return 0;
  }

  global.FF_SEARCH = {
    score: score,
    catLabel: catLabel,
    closeMatch: closeMatch,
    fuzzyWordMatch: fuzzyWordMatch,
    FALLBACK_LABELS: FALLBACK_LABELS
  };
})(window);
