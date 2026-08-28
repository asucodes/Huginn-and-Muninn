import * as vscode from 'vscode';

export class TracesPanel implements vscode.WebviewViewProvider {
  public static readonly viewType = 'taknee.traces';
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
      if (msg.kind === 'loadTask') await this.loadTask(msg.taskId);
    });
  }

  async loadTask(taskId: string) {
    try {
      const [spans, events] = await Promise.all([
        fetch(`${this.kernelUrl}/tasks/${taskId}/spans`).then(r => r.json()),
        fetch(`${this.kernelUrl}/tasks/${taskId}/events`).then(r => r.json()),
      ]);
      this.panel?.webview.postMessage({kind: 'traces', spans, events});
    } catch (e: any) {
      this.panel?.webview.postMessage({kind: 'error', message: e.message});
    }
  }

  show() { vscode.commands.executeCommand('workbench.view.extension.taknee'); }

  private html() {
    return /*html*/ `
    <style>
      :root { --bg: var(--vscode-editor-background); --fg: var(--vscode-editor-foreground);
              --accent: var(--vscode-button-background); --border: var(--vscode-panel-border); }
      * { box-sizing: border-box; margin: 0; padding: 0; }
      body { font-family: var(--vscode-font-family); background: var(--bg); color: var(--fg); font-size: 12px; }
      #toolbar { display: flex; gap: 6px; padding: 8px; border-bottom: 1px solid var(--border); }
      #toolbar input { flex: 1; background: var(--bg); border: 1px solid var(--border); border-radius: 4px;
                         padding: 4px 8px; color: var(--fg); font-family: inherit; }
      #toolbar button { background: var(--accent); color: #fff; border: none; border-radius: 4px; padding: 4px 12px; cursor: pointer; }
      #tree { padding: 8px; font-family: var(--vscode-editor-font-family); overflow-y: auto; }
      .node { padding: 2px 0; cursor: pointer; white-space: nowrap; }
      .node:hover { background: color-mix(in srgb, var(--fg) 8%, transparent); }
      .node .kind { color: var(--vscode-descriptionForeground); font-size: 11px; margin-right: 6px; }
      .node .name { font-weight: 600; }
      .node .meta { color: var(--vscode-descriptionForeground); margin-left: 8px; font-size: 11px; }
      .children { margin-left: 16px; border-left: 1px solid var(--border); padding-left: 8px; }
      .leaf { color: var(--vscode-descriptionForeground); }
      #detail { position: absolute; top: 0; right: 0; width: 55%; height: 100%; background: var(--bg);
                 border-left: 1px solid var(--border); padding: 12px; overflow-y: auto; display: none; z-index: 10; }
      #detail.open { display: block; }
      #detail h3 { margin: 12px 0 6px; font-size: 13px; }
      #detail pre { background: #0002; padding: 8px; border-radius: 4px; overflow-x: auto; font-size: 11px; max-height: 40vh; }
      #detail .field { margin: 4px 0; }
      #detail .label { color: var(--vscode-descriptionForeground); font-size: 11px; }
      .cost { color: #f0c040; }
    </style>
    <div id="toolbar">
      <input id="taskId" placeholder="Paste task ID to inspect…" />
      <button onclick="const vscode=acquireVsCodeApi(); vscode.postMessage({kind:'loadTask',taskId:document.getElementById('taskId').value})">Load</button>
    </div>
    <div style="position:relative; height:calc(100vh - 50px); overflow:hidden;">
      <div id="tree">Traces: load a task to see its call hierarchy.</div>
      <div id="detail">
        <button onclick="document.getElementById('detail').classList.remove('open')" style="float:right">Close</button>
        <div id="detail-content"></div>
      </div>
    </div>
    <script>
      const vscode = acquireVsCodeApi();
      window.addEventListener('message', ({data}) => {
        if (data.kind === 'traces') renderTree(data.spans, data.events);
        if (data.kind === 'error') document.getElementById('tree').textContent = 'Error: ' + data.message;
      });
      function renderTree(spans, events) {
        const root = document.getElementById('tree'); root.innerHTML = '';
        const byParent = {}; spans.forEach(s => { (byParent[s.parent_id] = byParent[s.parent_id] || []).push(s); });
        const children = (pid) => {
          const div = document.createElement('div'); div.className = 'children';
          (byParent[pid] || []).forEach(s => {
            const n = document.createElement('div'); n.className = 'node';
            const dur = s.t_start && s.t_end ? ((s.t_end - s.t_start) * 1000).toFixed(0) + 'ms' : '';
            const cost = s.usd > 0 ? ' · $' + s.usd.toFixed(4) : '';
            n.innerHTML = '<span class="kind">' + s.kind + '</span><span class="name">' + s.name + '</span>' +
              '<span class="meta">' + (s.model||'') + (s.provider ? ' @ ' + s.provider : '') + ' ' + dur + cost + '</span>';
            n.onclick = () => showDetail(s);
            const kids = children(s.id);
            if (kids.children.length) n.appendChild(kids);
            div.appendChild(n);
          });
          return div;
        };
        root.appendChild(children(null));
      }
      function showDetail(s) {
        const d = document.getElementById('detail'); d.classList.add('open');
        const c = document.getElementById('detail-content');
        let h = '<h3>' + s.kind + ': ' + s.name + '</h3>';
        if (s.model) h += '<div class="field"><span class="label">Model:</span> ' + s.model + ' @ ' + (s.provider||'') + '</div>';
        if (s.route_reason) h += '<div class="field"><span class="label">Route:</span> ' + s.route_reason + '</div>';
        if (s.tokens_in || s.tokens_out) h += '<div class="field"><span class="label">Tokens:</span> ' + s.tokens_in + ' in / ' + s.tokens_out + ' out <span class="cost">($' + (s.usd||0).toFixed(4) + ')</span></div>';
        if (s.input) { h += '<h3>Input</h3><pre>' + JSON.stringify(s.input, null, 2).substring(0, 3000) + '</pre>'; }
        if (s.output) { h += '<h3>Output</h3><pre>' + JSON.stringify(s.output, null, 2).substring(0, 3000) + '</pre>'; }
        c.innerHTML = h;
      }
    </script>`;
  }
}
