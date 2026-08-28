import * as vscode from 'vscode';

export class ChatPanel implements vscode.WebviewViewProvider {
  public static readonly viewType = 'taknee.chat';
  private panel: vscode.WebviewView | undefined;
  private currentTask = '';
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
      if (msg.kind === 'send') await this.sendTask(msg.text);
      if (msg.kind === 'bytheway') await this.byTheWay(msg.text);
    });
  }

  private async expandMentions(prompt: string): Promise<string> {
    const folder = vscode.workspace.workspaceFolders?.[0];
    if (!folder) return prompt;
    const mentions = [...prompt.matchAll(/@([^\s]+)/g)].map(m => m[1]);
    if (!mentions.length) return prompt;
    let out = prompt;
    for (const rel of mentions) {
      try {
        const uri = vscode.Uri.joinPath(folder.uri, rel);
        const bytes = await vscode.workspace.fs.readFile(uri);
        const text = new TextDecoder().decode(bytes).slice(0, 8000);
        out += `\n\n--- pinned file ${rel} ---\n${text}`;
      } catch {
        out += `\n\n--- pinned file ${rel} ---\n(not found in workspace)`;
      }
    }
    return out;
  }

  private async sendTask(prompt: string) {
    try {
      const expanded = await this.expandMentions(prompt);
      const r = await fetch(`${this.kernelUrl}/tasks`, {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({prompt: expanded, auto_approve: false}),
      });
      const data = await r.json();
      if (!r.ok || !data.task_id) {
        this.appendMessage('system', `Kernel error: ${data.detail || JSON.stringify(data)}`);
        return;
      }
      this.currentTask = data.task_id;
      this.appendMessage('system', `Task started: ${data.task_id}`);
      this.pollTask(data.task_id);
    } catch (e: any) {
      this.appendMessage('system', `Error: ${e.message}. Is the kernel running? uv run taknee`);
    }
  }

  private async pollTask(taskId: string) {
    let lastStatus = '';
    const poll = setInterval(async () => {
      try {
        const r = await fetch(`${this.kernelUrl}/tasks/${taskId}`);
        const t = await r.json();
        if (t.stage) this.updateStage(t.stage);
        if (t.status === 'awaiting_approval' && lastStatus !== t.status) {
          this.appendMessage('system', 'Waiting for review: accept or reject in the Review panel.');
        }
        lastStatus = t.status;
        if (t.status !== 'running' && t.status !== 'awaiting_approval') {
          clearInterval(poll);
          const label = t.status === 'done' ? 'Task completed' : `Task ${t.status}: ${t.error || ''}`;
          this.appendMessage('system', `${label} ($${t.usd?.toFixed(4) || '0'} · ${t.tokens_in + t.tokens_out} tokens)`);
        }
      } catch { clearInterval(poll); }
    }, 2000);
  }

  private async byTheWay(question: string) {
    const q = question.replace(/^\/bytheway\s+/i, '').trim();
    try {
      const r = await fetch(`${this.kernelUrl}/bytheway`, {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({question: q}),
      });
      const data = await r.json();
      if (!r.ok) {
        this.appendMessage('system', `bytheway error: ${data.detail || JSON.stringify(data)}`, true);
        return;
      }
      this.appendMessage('system', data.answer || '(empty answer)', true);
    } catch (e: any) {
      this.appendMessage('system', `bytheway failed: ${e.message}. Is the kernel running?`, true);
    }
  }

  private appendMessage(role: string, text: string, ephemeral = false) {
    this.panel?.webview.postMessage({kind: 'message', role, text, ephemeral});
  }

  private updateStage(stage: string) {
    this.panel?.webview.postMessage({kind: 'stage', stage});
  }

  show() { vscode.commands.executeCommand('workbench.view.extension.taknee'); }

  private html() {
    return /*html*/ `
    <style>
      :root { --bg: var(--vscode-editor-background); --fg: var(--vscode-editor-foreground);
              --accent: var(--vscode-button-background); --border: var(--vscode-panel-border); }
      * { box-sizing: border-box; margin: 0; padding: 0; }
      body { font-family: var(--vscode-font-family); background: var(--bg); color: var(--fg);
             display: flex; flex-direction: column; height: 100vh; }
      #messages { flex: 1; overflow-y: auto; padding: 12px; }
      .msg { margin-bottom: 12px; padding: 8px 12px; border-radius: 6px; font-size: 13px; line-height: 1.5; }
      .msg.user { background: var(--accent); color: #fff; margin-left: 20%; border-radius: 12px 12px 2px 12px; }
      .msg.system { background: color-mix(in srgb, var(--fg) 10%, transparent); font-style: italic; }
      .msg.ephemeral { opacity: 0.7; border-left: 3px solid var(--accent); }
      .msg pre { background: #0002; padding: 8px; border-radius: 4px; overflow-x: auto; margin-top: 6px; }
      #stage-bar { padding: 6px 12px; font-size: 11px; text-transform: uppercase; letter-spacing: 1px;
                      color: var(--vscode-descriptionForeground); border-top: 1px solid var(--border); }
      #input-area { display: flex; gap: 8px; padding: 12px; border-top: 1px solid var(--border); }
      #input { flex: 1; background: var(--bg); border: 1px solid var(--border); border-radius: 6px;
                 padding: 8px 12px; color: var(--fg); font-family: inherit; font-size: 13px; resize: none; outline: none; }
      #input:focus { border-color: var(--accent); }
      #send { background: var(--accent); color: #fff; border: none; border-radius: 6px; padding: 8px 16px;
                  cursor: pointer; font-family: inherit; font-weight: 600; }
      #send:hover { opacity: 0.9; }
      .tag { background: var(--accent); color: #fff; padding: 1px 6px; border-radius: 3px;
              font-size: 11px; cursor: pointer; font-family: var(--vscode-editor-font-family); }
      .tag:hover { opacity: 0.85; }
    </style>
    <div id="messages"><div class="msg system">The ravens are ready. Describe a coding task below.</div></div>
    <div id="stage-bar">idle</div>
    <div id="input-area">
      <textarea id="input" rows="3" placeholder="Describe a coding task… (@file for context, /bytheway for isolated question)"></textarea>
      <button id="send">Run</button>
    </div>
    <script>
      const vscode = acquireVsCodeApi();
      const input = document.getElementById('input');
      document.getElementById('send').onclick = () => {
        const text = input.value.trim(); if (!text) return;
        if (text.startsWith('/bytheway ')) {
          vscode.postMessage({kind: 'bytheway', text: text});
        } else {
          vscode.postMessage({kind: 'send', text});
        }
        const div = document.createElement('div'); div.className = 'msg user'; div.textContent = text;
        document.getElementById('messages').appendChild(div);
        input.value = '';
      };
      input.onkeydown = (e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); document.getElementById('send').click(); } };
      window.addEventListener('message', ({data}) => {
        if (data.kind === 'message') {
          const div = document.createElement('div');
          div.className = 'msg ' + data.role + (data.ephemeral ? ' ephemeral' : '');
          div.textContent = data.text;
          document.getElementById('messages').appendChild(div);
        }
        if (data.kind === 'stage') document.getElementById('stage-bar').textContent = data.stage;
      });
    </script>`;
  }
}
