/* Shared shareable-card renderer — used by achievements.html (achievement
 * unlock), legend pages (nearest-legend-found, via legend-page.js) and
 * generated collection pages (collection-complete, via generate_pages.py's
 * inline scripts). One canvas template so all three read as the same
 * "artifact," not three different designs.
 *
 * Renders a 1080x1080 PNG entirely client-side — the site is static with no
 * server to generate personalised per-visitor images — then hands it to the
 * native share sheet where available, falling back to a plain download.
 *
 * Every card carries the site name and a one-line explainer, and callers
 * should always pass a `body` that says literally what happened (not just
 * mood-setting flavour text): shared out of context, the card has no
 * surrounding page to lean on.
 */
window.ShareCard = (function(){
  const CARD_SIZE = 1080;
  const FRAME_SRC = '/assets/ornaments/generated-variants/oak-branch-frame-v1.png';
  const CHART_SRC = '/hero-nautical-chart.jpg';

  function loadImage(src){
    // No crossOrigin attribute — every image this loads is same-origin, and
    // setting it unnecessarily risks the load failing if the CDN doesn't
    // send CORS headers on static assets (canvas only taints on an actual
    // cross-origin draw, which never happens here).
    return new Promise((resolve, reject) => {
      const img = new Image();
      img.onload = () => resolve(img);
      img.onerror = reject;
      img.src = src;
    });
  }

  // Two brand assets shared by every card variant, cached after first load.
  let framePromise, chartPromise;
  function loadFrame(){ return framePromise || (framePromise = loadImage(FRAME_SRC)); }
  function loadChart(){ return chartPromise || (chartPromise = loadImage(CHART_SRC)); }

  function drawCoverImage(ctx, img, x, y, w, h){
    const scale = Math.max(w / img.width, h / img.height);
    const dw = img.width * scale, dh = img.height * scale;
    ctx.drawImage(img, x + (w - dw) / 2, y + (h - dh) / 2, dw, dh);
  }

  function wrapCanvasText(ctx, text, maxWidth){
    const words = String(text || '').split(/\s+/).filter(Boolean);
    const lines = [];
    let line = '';
    words.forEach(word => {
      const test = line ? line + ' ' + word : word;
      if(ctx.measureText(test).width > maxWidth && line){
        lines.push(line);
        line = word;
      } else {
        line = test;
      }
    });
    if(line) lines.push(line);
    return lines;
  }


  // ── Generic chrome ──────────────────────────────────────────────────────
  // Background, frame, kicker, headline, body copy and the site URL — the
  // part every card variant shares. Callers draw their own centerpiece (a
  // tinted seal, a circular photo medallion, …) into the gap this leaves
  // between subKicker and the headline, then call drawFrame() last.
  async function drawChrome(ctx, { kicker, subKicker, title, body }){
    const chart = await loadChart();

    // Parchment base, then the nautical chart worked in at low opacity so
    // the card reads as "a page from the atlas," not a plain text card.
    const bg = ctx.createLinearGradient(0, 0, 0, CARD_SIZE);
    bg.addColorStop(0, '#e8dcc5');
    bg.addColorStop(0.65, '#f6f1e6');
    bg.addColorStop(1, '#eadfc9');
    ctx.fillStyle = bg;
    ctx.fillRect(0, 0, CARD_SIZE, CARD_SIZE);
    ctx.save();
    ctx.globalAlpha = 0.24;
    drawCoverImage(ctx, chart, 0, 0, CARD_SIZE, CARD_SIZE);
    ctx.restore();
    // Warm the centre back up over the chart so text stays legible —
    // darkest at the frame edge, clear in the middle where the art sits.
    const vignette = ctx.createRadialGradient(
      CARD_SIZE / 2, CARD_SIZE / 2, CARD_SIZE * 0.28,
      CARD_SIZE / 2, CARD_SIZE / 2, CARD_SIZE * 0.72
    );
    vignette.addColorStop(0, 'rgba(246,241,230,0)');
    vignette.addColorStop(1, 'rgba(232,220,197,.85)');
    ctx.fillStyle = vignette;
    ctx.fillRect(0, 0, CARD_SIZE, CARD_SIZE);

    // No gilded piping here. It used to be drawn inset 120px, but the oak
    // frame is the topmost layer and its leaves reach ~180px in, so the mat
    // line was partly buried under them and read as a mistake rather than a
    // border. The frame is the border.

    ctx.textAlign = 'center';

    // Safe interior: measured from the actual frame PNG (its leafy border
    // is organic, not a uniform band — stray leaf tips reach up to ~180px
    // deep at 1080-canvas scale on every side). Keep all text within
    // roughly y=205..900 and +/-170px margin either side of center.

    // Kicker.
    ctx.fillStyle = '#c4622a';
    ctx.font = '600 26px Marcellus, serif';
    ctx.fillText(`FOLKLORE FINDER · ${kicker}`, CARD_SIZE / 2, 210);
    if(subKicker){
      ctx.fillStyle = '#5a4632';
      ctx.font = 'italic 24px Spectral, serif';
      ctx.fillText(subKicker, CARD_SIZE / 2, 244);
    }

    // Headline — drawn after the caller's centerpiece, so this just marks
    // the baseline it renders at.
    const titleY = 712;
    ctx.fillStyle = '#3f3023';
    ctx.font = '400 60px Marcellus, serif';
    ctx.fillText(title, CARD_SIZE / 2, titleY);

    let afterBodyY = titleY + 36;
    if(body){
      ctx.fillStyle = '#5a4632';
      ctx.font = '27px Spectral, serif';
      const bodyLines = wrapCanvasText(ctx, body, CARD_SIZE - 380);
      let bodyY = titleY + 46;
      bodyLines.slice(0, 2).forEach(line => {
        ctx.fillText(line, CARD_SIZE / 2, bodyY);
        bodyY += 28;
      });
      afterBodyY = bodyY;
    }

    // Site explainer — the copy above says what happened; this says what it
    // happened *on*, for a viewer with zero context.
    ctx.fillStyle = '#8a7256';
    ctx.font = 'italic 19px Spectral, serif';
    ctx.fillText('An interactive folklore map of Britain & Ireland', CARD_SIZE / 2, afterBodyY + 12);

    // Divider + site URL.
    const dividerY = afterBodyY + 26;
    ctx.strokeStyle = 'rgba(176,144,96,.7)';
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.moveTo(CARD_SIZE / 2 - 70, dividerY);
    ctx.lineTo(CARD_SIZE / 2 + 70, dividerY);
    ctx.stroke();
    ctx.fillStyle = '#c4622a';
    ctx.font = '600 24px Marcellus, serif';
    ctx.fillText('folklorefinder.uk', CARD_SIZE / 2, dividerY + 26);

    // Deliberately NOT drawing the oak-branch frame here — it has to stay
    // the true topmost layer over each card variant's own centerpiece, so
    // callers draw it last via drawFrame().
  }

  async function drawFrame(ctx){
    const frame = await loadFrame();
    // Its centre is transparent, so this only ever reads as a decorative
    // border around whatever the caller already drew.
    ctx.drawImage(frame, 0, 0, CARD_SIZE, CARD_SIZE);
  }

  // Shared centerpiece geometry — every variant places its medallion at the
  // same spot, so the template reads consistently across card types.
  const MEDALLION_SIZE = 400;
  const MEDALLION_X = (CARD_SIZE - MEDALLION_SIZE) / 2;
  const MEDALLION_Y = 254;

  function drawGlow(ctx, colorRgb){
    const cx = CARD_SIZE / 2, cy = MEDALLION_Y + MEDALLION_SIZE / 2;
    const glow = ctx.createRadialGradient(
      cx, cy, MEDALLION_SIZE * 0.15,
      cx, cy, MEDALLION_SIZE * 0.85
    );
    glow.addColorStop(0, `rgba(${colorRgb},.45)`);
    glow.addColorStop(1, `rgba(${colorRgb},0)`);
    ctx.fillStyle = glow;
    ctx.fillRect(0, 0, CARD_SIZE, CARD_SIZE);
  }

  // Wax-seal centerpiece: the seal artwork itself is already circular (with
  // transparent corners), tinted per its achievement section — mirrors the
  // CSS .seal filter on achievements.html.
  function drawSealMedallion(ctx, sealImg, tint){
    drawGlow(ctx, '196,98,42');
    ctx.save();
    ctx.shadowColor = 'rgba(44,31,14,.4)';
    ctx.shadowBlur = 30;
    ctx.shadowOffsetY = 14;
    if(tint && 'filter' in ctx){
      ctx.filter = `hue-rotate(${tint.hue}deg) saturate(${tint.sat}) brightness(${tint.bright})`;
    }
    ctx.drawImage(sealImg, MEDALLION_X, MEDALLION_Y, MEDALLION_SIZE, MEDALLION_SIZE);
    ctx.restore();
  }

  // Photo centerpiece (nearest-legend, collection-complete): a real
  // photograph, so no hue tint — clipped to a circle with a thin gold ring,
  // like a coin or medallion rather than a wax impression.
  function drawPhotoMedallion(ctx, img){
    drawGlow(ctx, '176,144,96');
    const cx = CARD_SIZE / 2, cy = MEDALLION_Y + MEDALLION_SIZE / 2, r = MEDALLION_SIZE / 2;
    ctx.save();
    ctx.shadowColor = 'rgba(44,31,14,.4)';
    ctx.shadowBlur = 26;
    ctx.shadowOffsetY = 12;
    ctx.beginPath();
    ctx.arc(cx, cy, r, 0, Math.PI * 2);
    ctx.fillStyle = '#3f3023'; // shadow needs an opaque fill to cast from
    ctx.fill();
    ctx.restore();

    ctx.save();
    ctx.beginPath();
    ctx.arc(cx, cy, r, 0, Math.PI * 2);
    ctx.clip();
    drawCoverImage(ctx, img, MEDALLION_X, MEDALLION_Y, MEDALLION_SIZE, MEDALLION_SIZE);
    ctx.restore();

    ctx.beginPath();
    ctx.arc(cx, cy, r - 1.5, 0, Math.PI * 2);
    ctx.lineWidth = 5;
    ctx.strokeStyle = '#b09060';
    ctx.stroke();
    ctx.beginPath();
    ctx.arc(cx, cy, r - 5, 0, Math.PI * 2);
    ctx.lineWidth = 1.5;
    ctx.strokeStyle = 'rgba(63,48,35,.35)';
    ctx.stroke();
  }

  async function newCardCanvas(){
    await (document.fonts && document.fonts.ready ? document.fonts.ready : Promise.resolve());
    const canvas = document.createElement('canvas');
    canvas.width = CARD_SIZE;
    canvas.height = CARD_SIZE;
    return canvas;
  }

  async function renderSealCard({ kicker, subKicker, title, body, sealSrc, tint }){
    const [canvas, sealImg] = await Promise.all([newCardCanvas(), loadImage(sealSrc)]);
    const ctx = canvas.getContext('2d');
    await drawChrome(ctx, { kicker, subKicker, title, body });
    drawSealMedallion(ctx, sealImg, tint);
    await drawFrame(ctx);
    return new Promise(resolve => canvas.toBlob(resolve, 'image/png'));
  }

  async function renderPhotoCard({ kicker, subKicker, title, body, photoSrc }){
    const [canvas, photoImg] = await Promise.all([newCardCanvas(), loadImage(photoSrc)]);
    const ctx = canvas.getContext('2d');
    await drawChrome(ctx, { kicker, subKicker, title, body });
    drawPhotoMedallion(ctx, photoImg);
    await drawFrame(ctx);
    return new Promise(resolve => canvas.toBlob(resolve, 'image/png'));
  }

  async function shareOrDownload(blob, filename, shareTitle, shareText){
    if(navigator.canShare){
      try{
        const file = new File([blob], filename, { type: 'image/png' });
        if(navigator.canShare({ files: [file] })){
          await navigator.share({ files: [file], title: shareTitle, text: shareText });
          return 'shared';
        }
      }catch(err){
        if(err && err.name === 'AbortError') return 'cancelled';
        // fall through to download on any other failure
      }
    }
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 4000);
    return 'downloaded';
  }



  // ── Share dialog ──────────────────────────────────────────────────────
  // "Share this seal" used to generate the card and drop it straight into
  // Downloads, with link buttons tacked on underneath. The person never saw
  // what they were sharing and never got a choice. This shows the card, then
  // offers the ways out.
  //
  // One network list for the whole site. legend-page.js had its own copy of
  // these brand paths; it now reads this one.
  function shareNetworks(c){
    var enc = encodeURIComponent;
    // [label, brand colour, Simple Icons path] used in brand colours per each
    // platform's own share-button guidelines.
    return [
      { label: 'Reddit', colour: '#FF4500',
        href: 'https://www.reddit.com/submit?url=' + enc(c.url) + '&title=' + enc(c.title),
        path: 'M12 0A12 12 0 0 0 0 12a12 12 0 0 0 12 12 12 12 0 0 0 12-12A12 12 0 0 0 12 0zm5.01 4.744c.688 0 1.25.561 1.25 1.249a1.25 1.25 0 0 1-2.498.056l-2.597-.547-.8 3.747c1.824.07 3.48.632 4.674 1.488.308-.309.73-.491 1.207-.491.968 0 1.754.786 1.754 1.754 0 .716-.435 1.333-1.01 1.614a3.111 3.111 0 0 1 .042.52c0 2.694-3.13 4.87-6.993 4.87-3.863 0-6.993-2.176-6.993-4.87 0-.183.015-.366.043-.534A1.748 1.748 0 0 1 4.028 12c0-.968.786-1.754 1.754-1.754.463 0 .898.196 1.207.49 1.207-.883 2.878-1.43 4.744-1.487l.885-4.182a.342.342 0 0 1 .14-.197.35.35 0 0 1 .238-.042l2.906.617a1.214 1.214 0 0 1 1.108-.701zM9.25 12C8.561 12 8 12.562 8 13.25c0 .687.561 1.248 1.25 1.248.687 0 1.248-.561 1.248-1.249 0-.688-.561-1.249-1.249-1.249zm5.5 0c-.687 0-1.248.561-1.248 1.25 0 .687.561 1.248 1.249 1.248.688 0 1.249-.561 1.249-1.249 0-.687-.562-1.249-1.25-1.249zm-5.466 3.99a.327.327 0 0 0-.231.094.33.33 0 0 0 0 .463c.842.842 2.484.913 2.961.913.477 0 2.105-.056 2.961-.913a.361.361 0 0 0 .029-.463.33.33 0 0 0-.464 0c-.547.533-1.684.73-2.512.73-.828 0-1.979-.196-2.512-.73a.326.326 0 0 0-.232-.095z' },
      { label: 'Pinterest', colour: '#BD081C',
        href: 'https://www.pinterest.com/pin/create/button/?url=' + enc(c.url) + '&media=' + enc(c.image || '') + '&description=' + enc(c.title),
        path: 'M12 0C5.373 0 0 5.372 0 12c0 5.084 3.163 9.426 7.627 11.174-.105-.949-.2-2.405.042-3.441.218-.937 1.407-5.965 1.407-5.965s-.359-.719-.359-1.782c0-1.668.967-2.914 2.171-2.914 1.023 0 1.518.769 1.518 1.69 0 1.029-.655 2.568-.994 3.995-.283 1.194.599 2.169 1.777 2.169 2.133 0 3.772-2.249 3.772-5.495 0-2.873-2.064-4.882-5.012-4.882-3.414 0-5.418 2.561-5.418 5.207 0 1.031.397 2.138.893 2.738a.36.36 0 0 1 .083.345c-.091.378-.293 1.194-.333 1.361-.052.22-.174.267-.402.161-1.499-.698-2.436-2.889-2.436-4.649 0-3.785 2.75-7.262 7.929-7.262 4.163 0 7.398 2.967 7.398 6.931 0 4.136-2.607 7.464-6.227 7.464-1.216 0-2.359-.632-2.75-1.378l-.748 2.853c-.271 1.043-1.002 2.35-1.492 3.146C9.57 23.812 10.763 24 12 24c6.627 0 12-5.373 12-12 0-6.628-5.373-12-12-12z' },
      { label: 'X', colour: '#000000',
        href: 'https://x.com/intent/tweet?url=' + enc(c.url) + '&text=' + enc(c.text || c.title),
        path: 'M18.901 1.153h3.68l-8.04 9.19L24 22.846h-7.406l-5.8-7.584-6.638 7.584H.474l8.6-9.83L0 1.154h7.594l5.243 6.932ZM17.61 20.644h2.039L6.486 3.24H4.298Z' },
      { label: 'WhatsApp', colour: '#25D366',
        href: 'https://wa.me/?text=' + enc((c.text || c.title) + ' ' + c.url),
        path: 'M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.247-.694.247-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893A11.821 11.821 0 0020.885 3.488' },
      { label: 'Facebook', colour: '#1877F2',
        href: 'https://www.facebook.com/sharer/sharer.php?u=' + enc(c.url),
        path: 'M9.101 23.691v-7.98H6.627v-3.667h2.474v-1.58c0-4.085 1.848-5.978 5.858-5.978.401 0 .955.042 1.468.103a8.68 8.68 0 0 1 1.141.195v3.325a8.623 8.623 0 0 0-.653-.036 26.805 26.805 0 0 0-.733-.009c-.707 0-1.259.096-1.675.309a1.686 1.686 0 0 0-.679.622c-.258.42-.374.995-.374 1.752v1.297h3.919l-.386 2.103-.287 1.564h-3.246v8.245C19.396 23.238 24 18.179 24 12.044c0-6.627-5.373-12-12-12s-12 5.373-12 12c0 5.628 3.874 10.35 9.101 11.647Z' }
    ];
  }

  function openShareDialog(opts){
    var previousFocus = document.activeElement;
    var objectUrl = opts.blob ? URL.createObjectURL(opts.blob) : '';

    var overlay = document.createElement('div');
    overlay.className = 'sharecard-overlay';
    overlay.setAttribute('role', 'dialog');
    overlay.setAttribute('aria-modal', 'true');
    overlay.setAttribute('aria-label', opts.heading || 'Share');

    var panel = document.createElement('div');
    panel.className = 'sharecard-panel';
    overlay.appendChild(panel);

    var close = document.createElement('button');
    close.type = 'button';
    close.className = 'sharecard-close';
    close.setAttribute('aria-label', 'Close');
    close.innerHTML = '&times;';
    panel.appendChild(close);

    var head = document.createElement('p');
    head.className = 'sharecard-head';
    head.textContent = opts.heading || 'Share';
    panel.appendChild(head);

    if(objectUrl){
      var img = document.createElement('img');
      img.className = 'sharecard-preview';
      img.src = objectUrl;
      img.alt = opts.previewAlt || 'Preview of the share image';
      panel.appendChild(img);
    }

    var actions = document.createElement('div');
    actions.className = 'sharecard-actions';
    panel.appendChild(actions);

    // The native sheet is the only route that can carry the image itself, so
    // it leads where the device offers it. Everything else shares a link.
    var canNative = !!(opts.blob && navigator.canShare && window.File &&
      (function(){
        try { return navigator.canShare({ files: [new File([opts.blob], opts.filename, { type: 'image/png' })] }); }
        catch(e){ return false; }
      })());
    if(canNative){
      var nativeBtn = document.createElement('button');
      nativeBtn.type = 'button';
      nativeBtn.className = 'sharecard-btn sharecard-btn-primary';
      nativeBtn.textContent = 'Share image';
      nativeBtn.addEventListener('click', function(){
        var file = new File([opts.blob], opts.filename, { type: 'image/png' });
        navigator.share({ files: [file], title: opts.title, text: opts.text }).catch(function(){});
      });
      actions.appendChild(nativeBtn);
    }

    var dl = document.createElement('a');
    dl.className = 'sharecard-btn' + (canNative ? '' : ' sharecard-btn-primary');
    dl.textContent = 'Download image';
    dl.href = objectUrl;
    dl.download = opts.filename || 'folklore-finder.png';
    actions.appendChild(dl);

    var orLine = document.createElement('p');
    orLine.className = 'sharecard-or';
    orLine.textContent = 'or share a link';
    panel.appendChild(orLine);

    var row = document.createElement('div');
    row.className = 'sharecard-networks';
    shareNetworks({ url: opts.url, title: opts.title, text: opts.text, image: opts.image })
      .forEach(function(n){
        var a = document.createElement('a');
        a.className = 'sharecard-net';
        a.href = n.href;
        a.target = '_blank';
        a.rel = 'noopener noreferrer';
        a.title = n.label;
        a.innerHTML = '<svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true">'
          + '<path fill="' + n.colour + '" d="' + n.path + '"></path></svg>'
          + '<span>' + n.label + '</span>';
        row.appendChild(a);
      });
    panel.appendChild(row);

    function shut(){
      document.removeEventListener('keydown', onKey);
      overlay.remove();
      if(objectUrl) setTimeout(function(){ URL.revokeObjectURL(objectUrl); }, 4000);
      if(previousFocus && previousFocus.focus) previousFocus.focus();
    }
    function onKey(e){ if(e.key === 'Escape') shut(); }
    close.addEventListener('click', shut);
    overlay.addEventListener('click', function(e){ if(e.target === overlay) shut(); });
    document.addEventListener('keydown', onKey);

    document.body.appendChild(overlay);
    close.focus();
    return shut;
  }

  return { renderSealCard, renderPhotoCard, shareOrDownload, shareNetworks, openShareDialog };
})();
