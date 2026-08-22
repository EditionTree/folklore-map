function trackEvent(eventType, extra){
  try{
    var id=sessionStorage.getItem('ff_session_id');
    if(!id){ id=Math.random().toString(36).slice(2)+Date.now().toString(36); sessionStorage.setItem('ff_session_id', id); }
    var payload=Object.assign({event_type:eventType,referring_page:location.pathname,session_id:id}, extra||{});
    fetch('https://canjzkpvjwvkbjcduaaj.supabase.co/functions/v1/submit-event', {
      method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload), keepalive:true
    }).catch(function(){});
  }catch(e){}
}


// Previously an inline onclick; a listener now so script-src can drop
// 'unsafe-inline'.
document.querySelectorAll('[data-track-journal]').forEach(a =>
  a.addEventListener('click', () => trackEvent('research_journal_clicked')));
