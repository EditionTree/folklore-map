// Removes the decorative artwork if it fails to load.
//
// This was an inline onerror= attribute, which CSP blocks once script-src drops
// 'unsafe-inline'. It cannot simply move to the end of the body: an image error
// fires while the document is still parsing, long before a bottom-of-page
// listener would exist. The error event does not bubble either, so a delegated
// listener has to use the capture phase.
//
// Loaded as a classic script in <head>, which blocks parsing until it runs, so
// the listener is registered before the <img> below it is even seen.
document.addEventListener('error', function (e) {
  const el = e.target;
  if (el && el.tagName === 'IMG' && el.classList.contains('art')) el.remove();
}, true);
