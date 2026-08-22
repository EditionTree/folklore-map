(function(){
  const VISITED_KEY = 'ff_visited_legends_v1';
  const BEHAVIOUR_KEY = 'ff_behaviour_v1';
  const sectionsEl = document.getElementById('achievementSections');
  const slugify = s => String(s||'').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/&/g,' and ').replace(/[^a-z0-9]+/g,'-').replace(/^-+|-+$/g,'');
  const regionSlug = s => slugify(String(s||'').split(',').pop().trim() || s);
  const getJSON = key => { try { return JSON.parse(localStorage.getItem(key)||'{}'); } catch(e) { return {}; } };
  const visitedObj = getJSON(VISITED_KEY);
  const behaviour = getJSON(BEHAVIOUR_KEY);
  const visitedNames = new Set(Object.keys(visitedObj));
  let legends = [];
  let byName = new Map();
  const shareIndex = new Map(); // achievement id -> {a, hueDeg, shade}, for the share-card renderer

  function iconPath(a){
    return a.icon && a.icon.file ? a.icon.file : 'assets/achievements/wax-seals-v2/achievement-folklore-finder.webp';
  }

  // Shade variants so same-category badges don't look identical.
  const SHADE_VARIANTS = [ {sat:1, bright:1}, {sat:.85, bright:.93}, {sat:1.14, bright:1.07} ];

  // Tiered achievements (e.g. Visit 50 / 100 / 250 legends) share a type +
  // scope + value but climb in `n`. A later tier should stay fully hidden
  // until the previous tier in its chain is unlocked, so build that chain
  // once per section: tierKey -> items sorted by requirement, ascending.
  function tierKey(a){
    const c = a.criteria || {};
    if(c.type !== 'count') return null;
    return [c.type, c.scope || '', c.value || ''].join('|');
  }
  function tierRank(a){
    const c = a.criteria || {};
    return c.all ? Infinity : (c.n || 0);
  }
  function buildTierChains(items){
    const groups = new Map();
    items.forEach(a => {
      const key = tierKey(a);
      if(!key) return;
      if(!groups.has(key)) groups.set(key, []);
      groups.get(key).push(a);
    });
    const prevOf = new Map(); // achievement id -> previous-tier achievement
    groups.forEach(group => {
      if(group.length < 2) return;
      group.sort((x, y) => tierRank(x) - tierRank(y));
      for(let i = 1; i < group.length; i++) prevOf.set(group[i].id, group[i - 1]);
    });
    return prevOf;
  }

  function allPublicAchievements(data){
    return data.sections.flatMap(s => s.items.filter(a => !(a.availability && a.availability.status === 'draft')));
  }

  function countBy(fn){
    let n = 0;
    visitedNames.forEach(name => { const l = byName.get(name); if(l && fn(l)) n++; });
    return n;
  }

  function targetTotal(criteria){
    if(!criteria) return 1;
    if(criteria.all) {
      if(criteria.scope === 'total') return legends.length;
      if(criteria.scope === 'category') return legends.filter(l => l.category === criteria.value).length;
      if(criteria.scope === 'region') return legends.filter(l => regionSlug(l.region) === criteria.value || slugify(l.region).includes(criteria.value)).length;
    }
    return criteria.n || criteria.days || criteria.values?.length || criteria.names?.length || 1;
  }

  function evaluate(a){
    const c = a.criteria || {};
    let current = 0, target = targetTotal(c);
    if(c.type === 'count'){
      if(c.scope === 'total') current = visitedNames.size;
      if(c.scope === 'category') current = countBy(l => l.category === c.value);
      if(c.scope === 'region') current = countBy(l => regionSlug(l.region) === c.value || slugify(l.region).includes(c.value));
      if(c.scope === 'tag') current = 0;
    } else if(c.type === 'regions_all'){
      current = c.values.filter(v => [...visitedNames].some(name => { const l = byName.get(name); return l && (regionSlug(l.region) === v || slugify(l.region).includes(v)); })).length;
      target = c.values.length;
    } else if(c.type === 'category_all'){
      const cats = [...new Set(legends.map(l => l.category).filter(Boolean))];
      current = cats.filter(cat => [...visitedNames].some(name => byName.get(name)?.category === cat)).length;
      target = cats.length;
    } else if(c.type === 'specific'){
      const names = c.names || [];
      if(c.match) {
        current = [...visitedNames].some(n => slugify(n).includes(slugify(c.match))) ? 1 : 0;
      } else {
        current = names.filter(n => visitedNames.has(n)).length;
      }
      target = names.length || 1;
    } else if(c.type === 'behaviour'){
      if(c.kind === 'after_midnight') current = behaviour.afterMidnight ? 1 : 0;
      if(c.kind === 'visits') current = behaviour.mapVisits || 0;
      if(c.kind === 'streak') current = behaviour.streak || 0;
      target = c.n || c.days || 1;
    }
    const pct = target ? Math.min(100, Math.round(current / target * 100)) : 0;
    return { current, target, pct, unlocked: current >= target && target > 0 };
  }

  function visibleAchievement(a, result, prevOf){
    if(a.availability && a.availability.status === 'draft') return false;
    const mode = (a.visibility && a.visibility.locked) || (a.hidden ? 'on_unlock' : 'visible');
    if(!result.unlocked){
      if(mode === 'on_unlock') return false;
      if(mode === 'on_progress' && result.current <= 0) return false;
      // Tier gating: a later tier (e.g. the 100-legend badge) stays fully
      // hidden until the previous tier (the 50-legend badge) is unlocked.
      const prev = prevOf.get(a.id);
      if(prev && !evaluate(prev).unlocked) return false;
    }
    return true;
  }

  function renderBadge(a, hueDeg, shadeIdx){
    const r = evaluate(a);
    // Every achievement starts as a blank placeholder — real name, requirement
    // and artwork only reveal once at least one qualifying legend is found;
    // full colour only once complete.
    const state = r.unlocked ? 'unlocked' : (r.current > 0 ? 'progress' : 'not-started');
    const notStarted = state === 'not-started';
    const name = notStarted ? '???' : a.name;
    const req = notStarted ? '???' : a.req;
    const desc = notStarted ? 'Keep exploring the map to reveal this achievement.' : a.description;
    const shade = SHADE_VARIANTS[shadeIdx % SHADE_VARIANTS.length];
    const cssVars = `--hue:${hueDeg}deg;--shade-sat:${shade.sat};--shade-bright:${shade.bright}`;
    const sealHtml = notStarted
      ? `<span class="seal seal-placeholder" aria-hidden="true">?</span>`
      : `<img class="seal" src="${iconPath(a)}" alt="" loading="lazy"/>`;
    const popSealHtml = notStarted
      ? `<span class="seal seal-placeholder" aria-hidden="true">?</span>`
      : `<img src="${iconPath(a)}" alt=""/>`;
    // A share button has to be a real <button>, which can't nest inside the
    // badge's own <button> — so the badge itself is a focusable <div> (still
    // reachable by keyboard via tabindex, still triggers the CSS :focus
    // popover) rather than a <button>. It never had a click handler of its
    // own; hover/focus-revealing .badge-pop was always the only behaviour.
    return `<div class="badge ${state}" tabindex="0" role="group" aria-label="${name}" style="${cssVars}">
      ${sealHtml}
      <span class="badge-name">${name}</span>
      <span class="badge-req">${req}</span>
      ${!r.unlocked && r.current > 0 ? `<span class="badge-pct">${r.current} of ${r.target}</span>` : ''}
      <span class="badge-pop">
        ${popSealHtml}
        <span class="pop-name">${name}</span>
        <span class="pop-desc">${desc}</span>
        <span class="pop-req">${req}${!r.unlocked && r.current > 0 ? ` · ${r.current} of ${r.target}` : ''}</span>
        ${!r.unlocked && r.current > 0 ? `<span class="mini-track"><span style="width:${r.pct}%"></span></span>` : ''}
        ${r.unlocked ? `<button type="button" class="badge-share-btn" data-share-id="${a.id}">Share this seal</button><span class="badge-share-status" aria-live="polite"></span>` : ''}
      </span>
    </div>`;
  }

  function render(data){
    const publicItems = allPublicAchievements(data);
    const unlocked = publicItems.filter(a => evaluate(a).unlocked).length;
    document.getElementById('visitedCount').firstChild.nodeValue = visitedNames.size;
    document.getElementById('unlockedCount').firstChild.nodeValue = unlocked;
    document.getElementById('overallFill').style.width = publicItems.length ? Math.round(unlocked / publicItems.length * 100) + '%' : '0%';
    document.getElementById('overallNote').textContent = unlocked + ' of ' + publicItems.length + ' public achievements unlocked on this browser.';
    const totalSections = data.sections.length;
    shareIndex.clear();
    sectionsEl.innerHTML = data.sections.map((section, sectionIdx) => {
      const prevOf = buildTierChains(section.items);
      const items = section.items.filter(a => visibleAchievement(a, evaluate(a), prevOf));
      if(!items.length) return '';
      const got = items.filter(a => evaluate(a).unlocked).length;
      const hueDeg = Math.round(sectionIdx * (360 / Math.max(totalSections, 1)));
      const badges = items.map((a, i) => {
        shareIndex.set(a.id, {a, sectionTitle: section.title, hueDeg, shade: SHADE_VARIANTS[i % SHADE_VARIANTS.length]});
        return renderBadge(a, hueDeg, i);
      }).join('');
      return `<section class="section"><div class="section-head"><h2>${section.title}</h2><span class="section-count">${got} of ${items.length}</span></div><div class="badge-grid">${badges}</div></section>`;
    }).join('') || '<div class="empty">No public achievements are available yet.</div>';
  }

  // ── Shareable achievement card ──────────────────────────────────────────
  // Uses the shared renderer in /share-card.js (also used by legend pages
  // for the nearest-legend-found card and generated collection pages for
  // the collection-complete card) so all three read as the same template.
  async function renderAchievementCard(meta){
    const { a, sectionTitle, hueDeg, shade } = meta;
    return window.ShareCard.renderSealCard({
      kicker: 'ACHIEVEMENT UNLOCKED',
      subKicker: sectionTitle,
      title: a.name,
      // `req` is the literal, unambiguous "what you did" ("Visit Black
      // Shuck"); `description" is the flavour line. Neither alone is enough
      // out of context — the flavour text especially can read as a random
      // sentence with no seal, no achievement name, and no site attached.
      body: a.req ? `${a.req}. ${a.description}` : a.description,
      sealSrc: iconPath(a),
      tint: { hue: hueDeg, sat: shade.sat, bright: shade.bright },
    });
  }

  sectionsEl.addEventListener('click', async event => {
    const btn = event.target.closest('.badge-share-btn');
    if(!btn) return;
    event.preventDefault();
    const meta = shareIndex.get(btn.dataset.shareId);
    const statusEl = btn.nextElementSibling;
    if(!meta){
      if(statusEl) statusEl.textContent = "Couldn't find that achievement.";
      return;
    }
    const idleLabel = btn.textContent;
    btn.disabled = true;
    btn.textContent = 'Generating…';
    if(statusEl) statusEl.textContent = '';
    try{
      const blob = await renderAchievementCard(meta);
      const filename = `folklore-finder-${slugify(meta.a.name)}-seal.png`;
      const outcome = await window.ShareCard.shareOrDownload(
        blob, filename,
        `${meta.a.name} — Folklore Finder`,
        `I unlocked the "${meta.a.name}" achievement on Folklore Finder!`
      );
      if(statusEl){
        statusEl.textContent = outcome === 'shared' ? 'Shared!'
          : outcome === 'downloaded' ? 'Image saved'
          : '';
      }
    }catch(err){
      if(statusEl) statusEl.textContent = "Couldn't generate the image — try again.";
    }finally{
      btn.disabled = false;
      btn.textContent = idleLabel;
    }
  });

  Promise.all([
    fetch('assets/achievements/achievements.json?v=20260716a').then(r => r.json()),
    fetch('legends.json').then(r => r.json())
  ]).then(([ach, data]) => {
    legends = data.legends || [];
    byName = new Map(legends.map(l => [l.name, l]));
    render(ach);
  }).catch(() => {
    sectionsEl.innerHTML = '<div class="empty">Could not load achievements yet.</div>';
  });
})();
