(function(){
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

  if(shareButton&&navigator.share){
    var shareData={title:document.title,url:url};
    var canShare=true;
    if(navigator.canShare){
      try{
        canShare=navigator.canShare(shareData);
      }catch(error){
        canShare=false;
      }
    }
    if(canShare){
      shareButton.hidden=false;
      shareButton.addEventListener('click',function(){
        navigator.share(shareData).catch(function(error){
          if(error&&error.name==='AbortError')return;
          copyLink().then(function(copied){
            if(copied){
              announce('Sharing unavailable here, so the link was copied instead.');
            }
          });
        });
      });
    }
  }
})();
