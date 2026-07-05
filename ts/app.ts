// ── Types ──

interface Message {
  role: string;
  content: string;
}

interface Session {
  id: string;
  name: string;
  cbcSessionId?: string | null;
  model?: string | null;
  permissionMode?: string | null;
  alwaysThinkingEnabled: boolean;
  effort: string;
  maxThinkingTokens?: number;
  workdir?: string;
  workerStatus?: string | null;
  workerId?: string | null;
  history: Message[];
  lastResult?: Record<string, unknown> | null;
}

interface WorkerEventContent {
  type: string;
  text?: string;
  thinking?: string;
  name?: string;
  input?: Record<string, unknown>;
}

interface WorkerEvent {
  type: string;
  subtype?: string;
  message?: {
    content?: WorkerEventContent[];
  };
  session_id?: string;
  model?: string;
  is_error?: boolean;
  result?: string;
  cbc_session_id?: string;
}

interface StreamEvent {
  type: string;
  sessionId?: string;
  workerId?: string;
  event?: WorkerEvent;
  message?: string;
  status?: string;
  name?: string;
  cbcSessionId?: string;
}

interface ApiSessionsResponse {
  sessions: Session[];
  error?: string;
}

interface ApiModelsResponse {
  models: string[];
  default: string;
}

interface ApiGenericResponse {
  error?: string;
  workerId?: string;
  sessionId?: string;
  status?: string;
  cbcSessionId?: string;
}

interface ApiConfigResponse {
  models: string[];
  defaultModel: string;
  effortValues: string[];
  permissionModes: {value: string; label: string}[];
}

interface SyncedSettings {
  model: string;
  permissionMode: string;
  alwaysThinkingEnabled: boolean;
  effort: string;
}

// ── State ──

let allModels: string[] = [];
let defaultModel: string = 'deepseek-v4-flash';
let effortValues: string[] = [];
let permissionModes: {value: string; label: string}[] = [];
let _adapterConfigReady: boolean = false;
let currentSessionId: string | null = null;
let currentWorkerId: string | null = null;
let modelData: Session[] = [];
let lastSyncedSettings: SyncedSettings | null = null;

// ── WebSocket ──

const wsProtocol = location.protocol === 'https:' ? 'wss://' : 'ws://';
const ws: WebSocket = new WebSocket(wsProtocol + location.host + '/ws');
ws.onopen = refreshSessions;
ws.onmessage = onWsMessage;

function onWsMessage(e: MessageEvent): void {
  const d: StreamEvent = JSON.parse(e.data);
  switch (d.type) {
    case 'worker.spawned':
    case 'worker.restarted':
    case 'worker.reconfigured':
      _applyWorkerUpdate(d.sessionId, d.workerId, 'idle');
      break;
    case 'worker.destroyed':
    case 'worker.crashed':
      _applyWorkerUpdate(d.sessionId, null, null);
      break;
    case 'worker.stream':
      if (d.sessionId === currentSessionId && d.event) {
        appendEvent(d.event);
      }
      break;
    case 'worker.result':
      if (d.sessionId === currentSessionId) appendResult(d);
      _applyWorkerUpdate(d.sessionId, d.workerId, 'idle');
      break;
    case 'worker.status':
      _applyWorkerUpdate(d.sessionId, d.workerId, d.status ?? 'idle');
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

/** Apply a worker update from a WebSocket event.
 *  Side effects: syncs currentWorkerId, updateTopBar (incl. mobile dot),
 *  renderSessionList, and triggers a debounced refreshSessions fetch. */
function _applyWorkerUpdate(
  sessionId: string | undefined,
  workerId: string | undefined | null,
  status: string | null
): void {
  for (let i = 0; i < modelData.length; i++) {
    if (modelData[i].id === sessionId) {
      modelData[i].workerId = workerId ?? undefined;
      modelData[i].workerStatus = status;
      break;
    }
  }
  if (sessionId === currentSessionId) {
    currentWorkerId = workerId ?? null;
    updateTopBar();
  }
  renderSessionList();
  refreshSessions();
}

// ── Session list ──
let _refreshVersion: number = 0;

function refreshSessions(): void {
  _refreshVersion++;
  const version = _refreshVersion;
  fetch('/api/sessions')
    .then((r: Response) => r.json())
    .then((data: ApiSessionsResponse) => {
      if (version !== _refreshVersion) return;
      modelData = data.sessions || [];
      renderSessionList();
      const matched = modelData.find((s: Session) => s.id === currentSessionId);
      if (!matched) {
        currentSessionId = null;
        currentWorkerId = null;
        showEmpty();
      } else {
        currentWorkerId = matched.workerId ?? null;
        const chatNameEl = document.getElementById('chatName')!;
        if (chatNameEl.style.display !== 'none') {
          renderMessages(matched.history || []);
        }
      }
      if (currentSessionId) updateTopBar();
    });
}

function renderSessionList(): void {
  const el = document.getElementById('sessionList')!;
  el.innerHTML = '';
  modelData.forEach((s: Session) => {
    const div = document.createElement('div');
    div.className = 'sess-item' + (s.id === currentSessionId ? ' active' : '');
    div.onclick = function (e: MouseEvent) {
      const target = e.target as HTMLElement;
      if (target.closest('.sess-del')) return;
      selectSession(s.id);
    };

    let lastMsg = '';
    const h = s.history || [];
    if (h.length > 0) {
      const last = h[h.length - 1];
      lastMsg = last.content || '';
      if (lastMsg.length > 40) lastMsg = lastMsg.slice(0, 40) + '\u2026';
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

function selectSession(id: string): void {
  currentSessionId = id;
  const s = modelData.find((x: Session) => x.id === id);
  if (!s) return;

  currentWorkerId = s.workerId ?? null;

  renderSessionList();
  updateTopBar();
  renderMessages(s.history || []);
  const settingsBtn = document.getElementById('settingsBtn')!;
  settingsBtn.style.display = '';
  // sync panel if it's already open
  if (document.getElementById('settingsPanel')!.classList.contains('open')) {
    syncPanelFromServer();
  }
}

// ── Top bar ──

function updateTopBar(): void {
  const s = modelData.find((x: Session) => x.id === currentSessionId);
  if (!s) {
    showEmpty();
    return;
  }
  (document.getElementById('emptyHint')!).style.display = 'none';
  (document.getElementById('chatName')!).style.display = '';
  (document.getElementById('chatModel')!).style.display = '';
  (document.getElementById('chatName')!).textContent =
    s.name || (currentSessionId ?? '').slice(0, 12);
  (document.getElementById('chatModel')!).textContent = s.model || defaultModel;
  const status = s.workerStatus || 'offline';
  (document.getElementById('chatStatus')!).textContent =
    status + (currentWorkerId ? ' (' + currentWorkerId + ')' : ' (no worker)');
  const dot = document.getElementById('mobileWorkerDot');
  if (dot) dot.className = 's-dot ' + status;
}

function showEmpty(): void {
  (document.getElementById('emptyHint')!).style.display = '';
  (document.getElementById('chatName')!).style.display = 'none';
  (document.getElementById('chatModel')!).style.display = 'none';
  (document.getElementById('chatStatus')!).textContent = '';
  const dot = document.getElementById('mobileWorkerDot');
  if (dot) dot.className = 's-dot offline';
  (document.getElementById('settingsBtn')!).style.display = 'none';
  (document.getElementById('settingsPanel')!).className = '';
  (document.getElementById('messages')!).innerHTML =
    '<div class="empty-chat">Select a session to start</div>';
}

// ── Messages ──

function renderMessages(history: Message[]): void {
  const el = document.getElementById('messages')!;
  el.innerHTML = '';
  if (!history || history.length === 0) {
    el.innerHTML =
      '<div class="empty-chat">No messages yet. Start a conversation.</div>';
    return;
  }
  history.forEach((h: Message) => {
    addMessage(h.role, h.content);
  });
  el.scrollTop = el.scrollHeight;
}

function addMessage(role: string, content: string): void {
  const el = document.getElementById('messages')!;
  const div = document.createElement('div');

  if (role === 'user') {
    div.className = 'msg user';
    div.textContent = content;
  } else if (role === 'assistant') {
    div.className = 'msg assistant';
    const display = content.replace(/🔧.*(\n|$)/g, '').trim();
    div.textContent = display || '(tool call only)';
  } else if (role === 'thinking') {
    div.className = 'msg thinking';
    div.innerHTML =
      '💭 <span class="thinking-toggle">show thinking</span><div class="thinking-body">' +
      esc(content) +
      '</div>';
    div.onclick = function () {
      const body = div.querySelector('.thinking-body');
      const toggle = div.querySelector('.thinking-toggle');
      if (!body || !toggle) return;
      body.classList.toggle('open');
      toggle.textContent = body.classList.contains('open')
        ? 'hide thinking'
        : 'show thinking';
    };
  } else if (role === 'tool') {
    div.className = 'msg tool';
    div.textContent = '🔧 ' + content;
  } else {
    div.className = 'msg system';
    div.textContent = content || '';
  }

  el.appendChild(div);
  el.scrollTop = el.scrollHeight;
}

function appendEvent(event: WorkerEvent): void {
  const t = event.type;
  if (t === 'system' && event.subtype === 'init') return;
  if (t === 'result') return;

  if (t === 'assistant') {
    const content = (event.message && event.message.content) || [];
    content.forEach((b: WorkerEventContent) => {
      if (b.type === 'text') addMessage('assistant', b.text ?? '');
      else if (b.type === 'thinking') addMessage('thinking', b.thinking ?? '');
      else if (b.type === 'tool_use')
        addMessage(
          'tool',
          (b.name ?? '') + '(' + JSON.stringify(b.input || {}) + ')'
        );
    });
  }
}

function appendResult(d: StreamEvent): void {
  const status = d.status === 'error' ? 'error' : 'done';
  addMessage('system', '[' + status.toUpperCase() + '] Task completed');
}

// ── Settings panel ──

function toggleSettings(): void {
  const panel = document.getElementById('settingsPanel')!;
  const btn = document.getElementById('settingsBtn')!;
  const isOpen = panel.classList.toggle('open');
  btn.classList.toggle('open', isOpen);
  if (isOpen) {
    if (!_adapterConfigReady)
      toast('Loading settings…');
    syncPanelFromServer();
  }
}

/** Sync the settings panel fields to the current session's server-side values.
 *  Called when the panel opens or the session switches. */
function syncPanelFromServer(): void {
  const s = modelData.find((x: Session) => x.id === currentSessionId);
  if (!s) return;

  // wait until all selects are populated (async adapter config fetch)
  if ((document.getElementById('settingModel') as HTMLSelectElement).getAttribute('data-loaded') !== '1') return;
  if (!_adapterConfigReady) return;

  const sel = document.getElementById('settingModel') as HTMLSelectElement;
  const model = s.model || defaultModel;
  sel.value = allModels.indexOf(model) >= 0 ? model : '';

  (document.getElementById('settingMode') as HTMLSelectElement).value =
    s.permissionMode || '';
  (document.getElementById('settingThinking') as HTMLInputElement).checked =
    s.alwaysThinkingEnabled || false;
  (document.getElementById('settingEffort') as HTMLSelectElement).value =
    effortValues.indexOf(s.effort) >= 0 ? s.effort : (effortValues[1] || effortValues[0] || '');
  (document.getElementById('effortGroup')!).style.display =
    (s.alwaysThinkingEnabled && effortValues.length > 0) ? '' : 'none';

  // record the baseline so we can detect pending changes
  lastSyncedSettings = {
    model: getSettingModel(),
    permissionMode: (document.getElementById('settingMode') as HTMLSelectElement).value,
    alwaysThinkingEnabled: (
      document.getElementById('settingThinking') as HTMLInputElement
    ).checked,
    effort: (document.getElementById('settingEffort') as HTMLSelectElement).value,
  };
  updateSetButtonVisibility();
}

/** Returns true when any panel field differs from lastSyncedSettings. */
function hasPendingChanges(): boolean {
  if (!lastSyncedSettings) return false;
  return (
    getSettingModel() !== lastSyncedSettings.model ||
    (document.getElementById('settingMode') as HTMLSelectElement).value !==
      lastSyncedSettings.permissionMode ||
    (document.getElementById('settingThinking') as HTMLInputElement).checked !==
      lastSyncedSettings.alwaysThinkingEnabled ||
    (document.getElementById('settingEffort') as HTMLSelectElement).value !==
      lastSyncedSettings.effort
  );
}

function getSettingModel(): string {
  const sel = document.getElementById('settingModel') as HTMLSelectElement;
  if (sel.value === '__custom__') {
    const inp = document.getElementById(
      'settingModelCustom'
    ) as HTMLInputElement;
    return inp.value.trim() || defaultModel;
  }
  return sel.value || defaultModel;
}

/** Show/hide the Apply Settings button based on whether settings differ from
 *  the last synced state. */
function updateSetButtonVisibility(): void {
  const btn = document.getElementById('applySettingsBtn')!;
  btn.style.display = hasPendingChanges() ? '' : 'none';
}

/** Called when the Think checkbox is toggled: show/hide Effort + auto-select
 *  medium, then update the Set button.  No API call is made. */
function onThinkingToggle(): void {
  const thinking = (document.getElementById('settingThinking') as HTMLInputElement).checked;
  (document.getElementById('effortGroup')!).style.display =
    (thinking && effortValues.length > 0) ? '' : 'none';
  if (thinking && effortValues.length > 0) {
    const eff = document.getElementById('settingEffort') as HTMLSelectElement;
    if (!eff.value || eff.value === effortValues[0])
      eff.value = effortValues[1] || effortValues[0];
  }
  updateSetButtonVisibility();
}

/** Apply all pending model/mode/thinking/effort changes via a single API call.
 *  Handles both the "no worker" (PATCH session) and "worker exists" cases. */
function applySettings(): void {
  if (!currentSessionId) return;
  const s = modelData.find((x: Session) => x.id === currentSessionId);
  if (s && (s.workerStatus === 'running' || s.workerStatus === 'held')) {
    toast('Cannot change settings while worker is busy');
    return;
  }

  const thinking = (document.getElementById('settingThinking') as HTMLInputElement).checked;
  const effort = (document.getElementById('settingEffort') as HTMLSelectElement).value;

  if (!currentWorkerId) {
    // no worker: persist settings to session via PATCH
    fetch('/api/sessions/' + currentSessionId, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        model: getSettingModel(),
        permissionMode: (document.getElementById('settingMode') as HTMLSelectElement).value || undefined,
        alwaysThinkingEnabled: thinking,
        effort: effort,
      }),
    })
      .then((r: Response) => r.json())
      .then((d: ApiGenericResponse) => {
        if (d.error) { toast(d.error); return; }
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
      permissionMode: (document.getElementById('settingMode') as HTMLSelectElement).value || undefined,
      alwaysThinkingEnabled: thinking,
      effort: effort,
    }),
  })
    .then((r: Response) => r.json())
    .then((d: ApiGenericResponse) => {
      if (d.error) { toast(d.error); return; }
      markSettingsApplied();
    });
}

/** Called after successful settings apply — update baseline and hide button. */
function markSettingsApplied(): void {
  lastSyncedSettings = {
    model: getSettingModel(),
    permissionMode: (document.getElementById('settingMode') as HTMLSelectElement).value,
    alwaysThinkingEnabled: (document.getElementById('settingThinking') as HTMLInputElement).checked,
    effort: (document.getElementById('settingEffort') as HTMLSelectElement).value,
  };
  updateSetButtonVisibility();
}

// ── Worker actions (restart / interrupt / takeover / kill) ──

function restartWorker(): void {
  if (currentWorkerId) {
    // Always restart with current panel settings (user intent).
    // applySettings handles both "no-change respawn" and "apply pending changes".
    applySettings();
  } else {
    const model = getSettingModel();
    const mode = (document.getElementById('settingMode') as HTMLSelectElement).value;
    const body: Record<string, unknown> = {
      sessionId: currentSessionId,
      model: model,
    };
    if (mode) body.permissionMode = mode;
    body.alwaysThinkingEnabled = (
      document.getElementById('settingThinking') as HTMLInputElement
    ).checked;
    body.effort = (document.getElementById('settingEffort') as HTMLSelectElement).value;
    fetch('/api/spawn', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
      .then((r: Response) => r.json())
      .then((d: ApiGenericResponse) => {
        if (d.error) {
          toast('Spawn failed: ' + d.error);
          return;
        }
        currentWorkerId = d.workerId ?? null;
        updateTopBar();
      });
  }
}

function interruptWorker(): void {
  if (!currentWorkerId) {
    toast('No worker running');
    return;
  }
  fetch('/api/worker/' + currentWorkerId + '/interrupt', { method: 'POST' })
    .then((r: Response) => r.json())
    .then((d: ApiGenericResponse) => {
      if (d.error) toast(d.error);
    });
}

function takeover(): void {
  if (!currentWorkerId) {
    toast('No worker running');
    return;
  }
  fetch('/api/worker/' + currentWorkerId + '/takeover', { method: 'POST' })
    .then((r: Response) => r.json())
    .then((d: ApiGenericResponse) => {
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

function killWorker(): void {
  if (!currentWorkerId) {
    toast('No worker running');
    return;
  }
  if (!confirm('Kill worker ' + currentWorkerId + '?')) return;
  const deadId = currentWorkerId;
  currentWorkerId = null;
  updateTopBar();
  fetch('/api/kill/' + deadId, { method: 'POST' })
    .then((r: Response) => r.json())
    .then((d: ApiGenericResponse) => {
      if (d.error) toast(d.error);
    });
}

// ── Send message ──

function send(): void {
  const input = document.getElementById('chatInput') as HTMLInputElement;
  const text = input.value.trim();
  if (!currentSessionId) {
    toast('Select a session first');
    return;
  }
  if (!text) return;
  const s = modelData.find((x: Session) => x.id === currentSessionId);
  if (s && (s.workerStatus === 'running' || s.workerStatus === 'held')) {
    toast('Worker is busy');
    return;
  }
  input.value = '';

  addMessage('user', text);

  function doSend(): void {
    const msg = JSON.stringify({
      type: 'user_inject',
      sessionId: currentSessionId,
      text: text,
    });
    if (ws.readyState === WebSocket.OPEN) {
      ws.send(msg);
      return;
    }
    if (ws.readyState === WebSocket.CONNECTING) {
      // Wait for connection to open (common on slow mobile networks)
      ws.addEventListener('open', function handler() {
        ws.removeEventListener('open', handler);
        ws.send(msg);
      }, { once: true } as any);
      return;
    }
    // CLOSED or CLOSING — give up
    toast('Connection lost. Please refresh the page.');
  }

  if (!currentWorkerId) {
    const model = getSettingModel();
    const mode = (document.getElementById('settingMode') as HTMLSelectElement).value;
    const body: Record<string, unknown> = {
      sessionId: currentSessionId,
      model: model,
    };
    if (mode) body.permissionMode = mode;
    body.alwaysThinkingEnabled = (
      document.getElementById('settingThinking') as HTMLInputElement
    ).checked;
    body.effort = (document.getElementById('settingEffort') as HTMLSelectElement).value;
    fetch('/api/spawn', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
      .then((r: Response) => r.json())
      .then((d: ApiGenericResponse) => {
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
    const thinking = (document.getElementById('settingThinking') as HTMLInputElement).checked;
    const effort = (document.getElementById('settingEffort') as HTMLSelectElement).value;
    fetch('/api/worker/' + currentWorkerId + '/settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        model: getSettingModel(),
        permissionMode: (document.getElementById('settingMode') as HTMLSelectElement).value || undefined,
        alwaysThinkingEnabled: thinking,
        effort: effort,
      }),
    })
      .then((r: Response) => r.json())
      .then((d: ApiGenericResponse) => {
        if (d.error) { toast(d.error); return; }
        markSettingsApplied();
        doSend();
      });
    return;
  }

  doSend();
}

// ── New Session ──

function newSession(): void {
  let name = 'session-' + (modelData.length + 1);
  let n = 1;
  while (modelData.find((s: Session) => s.name === name)) {
    name = 'session-' + (modelData.length + n);
    n++;
  }
  fetch('/api/sessions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name: name }),
  })
    .then((r: Response) => r.json())
    .then((d: Session & ApiGenericResponse) => {
      if (d.error) {
        toast(d.error);
        return;
      }
      modelData.push(d as Session);
      selectSession(d.id);
      refreshSessions();
    });
}

function deleteSession(id: string): void {
  if (!confirm('Delete session ' + id.slice(0, 12) + '\u2026?')) return;
  fetch('/api/sessions/' + id, { method: 'DELETE' })
    .then((r: Response) => r.json())
    .then((d: ApiGenericResponse) => {
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

function init(): void {
  fetch('/api/adapter/config')
    .then((r: Response) => r.json())
    .then((data: ApiConfigResponse) => {
      allModels = data.models || [];
      defaultModel = data.defaultModel || 'deepseek-v4-flash';
      effortValues = data.effortValues || [];
      permissionModes = data.permissionModes || [];
      buildModelSelect();
      buildModeSelect();
      buildEffortSelect();
      _adapterConfigReady = true;
      if (document.getElementById('settingsPanel')!.classList.contains('open'))
        syncPanelFromServer();
    });
  refreshSessions();
}

function buildModelSelect(): void {
  const sel = document.getElementById('settingModel') as HTMLSelectElement;
  sel.innerHTML = '';
  const blank = document.createElement('option');
  blank.value = '';
  blank.textContent = '\u2014 model \u2014';
  sel.appendChild(blank);
  allModels.forEach((m: string) => {
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
    (document.getElementById('settingModelCustom')!).style.display =
      sel.value === '__custom__' ? 'inline-block' : 'none';
    updateSetButtonVisibility();
  };
  sel.setAttribute('data-loaded', '1');
}

function buildModeSelect(): void {
  const sel = document.getElementById('settingMode') as HTMLSelectElement;
  sel.innerHTML = '';
  permissionModes.forEach((p: {value: string; label: string}) => {
    const opt = document.createElement('option');
    opt.value = p.value;
    opt.textContent = p.label;
    sel.appendChild(opt);
  });
}

function buildEffortSelect(): void {
  const sel = document.getElementById('settingEffort') as HTMLSelectElement;
  sel.innerHTML = '';
  effortValues.forEach((v: string) => {
    const opt = document.createElement('option');
    opt.value = v;
    opt.textContent = v;
    sel.appendChild(opt);
  });
}

function esc<T extends HTMLElement | string>(s: T): string {
  const d = document.createElement('div');
  d.textContent = s as string;
  return d.innerHTML;
}

function toast(msg: string): void {
  const el = document.getElementById('toast')!;
  el.textContent = msg;
  el.className = 'toast show';
  setTimeout(() => {
    el.className = 'toast';
  }, 3000);
}

window.addEventListener('unhandledrejection', (e: PromiseRejectionEvent) => {
  toast('Request failed');
  e.preventDefault();
});

init();
