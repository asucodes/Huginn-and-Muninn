import * as vscode from 'vscode';

export class ReviewPanel implements vscode.WebviewViewProvider {
  public static readonly viewType = 'taknee.review';
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
      if (msg.kind === 'load') await this.loadPending();
      if (msg.kind === 'resolve') await this.resolve(msg.approvalId, msg.decision, msg.acceptedIds);
    });
    this.loadPending();
  }

  async loadPending() {
    try {
      const r = await fetch(`${this.kernelUrl}/approvals`);
      const list = await r.json();
      this.panel?.webview.postMessage({kind: 'pending', approvals: list});
    } catch {}
  }

  async resolve(approvalId: number, decision: string, acceptedIds: number[]) {
    await fetch(`${this.kernelUrl}/approvals/${approvalId}/resolve`, {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({decision, accepted_ids: acceptedIds}),
    });
    this.loadPending();
  }

  show() { vscode.commands.executeCommand('workbench.view.extension.taknee'); }

  private html() {
    return /*html*/ `
    <style>
      :root { --bg: var(--vscode-editor-background); --fg: var(--vscode-editor-foreground);
              --accent: var(--vscode-button-background); --green: var(--vscode-terminal-ansiGreen);
              --red: var(--vscode-terminal-ansiRed); --border: var(--vscode-panel-border); }
      * { box-sizing: border-box; margin: 0; padding: 0; }
      body { font-family: var(--vscode-font-family); background: var(--bg); color: var(--fg); font-size: 12px; }
      h3 { padding: 12px; border-bottom: 1px solid var(--border); font-size: 13px; }
      #toolbar { display: flex; gap: 6px; padding: 8px 12px; border-bottom: 1px solid var(--border); position: sticky; top: 0; background: var(--bg); z-index: 5; }
      #toolbar button { border: none; border-radius: 4px; padding: 4px 12px; cursor: pointer; font-weight: 600; }
      .btn-accept { background: var(--green); color: #000; }
      .btn-reject { background: var(--red); color: #fff; }
      #hunks { padding: 8px 12px; overflow-y: auto; }
      .hunk { margin-bottom: 12px; border: 1px solid var(--border); border-radius: 6px; overflow: hidden; }
      .hunk-header { display: flex; justify-content: space-between; align-items: center; padding: 6px 12px;
                         background: color-mix(in srgb, var(--fg) 6%, transparent); cursor: pointer; }
      .hunk-header input { margin-right: 8px; }
      .hunk-file { font-weight: 600; font-size: 11px; text-transform: uppercase; }
      .diff { padding: 8px 12px; font-family: var(--vscode-editor-font-family); font-size: 11px; overflow-x: auto; }
      .del { background: color-mix(in srgb, var(--red) 15%, transparent); }
      .add { background: color-mix(in srgb, var(--green) 15%, transparent); }
      .empty { padding: 40px; text-align: center; color: var(--vscode-descriptionForeground); }
    </style>
    <h3>Review</h3>
    <div id="toolbar" style="display:none">
      <button class="btn-accept" onclick="resolve('accepted')">Accept All</button>
      <button class="btn-reject" onclick="resolve('rejected')">Reject All</button>
      <button class="btn-accept" onclick="resolveSelected()">Accept Selected</button>
      <button class="btn-reject" onclick="resolveSelected('rejected')">Reject Selected</button>
    </div>
    <div id="hunks"><div class="empty">No pending changes. Start a task to see hunks here.</div></div>
    <script>
      const vscode = acquireVsCodeApi();
      let currentApproval = null;
      function resolve(decision, acceptedIds) {
        if (!currentApproval) return;
        vscode.postMessage({kind:'resolve', approvalId: currentApproval.id, decision, acceptedIds: acceptedIds || []});
        currentApproval = null; document.getElementById('toolbar').style.display = 'none';
        document.getElementById('hunks').innerHTML = '<div class="empty">Resolving…</div>';
      }
      function resolveSelected(decision = 'partial') {
        const ids = [...document.querySelectorAll('.hunk-check:checked')].map(c => +c.dataset.id);
        resolve(decision, ids);
      }
      function toggleCheck(id, el) {
        const checks = document.querySelectorAll('.hunk-check');
        const all = [...checks].every(c => c.checked);
        checks.forEach(c => c.checked = all ? false : true);
        if (el) el.checked = !all;
      }
      function esc(s) { return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
      function diffHtml(search, replace) {
        const sLines = search.split('\\n'), rLines = replace.split('\\n');
        const max = Math.max(sLines.length, rLines.length);
        let h = '';
        for (let i = 0; i < max; i++) {
          const s = sLines[i] ?? '', r = rLines[i] ?? '';
          if (s === r) { h += '<div>' + esc(s) + '</div>'; }
          else {
            if (s) h += '<div class="del">- ' + esc(s) + '</div>';
            if (r) h += '<div class="add">+ ' + esc(r) + '</div>';
          }
        }
        return h;
      }
      window.addEventListener('message', ({data}) => {
        if (data.kind !== 'pending') return;
        if (!data.approvals || !data.approvals.length) {
          currentApproval = null;
          document.getElementById('toolbar').style.display = 'none';
          document.getElementById('hunks').innerHTML = '<div class="empty">No pending changes. Start a task to see hunks here.</div>';
          return;
        }
        currentApproval = data.approvals[0];
        const payload = currentApproval.payload || [];
        document.getElementById('toolbar').style.display = 'flex';
        if (currentApproval.kind === 'command') {
          const cmd = payload.command || '';
          document.getElementById('hunks').innerHTML =
            '<div class="hunk"><div class="hunk-header"><span class="hunk-file">run command</span></div>' +
            '<div class="diff"><pre>' + esc(cmd) + '</pre></div></div>' +
            '<p class="empty">Side-effecting command: accept to run, reject to skip tests.</p>';
          return;
        }
        if (!Array.isArray(payload) || !payload.length) {
          document.getElementById('hunks').innerHTML = '<div class="empty">Empty approval payload.</div>';
          return;
        }
        let html = '';
        payload.forEach((h, i) => {
          html += '<div class="hunk"><div class="hunk-header">' +
            '<input type="checkbox" class="hunk-check" data-id="' + i + '" checked>' +
            '<span class="hunk-file">' + esc(h.file) + '</span></div>' +
            '<div class="diff">' + diffHtml(h.search || '', h.replace || '') + '</div></div>';
        });
        document.getElementById('hunks').innerHTML = html;
      });
      setInterval(() => vscode.postMessage({kind:'load'}), 3000);
    </script>`;
  }
}
