"""Lightweight BM25 retrieval over the company document library.

Pure-Python and dependency-free so the prototype runs anywhere. In the
production build this is the module you'd swap for a vector store fed by a
SharePoint/OneDrive ingestion job — the interface (search -> RetrievedSource)
stays the same.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from .catalog import DATA_DIR
from .models import RetrievedSource

_TOKEN_RE = re.compile(r"[a-z0-9']+")
_STOP = set("the a an and or of to in for with on at is are be this that our we".split())


def _tokens(text: str) -> list[str]:
    return [t for t in _TOKEN_RE.findall(text.lower()) if t not in _STOP]


@dataclass
class _Doc:
    doc_id: str
    title: str
    text: str
    tf: Counter = field(default_factory=Counter)
    length: int = 0


class DocumentIndex:
    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.docs: list[_Doc] = []
        self.df: Counter = Counter()
        self.avg_len = 0.0

    @classmethod
    def build(cls, data_dir: Path = DATA_DIR) -> "DocumentIndex":
        idx = cls()
        for sub in ("venues", "menus", "proposals"):
            folder = data_dir / sub
            if not folder.is_dir():
                continue
            for path in sorted(folder.glob("*.md")):
                text = path.read_text()
                title = next((l.lstrip("# ").strip() for l in text.splitlines() if l.startswith("#")), path.stem)
                idx._add(f"{sub}/{path.name}", title, text)
        idx._finalize()
        return idx

    def _add(self, doc_id: str, title: str, text: str) -> None:
        toks = _tokens(title + " " + text)
        doc = _Doc(doc_id=doc_id, title=title, text=text, tf=Counter(toks), length=len(toks))
        self.docs.append(doc)
        for term in doc.tf:
            self.df[term] += 1

    def _finalize(self) -> None:
        self.avg_len = (sum(d.length for d in self.docs) / len(self.docs)) if self.docs else 0.0

    def get(self, doc_id: str) -> RetrievedSource | None:
        for d in self.docs:
            if d.doc_id == doc_id:
                return RetrievedSource(doc_id=d.doc_id, title=d.title, score=0.0,
                                       excerpt=_excerpt(d.text, []))
        return None

    def search(self, query: str, top_k: int = 4) -> list[RetrievedSource]:
        q_terms = _tokens(query)
        n = len(self.docs)
        scored: list[tuple[float, _Doc]] = []
        for doc in self.docs:
            score = 0.0
            for term in q_terms:
                tf = doc.tf.get(term, 0)
                if not tf:
                    continue
                idf = math.log(1 + (n - self.df[term] + 0.5) / (self.df[term] + 0.5))
                score += idf * tf * (self.k1 + 1) / (tf + self.k1 * (1 - self.b + self.b * doc.length / self.avg_len))
            if score > 0:
                scored.append((score, doc))
        scored.sort(key=lambda s: -s[0])
        return [
            RetrievedSource(doc_id=d.doc_id, title=d.title, score=round(s, 3), excerpt=_excerpt(d.text, q_terms))
            for s, d in scored[:top_k]
        ]


def _excerpt(text: str, q_terms: list[str], width: int = 240) -> str:
    lowered = text.lower()
    pos = min((lowered.find(t) for t in q_terms if lowered.find(t) >= 0), default=0)
    start = max(0, pos - width // 4)
    snippet = text[start:start + width].replace("\n", " ").strip()
    return ("…" if start else "") + snippet + ("…" if start + width < len(text) else "")
