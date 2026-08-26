"""Small capability registry.

Plugins are intentionally boring: a plugin contributes named tools and a
short description. The kernel owns policy, approvals, workspace jail and
execution; plugins only provide capabilities.
"""
from dataclasses import dataclass
from typing import Any, Callable

@dataclass(frozen=True)
class Plugin:
    name: str
    description: str
    tools: tuple[str, ...]

_PLUGINS = {
    "web": Plugin("web", "Search and fetch public web pages", ("web_search", "web_fetch")),
    "workspace": Plugin("workspace", "Inspect and modify the open project", ("read_file", "list_files", "search_code", "retrieve", "write_file")),
    "git": Plugin("git", "Review and manage project history", ("git_diff", "git_log", "git_commit", "git_checkout")),
    "terminal": Plugin("terminal", "Run approved project commands", ("run_terminal",)),
}

def list_plugins() -> list[dict[str, Any]]:
    return [{"name": p.name, "description": p.description, "tools": list(p.tools)} for p in _PLUGINS.values()]

def get(name: str) -> Plugin | None:
    return _PLUGINS.get(name)
