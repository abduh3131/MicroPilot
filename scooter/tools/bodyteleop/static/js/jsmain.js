import { handleKeyX, getXY, executePlan } from "./controls.js";
import { start, stop, lastChannelMessageTime, playSoundRequest } from "./webrtc.js";

export var pc = null;
export var dc = null;

document.addEventListener('keydown', (e)=>(handleKeyX(e.key.toLowerCase(), 1)));
document.addEventListener('keyup', (e)=>(handleKeyX(e.key.toLowerCase(), 0)));
$(".keys").bind("mousedown touchstart", (e)=>handleKeyX($(e.target).attr('id').replace('key-', ''), 1));
$(".keys").bind("mouseup touchend", (e)=>handleKeyX($(e.target).attr('id').replace('key-', ''), 0));
$("#plan-button").click(executePlan);
$(".sound").click((e)=>{
  const sound = $(e.target).attr('id').replace('sound-', '')
  return playSoundRequest(sound);
});

// ─── JOYSTICK IPC: POST /joystick every 50ms ───
// Arbiter fix: browser only posts when NO autonomous mode is active.
// All autonomous modes write to their own private files now.
// The arbiter.py picks the winner and writes to /tmp/joystick.
function isAnyAutoModeActive() {
  return isAutopilot || isExpAuto || isLaneFollow;
}

setInterval(() => {
  if (isAnyAutoModeActive()) return;
  const {x, y} = getXY();
  fetch('/joystick', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({x, y})
  }).catch(() => {});
}, 50);

// ─── ENGAGE / DISENGAGE TOGGLE ───
let isEngaged = false;

$("#engage-btn").click(async function() {
  isEngaged = !isEngaged;
  try {
    const response = await fetch('/engage', {
      body: JSON.stringify({engaged: isEngaged}),
      headers: {'Content-Type': 'application/json'},
      method: 'POST'
    });
    if (response.ok) {
      if (isEngaged) {
        $(this).removeClass('btn-outline-danger').addClass('btn-success').text('DISENGAGE');
        $("#engage-status").text('ENGAGED');
        playSoundRequest('engage');
      } else {
        $(this).removeClass('btn-success').addClass('btn-outline-danger').text('ENGAGE');
        $("#engage-status").text('DISENGAGED');
        playSoundRequest('disengage');
        // Kill all modes on disengage
        await setAllModesOff();
      }
    } else {
      isEngaged = !isEngaged;
    }
  } catch (err) {
    console.error('Engage request failed:', err);
    isEngaged = !isEngaged;
  }
});

// ─── HELPER: turn off all autonomous modes ───
async function setAllModesOff() {
  const calls = [];
  if (isAutopilot) calls.push(fetch('/autopilot', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({autopilot: false}) }));
  if (isExpAuto)   calls.push(fetch('/exp_auto',  { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({exp_auto: false}) }));
  if (isLaneFollow) calls.push(fetch('/lane_follow', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({lane_follow: false}) }));
  await Promise.all(calls).catch(() => {});
  isAutopilot = false;
  isExpAuto = false;
  isLaneFollow = false;
  updateModeUI();
}

function updateModeUI() {
  // Reset all preset buttons
  $(".preset-btn").removeClass('active-preset');
  if (!isAutopilot && !isExpAuto && !isLaneFollow) {
    $("#mode-status").text('MANUAL');
  }
}

// ─── INDIVIDUAL MODE TOGGLES (kept for backward compat) ───
let isAutopilot = false;
let isExpAuto = false;
let isLaneFollow = false;

$("#autopilot-btn").click(async function() {
  if (!isEngaged && !isAutopilot) {
    $("#autopilot-status").text('ENGAGE FIRST');
    setTimeout(() => $("#autopilot-status").text('OFF'), 1500);
    return;
  }
  isAutopilot = !isAutopilot;
  try {
    const response = await fetch('/autopilot', {
      body: JSON.stringify({autopilot: isAutopilot}),
      headers: {'Content-Type': 'application/json'},
      method: 'POST'
    });
    if (response.ok) {
      if (isAutopilot) {
        if (isLaneFollow) { isLaneFollow = false; await fetch('/lane_follow', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({lane_follow: false}) }); }
        if (isExpAuto) { isExpAuto = false; await fetch('/exp_auto', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({exp_auto: false}) }); }
        $(this).removeClass('btn-outline-info').addClass('btn-warning').text('STOP AUTOPILOT');
        $("#autopilot-status").text('SELF-DRIVING');
        playSoundRequest('engage');
      } else {
        $(this).removeClass('btn-warning').addClass('btn-outline-info').text('AUTOPILOT');
        $("#autopilot-status").text('OFF');
        playSoundRequest('disengage');
      }
    } else { isAutopilot = !isAutopilot; }
  } catch (err) { isAutopilot = !isAutopilot; }
});

$("#exp-auto-btn").click(async function() {
  if (!isEngaged && !isExpAuto) {
    $("#exp-auto-status").text('ENGAGE FIRST');
    setTimeout(() => $("#exp-auto-status").text('OFF'), 1500);
    return;
  }
  isExpAuto = !isExpAuto;
  try {
    const response = await fetch('/exp_auto', {
      body: JSON.stringify({exp_auto: isExpAuto}),
      headers: {'Content-Type': 'application/json'},
      method: 'POST'
    });
    if (response.ok) {
      if (isExpAuto) {
        if (isAutopilot) { isAutopilot = false; await fetch('/autopilot', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({autopilot: false}) }); }
        if (isLaneFollow) { isLaneFollow = false; await fetch('/lane_follow', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({lane_follow: false}) }); }
        $(this).removeClass('btn-outline-warning').addClass('btn-danger').text('STOP EXP AUTO');
        $("#exp-auto-status").text('OPENPILOT ACTIVE');
        playSoundRequest('engage');
      } else {
        $(this).removeClass('btn-danger').addClass('btn-outline-warning').text('EXP AUTO');
        $("#exp-auto-status").text('OFF');
        playSoundRequest('disengage');
      }
    } else { isExpAuto = !isExpAuto; }
  } catch (err) { isExpAuto = !isExpAuto; }
});

$("#lane-follow-btn").click(async function() {
  if (!isEngaged && !isLaneFollow) {
    $("#lane-follow-status").text('ENGAGE FIRST');
    setTimeout(() => $("#lane-follow-status").text('OFF'), 1500);
    return;
  }
  isLaneFollow = !isLaneFollow;
  try {
    const response = await fetch('/lane_follow', {
      body: JSON.stringify({lane_follow: isLaneFollow}),
      headers: {'Content-Type': 'application/json'},
      method: 'POST'
    });
    if (response.ok) {
      if (isLaneFollow) {
        if (isAutopilot) { isAutopilot = false; await fetch('/autopilot', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({autopilot: false}) }); }
        if (isExpAuto) { isExpAuto = false; await fetch('/exp_auto', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({exp_auto: false}) }); }
        $(this).removeClass('btn-outline-success').addClass('btn-danger').text('STOP LANE FOLLOW');
        $("#lane-follow-status").text('FOLLOWING LANE');
        playSoundRequest('engage');
      } else {
        $(this).removeClass('btn-danger').addClass('btn-outline-success').text('LANE FOLLOW');
        $("#lane-follow-status").text('OFF');
        playSoundRequest('disengage');
      }
    } else { isLaneFollow = !isLaneFollow; }
  } catch (err) { isLaneFollow = !isLaneFollow; }
});

// ─── PRESET MODE BUTTONS ───
// One button per demo scenario. Sets the right combination of flags.

// DEMO MODE: gym with no tape - just drives straight, lidar avoids obstacles
$("#preset-demo-btn").click(async function() {
  if (!isEngaged) { alert('Engage first'); return; }
  await setAllModesOff();
  await fetch('/autopilot', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({autopilot: true}) });
  isAutopilot = true;
  $(".preset-btn").removeClass('active-preset');
  $(this).addClass('active-preset');
  $("#mode-status").text('DEMO: Straight + LiDAR');
  playSoundRequest('engage');
});

// LANE MODE: gym with tape OR outdoor sidewalk - vision follows path
$("#preset-lane-btn").click(async function() {
  if (!isEngaged) { alert('Engage first'); return; }
  await setAllModesOff();
  await fetch('/lane_follow', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({lane_follow: true}) });
  isLaneFollow = true;
  $(".preset-btn").removeClass('active-preset');
  $(this).addClass('active-preset');
  $("#mode-status").text('LANE: Vision following');
  playSoundRequest('engage');
});

// OUTDOOR AUTO: best path following outdoors - lane follow + pure pursuit
$("#preset-outdoor-btn").click(async function() {
  if (!isEngaged) { alert('Engage first'); return; }
  await setAllModesOff();
  // Both lane_follow AND exp_auto on - lane_follow runs model, exp_auto does pure pursuit steering
  await fetch('/lane_follow', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({lane_follow: true}) });
  await fetch('/exp_auto', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({exp_auto: true}) });
  isLaneFollow = true;
  isExpAuto = true;
  $(".preset-btn").removeClass('active-preset');
  $(this).addClass('active-preset');
  $("#mode-status").text('OUTDOOR: Pure pursuit');
  playSoundRequest('engage');
});

// GPS SUMMON: outdoor navigation to GPS coordinate
$("#preset-gps-btn").click(async function() {
  if (!isEngaged) { alert('Engage first'); return; }
  await setAllModesOff();
  // Autopilot for GPS nav + lane_follow for path awareness
  await fetch('/autopilot', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({autopilot: true}) });
  await fetch('/lane_follow', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({lane_follow: true}) });
  isAutopilot = true;
  isLaneFollow = true;
  $(".preset-btn").removeClass('active-preset');
  $(this).addClass('active-preset');
  $("#mode-status").text('GPS: Tap map to summon');
  playSoundRequest('engage');
});

// STOP ALL
$("#preset-stop-btn").click(async function() {
  await setAllModesOff();
  $(".preset-btn").removeClass('active-preset');
  $("#mode-status").text('MANUAL');
  playSoundRequest('disengage');
});

// Safety: auto-disengage when closing the page
window.addEventListener('beforeunload', function() {
  if (isEngaged) navigator.sendBeacon('/engage', JSON.stringify({engaged: false}));
  if (isAutopilot) navigator.sendBeacon('/autopilot', JSON.stringify({autopilot: false}));
  if (isExpAuto) navigator.sendBeacon('/exp_auto', JSON.stringify({exp_auto: false}));
  if (isLaneFollow) navigator.sendBeacon('/lane_follow', JSON.stringify({lane_follow: false}));
});

// Escape kills everything
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    setAllModesOff();
    if (isEngaged) $("#engage-btn").click();
  }
});

setInterval(() => {
  const dt = new Date().getTime();
  if ((dt - lastChannelMessageTime) > 1000) {
    $(".pre-blob").removeClass('blob');
    $("#battery").text("-");
    $("#ping-time").text('-');
    $("video")[0].load();
  }
}, 5000);

// ─── ACTUATOR LOG ───
let logPaused = false;
const MAX_LOG_LINES = 200;

$("#log-pause-btn").click(function() {
  logPaused = !logPaused;
  $(this).text(logPaused ? 'Resume' : 'Pause');
});

$("#log-clear-btn").click(function() {
  $("#actuator-log").empty();
});

function formatLogLine(data) {
  const now = new Date().toLocaleTimeString('en-US', {hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit'});
  let mode = 'MANUAL';
  let modeColor = '#666';
  if (data.exp_auto === '1' && data.lane_follow === '1') { mode = 'OUTDOOR '; modeColor = '#f0f'; }
  else if (data.exp_auto === '1') { mode = 'EXP_AUTO'; modeColor = '#f80'; }
  else if (data.lane_follow === '1') { mode = 'LANE_FLW'; modeColor = '#0f0'; }
  else if (data.autopilot === '1') { mode = 'AUTOPILOT'; modeColor = '#0af'; }

  let engaged = data.engage === '1';
  let lidar = data.lidar_stop === '1';
  let thr = '-.---', str = '-.---';
  if (data.joystick) {
    thr = data.joystick.throttle.toFixed(3);
    str = data.joystick.steering.toFixed(3);
  }
  let conf = '-', planP = '-', laneL = '-', laneR = '-', frm = '-';
  if (data.model) {
    conf = (data.model.confidence * 100).toFixed(0) + '%';
    planP = (data.model.plan_prob * 100).toFixed(0) + '%';
    laneL = data.model.left_near_y.toFixed(1) + '(' + (data.model.left_near_prob * 100).toFixed(0) + '%)';
    laneR = data.model.right_near_y.toFixed(1) + '(' + (data.model.right_near_prob * 100).toFixed(0) + '%)';
    frm = data.model.frame;
  }
  let engColor = engaged ? '#0f0' : '#f44';
  let engText = engaged ? 'ENG' : 'DIS';
  let lidarText = lidar ? ' <span style="color:#f00;font-weight:bold">ESTOP</span>' : '';
  let ctrlText = isAnyAutoModeActive() ? ' <span style="color:#0af">[AUTO]</span>' : ' <span style="color:#888">[MANUAL]</span>';

  return `<span style="color:#888">${now}</span> ` +
    `<span style="color:${engColor}">[${engText}]</span> ` +
    `<span style="color:${modeColor}">${mode.padEnd(9)}</span> ` +
    `T=<span style="color:#ff0">${thr}</span> ` +
    `S=<span style="color:#0ff">${str}</span> ` +
    `conf=<span style="color:#0f0">${conf}</span> ` +
    `plan=<span style="color:#0f0">${planP}</span> ` +
    `L=${laneL} R=${laneR} ` +
    `#${frm}` +
    lidarText + ctrlText;
}

setInterval(async () => {
  if (logPaused) return;
  try {
    const resp = await fetch('/status');
    if (!resp.ok) return;
    const data = await resp.json();
    const logEl = document.getElementById('actuator-log');
    if (!logEl) return;
    const line = document.createElement('div');
    line.innerHTML = formatLogLine(data);
    logEl.appendChild(line);
    while (logEl.children.length > MAX_LOG_LINES) logEl.removeChild(logEl.firstChild);
    logEl.scrollTop = logEl.scrollHeight;
  } catch (e) {}
}, 250);

start(pc, dc);
