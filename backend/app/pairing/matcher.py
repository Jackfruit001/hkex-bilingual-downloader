"""The pairing engine (SPEC §4, D-009, D-010 to D-011). Pure: no I/O, no clock.

The order of work is the order of trust:
1. stubs are removed first and claim the real document they stand in for;
2. decisive evidence (identical bytes, a conclusive content check) fixes pairs;
3. a pair that is *dominant* (each side's best candidate, clear of every rival) is fixed and is
   `matched` only if it also passes the threshold, conflict and layout rules;
4. what remains is assigned one-to-one and shown as `check`;
5. unassigned documents of separately submitted categories are searched ±14 days;
6. everything else is single-language, with the reason.
"""

from bisect import bisect_left
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from itertools import pairwise

from app.config import PAIRING, PairingConfig
from app.domain.models import Document, Lang
from app.pairing import evidence as text
from app.pairing.models import (
    Announcement,
    ContentEvidence,
    ContentVerdict,
    Format,
    PairingDiagnostics,
    PairingResult,
    Rival,
    SignalHit,
    SingleReason,
    Status,
)
from app.pairing.signals import (
    category_signal,
    hard_conflicts,
    news_id_signal,
    numbering_uses_same_number,
    sequence_signal,
    time_signal,
    title_number_signal,
)

_MULTI_FILE_LABELS = frozenset({"multi-files", "多檔案"})
_FORMAT_NAME = {
    Format.PDF: "PDF",
    Format.WEB_PAGE: "web page",
    Format.MULTI_FILE: "multiple files",
    Format.OTHER: "other format",
}


def document_format(doc: Document) -> Format:
    if doc.size_label.strip().lower() in _MULTI_FILE_LABELS:
        return Format.MULTI_FILE
    name = doc.path.rsplit("/", 1)[-1]
    extension = name.rsplit(".", 1)[-1].lower() if "." in name else doc.file_type.lower()
    if extension == "pdf":
        return Format.PDF
    if extension in ("htm", "html"):
        return Format.WEB_PAGE
    return Format.OTHER


def _order(doc: Document) -> tuple[datetime, date, int, str]:
    return (
        doc.release_at,
        doc.folder_date or date.min,
        doc.seq if doc.seq is not None else -1,
        doc.news_id,
    )


def _int(value: str) -> int | None:
    try:
        return int(value)
    except ValueError:
        return None


@dataclass(frozen=True)
class _Edge:
    en: int
    tc: int
    score: int
    hits: tuple[SignalHit, ...]
    conflicts: tuple[str, ...]
    neutral: bool  # inside a non-interleaved same-minute group (D-011)


@dataclass(frozen=True)
class _Pair:
    edge: _Edge
    status: Status
    decisive: str | None = None  # "S5" or "S7"
    separate: bool = False


def best_assignment(
    weights: dict[tuple[int, int], int], *, max_side: int
) -> tuple[list[tuple[int, int]], int]:
    """Maximum-weight one-to-one assignment, per connected component.

    Exhaustive (bitmask dynamic programme over the smaller side) when that side has at most
    `max_side` nodes; otherwise greedy, and the number of greedy components is returned.
    Ties break on the file order so the result never depends on input order.
    """
    adjacency: dict[tuple[str, int], list[tuple[str, int]]] = defaultdict(list)
    for i, j in weights:
        adjacency[("e", i)].append(("t", j))
        adjacency[("t", j)].append(("e", i))
    seen: set[tuple[str, int]] = set()
    chosen: list[tuple[int, int]] = []
    greedy = 0
    for start in sorted(adjacency):
        if start in seen:
            continue
        stack, component = [start], []
        seen.add(start)
        while stack:
            node = stack.pop()
            component.append(node)
            for nxt in adjacency[node]:
                if nxt not in seen:
                    seen.add(nxt)
                    stack.append(nxt)
        lefts = sorted(i for kind, i in component if kind == "e")
        rights = sorted(j for kind, j in component if kind == "t")
        rank_e = {i: k for k, i in enumerate(lefts)}
        rank_t = {j: k for k, j in enumerate(rights)}
        local = {
            (i, j): w * 100 - abs(rank_e[i] - rank_t[j])
            for (i, j), w in weights.items()
            if i in rank_e and j in rank_t
        }
        if min(len(lefts), len(rights)) > max_side:
            greedy += 1
            taken_e: set[int] = set()
            taken_t: set[int] = set()
            for (i, j), _ in sorted(local.items(), key=lambda kv: (-kv[1], kv[0])):
                if i not in taken_e and j not in taken_t:
                    taken_e.add(i)
                    taken_t.add(j)
                    chosen.append((i, j))
        else:
            chosen.extend(_exhaustive(local, lefts, rights))
    return sorted(chosen), greedy


def _exhaustive(
    weights: dict[tuple[int, int], int], lefts: list[int], rights: list[int]
) -> list[tuple[int, int]]:
    flip = len(lefts) > len(rights)
    small, large = (rights, lefts) if flip else (lefts, rights)
    index = {node: k for k, node in enumerate(small)}
    options: dict[int, list[tuple[int, int]]] = defaultdict(list)
    for (i, j), w in weights.items():
        big, little = (i, j) if flip else (j, i)
        options[big].append((index[little], w))
    states: dict[int, tuple[int, tuple[tuple[int, int], ...]]] = {0: (0, ())}
    for node in large:
        updated = dict(states)
        for mask, (total, pairs) in states.items():
            for k, w in options[node]:
                if mask >> k & 1:
                    continue
                candidate = (total + w, (*pairs, (node, small[k])))
                new_mask = mask | 1 << k
                current = updated.get(new_mask)
                if current is None or (-candidate[0], candidate[1]) < (-current[0], current[1]):
                    updated[new_mask] = candidate
        states = updated
    _, pairs = min(states.values(), key=lambda v: (-v[0], v[1]))
    return [(big, little) if flip else (little, big) for big, little in pairs]


class _Pairer:
    def __init__(
        self,
        english: Sequence[Document],
        chinese: Sequence[Document],
        cfg: PairingConfig,
        content: ContentEvidence,
        searched: tuple[date, date] | None,
    ) -> None:
        self.cfg = cfg
        self.content = content
        self.searched = searched
        self.warnings: list[str] = []
        self.orphan_stubs = 0
        self.greedy_components = 0

        real_en = sorted((d for d in english if not d.is_stub), key=_order)
        real_tc = sorted((d for d in chinese if not d.is_stub), key=_order)
        self.stub_claims_en = self._claim(
            sorted((d for d in chinese if d.is_stub), key=_order), real_en, real_tc
        )
        self.stub_claims_tc = self._claim(
            sorted((d for d in english if d.is_stub), key=_order), real_tc, real_en
        )
        claimed_en = {real.news_id for real, _ in self.stub_claims_en}
        claimed_tc = {real.news_id for real, _ in self.stub_claims_tc}
        self.E = [d for d in real_en if d.news_id not in claimed_en]
        self.T = [d for d in real_tc if d.news_id not in claimed_tc]
        self.by_e: dict[int, list[_Edge]] = {}
        self.by_t: dict[int, list[_Edge]] = {}

        folders: dict[date, list[Document]] = defaultdict(list)
        for doc in real_en + real_tc:
            if doc.folder_date is not None:
                folders[doc.folder_date].append(doc)
        self.same_number = numbering_uses_same_number(folders, cfg)

        self.ambiguous_groups = self._find_ambiguous_groups()

    # --- stubs -------------------------------------------------------------------------

    def _claim(
        self, stubs: list[Document], reals: list[Document], partners: list[Document]
    ) -> list[tuple[Document, Document]]:
        """(real document, stub) pairs: each stub claims the document it stands in for.

        A stub is normally the file number right after its document, but file numbers are one
        counter for the whole market, so another issuer's file can sit between them (2 of 790
        in the recorded data were at +2 and +3). The first pass takes the exact +1 slot. The
        second takes a document up to `candidate_window` numbers earlier in the same minute,
        only if exactly one qualifies and it has no real counterpart in the stub's section.
        """
        by_number: dict[tuple[date, int], list[Document]] = defaultdict(list)
        by_minute: dict[datetime, list[Document]] = defaultdict(list)
        for doc in reals:
            if doc.folder_date is not None and doc.seq is not None:
                by_number[(doc.folder_date, doc.seq)].append(doc)
            else:
                by_minute[doc.release_at].append(doc)
        has_counterpart = {
            (p.folder_date, p.seq, p.release_at)
            for p in partners
            if p.folder_date is not None and p.seq is not None
        }
        claimed: dict[str, Document] = {}
        found: list[tuple[Document, Document]] = []

        def take(real: Document, stub: Document) -> None:
            claimed[real.news_id] = stub
            found.append((real, stub))

        later: list[Document] = []
        for stub in stubs:
            if stub.folder_date is not None and stub.seq is not None:
                exact = [
                    d
                    for d in by_number.get((stub.folder_date, stub.seq - 1), [])
                    if d.release_at == stub.release_at and d.news_id not in claimed
                ]
                if len(exact) == 1:
                    take(exact[0], stub)
                else:
                    later.append(stub)
            else:
                stub_id = _int(stub.news_id)
                shared = [
                    d
                    for d in by_minute.get(stub.release_at, [])
                    if stub_id is not None
                    and _int(d.news_id) == stub_id - 1
                    and d.news_id not in claimed
                ]
                if len(shared) == 1:
                    take(shared[0], stub)
                else:
                    self.orphan_stubs += 1
        for stub in later:
            assert stub.folder_date is not None and stub.seq is not None
            window = range(stub.seq - self.cfg.candidate_window, stub.seq - 1)
            options = [
                d
                for seq in window
                for d in by_number.get((stub.folder_date, seq), [])
                if d.release_at == stub.release_at
                and d.news_id not in claimed
                and (d.folder_date, (d.seq or 0) + 1, d.release_at) not in has_counterpart
            ]
            if len(options) == 1:
                take(options[0], stub)
            else:
                self.orphan_stubs += 1
        return found

    # --- same-minute groups (D-011) ----------------------------------------------------------

    @staticmethod
    def _group_key(doc: Document) -> tuple[datetime, date | None]:
        return (doc.release_at, doc.folder_date)

    def _find_ambiguous_groups(self) -> set[tuple[datetime, date | None]]:
        groups: dict[tuple[datetime, date | None], list[Document]] = defaultdict(list)
        for doc in self.E + self.T:
            groups[self._group_key(doc)].append(doc)
        ambiguous: set[tuple[datetime, date | None]] = set()
        self.group_counts: dict[tuple[datetime, date | None], tuple[int, int]] = {}
        for key, docs in groups.items():
            ens = [d for d in docs if d.lang is Lang.EN]
            tcs = [d for d in docs if d.lang is Lang.TC]
            if not ens or not tcs:
                continue
            same_number = bool(key[1] and self.same_number.get(key[1], False))
            if not self._interleaved(ens, tcs, same_number):
                ambiguous.add(key)
                self.group_counts[key] = (len(ens), len(tcs))
        return ambiguous

    @staticmethod
    def _interleaved(ens: list[Document], tcs: list[Document], same_number: bool) -> bool:
        """No two documents of one language have consecutive file numbers (D-011).

        Not applicable where the Chinese file reuses the English number (2005): an exact number
        identifies the pair, whatever else was released in the minute.
        """
        if same_number or (len(ens) <= 1 and len(tcs) <= 1):
            return True
        for group in (ens, tcs):
            seqs = sorted(d.seq for d in group if d.seq is not None)
            if any(b - a == 1 for a, b in pairwise(seqs)):
                return False
        return True

    # --- scoring ---------------------------------------------------------------------------

    def _score(self, e: Document, t: Document, i: int, j: int) -> _Edge:
        cfg = self.cfg
        key = self._group_key(e)
        neutral = key == self._group_key(t) and key in self.ambiguous_groups
        same_number = bool(e.folder_date and self.same_number.get(e.folder_date, False))
        hits = [
            time_signal(e, t, cfg),
            category_signal(e, t, cfg),
            sequence_signal(e, t, same_number_numbering=same_number, neutral=neutral, cfg=cfg),
        ]
        if not neutral:
            s4 = news_id_signal(e, t, cfg)
            if s4 is not None:
                hits.append(s4)
        s6 = title_number_signal(e, t, cfg)
        if s6 is not None:
            hits.append(s6)
        return _Edge(
            i, j, sum(h.points for h in hits), tuple(hits), hard_conflicts(e, t, hits), neutral
        )

    def _candidates(self, ens: list[int], tcs: list[int]) -> dict[tuple[int, int], _Edge]:
        by_folder: dict[date, list[tuple[int, int]]] = defaultdict(list)
        by_minute: dict[datetime, list[int]] = defaultdict(list)
        for j in tcs:
            t = self.T[j]
            by_minute[t.release_at].append(j)
            if t.folder_date is not None and t.seq is not None:
                by_folder[t.folder_date].append((t.seq, j))
        for entries in by_folder.values():
            entries.sort()
        edges: dict[tuple[int, int], _Edge] = {}
        for i in ens:
            e = self.E[i]
            found: set[int] = set(by_minute.get(e.release_at, []))
            if e.folder_date is not None and e.seq is not None and e.folder_date in by_folder:
                entries = by_folder[e.folder_date]
                low = bisect_left(entries, (e.seq - self.cfg.candidate_window, -1))
                for seq, j in entries[low:]:
                    if seq > e.seq + self.cfg.candidate_window:
                        break
                    found.add(j)
            for j in found:
                edges[(i, j)] = self._score(e, self.T[j], i, j)
        return edges

    def _can_match(self, edge: _Edge) -> bool:
        if edge.conflicts or edge.neutral:
            return False
        e, t = self.E[edge.en], self.T[edge.tc]
        if e.category_codes or t.category_codes:
            return edge.score >= self.cfg.match_min_score
        kinds = {(h.id, h.kind) for h in edge.hits}
        return (
            edge.score >= self.cfg.match_min_score_no_category
            and ("S1", "same_minute") in kinds
            and (("S3", "plus_one") in kinds or ("S3", "same_number_c") in kinds)
        )

    # --- decisive evidence -------------------------------------------------------------------

    def _decisive(self) -> dict[tuple[int, int], str]:
        e_index = {d.news_id: i for i, d in enumerate(self.E)}
        t_index = {d.news_id: j for j, d in enumerate(self.T)}
        found: dict[tuple[int, int], str] = {}

        by_digest: dict[str, tuple[list[int], list[int]]] = defaultdict(lambda: ([], []))
        for (lang, news_id), digest in sorted(self.content.sha256.items()):
            if lang is Lang.EN and news_id in e_index:
                by_digest[digest][0].append(e_index[news_id])
            elif lang is Lang.TC and news_id in t_index:
                by_digest[digest][1].append(t_index[news_id])
        for _, (ens, tcs) in sorted(by_digest.items()):
            if len(ens) == 1 and len(tcs) == 1:
                found[(ens[0], tcs[0])] = "S5"
            elif ens and tcs:
                self.warnings.append("Several documents share identical bytes; none was confirmed.")

        for v in self.content.verdicts:
            if v.conclusive and v.en_news_id in e_index and v.tc_news_id in t_index:
                found.setdefault((e_index[v.en_news_id], t_index[v.tc_news_id]), "S7")

        usage_e = Counter(i for i, _ in found)
        usage_t = Counter(j for _, j in found)
        accepted: dict[tuple[int, int], str] = {}
        for (i, j), kind in sorted(found.items()):
            if usage_e[i] > 1 or usage_t[j] > 1:
                self.warnings.append(
                    "A document had two conclusive counterparts; none was confirmed."
                )
                continue
            if self._score(self.E[i], self.T[j], i, j).conflicts:
                continue  # a decisive signal never overrides a hard conflict
            accepted[(i, j)] = kind
        return accepted

    # --- the passes -----------------------------------------------------------------------------

    def run(self) -> PairingResult:
        cfg = self.cfg
        decisive = self._decisive()
        fixed_e = {i for i, _ in decisive}
        fixed_t = {j for _, j in decisive}
        pairs: list[_Pair] = []
        for (i, j), kind in sorted(decisive.items()):
            edge = self._score(self.E[i], self.T[j], i, j)
            pairs.append(_Pair(edge, Status.MATCHED, decisive=kind))

        free_e = [i for i in range(len(self.E)) if i not in fixed_e]
        free_t = [j for j in range(len(self.T)) if j not in fixed_t]
        edges = self._candidates(free_e, free_t)
        by_e: dict[int, list[_Edge]] = defaultdict(list)
        by_t: dict[int, list[_Edge]] = defaultdict(list)
        for edge in edges.values():
            by_e[edge.en].append(edge)
            by_t[edge.tc].append(edge)
        self.by_e, self.by_t = by_e, by_t

        def clear_of_rivals(edge: _Edge, others: list[_Edge]) -> bool:
            scores = sorted((o.score for o in others if o is not edge), reverse=True)
            best_other = scores[0] if scores else None
            return best_other is None or edge.score - best_other >= cfg.margin

        taken_e: set[int] = set()
        taken_t: set[int] = set()
        for edge in sorted(edges.values(), key=lambda x: (x.en, x.tc)):
            if edge.score < cfg.check_min_score:
                continue
            if (
                clear_of_rivals(edge, by_e[edge.en])
                and clear_of_rivals(edge, by_t[edge.tc])
                and edge.score == max(o.score for o in by_e[edge.en])
                and edge.score == max(o.score for o in by_t[edge.tc])
            ):
                status = Status.MATCHED if self._can_match(edge) else Status.CHECK
                pairs.append(_Pair(edge, status))
                taken_e.add(edge.en)
                taken_t.add(edge.tc)

        remaining = {
            key: edge.score
            for key, edge in edges.items()
            if edge.score >= cfg.check_min_score
            and edge.en not in taken_e
            and edge.tc not in taken_t
        }
        assigned, greedy = best_assignment(remaining, max_side=cfg.exhaustive_max_side)
        self.greedy_components += greedy
        for key in assigned:
            pairs.append(_Pair(edges[key], Status.CHECK))
            taken_e.add(key[0])
            taken_t.add(key[1])

        pairs.extend(self._separate(free_e, free_t, taken_e, taken_t))

        return self._build(pairs)

    def _separate(
        self, free_e: list[int], free_t: list[int], taken_e: set[int], taken_t: set[int]
    ) -> list[_Pair]:
        """Annual reports and listing documents may be submitted in each language separately."""
        cfg = self.cfg

        def separate_category(doc: Document) -> bool:
            return any(
                c in cfg.separate_codes or c.startswith(cfg.separate_code_prefixes)
                for c in doc.category_codes
            )

        ens = [i for i in free_e if i not in taken_e and separate_category(self.E[i])]
        tcs = [j for j in free_t if j not in taken_t and separate_category(self.T[j])]
        weights: dict[tuple[int, int], int] = {}
        found: dict[tuple[int, int], _Edge] = {}
        for i in ens:
            e = self.E[i]
            for j in tcs:
                t = self.T[j]
                gap = abs((e.release_at.date() - t.release_at.date()).days)
                if not 1 <= gap <= cfg.separate_days or set(e.category_codes) != set(
                    t.category_codes
                ):
                    continue
                s2 = category_signal(e, t, cfg)
                s6 = title_number_signal(e, t, cfg)
                hits = [s2] + ([s6] if s6 else [])
                edge = _Edge(
                    i,
                    j,
                    sum(h.points for h in hits),
                    tuple(hits),
                    hard_conflicts(e, t, hits),
                    False,
                )
                if edge.conflicts or edge.score < cfg.separate_min_score:
                    continue
                found[(i, j)] = edge
                weights[(i, j)] = edge.score * 100 - gap
        assigned, greedy = best_assignment(
            {k: w // 100 for k, w in weights.items()}, max_side=cfg.exhaustive_max_side
        )
        self.greedy_components += greedy
        return [_Pair(found[k], Status.CHECK, separate=True) for k in assigned]

    # --- output ----------------------------------------------------------------------------------

    def _rivals(self, edge: _Edge) -> tuple[Rival, ...]:
        found: list[Rival] = []
        for other in self.by_e.get(edge.en, []):
            if other.tc != edge.tc and other.score >= self.cfg.check_min_score:
                found.append(Rival(document=self.T[other.tc], score=other.score))
        for other in self.by_t.get(edge.tc, []):
            if other.en != edge.en and other.score >= self.cfg.check_min_score:
                found.append(Rival(document=self.E[other.en], score=other.score))
        found.sort(key=lambda r: (-r.score, r.document.lang.value, _order(r.document)))
        return tuple(found[:2])

    def _verdict(self, e: Document, t: Document) -> ContentVerdict | None:
        for v in self.content.verdicts:
            if v.conclusive and v.en_news_id == e.news_id and v.tc_news_id == t.news_id:
                return v
        return None

    def _announce_pair(self, p: _Pair) -> Announcement:
        e, t = self.E[p.edge.en], self.T[p.edge.tc]
        matched = p.status is Status.MATCHED
        signals = list(p.edge.hits)
        verdict = self._verdict(e, t) if p.decisive == "S7" else None
        if p.decisive == "S5":
            signals.append(SignalHit(id="S5", points=0, kind="identical_bytes"))
        if verdict is not None:
            signals.append(
                SignalHit(id="S7", points=0, kind="conclusive", values=(f"{verdict.score:.2f}",))
            )
        fe, ft = document_format(e), document_format(t)
        different_days = e.release_at.date() != t.release_at.date()
        separate = p.separate or (p.decisive is not None and different_days)
        layout = p.edge.neutral and p.decisive is None
        rivals = () if matched else self._rivals(p.edge)
        lines = text.pair_evidence(
            e,
            t,
            tuple(signals),
            matched=matched,
            conflicts=p.edge.conflicts,
            bilingual=p.decisive == "S5",
            separate=separate,
            verdict=verdict,
            layout_counts=self.group_counts.get(self._group_key(e)) if layout else None,
            rivals=rivals,
            mixed_formats=(_FORMAT_NAME[fe], _FORMAT_NAME[ft]) if fe is not ft else None,
        )
        return Announcement(
            id=f"{e.news_id}:{t.news_id}",
            status=p.status,
            release_at=e.release_at,
            en=e,
            tc=t,
            score=p.edge.score,
            signals=tuple(signals),
            evidence=lines,
            rivals=rivals,
            format=fe if fe is ft else Format.OTHER,
            bilingual=p.decisive == "S5",
            separate=separate,
            layout_ambiguous=layout,
        )

    def _announce_single(
        self, doc: Document, *, stub: Document | None = None, lost_to: Document | None = None
    ) -> Announcement:
        english = doc.lang is Lang.EN
        reason = SingleReason.STUB_IN_OTHER_SECTION if stub else SingleReason.NOT_FOUND
        return Announcement(
            id=f"{doc.news_id}:-" if english else f"-:{doc.news_id}",
            status=Status.EN_ONLY if english else Status.TC_ONLY,
            release_at=doc.release_at,
            en=doc if english else None,
            tc=None if english else doc,
            evidence=text.single_evidence(doc, reason, searched=self.searched, lost_to=lost_to),
            reason=reason,
            stub=stub,
            format=document_format(doc),
        )

    def _build(self, pairs: list[_Pair]) -> PairingResult:
        used_e = {p.edge.en for p in pairs}
        used_t = {p.edge.tc for p in pairs}
        partner_of_e = {p.edge.en: p.edge.tc for p in pairs}
        partner_of_t = {p.edge.tc: p.edge.en for p in pairs}
        minimum = self.cfg.check_min_score

        announcements = [self._announce_pair(p) for p in pairs]
        for i, e in enumerate(self.E):
            if i not in used_e:
                taken = [
                    x for x in self.by_e.get(i, []) if x.score >= minimum and x.tc in partner_of_t
                ]
                best = max(taken, key=lambda x: (x.score, -x.tc), default=None)
                announcements.append(
                    self._announce_single(e, lost_to=self.T[best.tc] if best else None)
                )
        for j, t in enumerate(self.T):
            if j not in used_t:
                taken = [
                    x for x in self.by_t.get(j, []) if x.score >= minimum and x.en in partner_of_e
                ]
                best = max(taken, key=lambda x: (x.score, -x.en), default=None)
                announcements.append(
                    self._announce_single(t, lost_to=self.E[best.en] if best else None)
                )
        for real, stub in self.stub_claims_en + self.stub_claims_tc:
            announcements.append(self._announce_single(real, stub=stub))

        announcements.sort(key=lambda a: (a.release_at, a.id), reverse=True)
        diagnostics = PairingDiagnostics(
            announcements=len(announcements),
            by_status=dict(Counter(a.status.value for a in announcements)),
            orphan_stubs=self.orphan_stubs,
            non_interleaved_groups=len(self.ambiguous_groups),
            greedy_components=self.greedy_components,
            warnings=tuple(dict.fromkeys(self.warnings)),
        )
        return PairingResult(tuple(announcements), diagnostics)


def pair_documents(
    english: Sequence[Document],
    chinese: Sequence[Document],
    *,
    cfg: PairingConfig = PAIRING,
    content: ContentEvidence | None = None,
    searched: tuple[date, date] | None = None,
) -> PairingResult:
    """Pair English and Traditional Chinese documents for one stock (SPEC §4)."""
    return _Pairer(english, chinese, cfg, content or ContentEvidence(), searched).run()
