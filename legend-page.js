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

  function flashButton(button,idleText,activeText){
    if(!button)return;
    button.textContent=activeText;
    clearTimeout(resetTimer);
    resetTimer=setTimeout(function(){
      button.textContent=idleText;
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
    // [label, url, brand colour, SVG path] — official brand marks (Simple Icons
    // paths), used in brand colours per each platform's share-button guidelines.
    var networks=[
      ['Reddit','https://www.reddit.com/submit?url='+enc(url)+'&title='+enc(shareTitle),'#FF4500','M12 0A12 12 0 0 0 0 12a12 12 0 0 0 12 12 12 12 0 0 0 12-12A12 12 0 0 0 12 0zm5.01 4.744c.688 0 1.25.561 1.25 1.249a1.25 1.25 0 0 1-2.498.056l-2.597-.547-.8 3.747c1.824.07 3.48.632 4.674 1.488.308-.309.73-.491 1.207-.491.968 0 1.754.786 1.754 1.754 0 .716-.435 1.333-1.01 1.614a3.111 3.111 0 0 1 .042.52c0 2.694-3.13 4.87-6.993 4.87-3.863 0-6.993-2.176-6.993-4.87 0-.183.015-.366.043-.534A1.748 1.748 0 0 1 4.028 12c0-.968.786-1.754 1.754-1.754.463 0 .898.196 1.207.49 1.207-.883 2.878-1.43 4.744-1.487l.885-4.182a.342.342 0 0 1 .14-.197.35.35 0 0 1 .238-.042l2.906.617a1.214 1.214 0 0 1 1.108-.701zM9.25 12C8.561 12 8 12.562 8 13.25c0 .687.561 1.248 1.25 1.248.687 0 1.248-.561 1.248-1.249 0-.688-.561-1.249-1.249-1.249zm5.5 0c-.687 0-1.248.561-1.248 1.25 0 .687.561 1.248 1.249 1.248.688 0 1.249-.561 1.249-1.249 0-.687-.562-1.249-1.25-1.249zm-5.466 3.99a.327.327 0 0 0-.231.094.33.33 0 0 0 0 .463c.842.842 2.484.913 2.961.913.477 0 2.105-.056 2.961-.913a.361.361 0 0 0 .029-.463.33.33 0 0 0-.464 0c-.547.533-1.684.73-2.512.73-.828 0-1.979-.196-2.512-.73a.326.326 0 0 0-.232-.095z'],
      ['Pinterest','https://www.pinterest.com/pin/create/button/?url='+enc(url)+'&media='+enc(shareImage)+'&description='+enc(shareTitle),'#BD081C','M12 0C5.373 0 0 5.372 0 12c0 5.084 3.163 9.426 7.627 11.174-.105-.949-.2-2.405.042-3.441.218-.937 1.407-5.965 1.407-5.965s-.359-.719-.359-1.782c0-1.668.967-2.914 2.171-2.914 1.023 0 1.518.769 1.518 1.69 0 1.029-.655 2.568-.994 3.995-.283 1.194.599 2.169 1.777 2.169 2.133 0 3.772-2.249 3.772-5.495 0-2.873-2.064-4.882-5.012-4.882-3.414 0-5.418 2.561-5.418 5.207 0 1.031.397 2.138.893 2.738a.36.36 0 0 1 .083.345c-.091.378-.293 1.194-.333 1.361-.052.22-.174.267-.402.161-1.499-.698-2.436-2.889-2.436-4.649 0-3.785 2.75-7.262 7.929-7.262 4.163 0 7.398 2.967 7.398 6.931 0 4.136-2.607 7.464-6.227 7.464-1.216 0-2.359-.632-2.75-1.378l-.748 2.853c-.271 1.043-1.002 2.35-1.492 3.146C9.57 23.812 10.763 24 12 24c6.627 0 12-5.373 12-12 0-6.628-5.373-12-12-12z'],
      ['X','https://x.com/intent/tweet?url='+enc(url)+'&text='+enc(shareTitle),'#000000','M18.901 1.153h3.68l-8.04 9.19L24 22.846h-7.406l-5.8-7.584-6.638 7.584H.474l8.6-9.83L0 1.154h7.594l5.243 6.932ZM17.61 20.644h2.039L6.486 3.24H4.298Z'],
      ['Facebook','https://www.facebook.com/sharer/sharer.php?u='+enc(url),'#1877F2','M9.101 23.691v-7.98H6.627v-3.667h2.474v-1.58c0-4.085 1.848-5.978 5.858-5.978.401 0 .955.042 1.468.103a8.68 8.68 0 0 1 1.141.195v3.325a8.623 8.623 0 0 0-.653-.036 26.805 26.805 0 0 0-.733-.009c-.707 0-1.259.096-1.675.309a1.686 1.686 0 0 0-.679.622c-.258.42-.374.995-.374 1.752v1.297h3.919l-.386 2.103-.287 1.564h-3.246v8.245C19.396 23.238 24 18.179 24 12.044c0-6.627-5.373-12-12-12s-12 5.373-12 12c0 5.628 3.874 10.35 9.101 11.647Z']
    ];
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
