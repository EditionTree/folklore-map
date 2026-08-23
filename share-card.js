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

  // ── Social share links ────────────────────────────────────────────────
  // The card renderer produces an image, and navigator.share can attach it on
  // a phone, but on a desktop browser that falls back to a download and the
  // trail ends there. Web intents cannot carry an image, so these share the
  // page and the sentence instead, and sit alongside the saved image rather
  // than replacing it.
  //
  // Plain links on purpose. No platform SDKs, no embedded buttons, nothing
  // that phones home before the visitor has chosen to share, which matches
  // what the Privacy Notice says the site does.
  var SOCIAL = [
    { label: 'X',        url: function(t, u){ return 'https://twitter.com/intent/tweet?text=' + t + '&url=' + u; } },
    { label: 'Bluesky',  url: function(t, u){ return 'https://bsky.app/intent/compose?text=' + t + '%20' + u; } },
    { label: 'Facebook', url: function(t, u){ return 'https://www.facebook.com/sharer/sharer.php?u=' + u; } },
    { label: 'WhatsApp', url: function(t, u){ return 'https://wa.me/?text=' + t + '%20' + u; } }
  ];

  function buildShareLinks(container, text, pageUrl){
    if(!container) return;
    var t = encodeURIComponent(text);
    var u = encodeURIComponent(pageUrl);
    container.textContent = '';
    var lead = document.createElement('span');
    lead.className = 'share-links-lead';
    lead.textContent = 'Share on ';
    container.appendChild(lead);
    SOCIAL.forEach(function(net, i){
      if(i) container.appendChild(document.createTextNode(' · '));
      var a = document.createElement('a');
      a.href = net.url(t, u);
      a.target = '_blank';
      a.rel = 'noopener noreferrer';
      a.textContent = net.label;
      container.appendChild(a);
    });
    container.hidden = false;
  }

  return { renderSealCard, renderPhotoCard, shareOrDownload, buildShareLinks };
})();
