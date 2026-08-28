"""Orchestrator — deterministic state machine (Agentless-style) with caps.

Pipeline: retrieve -> [research] -> localize -> patch -> approval -> apply
          -> verify -> (fail) diagnose -> patch ... -> done
No free-form ReAct loop: tools are available at named stages only, which is
what keeps small models on the rails (docs/decisions.md D2). Research-write
tasks get a harness-owned search+fetch stage and a read-back grader; the
model still only fills JSON / SEARCH/REPLACE artifacts. File existence is
not success.

Every stage transition, LLM call, approval and cap hit is a span or event in
the store — the Traces view and resume logic read exactly this data. The state
machine parks (status=awaiting_approval) whenever a human decision is needed;
resume() continues from the recorded stage, so multi-session resume (req 6)
falls out of the same mechanism.
"""

from __future__ import annotations

import json
import re
import subprocess
import time
from collections import Counter
from pathlib import Path
from typing import Any, Callable

from . import agents_md, catalog, compaction, patches, providers, research, retrieval, tools
from .compaction import ContextItem
from .memory import MemoryManager
from .router import Router
from .store import Store

MAX_REPAIR_ITERATIONS = 3
MAX_TOOL_ROUNDS = 4
TARGET_WORKING_CONTEXT = 24_000  # tokens — small models rot beyond this (docs/02 §4.3)

RESEARCH_PATCH_PROMPT = """You are the patch stage of a research-write agent. \
Produce ONE new-file SEARCH/REPLACE block for the requested file.

```{filename}
<<<<<<< SEARCH
=======
<full file>
>>>>>>> REPLACE
```

Rules:
- Write only from the pinned web_search / web_fetch observations and the pinned ISO retrieval date.
- If a number, system name, or URL is not in those observations, write UNKNOWN. Never invent.
- Never use placeholders like System A, System B, or System C.
- List only URLs that appear in the fetched observations.
- Do not copy the user's instruction outline as the file body.
- The retrieval date is the pinned ISO date, not a date you remember.
- SEARCH must be empty (new file). The fence path must be '{filename}'."""

PATCH_PROMPT = """You are the patch stage of a coding agent. Produce edits as \
SEARCH/REPLACE blocks, one per change, using this exact format inside fences:

```<relative/file/path>
<<<<<<< SEARCH
exact existing lines to find (copy them exactly)
=======
replacement lines
>>>>>>> REPLACE
```

Rules:
- SEARCH must match existing file content exactly (including indentation).
- To create a new file, use an empty SEARCH section and put the full file in REPLACE.
- Create parent directories implicitly by naming the desired relative file path.
- One block per logical change; keep blocks small.
- Do not rewrite whole files unless the file is under 40 lines.
- No explanation outside the fences."""

LOCALIZE_PROMPT = (
    "You are the localization stage of a coding agent. Given the task and a "
    "repository map, list the exact files (and symbols, if known) that must be "
    "read or changed. Reply ONLY with JSON: "
    '{"files": [{"path": "...", "why": "...", "symbols": ["..."]}]}'
)

DIAGNOSE_PROMPT = (
    "You are the diagnose stage of a coding agent. The last patch was empty "
    "or verification failed. Using the pinned fail log, last diff, and task, "
    "diagnose the failure in 3-6 bullets and say what to change next. "
    "Do not emit SEARCH/REPLACE blocks. Reply with plain text."
)


class CapHit(Exception):
    """A governor fired: stop the task, persist state, never run forever."""


class Parked(Exception):
    """A human decision is required; task state is durable until resolved."""


class Orchestrator:
    def __init__(
        self,
        store: Store,
        router: Router,
        workspace: str,
        *,
        chat_fn: Callable[..., providers.ChatResult] = providers.chat,
        auto_approve: bool = False,
    ):
        self.store = store
        self.router = router
        self.workspace = str(Path(workspace).resolve())
        self.chat_fn = chat_fn
        self.auto_approve = auto_approve
        self.memory = MemoryManager(Path(self.workspace))
        self.rules = agents_md.load_for_workspace(Path(self.workspace))
        self.index: retrieval.Index | None = None
        self._fingerprints: Counter[str] = Counter()
        self._steps = 0
        self._llm_calls = 0
        self._current_task: str = ""
        self._context_items: list[ContextItem] = []
        self._decisions: list[str] = []
        self._pending_blocks: list[patches.PatchBlock] = []
        self._research = False
        self._search_count = 0
        self._fetch_count = 0
        self._fetched_urls: list[str] = []
        self._fetched_text = ""

    # ------------------------------------------------------------------ run

    def run(self, task_id: str, *, start_stage: str = "retrieve") -> str:
        """Run until done/stopped/parked. Returns final status."""
        task = self.store.get_task(task_id)
        if task is None:
            raise KeyError(task_id)
        caps = self._caps()
        self._current_task = task_id
        self._research = research.is_research_write(task["prompt"])
        self._restore_research_trace(task_id)
        self.store.update_task(task_id, status="running", stage=start_stage)

        stage = start_stage
        iteration = 0
        empty_patches = 0

        try:
            while stage not in ("done", "stopped"):
                self.store.update_task(task_id, status="running", stage=stage)
                self._check_caps(task_id, caps)
                self._steps += 1

                if stage == "retrieve":
                    self._stage_retrieve(task_id, task["prompt"])
                    stage = "research" if self._research else "localize"

                elif stage == "research":
                    self._stage_research(task_id, task["prompt"])
                    stage = "localize"

                elif stage == "localize":
                    self._stage_localize(task_id, task["prompt"])
                    stage = "patch"

                elif stage == "patch":
                    blocks = self._stage_patch(task_id, task["prompt"], iteration)
                    if not blocks:
                        empty_patches += 1
                        if empty_patches >= caps.get("empty_patch_limit", 3):
                            self._stop(task_id, f"empty patch x{empty_patches}")
                            return "stopped"
                        stage = "diagnose" if iteration else "localize"
                    else:
                        self._pending_blocks = blocks
                        stage = "approval"

                elif stage == "approval":
                    self._stage_approval(task_id, self._pending_blocks)  # may raise Parked
                    stage = "apply"

                elif stage == "apply":
                    self._stage_apply(task_id, self._pending_blocks)
                    stage = "verify"

                elif stage == "verify":
                    ok, _log = self._stage_verify(task_id)  # may raise Parked
                    if ok:
                        stage = "done"
                    else:
                        iteration += 1
                        if iteration > MAX_REPAIR_ITERATIONS:
                            self._stop(
                                task_id,
                                f"verify failed after {MAX_REPAIR_ITERATIONS} repair attempts",
                            )
                            return "stopped"
                        stage = "diagnose"

                elif stage == "diagnose":
                    self._stage_diagnose(task_id, task["prompt"])
                    stage = "patch"

                else:
                    raise RuntimeError(f"unknown stage {stage}")

        except Parked:
            return "awaiting_approval"
        except CapHit as e:
            self._stop(task_id, str(e))
            return "stopped"

        self.store.update_task(task_id, status="done", stage="done")
        self.store.add_event(task_id, "status", {"status": "done"})
        changed = sorted({b.file for b in self._pending_blocks})
        summary = "The ravens have returned."
        if changed:
            summary += " Changed: " + ", ".join(changed) + "."
        summary += " Verification passed." if self.rules.test_cmd else " No project test command was configured, so only patch application was verified."
        self.store.add_message(task_id, "assistant", summary)
        return "done"

    def resume(self, task_id: str, approval_id: int, decision: str, accepted_ids: list[int]) -> str:
        """Continue a parked task after the user resolved an approval."""
        approval = self.store.get_approval(approval_id)
        if approval is None or approval["task_id"] != task_id:
            raise KeyError(approval_id)
        task = self.store.get_task(task_id)
        parked_stage = task["stage"] if task else "apply"

        if approval["kind"] == "patch":
            payload = approval.get("payload") or []
            blocks = [patches.PatchBlock(p["file"], p["search"], p["replace"]) for p in payload]
            if decision == "rejected":
                self.store.resolve_approval(
                    approval_id, decision, rejected=[b.fingerprint for b in blocks]
                )
                self._stop(task_id, "all hunks rejected by user")
                return "stopped"
            # Accept All from the UI sends decision=accepted with an empty id list
            if decision == "accepted" and not accepted_ids:
                accepted_ids = list(range(len(blocks)))
            accepted, rejected = patches.select_blocks(blocks, accepted_ids)
            self.store.resolve_approval(approval_id, decision, rejected=[b.fingerprint for b in rejected])
            if not accepted:
                self._stop(task_id, "all hunks rejected by user")
                return "stopped"
            self._pending_blocks = accepted
            next_stage = "apply"
        else:  # command approval (verify)
            self.store.resolve_approval(approval_id, decision)
            if decision != "accepted":
                self.store.update_task(task_id, status="done", stage="done")
                self.store.add_event(task_id, "note", {"verify": "skipped by user"})
                return "done"
            # user approved the command — run it now and continue
            span = self.store.add_span(task_id, "stage", "verify")
            cmd = (approval.get("payload") or {}).get("command", "")
            ok, log = self._run_verify(task_id, cmd, span)
            if ok:
                self.store.update_task(task_id, status="done", stage="done")
                self.store.add_event(task_id, "status", {"status": "done"})
                return "done"
            self.store.add_event(task_id, "note", {"verify_ok": False, "restarting": True})
            return self.run(task_id, start_stage="diagnose")

        # reset the clock base so a multi-day gap doesn't insta-trip the time cap
        # TODO: track active vs wall-clock seconds properly (docs/03 §7)
        self.store.update_task(task_id, created_at=time.time())
        self.store.add_event(task_id, "approval", {"decision": decision, "accepted": accepted_ids})
        return self.run(task_id, start_stage=next_stage)

    # --------------------------------------------------------------- stages

    def _stage_retrieve(self, task_id: str, prompt: str) -> None:
        span = self.store.add_span(task_id, "stage", "retrieve")
        if self.index is None:
            self.index = retrieval.Index(Path(self.workspace))
            if not self.index.load() or self.index.stale_files():
                self.index.build()
                self.index.save()
        hits = self.index.search(prompt, k=8)
        for chunk, _score, _reason in hits:
            self._remember(f"chunk:{chunk.header()}", chunk.text)
        self._remember("repo_map", self.index.repo_map(token_budget=900), pinned=True)
        digest = self.rules.pinned_digest() or self.memory.export_digest()
        if digest:
            self._remember("AGENTS.md", digest, pinned=True)
        self._remember("task_prompt", prompt, pinned=True)
        if self._research:
            self._remember(
                "retrieval_date",
                research.iso_today(),
                pinned=True,
            )
            self._remember(
                "research_contract",
                "Write only from web_search/web_fetch observations. "
                "Unverified claims must be UNKNOWN. File existence is not success. "
                f"ISO retrieval date: {research.iso_today()}.",
                pinned=True,
            )
        elif any(term in prompt.lower() for term in ("web", "search online", "scrape", "website", "internet")):
            query = research.search_queries(prompt)[0]
            web_span = self.store.add_span(task_id, "tool", "web_search", parent_id=span)
            result = tools.execute("web_search", {"query": query}, workspace=self.workspace)
            self._remember("web_research", result[:6000], pinned=True)
            self.store.end_span(web_span, {"query": query, "result": result[:1500]})
        self.store.end_span(span, {"hits": len(hits)})

    def _stage_research(self, task_id: str, prompt: str) -> None:
        """Harness-owned search+fetch. The model does not pick these tools."""
        span = self.store.add_span(task_id, "stage", "research")
        today = research.iso_today()
        self._remember("retrieval_date", today, pinned=True)

        blobs: list[str] = []
        found: list[str] = []
        for query in research.search_queries(prompt):
            web_span = self.store.add_span(task_id, "tool", "web_search", parent_id=span)
            result = tools.execute("web_search", {"query": query}, workspace=self.workspace)
            self._search_count += 1
            blobs.append(f"query: {query}\n{result}")
            found.extend(research.urls_from_text(result))
            self.store.end_span(web_span, {"query": query, "result": result[:1500]})
        self._remember("web_search", "\n\n".join(blobs)[:6000], pinned=True)

        urls = research.select_fetch_urls(prompt, found)
        pages: list[str] = []
        for url in urls[:MAX_TOOL_ROUNDS]:
            fetch_span = self.store.add_span(task_id, "tool", "web_fetch", parent_id=span)
            body = tools.execute("web_fetch", {"url": url}, workspace=self.workspace)
            self._fetch_count += 1
            self._fetched_urls.append(url)
            pages.append(f"URL: {url}\n{body[:4000]}")
            self.store.end_span(fetch_span, {"url": url, "result": body[:1500]})
        self._fetched_text = "\n\n".join(pages)
        self._remember("web_fetch", self._fetched_text[:12_000], pinned=True)
        self._decisions.append(
            f"research: {self._search_count} searches, {self._fetch_count} fetches"
        )
        self.store.end_span(
            span,
            {
                "searches": self._search_count,
                "fetches": self._fetch_count,
                "urls": list(self._fetched_urls),
            },
        )

    def _restore_research_trace(self, task_id: str) -> None:
        """Rebuild search/fetch counts from durable spans (resume / kernel restart)."""
        if not self._research:
            return
        searches = fetches = 0
        urls: list[str] = []
        texts: list[str] = []
        for s in self.store.spans_for_task(task_id):
            if s.get("kind") != "tool":
                continue
            out = s.get("output") if isinstance(s.get("output"), dict) else {}
            if s.get("name") == "web_search":
                searches += 1
            elif s.get("name") == "web_fetch":
                fetches += 1
                url = str(out.get("url") or "")
                if url:
                    urls.append(url)
                texts.append(str(out.get("result") or ""))
        if searches:
            self._search_count = searches
        if fetches:
            self._fetch_count = fetches
            self._fetched_urls = urls
            self._fetched_text = "\n".join(texts)

    def _verify_research(self, task_id: str, span: int) -> tuple[bool, str]:
        prompt = (self.store.get_task(task_id) or {}).get("prompt", "")
        wanted = research.requested_files(prompt)
        path = ""
        if wanted:
            path = wanted[0]
        elif self._pending_blocks:
            path = self._pending_blocks[0].file
        body = self._read_jailed(path) if path else None
        if body is None and self._pending_blocks:
            path = self._pending_blocks[0].file
            body = self._read_jailed(path)
        grade = research.grade_research_write(
            prompt=prompt,
            path=path or "",
            body=body or "",
            search_count=self._search_count,
            fetch_count=self._fetch_count,
            fetched_urls=self._fetched_urls,
            fetched_text=self._fetched_text,
            today=research.iso_today(),
        )
        log = "research read-back ok" if grade.ok else "; ".join(grade.reasons)
        self._remember("last_fail_log", log[:3000], pinned=True)
        self.store.end_span(
            span,
            {
                "ok": grade.ok,
                "path": path,
                "reasons": grade.reasons,
                "searches": self._search_count,
                "fetches": self._fetch_count,
            },
        )
        self.store.add_event(task_id, "note", {"verify_ok": grade.ok, "research": True})
        return grade.ok, log

    def _stage_localize(self, task_id: str, prompt: str) -> None:
        span = self.store.add_span(task_id, "stage", "localize")
        result, _route = self._llm(
            task_id, span, "localize", "primary",
            [
                {"role": "system", "content": LOCALIZE_PROMPT},
                {"role": "user", "content": self._context(prompt)},
            ],
        )
        files = self._extract_json(result.content, "files", [])
        if not isinstance(files, list):
            files = []
        files = files[:8]  # small models dump the whole repo otherwise
        self._remember("localization", json.dumps(files)[:2000], pinned=True)
        for f in files:
            path = str(f.get("path", "")) if isinstance(f, dict) else ""
            content = self._read_jailed(path) if path else None
            if content is not None:
                self._remember(f"file:{path}", content[:4000])
        self._decisions.append(f"localized to {len(files)} files")
        self.store.end_span(span, {"files": files})

    def _stage_patch(self, task_id: str, prompt: str, iteration: int) -> list[patches.PatchBlock]:
        span = self.store.add_span(task_id, "stage", "patch")
        wanted = research.requested_files(prompt) if self._research else []
        default_file = wanted[0] if wanted else None
        target_fn = default_file or "output.md"
        if self._research:
            system = RESEARCH_PATCH_PROMPT.replace("{filename}", target_fn)
            system += f"\nRequested target file: {target_fn}"
        else:
            system = PATCH_PROMPT
        result, _route = self._llm(
            task_id, span, "patch", "primary",
            [
                {"role": "system", "content": system},
                {"role": "user", "content": self._context(prompt)},
            ],
            iteration=iteration,
        )
        blocks = patches.parse(result.content, default_file=default_file)
        fp = patches.hash_text(result.content)
        self._fingerprints[f"patch:{fp}"] += 1
        if self._fingerprints[f"patch:{fp}"] >= self._caps().get("fingerprint_limit", 3):
            raise CapHit("patch stage repeated identical output (stuck)")
        self.store.end_span(span, {"blocks": len(blocks), "iteration": iteration})
        return blocks

    def _stage_approval(self, task_id: str, blocks: list[patches.PatchBlock]) -> None:
        payload = patches.blocks_to_review_payload(blocks)
        if self.auto_approve:
            aid = self.store.add_approval(task_id, "patch", payload)
            self.store.resolve_approval(aid, "accepted")
            return
        aid = self.store.add_approval(task_id, "patch", payload)
        self.store.update_task(task_id, status="awaiting_approval", stage="approval")
        self.store.add_event(task_id, "approval", {"approval_id": aid, "hunks": len(blocks)})
        raise Parked()

    def _stage_apply(self, task_id: str, blocks: list[patches.PatchBlock]) -> None:
        span = self.store.add_span(task_id, "stage", "apply")
        originals: dict[str, str] = {}
        report = patches.apply_blocks(
            blocks,
            read_file=self._read_jailed,
            write_file=self._write_jailed,
            originals=originals,
        )
        new_state = {b.file: (self._read_jailed(b.file) or "") for b in blocks}
        diff = report.diff(new_state, originals)
        self._remember("last_diff", diff[:6000], pinned=True)
        self.store.end_span(
            span,
            {"applied": len(report.applied), "failed": [f"{b.file}: {why}" for b, why in report.failed]},
        )
        if not report.applied:
            raise CapHit("patch produced no applicable file changes")

        # A model must not satisfy a create/build request by editing an
        # unrelated existing document. This catches the common failure mode
        # where a truncated response rewrites README.md and is reported done.
        prompt = (self.store.get_task(task_id) or {}).get("prompt", "").lower()
        if any(word in prompt for word in ("create", "build", "implement", "make")):
            requested = set()
            for token in prompt.replace("\\", "/").split():
                token = token.strip(".,:;()[]\"")
                if "/" in token or token.endswith((".py", ".js", ".ts", ".md")):
                    requested.add(token)
            if "solver" in prompt and not any("solver" in b.file.lower() for b in report.applied):
                raise CapHit("task requested a solver but patch created no solver file")
            if requested and not any(any(token in b.file.lower() for token in requested) for b in report.applied):
                raise CapHit("patch changed files unrelated to the requested deliverable")
            # "create a python tutorial" must produce a new artifact, not a
            # stray edit to whatever file retrieval surfaced (observed: the
            # model docstring-ing an unrelated password checker).
            new_files = [f for f, base in originals.items() if base == ""]
            if (
                not requested
                and not new_files
                and re.search(r"\b(create|build|make|generate)\b", prompt)
                and re.search(r"\b(a|an|new)\b", prompt)
            ):
                raise CapHit(
                    "task asked to create something new, but the patch only edited "
                    "existing files — no new file was created"
                )

    def _stage_diagnose(self, task_id: str, prompt: str) -> None:
        span = self.store.add_span(task_id, "stage", "diagnose")
        result, _route = self._llm(
            task_id, span, "diagnose", "utility",
            [
                {"role": "system", "content": DIAGNOSE_PROMPT},
                {"role": "user", "content": self._context(prompt)},
            ],
        )
        self._remember("diagnosis", result.content[:2000], pinned=True)
        self._decisions.append("diagnosed after failure")
        self.store.end_span(span, {"diagnosis": result.content[:800]})

    def _stage_verify(self, task_id: str) -> tuple[bool, str]:
        span = self.store.add_span(task_id, "stage", "verify")
        if self._research:
            return self._verify_research(task_id, span)
        cmd = self.rules.test_cmd
        if not cmd:
            self.store.end_span(span, {"skipped": "no test command in AGENTS.md"})
            return True, "(no test command)"
        if not self.auto_approve:
            aid = self.store.add_approval(task_id, "command", {"command": cmd})
            self.store.update_task(task_id, status="awaiting_approval", stage="verify")
            self.store.add_event(task_id, "approval", {"approval_id": aid, "command": cmd})
            raise Parked()
        return self._run_verify(task_id, cmd, span)

    def _run_verify(self, task_id: str, cmd: str, span: int | None = None) -> tuple[bool, str]:
        try:
            r = subprocess.run(
                cmd, shell=True, capture_output=True, text=True,
                cwd=self.workspace, timeout=300,
            )
            log = (r.stdout or "") + "\n" + (r.stderr or "")
            ok = r.returncode == 0
            if ok:
                self.memory.record_test_result(cmd, True)
        except subprocess.TimeoutExpired:
            log, ok = "test command timed out (300s)", False
        self._remember("last_fail_log", log[-3000:], pinned=True)
        if span is not None:
            self.store.end_span(span, {"ok": ok, "log_tail": log[-500:]})
        self.store.add_event(task_id, "note", {"verify_ok": ok})
        return ok, log

    # ------------------------------------------------------------------ llm

    def _chat_with_readonly_tools(self, task_id: str, parent_span: int, route, messages):
        """Call the provider for a deterministic pipeline stage.

        Retrieval and file reads already happen in named stages. Advertising
        native tools here caused some models to return only tool calls, which
        this stage pipeline does not consume, leaving an empty patch response.
        """
        return self.chat_fn(
            route.provider, route.model, messages, temperature=0.2, timeout=120
        )

    def _llm(
        self,
        task_id: str,
        parent_span: int,
        stage: str,
        tier: str,
        messages: list[dict],
        iteration: int = 0,
    ):
        est = compaction.estimate_tokens(
            "\n".join(str(m.get("content", "")) for m in messages)
        )
        last_err = "no healthy provider/model — add API keys in Settings"
        for attempt in range(4):
            route = self.router.pick(tier, est_tokens=est, iteration=iteration)
            if route is None and tier != "primary":
                route = self.router.pick("primary", est_tokens=est, iteration=iteration)
            if route is None:
                raise CapHit(last_err)

            span = self.store.add_span(
                task_id, "llm", stage, parent_id=parent_span,
                model=route.model, provider=route.provider,
                route_reason=(
                    route.reason if attempt == 0 else f"fallback #{attempt}: {route.reason}"
                ),
            )
            try:
                result = self._chat_with_readonly_tools(task_id, parent_span, route, messages)
            except providers.RateLimited as e:
                self.router.record_failure(route.provider, e.retry_after)
                self.store.end_span(span, {"error": "rate_limited"})
                self.store.add_event(task_id, "route", {"fallback_from": route.provider})
                last_err = str(e)
                continue
            except providers.ProviderError as e:
                error_text = str(e).lower()
                if e.status in (401, 403) or (
                    e.status == 0
                    and not any(marker in error_text for marker in ("deprecated", "end of life", "model"))
                ):
                    # A refused Ollama connection is an unavailable provider,
                    # not two separately missing local models.
                    self.router.record_failure(route.provider, retry_after=300.0)
                else:
                    self.router.record_model_skip(route.provider, route.model)
                self.store.end_span(span, {"error": str(e)[:400]})
                self.store.add_event(
                    task_id, "route", {"fallback_from": route.provider, "model": route.model}
                )
                last_err = str(e)
                continue

            self.router.record_success(route.provider)
            self.store.end_span(
                span, {"content": result.content[:1500]},
                tokens_in=result.tokens_in, tokens_out=result.tokens_out, usd=result.usd,
            )
            self.store.add_usage(task_id, result.tokens_in, result.tokens_out, result.usd)
            return result, route

        raise CapHit(last_err)

    # -------------------------------------------------------------- context

    def _remember(self, key: str, content: str, pinned: bool = False) -> None:
        self._context_items = [i for i in self._context_items if i.key != key]
        self._context_items.append(ContextItem(key, content, pinned=pinned))

    def _context(self, prompt: str) -> str:
        items = list(self._context_items)
        items.append(compaction.decision_ledger(self._decisions))
        text, stats = compaction.assemble(items, TARGET_WORKING_CONTEXT)
        if stats["items_compacted"]:
            self.store.add_event(self._current_task, "compaction", stats)
        return text

    # ----------------------------------------------------------------- caps

    def _caps(self) -> dict:
        from . import settings as settings_mod
        return settings_mod.load().get("caps", {})

    def _check_caps(self, task_id: str, caps: dict) -> None:
        task = self.store.get_task(task_id)
        elapsed = time.time() - task["created_at"]
        if elapsed > caps.get("max_seconds", 2400):
            raise CapHit(f"time cap {caps.get('max_seconds')}s exceeded")
        if task["usd"] > caps.get("max_usd", 0.40):
            raise CapHit(f"cost cap ${caps.get('max_usd')} exceeded")
        if self._steps > caps.get("max_steps", 120):
            raise CapHit(f"step cap {caps.get('max_steps')} exceeded")

    def _stop(self, task_id: str, reason: str) -> None:
        self.store.update_task(task_id, status="stopped", error=reason)
        self.store.add_event(task_id, "cap", {"reason": reason})
        self.store.add_message(task_id, "assistant", f"The raven did not return: {reason}")

    # ------------------------------------------------------------------- fs

    def _read_jailed(self, rel: str) -> str | None:
        try:
            root = Path(self.workspace).resolve()
            p = (root / rel).resolve()
            p.relative_to(root)
            return p.read_text(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            return None

    def _write_jailed(self, rel: str, content: str) -> None:
        root = Path(self.workspace).resolve()
        p = (root / rel).resolve()
        p.relative_to(root)  # ValueError escapes: caller records a failed block
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")

    @staticmethod
    def _extract_json(text: str, key: str, default: Any) -> Any:
        try:
            start = text.index("{")
            end = text.rindex("}") + 1
            return json.loads(text[start:end]).get(key, default)
        except (ValueError, json.JSONDecodeError):
            return default
