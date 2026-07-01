"use strict";
// ── Types ──
// ── State ──
let allModels = [];
let defaultModel = 'deepseek-v4-flash';
let effortValues = [];
let permissionModes = [];
let currentSessionId = null;
let currentWorkerId = null;
let modelData = [];
let lastSyncedSettings = null;
// ── WebSocket ──
const ws = new WebSocket('ws://' + location.host + '/ws');
ws.onopen = refreshSessions;
ws.onmessage = onWsMessage;
function onWsMessage(e) {
    const d = JSON.parse(e.data);
    switch (d.type) {
        case 'worker.spawned':
        case 'worker.restarted':
        case 'worker.reconfigured':
            _setLocalWorker(d.sessionId, d.workerId, 'idle');
            if (d.sessionId === currentSessionId) {
                currentWorkerId = d.workerId ?? null;
                updateTopBar();
            }
            refreshSessions();
            break;
        case 'worker.destroyed':
        case 'worker.crashed':
            _setLocalWorker(d.sessionId, null, null);
            if (d.sessionId === currentSessionId) {
                currentWorkerId = null;
                updateTopBar();
            }
            refreshSessions();
            break;
        case 'worker.stream':
            if (d.sessionId === currentSessionId && d.event) {
                appendEvent(d.event);
            }
            break;
        case 'worker.result':
            if (d.sessionId === currentSessionId)
                appendResult(d);
            refreshSessions();
            break;
        case 'worker.status':
            _setLocalWorker(d.sessionId, d.workerId, d.status ?? 'idle');
            if (d.sessionId === currentSessionId)
                updateTopBar();
            refreshSessions();
            break;
        case 'session.created':
        case 'session.renamed':
        case 'session.updated':
        case 'session.deleted':
            refreshSessions();
            break;
        case 'error':
            toast(d.message ?? 'Unknown error');
            break;
    }
}
function _setLocalWorker(sessionId, workerId, status) {
    for (let i = 0; i < modelData.length; i++) {
        if (modelData[i].id === sessionId) {
            modelData[i].workerId = workerId ?? undefined;
            modelData[i].workerStatus = status;
            break;
        }
    }
    renderSessionList();
}
// ── Session list ──
function refreshSessions() {
    fetch('/api/sessions')
        .then((r) => r.json())
        .then((data) => {
        modelData = data.sessions || [];
        renderSessionList();
        const matched = modelData.find((s) => s.id === currentSessionId);
        if (!matched) {
            currentSessionId = null;
            currentWorkerId = null;
            showEmpty();
        }
        else {
            currentWorkerId = matched.workerId ?? null;
            const chatNameEl = document.getElementById('chatName');
            if (chatNameEl.style.display !== 'none') {
                renderMessages(matched.history || []);
            }
        }
        if (currentSessionId)
            updateTopBar();
    });
}
function renderSessionList() {
    const el = document.getElementById('sessionList');
    el.innerHTML = '';
    modelData.forEach((s) => {
        const div = document.createElement('div');
        div.className = 'sess-item' + (s.id === currentSessionId ? ' active' : '');
        div.onclick = function (e) {
            const target = e.target;
            if (target.closest('.sess-del'))
                return;
            selectSession(s.id);
        };
        let lastMsg = '';
        const h = s.history || [];
        if (h.length > 0) {
            const last = h[h.length - 1];
            lastMsg = last.content || '';
            if (lastMsg.length > 40)
                lastMsg = lastMsg.slice(0, 40) + '\u2026';
        }
        div.innerHTML =
            '<div style="display:flex;justify-content:space-between;align-items:start">' +
                '<div class="sess-name"><span class="s-dot ' +
                (s.workerStatus || 'offline') +
                '"></span>' +
                esc(s.name) +
                '</div>' +
                '<button class="sess-del" onclick="deleteSession(\'' +
                s.id +
                '\')" title="Delete session" style="background:none;border:none;color:#484f58;cursor:pointer;font-size:.85rem;padding:0 2px">\u2699</button>' +
                '</div>' +
                (lastMsg ? '<div class="sess-preview">' + esc(lastMsg) + '</div>' : '') +
                '<div class="sess-meta"><span class="sess-model">' +
                esc(s.model || defaultModel) +
                '</span>' +
                '<span>' +
                (s.history || []).length +
                ' msgs</span></div>';
        el.appendChild(div);
    });
}
function selectSession(id) {
    currentSessionId = id;
    const s = modelData.find((x) => x.id === id);
    if (!s)
        return;
    currentWorkerId = s.workerId ?? null;
    renderSessionList();
    updateTopBar();
    renderMessages(s.history || []);
    const settingsBtn = document.getElementById('settingsBtn');
    settingsBtn.style.display = '';
    // sync panel if it's already open
    if (document.getElementById('settingsPanel').classList.contains('open')) {
        syncPanelFromServer();
    }
}
// ── Top bar ──
function updateTopBar() {
    const s = modelData.find((x) => x.id === currentSessionId);
    if (!s) {
        showEmpty();
        return;
    }
    (document.getElementById('emptyHint')).style.display = 'none';
    (document.getElementById('chatName')).style.display = '';
    (document.getElementById('chatModel')).style.display = '';
    (document.getElementById('chatName')).textContent =
        s.name || (currentSessionId ?? '').slice(0, 12);
    (document.getElementById('chatModel')).textContent = s.model || defaultModel;
    const status = s.workerStatus || 'offline';
    (document.getElementById('chatStatus')).textContent =
        status + (currentWorkerId ? ' (' + currentWorkerId + ')' : ' (no worker)');
}
function showEmpty() {
    (document.getElementById('emptyHint')).style.display = '';
    (document.getElementById('chatName')).style.display = 'none';
    (document.getElementById('chatModel')).style.display = 'none';
    (document.getElementById('chatStatus')).textContent = '';
    (document.getElementById('settingsBtn')).style.display = 'none';
    (document.getElementById('settingsPanel')).className = '';
    (document.getElementById('messages')).innerHTML =
        '<div class="empty-chat">Select a session to start</div>';
}
// ── Messages ──
function renderMessages(history) {
    const el = document.getElementById('messages');
    el.innerHTML = '';
    if (!history || history.length === 0) {
        el.innerHTML =
            '<div class="empty-chat">No messages yet. Start a conversation.</div>';
        return;
    }
    history.forEach((h) => {
        addMessage(h.role, h.content);
    });
    el.scrollTop = el.scrollHeight;
}
function addMessage(role, content) {
    const el = document.getElementById('messages');
    const div = document.createElement('div');
    if (role === 'user') {
        div.className = 'msg user';
        div.textContent = content;
    }
    else if (role === 'assistant') {
        div.className = 'msg assistant';
        const display = content.replace(/🔧.*(\n|$)/g, '').trim();
        div.textContent = display || '(tool call only)';
    }
    else if (role === 'thinking') {
        div.className = 'msg thinking';
        div.innerHTML =
            '💭 <span class="thinking-toggle">show thinking</span><div class="thinking-body">' +
                esc(content) +
                '</div>';
        div.onclick = function () {
            const body = div.querySelector('.thinking-body');
            const toggle = div.querySelector('.thinking-toggle');
            if (!body || !toggle)
                return;
            body.classList.toggle('open');
            toggle.textContent = body.classList.contains('open')
                ? 'hide thinking'
                : 'show thinking';
        };
    }
    else if (role === 'tool') {
        div.className = 'msg tool';
        div.textContent = '🔧 ' + content;
    }
    else {
        div.className = 'msg system';
        div.textContent = content || '';
    }
    el.appendChild(div);
    el.scrollTop = el.scrollHeight;
}
function appendEvent(event) {
    const t = event.type;
    if (t === 'system' && event.subtype === 'init')
        return;
    if (t === 'result')
        return;
    if (t === 'assistant') {
        const content = (event.message && event.message.content) || [];
        content.forEach((b) => {
            if (b.type === 'text')
                addMessage('assistant', b.text ?? '');
            else if (b.type === 'thinking')
                addMessage('thinking', b.thinking ?? '');
            else if (b.type === 'tool_use')
                addMessage('tool', (b.name ?? '') + '(' + JSON.stringify(b.input || {}) + ')');
        });
    }
}
function appendResult(d) {
    const status = d.status === 'error' ? 'error' : 'done';
    addMessage('system', '[' + status.toUpperCase() + '] Task completed');
}
// ── Settings panel ──
function toggleSettings() {
    const panel = document.getElementById('settingsPanel');
    const btn = document.getElementById('settingsBtn');
    const isOpen = panel.classList.toggle('open');
    btn.classList.toggle('open', isOpen);
    if (isOpen) {
        syncPanelFromServer();
    }
}
/** Sync the settings panel fields to the current session's server-side values.
 *  Called when the panel opens or the session switches. */
function syncPanelFromServer() {
    const s = modelData.find((x) => x.id === currentSessionId);
    if (!s)
        return;
    const sel = document.getElementById('settingModel');
    if (sel.getAttribute('data-loaded') !== '1')
        return;
    const model = s.model || defaultModel;
    sel.value = allModels.indexOf(model) >= 0 ? model : '';
    document.getElementById('settingMode').value =
        s.permissionMode || '';
    document.getElementById('settingThinking').checked =
        s.alwaysThinkingEnabled || false;
    document.getElementById('settingEffort').value =
        effortValues.indexOf(s.effort) >= 0 ? s.effort : (effortValues[1] || effortValues[0] || '');
    (document.getElementById('effortGroup')).style.display =
        (s.alwaysThinkingEnabled && effortValues.length > 0) ? '' : 'none';
    // record the baseline so we can detect pending changes
    lastSyncedSettings = {
        model: getSettingModel(),
        permissionMode: document.getElementById('settingMode').value,
        alwaysThinkingEnabled: document.getElementById('settingThinking').checked,
        effort: document.getElementById('settingEffort').value,
    };
    updateSetButtonVisibility();
}
/** Returns true when any panel field differs from lastSyncedSettings. */
function hasPendingChanges() {
    if (!lastSyncedSettings)
        return false;
    return (getSettingModel() !== lastSyncedSettings.model ||
        document.getElementById('settingMode').value !==
            lastSyncedSettings.permissionMode ||
        document.getElementById('settingThinking').checked !==
            lastSyncedSettings.alwaysThinkingEnabled ||
        document.getElementById('settingEffort').value !==
            lastSyncedSettings.effort);
}
function getSettingModel() {
    const sel = document.getElementById('settingModel');
    if (sel.value === '__custom__') {
        const inp = document.getElementById('settingModelCustom');
        return inp.value.trim() || defaultModel;
    }
    return sel.value || defaultModel;
}
/** Show/hide the Apply Settings button based on whether settings differ from
 *  the last synced state. */
function updateSetButtonVisibility() {
    const btn = document.getElementById('applySettingsBtn');
    btn.style.display = hasPendingChanges() ? '' : 'none';
}
/** Called when the Think checkbox is toggled: show/hide Effort + auto-select
 *  medium, then update the Set button.  No API call is made. */
function onThinkingToggle() {
    const thinking = document.getElementById('settingThinking').checked;
    (document.getElementById('effortGroup')).style.display =
        (thinking && effortValues.length > 0) ? '' : 'none';
    if (thinking && effortValues.length > 0) {
        const eff = document.getElementById('settingEffort');
        if (!eff.value || eff.value === effortValues[0])
            eff.value = effortValues[1] || effortValues[0];
    }
    updateSetButtonVisibility();
}
/** Apply all pending model/mode/thinking/effort changes via a single API call.
 *  Handles both the "no worker" (PATCH session) and "worker exists" cases. */
function applySettings() {
    if (!currentSessionId)
        return;
    const thinking = document.getElementById('settingThinking').checked;
    const effort = document.getElementById('settingEffort').value;
    if (!currentWorkerId) {
        // no worker: persist settings to session via PATCH
        fetch('/api/sessions/' + currentSessionId, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                model: getSettingModel(),
                permissionMode: document.getElementById('settingMode').value || undefined,
                alwaysThinkingEnabled: thinking,
                effort: effort,
            }),
        })
            .then((r) => r.json())
            .then((d) => {
            if (d.error) {
                toast(d.error);
                return;
            }
            markSettingsApplied();
        });
        return;
    }
    // worker exists: consolidated endpoint
    fetch('/api/worker/' + currentWorkerId + '/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            model: getSettingModel(),
            permissionMode: document.getElementById('settingMode').value || undefined,
            alwaysThinkingEnabled: thinking,
            effort: effort,
        }),
    })
        .then((r) => r.json())
        .then((d) => {
        if (d.error) {
            toast(d.error);
            return;
        }
        markSettingsApplied();
    });
}
/** Called after successful settings apply — update baseline and hide button. */
function markSettingsApplied() {
    lastSyncedSettings = {
        model: getSettingModel(),
        permissionMode: document.getElementById('settingMode').value,
        alwaysThinkingEnabled: document.getElementById('settingThinking').checked,
        effort: document.getElementById('settingEffort').value,
    };
    updateSetButtonVisibility();
}
// ── Worker actions (restart / interrupt / takeover / kill) ──
function restartWorker() {
    if (currentWorkerId) {
        // Always restart with current panel settings (user intent).
        // applySettings handles both "no-change respawn" and "apply pending changes".
        applySettings();
    }
    else {
        const model = getSettingModel();
        const mode = document.getElementById('settingMode').value;
        const body = {
            sessionId: currentSessionId,
            model: model,
        };
        if (mode)
            body.permissionMode = mode;
        body.alwaysThinkingEnabled = document.getElementById('settingThinking').checked;
        body.effort = document.getElementById('settingEffort').value;
        fetch('/api/spawn', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        })
            .then((r) => r.json())
            .then((d) => {
            if (d.error) {
                toast('Spawn failed: ' + d.error);
                return;
            }
            currentWorkerId = d.workerId ?? null;
            updateTopBar();
        });
    }
}
function interruptWorker() {
    if (!currentWorkerId) {
        toast('No worker running');
        return;
    }
    fetch('/api/worker/' + currentWorkerId + '/interrupt', { method: 'POST' })
        .then((r) => r.json())
        .then((d) => {
        if (d.error)
            toast(d.error);
    });
}
function takeover() {
    if (!currentWorkerId) {
        toast('No worker running');
        return;
    }
    fetch('/api/worker/' + currentWorkerId + '/takeover', { method: 'POST' })
        .then((r) => r.json())
        .then((d) => {
        if (d.error) {
            toast(d.error);
            return;
        }
        navigator.clipboard
            .writeText('cbc --resume ' + (d.cbcSessionId ?? ''))
            .then(() => {
            toast('PowerShell opened. Session copied to clipboard.');
        })
            .catch(() => {
            toast('PowerShell opened for takeover.');
        });
    });
}
function killWorker() {
    if (!currentWorkerId) {
        toast('No worker running');
        return;
    }
    if (!confirm('Kill worker ' + currentWorkerId + '?'))
        return;
    const deadId = currentWorkerId;
    currentWorkerId = null;
    updateTopBar();
    fetch('/api/kill/' + deadId, { method: 'POST' })
        .then((r) => r.json())
        .then((d) => {
        if (d.error)
            toast(d.error);
    });
}
// ── Send message ──
function send() {
    const input = document.getElementById('chatInput');
    const text = input.value.trim();
    if (!currentSessionId) {
        toast('Select a session first');
        return;
    }
    if (!text)
        return;
    input.value = '';
    addMessage('user', text);
    function doSend() {
        ws.send(JSON.stringify({
            type: 'user_inject',
            sessionId: currentSessionId,
            text: text,
        }));
    }
    if (!currentWorkerId) {
        const model = getSettingModel();
        const mode = document.getElementById('settingMode').value;
        const body = {
            sessionId: currentSessionId,
            model: model,
        };
        if (mode)
            body.permissionMode = mode;
        body.alwaysThinkingEnabled = document.getElementById('settingThinking').checked;
        body.effort = document.getElementById('settingEffort').value;
        fetch('/api/spawn', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        })
            .then((r) => r.json())
            .then((d) => {
            if (d.error) {
                toast('Spawn failed: ' + d.error);
                return;
            }
            currentWorkerId = d.workerId ?? null;
            doSend();
        });
        return;
    }
    // worker exists: if panel has unapplied changes, apply them first, then send
    if (hasPendingChanges()) {
        const thinking = document.getElementById('settingThinking').checked;
        const effort = document.getElementById('settingEffort').value;
        fetch('/api/worker/' + currentWorkerId + '/settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                model: getSettingModel(),
                permissionMode: document.getElementById('settingMode').value || undefined,
                alwaysThinkingEnabled: thinking,
                effort: effort,
            }),
        })
            .then((r) => r.json())
            .then((d) => {
            if (d.error) {
                toast(d.error);
                return;
            }
            markSettingsApplied();
            doSend();
        });
        return;
    }
    doSend();
}
// ── New Session ──
function newSession() {
    let name = 'session-' + (modelData.length + 1);
    let n = 1;
    while (modelData.find((s) => s.name === name)) {
        name = 'session-' + (modelData.length + n);
        n++;
    }
    fetch('/api/sessions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: name }),
    })
        .then((r) => r.json())
        .then((d) => {
        if (d.error) {
            toast(d.error);
            return;
        }
        modelData.push(d);
        selectSession(d.id);
        refreshSessions();
    });
}
function deleteSession(id) {
    if (!confirm('Delete session ' + id.slice(0, 12) + '\u2026?'))
        return;
    fetch('/api/sessions/' + id, { method: 'DELETE' })
        .then((r) => r.json())
        .then((d) => {
        if (d.error) {
            toast(d.error);
            return;
        }
        if (currentSessionId === id) {
            currentSessionId = null;
            currentWorkerId = null;
            showEmpty();
        }
        refreshSessions();
    });
}
// ── Init ──
function init() {
    fetch('/api/adapter/config')
        .then((r) => r.json())
        .then((data) => {
        allModels = data.models || [];
        defaultModel = data.defaultModel || 'deepseek-v4-flash';
        effortValues = data.effortValues || [];
        permissionModes = data.permissionModes || [];
        buildModelSelect();
        buildModeSelect();
        buildEffortSelect();
    });
    refreshSessions();
    setInterval(refreshSessions, 5000);
}
function buildModelSelect() {
    const sel = document.getElementById('settingModel');
    sel.innerHTML = '';
    const blank = document.createElement('option');
    blank.value = '';
    blank.textContent = '\u2014 model \u2014';
    sel.appendChild(blank);
    allModels.forEach((m) => {
        const opt = document.createElement('option');
        opt.value = m;
        opt.textContent = m;
        sel.appendChild(opt);
    });
    const cust = document.createElement('option');
    cust.value = '__custom__';
    cust.textContent = '\u270e custom\u2026';
    sel.appendChild(cust);
    sel.onchange = function () {
        (document.getElementById('settingModelCustom')).style.display =
            sel.value === '__custom__' ? 'inline-block' : 'none';
        updateSetButtonVisibility();
    };
    sel.setAttribute('data-loaded', '1');
}
function buildModeSelect() {
    const sel = document.getElementById('settingMode');
    sel.innerHTML = '';
    permissionModes.forEach((p) => {
        const opt = document.createElement('option');
        opt.value = p.value;
        opt.textContent = p.label;
        sel.appendChild(opt);
    });
}
function buildEffortSelect() {
    const sel = document.getElementById('settingEffort');
    sel.innerHTML = '';
    effortValues.forEach((v) => {
        const opt = document.createElement('option');
        opt.value = v;
        opt.textContent = v;
        sel.appendChild(opt);
    });
}
function esc(s) {
    const d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML;
}
function toast(msg) {
    const el = document.getElementById('toast');
    el.textContent = msg;
    el.className = 'toast show';
    setTimeout(() => {
        el.className = 'toast';
    }, 3000);
}
init();
//# sourceMappingURL=app.js.map