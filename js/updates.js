(function(){
  // ── Curated site updates (newest first). Append new release blocks at the
  // top. Each item is either a plain string (shown as a visitor-facing
  // update, the default) or {text, tech:true} for a technical/dev note —
  // those render in a collapsed "Technical changelog" below the main list
  // instead of mixed into it. ──
  const UPDATES = [
    { date: "August 2026", items: [
      "A new homepage guidance carousel: quick routes into My Archive, achievements, collections and what's new, with a first card that adapts to how far you've explored.",
      "Find folklore near me: a button that uses your device's location to jump straight to the nearest legend.",
      "My Archive redesigned for first-time visitors, with a clear starting point and a prompt to pick up an in-progress collection where you left off.",
      "Collection pages now show your own progress: begin, continue or complete, for every themed collection.",
      "The map now fills the full page, with the entries panel opening over the top instead of squeezing it into a smaller column.",
      "A new Editorial & AI-Use Policy page explains how entries are researched, sourced and, where AI-generated, illustrated.",
      "AI-generated legend illustrations are now labelled on the page.",
      { text: "Search-engine rules updated to keep AI training crawlers out while normal search indexing continues as before.", tech: true },
      { text: "A recurring sourcing-audit tool now flags thin or single-sourced entries for the ongoing research process to revisit.", tech: true }
    ] },
    { date: "July 2026", items: [
      "Collections reimagined. Each one now reads as an illustrated article, with an image beside every tale.",
      "A new Birth of Albion collection, tracing the mythic founding of Britain from Brutus and the fall of Troy to the last giants of Albion.",
      "Every collection trimmed and re-curated to its strongest, best-fitting legends.",
      "A consistent banner across the whole site, with the full navigation now built into the map too.",
      "Achievement seals now grey out while a badge is in progress and turn full colour once it's earned."
    ] },
    { date: "June 2026", items: [
      "New welcome page with a weekly featured legend, recently-added entries and instant search.",
      "Related Legends added to the foot of every entry page, linking kindred tales nearby and alike.",
      "Browse the whole collection by category or by region.",
      "A dusk (night) mode for the map, easier on the eyes after dark.",
      "Moved to faster, more secure hosting."
    ] }
  ];

  // Carousel: index 0 is always the newest month, shown by default. Prev
  // steps back through older months; Next returns toward the present.
  let monthIdx = 0;
  const su = document.getElementById('siteUpdates');
  const label = document.getElementById('carouselLabel');
  const prevBtn = document.getElementById('prevMonthBtn');
  const nextBtn = document.getElementById('nextMonthBtn');

  function renderMonth(){
    const rel = UPDATES[monthIdx];
    su.innerHTML = '';
    if (!rel) { su.innerHTML = '<p class="empty-note">No updates recorded yet.</p>'; return; }
    var visitorItems = rel.items.filter(function(it){ return !(it && it.tech); });
    var techItems = rel.items.filter(function(it){ return it && it.tech; });
    var box = document.createElement('div'); box.className = 'release';
    var ul = document.createElement('ul');
    visitorItems.forEach(function(it){
      var li = document.createElement('li');
      li.textContent = typeof it === 'string' ? it : it.text;
      ul.appendChild(li);
    });
    box.appendChild(ul);
    if (techItems.length) {
      var details = document.createElement('details'); details.className = 'tech-changelog';
      var summary = document.createElement('summary'); summary.textContent = 'Technical changelog (' + techItems.length + ')';
      var techUl = document.createElement('ul');
      techItems.forEach(function(it){ var li = document.createElement('li'); li.textContent = it.text; techUl.appendChild(li); });
      details.appendChild(summary); details.appendChild(techUl);
      box.appendChild(details);
    }
    su.appendChild(box);
    label.textContent = rel.date;
    prevBtn.disabled = monthIdx >= UPDATES.length - 1;
    nextBtn.disabled = monthIdx <= 0;
  }
  prevBtn.addEventListener('click', function(){ if (monthIdx < UPDATES.length - 1) { monthIdx++; renderMonth(); } });
  nextBtn.addEventListener('click', function(){ if (monthIdx > 0) { monthIdx--; renderMonth(); } });
  renderMonth();

  // ── Recently added legends and new collections. Populated at build time by
  // generate_pages.py (see build_recent_legends()/build_new_collections()); the
  // empty-array fallbacks below only show if the build step hasn't run yet. ──
  const RECENT_LEGENDS = [{"slug": "mother-redcap-s", "name": "Mother Redcap's", "date_added": "1 September 2026", "region": "Wallasey, Wirral, Merseyside", "category": "Pirates", "colour": "#6b6b6b"}, {"slug": "poldies", "name": "Poldies", "date_added": "1 September 2026", "region": "Wirral, Merseyside", "category": "Fae & Spirits", "colour": "#7e5577"}, {"slug": "the-bidston-hill-carvings", "name": "The Bidston Hill Carvings", "date_added": "1 September 2026", "region": "Bidston, Wirral, Merseyside", "category": "Sacred Sites", "colour": "#5a3a18"}, {"slug": "the-bloody-acre", "name": "The Bloody Acre", "date_added": "1 September 2026", "region": "Childwall, Liverpool, Merseyside", "category": "Sacred Sites", "colour": "#5a3a18"}, {"slug": "the-grey-lady-of-speke-hall", "name": "The Grey Lady of Speke Hall", "date_added": "1 September 2026", "region": "Speke, Liverpool, Merseyside", "category": "Ghosts", "colour": "#4a3d6e"}, {"slug": "the-liver-birds", "name": "The Liver Birds", "date_added": "1 September 2026", "region": "Liverpool, Merseyside", "category": "Beasts", "colour": "#2d6a8a"}, {"slug": "the-monk-s-well", "name": "The Monk's Well", "date_added": "1 September 2026", "region": "Wavertree, Liverpool, Merseyside", "category": "Sacred Sites", "colour": "#5a3a18"}, {"slug": "the-queensway-tunnel-hitchhiker", "name": "The Queensway Tunnel Hitchhiker", "date_added": "1 September 2026", "region": "Queensway Tunnel, Liverpool and Birkenhead, Merseyside", "category": "Ghosts", "colour": "#4a3d6e"}];
  const NEW_COLLECTIONS = [{"slug": "birth-of-albion", "title": "Birth of Albion"}];

  const rl = document.getElementById('recentLegends');
  if (RECENT_LEGENDS.length) {
    RECENT_LEGENDS.forEach(function(leg){
      var li = document.createElement('li');
      var a = document.createElement('a');
      a.className = 'recent-card';
      a.href = 'legends/' + leg.slug;
      var dt = document.createElement('div'); dt.className = 'recent-added-date';
      dt.textContent = leg.date_added ? 'Added ' + leg.date_added : 'Newly added';
      var nm = document.createElement('div'); nm.className = 'recent-name'; nm.textContent = leg.name;
      var rg = document.createElement('div'); rg.className = 'recent-region'; rg.textContent = leg.region || '';
      var ct = document.createElement('div'); ct.className = 'recent-cat';
      ct.textContent = leg.category || '';
      ct.style.background = leg.colour || '#8b3a1a';
      a.appendChild(dt); a.appendChild(nm); a.appendChild(rg); a.appendChild(ct);
      // Only entries that began as a follower's submission carry this flag.
      if (leg.follower) {
        var fs = document.createElement('div'); fs.className = 'recent-follower';
        fs.textContent = 'Follower suggestion';
        a.appendChild(fs);
      }
      li.appendChild(a);
      rl.appendChild(li);
    });
  } else {
    rl.innerHTML = '<li><p class="empty-note">Check back soon for the latest additions to the map.</p></li>';
  }

  const nc = document.getElementById('newCollections');
  if (NEW_COLLECTIONS.length) {
    NEW_COLLECTIONS.forEach(function(col){
      var li = document.createElement('li');
      var a = document.createElement('a');
      a.href = 'legends/collection/' + col.slug;
      // archive.js builds the same card with textContent; this one was
      // concatenating the title in raw, so an ampersand in a collection name
      // rendered as broken markup.
      a.innerHTML = '<span class="card-eyebrow">Collection</span>'
        + '<span class="card-title">' + SafeDOM.escapeHtml(col.title) + '</span>';
      li.appendChild(a);
      nc.appendChild(li);
    });
  } else {
    nc.innerHTML = '<li><p class="empty-note">No new collections since the last update. Browse the <a href="legends/collections">full list</a>.</p></li>';
  }
})();

// ── FEEDBACK POPUP ──────────────────────────────────────────────────────
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

function openFeedback(){
  document.getElementById('feedbackModalOverlay').classList.add('open');
  mountTurnstile('.cf-turnstile');
}
function closeFeedback(){
  document.getElementById('feedbackModalOverlay').classList.remove('open');
}

// ── FEEDBACK FORM ──────────────────────────────────────────────────────
const FEEDBACK_SUBMIT_ENDPOINT = 'https://canjzkpvjwvkbjcduaaj.supabase.co/functions/v1/submit-feedback';

async function submitFeedback() {
  const feedback_type = document.getElementById('fbType').value;
  const message        = document.getElementById('fbMessage').value.trim();
  const contact_email  = document.getElementById('fbEmail').value.trim();
  const statusEl        = document.getElementById('fbStatus');
  const submitBtn       = document.querySelector('.f-submit');

  if (!message) {
    statusEl.textContent = 'Please write a message before sending.';
    statusEl.className = 'f-status error';
    return;
  }

  const tokenEl = document.querySelector('[name="cf-turnstile-response"]');
  const token   = tokenEl ? tokenEl.value : '';
  if (!token) {
    statusEl.textContent = 'Please wait for the security check to complete.';
    statusEl.className = 'f-status error';
    return;
  }

  submitBtn.disabled = true;
  submitBtn.textContent = 'Sending…';

  try {
    const res = await fetch(FEEDBACK_SUBMIT_ENDPOINT, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        feedback_type,
        message,
        page_url: location.href,
        contact_email: contact_email || null,
        cf_turnstile_response: token,
      })
    });
    const data = await res.json();

    if (res.ok && data.success) {
      statusEl.textContent = 'Thank you. Your feedback has been sent for review and may help expand the archive.';
      statusEl.className = 'f-status success';
      submitBtn.textContent = 'Sent';
      document.getElementById('fbMessage').value = '';
      document.getElementById('fbEmail').value = '';
      trackEvent('feedback_submitted', {item_id: feedback_type});
    } else {
      throw new Error(data.error || 'Unexpected error');
    }
  } catch (err) {
    statusEl.textContent = err.message || 'Something went wrong. Please try again.';
    statusEl.className = 'f-status error';
    submitBtn.disabled = false;
    submitBtn.textContent = 'Send Feedback';
    mountTurnstile('.cf-turnstile');
  }
}

function trackEvent(eventType, extra){
  try{
    var id=sessionStorage.getItem('ff_session_id');
    if(!id){ id=Math.random().toString(36).slice(2)+Date.now().toString(36); sessionStorage.setItem('ff_session_id', id); }
    var payload=Object.assign({event_type:eventType,referring_page:location.pathname,session_id:id}, extra||{});
    fetch('https://canjzkpvjwvkbjcduaaj.supabase.co/functions/v1/submit-event', {
      method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload), keepalive:true
    }).catch(function(){});
  }catch(e){}
}


// ── Event wiring ──────────────────────────────────────────────────────────
// Previously inline on*= attributes; listeners now so script-src can drop
// 'unsafe-inline'. The journal links are delegated off a data attribute rather
// than each carrying its own handler.
(function wireUpdatesEvents() {
  const on = (sel, ev, fn) => {
    const el = document.querySelector(sel);
    if (el) el.addEventListener(ev, fn);
  };
  document.querySelectorAll('[data-track-journal]').forEach(a =>
    a.addEventListener('click', () => trackEvent('research_journal_clicked')));
  on('.feedback-trigger', 'click', () => openFeedback());
  on('#feedbackModalOverlay', 'click', e => { if (e.target.id === 'feedbackModalOverlay') closeFeedback(); });
  on('.feedback-modal-close', 'click', () => closeFeedback());
  on('.f-submit', 'click', () => submitFeedback());
})();
