(function(){
  var submitPrompt = document.querySelector('.hero-submit-cta');
  var submitPromptClose = document.querySelector('.hero-submit-close');
  try {
    if (submitPrompt && localStorage.getItem('ff_submit_prompt_closed_v1') === '1') {
      submitPrompt.classList.add('is-hidden');
    }
  } catch(e) {}
  if (submitPromptClose && submitPrompt) {
    submitPromptClose.addEventListener('click', function(){
      submitPrompt.classList.add('is-hidden');
      try { localStorage.setItem('ff_submit_prompt_closed_v1', '1'); } catch(e) {}
    });
  }

  let LEGENDS = [];
  let IMAGED = new Set(); // slugs with a hero image (legend-images/manifest.json)

  // Category labels, colours and glyphs come from js/categories.js, which
  // must load before this file. This was a byte-for-byte duplicate that
  // drifted on the pirate label.
  const CATMETA = window.FF_CATEGORIES || {};
  function catLabel(c){return (CATMETA[c]&&CATMETA[c].label)||c||'';}
  function catColour(c){return (CATMETA[c]&&CATMETA[c].colour)||'#8b3a1a';}

  function isoWeekSeed(date){
    const d = new Date(Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()));
    const dayNum = (d.getUTCDay() + 6) % 7;
    d.setUTCDate(d.getUTCDate() - dayNum + 3);
    const firstThursday = new Date(Date.UTC(d.getUTCFullYear(), 0, 4));
    const ftDayNum = (firstThursday.getUTCDay() + 6) % 7;
    firstThursday.setUTCDate(firstThursday.getUTCDate() - ftDayNum + 3);
    const week = 1 + Math.round((d - firstThursday) / (7 * 24 * 3600 * 1000));
    return d.getUTCFullYear() * 53 + week;
  }

  function mapLink(name){ return './map?legend=' + encodeURIComponent(name); }

  // Mirrors slugify() in generate_pages.py so homepage features link straight to
  // the static article page (legends/<slug>) rather than opening the map. The map
  // is reached via a separate "Show on map" action.
  function slugify(name){
    return (name || '')
      .normalize('NFKD').replace(/[̀-ͯ]/g, '')
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-+|-+$/g, '') || 'legend';
  }
  function articleLink(name){ return './legends/' + slugify(name); }

  // Round the published legend count down to the nearest 50 and show it as
  // "X+" (e.g. 664 -> "650+") wherever it's displayed — keeps the headline
  // number stable as entries are added rather than ticking up by ones. No
  // "+" when the total lands exactly on a multiple of 50 (e.g. 700 -> "700"),
  // since it isn't "more than" in that case.
  function roundedCountPlus(n){
    const r = Math.floor(n / 50) * 50;
    return r + (r < n ? '+' : '');
  }

  function getJSON(key, fallback){
    try { return JSON.parse(localStorage.getItem(key) || 'null') || fallback; } catch(e) { return fallback; }
  }

  // ── Stats strip ──
  function renderStats(data){
    const elLegends = document.getElementById('statLegends');
    const elCategories = document.getElementById('statCategories');
    const elRegions = document.getElementById('statRegions');
    const elCollections = document.getElementById('statCollections');
    if (elLegends) elLegends.textContent = roundedCountPlus(data.total || LEGENDS.length);
    if (elCategories) elCategories.textContent = Object.keys(CATMETA).length;
    if (elRegions) {
      // l.region is free text ("Slaghtaverty, County Londonderry") rather than a
      // controlled taxonomy, so a raw unique count runs into the hundreds and
      // reads as noise. Detect nation coverage instead — a small, stable number
      // that matches the "Britain and Ireland" framing directly.
      const NATIONS = ['England', 'Scotland', 'Wales', 'Northern Ireland', 'Ireland'];
      const found = new Set();
      LEGENDS.forEach(l => {
        const r = l.region || '';
        NATIONS.forEach(n => { if (r.includes(n)) found.add(n); });
      });
      // Only ever improve on the server-rendered fallback. Blanking it to a
      // placeholder when the count comes back empty would replace a correct
      // number with a worse one.
      if (found.size) elRegions.textContent = found.size;
    }
    if (elCollections) {
      fetch('./collections.json')
        .then(r => r.json())
        .then(c => {
          const n = (c.collections || []).length;
          if (n) elCollections.textContent = n;
        })
        // On failure keep the static count that generate_pages.py wrote in.
        .catch(() => {});
    }
  }

  // ── Guidance carousel ──
  // Card 5 (Ko-fi/growth cards) is out of scope for this pass — the proposal's
  // five-card set covers navigation to existing features only. Card 1 adapts to
  // visitor state using the same localStorage keys My Archive reads.
  const STATIC_GC_CARDS = [
    { id: 'archive', eyebrow: 'Your Archive', title: 'Build My Archive', desc: 'Save legends, track what you have discovered and continue where you left off.', cta: 'View My Archive', href: './archive' },
    { id: 'achievements', eyebrow: 'Achievements', title: 'Unlock achievements', desc: 'Discover creatures, places and traditions to unlock explorer seals.', cta: 'See achievements', href: './achievements' },
    { id: 'collections', eyebrow: 'Collections', title: 'Explore a collection', desc: 'Follow curated trails through black dogs, dragons, standing stones and more.', cta: 'Browse collections', href: './legends/collections' },
    { id: 'updates', eyebrow: 'What’s New', title: 'See what is new', desc: 'Discover the latest legends, collections and improvements added to the archive.', cta: 'Latest updates', href: './updates' }
  ];

  // Synchronous first-guess adaptive card — no network fetch, so the carousel
  // never has to wait on anything to show its first slide. A first-time
  // visitor's card ("Find folklore near you") is already the best answer, so
  // this is final for them. A returning visitor's card ("Continue exploring")
  // is a reasonable placeholder that computeBetterAdaptiveCard() below may
  // upgrade in place to a "partway through a collection" card once the
  // (slower, two-fetch) collections data has actually loaded.
  function adaptiveCardSync(){
    const visited = getJSON('ff_visited_legends_v1', {});
    const visitedNames = Object.keys(visited);
    if (!visitedNames.length) {
      return {
        id: 'near',
        eyebrow: 'Start Here',
        title: 'Find folklore near you',
        desc: 'Search a town, county or landmark to uncover stories rooted nearby.',
        cta: 'Search the map',
        href: './map'
      };
    }
    const mostRecent = visitedNames
      .map(n => ({ name: n, last: visited[n] && visited[n].lastVisited }))
      .sort((a, b) => new Date(b.last) - new Date(a.last))[0];
    return {
      id: 'continue',
      eyebrow: 'Welcome Back',
      title: 'Continue exploring',
      desc: mostRecent ? 'Pick up where you left off and return to ' + mostRecent.name + '.' : 'Pick up where you left off in your archive.',
      cta: 'Continue exploring',
      href: mostRecent ? articleLink(mostRecent.name) : './archive'
    };
  }

  // Slower upgrade path for returning visitors only: checks whether any
  // collection is partway complete, which needs collections.json plus every
  // collection's own member list (2 sequential fetch stages). Resolves to
  // null when there's nothing better than the sync fallback already shown,
  // so the caller knows not to touch the DOM.
  function computeBetterAdaptiveCard(){
    const visited = getJSON('ff_visited_legends_v1', {});
    const visitedNames = Object.keys(visited);
    if (!visitedNames.length) return Promise.resolve(null);
    const visitedSet = new Set(visitedNames);

    return fetch('./collections.json')
      .then(r => r.json())
      .then(colData => {
        const collections = (colData && colData.collections) || [];
        if (!collections.length) return null;
        return Promise.all(collections.map(col =>
          fetch('./legends/collection/' + col.slug + '.json')
            .then(r => r.ok ? r.json() : { legends: [] })
            .catch(() => ({ legends: [] }))
            .then(m => ({ col: col, members: m.legends || [] }))
        )).then(results => {
          const partial = results.find(r => {
            if (!r.members.length) return false;
            const count = r.members.filter(n => visitedSet.has(n)).length;
            return count > 0 && count < r.members.length;
          });
          if (!partial) return null;
          const count = partial.members.filter(n => visitedSet.has(n)).length;
          return {
            id: 'collection',
            eyebrow: 'In Progress',
            title: 'Continue your collection',
            desc: 'You have discovered ' + count + ' of ' + partial.members.length + ' legends in ' + partial.col.title + '.',
            cta: 'Continue collection',
            href: './legends/collection/' + partial.col.slug
          };
        });
      })
      .catch(() => null);
  }

  // Patches the already-rendered first slide's text/link in place, instead
  // of re-rendering the whole carousel — so a late-arriving upgrade never
  // resets a visitor's scroll position if they've already started browsing.
  function updateFirstSlideContent(card){
    const track = document.getElementById('gcTrack');
    const slide = track && track.children[0];
    if (!slide) return;
    slide.setAttribute('data-card-id', card.id);
    slide.setAttribute('aria-label', '1 of ' + track.children.length + ': ' + card.title);
    const eyebrow = slide.querySelector('.gc-eyebrow');
    const title = slide.querySelector('.gc-title');
    const desc = slide.querySelector('.gc-desc');
    const cta = slide.querySelector('.gc-cta');
    if (eyebrow) eyebrow.textContent = card.eyebrow || '';
    if (title) title.textContent = card.title;
    if (desc) desc.textContent = card.desc;
    if (cta) {
      cta.textContent = card.cta + ' →';
      cta.href = card.href;
      cta.setAttribute('data-track', 'carousel_' + card.id);
    }
  }

  function renderCarousel(adaptiveCard){
    const cards = [adaptiveCard].concat(STATIC_GC_CARDS);
    const track = document.getElementById('gcTrack');
    const dots = document.getElementById('gcDots');
    const prevBtn = document.getElementById('gcPrev');
    const nextBtn = document.getElementById('gcNext');
    if (!track || !dots) return;
    track.innerHTML = '';
    dots.innerHTML = '';

    cards.forEach((c, i) => {
      const slide = document.createElement('div');
      slide.className = 'gc-card';
      slide.setAttribute('data-card-id', c.id);
      slide.setAttribute('role', 'group');
      slide.setAttribute('aria-roledescription', 'slide');
      slide.setAttribute('aria-label', (i + 1) + ' of ' + cards.length + ': ' + c.title);
      const eyebrow = document.createElement('span'); eyebrow.className = 'gc-eyebrow'; eyebrow.textContent = c.eyebrow || '';
      const h = document.createElement('h3'); h.className = 'gc-title'; h.textContent = c.title;
      const p = document.createElement('p'); p.className = 'gc-desc'; p.textContent = c.desc;
      const a = document.createElement('a'); a.className = 'gc-cta'; a.href = c.href;
      a.setAttribute('data-track', 'carousel_' + c.id);
      a.textContent = c.cta + ' →';
      slide.appendChild(eyebrow); slide.appendChild(h); slide.appendChild(p); slide.appendChild(a);
      track.appendChild(slide);

      const dot = document.createElement('button');
      dot.type = 'button'; dot.className = 'gc-dot';
      dot.setAttribute('aria-label', 'Go to slide ' + (i + 1) + ': ' + c.title);
      dot.addEventListener('click', () => goToSlide(i));
      dots.appendChild(dot);
    });

    const reduceMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    function currentIdx(){
      return track.clientWidth ? Math.round(track.scrollLeft / track.clientWidth) : 0;
    }
    function goToSlide(i){
      const clamped = Math.max(0, Math.min(cards.length - 1, i));
      const target = track.children[clamped];
      if (target) target.scrollIntoView({ behavior: reduceMotion ? 'auto' : 'smooth', inline: 'start', block: 'nearest' });
    }
    function updateControls(){
      const idx = currentIdx();
      Array.from(dots.children).forEach((d, i) => {
        d.classList.toggle('active', i === idx);
        d.setAttribute('aria-current', i === idx ? 'true' : 'false');
      });
      if (prevBtn) prevBtn.disabled = idx <= 0;
      if (nextBtn) nextBtn.disabled = idx >= cards.length - 1;
    }

    let scrollTimer;
    track.addEventListener('scroll', () => {
      clearTimeout(scrollTimer);
      scrollTimer = setTimeout(updateControls, 80);
    });
    if (prevBtn) prevBtn.addEventListener('click', () => goToSlide(currentIdx() - 1));
    if (nextBtn) nextBtn.addEventListener('click', () => goToSlide(currentIdx() + 1));
    track.addEventListener('keydown', e => {
      if (e.key === 'ArrowRight') { e.preventDefault(); goToSlide(currentIdx() + 1); }
      else if (e.key === 'ArrowLeft') { e.preventDefault(); goToSlide(currentIdx() - 1); }
    });

    updateControls();
    enhanceAchievementsCard();
  }

  // Rewrites the "Unlock achievements" carousel card with a live count once
  // achievements.json loads, instead of the static description — matches the
  // adaptive card's "show real numbers" treatment rather than generic copy.
  function enhanceAchievementsCard(){
    const desc = document.querySelector('.gc-card[data-card-id="achievements"] .gc-desc');
    if (!desc) return;
    fetch('./assets/achievements/achievements.json')
      .then(r => r.json())
      .then(data => {
        const total = (data.sections || []).reduce((sum, s) =>
          sum + (s.items || []).filter(a => !(a.availability && a.availability.status === 'draft')).length, 0);
        if (!total) return;
        const unlocked = getJSON('ff_achievements_unlocked_v1', []).length;
        desc.textContent = unlocked
          ? unlocked + ' of ' + total + ' explorer seals unlocked so far.'
          : total + ' explorer seals to discover as you explore the map.';
      })
      .catch(() => {});
  }

  // ── Find folklore near me ──
  function haversineKm(lat1, lng1, lat2, lng2){
    const R = 6371, toRad = d => d * Math.PI / 180;
    const dLat = toRad(lat2 - lat1), dLng = toRad(lng2 - lng1);
    const a = Math.sin(dLat / 2) ** 2 + Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLng / 2) ** 2;
    return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  }
  // Beyond this, the "nearest" match is too far to be meaningfully near —
  // roughly the corner-to-corner span of Britain & Ireland — so a visitor
  // outside that area gets an honest message instead of a misleading match.
  const NEAR_ME_MAX_KM = 650;
  function nearestLegend(lat, lng){
    let best = null, bestD = Infinity;
    LEGENDS.forEach(l => {
      if (typeof l.lat !== 'number' || typeof l.lng !== 'number') return;
      const d = haversineKm(lat, lng, l.lat, l.lng);
      if (d < bestD) { bestD = d; best = l; }
    });
    return best ? { legend: best, distanceKm: bestD } : null;
  }

  const nearMeBtn = document.getElementById('nearMeBtn');
  const nearMeStatus = document.getElementById('nearMeStatus');

  function statusLink(text, href){
    const a = document.createElement('a');
    a.href = href; a.textContent = text;
    return a;
  }
  // Accepts a mix of plain strings and link elements (from statusLink) so
  // every outcome — including denial, timeout and out-of-range — gets a
  // visible explanation instead of a silent redirect.
  function setNearMeStatus(...parts){
    if (!nearMeStatus) return;
    nearMeStatus.innerHTML = '';
    if (!parts.length) { nearMeStatus.hidden = true; return; }
    parts.forEach(part => {
      nearMeStatus.appendChild(typeof part === 'string' ? document.createTextNode(part) : part);
    });
    nearMeStatus.hidden = false;
  }

  if (nearMeBtn) {
    // Swap the label, not the button's textContent — the button also holds an
    // inline SVG icon, which a textContent write would wipe out.
    const nearMeLabel = nearMeBtn.querySelector('.btn-label');
    const nearMeDefaultText = nearMeLabel.textContent;
    function resetNearMeBtn(){
      nearMeBtn.disabled = false;
      nearMeLabel.textContent = nearMeDefaultText;
    }
    nearMeBtn.addEventListener('click', () => {
      setNearMeStatus();
      if (!navigator.geolocation) {
        setNearMeStatus("Your browser doesn't support location lookup. ", statusLink('Explore the map instead →', './map'));
        return;
      }
      nearMeBtn.disabled = true;
      nearMeLabel.textContent = 'Locating…';
      setNearMeStatus('Requesting your location. Look for a permission prompt from your browser.');
      navigator.geolocation.getCurrentPosition(
        pos => {
          resetNearMeBtn();
          const result = nearestLegend(pos.coords.latitude, pos.coords.longitude);
          if (!result) {
            setNearMeStatus("Couldn't match your location to a legend. ", statusLink('Explore the map instead →', './map'));
            return;
          }
          if (result.distanceKm > NEAR_ME_MAX_KM) {
            setNearMeStatus(
              'Folklore Finder currently covers Britain & Ireland, so nothing is truly nearby from where you are. The closest entry on the map is ' + result.legend.name + '. ',
              statusLink('See it anyway →', articleLink(result.legend.name)),
              ' or ',
              statusLink('explore the full map →', './map')
            );
            return;
          }
          setNearMeStatus('Found it: ' + result.legend.name + ', about ' + Math.round(result.distanceKm) + ' km away. Taking you there…');
          // Hand off to the legend page via sessionStorage (survives the
          // redirect without a URL param) so it can offer a "share this
          // discovery" toast on arrival — this redirect itself stays exactly
          // as tuned, no pause added here.
          try {
            sessionStorage.setItem('ff_near_me_find', JSON.stringify({
              name: result.legend.name,
              distanceKm: Math.round(result.distanceKm),
              region: result.legend.region || '',
              category: result.legend.category || '',
            }));
          } catch (e) {}
          window.location.href = articleLink(result.legend.name);
        },
        err => {
          resetNearMeBtn();
          let msg;
          if (err.code === err.PERMISSION_DENIED) msg = "Location access was declined, so we can't find your nearest legend. ";
          else if (err.code === err.TIMEOUT) msg = "Couldn't get your location in time. ";
          else msg = "Couldn't get your location. ";
          setNearMeStatus(msg, statusLink('Explore the map instead →', './map'));
        },
        { timeout: 8000 }
      );
    });
  }

  // ── Homepage click tracking ──
  function trackEvent(eventType, extra){
    try {
      let id = sessionStorage.getItem('ff_session_id');
      if (!id) { id = Math.random().toString(36).slice(2) + Date.now().toString(36); sessionStorage.setItem('ff_session_id', id); }
      const payload = Object.assign({ event_type: eventType, referring_page: location.pathname, session_id: id }, extra || {});
      fetch('https://canjzkpvjwvkbjcduaaj.supabase.co/functions/v1/submit-event', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload), keepalive: true
      }).catch(() => {});
    } catch(e) {}
  }
  document.addEventListener('click', e => {
    const el = e.target.closest('[data-track]');
    // item_id, not cta: item_id is the generic column for events that do not
    // fit the named ones. A `cta` key has no column behind it and was silently
    // dropped even before home_cta_click was added to the allowlist.
    if (el) trackEvent('home_cta_click', { item_id: el.getAttribute('data-track') });
  });

  function renderLotw(){
    // Prefer entries that have hero artwork AND full detail prose, so the
    // banner reliably shows an image; fall back gracefully if few qualify.
    let pool = LEGENDS.filter(l => IMAGED.has(slugify(l.name)) && l.detail && l.detail.length > 60);
    if (pool.length < 3) pool = LEGENDS.filter(l => l.detail && l.detail.length > 60);
    if (!pool.length) pool = LEGENDS.slice();
    // Deterministic weekly pick that stays stable as the dataset grows:
    // pick the entry whose hash of (name + ISO-week) is highest. The week seed
    // is constant Mon–Sun, so the featured legend only changes once a week —
    // previously it used (seed % pool.length), which shifted daily as entries
    // were added or gained detail.
    const wk = isoWeekSeed(new Date());
    let pick = null, bestH = -1;
    for (let i = 0; i < pool.length; i++) {
      let s = pool[i].name + '|' + wk, h = 2166136261;
      for (let j = 0; j < s.length; j++) { h ^= s.charCodeAt(j); h = Math.imul(h, 16777619); }
      h = h >>> 0;
      if (h > bestH) { bestH = h; pick = pool[i]; }
    }
    if (!pick) return;
    const meta = CATMETA[pick.category];
    const colour = catColour(pick.category);
    document.getElementById('lotwCat').textContent = catLabel(pick.category);
    document.getElementById('lotwName').textContent = pick.name;
    document.getElementById('lotwRegion').textContent = pick.region || '';
    document.getElementById('lotwLink').href = articleLink(pick.name);
    document.getElementById('lotwMapLink').href = mapLink(pick.name);

    // Placeholder styling (category colour + icon) — shown until/unless the
    // legend's hero image loads, mirroring the legend-page hero behaviour.
    const ph = document.getElementById('lotwPh');
    const media = document.getElementById('lotwMedia');
    ph.style.setProperty('--ph', colour);
    if (meta && meta.iconPath) document.getElementById('lotwMarkPath').setAttribute('d', meta.iconPath);
    ph.style.display = '';
    media.style.backgroundImage = 'none';

    // Probe the legend's 16:9 hero image; on success show it, hide placeholder.
    const imgUrl = './legend-images/' + slugify(pick.name) + '-hero.jpg';
    const probe = new Image();
    probe.onload = function(){
      media.style.backgroundImage = 'url("' + imgUrl + '")';
      ph.style.display = 'none';
    };
    probe.src = imgUrl;
  }

  // Render the carousel immediately with the synchronous fallback card — no
  // fetch, no wait. For a returning visitor, computeBetterAdaptiveCard() then
  // checks in the background whether a partway-complete collection would be
  // a better first slide (that needs collections.json + every collection's
  // member list — a real two-stage fetch chain, ~2 round trips) and patches
  // just that slide's text in place if so, rather than blocking the whole
  // carousel on it. This is what was still causing carousel lag for
  // returning visitors even after decoupling it from the unrelated
  // legends.json fetch below.
  renderCarousel(adaptiveCardSync());
  computeBetterAdaptiveCard().then(better => {
    if (better) updateFirstSlideContent(better);
  });

  // manifest.json (tiny) and legends.json (~500KB) are independent too —
  // fetch them together instead of one after the other.
  Promise.all([
    fetch('./legend-images/manifest.json').then(r => r.ok ? r.json() : []).catch(() => []),
    fetch('./legends.json').then(r => r.json()),
  ]).then(([slugs, data]) => {
    IMAGED = new Set(slugs || []);
    LEGENDS = data.legends || [];
    const n = data.total || LEGENDS.length;
    document.getElementById('heroCount').textContent = roundedCountPlus(n);
    renderLotw();
    renderStats(data);
  });

  // Surprise me
  document.getElementById('surpriseBtn').addEventListener('click', () => {
    if (!LEGENDS.length) return;
    const l = LEGENDS[Math.floor(Math.random() * LEGENDS.length)];
    window.location.href = articleLink(l.name);
  });

  // ── Search ──
  // Searches name, region, friendly category, tags and summary. Each legend is
  // scored by its strongest match (exact name > prefix > name > region >
  // category > tag > summary) so precise hits rank above broad summary matches.
  const input = document.getElementById('heroSearch');
  const results = document.getElementById('heroResults');
  let activeIdx = -1;
  let currentMatches = [];

  // Return {score, reason} for a legend against query q, or null if no match.
  function scoreLegend(leg, q){
    const name = (leg.name || '').toLowerCase();
    const region = (leg.region || '').toLowerCase();
    const cat = catLabel(leg.category).toLowerCase();
    const summary = (leg.summary || '').toLowerCase();
    const tags = leg.tags || [];

    let score = 0;
    if (name === q) score = 100;
    else if (name.startsWith(q)) score = 80;
    else if (name.includes(q)) score = 60;
    else if (region.includes(q)) score = 45;
    else if (cat.includes(q)) score = 35;
    else if (tags.some(t => t.toLowerCase().includes(q))) score = 30;
    else if (summary.includes(q)) score = 15;
    else return null;

    // Secondary line shows where it sits: region · category.
    const parts = [];
    if (leg.region) parts.push(leg.region);
    if (catLabel(leg.category)) parts.push(catLabel(leg.category));
    return { score: score, reason: parts.join(' · ') };
  }

  function search(q){
    const scored = [];
    for (const leg of LEGENDS){
      const r = scoreLegend(leg, q);
      if (r) scored.push({ leg: leg, score: r.score, reason: r.reason });
    }
    scored.sort((a, b) => b.score - a.score || a.leg.name.localeCompare(b.leg.name));
    return scored.slice(0, 8);
  }

  function setExpanded(open){
    input.setAttribute('aria-expanded', open ? 'true' : 'false');
    results.classList.toggle('open', open);
    if (!open) input.removeAttribute('aria-activedescendant');
  }

  function renderResults(items, q){
    results.innerHTML = '';
    activeIdx = -1;
    currentMatches = items;
    input.removeAttribute('aria-activedescendant');
    if (!items.length) { setExpanded(false); return; }
    items.forEach((it, i) => {
      const el = document.createElement('div');
      el.className = 'search-result-item';
      el.id = 'heroResult-' + i;
      el.setAttribute('role', 'option');
      el.setAttribute('aria-selected', 'false');
      const nm = document.createElement('span'); nm.className = 'rn'; nm.textContent = it.leg.name;
      const meta = document.createElement('span'); meta.className = 'rmeta';
      meta.textContent = it.reason || '';
      el.appendChild(nm); el.appendChild(meta);
      el.addEventListener('mousedown', e => {
        e.preventDefault();
        goToLegend(it.leg.name);
      });
      results.appendChild(el);
    });
    setExpanded(true);
  }

  function setActive(idx){
    const items = results.querySelectorAll('.search-result-item');
    items.forEach((el, i) => {
      const on = i === idx;
      el.classList.toggle('active', on);
      el.setAttribute('aria-selected', on ? 'true' : 'false');
    });
    if (idx >= 0 && items[idx]){
      input.setAttribute('aria-activedescendant', items[idx].id);
      items[idx].scrollIntoView({ block: 'nearest' });
    } else {
      input.removeAttribute('aria-activedescendant');
    }
  }

  function goToLegend(name) {
    setExpanded(false);
    input.value = '';
    window.location.href = articleLink(name);
  }

  input.addEventListener('input', () => {
    const q = input.value.trim().toLowerCase();
    if (q.length < 2) { setExpanded(false); return; }
    renderResults(search(q), q);
  });

  input.addEventListener('keydown', e => {
    const items = results.querySelectorAll('.search-result-item');
    if (!items.length) return;
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      activeIdx = Math.min(activeIdx + 1, items.length - 1);
      setActive(activeIdx);
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      activeIdx = Math.max(activeIdx - 1, -1);
      setActive(activeIdx);
    } else if (e.key === 'Enter') {
      e.preventDefault();
      const pick = activeIdx >= 0 ? currentMatches[activeIdx] : currentMatches[0];
      if (pick) goToLegend(pick.leg.name);
    } else if (e.key === 'Escape') {
      setExpanded(false);
    }
  });

  document.addEventListener('click', e => {
    if (!e.target.closest('#heroSearch') && !e.target.closest('#heroResults'))
      setExpanded(false);
  });
})();
