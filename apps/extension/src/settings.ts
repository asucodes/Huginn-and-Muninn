import * as vscode from 'vscode';

export class SettingsPanel implements vscode.WebviewViewProvider {
  public static readonly viewType = 'taknee.settings';
  private panel: vscode.WebviewView | undefined;
  private kernelUrl: string;

  constructor(_ctx: vscode.ExtensionContext, kernelUrl: string) {
    this.kernelUrl = kernelUrl;
  }

  resolveWebviewView(
    webviewView: vscode.WebviewView,
    _ctx: vscode.WebviewViewResolveContext,
    _token: vscode.CancellationToken,
  ) {
    this.panel = webviewView;
    webviewView.webview.options = { enableScripts: true };
    webviewView.webview.html = this.html();
    webviewView.webview.onDidReceiveMessage(async (msg) => {
      if (msg.kind === 'load') await this.loadSettings();
      if (msg.kind === 'setKey') await this.setKey(msg.provider, msg.key);
      if (msg.kind === 'testKey') await this.testKey(msg.provider, msg.key);
      if (msg.kind === 'update') await this.update(msg.data);
    });
    this.loadSettings();
  }

  async loadSettings() {
    try {
      const r = await fetch(`${this.kernelUrl}/settings`);
      const data = await r.json();
      this.panel?.webview.postMessage({kind: 'settings', data});
    } catch {}
  }

  async setKey(provider: string, key: string) {
    try {
      const r = await fetch(`${this.kernelUrl}/settings/providers/${provider}/key`, {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({key}),
      });
      const data = await r.json();
      if (!r.ok) {
        this.panel?.webview.postMessage({
          kind: 'testResult', provider, ok: false,
          message: 'Did not save: ' + (data.detail || r.status),
        });
        return;
      }
      this.panel?.webview.postMessage({
        kind: 'testResult', provider, ok: !!data.saved,
        message: data.saved
          ? 'Saved locally. Click Test to ping the API.'
          : 'Did not save: paste a real API key (NVIDIA: nvapi-...).',
      });
      this.loadSettings();
    } catch (e: any) {
      this.panel?.webview.postMessage({
        kind: 'testResult', provider, ok: false,
        message: 'Did not save: kernel unreachable: ' + e.message,
      });
    }
  }

  async testKey(provider: string, key?: string) {
    this.panel?.webview.postMessage({
      kind: 'testResult', provider, ok: true,
      message: 'Pinging ' + provider + '…',
    });
    try {
      const r = await fetch(`${this.kernelUrl}/settings/providers/${provider}/test`, {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({key: key || ''}),
      });
      const data = await r.json();
      this.panel?.webview.postMessage({kind: 'testResult', provider, ...data});
      this.loadSettings();
    } catch (e: any) {
      this.panel?.webview.postMessage({
        kind: 'testResult', provider, ok: false,
        message: 'Did not ping: kernel unreachable: ' + e.message + '. Start it with: uv run taknee',
      });
    }
  }

  async update(data: any) {
    await fetch(`${this.kernelUrl}/settings`, {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(data),
    });
    this.loadSettings();
  }

  show() { vscode.commands.executeCommand('workbench.view.extension.taknee'); }

  private html() {
    const providers = [
      {id: 'groq', name: 'Groq', hint: 'console.groq.com/keys, key starts with gsk_', ph: 'gsk_…'},
      {id: 'openrouter', name: 'OpenRouter', hint: 'openrouter.ai/keys, key starts with sk-or-v1-', ph: 'sk-or-v1-…'},
      {id: 'nim', name: 'NVIDIA NIM', hint: 'build.nvidia.com/settings/api-keys, key starts with nvapi-', ph: 'nvapi-…'},
      {id: 'mistral', name: 'Mistral', hint: 'console.mistral.ai, Devstral direct', ph: 'sk-…'},
      {id: 'cerebras', name: 'Cerebras', hint: 'inference.cerebras.ai — extreme speed', ph: 'csk-…'},
      {id: 'deepinfra', name: 'DeepInfra', hint: 'deepinfra.com — cheap PAYG fallback', ph: 'sk-…'},
    ];
    return /*html*/ `
    <style>
      :root { --bg: var(--vscode-editor-background); --fg: var(--vscode-editor-foreground);
              --accent: var(--vscode-button-background); --border: var(--vscode-panel-border); }
      * { box-sizing: border-box; margin: 0; padding: 0; }
      body { font-family: var(--vscode-font-family); background: var(--bg); color: var(--fg); font-size: 13px; }
      h3 { padding: 12px; border-bottom: 1px solid var(--border); }
      .section { padding: 16px; border-bottom: 1px solid var(--border); }
      .section h4 { margin-bottom: 8px; font-size: 12px; text-transform: uppercase; color: var(--vscode-descriptionForeground); letter-spacing: 0.5px; }
      .row { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; }
      .row label { width: 110px; font-weight: 600; font-size: 12px; flex-shrink: 0; }
      .row input { flex: 1; background: var(--bg); border: 1px solid var(--border); border-radius: 4px;
                           padding: 6px 10px; color: var(--fg); font-family: var(--vscode-editor-font-family); font-size: 12px; }
      .row input:focus { border-color: var(--accent); outline: none; }
      .hint { font-size: 11px; color: var(--vscode-descriptionForeground); margin: -4px 0 10px 118px; }
      button { background: var(--accent); color: #fff; border: none; border-radius: 4px; padding: 5px 14px; cursor: pointer; font-size: 12px; font-weight: 500; }
      button:hover { opacity: 0.9; }
      button.test { background: transparent; color: var(--accent); border: 1px solid var(--accent); }
      .status { font-size: 12px; display: block; margin: 0 0 10px 118px; line-height: 1.4; white-space: normal; }
      .ok { color: var(--vscode-terminal-ansiGreen); }
      .err { color: var(--vscode-terminal-ansiRed); }
      .badge { font-size: 10px; font-weight: 600; letter-spacing: .04em; text-transform: uppercase;
               padding: 1px 6px; border-radius: 3px; border: 1px solid var(--border); color: var(--vscode-descriptionForeground); }
      .badge.on { color: var(--vscode-terminal-ansiGreen); }
      .toggle { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
      .toggle input { width: 16px; height: 16px; }
    </style>
    <h3>Huginn &amp; Muninn Settings</h3>
    <div class="section">
      <h4>API Keys</h4>
      <p style="font-size:11px; color:var(--vscode-descriptionForeground); margin-bottom:12px">
        Keys are stored locally and never logged. Test pings the live API and reports Ping OK / Ping failed / Did not ping.
        NVIDIA: paste only the <code>nvapi-…</code> key, not a code snippet.</p>
      ${providers.map(p => `
        <div class="row">
          <label>${p.name}</label>
          <input id="key-${p.id}" type="password" placeholder="${p.ph}" />
          <span class="badge" id="badge-${p.id}">not saved</span>
          <button class="test" onclick="testKey('${p.id}')">Test</button>
          <button onclick="saveKey('${p.id}')">Save</button>
        </div>
        <span class="status" id="status-${p.id}"></span>
        <div class="hint">${p.hint}</div>
      `).join('')}
    </div>
    <div class="section">
      <h4>Preferences</h4>
      <div class="toggle">
        <input type="checkbox" id="allowPaid" />
        <label for="allowPaid">Allow pay-as-you-go providers</label>
      </div>
      <div class="toggle">
        <input type="checkbox" id="preferLocal" />
        <label for="preferLocal">Prefer local models (Ollama)</label>
      </div>
    </div>
    <div class="section">
      <h4>Governors</h4>
      <div class="row"><label>Max $ / task</label><input id="capUsd" type="number" step="0.05" value="0.40" /></div>
      <div class="row"><label>Max seconds</label><input id="capSec" type="number" step="60" value="2400" /></div>
      <div class="row"><label>Max steps</label><input id="capSteps" type="number" value="120" /></div>
      <button onclick="savePrefs()" style="margin-top:8px">Save Preferences</button>
    </div>
    <script>
      const vscode = acquireVsCodeApi();
      function saveKey(provider) {
        const key = document.getElementById('key-' + provider).value;
        vscode.postMessage({kind:'setKey', provider, key});
        document.getElementById('status-' + provider).textContent = 'saving…';
      }
      function testKey(provider) {
        const key = document.getElementById('key-' + provider).value;
        const el = document.getElementById('status-' + provider);
        el.className = 'status';
        el.textContent = 'Pinging ' + provider + '…';
        vscode.postMessage({kind:'testKey', provider, key});
      }
      function savePrefs() {
        vscode.postMessage({kind:'update', data: {
          allow_paid: document.getElementById('allowPaid').checked,
          prefer_local: document.getElementById('preferLocal').checked,
          caps: { max_usd: +document.getElementById('capUsd').value,
                   max_seconds: +document.getElementById('capSec').value,
                   max_steps: +document.getElementById('capSteps').value }
        }});
      }
      window.addEventListener('message', ({data}) => {
        if (data.kind === 'settings') {
          for (const [p, v] of Object.entries(data.data.providers || {})) {
            const el = document.getElementById('key-' + p);
            const badge = document.getElementById('badge-' + p);
            const set = !!(v && v.key);
            if (el && set) el.placeholder = '•••••••• (saved)';
            if (badge) {
              badge.textContent = set ? 'saved' : 'not saved';
              badge.className = 'badge' + (set ? ' on' : '');
            }
          }
          document.getElementById('allowPaid').checked = !!data.data.allow_paid;
          document.getElementById('preferLocal').checked = !!data.data.prefer_local;
          const caps = data.data.caps || {};
          if (caps.max_usd) document.getElementById('capUsd').value = caps.max_usd;
          if (caps.max_seconds) document.getElementById('capSec').value = caps.max_seconds;
          if (caps.max_steps) document.getElementById('capSteps').value = caps.max_steps;
        }
        if (data.kind === 'testResult') {
          const el = document.getElementById('status-' + data.provider);
          el.className = 'status ' + (data.ok ? 'ok' : 'err');
          el.textContent = data.message;
        }
      });
      vscode.postMessage({kind:'load'});
    </script>`;
  }
}
