// Shared behaviour for the generated pages: collection indexes, collection
// detail pages, period pages and the browse page.
//
// Each of these was an inline <script> emitted by generate_pages.py, with its
// parameters baked into the source. That meant every page carried a slightly
// different script, so every page had a different CSP hash, which made
// script-src 'unsafe-inline' impossible to remove. The logic is unchanged; the
// parameters now arrive on hidden data-* elements and the code lives here,
// cached once for the whole site.
(function () {
  'use strict';

  // Collection detail pages include this script twice, because the analytics
  // parameters and the progress parameters are emitted by two different
  // functions. Guard so the beacon fires once rather than twice.
  if (window.__ffPageInit) return;
  window.__ffPageInit = true;

  function init() {
  // Selected by attribute, not by id: the two emitters each drop their own
  // element, and the first script tag runs before the second element has been
  // parsed. Waiting for the document below is what makes both visible.
  var trackEl = document.querySelector('[data-track]');
  var collEl = document.querySelector('[data-collection-slug]');
  var data = {
    track: trackEl ? trackEl.dataset.track : '',
    collectionSlug: collEl ? collEl.dataset.collectionSlug : '',
    collectionTitle: collEl ? collEl.dataset.collectionTitle : '',
  };

  // ── Analytics beacon ────────────────────────────────────────────────────
  // Mirrors trackEvent() in legend-page.js. These pages do not load that
  // script, so the same fire-and-forget POST is repeated here.
  if (data.track) {
    try {
      var payload = JSON.parse(data.track);
      var s = sessionStorage.getItem('ff_session_id');
      if (!s) {
        s = Math.random().toString(36).slice(2) + Date.now().toString(36);
        sessionStorage.setItem('ff_session_id', s);
      }
      var p = Object.assign({ referring_page: location.pathname, session_id: s }, payload);
      fetch('https://canjzkpvjwvkbjcduaaj.supabase.co/functions/v1/submit-event', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(p),
        keepalive: true,
      }).catch(function () {});
    } catch (e) {}
  }

  // Visited legends, read from the same localStorage key My Archive uses.
  function visitedSet() {
    try {
      var visited = JSON.parse(localStorage.getItem('ff_visited_legends_v1') || 'null') || {};
      return new Set(Object.keys(visited));
    } catch (e) {
      return new Set();
    }
  }

  // ── Collections landing page: per-card progress ─────────────────────────
  // One small JSON fetch per card, so cost stays proportional to the number
  // of collections shown.
  var rows = document.querySelectorAll('.col-index-row[data-slug]');
  if (rows.length) {
    var set = visitedSet();
    rows.forEach(function (row) {
      var slug = row.getAttribute('data-slug');
      fetch('collection/' + slug + '.json').then(function (r) {
        return r.json();
      }).then(function (d) {
        var members = d.legends || [];
        if (!members.length) return;
        var count = members.filter(function (n) { return set.has(n); }).length;
        var pct = Math.round(count / members.length * 100);
        var done = count === members.length;
        var prog = row.querySelector('.col-index-progress');
        var more = row.querySelector('.col-index-more');
        if (prog) {
          prog.hidden = false;
          prog.querySelector('.cip-fill').style.width = pct + '%';
          prog.querySelector('.cip-label').textContent = done
            ? 'Collection complete ✓'
            : (count + ' of ' + members.length + ' discovered');
        }
        if (more) {
          more.textContent = done
            ? 'Revisit the collection →'
            : (count > 0 ? 'Continue collection →' : 'Begin collection →');
        }
        if (done) row.classList.add('done');
      }).catch(function () {});
    });
  }

  // ── Single collection page: summary bar and share card ──────────────────
  // Pages 2+ only carry their own slice of the membership, so the full list
  // comes from the collection's own JSON rather than the DOM.
  if (data.collectionSlug) {
    var slug = data.collectionSlug;
    var title = data.collectionTitle || '';
    var set2 = visitedSet();
    fetch(slug + '.json').then(function (r) {
      return r.json();
    }).then(function (d) {
      var members = d.legends || [];
      if (!members.length) return;
      var count = members.filter(function (n) { return set2.has(n); }).length;
      var pct = Math.round(count / members.length * 100);
      var done = count === members.length;
      var el = document.querySelector('.col-progress');
      if (!el) return;
      el.hidden = false;
      el.classList.toggle('done', done);
      el.querySelector('.cip-fill').style.width = pct + '%';
      el.querySelector('.cip-label').textContent = done
        ? 'Collection complete ✓'
        : (count + ' of ' + members.length + ' discovered');

      // The share button only exists in the page-1 markup, because it needs
      // the hero photo that only page 1 renders.
      var shareBtn = el.querySelector('.col-share-btn');
      var heroImg = document.querySelector('.col-hero-media img');
      if (!shareBtn || !done || !heroImg || !window.ShareCard) return;
      shareBtn.hidden = false;
      shareBtn.addEventListener('click', function () {
        var statusEl = el.querySelector('.col-share-status');
        var idle = shareBtn.textContent;
        shareBtn.disabled = true;
        shareBtn.textContent = 'Generating…';
        if (statusEl) statusEl.textContent = '';
        window.ShareCard.renderPhotoCard({
          kicker: 'COLLECTION COMPLETE',
          subKicker: members.length + ' legends discovered',
          title: title,
          body: 'Every legend in this collection, found.',
          photoSrc: heroImg.currentSrc || heroImg.src,
        }).then(function (blob) {
          return window.ShareCard.shareOrDownload(
            blob,
            'folklore-finder-' + slug + '-collection.png',
            title + ' — complete!',
            'I completed the "' + title + '" collection on Folklore Finder!'
          );
        }).then(function (outcome) {
          if (statusEl) {
            statusEl.textContent = outcome === 'shared'
              ? 'Shared!'
              : (outcome === 'downloaded' ? 'Image saved' : '');
          }
        }).catch(function () {
          if (statusEl) statusEl.textContent = "Couldn't generate the image — try again.";
        }).then(function () {
          shareBtn.disabled = false;
          shareBtn.textContent = idle;
        });
      });
    }).catch(function () {});
  }

  // ── Browse page tabs ────────────────────────────────────────────────────
  var tabs = document.querySelectorAll('.browse-tab');
  if (tabs.length) {
    var panels = document.querySelectorAll('.browse-tab-panel');
    tabs.forEach(function (t) {
      t.addEventListener('click', function () {
        tabs.forEach(function (o) { o.classList.remove('active'); });
        panels.forEach(function (pa) { pa.classList.remove('active'); });
        t.classList.add('active');
        var panel = document.querySelector('.browse-tab-panel[data-tab-panel="' + t.dataset.tab + '"]');
        if (panel) panel.classList.add('active');
      });
    });
  }
  }

  // The first of the two script tags is parsed before the second data element
  // exists, so the work waits for the document to finish parsing.
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
