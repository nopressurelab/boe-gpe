"""Environmental relevance classifier.

The whole vocabulary comes from config/classification.json; this module only
applies the rules. A term scores once per field it appears in, and each field
contributes according to `field_weights`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .util import normalize

_WORD_EDGE = r"(?<![0-9a-z])"
_WORD_EDGE_END = r"(?![0-9a-z])"


@dataclass
class Verdict:
    score: float = 0.0
    topics: list[str] = field(default_factory=list)
    doc_types: list[str] = field(default_factory=list)
    matches: list[dict[str, Any]] = field(default_factory=list)
    topic_scores: dict[str, float] = field(default_factory=dict)

    @property
    def relevant(self) -> bool:
        return self._relevant

    _relevant: bool = False


def _compile(term: str) -> re.Pattern[str]:
    """Normalized term -> pattern with word boundaries and flexible whitespace."""
    parts = [re.escape(token) for token in term.split()]
    body = r"\s+".join(parts)
    return re.compile(_WORD_EDGE + body + _WORD_EDGE_END)


class Classifier:
    def __init__(self, rules: dict[str, Any]):
        self.rules = rules
        scoring = rules.get("scoring", {})
        self.min_score = float(scoring.get("min_score", 3.0))
        self.min_topic_score = float(scoring.get("min_topic_score", 1.5))
        self.field_weights: dict[str, float] = {
            key: float(value) for key, value in (scoring.get("field_weights") or {}).items()
        }
        # Topics score on these fields only. The name of the issuing body is left
        # to `boosts`: on its own it signals environmental remit, not a topic.
        self.topic_fields: list[str] = [
            f for f in (scoring.get("topic_fields") or list(self.field_weights))
            if f in self.field_weights
        ]
        norm = scoring.get("normalize", {})
        self._norm_kwargs = {
            "lowercase": norm.get("lowercase", True),
            "accents": norm.get("strip_accents", True),
            "collapse_whitespace": norm.get("collapse_whitespace", True),
        }
        self.topics = [
            {
                "id": topic["id"],
                "label": topic.get("label", topic["id"]),
                "color": topic.get("color", "#666"),
                "min_score": float(topic.get("min_score", self.min_topic_score)),
                "terms": [(_compile(self._norm(t["t"])), float(t.get("w", 1)), t["t"])
                          for t in topic.get("terms", [])],
            }
            for topic in rules.get("topics", [])
        ]
        self.boosts = [
            {
                "id": boost.get("id", "boost"),
                "fields": boost.get("fields") or list(self.field_weights),
                "terms": [(_compile(self._norm(t["t"])), float(t.get("w", 1)), t["t"])
                          for t in boost.get("terms", [])],
            }
            for boost in rules.get("boosts", [])
        ]
        self.exclusions = [(_compile(self._norm(t["t"])), float(t.get("w", -1)), t["t"])
                           for t in rules.get("exclusions", [])]
        self.doc_types = [
            {
                "id": doc["id"],
                "label": doc.get("label", doc["id"]),
                "terms": [_compile(self._norm(t)) for t in doc.get("terms", [])],
            }
            for doc in rules.get("doc_types", [])
        ]

    def _norm(self, text: str) -> str:
        return normalize(text, **self._norm_kwargs)

    # -- API ------------------------------------------------------------
    def topic_label(self, topic_id: str) -> str:
        for topic in self.topics:
            if topic["id"] == topic_id:
                return topic["label"]
        return topic_id

    def topic_meta(self) -> list[dict[str, str]]:
        return [{"id": t["id"], "label": t["label"], "color": t["color"]} for t in self.topics]

    def doc_type_meta(self) -> list[dict[str, str]]:
        return [{"id": d["id"], "label": d["label"]} for d in self.doc_types]

    def classify(self, fields: dict[str, str]) -> Verdict:
        haystack = {name: self._norm(text or "")
                    for name, text in fields.items()
                    if name in self.field_weights}
        joined = " · ".join(haystack.values())

        verdict = Verdict()
        total = 0.0
        for topic in self.topics:
            topic_score = 0.0
            for pattern, weight, label in topic["terms"]:
                for field_name in self.topic_fields:
                    text = haystack.get(field_name, "")
                    if text and pattern.search(text):
                        gain = weight * self.field_weights.get(field_name, 0.0)
                        topic_score += gain
                        verdict.matches.append({
                            "term": label, "field": field_name,
                            "topic": topic["id"], "weight": round(gain, 2),
                        })
            if topic_score > 0:
                verdict.topic_scores[topic["id"]] = round(topic_score, 2)
                total += topic_score
                if topic_score >= topic["min_score"]:
                    verdict.topics.append(topic["id"])

        for boost in self.boosts:
            for pattern, weight, label in boost["terms"]:
                for field_name in boost["fields"]:
                    text = haystack.get(field_name, "")
                    if text and pattern.search(text):
                        gain = weight * self.field_weights.get(field_name, 0.0)
                        total += gain
                        verdict.matches.append({
                            "term": label, "field": field_name,
                            "topic": boost["id"], "weight": round(gain, 2),
                        })

        for pattern, weight, label in self.exclusions:
            if pattern.search(joined):
                total += weight
                verdict.matches.append({
                    "term": label, "field": "*", "topic": "exclusion",
                    "weight": round(weight, 2),
                })

        verdict.score = round(total, 2)
        verdict._relevant = total >= self.min_score
        if verdict._relevant:
            verdict.doc_types = [doc["id"] for doc in self.doc_types
                                 if any(p.search(joined) for p in doc["terms"])]
            if not verdict.topics and verdict.topic_scores:
                best = max(verdict.topic_scores.items(), key=lambda kv: kv[1])[0]
                verdict.topics = [best]
        return verdict
