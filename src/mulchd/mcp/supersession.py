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
    # Same edges, but keeping every superseder rather than one winner — a fork
    # is exactly what tip resolution has to detect, so it can't run off a map
    # that has already discarded all but the last-scanned branch.
    superseders: dict[str, list[str]] = {}
    for stored in project_records:
        sid = stored.get("id", "")
        for vid in stored.get("supersedes") or []:
            if sid:
                superseded_by[vid] = (sid, stored.get("_domain", ""))
                superseders.setdefault(vid, []).append(sid)

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

            tips, hops = _resolve_tips(rid or "", superseders, cycles)
            if len(tips) > 1:
                r["_superseded_tip_ambiguous"] = tips
                branch_domains = {
                    tid: dom
                    for tid in tips
                    if (dom := (live_by_id.get(tid) or {}).get("_domain", ""))
                    and dom != r.get("_domain", "")
                }
                if branch_domains:
                    r["_superseded_tip_ambiguous_domains"] = branch_domains
            elif hops > 1:
                # hops == 1 means the immediate superseder is already the tip,
                # so annotating it would only repeat what the header shows.
                r["_superseded_tip"] = tips[0]
                r["_superseded_tip_hops"] = hops
                tip_domain = (live_by_id.get(tips[0]) or {}).get("_domain", "")
                if tip_domain and tip_domain != r.get("_domain", ""):
                    r["_superseded_tip_domain"] = tip_domain

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


def _resolve_tips(
    record_id: str,
    superseders: dict[str, list[str]],
    cycles: dict[str, list[str]],
) -> tuple[list[str], int]:
    """Every terminal record reachable by walking supersede edges forward from
    record_id, sorted, plus the hop distance to it when there is exactly one.

    Breadth-first, so the reported distance is the shortest path when two
    branches reconverge on the same tip. Hops is 0 whenever the walk ends at
    more than one tip — a forked graph has no single current record, and
    picking a winner would assert an ordering the data doesn't carry.

    Cycle members are neither traversed nor returned: reads deliberately leave
    them untagged with the contradictory-cycle banner instead, and following a
    cycle edge wouldn't terminate. A chain running into a cycle therefore
    resolves to no tip rather than to the last record before it, since that
    record isn't actually current.
    """
    if record_id in cycles:
        return [], 0
    tips: dict[str, int] = {}
    seen = {record_id}
    frontier = [record_id]
    depth = 0
    while frontier:
        depth += 1
        next_frontier: list[str] = []
        for node in frontier:
            onward = [s for s in superseders.get(node, []) if s not in cycles]
            if not onward:
                # The starting record is a tip of nothing — it's the walk's origin.
                if node != record_id:
                    tips.setdefault(node, depth - 1)
                continue
            for s in onward:
                if s not in seen:
                    seen.add(s)
                    next_frontier.append(s)
        frontier = next_frontier
    ordered = sorted(tips)
    return ordered, tips[ordered[0]] if len(ordered) == 1 else 0


def _cross_domain_supersede_hints(records: list[dict]) -> list[dict]:
    """Structured "read this domain next" pointers for records superseded from
    outside their own domain.

    Points at whatever is actually current, not at the nearest superseder: for
    a chain, that's the tip, and an out-of-domain intermediate hop generates no
    hint at all once the tip is local — sending a reader to a domain whose only
    relevant record is itself superseded is the same wasted fetch this field
    exists to prevent. Forks emit one pointer per out-of-domain branch, since
    no single one of them is the answer.

    Records must already be annotated by _mark_superseded.
    """
    hints: list[dict] = []
    for r in records:
        rid = r.get("id")
        if r.get("_superseded_tip_domain"):
            hints.append(
                {
                    "record_id": rid,
                    "superseded_by": r["_superseded_tip"],
                    "in_domain": r["_superseded_tip_domain"],
                }
            )
        elif r.get("_superseded_tip"):
            continue  # tip is in this record's own domain — nothing else to read
        elif r.get("_superseded_tip_ambiguous"):
            for tid, dom in (r.get("_superseded_tip_ambiguous_domains") or {}).items():
                hints.append({"record_id": rid, "superseded_by": tid, "in_domain": dom})
        elif r.get("_superseder_domain"):
            hints.append(
                {
                    "record_id": rid,
                    "superseded_by": r["_superseded_by"],
                    "in_domain": r["_superseder_domain"],
                }
            )
    return hints


async def _mark_related_to(records: list[dict], org_slug: str, project_slug: str) -> None:
    """Tag each record with incoming/outgoing relates_to links.

    Mirrors _mark_superseded's scan-the-whole-project approach, but
    relates_to is a plain, non-exclusive association rather than a
    hierarchical one — a target can be referenced by any number of other
    records (unlike _superseded_by, which keeps whichever superseder happened
    to be scanned last), so incoming links are collected as a list, not a
    single winner.
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
