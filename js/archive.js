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
