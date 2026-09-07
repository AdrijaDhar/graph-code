import * as vscode from "vscode";
import { spawn } from "child_process";

let statusBarItem: vscode.StatusBarItem;

function getCommand(): string {
  return vscode.workspace.getConfiguration("graphcode").get<string>("command") || "graphcode";
}

function getWorkspaceRoot(): string | undefined {
  return vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
}

/** Shells out to `graphcode <args>`, parsing stdout as JSON. Stateless per call by
 * design (see cli.py's own comment on the `query` subcommand) — the graph persists
 * to a RocksDB snapshot on disk and gets rehydrated by the *next* invocation's own
 * IndexService, so there's no long-lived daemon process for this extension to manage
 * or leak. Trades a little per-query latency (embedding model + snapshot load) for
 * not having to think about process lifecycle at all. */
function runGraphcode(args: string[], cwd: string): Promise<any> {
  return new Promise((resolve, reject) => {
    const cmd = getCommand();
    const proc = spawn(cmd, args, { cwd });
    let stdout = "";
    let stderr = "";
    proc.stdout.on("data", (d) => (stdout += d.toString()));
    proc.stderr.on("data", (d) => (stderr += d.toString()));
    proc.on("error", (err: NodeJS.ErrnoException) => {
      if (err.code === "ENOENT") {
        reject(
          new Error(
            `Could not find "${cmd}" on PATH. Install it with "pip install -e ." from the ` +
              `graph-code repo (or set the graphcode.command setting to its full path).`
          )
        );
      } else {
        reject(err);
      }
    });
    proc.on("close", (code) => {
      if (code !== 0) {
        reject(new Error(stderr.trim() || `graphcode exited with code ${code}`));
        return;
      }
      try {
        resolve(JSON.parse(stdout));
      } catch {
        reject(new Error(`Could not parse graphcode output as JSON:\n${stdout}`));
      }
    });
  });
}

async function openAtLine(root: string, relPath: string, startLine?: number) {
  const uri = vscode.Uri.file(`${root}/${relPath}`);
  const doc = await vscode.workspace.openTextDocument(uri);
  const line = Math.max((startLine || 1) - 1, 0);
  await vscode.window.showTextDocument(doc, {
    selection: new vscode.Range(line, 0, line, 0),
  });
}

async function indexWorkspace() {
  const root = getWorkspaceRoot();
  if (!root) {
    vscode.window.showWarningMessage("Graph-Code: open a folder first.");
    return;
  }
  await vscode.window.withProgress(
    { location: vscode.ProgressLocation.Notification, title: "Graph-Code: indexing workspace..." },
    async () => {
      try {
        const result = await runGraphcode(["index", root], root);
        const counts = result.counts || {};
        statusBarItem.text = `$(graph) graph-code: ${counts.Function ?? "?"} fn / ${counts.edges ?? "?"} edges`;
        statusBarItem.tooltip = `Indexed ${result.files ?? "?"} files at ${result.indexed_at ?? ""}`;
        vscode.window.showInformationMessage(
          `Graph-Code: indexed ${result.files ?? "?"} files, ${counts.Function ?? "?"} functions.`
        );
      } catch (err: any) {
        vscode.window.showErrorMessage(`Graph-Code: ${err.message}`);
      }
    }
  );
}

interface NodePickItem extends vscode.QuickPickItem {
  node: any;
}

function nodeQuickPickItem(n: any): NodePickItem {
  const label = n.qualified_name || n.path || n.id;
  const details = [n.via ? `via ${n.via}` : null, n.hop != null ? `hop ${n.hop}` : null].filter(Boolean).join(" · ");
  return { label, description: n.path, detail: details, node: n };
}

async function blastRadius(symbol: string) {
  const root = getWorkspaceRoot();
  if (!root) return;
  try {
    const result = await runGraphcode(["query", "blast-radius", symbol, "--direction", "upstream"], root);
    if (result.error) {
      vscode.window.showWarningMessage(`Graph-Code: "${symbol}" — ${result.error}`);
      return;
    }
    const nodes = (result.nodes || []).filter((n: any) => n.id !== result.origin?.id);
    if (nodes.length === 0) {
      vscode.window.showInformationMessage(`Graph-Code: nothing depends on "${symbol}".`);
      return;
    }
    const picked = await vscode.window.showQuickPick<NodePickItem>(nodes.map(nodeQuickPickItem), {
      title: `What depends on ${result.origin?.qualified_name || symbol}? (${nodes.length} found)`,
      matchOnDescription: true,
    });
    if (picked) await openAtLine(root, picked.node.path, picked.node.start_line);
  } catch (err: any) {
    vscode.window.showErrorMessage(`Graph-Code: ${err.message}`);
  }
}

async function blastRadiusAtCursor() {
  const editor = vscode.window.activeTextEditor;
  if (!editor) return;
  const range = editor.selection.isEmpty
    ? editor.document.getWordRangeAtPosition(editor.selection.active)
    : editor.selection;
  if (!range) {
    vscode.window.showWarningMessage("Graph-Code: place your cursor on a symbol first.");
    return;
  }
  const symbol = editor.document.getText(range).trim();
  if (!symbol) return;
  await blastRadius(symbol);
}

async function blastRadiusPrompt() {
  const symbol = await vscode.window.showInputBox({ prompt: "Symbol or file to check (e.g. a function name)" });
  if (symbol) await blastRadius(symbol);
}

async function semanticSearch() {
  const root = getWorkspaceRoot();
  if (!root) return;
  const text = await vscode.window.showInputBox({
    prompt: "Describe what you're looking for (natural language or code-like)",
  });
  if (!text) return;
  try {
    const result = await runGraphcode(["query", "semantic", text, "--k", "8"], root);
    const hits = result.hits || [];
    if (hits.length === 0) {
      vscode.window.showInformationMessage("Graph-Code: no matches.");
      return;
    }
    const items: NodePickItem[] = hits.map((h: any) => ({
      label: h.qualified_name || h.path,
      description: `${h.path} · score ${h.score?.toFixed(3)}`,
      node: h,
    }));
    const picked = await vscode.window.showQuickPick<NodePickItem>(items, { title: `Semantic search: "${text}"` });
    if (picked) await openAtLine(root, picked.node.path, picked.node.start_line);
  } catch (err: any) {
    vscode.window.showErrorMessage(`Graph-Code: ${err.message}`);
  }
}

async function shortestPath() {
  const root = getWorkspaceRoot();
  if (!root) return;
  const from = await vscode.window.showInputBox({ prompt: "From symbol/file" });
  if (!from) return;
  const to = await vscode.window.showInputBox({ prompt: "To symbol/file" });
  if (!to) return;
  try {
    const result = await runGraphcode(["query", "shortest-path", from, to], root);
    const path = result.path || [];
    if (path.length === 0) {
      vscode.window.showInformationMessage(
        `Graph-Code: ${result.error || "no structural path found"} between "${from}" and "${to}".`
      );
      return;
    }
    const items: NodePickItem[] = path.map((n: any) => ({
      label: n.qualified_name || n.path || n.id,
      description: n.via ? `→ ${n.via} →` : "(start)",
      node: n,
    }));
    const picked = await vscode.window.showQuickPick<NodePickItem>(items, {
      title: `Path: ${from} → ${to} (${path.length - 1} hop${path.length - 1 === 1 ? "" : "s"})`,
    });
    if (picked?.node.path) await openAtLine(root, picked.node.path, picked.node.start_line);
  } catch (err: any) {
    vscode.window.showErrorMessage(`Graph-Code: ${err.message}`);
  }
}

async function affectedTests(symbol: string) {
  const root = getWorkspaceRoot();
  if (!root) return;
  try {
    const result = await runGraphcode(["query", "affected-tests", symbol], root);
    if (result.error) {
      vscode.window.showWarningMessage(`Graph-Code: "${symbol}" — ${result.error}`);
      return;
    }
    const tests = result.tests || [];
    if (tests.length === 0) {
      vscode.window.showWarningMessage(
        `Graph-Code: no indexed tests call "${symbol}" (even transitively) — consider adding coverage.`
      );
      return;
    }
    const items: NodePickItem[] = tests.map((t: any) => ({
      label: t.qualified_name || t.name || t.id,
      description: `${t.path} · ${t.depth} call${t.depth === 1 ? "" : "s"} deep`,
      node: t,
    }));
    const picked = await vscode.window.showQuickPick<NodePickItem>(items, {
      title: `${tests.length} test(s) exercise ${result.origin?.qualified_name || symbol}`,
    });
    if (picked) await openAtLine(root, picked.node.path, picked.node.start_line);
  } catch (err: any) {
    vscode.window.showErrorMessage(`Graph-Code: ${err.message}`);
  }
}

async function affectedTestsAtCursor() {
  const editor = vscode.window.activeTextEditor;
  if (!editor) return;
  const range = editor.selection.isEmpty
    ? editor.document.getWordRangeAtPosition(editor.selection.active)
    : editor.selection;
  if (!range) {
    vscode.window.showWarningMessage("Graph-Code: place your cursor on a symbol first.");
    return;
  }
  const symbol = editor.document.getText(range).trim();
  if (symbol) await affectedTests(symbol);
}

async function affectedTestsPrompt() {
  const symbol = await vscode.window.showInputBox({ prompt: "Symbol or file to find tests for" });
  if (symbol) await affectedTests(symbol);
}

export function activate(context: vscode.ExtensionContext) {
  statusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 100);
  statusBarItem.text = "$(graph) graph-code: not indexed";
  statusBarItem.command = "graphcode.indexWorkspace";
  statusBarItem.tooltip = "Click to index this workspace";
  statusBarItem.show();

  context.subscriptions.push(
    statusBarItem,
    vscode.commands.registerCommand("graphcode.indexWorkspace", indexWorkspace),
    vscode.commands.registerCommand("graphcode.blastRadiusAtCursor", blastRadiusAtCursor),
    vscode.commands.registerCommand("graphcode.blastRadiusPrompt", blastRadiusPrompt),
    vscode.commands.registerCommand("graphcode.semanticSearch", semanticSearch),
    vscode.commands.registerCommand("graphcode.shortestPath", shortestPath),
    vscode.commands.registerCommand("graphcode.affectedTestsAtCursor", affectedTestsAtCursor),
    vscode.commands.registerCommand("graphcode.affectedTestsPrompt", affectedTestsPrompt)
  );
}

export function deactivate() {}
