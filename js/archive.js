(function(){
  function getJSON(key, fallback){
    try { return JSON.parse(localStorage.getItem(key) || 'null') || fallback; } catch(e) { return fallback; }
  }

  var bookmarks = Array.from(getJSON('folkloreMapBookmarks', []));
  var visitedObj = getJSON('ff_visited_legends_v1', {});
  var visitedNames = Object.keys(visitedObj);
  var unlockedIds = getJSON('ff_achievements_unlocked_v1', []);
  var isEmpty = !visitedNames.length && !bookmarks.length && !unlockedIds.length;

  document.getElementById('statVisited').firstChild.nodeValue = visitedNames.length;
  document.getElementById('statUnlocked').firstChild.nodeValue = unlockedIds.length;
  document.getElementById('statSaved').firstChild.nodeValue = bookmarks.length;

  // First-time visitor: replace the (currently empty) grid with a single
  // welcoming call to action rather than three separate "nothing yet" notes.
  if (isEmpty) {
    document.getElementById('archiveEmpty').hidden = false;
    document.getElementById('archiveGrid').hidden = true;
    document.getElementById('collectionProgressSection').hidden = true;
  }

  function slugify(name){
    return String(name || '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '')
      .replace(/&/g, ' and ').replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');
  }

  // Matches the recent-viewed-card look (image-backed, .recent-viewed-list
  // layout) so Saved Legends and Recently Viewed read as the same pattern.
  function renderCard(container, leg, eyebrow){
    var slug = slugify(leg.name);
    var a = document.createElement('a');
    a.className = 'recent-viewed-card';
    a.href = 'legends/' + slug;
    a.style.setProperty('--card-img', "url('legend-images/" + slug + "-hero.jpg')");
    a.innerHTML = '<span><span class="card-eyebrow"></span><span class="card-title"></span></span>';
    a.querySelector('.card-eyebrow').textContent = leg.region || eyebrow;
    a.querySelector('.card-title').textContent = leg.name;
    container.appendChild(a);
  }

  // Latest unlocked achievement — ff_achievements_unlocked_v1 is appended to in
  // unlock order (see legend-page.js), so the last entry is the most recent.
  if (unlockedIds.length) {
    fetch('assets/achievements/achievements.json?v=20260716a').then(function(r){ return r.json(); }).then(function(ach){
      // Tint each seal to its section hue, mirroring achievements.html.
      var SHADE_VARIANTS = [{sat:1,bright:1},{sat:.85,bright:.93},{sat:1.14,bright:1.07}];
      var totalSections = (ach.sections || []).length;
      var allItems = (ach.sections || []).reduce(function(acc, s, sIdx){
        var hueDeg = Math.round(sIdx * (360 / Math.max(totalSections, 1)));
        s.items.forEach(function(a, i){ var sh = SHADE_VARIANTS[i % SHADE_VARIANTS.length]; a._tint = {hue:hueDeg, sat:sh.sat, bright:sh.bright}; });
        return acc.concat(s.items);
      }, []);
      var byId = new Map(allItems.map(function(a){ return [a.id, a]; }));
      var latest = byId.get(unlockedIds[unlockedIds.length - 1]);
      if (latest) {
        var box = document.getElementById('latestSeal');
        var t = latest._tint || {hue:0, sat:1, bright:1};
        box.innerHTML = '<div class="latest-seal">'
          // The seal path comes from achievements.json and went straight into a
          // src attribute. safeAttrUrl allows only http/https and escapes it.
          + '<img src="' + SafeDOM.safeAttrUrl(latest.icon && latest.icon.file || '') + '" alt="" style="--hue:' + t.hue + 'deg;--shade-sat:' + t.sat + ';--shade-bright:' + t.bright + '"/>'
          + '<div class="latest-seal-text"><p>Latest Achievement</p><h3></h3></div>'
          + '</div>';
        box.querySelector('h3').textContent = latest.name;
      }
    }).catch(function(){});
  }

  fetch('legends.json').then(function(r){ return r.json(); }).then(function(data){
    var legends = data.legends || [];
    var byName = new Map(legends.map(function(l){ return [l.name, l]; }));

    var firstLegendBtn = document.getElementById('firstLegendBtn');
    if (firstLegendBtn) {
      firstLegendBtn.addEventListener('click', function(){
        if (!legends.length) return;
        var pick = legends[Math.floor(Math.random() * legends.length)];
        window.location.href = 'legends/' + slugify(pick.name);
      });
    }

    var savedEl = document.getElementById('savedLegends');
    var savedLegends = bookmarks.map(function(n){ return byName.get(n); }).filter(Boolean);
    if(savedLegends.length){
      savedLegends.forEach(function(l){ renderCard(savedEl, l, 'Saved'); });
    } else {
      savedEl.innerHTML = '<p class="empty-note">Nothing saved yet. Bookmark a legend from the <a href="map">map</a> or any legend page.</p>';
    }

    // Recently viewed — image-backed list rows, matching the suggested-legends
    // card style used on individual legend pages.
    var recentEl = document.getElementById('recentlyViewed');
    var recent = visitedNames
      .map(function(n){ return { name: n, last: visitedObj[n].lastVisited, leg: byName.get(n) }; })
      .filter(function(v){ return v.leg; })
      .sort(function(a, b){ return new Date(b.last) - new Date(a.last); })
      .slice(0, 3);
    if(recent.length){
      recent.forEach(function(v){
        var slug = slugify(v.leg.name);
        var a = document.createElement('a');
        a.className = 'recent-viewed-card';
        a.href = 'legends/' + slug;
        a.style.setProperty('--card-img', "url('legend-images/" + slug + "-hero.jpg')");
        a.innerHTML = '<span><span class="card-eyebrow"></span><span class="card-title"></span></span>';
        a.querySelector('.card-eyebrow').textContent = new Date(v.last).toLocaleDateString('en-GB', {day:'numeric', month:'short'});
        a.querySelector('.card-title').textContent = v.leg.name;
        recentEl.appendChild(a);
      });
    } else {
      recentEl.innerHTML = '<p class="empty-note">Visit a few legend pages and they will show up here.</p>';
    }

    var visitedSet = new Set(visitedNames);
    fetch('collections.json').then(function(r){ return r.json(); }).then(function(colData){
      var collections = colData.collections || [];
      var colEl = document.getElementById('collectionProgress');
      if(!collections.length){
        colEl.innerHTML = '<p class="empty-note">No collections available yet.</p>';
        return;
      }
      Promise.all(collections.map(function(col){
        return fetch('legends/collection/' + col.slug + '.json')
          .then(function(r){ return r.ok ? r.json() : { legends: [] }; })
          .catch(function(){ return { legends: [] }; })
          .then(function(members){ return { col: col, members: members.legends || [] }; });
      })).then(function(results){
        colEl.innerHTML = '';
        results.filter(function(r){ return r.members.length; }).forEach(function(r){
          var visitedCount = r.members.filter(function(n){ return visitedSet.has(n); }).length;
          var pct = Math.round(visitedCount / r.members.length * 100);
          var done = visitedCount === r.members.length;
          var row = document.createElement('a');
          row.className = 'collection-row' + (done ? ' done' : '');
          row.href = 'legends/collection/' + r.col.slug;
          row.setAttribute('aria-label', 'View ' + r.col.title + ' collection progress');
          row.style.setProperty('--pct', pct + '%');
          row.innerHTML = '<span class="collection-name"></span>'
            + '<span class="collection-frac">' + visitedCount + ' / ' + r.members.length + (done ? ' &#10003;' : '') + '</span>';
          row.querySelector('.collection-name').textContent = r.col.title;
          colEl.appendChild(row);
        });

        // Continuation banner: prefer the collection you're furthest into
        // (but not finished), matching the homepage's adaptive-card logic.
        // Falls back to the most recently viewed legend if no collection is
        // in progress. Only shown once there's something to continue.
        if (!isEmpty) {
          var partial = results
            .filter(function(r){ return r.members.length; })
            .map(function(r){
              var visitedCount = r.members.filter(function(n){ return visitedSet.has(n); }).length;
              return { col: r.col, visitedCount: visitedCount, total: r.members.length };
            })
            .filter(function(r){ return r.visitedCount > 0 && r.visitedCount < r.total; })
            .sort(function(a, b){ return (b.visitedCount / b.total) - (a.visitedCount / a.total); })[0];

          var banner = document.getElementById('continuationBanner');
          var text = document.getElementById('continuationText');
          var link = document.getElementById('continuationLink');
          if (partial) {
            text.textContent = 'You have discovered ' + partial.visitedCount + ' of ' + partial.total
              + ' legends in ' + partial.col.title + '.';
            link.textContent = 'Continue collection →';
            link.href = 'legends/collection/' + partial.col.slug;
            banner.hidden = false;
          } else if (recent.length) {
            text.textContent = 'Pick up where you left off with ' + recent[0].leg.name + '.';
            link.textContent = 'Continue exploring →';
            link.href = 'legends/' + slugify(recent[0].leg.name);
            banner.hidden = false;
          }
        }
      });
    });
  });
})();

/* ── Export and import ────────────────────────────────────────────────────
 * My Archive is accountless and lives only in this browser, which is a real
 * differentiator and also a real way to lose everything. The page has always
 * said so and offered nothing to do about it. This is the way out.
 *
 * Import MERGES rather than replaces, and every merge rule is idempotent, so
 * importing the same file twice is a no-op rather than something that inflates
 * visit counts or duplicates entries. Replacing would let one careless import
 * destroy progress the file does not know about.
 */
(function(){
  var FORMAT = 'folklore-finder-archive';
  var VERSION = 1;

  // Only real archive data. Device preferences (dusk mode, sidebar state, the
  // submit-prompt dismissal) are deliberately not carried between browsers.
  var KEYS = [
    'ff_visited_legends_v1',
    'folkloreMapBookmarks',
    'ff_achievements_unlocked_v1',
    'ff_behaviour_v1'
  ];

  var exportBtn = document.getElementById('archiveExportBtn');
  var importBtn = document.getElementById('archiveImportBtn');
  var fileInput = document.getElementById('archiveImportInput');
  var statusEl  = document.getElementById('archiveKeepStatus');
  if (!exportBtn || !importBtn || !fileInput || !statusEl) return;

  function read(key, fallback){
    try { return JSON.parse(localStorage.getItem(key) || 'null') || fallback; }
    catch(e) { return fallback; }
  }
  function write(key, value){
    try { localStorage.setItem(key, JSON.stringify(value)); } catch(e) {}
  }
  function say(message, ok){
    statusEl.textContent = message;
    statusEl.classList.toggle('is-error', ok === false);
    statusEl.classList.toggle('is-ok', ok === true);
  }

  // ── Export ──
  exportBtn.addEventListener('click', function(){
    var payload = { format: FORMAT, version: VERSION,
                    exported: new Date().toISOString(),
                    site: location.origin, data: {} };
    KEYS.forEach(function(k){
      var raw = localStorage.getItem(k);
      if (raw !== null) { try { payload.data[k] = JSON.parse(raw); } catch(e) {} }
    });
    var visited = Object.keys(payload.data.ff_visited_legends_v1 || {}).length;
    var saved = (payload.data.folkloreMapBookmarks || []).length;
    var seals = (payload.data.ff_achievements_unlocked_v1 || []).length;
    if (!visited && !saved && !seals) {
      say('There is nothing to export yet. Visit a legend first.', false);
      return;
    }
    var blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
    var name = 'folklore-finder-archive-' + new Date().toISOString().slice(0, 10) + '.json';
    // Same approach share-card.js already uses, so it is known to work under
    // this site's Content-Security-Policy.
    var url = URL.createObjectURL(blob);
    var link = document.createElement('a');
    link.href = url;
    link.download = name;
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(function(){ URL.revokeObjectURL(url); }, 4000);
    say('Exported ' + visited + ' visited, ' + saved + ' saved and ' + seals + ' seals to ' + name, true);
  });

  // ── Import ──
  importBtn.addEventListener('click', function(){ fileInput.click(); });

  fileInput.addEventListener('change', function(){
    var file = fileInput.files && fileInput.files[0];
    if (!file) return;
    var reader = new FileReader();
    reader.onerror = function(){ say('That file could not be read.', false); };
    reader.onload = function(){
      var added;
      try { added = merge(JSON.parse(String(reader.result))); }
      catch (err) { say(err.message, false); fileInput.value = ''; return; }
      fileInput.value = '';
      say('Added ' + added.visited + ' visited, ' + added.saved + ' saved and '
          + added.seals + ' seals. Reloading.', true);
      setTimeout(function(){ location.reload(); }, 1200);
    };
    reader.readAsText(file);
  });

  function merge(payload){
    if (!payload || payload.format !== FORMAT) {
      throw new Error('That is not a Folklore Finder archive file.');
    }
    if (Number(payload.version) > VERSION) {
      throw new Error('That file came from a newer version of the site.');
    }
    var incoming = payload.data || {};

    // Visited: earliest first visit, latest last visit, highest count. Taking
    // the max rather than summing is what makes a repeat import a no-op.
    var visited = read('ff_visited_legends_v1', {});
    var addedVisited = 0;
    Object.keys(incoming.ff_visited_legends_v1 || {}).forEach(function(name){
      var them = incoming.ff_visited_legends_v1[name] || {};
      var mine = visited[name];
      if (!mine) { visited[name] = them; addedVisited++; return; }
      visited[name] = {
        firstVisited: minDate(mine.firstVisited, them.firstVisited),
        lastVisited:  maxDate(mine.lastVisited, them.lastVisited),
        count: Math.max(Number(mine.count) || 0, Number(them.count) || 0),
        url: mine.url || them.url
      };
    });
    write('ff_visited_legends_v1', visited);

    var addedSaved = union('folkloreMapBookmarks', incoming.folkloreMapBookmarks);
    var addedSeals = union('ff_achievements_unlocked_v1', incoming.ff_achievements_unlocked_v1);

    var behaviour = read('ff_behaviour_v1', {});
    var theirs = incoming.ff_behaviour_v1 || {};
    behaviour.mapVisits = Math.max(Number(behaviour.mapVisits) || 0, Number(theirs.mapVisits) || 0);
    if (theirs.afterMidnight) behaviour.afterMidnight = true;
    write('ff_behaviour_v1', behaviour);

    return { visited: addedVisited, saved: addedSaved, seals: addedSeals };
  }

  function union(key, incoming){
    if (!Array.isArray(incoming)) return 0;
    var mine = read(key, []);
    if (!Array.isArray(mine)) mine = [];
    var seen = {}, out = [], added = 0;
    mine.concat(incoming).forEach(function(v){
      var k = String(v);
      if (seen[k]) return;
      seen[k] = 1;
      out.push(v);
    });
    added = out.length - mine.length;
    write(key, out);
    return added;
  }

  function minDate(a, b){ return pick(a, b, false); }
  function maxDate(a, b){ return pick(a, b, true); }
  function pick(a, b, wantLater){
    if (!a) return b;
    if (!b) return a;
    var later = String(a) > String(b) ? a : b;   // ISO 8601 sorts lexically
    var earlier = later === a ? b : a;
    return wantLater ? later : earlier;
  }
})();
