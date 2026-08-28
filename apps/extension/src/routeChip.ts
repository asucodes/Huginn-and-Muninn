import * as vscode from 'vscode';

/**
 * Route chip: the always-visible routing transparency surface (PS req 3b).
 * Shows kernel health + which model/provider handled the last LLM call, live.
 */
export class RouteChip {
  private item: vscode.StatusBarItem;
  private kernelUrl: string;
  private timer: NodeJS.Timeout;
  private lastSpanId = 0;

  constructor(ctx: vscode.ExtensionContext, kernelUrl: string) {
    this.kernelUrl = kernelUrl;
    this.item = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 100);
    this.item.text = '$(circle-filled) H&M: connecting…';
    this.item.tooltip = 'Huginn & Muninn kernel connection';
    this.item.command = 'taknee.openTraces';
    this.item.show();
    ctx.subscriptions.push(this.item);
    this.timer = setInterval(() => this.poll(), 4000);
    ctx.subscriptions.push({ dispose: () => clearInterval(this.timer) });
  }

  private async poll() {
    try {
      const health = await fetch(`${this.kernelUrl}/health`).then(r => r.json());
      if (!health.ok) throw new Error('unhealthy');
      const tasksRes = await fetch(`${this.kernelUrl}/tasks`);
      const tasks = tasksRes.ok ? await tasksRes.json() : [];
      if (!Array.isArray(tasks)) {
        this.setOk('idle', 'Kernel healthy, no workspace yet');
        return;
      }
      const active = tasks.find((t: any) => t.status === 'running' || t.status === 'awaiting_approval');
      if (!active) {
        this.setOk('idle', 'Kernel healthy, no active task');
        return;
      }
      const spans = await fetch(`${this.kernelUrl}/tasks/${active.id}/spans`).then(r => r.json());
      const llm = [...spans].reverse().find((s: any) => s.kind === 'llm' && s.id > this.lastSpanId);
      if (llm) {
        this.lastSpanId = llm.id;
        const model = (llm.model || '?').split('/').pop();
        this.setOk(
          `${active.stage}: ${model} @ ${llm.provider}`,
          llm.route_reason || 'routing decision',
        );
      } else {
        this.setOk(active.stage, `task ${active.id}: ${active.status}`);
      }
    } catch {
      this.item.text = '$(debug-disconnect) H&M: kernel offline';
      this.item.tooltip = 'Run `uv run taknee` in a terminal, then reload';
      this.item.backgroundColor = new vscode.ThemeColor('statusBarItem.warningBackground');
    }
  }

  private setOk(text: string, tooltip: string) {
    this.item.text = `$(sparkle) H&M: ${text}`;
    this.item.tooltip = new vscode.MarkdownString(tooltip);
    this.item.backgroundColor = undefined;
  }
}
