import * as vscode from 'vscode';
import { ChatPanel } from './chat';
import { TracesPanel } from './traces';
import { ReviewPanel } from './review';
import { SettingsPanel } from './settings';
import { RouteChip } from './routeChip';

const KERNEL_URL = 'http://127.0.0.1:47821';

export function activate(ctx: vscode.ExtensionContext) {
	const chat = new ChatPanel(ctx, KERNEL_URL);
	const traces = new TracesPanel(ctx, KERNEL_URL);
	const review = new ReviewPanel(ctx, KERNEL_URL);
	const settings = new SettingsPanel(ctx, KERNEL_URL);
	new RouteChip(ctx, KERNEL_URL);

	const retain = { webviewOptions: { retainContextWhenHidden: true } };
	ctx.subscriptions.push(
		vscode.window.registerWebviewViewProvider(ChatPanel.viewType, chat, retain),
		vscode.window.registerWebviewViewProvider(TracesPanel.viewType, traces, retain),
		vscode.window.registerWebviewViewProvider(ReviewPanel.viewType, review, retain),
		vscode.window.registerWebviewViewProvider(SettingsPanel.viewType, settings),
		vscode.commands.registerCommand('taknee.openSettings', () =>
			vscode.commands.executeCommand('taknee.settings.focus'),
		),
		vscode.commands.registerCommand('taknee.newTask', () =>
			vscode.commands.executeCommand('taknee.chat.focus'),
		),
		vscode.commands.registerCommand('taknee.openTraces', () =>
			vscode.commands.executeCommand('taknee.traces.focus'),
		),
	);

	const syncWorkspace = () => {
		const folder = vscode.workspace.workspaceFolders?.[0];
		if (!folder) return;
		fetch(`${KERNEL_URL}/workspace`, {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ path: folder.uri.fsPath }),
		}).catch(() => {});
	};
	syncWorkspace();
	const timer = setInterval(syncWorkspace, 4000);
	ctx.subscriptions.push({ dispose: () => clearInterval(timer) });
	ctx.subscriptions.push(vscode.workspace.onDidChangeWorkspaceFolders(() => syncWorkspace()));

	void vscode.commands.executeCommand('workbench.view.extension.taknee').then(() =>
		vscode.commands.executeCommand('taknee.chat.focus'),
	);
	void vscode.window.showInformationMessage(
		'Huginn & Muninn is in the left activity bar (diamond icon). Kernel console: http://127.0.0.1:47821/',
	);
}

export function deactivate() {}
