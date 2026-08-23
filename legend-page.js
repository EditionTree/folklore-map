(function(){
  // ── Lightweight, privacy-conscious event tracking ──────────────────────
  // Anonymous session id (random, session-scoped, no personal data) lets
  // events from the same visit be grouped without identifying anyone.
  var EVENT_ENDPOINT='https://canjzkpvjwvkbjcduaaj.supabase.co/functions/v1/submit-event';
  function sessionId(){
    try{
      var id=sessionStorage.getItem('ff_session_id');
      if(!id){ id=Math.random().toString(36).slice(2)+Date.now().toString(36); sessionStorage.setItem('ff_session_id', id); }
      return id;
    }catch(e){ return null; }
  }
  function trackEvent(eventType, extra){
    try{
      var payload=Object.assign({
        event_type: eventType,
        referring_page: location.pathname,
        session_id: sessionId(),
      }, extra || {});
      fetch(EVENT_ENDPOINT, {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body: JSON.stringify(payload),
        keepalive: true,
      }).catch(function(){});
    }catch(e){}
  }

  function readJsonStorage(key, fallback){
    try{
      var raw=localStorage.getItem(key);
      return raw?JSON.parse(raw):fallback;
    }catch(error){
      return fallback;
    }
  }

  function writeJsonStorage(key, value){
    try{
      localStorage.setItem(key, JSON.stringify(value));
    }catch(error){}
  }

  function markLegendVisited(){
    var title=document.getElementById('legend-title')||document.querySelector('article.card h1');
    if(!title)return null;
    var name=(title.textContent||'').trim();
    if(!name)return null;

    var now=new Date();
    var visited=readJsonStorage('ff_visited_legends_v1',{});
    var previous=visited[name]||{};
    var isFirstVisit=!previous.firstVisited;
    visited[name]={
      firstVisited:previous.firstVisited||now.toISOString(),
      lastVisited:now.toISOString(),
      count:(Number(previous.count)||0)+1,
      url:location.pathname.replace(/\/$/,'')
    };
    writeJsonStorage('ff_visited_legends_v1', visited);

    var behaviour=readJsonStorage('ff_behaviour_v1',{});
    if(now.getHours()<5)behaviour.afterMidnight=true;
    writeJsonStorage('ff_behaviour_v1', behaviour);

    return isFirstVisit?name:null;
  }

  // ── Achievement toasts ──────────────────────────────────────────────────
  // Only fires on a legend's first-ever visit on this browser, so re-reading
  // a page doesn't spam notifications. Ports the same evaluation rules as
  // achievements.html so progress/unlock toasts agree with that page.
  function ensureToastStack(){
    var el=document.getElementById('achToastStack');
    if(!el){
      el=document.createElement('div');
      el.id='achToastStack';
      el.className='ach-toast-stack';
      el.setAttribute('aria-live','polite');
      document.body.appendChild(el);
    }
    return el;
  }

  function showAchievementToast(title, body, iconFile, tint){
    var stack=ensureToastStack();
    var toast=document.createElement('div');
    var isUnlock=title==='Achievement unlocked';
    toast.className='ach-toast'+(isUnlock?' unlock':'');
    if(tint){
      toast.style.setProperty('--hue', tint.hue+'deg');
      toast.style.setProperty('--shade-sat', tint.sat);
      toast.style.setProperty('--shade-bright', tint.bright);
    }
    if(iconFile){
      var iconEl=document.createElement('img');
      iconEl.className='ach-toast-icon';
      iconEl.src='/'+String(iconFile).replace(/^\/+/,'');
      iconEl.alt='';
      iconEl.setAttribute('aria-hidden','true');
      toast.appendChild(iconEl);
    }
    var textWrap=document.createElement('span'); textWrap.className='ach-toast-text';
    var titleEl=document.createElement('span'); titleEl.className='ach-toast-title'; titleEl.textContent=title;
    var bodyEl=document.createElement('span'); bodyEl.className='ach-toast-body'; bodyEl.textContent=body;
    textWrap.appendChild(titleEl); textWrap.appendChild(bodyEl);
    toast.appendChild(textWrap);

    // Clicking the toast jumps to the achievements page, wherever this page
    // happens to live (root or /legends/*) — a root-absolute link sidesteps
    // any directory-depth guesswork.
    toast.classList.add('ach-toast-clickable');
    toast.setAttribute('role','link');
    toast.setAttribute('tabindex','0');
    toast.setAttribute('aria-label',title+': '+body+'. View achievements.');
    function go(){ location.href='/achievements.html'; }
    toast.addEventListener('click', go);
    toast.addEventListener('keydown', function(e){
      if(e.key==='Enter'||e.key===' '){ e.preventDefault(); go(); }
    });

    stack.appendChild(toast);
    requestAnimationFrame(function(){ toast.classList.add('show'); });
    setTimeout(function(){
      toast.classList.remove('show');
      setTimeout(function(){ toast.remove(); }, 400);
    }, 5000);
  }

  // ── "Nearest legend found" toast ────────────────────────────────────────
  // Fires once, right after arriving here via the homepage's "Find folklore
  // near me" — the homepage's own redirect-on-success flow is left exactly
  // as tuned, so this reads the handoff from sessionStorage rather than
  // changing that flow to pause for a share prompt. Unlike the achievement
  // toast, this one isn't click-to-navigate: it holds a real "Share this
  // discovery" button, so it needs its own dismiss timer that pauses while
  // a share is in flight instead of a flat 5s auto-hide.
  function showNearMeToast(find){
    var stack=ensureToastStack();
    var toast=document.createElement('div');
    toast.className='ach-toast near-me-toast';

    var textWrap=document.createElement('span'); textWrap.className='ach-toast-text';
    var titleEl=document.createElement('span'); titleEl.className='ach-toast-title'; titleEl.textContent='Nearest legend found';
    var bodyEl=document.createElement('span'); bodyEl.className='ach-toast-body';
    bodyEl.textContent=find.name+', about '+find.distanceKm+' km away';
    textWrap.appendChild(titleEl); textWrap.appendChild(bodyEl);
    toast.appendChild(textWrap);

    var actions=document.createElement('span'); actions.className='ach-toast-actions';
    var shareBtn=document.createElement('button');
    shareBtn.type='button'; shareBtn.className='ach-toast-share-btn'; shareBtn.textContent='Share this discovery';
    var statusEl=document.createElement('span'); statusEl.className='ach-toast-share-status'; statusEl.setAttribute('aria-live','polite');
    actions.appendChild(shareBtn); actions.appendChild(statusEl);
    toast.appendChild(actions);

    var closeBtn=document.createElement('button');
    closeBtn.type='button'; closeBtn.className='ach-toast-close'; closeBtn.setAttribute('aria-label','Dismiss');
    closeBtn.textContent='×';
    toast.appendChild(closeBtn);

    stack.appendChild(toast);
    requestAnimationFrame(function(){ toast.classList.add('show'); });

    var dismissTimer=setTimeout(dismiss, 12000);
    function dismiss(){
      clearTimeout(dismissTimer);
      toast.classList.remove('show');
      setTimeout(function(){ toast.remove(); }, 400);
    }
    closeBtn.addEventListener('click', dismiss);

    shareBtn.addEventListener('click', function(){
      if(!window.ShareCard) return;
      clearTimeout(dismissTimer); // keep the toast open while a share is in flight
      var heroImg=document.querySelector('.hero-media-wrap img');
      var photoSrc=heroImg?(heroImg.currentSrc||heroImg.src):null;
      var idle=shareBtn.textContent;
      shareBtn.disabled=true; shareBtn.textContent='Generating…'; statusEl.textContent='';
      var renderP=photoSrc
        ? window.ShareCard.renderPhotoCard({
            kicker:'NEAREST LEGEND FOUND',
            subKicker: find.region||find.category||'',
            title: find.name,
            body: 'Found about '+find.distanceKm+' km from your location.',
            photoSrc: photoSrc,
          })
        : Promise.reject(new Error('no hero photo on this page'));
      renderP.then(function(blob){
        var filename='folklore-finder-'+slugify(find.name)+'-nearby.png';
        return window.ShareCard.shareOrDownload(
          blob, filename,
          find.name+', the nearest legend on Folklore Finder',
          'I found my nearest legend on Folklore Finder: '+find.name+'!'
        );
      }).then(function(outcome){
        statusEl.textContent = outcome==='shared' ? 'Shared!' : (outcome==='downloaded' ? 'Image saved' : '');
      }).catch(function(){
        statusEl.textContent="Couldn't generate the image. Try again.";
      }).then(function(){
        shareBtn.disabled=false; shareBtn.textContent=idle;
        dismissTimer=setTimeout(dismiss, 6000);
      });
    });
  }

  function slugify(s){
    return String(s||'').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g,'')
      .replace(/&/g,' and ').replace(/[^a-z0-9]+/g,'-').replace(/^-+|-+$/g,'');
  }
  function regionSlug(s){
    var parts=String(s||'').split(',');
    return slugify(parts[parts.length-1].trim()||s);
  }

  function evaluateAchievements(visitedNames, byName, legends, behaviour, criteria){
    function countBy(fn){
      var n=0;
      visitedNames.forEach(function(name){ var l=byName.get(name); if(l&&fn(l))n++; });
      return n;
    }
    function targetTotal(c){
      if(!c)return 1;
      if(c.all){
        if(c.scope==='total')return legends.length;
        if(c.scope==='category')return legends.filter(function(l){return l.category===c.value;}).length;
        if(c.scope==='region')return legends.filter(function(l){return regionSlug(l.region)===c.value||slugify(l.region).indexOf(c.value)>=0;}).length;
      }
      return c.n||c.days||(c.values&&c.values.length)||(c.names&&c.names.length)||1;
    }
    var c=criteria||{};
    var current=0, target=targetTotal(c);
    if(c.type==='count'){
      if(c.scope==='total')current=visitedNames.size;
      if(c.scope==='category')current=countBy(function(l){return l.category===c.value;});
      if(c.scope==='region')current=countBy(function(l){return regionSlug(l.region)===c.value||slugify(l.region).indexOf(c.value)>=0;});
    } else if(c.type==='regions_all'){
      current=c.values.filter(function(v){
        return Array.from(visitedNames).some(function(name){ var l=byName.get(name); return l&&(regionSlug(l.region)===v||slugify(l.region).indexOf(v)>=0); });
      }).length;
      target=c.values.length;
    } else if(c.type==='category_all'){
      var cats=Array.from(new Set(legends.map(function(l){return l.category;}).filter(Boolean)));
      current=cats.filter(function(cat){ return Array.from(visitedNames).some(function(name){ var l=byName.get(name); return l&&l.category===cat; }); }).length;
      target=cats.length;
    } else if(c.type==='specific'){
      var names=c.names||[];
      if(c.match){
        current=Array.from(visitedNames).some(function(n){return slugify(n).indexOf(slugify(c.match))>=0;})?1:0;
      } else {
        current=names.filter(function(n){return visitedNames.has(n);}).length;
      }
      target=names.length||1;
    } else if(c.type==='behaviour'){
      if(c.kind==='after_midnight')current=behaviour.afterMidnight?1:0;
      if(c.kind==='visits')current=behaviour.mapVisits||0;
      if(c.kind==='streak')current=behaviour.streak||0;
      target=c.n||c.days||1;
    }
    return {current:current, target:target, unlocked:current>=target&&target>0};
  }

  function checkAchievementToasts(visitedLegendName){
    Promise.all([
      fetch('/assets/achievements/achievements.json?v=20260716a').then(function(r){return r.json();}),
      fetch('/legends-index.json').then(function(r){return r.json();})
    ]).then(function(results){
      var achData=results[0], legendData=results[1];
      var legends=legendData.legends||[];
      var byName=new Map(legends.map(function(l){return [l.name, l];}));
      var visitedObj=readJsonStorage('ff_visited_legends_v1',{});
      var visitedNames=new Set(Object.keys(visitedObj));
      var behaviour=readJsonStorage('ff_behaviour_v1',{});
      var visitedLegend=byName.get(visitedLegendName);

      // Tint each seal to its section's hue, mirroring achievements.html
      // (hueDeg = sectionIdx * 360/totalSections; per-item shade variation).
      var SHADE_VARIANTS=[{sat:1,bright:1},{sat:.85,bright:.93},{sat:1.14,bright:1.07}];
      var totalSections=(achData.sections||[]).length;
      var allItems=(achData.sections||[]).reduce(function(acc, s, sIdx){
        var hueDeg=Math.round(sIdx*(360/Math.max(totalSections,1)));
        var visible=s.items.filter(function(a){ return !(a.availability&&a.availability.status==='draft'); });
        visible.forEach(function(a, i){
          a._tint={hue:hueDeg, sat:SHADE_VARIANTS[i%SHADE_VARIANTS.length].sat, bright:SHADE_VARIANTS[i%SHADE_VARIANTS.length].bright};
        });
        return acc.concat(visible);
      }, []);

      var previouslyUnlocked=new Set(readJsonStorage('ff_achievements_unlocked_v1',[]));
      var nowUnlocked=[];
      var bestProgress=null;

      allItems.forEach(function(a){
        var r=evaluateAchievements(visitedNames, byName, legends, behaviour, a.criteria);
        if(r.unlocked){
          nowUnlocked.push(a.id);
          if(!previouslyUnlocked.has(a.id)){
            var sealFile=a.icon&&a.icon.file?a.icon.file:'';
            showAchievementToast('Achievement unlocked', a.name, sealFile, a._tint);
            trackEvent('achievement_unlocked', {item_id: a.id});
          }
          return;
        }
        // Progress toast: only for achievements this specific visit plausibly
        // moved (count-by-category/region matching the legend just opened).
        var c=a.criteria||{};
        if(c.type==='count'&&visitedLegend&&r.current>0){
          var relevant=(c.scope==='category'&&visitedLegend.category===c.value)
            || (c.scope==='region'&&(regionSlug(visitedLegend.region)===c.value||slugify(visitedLegend.region).indexOf(c.value)>=0));
          if(relevant&&(!bestProgress||r.current/r.target>bestProgress.r.current/bestProgress.r.target)){
            bestProgress={a:a, r:r};
          }
        }
      });

      // Preserve unlock order (append-only) rather than overwriting positionally,
      // so the last entry is always the most recently unlocked achievement —
      // used by My Archive to show the latest seal earned.
      var newlyUnlocked=nowUnlocked.filter(function(id){return !previouslyUnlocked.has(id);});
      var orderedUnlocked=Array.from(previouslyUnlocked).concat(newlyUnlocked);
      writeJsonStorage('ff_achievements_unlocked_v1', orderedUnlocked);
      if(!newlyUnlocked.length && bestProgress){
        var progressSeal=bestProgress.a.icon&&bestProgress.a.icon.file?bestProgress.a.icon.file:'';
        showAchievementToast('Achievement progress', bestProgress.a.name+', '+bestProgress.r.current+'/'+bestProgress.r.target+' legends discovered', progressSeal, bestProgress.a._tint);
        trackEvent('achievement_progress', {item_id: bestProgress.a.id});
      }
    }).catch(function(){ /* Achievement data unavailable — fail silently */ });
  }

  var pageTitle=document.getElementById('legend-title')||document.querySelector('article.card h1');
  if(pageTitle){
    trackEvent('legend_viewed', {legend_name: (pageTitle.textContent||'').trim()});
  }

  var firstVisitName=markLegendVisited();
  if(firstVisitName) checkAchievementToasts(firstVisitName);

  // "Find folklore near me" hands off here via sessionStorage rather than a
  // URL param, so it survives the redirect without cluttering the URL. Read
  // once and clear immediately so it can never fire again on a reload or a
  // later visit to this same page.
  (function checkNearMeArrival(){
    try{
      var raw=sessionStorage.getItem('ff_near_me_find');
      if(!raw) return;
      sessionStorage.removeItem('ff_near_me_find');
      var find=JSON.parse(raw);
      var pageName=pageTitle?(pageTitle.textContent||'').trim():'';
      if(find&&find.name&&find.name===pageName) showNearMeToast(find);
    }catch(e){}
  })();

  // Of the 6 related-legend candidates the page ships (see generate_pages.py),
  // show the 3 not yet in ff_visited_legends_v1 first, keeping each group's
  // original relevance order — steers a returning visitor toward something
  // new rather than the same 3 cards every time they open this page.
  (function prioritizeUnvisitedRelated(){
    try{
      var grid=document.querySelector('.related-grid');
      if(!grid)return;
      var cards=Array.from(grid.querySelectorAll('.related-card'));
      if(cards.length<=3)return;
      var visited=readJsonStorage('ff_visited_legends_v1',{});
      function isVisited(card){
        var nameEl=card.querySelector('.related-name');
        var name=nameEl?nameEl.textContent.trim():'';
        return !!visited[name];
      }
      var unvisited=cards.filter(function(c){return !isVisited(c);});
      var alreadyVisited=cards.filter(isVisited);
      var chosen=unvisited.concat(alreadyVisited).slice(0,3);
      cards.forEach(function(c){c.classList.add('extra');});
      chosen.forEach(function(c){c.classList.remove('extra');});
    }catch(e){}
  })();

  var mapElement=document.getElementById('miniMap');
  if(mapElement&&window.L){
    var latitude=Number(mapElement.dataset.lat);
    var longitude=Number(mapElement.dataset.lng);
    var colour=mapElement.dataset.colour||'#2d6a8a';
    var initial=(mapElement.dataset.initial||'?').slice(0,1);
    var miniMap=L.map(mapElement,{
      zoomControl:true,
      scrollWheelZoom:false,
      dragging:true,
      doubleClickZoom:false,
      boxZoom:false,
      keyboard:false
    }).setView([latitude,longitude],8);

    L.tileLayer('https://tiles.stadiamaps.com/tiles/stamen_terrain/{z}/{x}/{y}{r}.png?api_key=89e39892-dad3-41e7-89e6-fa69ac42bb85',{
      attribution:'&copy; Stadia Maps, Stamen Design, OpenStreetMap',
      maxZoom:18
    }).addTo(miniMap);

    var marker=L.divIcon({
      className:'legend-marker',
      html:'<div class="legend-pin" style="--marker-colour:'+colour+'"><span>'+initial+'</span></div>',
      iconSize:[34,34],
      iconAnchor:[17,34]
    });
    L.marker([latitude,longitude],{icon:marker,keyboard:false}).addTo(miniMap);
  }

  var canonical=document.querySelector('link[rel=canonical]');
  var url=canonical?canonical.href:location.href;
  var copyButton=document.getElementById('copyLinkBtn');
  var shareButton=document.getElementById('webShareBtn');
  var status=document.getElementById('shareStatus');
  var resetTimer=0;

  function announce(message){
    if(status)status.textContent=message;
  }

  // Writes the label span, not the button's textContent: these buttons also
  // hold an inline Lucide icon, and a textContent write would delete it.
  // Falls back to the button itself for any markup without the span.
  function flashButton(button,idleText,activeText){
    if(!button)return;
    var label=button.querySelector('.btn-label')||button;
    label.textContent=activeText;
    clearTimeout(resetTimer);
    resetTimer=setTimeout(function(){
      label.textContent=idleText;
    },1800);
  }

  function markCopied(){
    flashButton(copyButton,'Copy link','Copied');
    announce('Link copied');
  }

  function fallbackCopy(){
    try{
      var textArea=document.createElement('textarea');
      textArea.value=url;
      textArea.setAttribute('readonly','');
      textArea.style.position='absolute';
      textArea.style.left='-9999px';
      document.body.appendChild(textArea);
      textArea.select();
      document.execCommand('copy');
      document.body.removeChild(textArea);
      markCopied();
      return Promise.resolve(true);
    }catch(error){
      announce("Couldn't copy. Press Ctrl+C to copy the address.");
      return Promise.resolve(false);
    }
  }

  function copyLink(){
    if(navigator.clipboard&&navigator.clipboard.writeText&&window.isSecureContext){
      return navigator.clipboard.writeText(url).then(function(){
        markCopied();
        return true;
      }).catch(function(){
        return fallbackCopy();
      });
    }
    return fallbackCopy();
  }

  if(copyButton){
    copyButton.addEventListener('click',function(){
      copyLink();
    });
  }

  if(shareButton){
    // Build an explicit share menu (works on desktop AND mobile, unlike the
    // Web Share API which is absent on most desktop browsers).
    shareButton.hidden=false;
    function metaContent(prop){
      var m=document.querySelector('meta[property="'+prop+'"]');
      return m?m.getAttribute('content'):'';
    }
    var shareTitle=metaContent('og:title')||document.title;
    var shareImage=metaContent('og:image');
    var enc=encodeURIComponent;
    // Network list comes from share-card.js, which every page carrying a share
    // control already loads. This file used to hold its own copy of the brand
    // paths; two copies of an icon set is how one of them silently goes stale.
    if(!window.ShareCard || !window.ShareCard.shareNetworks) return;
    var networks = window.ShareCard.shareNetworks({
      url: url, title: shareTitle, text: shareTitle, image: shareImage
    }).map(function(n){ return [n.label, n.href, n.colour, n.path]; });
    var wrap=document.createElement('span');
    wrap.className='share-wrap';
    shareButton.parentNode.insertBefore(wrap,shareButton);
    wrap.appendChild(shareButton);
    var menu=document.createElement('div');
    menu.className='share-menu';
    menu.setAttribute('role','menu');
    menu.hidden=true;
    var sheetHead=document.createElement('p');
    sheetHead.className='share-menu-head';
    sheetHead.textContent='Share this legend';
    menu.appendChild(sheetHead);
    networks.forEach(function(n){
      var a=document.createElement('a');
      a.className='share-menu-item';
      a.setAttribute('role','menuitem');
      a.href=n[1];
      a.target='_blank';
      a.rel='noopener noreferrer';
      a.innerHTML='<svg class="share-ico" viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><path fill="'+n[2]+'" d="'+n[3]+'"></path></svg><span>'+n[0]+'</span>';
      menu.appendChild(a);
    });
    wrap.appendChild(menu);
    // Backdrop for the mobile bottom-sheet (hidden on desktop via CSS).
    var backdrop=document.createElement('div');
    backdrop.className='share-backdrop';
    backdrop.hidden=true;
    document.body.appendChild(backdrop);
    backdrop.addEventListener('click',function(){ closeMenu(); });
    shareButton.setAttribute('aria-haspopup','true');
    shareButton.setAttribute('aria-expanded','false');
    function onDocClick(e){ if(!wrap.contains(e.target)) closeMenu(); }
    function onKey(e){ if(e.key==='Escape'){ closeMenu(); shareButton.focus(); } }
    function openMenu(){
      menu.hidden=false;
      backdrop.hidden=false;
      shareButton.setAttribute('aria-expanded','true');
      // defer so the click that opened the menu doesn't immediately close it
      setTimeout(function(){
        document.addEventListener('click',onDocClick);
        document.addEventListener('keydown',onKey);
      },0);
    }
    function closeMenu(){
      menu.hidden=true;
      backdrop.hidden=true;
      shareButton.setAttribute('aria-expanded','false');
      document.removeEventListener('click',onDocClick);
      document.removeEventListener('keydown',onKey);
    }
    shareButton.addEventListener('click',function(){
      if(menu.hidden){ openMenu(); } else { closeMenu(); }
    });
    menu.addEventListener('click',function(e){
      if(e.target.closest('.share-menu-item')) closeMenu();
    });
  }
})();
