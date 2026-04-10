/**
 * AutoScoot GPS Navigation Module
 * Extracted from index.html per Redesign Game Plan v1.0
 */

let map = null, scooterMarker = null, destMarker = null;

// Exported to window so jsmain.js can block joystick input during nav
window.navState = 'idle'; 
window._clickedGoal = null;

export function initMap(lat, lon) {
  if (map) return;
  // Map settings per spec: height 280px, zoom 18
  map = L.map('map', { zoomControl: true }).setView([lat, lon], 18);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: 'OpenStreetMap'
  }).addTo(map);

  // Scooter marker: Green dot per design tokens
  scooterMarker = L.marker([lat, lon], {
    icon: L.divIcon({
      className:'', 
      html:'<div style="background:#00C853;width:14px;height:14px;border-radius:50%;border:2px solid white;box-shadow:0 0 6px #00C853;"></div>'
    })
  }).addTo(map).bindPopup('AutoScoot');

  map.on('click', function(e) {
    if (window.navState !== 'idle') return;
    var clat = e.latlng.lat.toFixed(6);
    var clon = e.latlng.lng.toFixed(6);
    if (destMarker) map.removeLayer(destMarker);
    
    // Destination marker: AutoScoot Orange
    destMarker = L.marker([clat, clon], {
      icon: L.divIcon({
        className:'', 
        html:'<div style="background:#FF4D00;width:14px;height:14px;border-radius:50%;border:2px solid white;box-shadow:0 0 6px #FF4D00;"></div>'
      })
    }).addTo(map).bindPopup('Destination').openPopup();

    window._clickedGoal = {name: 'Destination', lat: parseFloat(clat), lon: parseFloat(clon), alt: 0};
    
    // UI Updates for "Destination Set" state
    const summonBtn = document.getElementById('summon-btn');
    const gpsStatus = document.getElementById('gps-status');
    const summonCoords = document.getElementById('summon-coords');

    if (summonBtn) summonBtn.style.display = 'block';
    if (summonCoords) summonCoords.textContent = clat + ', ' + clon;
    if (gpsStatus) {
        gpsStatus.textContent = clat + ', ' + clon + ' — tap SUMMON';
        gpsStatus.style.color = '#FF4D00'; 
    }
  });
}

export function pollGPS() {
  fetch('/gps').then(r => r.json()).then(d => {
    if (d.status === 0 && d.lat && !isNaN(d.lat)) {
      if (window.navState === 'idle' && !window._clickedGoal) {
        const gpsStatus = document.getElementById('gps-status');
        if (gpsStatus) {
            gpsStatus.textContent = d.lat.toFixed(5) + ', ' + d.lon.toFixed(5);
            gpsStatus.style.color = '#a5c8ff'; 
        }
      }
      initMap(d.lat, d.lon);
      if (scooterMarker) scooterMarker.setLatLng([d.lat, d.lon]);
    } else if (window.navState === 'idle') {
      const gpsStatus = document.getElementById('gps-status');
      if (gpsStatus) {
          gpsStatus.textContent = 'Waiting for GPS fix...';
          gpsStatus.style.color = 'rgba(255,255,255,0.25)';
      }
    }
  }).catch(e => console.error("GPS Poll Error:", e));
}

export function pollNavStatus() {
  fetch('/nav_status').then(r => r.json()).then(d => {
    if (!d.status) return;
    var status = d.status;

    if (status.startsWith('ARRIVED')) {
      setNavState('arrived');
    } else if (status.startsWith('Navigating') || status.startsWith('Crawling') || status.startsWith('Heading')) {
      setNavState('navigating');
      var distMatch = status.match(/dist=(\d+)m/);
      if (distMatch) {
        const distEl = document.getElementById('nav-dist');
        if (distEl) distEl.textContent = distMatch[1] + ' m';
      }
      const navLog = document.getElementById('nav-log');
      if (navLog) navLog.textContent = status;
    } else if (status.startsWith('LIDAR STOP')) {
      setNavState('navigating');
      const distEl = document.getElementById('nav-dist');
      if (distEl) distEl.innerHTML = '<span style="color:#FF1744">⚠️ STOP</span>';
    }
  }).catch(e => console.error("Nav Status Error:", e));
}

export function setNavState(state) {
  window.navState = state;
  const panels = {
    'nav-idle': state === 'idle',
    'nav-active': state === 'navigating',
    'nav-arrived': state === 'arrived'
  };
  
  Object.keys(panels).forEach(id => {
    const el = document.getElementById(id);
    if (el) el.style.display = panels[id] ? 'block' : 'none';
  });

  // Handle WASD visual lockout feedback per Game Plan 5.3
  const wasdWrap = document.getElementById('wasd-wrap');
  const banner = document.getElementById('wasd-lockout-banner');
  if (state === 'navigating') {
    if (wasdWrap) wasdWrap.classList.add('locked'); 
    if (banner) banner.style.display = 'block';
  } else {
    if (wasdWrap) wasdWrap.classList.remove('locked');
    if (banner) banner.style.display = 'none';
  }
}

export function doSummon(goal) {
  fetch('/summon', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(goal)
  }).then(() => {
    // Auto-engage and enable autopilot during summon per implementation guide
    fetch('/autopilot', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({autopilot: true})});
    fetch('/engage', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({engaged: true})});
    setNavState('navigating');
  });
}

export function cancelNav() {
  fetch('/summon_cancel', {method:'POST'}).catch(()=>{});
  fetch('/autopilot', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({autopilot: false})});
  fetch('/engage', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({engaged: false})});
  
  if (destMarker && map) { map.removeLayer(destMarker); destMarker = null; }
  window._clickedGoal = null;
  
  const summonBtn = document.getElementById('summon-btn');
  if (summonBtn) summonBtn.style.display = 'none';
  setNavState('idle');
}
