// Shared safe-DOM helpers.
//
// These two were already correct in map.js and are promoted here rather than
// rewritten, so there is one definition instead of several near-copies. The
// pages that were building HTML by concatenation without them are the reason
// this file exists: achievements, archive and updates all interpolated values
// from first-party JSON straight into innerHTML.
//
// None of that was exploitable, since the JSON is ours. It was still wrong: a
// collection title containing an ampersand rendered as broken markup, and the
// habit is one line away from becoming a real hole the day any of that data
// stops being first-party.
window.SafeDOM = (function () {
  'use strict';

  // Escapes for both text and quoted-attribute contexts. Single quotes are
  // included deliberately: attributes elsewhere in the codebase are written
  // with either quote style.
  function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>"']/g, function (char) {
      return {
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#39;',
      }[char];
    });
  }

  // Resolves against the current page and allows only http/https, so a
  // javascript: or data: URL arriving in JSON cannot become a live link.
  // Returns '#' rather than throwing, because a bad URL should render as an
  // inert link rather than break the page around it.
  function safeUrl(value) {
    // Empty input returns '#', not the current page. new URL('', here) resolves
    // to the page itself, so an <img src> built from a missing value would
    // fetch the HTML document as an image.
    if (value == null || String(value).trim() === '') return '#';
    try {
      var url = new URL(String(value ?? ''), window.location.href);
      return ['http:', 'https:'].indexOf(url.protocol) !== -1 ? url.href : '#';
    } catch (e) {
      return '#';
    }
  }

  // Escaped href, ready to drop into an attribute.
  function safeAttrUrl(value) {
    return escapeHtml(safeUrl(value));
  }

  // An external link with the rel that stops the opened page reaching back
  // through window.opener.
  function externalLink(href, text, className) {
    var a = document.createElement('a');
    a.href = safeUrl(href);
    a.target = '_blank';
    a.rel = 'noopener noreferrer';
    if (className) a.className = className;
    a.textContent = String(text == null ? '' : text);
    return a;
  }

  return {
    escapeHtml: escapeHtml,
    safeUrl: safeUrl,
    safeAttrUrl: safeAttrUrl,
    externalLink: externalLink,
  };
})();
