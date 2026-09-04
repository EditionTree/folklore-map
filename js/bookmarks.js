// Shared bookmark/archive storage — the single source of truth for
// "folkloreMapBookmarks", the localStorage set that already backs the map's
// star button and My Archive's Saved Legends list (see js/archive.js). Both
// the map (js/map.js) and individual legend pages (legend-page.js) load this
// so saving a legend from either place shows up identically in My Archive.
(function (global) {
  var STORAGE_KEY = 'folkloreMapBookmarks';

  function load() {
    try {
      var stored = JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]');
      return new Set(Array.isArray(stored) ? stored : []);
    } catch (e) {
      return new Set();
    }
  }

  function save(set) {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify([...set]));
    } catch (e) {
      // Bookmark remains available for the current page if storage is blocked.
    }
  }

  function isBookmarked(name) {
    return load().has(name);
  }

  // Returns the new bookmarked state.
  function toggle(name) {
    var set = load();
    var on;
    if (set.has(name)) { set.delete(name); on = false; }
    else { set.add(name); on = true; }
    save(set);
    return on;
  }

  function iconSvg(bookmarked) {
    return '<svg class="bookmark-icon" viewBox="0 0 16 20" aria-hidden="true">'
      + '<path d="M2.5 1.5h11v16l-5.5-3.6-5.5 3.6z"'
      + ' fill="' + (bookmarked ? 'currentColor' : 'none') + '"'
      + ' stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/>'
      + '</svg>';
  }

  function tabSvg(bookmarked) {
    return '<svg class="popup-bookmark-tab" viewBox="0 0 24 34" aria-hidden="true">'
      + '<path d="M1 0.5h22v31l-11-6.8-11 6.8z"'
      + ' fill="' + (bookmarked ? 'var(--accent)' : 'var(--parchment-dk)') + '"'
      + ' stroke="' + (bookmarked ? 'var(--accent)' : 'var(--border)') + '"'
      + ' stroke-width="1.5" stroke-linejoin="round"/>'
      + '</svg>';
  }

  global.FFBookmarks = {
    STORAGE_KEY: STORAGE_KEY,
    load: load,
    save: save,
    isBookmarked: isBookmarked,
    toggle: toggle,
    iconSvg: iconSvg,
    tabSvg: tabSvg
  };
})(window);
