import { handleKeyX, getXY } from "./controls.js";
import { start, playSoundRequest } from "./webrtc.js";

// Global States
let isEngaged = false;
let isAutopilot = false;
let isExpAuto = false;
let isLaneFollow = false;
let logPaused = false;

const MAX_LOG_LINES = 100;

// ─── CORE JOYSTICK ENGINE ───
// This is what makes the scooter move.
setInterval(() => {
    const coords = getXY(); // Should return {x: float, y: float}
    
    // Update the UI display
    const posDisplay = document.getElementById('pos-vals');
    if (posDisplay) posDisplay.textContent = `${coords.x.toFixed(2)},${coords.y.toFixed(2)}`;

    // Send to backend
    fetch('/joystick', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(coords)
    }).catch(err => console.error("Joystick link lost:", err));
}, 50);

// ─── INTERACTION BINDINGS ───
const bindButton = (id, stateVar, endpoint, onLabel, offLabel, statusId, activeStatusText) => {
    const btn = document.getElementById(id);
    const status = document.getElementById(statusId);

    btn.addEventListener('click', async () => {
        // Toggle state
        const newState = !window[stateVar];
        
        try {
            const res = await fetch(endpoint, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ [endpoint.replace('/', '')]: newState, engaged: newState })
            });

            if (res.ok) {
                window[stateVar] = newState;
                if (newState) {
                    btn.classList.add('border-orange-500', 'text-orange-500');
                    btn.classList.remove('border-zinc-800', 'text-zinc-500');
                    status.textContent = activeStatusText;
                    playSoundRequest('engage');
                } else {
                    btn.classList.remove('border-orange-500', 'text-orange-500');
                    btn.classList.add('border-zinc-800', 'text-zinc-500');
                    status.textContent = 'OFF';
                    playSoundRequest('disengage');
                }
            }
        } catch (e) { console.error("Toggle Failed", e); }
    });
};

// Map global variables to the window for the helper function to see them
window.isEngaged = isEngaged;
window.isAutopilot = isAutopilot;

// Special Engage Handler (Colors are different)
document.getElementById('engage-btn').addEventListener('click', async function() {
    isEngaged = !isEngaged;
    const res = await fetch('/engage', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ engaged: isEngaged })
    });

    if (res.ok) {
        this.textContent = isEngaged ? 'DISENGAGE' : 'ENGAGE';
        this.classList.toggle('bg-red-600', isEngaged);
        this.classList.toggle('text-white', isEngaged);
        document.getElementById('engage-status').textContent = isEngaged ? 'ENGAGED' : 'DISENGAGED';
        playSoundRequest(isEngaged ? 'engage' : 'disengage');
    }
});

// Bind other modes
bindButton('autopilot-btn', 'isAutopilot', '/autopilot', 'STOP', 'AUTO', 'autopilot-status', 'SELF-DRIVING');
bindButton('exp-auto-btn', 'isExpAuto', '/exp_auto', 'STOP', 'EXP', 'exp-auto-status', 'ACTIVE');
bindButton('lane-follow-btn', 'isLaneFollow', '/lane_follow', 'STOP', 'LANE', 'lane-follow-status', 'FOLLOWING');

// ─── KEYS HANDLER ───
document.addEventListener('keydown', (e) => handleKeyX(e.key.toLowerCase(), 1));
document.addEventListener('keyup', (e) => handleKeyX(e.key.toLowerCase(), 0));

document.querySelectorAll('.keys').forEach(el => {
    const key = el.id.replace('key-', '');
    el.addEventListener('mousedown', () => handleKeyX(key, 1));
    el.addEventListener('mouseup', () => handleKeyX(key, 0));
    el.addEventListener('touchstart', (e) => { e.preventDefault(); handleKeyX(key, 1); });
    el.addEventListener('touchend', () => handleKeyX(key, 0));
});

// ─── LOGGING ───
setInterval(async () => {
    if (logPaused) return;
    try {
        const resp = await fetch('/status');
        const data = await resp.json();
        const log = document.getElementById('actuator-log');
        
        const entry = document.createElement('div');
        entry.className = "border-l-2 border-zinc-800 pl-2 mb-1";
        entry.innerHTML = `<span class="opacity-50">${new Date().toLocaleTimeString()}</span> > THR: ${data.joystick?.throttle.toFixed(2)} STR: ${data.joystick?.steering.toFixed(2)}`;
        
        log.appendChild(entry);
        if (log.children.length > MAX_LOG_LINES) log.removeChild(log.firstChild);
        log.scrollTop = log.scrollHeight;

        // Update Stats
        document.getElementById('battery').textContent = data.battery || '-';
    } catch (e) {}
}, 500);

// Cleanup on close
window.onbeforeunload = () => {
    navigator.sendBeacon('/engage', JSON.stringify({engaged: false}));
};

start(null, null);
