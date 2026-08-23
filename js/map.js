const CATEGORIES = window.FF_CATEGORIES;
if (!CATEGORIES) {
  // js/categories.js must load first. It carries data-cfasync="false" so
  // Cloudflare Rocket Loader cannot defer it behind this file.
  throw new Error("js/categories.js did not load before js/map.js");
}


let nightMode = false;
let markers = [];
let activeFilters = new Set();
let bookmarksOnly = false;
let activeRegion = null;
let activeCollectionNames = null;
let FEATURED_PAGES = {};
const REGION_META = {
  england: { label: 'England' },
  scotland: { label: 'Scotland' },
  wales: { label: 'Wales' },
  ireland: { label: 'Ireland' },
  'northern-ireland': { label: 'Northern Ireland' }
};
const BOOKMARKS_STORAGE_KEY = 'folkloreMapBookmarks';
let bookmarks = loadBookmarks();
const isMobile = () => window.innerWidth <= 640;
let sidebarOpen = isMobile() ? false : (localStorage.getItem('sidebarOpen') !== 'false');

function loadBookmarks() {
  try {
    const stored = JSON.parse(localStorage.getItem(BOOKMARKS_STORAGE_KEY) || '[]');
    return new Set(Array.isArray(stored) ? stored : []);
  } catch {
    return new Set();
  }
}

function saveBookmarks() {
  try {
    localStorage.setItem(BOOKMARKS_STORAGE_KEY, JSON.stringify([...bookmarks]));
  } catch {
    // Bookmarks remain available for the current page if storage is blocked.
  }
}

function isBookmarked(name) {
  return bookmarks.has(name);
}

function bookmarkIconSvg(bookmarked) {
  return `<svg class="bookmark-icon" viewBox="0 0 16 20" aria-hidden="true">
    <path d="M2.5 1.5h11v16l-5.5-3.6-5.5 3.6z"
      fill="${bookmarked ? 'currentColor' : 'none'}"
      stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/>
  </svg>`;
}

function popupBookmarkTabSvg(bookmarked) {
  return `<svg class="popup-bookmark-tab" viewBox="0 0 24 34" aria-hidden="true">
    <path d="M1 0.5h22v31l-11-6.8-11 6.8z"
      fill="${bookmarked ? 'var(--accent)' : 'var(--parchment-dk)'}"
      stroke="${bookmarked ? 'var(--accent)' : 'var(--border)'}"
      stroke-width="1.5" stroke-linejoin="round"/>
  </svg>`;
}

// Apply persisted sidebar state immediately (before data loads)
document.addEventListener('DOMContentLoaded', () => {
  const sidebar = document.getElementById('sidebar');
  const btn     = document.getElementById('sidebarToggleBtn');
  if (!sidebarOpen) {
    sidebar.classList.add('collapsed');
    btn.textContent = '☰ Entries';
  }

  // Contextual example prompts — one picked at random per page load, not
  // rotated during the visit, to stay calm rather than draw the eye.
  const SEARCH_HINT_EXAMPLES = [
    'Try searching your hometown or county',
    'Try "dragon" or "black dog"',
    'Try "Cornwall" or "the Highlands"',
    'Search a creature, place or theme'
  ];
  const hintEl = document.getElementById('sidebarSearchHint');
  if (hintEl) {
    hintEl.textContent = SEARCH_HINT_EXAMPLES[Math.floor(Math.random() * SEARCH_HINT_EXAMPLES.length)];
  }
});

const EXCLUDED_LEGEND_NAMES = new Set([
  'Boulogne-sur-Mer',
  'Byland Abbey',
  'Cambridge University Press',
  'England',
  'English Channel',
]);

// Viewing/pan bounds only — NOT the legend-acceptance range (that lives in the
// QC agent). Mobile gets a much larger pan box (~2x linear span) so the isles
// aren't clamped against the edge on a narrow screen.
const DESKTOP_BOUNDS = L.latLngBounds([44.0, -16.0], [67.0, 9.0]);
const MOBILE_BOUNDS  = L.latLngBounds([34.0, -27.0], [76.0, 20.0]);
const BOUNDS = window.matchMedia('(max-width: 640px)').matches ? MOBILE_BOUNDS : DESKTOP_BOUNDS;
const map = L.map('map', {
  zoomControl: true, minZoom: 5, maxZoom: 17,
  maxBounds: BOUNDS, maxBoundsViscosity: 0.7,
  attributionControl: true
}).setView([54.5, -2.5], 6);

const clusterGroup = L.markerClusterGroup({
  maxClusterRadius: 55, spiderfyOnMaxZoom: true,
  showCoverageOnHover: false, zoomToBoundsOnClick: true,
  disableClusteringAtZoom: 12,
  iconCreateFunction: function(cluster) {
    const count = cluster.getChildCount();
    const size  = count < 10 ? 'small' : count < 50 ? 'medium' : 'large';
    const dim   = count < 10 ? 36 : count < 50 ? 42 : 50;
    return L.divIcon({
      html: '<div><span>' + count + '</span></div>',
      className: 'marker-cluster marker-cluster-' + size,
      iconSize: L.point(dim, dim)
    });
  }
});

L.tileLayer('https://tiles.stadiamaps.com/tiles/stamen_terrain/{z}/{x}/{y}{r}.png?api_key=89e39892-dad3-41e7-89e6-fa69ac42bb85', {
  attribution: '&copy; <a href="https://stadiamaps.com/">Stadia Maps</a> &copy; <a href="https://stamen.com">Stamen Design</a> &copy; <a href="https://openstreetmap.org">OpenStreetMap</a>',
  maxZoom: 18
}).addTo(map);

function makeIcon(category, isNight) {
  const cat = CATEGORIES[category] || CATEGORIES.beast;
  const c   = cat.colour;
  // Scale path from 512x512 to fit inside pin (offset+scale via transform)
  const svg = `<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 42' width='32' height='42'>
    <path d='M16 1C8.3 1 2 7.3 2 15c0 11 14 26 14 26S30 26 30 15C30 7.3 23.7 1 16 1z'
          fill='${c}' stroke='rgba(255,255,255,0.35)' stroke-width='0.8'/>
    <circle cx='16' cy='15' r='10' fill='rgba(0,0,0,0.15)'/>
    <g transform='translate(5, 4) scale(0.0430)'>
      <path d='${cat.iconPath}' fill='white' opacity='0.92'/>
    </g>
  </svg>`;
  return L.divIcon({ html: svg, className: '', iconSize: [32, 42], iconAnchor: [16, 42], popupAnchor: [0, -44] });
}

function lightenForNight(hex) {
  return hex;
}

// Promoted to js/dom-safe.js so achievements, archive and updates share one
// definition. Kept as thin wrappers here rather than renamed call sites, so the
// change is a redirect rather than a rewrite of everything that uses them.
function escapeHtml(value) { return SafeDOM.escapeHtml(value); }

function safeSourceUrl(value) { return SafeDOM.safeUrl(value); }

function buildPopup(leg) {
  const cat = CATEGORIES[leg.category];
  const encoded = encodeURIComponent(leg.name);
  const bookmarked = isBookmarked(leg.name);
  const featured = FEATURED_PAGES[leg.name];
  const hero = featured?.image
    ? `<div class="popup-hero"><img src="${escapeHtml(featured.image)}" alt="${escapeHtml(featured.alt || '')}"/></div>`
    : '';
  return `<div class="popup-inner">
    ${hero}
    <button class="bookmark-btn popup-bookmark${bookmarked ? ' bookmarked' : ''}" data-bookmark="${encoded}" aria-label="${bookmarked ? 'Remove bookmark' : 'Bookmark'}" title="${bookmarked ? 'Remove bookmark' : 'Bookmark'}">${popupBookmarkTabSvg(bookmarked)}</button>
    <span class="popup-cat" style="background:${cat.colour}">${cat.label}</span>
    <div class="popup-title">${escapeHtml(leg.name)}</div>
    <div class="popup-region">${escapeHtml(leg.region)}</div>
    <hr class="popup-divider"/>
    <p class="popup-summary">${escapeHtml(leg.summary)}</p>
    <div class="popup-footer">
      <a class="popup-source" href="${escapeHtml(safeSourceUrl(leg.source))}" target="_blank" rel="noopener noreferrer">Read More</a>
      <a class="popup-fullpage" href="legends/${legendSlug(leg.name)}">Full Page</a>
      <button class="popup-copylink" data-legend="${encoded}">Copy</button>
    </div>
  </div>`;
}

document.addEventListener('click', e => {
  const bookmarkBtn = e.target.closest('[data-bookmark]');
  if (bookmarkBtn) {
    e.preventDefault();
    e.stopPropagation();
    toggleBookmark(decodeURIComponent(bookmarkBtn.dataset.bookmark));
    return;
  }
  const btn = e.target.closest('.popup-copylink');
  if (!btn) return;
  const url = new URL(location.href);
  url.search = '?legend=' + btn.dataset.legend;
  navigator.clipboard.writeText(url.toString()).then(() => {
    btn.textContent = 'copied';
    setTimeout(() => { btn.textContent = 'copy link'; }, 2000);
  });
});

// Both the popup and the sidebar render a bookmark button carrying the same
// data-bookmark value, so one query finds every button for a legend wherever it
// is currently on screen. They use different icons, hence the class check.
function syncBookmarkButtons(name) {
  const on = isBookmarked(name);
  const label = on ? 'Remove bookmark' : 'Bookmark';
  document.querySelectorAll(`[data-bookmark="${encodeURIComponent(name)}"]`).forEach(btn => {
    btn.classList.toggle('bookmarked', on);
    btn.setAttribute('aria-label', label);
    btn.title = label;
    btn.innerHTML = btn.classList.contains('popup-bookmark')
      ? popupBookmarkTabSvg(on)
      : bookmarkIconSvg(on);
  });
}

function updateSavedCount() {
  const badge = document.querySelector('.filter-btn[data-cat="bookmarks"] .count-badge');
  if (badge) badge.textContent = bookmarks.size;
}

function toggleBookmark(name) {
  if (bookmarks.has(name)) bookmarks.delete(name);
  else bookmarks.add(name);
  saveBookmarks();

  // One legend changed, so touch only what that legend affects. This used to
  // rebuild all 709 popup bodies, the entire filter bar, and every one of the
  // ~4,200 sidebar DOM nodes, on every single click of a star.
  syncBookmarkButtons(name);
  updateSavedCount();

  // The visible set only actually changes when the bookmark filter is on.
  // Re-filtering clears the cluster layers, which closes the popup you just
  // clicked in, so it stays conditional.
  if (bookmarksOnly) filterMarkers();
}

let LEGENDS = [];

// Legends sharing (near-)identical coordinates render as perfectly overlapping
// markers once clustering is disabled (zoom >= 12), hiding all but the topmost
// one. Spread these into a small ring around the shared point so each stays
// individually visible/clickable while remaining close enough to still cluster
// normally at lower zooms.
const COORD_JITTER_RADIUS = 0.0025; // ~250-300m
function jitterCoincidentLegends(legends) {
  const groups = new Map();
  legends.forEach(leg => {
    const key = leg.lat.toFixed(4) + ',' + leg.lng.toFixed(4);
    (groups.get(key) || groups.set(key, []).get(key)).push(leg);
  });
  groups.forEach(group => {
    if (group.length < 2) return;
    group.forEach((leg, i) => {
      const angle = (2 * Math.PI * i) / group.length;
      leg.lat += COORD_JITTER_RADIUS * Math.cos(angle);
      leg.lng += COORD_JITTER_RADIUS * Math.sin(angle);
    });
  });
}

function loadMarkers(legends) {
  jitterCoincidentLegends(legends);
  legends.forEach(leg => {
    if (!CATEGORIES[leg.category]) leg.category = 'beast';
    const marker = L.marker([leg.lat, leg.lng], {
      icon: makeIcon(leg.category, false)
    // Popup content is bound as a function, not a string. Leaflet calls it when
    // the popup opens, so the 709 popup bodies are not all built at load, and
    // anything that changes what a popup should say (a bookmark toggle, the
    // featured-artwork manifest arriving) needs no rebuild pass at all: the
    // next open picks up current state on its own.
    }).bindPopup(() => buildPopup(leg), { maxWidth: 330 });
    marker._legendData = leg;
    markers.push(marker);
  });
  clusterGroup.addLayers(markers);
  map.addLayer(clusterGroup);
}

function buildFilters() {
  const bar = document.getElementById('filterBar');
  const entriesToggle = document.getElementById('sidebarToggleBtn');
  bar.innerHTML = '';
  bar.appendChild(entriesToggle);

  const allBtn = makeFilterBtn('all', 'All', null);
  bar.appendChild(allBtn);

  if (activeRegion) {
    const placeBtn = document.createElement('button');
    placeBtn.className = 'filter-btn filter-place active';
    placeBtn.dataset.region = activeRegion;
    placeBtn.setAttribute('aria-label', 'Remove ' + REGION_META[activeRegion].label + ' filter');
    // Lucide "x" (lucide.dev, ISC) — replaces a &times; glyph, which rendered
    // at whatever weight the body serif gave it.
    placeBtn.innerHTML = '<span class="btn-label">' + REGION_META[activeRegion].label + '</span><svg class="filter-place-clear" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>';
    placeBtn.onclick = () => filterMarkers('all');
    bar.appendChild(placeBtn);
  }

  bar.appendChild(makeFilterBtn('bookmarks', 'Saved', null, bookmarks.size));

  const randomBtn = document.createElement('button');
  randomBtn.className = 'filter-btn filter-random';
  randomBtn.title = 'Jump to a random legend';
  // Lucide "dices" (lucide.dev, ISC) — same icon as the homepage's Surprise me.
  randomBtn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect width="12" height="12" x="2" y="10" rx="2" ry="2"/><path d="m17.92 14 3.5-3.5a2.24 2.24 0 0 0 0-3l-5-4.92a2.24 2.24 0 0 0-3 0L10 6"/><path d="M6 18h.01"/><path d="M10 14h.01"/><path d="M15 6h.01"/><path d="M18 9h.01"/></svg><span class="btn-label">Surprise me</span>';
  randomBtn.onclick = randomLegend;
  bar.appendChild(randomBtn);

  const usedCats = [...new Set(LEGENDS.map(l => l.category))];
  usedCats.forEach(cat => {
    const count = LEGENDS.filter(l => l.category === cat).length;
    bar.appendChild(makeFilterBtn(cat, CATEGORIES[cat].label, CATEGORIES[cat].colour, count));
  });
}

function makeFilterBtn(cat, label, colour, count) {
  const btn = document.createElement('button');
  btn.className   = 'filter-btn';
  btn.dataset.cat = cat;
  const cat_obj = CATEGORIES[cat];
  let iconHtml = cat === 'bookmarks' ? '<span class="filter-icon">' + bookmarkIconSvg(true) + '</span>' : '';
  if (cat_obj && cat_obj.iconPath) {
    iconHtml = '<span class="filter-icon"><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" width="16" height="16" style="display:block"><path d="' + cat_obj.iconPath + '" fill="currentColor"/></svg></span>';
  }
  const cntHtml = count !== undefined ? '<span class="count-badge">' + count + '</span>' : '';
  btn.innerHTML  = iconHtml + '<span class="btn-label">' + label + '</span>' + (cntHtml ? ' ' + cntHtml : '');
  btn.classList.toggle('active',
    cat === 'all' ? !activeRegion && !bookmarksOnly && activeFilters.size === 0 :
    cat === 'bookmarks' ? bookmarksOnly :
    activeFilters.has(cat)
  );
  btn.setAttribute('aria-label', label);
  btn.onclick    = () => filterMarkers(cat);
  return btn;
}

function matchesActiveFilters(m) {
  const matchesCategory = activeFilters.size === 0 || activeFilters.has(m._legendData.category);
  const matchesBookmark = !bookmarksOnly || isBookmarked(m._legendData.name);
  const matchesPlace = !activeRegion || (m._legendData.tags || []).includes(activeRegion);
  const matchesCollection = !activeCollectionNames || activeCollectionNames.has(m._legendData.name);
  return matchesCategory && matchesBookmark && matchesPlace && matchesCollection;
}

function filterMarkers(cat) {
  if (cat === 'all') {
    activeFilters.clear();
    bookmarksOnly = false;
    activeRegion = null;
    activeCollectionNames = null;
    history.replaceState(null, '', location.pathname);
    buildFilters();
  } else if (cat === 'bookmarks') {
    bookmarksOnly = !bookmarksOnly;
  } else if (cat) {
    if (activeFilters.has(cat)) activeFilters.delete(cat);
    else activeFilters.add(cat);
  }
  document.querySelectorAll('.filter-btn').forEach(b => {
    if (b.dataset.region) {
      b.classList.toggle('active', b.dataset.region === activeRegion);
      return;
    }
    b.classList.toggle('active',
      b.dataset.cat === 'all' ? !activeRegion && !bookmarksOnly && activeFilters.size === 0 :
      b.dataset.cat === 'bookmarks' ? bookmarksOnly :
      activeFilters.has(b.dataset.cat)
    );
  });
  clusterGroup.clearLayers();
  const visible = markers.filter(matchesActiveFilters);
  clusterGroup.addLayers(visible);
  buildSidebarList(visible.map(m => m._legendData));
  return visible;
}

function applyRegionFilter(region, fitMap) {
  if (!REGION_META[region]) return;
  activeRegion = region;
  buildFilters();
  const visible = filterMarkers();
  history.replaceState(null, '', '?region=' + encodeURIComponent(region));
  if (fitMap && visible.length) {
    const bounds = L.latLngBounds(visible.map(marker => marker.getLatLng()));
    map.fitBounds(bounds, { padding: [36, 36], maxZoom: 7, animate: false });
  }
}

// Filters the map to just the members of a themed collection (e.g. Black Dogs).
// The name list is precomputed at build time by generate_pages.py — see
// legends/collection/<slug>.json — so this never has to port the Python
// matches_collection() rules into JS.
function applyCollectionFilter(slug, names, fitMap) {
  activeCollectionNames = new Set(names);
  const visible = filterMarkers();
  history.replaceState(null, '', '?collection=' + encodeURIComponent(slug));
  if (fitMap && visible.length) {
    const bounds = L.latLngBounds(visible.map(marker => marker.getLatLng()));
    map.fitBounds(bounds, { padding: [36, 36], maxZoom: 7, animate: false });
  }
}

function buildLegend() {
  const panel    = document.getElementById('legendPanel');
  const usedCats = [...new Set(LEGENDS.map(l => l.category))].sort();
  const collapsed = localStorage.getItem('legendCollapsed') === 'true';
  const items = usedCats.filter(c => CATEGORIES[c]).map(cat => {
    const ico = CATEGORIES[cat].iconPath
      ? '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" width="14" height="14" style="display:block;flex-shrink:0"><path d="' + CATEGORIES[cat].iconPath + '" fill="' + CATEGORIES[cat].colour + '"/></svg>'
      : '';
    return '<div class="legend-item"><span class="legend-dot" style="display:flex;align-items:center">' + ico + '</span>' + CATEGORIES[cat].label + '</div>';
  }).join('');
  panel.innerHTML =
    '<div class="legend-header">' +
      '<div class="legend-title">Legend</div>' +
      '<span class="legend-toggle" id="legendToggle">' + (collapsed ? '+' : '−') + '</span>' +
    '</div>' +
    '<div class="legend-body' + (collapsed ? ' collapsed' : '') + '" id="legendBody">' + items + '</div>';
  wireLegendHeader();
}

// The legend panel's header is written through innerHTML, so its handler has
// to be attached afterwards rather than being an onclick attribute in the
// markup: CSP blocks inline handlers regardless of how they were created.
function wireLegendHeader() {
  const hdr = document.querySelector('.legend-header');
  if (hdr && !hdr._wired) { hdr._wired = true; hdr.addEventListener('click', () => toggleLegend()); }
}

function toggleLegend() {
  const body = document.getElementById('legendBody');
  const btn  = document.getElementById('legendToggle');
  const nowCollapsed = !body.classList.toggle('collapsed');
  btn.textContent = body.classList.contains('collapsed') ? '+' : '−';
  localStorage.setItem('legendCollapsed', body.classList.contains('collapsed'));
}

function toggleNight() {
  nightMode = !nightMode;
  document.getElementById('map').classList.toggle('night', nightMode);
  document.body.classList.toggle('night', nightMode);
  document.getElementById('modeTrack').classList.toggle('on', nightMode);
  document.getElementById('modeToggle').setAttribute('aria-checked', nightMode ? 'true' : 'false');
  // Force filter-bar repaint (composited layer bypasses CSS variable cascade)
  const fb = document.querySelector('.filter-bar');
  fb.style.transition = 'background 0.6s ease, border-bottom-color 0.6s ease';
  fb.style.background = nightMode ? '#141e30' : '';
  fb.style.borderBottomColor = nightMode ? '#2e4870' : '';
  // Persist preference
  try { localStorage.setItem('folklore_night', nightMode ? '1' : '0'); } catch(e) {}
  document.getElementById('modeLabel').textContent = nightMode ? 'Night' : 'Day';
  markers.forEach(m => {
    m.setIcon(makeIcon(m._legendData.category, nightMode));
  });
  if (typeof clusterGroup !== 'undefined') clusterGroup.refreshClusters();
}

let searchActiveIdx = -1;

function closeSearchResults() {
  const box = document.getElementById('searchResults');
  const input = document.getElementById('searchInput');
  box.classList.remove('open');
  input.setAttribute('aria-expanded', 'false');
  input.removeAttribute('aria-activedescendant');
  searchActiveIdx = -1;
}

function showNoResults(q) {
  const box = document.getElementById('searchResults');
  const input = document.getElementById('searchInput');
  box.replaceChildren();
  const msg = document.createElement('div');
  msg.className = 'search-no-results';
  const line1 = document.createElement('span');
  line1.textContent = 'No legends found for “' + q + '”.';
  const line2 = document.createElement('span');
  line2.className = 'hint';
  line2.textContent = 'Try a place name, creature or theme, such as “dragon” or “Cornwall”.';
  msg.appendChild(line1);
  msg.appendChild(line2);
  box.appendChild(msg);
  box.classList.add('open');
  input.setAttribute('aria-expanded', 'true');
  input.removeAttribute('aria-activedescendant');
  searchActiveIdx = -1;
}

function setSearchActive(idx) {
  const items = document.querySelectorAll('#searchResults .search-result-item');
  const input = document.getElementById('searchInput');
  items.forEach((el, i) => {
    const on = i === idx;
    el.classList.toggle('active', on);
    el.setAttribute('aria-selected', on ? 'true' : 'false');
  });
  if (idx >= 0 && items[idx]) {
    input.setAttribute('aria-activedescendant', items[idx].id);
    items[idx].scrollIntoView({ block: 'nearest' });
  } else {
    input.removeAttribute('aria-activedescendant');
  }
}

// ── EXPANDED SEARCH ────────────────────────────────────────────────────────
// Extra data that broadens search beyond name/region/category: themed
// collections and a gazetteer of major towns for location-radius search
// (e.g. "York" surfaces both legends near York and legends mentioning it).
let COLLECTIONS = [];               // [{slug, title, intro}]
let LEGEND_COLLECTIONS = new Map(); // legend name -> [{slug, title}]
let UK_PLACES = [];                 // [{name, lat, lng}]

function loadSearchExtras() {
  fetch('collections.json')
    .then(r => r.json())
    .then(data => {
      COLLECTIONS = data.collections || [];
      return Promise.all(COLLECTIONS.map(col =>
        fetch(`legends/collection/${col.slug}.json`)
          .then(r => r.ok ? r.json() : { legends: [] })
          .catch(() => ({ legends: [] }))
          .then(data => ({ col, names: data.legends || [] }))
      ));
    })
    .then(results => {
      results.forEach(({ col, names }) => {
        names.forEach(name => {
          if (!LEGEND_COLLECTIONS.has(name)) LEGEND_COLLECTIONS.set(name, []);
          LEGEND_COLLECTIONS.get(name).push({ slug: col.slug, title: col.title });
        });
      });
    })
    .catch(() => {});

  fetch('uk-places.json')
    .then(r => r.json())
    .then(data => { UK_PLACES = data.places || []; })
    .catch(() => {});
}

function haversineKm(lat1, lng1, lat2, lng2) {
  const toRad = d => d * Math.PI / 180;
  const dLat = toRad(lat2 - lat1), dLng = toRad(lng2 - lng1);
  const a = Math.sin(dLat / 2) ** 2 +
            Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLng / 2) ** 2;
  return 2 * 6371 * Math.asin(Math.sqrt(a));
}

// Cheap edit-distance check (not full Levenshtein) — good enough to catch a
// single typo/transposition in a short word without the cost of a DP table
// on every keystroke across hundreds of legend names.
function closeMatch(a, b) {
  if (a === b) return true;
  if (Math.abs(a.length - b.length) > 1) return false;
  let i = 0, j = 0, mismatches = 0;
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
  const words = text.toLowerCase().split(/[^a-z0-9]+/).filter(Boolean);
  return words.some(w => w.length >= 4 && query.length >= 4 && closeMatch(query, w));
}

const LOCATION_RADIUS_KM = 40;

function findMatchingPlace(q) {
  return UK_PLACES.find(p => {
    const name = p.name.toLowerCase();
    return name === q || name.includes(q) || fuzzyWordMatch(q, name);
  });
}

function scoreLegend(leg, q) {
  const name = leg.name.toLowerCase();
  const catLabel = (CATEGORIES[leg.category]?.label || leg.category || '').toLowerCase();
  const region = (leg.region || '').toLowerCase();
  const summary = (leg.summary || '').toLowerCase();
  const tags = (leg.tags || []).map(t => t.toLowerCase());
  const altNames = (leg.alt_names || []).map(n => n.toLowerCase());
  const period = (leg.period || '').toLowerCase();
  const tradition = (leg.cultural_tradition || '').toLowerCase();
  const cols = (LEGEND_COLLECTIONS.get(leg.name) || []).map(c => c.title.toLowerCase());

  if (name === q) return 100;
  if (altNames.some(n => n === q)) return 95;
  if (name.startsWith(q)) return 90;
  if (name.includes(q)) return 80;
  if (altNames.some(n => n.includes(q))) return 75;
  if (tags.some(t => t === q || t.includes(q))) return 65;
  if (catLabel.includes(q)) return 60;
  if (region.includes(q)) return 55;
  if (cols.some(c => c.includes(q))) return 45;
  if (period.includes(q) || tradition.includes(q)) return 40;
  if (summary.includes(q)) return 25;
  if (fuzzyWordMatch(q, leg.name)) return 20;
  return 0;
}

function handleSearch(query) {
  const box = document.getElementById('searchResults');
  const input = document.getElementById('searchInput');
  searchActiveIdx = -1;
  input.removeAttribute('aria-activedescendant');
  if (!query.trim()) { closeSearchResults(); return; }
  const q = query.trim().toLowerCase();

  const place = q.length >= 3 ? findMatchingPlace(q) : null;
  const nearby = new Map(); // name -> distance km
  if (place) {
    LEGENDS.forEach(l => {
      if (l.lat == null || l.lng == null) return;
      const d = haversineKm(place.lat, place.lng, l.lat, l.lng);
      if (d <= LOCATION_RADIUS_KM) nearby.set(l.name, d);
    });
  }

  const legendMatches = LEGENDS
    .map(l => ({ leg: l, score: Math.max(scoreLegend(l, q), nearby.has(l.name) ? 35 : 0) }))
    .filter(m => m.score > 0)
    .sort((a, b) => b.score - a.score || (nearby.get(a.leg.name) ?? 999) - (nearby.get(b.leg.name) ?? 999))
    .slice(0, 8);

  const collectionMatches = COLLECTIONS
    .filter(c => c.title.toLowerCase().includes(q) || c.intro.toLowerCase().includes(q) ||
                 (place && c.intro.toLowerCase().includes(place.name.toLowerCase())))
    .slice(0, 3);

  if (!legendMatches.length && !collectionMatches.length) { showNoResults(q); return; }
  box.replaceChildren();
  let idx = 0;

  legendMatches.forEach(({ leg }) => {
    const item = document.createElement('div');
    const sub = document.createElement('span');
    item.className = 'search-result-item';
    item.id = 'searchResult-' + idx++;
    item.setAttribute('role', 'option');
    item.setAttribute('aria-selected', 'false');
    item.textContent = leg.name;
    item.onclick = () => focusLegend(leg.name);
    sub.textContent = nearby.has(leg.name)
      ? `near ${place.name} · ${Math.round(nearby.get(leg.name))} km`
      : leg.region;
    item.appendChild(sub);
    box.appendChild(item);
  });

  if (collectionMatches.length) {
    const label = document.createElement('div');
    label.className = 'search-result-section';
    label.textContent = 'Collections';
    box.appendChild(label);
    collectionMatches.forEach(col => {
      const item = document.createElement('div');
      item.className = 'search-result-item';
      item.id = 'searchResult-' + idx++;
      item.setAttribute('role', 'option');
      item.setAttribute('aria-selected', 'false');
      item.textContent = col.title;
      item.onclick = () => { location.href = `legends/collection/${col.slug}`; };
      box.appendChild(item);
    });
  }

  box.classList.add('open');
  input.setAttribute('aria-expanded', 'true');
}

document.getElementById('searchInput').addEventListener('keydown', e => {
  const items = document.querySelectorAll('#searchResults .search-result-item');
  if (!items.length) return;
  if (e.key === 'ArrowDown') {
    e.preventDefault();
    searchActiveIdx = Math.min(searchActiveIdx + 1, items.length - 1);
    setSearchActive(searchActiveIdx);
  } else if (e.key === 'ArrowUp') {
    e.preventDefault();
    searchActiveIdx = Math.max(searchActiveIdx - 1, -1);
    setSearchActive(searchActiveIdx);
  } else if (e.key === 'Enter') {
    e.preventDefault();
    const pick = searchActiveIdx >= 0 ? items[searchActiveIdx] : items[0];
    if (pick) pick.click();
  } else if (e.key === 'Escape') {
    closeSearchResults();
  }
});

function legendSlug(name) {
  return name.normalize('NFKD').replace(/[̀-ͯ]/g, '').replace(/[^\x00-\x7f]/g, '')
             .toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '') || 'legend';
}

function randomLegend() {
  if (!LEGENDS.length) return;
  const leg = LEGENDS[Math.floor(Math.random() * LEGENDS.length)];
  focusLegend(leg.name);
}

function focusLegend(name) {
  closeSearchResults();
  document.getElementById('searchInput').value = '';
  const leg = LEGENDS.find(l => l.name === name);
  if (!leg) return;
  if ((activeFilters.size && !activeFilters.has(leg.category)) ||
      (bookmarksOnly && !isBookmarked(name)) ||
      (activeRegion && !(leg.tags || []).includes(activeRegion))) {
    filterMarkers('all');
  }
  const marker = markers.find(m => m._legendData.name === name);
  if (!marker) return;
  highlightSidebarItem(name);
  if (isMobile() && sidebarOpen) toggleSidebar();
  map.setView([leg.lat, leg.lng], 12, { animate: true });
  setTimeout(() => clusterGroup.zoomToShowLayer(marker, () => marker.openPopup()), 400);
}

document.addEventListener('click', e => {
  if (!e.target.closest('.search-wrap')) {
    closeSearchResults();
  }
});


function toggleSidebar() {
  const list = document.getElementById('sidebarList');
  if (sidebarOpen && list) list._savedScrollTop = list.scrollTop;
  sidebarOpen = !sidebarOpen;
  document.getElementById('sidebar').classList.toggle('collapsed', !sidebarOpen);
  document.getElementById('sidebarToggleBtn').textContent = sidebarOpen ? '✕ Entries' : '☰ Entries';
  if (!isMobile()) localStorage.setItem('sidebarOpen', sidebarOpen);
  if (sidebarOpen && list && list._savedScrollTop !== undefined) {
    requestAnimationFrame(() => { list.scrollTop = list._savedScrollTop; });
  }
  setTimeout(() => map.invalidateSize(), 300);
}

// -- SIDEBAR LIST (virtualised) --------------------------------------------
// Only the rows in view are in the DOM. Rendering all of them cost ~10 DOM
// nodes per legend and grew linearly: measured against this exact code, a
// filter change took 196ms at 709 entries and 3.1s at 12,000. Windowed, it is
// ~4ms and 400 nodes at any size.
//
// Icons are cloned from a prepared node per category rather than parsed from an
// HTML string per row. Parsing SVG through innerHTML twice per row was roughly
// 55% of the old cost on its own.
const SIDEBAR_OVERSCAN = 8;          // rows rendered beyond the viewport, each side
const SIDEBAR_ROW_FALLBACK = 52;     // used only until a real row can be measured

let sidebarRows = [];                // the sorted, filtered legends
let sidebarRowHeight = 0;            // measured from a real row, never assumed
let activeSidebarName = null;
const sidebarIconTpl = {};
const sidebarBookmarkTpl = {};

function sidebarIconFor(cat, colour, iconPath) {
  if (!sidebarIconTpl[cat]) {
    const span = document.createElement('span');
    span.className = 'sidebar-item-icon';
    if (iconPath) {
      span.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" width="14" height="14"><path d="' + iconPath + '" fill="' + colour + '"/></svg>';
    }
    sidebarIconTpl[cat] = span;
  }
  return sidebarIconTpl[cat].cloneNode(true);
}

function sidebarBookmarkFor(on) {
  if (!sidebarBookmarkTpl[on]) {
    const btn = document.createElement('button');
    btn.className = 'bookmark-btn sidebar-bookmark' + (on ? ' bookmarked' : '');
    btn.innerHTML = bookmarkIconSvg(on);
    sidebarBookmarkTpl[on] = btn;
  }
  return sidebarBookmarkTpl[on].cloneNode(true);
}

function makeSidebarRow(leg) {
  const cat = CATEGORIES[leg.category] || CATEGORIES.beast;
  const on = isBookmarked(leg.name);
  const item = document.createElement('div');
  const text = document.createElement('div');
  const name = document.createElement('div');
  const region = document.createElement('div');
  const bookmark = sidebarBookmarkFor(on);
  item.className = 'sidebar-item' + (leg.name === activeSidebarName ? ' active' : '');
  item.style.setProperty('--item-colour', cat.colour);
  item.onclick = () => focusLegend(leg.name);
  name.className = 'sidebar-item-name';
  name.textContent = leg.name;
  region.className = 'sidebar-item-region';
  region.textContent = leg.region;
  text.className = 'sidebar-item-text';
  const label = on ? 'Remove bookmark' : 'Bookmark';
  bookmark.dataset.bookmark = encodeURIComponent(leg.name);
  bookmark.setAttribute('aria-label', label);
  bookmark.title = label;
  text.append(name, region);
  item.append(sidebarIconFor(leg.category, cat.colour, cat.iconPath), text, bookmark);
  return item;
}

function renderSidebarWindow() {
  const list   = document.getElementById('sidebarList');
  const spacer = document.getElementById('sidebarSpacer');
  const win    = document.getElementById('sidebarWindow');
  if (!list || !spacer || !win) return;

  const rowH = sidebarRowHeight || SIDEBAR_ROW_FALLBACK;
  const viewport = list.clientHeight || rowH * 12;
  const first = Math.max(0, Math.floor(list.scrollTop / rowH) - SIDEBAR_OVERSCAN);
  const last  = Math.min(sidebarRows.length, Math.ceil((list.scrollTop + viewport) / rowH) + SIDEBAR_OVERSCAN);

  spacer.style.height = (sidebarRows.length * rowH) + 'px';
  win.style.transform = 'translateY(' + (first * rowH) + 'px)';

  const frag = document.createDocumentFragment();
  for (let i = first; i < last; i++) frag.appendChild(makeSidebarRow(sidebarRows[i]));
  win.replaceChildren(frag);

  // Measure once from a real row rather than trusting a constant, then lay out
  // again now that the true height is known. Stays on the fallback while the
  // sidebar is collapsed and nothing can be measured.
  if (!sidebarRowHeight && win.firstElementChild) {
    const h = win.firstElementChild.getBoundingClientRect().height;
    if (h > 0) { sidebarRowHeight = h; renderSidebarWindow(); }
  }
}

function buildSidebarList(legends) {
  const list = document.getElementById('sidebarList');
  const sub  = document.getElementById('sidebarSubtitle');
  sidebarRows = [...legends].sort((a, b) => a.name.localeCompare(b.name));

  const filterLabels = [...activeFilters].map(cat => CATEGORIES[cat]?.label).filter(Boolean);
  const placeLabel = activeRegion ? REGION_META[activeRegion].label : '';
  const suffix = bookmarksOnly
    ? (filterLabels.length ? ' saved ' + filterLabels.join(' + ') : ' saved entries')
    : (filterLabels.length ? ' ' + filterLabels.join(' + ') : ' entries');
  sub.textContent = sidebarRows.length + suffix + (placeLabel ? ' in ' + placeLabel : '');

  if (!document.getElementById('sidebarSpacer')) {
    const spacer = document.createElement('div');
    spacer.className = 'sidebar-spacer';
    spacer.id = 'sidebarSpacer';
    const win = document.createElement('div');
    win.className = 'sidebar-window';
    win.id = 'sidebarWindow';
    spacer.appendChild(win);
    list.replaceChildren(spacer);
    list.addEventListener('scroll', renderSidebarWindow, { passive: true });
  }
  list.scrollTop = 0;
  renderSidebarWindow();
}

function highlightSidebarItem(name) {
  activeSidebarName = name;
  const list = document.getElementById('sidebarList');
  const index = sidebarRows.findIndex(leg => leg.name === name);
  if (index < 0 || !list) { renderSidebarWindow(); return; }

  // The target row may not be in the DOM at all, so scroll by index rather than
  // hunting for an element and calling scrollIntoView on it.
  const rowH = sidebarRowHeight || SIDEBAR_ROW_FALLBACK;
  const top = index * rowH;
  const viewport = list.clientHeight || rowH * 12;
  if (top < list.scrollTop || top + rowH > list.scrollTop + viewport) {
    // scrollTo rather than assigning scrollTop, to keep the smooth motion the
    // old scrollIntoView({behavior:'smooth'}) gave. The scroll listener renders
    // each frame as it travels. Guarded because older Safari lacks it on
    // elements, and a throw here would break clicking a marker.
    const target = Math.max(0, top - viewport / 2 + rowH / 2);
    if (typeof list.scrollTo === 'function') list.scrollTo({ top: target, behavior: 'smooth' });
    else list.scrollTop = target;
  }
  renderSidebarWindow();
}

// ── DATA SOURCE ───────────────────────────────────────────────────────────
// Supabase is the primary data source; legends.json is the fallback.
// The publishable key is intentionally public. It grants exactly one thing:
// SELECT on the public_legends view. Not the legends table (anon holds no grant
// there at all), and nothing on bug_reports, feedback, legend_submissions or
// analytics_events; those are written only by edge functions using the service
// role. Table grants enforce this, not row-level security, which is the
// distinction that let anon hold TRUNCATE on legends unnoticed for months.
// Asserted by scripts/rls_regression_test.py.
//
// Publishable key, not the legacy anon JWT: it can be rotated on its own
// without reissuing every key in the project.
const SUPABASE_URL      = 'https://canjzkpvjwvkbjcduaaj.supabase.co';
const SUPABASE_PUBLISHABLE_KEY = 'sb_publishable_-XlJB_bYZlSjHAn7rQ2MQQ_BFsS5-4v';

function onDataLoaded(legends) {
  const params = new URLSearchParams(location.search);
  const requestedRegion = params.get('region');
  activeRegion = REGION_META[requestedRegion] ? requestedRegion : null;
  const requestedCollection = params.get('collection');
  LEGENDS = legends
    .filter(leg => !EXCLUDED_LEGEND_NAMES.has(leg.name))
    .map(leg => ({ ...leg, tags: Array.isArray(leg.tags) ? leg.tags : [] }));
  const availableNames = new Set(LEGENDS.map(leg => leg.name));
  bookmarks = new Set([...bookmarks].filter(name => availableNames.has(name)));
  saveBookmarks();
  loadMarkers(LEGENDS);
  buildFilters();
  buildLegend();
  loadSearchExtras();
  if (activeRegion) applyRegionFilter(activeRegion, true);
  else if (requestedCollection) {
    fetch(`/legends/collection/${encodeURIComponent(requestedCollection)}.json`)
      .then(r => r.ok ? r.json() : Promise.reject())
      .then(data => applyCollectionFilter(requestedCollection, data.legends || [], true))
      .catch(() => buildSidebarList(LEGENDS));
  }
  else {
    buildSidebarList(LEGENDS);
  }
  markers.forEach(m => m.on('popupopen', () => {
    highlightSidebarItem(m._legendData.name);
    history.replaceState(null, '', '?legend=' + encodeURIComponent(m._legendData.name));
  }));
  clusterGroup.on('popupclose', () => {
    const nextUrl = activeRegion ? '?region=' + encodeURIComponent(activeRegion) : location.pathname;
    history.replaceState(null, '', nextUrl);
  });

  const deepLink = params.get('legend');
  if (deepLink) setTimeout(() => focusLegend(deepLink), 100);
  if (params.get('submit') === '1') setTimeout(() => openSubmitLegend(), 300);
  // Restore night mode preference
  try { if (localStorage.getItem('folklore_night') === '1') toggleNight(); } catch(e) {}
}

function onDataError(err) {
  console.error('Failed to load legend data:', err);
  document.getElementById('filterBar').insertAdjacentHTML('beforeend',
    `<span style="color:#8b3a1a;font-size:12px;margin-left:8px">
      ⚠ Could not load legend data. Check the console for details.
    </span>`
  );
}

function loadLocalLegends() {
  return fetch('legends.json')
    .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
    .then(data => data.legends || data);
}

fetch('legend_pages.json')
  .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
  .then(data => {
    FEATURED_PAGES = data.pages || {};
    // Nothing else to do. Popup content is a function, so every popup opened
    // from here on reads the manifest itself. This previously rebuilt all 709
    // popup bodies the moment a 489KB fetch resolved. A popup cannot already be
    // open at this point: the manifest resolves during load, before any marker
    // has been clicked.
  })
  .catch(err => console.warn('Featured artwork manifest unavailable:', err));

if (SUPABASE_URL && SUPABASE_PUBLISHABLE_KEY) {
  // ── Fetch from Supabase ──────────────────────────────────────────────
  // Selects only the fields the map needs, ordered by name.
  // Excludes long-form detail/date fields; tags power the place filter.
  // period/cultural_tradition/alt_names power expanded search matching.
  // A ceiling, not a page size: 709 entries today. Defined once and interpolated
  // into the URL so the constant and the query cannot drift apart, and checked
  // on the way back -- hitting the limit would otherwise truncate the map in
  // silence, which is the failure mode worth avoiding, not the large number.
  const MAP_QUERY_LIMIT = 2000;
  // public_legends, not legends: a view exposing only these 11 columns, so a
  // column added to the base table later is not public by default. anon holds
  // no grant on the base table at all.
  fetch(`${SUPABASE_URL}/rest/v1/public_legends?select=name,lat,lng,category,region,summary,source,tags,period,cultural_tradition,alt_names&order=name.asc&limit=${MAP_QUERY_LIMIT}`, {
    headers: {
      'apikey':        SUPABASE_PUBLISHABLE_KEY,
      'Authorization': `Bearer ${SUPABASE_PUBLISHABLE_KEY}`,
    }
  })
  .then(r => { if (!r.ok) throw new Error(`Supabase HTTP ${r.status}`); return r.json(); })
  .then(rows => {
    if (rows.length >= MAP_QUERY_LIMIT) {
      console.warn(`Map hit the ${MAP_QUERY_LIMIT}-row query limit, so entries are missing. Raise MAP_QUERY_LIMIT or paginate.`);
    }
    return rows;
  })
  .then(onDataLoaded)
  .catch(err => {
    console.warn('Supabase unavailable, using local legend backup:', err);
    return loadLocalLegends().then(onDataLoaded).catch(onDataError);
  });

} else {
  // ── Fallback: fetch from legends.json ────────────────────────────────
  loadLocalLegends().then(onDataLoaded).catch(onDataError);
}

// ── BUG REPORT ──────────────────────────────────────────────────────────
const BUG_SUBMIT_ENDPOINT = 'https://canjzkpvjwvkbjcduaaj.supabase.co/functions/v1/submit-bug';

// Element to return keyboard focus to when an open modal closes.
let modalReturnFocus = null;
function restoreModalFocus() {
  if (modalReturnFocus && typeof modalReturnFocus.focus === 'function') modalReturnFocus.focus();
  modalReturnFocus = null;
}

// Turnstile is rendered explicitly, when a modal opens, rather than on page load.
// Renders on first open, resets on every open after that, so each submission gets
// a fresh token (they are single-use and expire after 300 seconds). If api.js has
// not finished loading yet the call is queued and replayed by onTurnstileLoad.
const turnstileWidgets = new Map();
function mountTurnstile(selector) {
  const container = document.querySelector(selector);
  if (!container) return;
  if (!window.__tsReady) {
    window.__tsPending.push(function () { mountTurnstile(selector); });
    return;
  }
  try {
    const existing = turnstileWidgets.get(container);
    if (existing !== undefined) { window.turnstile.reset(existing); return; }
    turnstileWidgets.set(container, window.turnstile.render(container, {
      sitekey: container.dataset.sitekey,
      theme:   container.dataset.theme || 'light',
    }));
  } catch (e) {}
}

function openBugReport() {
  document.getElementById('bugDescription').value = '';
  document.getElementById('bugSteps').value = '';
  const s = document.getElementById('bugStatus');
  s.style.display = 'none'; s.className = 'bug-status';
  const btn = document.querySelector('#bugModal .bug-submit-btn');
  btn.disabled = false; btn.textContent = 'Send Report';
  mountTurnstile('#bugModal .cf-turnstile');
  modalReturnFocus = document.activeElement;
  document.getElementById('bugModal').style.display = 'flex';
  document.getElementById('bugDescription').focus();
}

function closeBugReport() {
  document.getElementById('bugModal').style.display = 'none';
  restoreModalFocus();
}

async function submitBugReport() {
  const description = document.getElementById('bugDescription').value.trim();
  const steps       = document.getElementById('bugSteps').value.trim();
  const statusEl    = document.getElementById('bugStatus');
  const submitBtn   = document.querySelector('#bugModal .bug-submit-btn');

  if (!description) {
    statusEl.textContent = 'Please describe the bug before submitting.';
    statusEl.className = 'bug-status error';
    statusEl.style.display = 'block';
    return;
  }

  const tokenEl = document.querySelector('#bugModal [name="cf-turnstile-response"]');
  const token   = tokenEl ? tokenEl.value : '';
  if (!token) {
    statusEl.textContent = 'Please wait for the security check to complete.';
    statusEl.className = 'bug-status error';
    statusEl.style.display = 'block';
    return;
  }

  submitBtn.disabled = true;
  submitBtn.textContent = 'Sending…';

  try {
    const res = await fetch(BUG_SUBMIT_ENDPOINT, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        description,
        steps:   steps || null,
        url:     location.href,
        browser: navigator.userAgent,
        device:  /Mobi|Android|iPhone|iPad/i.test(navigator.userAgent) ? 'mobile' : 'desktop',
        cf_turnstile_response: token,
      })
    });
    const data = await res.json();

    if (res.ok && data.success) {
      statusEl.textContent = 'Thank you. Your report has been received.';
      statusEl.className = 'bug-status success';
      statusEl.style.display = 'block';
      submitBtn.textContent = 'Sent';
      setTimeout(closeBugReport, 2000);
    } else {
      throw new Error(data.error || 'Unexpected error');
    }

  } catch (err) {
    statusEl.textContent = err.message || 'Something went wrong. Please try again.';
    statusEl.className = 'bug-status error';
    statusEl.style.display = 'block';
    submitBtn.disabled = false;
    submitBtn.textContent = 'Send Report';
    mountTurnstile('#bugModal .cf-turnstile');
  }
}

// Close modal on Escape key
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') { closeBugReport(); closeSubmitLegend(); }
});

// Trap Tab focus inside an open modal dialog.
function trapModalFocus(e, modal) {
  if (e.key !== 'Tab') return;
  const focusables = Array.from(modal.querySelectorAll(
    'a[href], button:not([disabled]), textarea, input, select, iframe, [tabindex]:not([tabindex="-1"])'
  )).filter(el => el.offsetParent !== null);
  if (!focusables.length) return;
  const first = focusables[0], last = focusables[focusables.length - 1];
  if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
  else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
}
document.addEventListener('keydown', e => {
  if (e.key !== 'Tab') return;
  const bug = document.getElementById('bugModal');
  const submit = document.getElementById('submitModal');
  if (bug && bug.style.display === 'flex') trapModalFocus(e, bug);
  else if (submit && submit.style.display === 'flex') trapModalFocus(e, submit);
});

// ── SUBMIT A LEGEND ─────────────────────────────────────────────────────
const SUBMIT_ENDPOINT = 'https://canjzkpvjwvkbjcduaaj.supabase.co/functions/v1/submit-legend';

function openSubmitLegend() {
  ['submitName','submitRegion','submitDescription','submitSource'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.value = '';
  });
  const st = document.getElementById('submitStatus');
  st.style.display = 'none'; st.className = 'bug-status';
  document.querySelector('#submitModal .bug-submit-btn').disabled = false;
  document.querySelector('#submitModal .bug-submit-btn').textContent = 'Submit';
  mountTurnstile('#submitModal .cf-turnstile');
  modalReturnFocus = document.activeElement;
  document.getElementById('submitModal').style.display = 'flex';
  document.getElementById('submitName').focus();
}

function closeSubmitLegend() {
  document.getElementById('submitModal').style.display = 'none';
  restoreModalFocus();
}

(function trackMapVisitForAchievements(){
  try{
    const key = 'ff_behaviour_v1';
    const behaviour = JSON.parse(localStorage.getItem(key) || '{}') || {};
    behaviour.mapVisits = (Number(behaviour.mapVisits) || 0) + 1;
    localStorage.setItem(key, JSON.stringify(behaviour));
  }catch(error){}
})();

async function submitLegend() {
  const name   = document.getElementById('submitName').value.trim();
  const region = document.getElementById('submitRegion').value.trim();
  const desc   = document.getElementById('submitDescription').value.trim();
  const source = document.getElementById('submitSource').value.trim();
  const statusEl = document.getElementById('submitStatus');
  const btn      = document.querySelector('#submitModal .bug-submit-btn');

  if (!name || !region || !desc || !source) {
    statusEl.textContent = 'Please fill in all required fields.';
    statusEl.className = 'bug-status error';
    statusEl.style.display = 'block';
    return;
  }

  // Basic URL check client-side
  try { new URL(source); } catch {
    statusEl.textContent = 'Please enter a valid source URL (must start with https://).';
    statusEl.className = 'bug-status error';
    statusEl.style.display = 'block';
    return;
  }

  // Get Turnstile token
  const tokenEl = document.querySelector('#submitModal [name="cf-turnstile-response"]');
  const token   = tokenEl ? tokenEl.value : '';
  if (!token) {
    statusEl.textContent = 'Please wait for the security check to complete.';
    statusEl.className = 'bug-status error';
    statusEl.style.display = 'block';
    return;
  }

  btn.disabled = true;
  btn.textContent = 'Submitting…';

  try {
    const res = await fetch(SUBMIT_ENDPOINT, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        legend_name: name, region, description: desc,
        source_url: source, cf_turnstile_response: token,
      }),
    });
    const data = await res.json();
    if (res.ok && data.success) {
      statusEl.textContent = 'Thank you. Your submission has been received and will be researched.';
      statusEl.className = 'bug-status success';
      statusEl.style.display = 'block';
      btn.textContent = 'Submitted';
      setTimeout(closeSubmitLegend, 2500);
    } else {
      throw new Error(data.error || 'Unexpected error');
    }
  } catch (err) {
    statusEl.textContent = err.message || 'Something went wrong. Please try again.';
    statusEl.className = 'bug-status error';
    statusEl.style.display = 'block';
    btn.disabled = false;
    btn.textContent = 'Submit';
    mountTurnstile('#submitModal .cf-turnstile');
  }
}


// ── Event wiring ──────────────────────────────────────────────────────────
// These were inline on*= attributes. They are listeners now so that
// script-src can drop 'unsafe-inline': an inline handler is blocked by CSP
// however it was written, including one produced through innerHTML.
// The two modals share .bug-modal-close and .bug-submit-btn class names, so
// every selector below is scoped to its modal rather than matching both.
(function wireMapEvents() {
  const on = (sel, ev, fn) => {
    const el = document.querySelector(sel);
    if (el) el.addEventListener(ev, fn);
  };
  on('#modeToggle', 'click', () => toggleNight());
  on('#sidebarToggleBtn', 'click', () => toggleSidebar());
  on('#searchInput', 'input', e => handleSearch(e.target.value));
  on('.footer-bug-btn', 'click', () => openBugReport());

  on('#bugModal', 'click', e => { if (e.target.id === 'bugModal') closeBugReport(); });
  on('#bugModal .bug-modal-close', 'click', () => closeBugReport());
  on('#bugModal .bug-submit-btn', 'click', () => submitBugReport());

  on('#submitModal', 'click', e => { if (e.target.id === 'submitModal') closeSubmitLegend(); });
  on('#submitModal .bug-modal-close', 'click', () => closeSubmitLegend());
  on('#submitModal .bug-submit-btn', 'click', () => submitLegend());
})();
