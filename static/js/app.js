"use strict";
// ── Types ──
// ── State ──
let allModels = [];
let defaultModel = 'deepseek-v4-flash';
let currentSessionId = null;
let currentWorkerId = null;
let modelData = [];
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
    syncSettingsPanel(s);
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
}
function syncSettingsPanel(s) {
    const sel = document.getElementById('settingModel');
    if (sel.getAttribute('data-loaded') !== '1')
        return;
    sel.value =
        allModels.indexOf(s.model || defaultModel) >= 0
            ? s.model || defaultModel
            : '';
    document.getElementById('settingMode').value =
        s.permissionMode || '';
    document.getElementById('settingThinking').checked =
        s.alwaysThinkingEnabled || false;
    document.getElementById('settingEffort').value =
        s.effort || '';
    (document.getElementById('effortGroup')).style.display =
        s.alwaysThinkingEnabled ? '' : 'none';
}
function getSettingModel() {
    const sel = document.getElementById('settingModel');
    if (sel.value === '__custom__') {
        const inp = document.getElementById('settingModelCustom');
        return inp.value.trim() || defaultModel;
    }
    return sel.value || defaultModel;
}
function applyModel() {
    if (!currentWorkerId) {
        toast('No worker running');
        return;
    }
    const model = getSettingModel();
    fetch('/api/worker/' + currentWorkerId + '/switch-model', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ model: model }),
    })
        .then((r) => r.json())
        .then((d) => {
        if (d.error)
            toast(d.error);
        else
            refreshSessions();
    });
}
function applyMode() {
    if (!currentWorkerId) {
        toast('No worker running');
        return;
    }
    const mode = document.getElementById('settingMode').value;
    if (!mode) {
        toast('Select a mode');
        return;
    }
    fetch('/api/worker/' + currentWorkerId + '/switch-mode', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ permissionMode: mode }),
    })
        .then((r) => r.json())
        .then((d) => {
        if (d.error)
            toast(d.error);
        else
            refreshSessions();
    });
}
function applyThinking() {
    const thinking = document.getElementById('settingThinking').checked;
    (document.getElementById('effortGroup')).style.display = thinking ? '' : 'none';
    if (thinking) {
        const eff = document.getElementById('settingEffort');
        if (!eff.value || eff.value === 'minimal')
            eff.value = 'medium';
    }
    const effort = document.getElementById('settingEffort').value;
    const s = modelData.find((x) => x.id === currentSessionId);
    const originalThinking = s ? s.alwaysThinkingEnabled : false;
    const originalEffort = s ? s.effort : '';
    if (s) {
        s.alwaysThinkingEnabled = thinking;
        s.effort = thinking ? effort : s.effort;
    }
    function revert() {
        document.getElementById('settingThinking').checked = originalThinking;
        (document.getElementById('effortGroup')).style.display = originalThinking ? '' : 'none';
        if (s) {
            s.alwaysThinkingEnabled = originalThinking;
            s.effort = originalEffort;
        }
    }
    if (!currentWorkerId) {
        if (!currentSessionId)
            return;
        fetch('/api/sessions/' + currentSessionId, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                alwaysThinkingEnabled: thinking,
                effort: effort,
            }),
        })
            .then((r) => r.json())
            .then((d) => {
            if (d.error) {
                toast(d.error);
                revert();
            }
        });
        return;
    }
    fetch('/api/worker/' + currentWorkerId + '/switch-thinking', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            alwaysThinkingEnabled: thinking,
            effort: effort,
        }),
    })
        .then((r) => r.json())
        .then((d) => {
        if (d.error) {
            toast(d.error);
            revert();
        }
    });
}
function applyEffort() {
    const effort = document.getElementById('settingEffort').value;
    const s = modelData.find((x) => x.id === currentSessionId);
    const originalEffort = s ? s.effort : '';
    if (s)
        s.effort = effort;
    if (!currentWorkerId) {
        if (!currentSessionId)
            return;
        fetch('/api/sessions/' + currentSessionId, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ effort: effort }),
        })
            .then((r) => r.json())
            .then((d) => {
            if (d.error) {
                toast(d.error);
                if (s)
                    s.effort = originalEffort;
                document.getElementById('settingEffort').value =
                    originalEffort;
            }
        });
        return;
    }
    fetch('/api/worker/' + currentWorkerId + '/switch-thinking', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ effort: effort }),
    })
        .then((r) => r.json())
        .then((d) => {
        if (d.error)
            toast(d.error);
        else
            refreshSessions();
    });
}
function restartWorker() {
    if (currentWorkerId) {
        fetch('/api/worker/' + currentWorkerId + '/restart', { method: 'POST' })
            .then((r) => r.json())
            .then((d) => {
            if (d.error)
                toast(d.error);
        });
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
    fetch('/api/models')
        .then((r) => r.json())
        .then((data) => {
        allModels = data.models || [];
        defaultModel = data.default || 'deepseek-v4-flash';
        buildModelSelect();
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
    };
    sel.setAttribute('data-loaded', '1');
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