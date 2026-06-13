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

  var copyButton=document.getElementById('copyLinkBtn');
  var status=document.getElementById('shareStatus');
  if(copyButton){
    copyButton.addEventListener('click',function(){
      var canonical=document.querySelector('link[rel=canonical]');
      var url=canonical?canonical.href:location.href;
      function copied(){
        copyButton.textContent='Copied';
        if(status)status.textContent='Link copied';
        setTimeout(function(){copyButton.textContent='Copy link';},1800);
      }
      if(navigator.clipboard&&navigator.clipboard.writeText){
        navigator.clipboard.writeText(url).then(copied);
      }
    });
  }

  var shareButton=document.getElementById('webShareBtn');
  if(shareButton&&navigator.share){
    shareButton.hidden=false;
    shareButton.addEventListener('click',function(){
      navigator.share({title:document.title,url:location.href}).catch(function(){});
    });
  }
})();
