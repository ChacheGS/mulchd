"""Supersede-graph logic for tier2: cycle detection, reference validation,
and classification-downgrade alerts.

Self-contained — depends only on things already independent of tier2.py
itself (project_cache, domains, records), so this has no circular import
with tier2.py re-exporting these names back for its own use.
"""

from enum import IntEnum
from pathlib import Path

from ..domains import mulch_dir
from ..records import read_domain_records
from .project_cache import get_archived_ids, get_project_records


async def _mark_superseded(records: list[dict], org_slug: str, project_slug: str) -> None:
    """Tag each record with incoming/outgoing supersede relationships and
    cycle membership.

    Scans all domains — not just the current result set — so cross-domain
    supersession and same-domain supersession where the superseder was not
    co-retrieved are both detected. Also scans archive/ so an outgoing
    reference to a now-deleted record can be labeled distinctly from a live
    one or a reference that never resolved to anything.

    Sets _superseder_domain when the superseder lives in a different domain
    than the superseded record (used to build cross-domain read hints).
    """
    if not records:
        return
    m_dir = mulch_dir(org_slug, project_slug)
    project_records = await get_project_records(m_dir)
    archived_ids = await get_archived_ids(m_dir)
    live_by_id = {r["id"]: r for r in project_records if r.get("id")}

    # {victim_id: (superseder_id, superseder_domain)}
    superseded_by: dict[str, tuple[str, str]] = {}
    for stored in project_records:
        sid = stored.get("id", "")
        for vid in stored.get("supersedes") or []:
            if sid:
                superseded_by[vid] = (sid, stored.get("_domain", ""))

    cycles = _find_cycles(project_records)

    for r in records:
        rid = r.get("id")

        if rid in cycles:
            r["_cycle_with"] = cycles[rid]
            continue

        if rid in superseded_by:
            superseder_id, superseder_domain = superseded_by[rid]
            r["_superseded"] = True
            r["_superseded_by"] = superseder_id
            if superseder_domain and superseder_domain != r.get("_domain", ""):
                r["_superseder_domain"] = superseder_domain
            if r.get("classification") == "foundational":
                r["_foundational_superseded"] = True

        outgoing = r.get("supersedes") or []
        if outgoing:
            display: list[str] = []
            displaced_foundational: list[str] = []
            for tid in outgoing:
                target = live_by_id.get(tid)
                if target is not None:
                    if target.get("classification") == "foundational":
                        # Shown via the dedicated "⚠ supersedes foundational" line
                        # below instead — listing it in the generic tag too would
                        # render the same id twice back-to-back.
                        displaced_foundational.append(tid)
                    else:
                        display.append(tid)
                elif tid in archived_ids:
                    display.append(f"{tid} (deleted)")
                else:
                    display.append(f"{tid} (missing)")
            r["_supersedes_display"] = display
            if displaced_foundational:
                r["_supersedes_foundational"] = displaced_foundational


async def _mark_related_to(records: list[dict], org_slug: str, project_slug: str) -> None:
    """Tag each record with incoming/outgoing relates_to links.

    Mirrors _mark_superseded's scan-the-whole-project approach, but
    relates_to is a plain, non-exclusive association rather than a
    hierarchical one — a target can be referenced by any number of other
    records (unlike _superseded_by, which keeps only the latest superseder),
    so incoming links are collected as a list, not a single winner.
    """
    if not records:
        return
    m_dir = mulch_dir(org_slug, project_slug)
    project_records = await get_project_records(m_dir)
    archived_ids = await get_archived_ids(m_dir)
    live_ids = {r["id"] for r in project_records if r.get("id")}

    related_by: dict[str, list[str]] = {}
    for stored in project_records:
        sid = stored.get("id", "")
        if not sid:
            continue
        for tid in stored.get("relates_to") or []:
            related_by.setdefault(tid, []).append(sid)

    for r in records:
        rid = r.get("id")
        if rid in related_by:
            r["_related_by"] = related_by[rid]

        outgoing = r.get("relates_to") or []
        if outgoing:
            display: list[str] = []
            for tid in outgoing:
                if tid in live_ids:
                    display.append(tid)
                elif tid in archived_ids:
                    display.append(f"{tid} (deleted)")
                else:
                    display.append(f"{tid} (missing)")
            r["_relates_to_display"] = display


async def _find_incoming_references(m_dir: Path, record_id: str) -> list[dict]:
    """Every other live record whose relates_to or supersedes points at record_id.

    Computed independently of `ml move`'s own incomingReferences — that scan
    (mulch 0.10.7's findIncomingReferences) skips the entire source-domain
    file, not just the moved record's own line, so it structurally misses
    same-domain references. mulchd already has the project-wide record set
    cached for _mark_related_to/_mark_superseded, so it's cheaper and more
    correct to answer this directly than to trust ml's result.
    """
    project_records = await get_project_records(m_dir)
    hits: list[dict] = []
    for r in project_records:
        rid = r.get("id")
        if not rid or rid == record_id:
            continue
        if record_id in (r.get("relates_to") or []):
            hits.append({"domain": r.get("_domain", ""), "id": rid, "field": "relates_to"})
        if record_id in (r.get("supersedes") or []):
            hits.append({"domain": r.get("_domain", ""), "id": rid, "field": "supersedes"})
    return hits


def _validate_references(
    live_ids: set[str],
    supersedes: list[str],
    relates_to: list[str],
    self_id: str | None = None,
) -> None:
    """Raise ValueError if any supersedes/relates_to ID doesn't resolve to a
    live record in live_ids, or references self_id. live_ids should come from
    get_project_records — archived and fabricated IDs are both simply absent
    from that set, so both are rejected the same way. Reports every problem
    across both fields in one error, not just the first one found."""
    errors: list[str] = []
    for field_name, ids in (("supersedes", supersedes), ("relates_to", relates_to)):
        self_refs = [i for i in ids if self_id is not None and i == self_id]
        missing = [i for i in ids if i != self_id and i not in live_ids]
        if self_refs:
            errors.append(
                f"{field_name} cannot reference the record's own id: {', '.join(self_refs)}"
            )
        if missing:
            errors.append(f"{field_name} references records that don't exist: {', '.join(missing)}")
    if errors:
        raise ValueError("\n".join(errors))


def _find_cycles(project_records: list[dict]) -> dict[str, list[str]]:
    """Tarjan's strongly-connected-components algorithm over the supersedes
    graph. Returns {record_id: [other ids in its cycle]} for every record
    whose component has more than one member (a genuine cycle) — records not
    part of any cycle are absent from the result entirely.

    Edges to an ID not present in project_records (e.g. an already-archived
    target, or a dangling legacy reference) are dropped before running the
    algorithm — a target that isn't a node in this graph can't complete a
    cycle back to anything.
    """
    ids_present = {r["id"] for r in project_records if r.get("id")}
    graph: dict[str, list[str]] = {}
    for r in project_records:
        rid = r.get("id")
        if not rid:
            continue
        graph[rid] = [t for t in (r.get("supersedes") or []) if t in ids_present]

    index_counter = 0
    stack: list[str] = []
    lowlink: dict[str, int] = {}
    index: dict[str, int] = {}
    on_stack: dict[str, bool] = {}
    sccs: list[list[str]] = []

    # Iterative Tarjan's — a recursive strongconnect() would hit Python's
    # default recursion limit (RecursionError) on a supersede chain of
    # roughly 1000+ records, turning every read of the domain into a crash.
    # This is the standard explicit-work-stack transformation: each stack
    # frame is (node, index of the next child edge to examine), so DFS
    # recursion becomes a while-loop over an explicit list instead of the
    # Python call stack.
    for start in graph:
        if start in index:
            continue
        work: list[tuple[str, int]] = [(start, 0)]
        index[start] = index_counter
        lowlink[start] = index_counter
        index_counter += 1
        stack.append(start)
        on_stack[start] = True

        while work:
            v, i = work[-1]
            children = graph.get(v, [])
            if i < len(children):
                w = children[i]
                work[-1] = (v, i + 1)
                if w not in index:
                    index[w] = index_counter
                    lowlink[w] = index_counter
                    index_counter += 1
                    stack.append(w)
                    on_stack[w] = True
                    work.append((w, 0))
                elif on_stack.get(w):
                    lowlink[v] = min(lowlink[v], index[w])
            else:
                work.pop()
                if work:
                    parent = work[-1][0]
                    lowlink[parent] = min(lowlink[parent], lowlink[v])
                if lowlink[v] == index[v]:
                    component: list[str] = []
                    while True:
                        w = stack.pop()
                        on_stack[w] = False
                        component.append(w)
                        if w == v:
                            break
                    sccs.append(component)

    result: dict[str, list[str]] = {}
    for component in sccs:
        if len(component) > 1:
            for rid in component:
                result[rid] = [other for other in component if other != rid]
    return result


class Classification(IntEnum):
    observational = 0
    tactical = 1
    foundational = 2

    @classmethod
    def of(cls, s: str) -> "Classification":
        try:
            return cls[s]
        except KeyError:
            return cls.observational


async def _supersede_alerts(
    m_dir: Path, supersedes: list[str], new_classification: str
) -> dict[str, str]:
    """Return {id: old_classification} for superseded records that need a warning.

    Covers two cases:
    - Any superseded foundational record (same or lower new tier) — guardrail replacement
    - Any superseded record with higher classification than the new one — tier downgrade
    """
    if not supersedes:
        return {}
    new_rank = Classification.of(new_classification)
    targets = set(supersedes)
    alerts: dict[str, str] = {}
    expertise_dir = m_dir / "expertise"
    if expertise_dir.exists():
        for jsonl_file in expertise_dir.glob("*.jsonl"):
            for r in await read_domain_records(jsonl_file):
                if r.get("id") in targets:
                    old_cls = r.get("classification", "")
                    if (
                        Classification.of(old_cls) == Classification.foundational
                        or Classification.of(old_cls) > new_rank
                    ):
                        alerts[r["id"]] = old_cls
    return alerts


def _format_supersession_alerts(alerts: dict[str, str], new_classification: str) -> str:
    """Render the ⚠ SUPERSESSION WARNING block for a set of alerted supersede
    targets, or "" if there are none. Shared by _record_expertise (write) and
    _edit_record (adding a supersedes reference to an existing record)."""
    if not alerts:
        return ""
    new_rank = Classification.of(new_classification)
    lines: list[str] = []
    for sid, old_cls in alerts.items():
        if Classification.of(old_cls) > new_rank:
            lines.append(f"  {sid}: {old_cls} → {new_classification} (classification downgrade)")
        else:
            lines.append(f"  {sid}: {old_cls} (foundational guardrail replaced)")
    return (
        "\n\n⚠ SUPERSESSION WARNING — stop and flag this to the user before continuing:\n"
        + "\n".join(lines)
    )
