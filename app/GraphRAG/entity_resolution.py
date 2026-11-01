from __future__ import annotations

import math
import re
import unicodedata
from collections import defaultdict
from typing import Any

from .embeddings import cosine_similarity, embed_texts
from .models.graph_models import CanonicalEntity, EntityMention

# Bidirectional domain synonym groups
SYNONYM_GROUPS: list[set[str]] = [
    {"atp", "adenosine triphosphate", "atp molecule"},
    {"dna", "deoxyribonucleic acid", "dna molecule"},
    {"rna", "ribonucleic acid"},
    {"mrna", "messenger rna"},
    {"mitochondria", "mitochondrion", "chondriosome"},
    {"cell", "cells"},
    {"pollen grain", "pollen grains", "pollen"},
    {"microspore", "microspores"},
    {"seed", "seeds"},
    {"ovule", "ovules"},
    {"fruit", "fruits"},
    {"chloroplast", "chloroplasts"},
]

# Build bidirectional lookup table
KNOWN_SYNONYMS: dict[str, set[str]] = defaultdict(set)
for group in SYNONYM_GROUPS:
    for item in group:
        for other in group:
            if item != other:
                KNOWN_SYNONYMS[item].add(other)


def slugify(value: str) -> str:
    """Create a URL-safe stable slug from a string."""
    norm = unicodedata.normalize("NFKD", str(value).lower())
    clean = re.sub(r"[^\w\s-]", "", norm).strip()
    return re.sub(r"[-\s]+", "_", clean)


def build_entity_reference_text(surface_text: str, entity_type: str = "Concept", context: str = "") -> str:
    """Create an entity-specific embedding input that is distinct from a passage embedding."""
    name = str(surface_text or "").strip()
    entity_label = str(entity_type or "Concept").strip() or "Concept"
    if not name:
        name = "concept"
    reference = f"{name} [{entity_label}]"
    compact_context = re.sub(r"\s+", " ", str(context or "")).strip()
    if compact_context and compact_context.lower() not in reference.lower():
        short_context = compact_context[:180].rstrip()
        if short_context:
            reference = f"{reference} {short_context}"
    return reference


def normalize_entity_name(raw_name: str) -> str:
    """
    Deterministically normalize an entity mention:
    - Unicode normalization (NFKC)
    - Trim and collapse whitespace
    - Strip outer punctuation, but preserve hyphens, pluses, digits (e.g. ATP-synthase, CO2, Adam+Lookahead)
    - Lowercase for comparison
    """
    if not raw_name:
        return ""
    text = unicodedata.normalize("NFKC", str(raw_name).strip())
    text = re.sub(r"\s+", " ", text)
    text = text.strip("\"'“”‘’.,:;!?()[]{}")
    return text.lower()


def compute_lexical_similarity(str1: str, str2: str) -> float:
    """
    Compute character and token similarity between two strings.
    Penalizes differing numerical identifiers, Roman numerals, or specific single-character designations.
    """
    s1 = normalize_entity_name(str1)
    s2 = normalize_entity_name(str2)
    if not s1 or not s2:
        return 0.0
    if s1 == s2:
        return 1.0

    tokens1 = s1.split()
    tokens2 = s2.split()

    # Detect distinct numerals, Roman numerals, or isolated letter suffixes (e.g. "I" vs "II", "1" vs "2", "A" vs "B")
    id_pattern = re.compile(r"^(?:[0-9]+|[ivxlcdm]+|[a-z])$", re.IGNORECASE)
    ids1 = [t for t in tokens1 if id_pattern.match(t)]
    ids2 = [t for t in tokens2 if id_pattern.match(t)]
    if ids1 and ids2 and ids1 != ids2:
        # Contrasting identifiers mean distinct entities (e.g., RNA polymerase I vs II)
        return 0.0

    # Token-level overlap (Jaccard)
    t_set1 = set(tokens1)
    t_set2 = set(tokens2)
    token_jaccard = len(t_set1 & t_set2) / max(1, len(t_set1 | t_set2))

    # Character bigrams
    bigrams1 = {s1[i : i + 2] for i in range(len(s1) - 1)} or {s1}
    bigrams2 = {s2[i : i + 2] for i in range(len(s2) - 1)} or {s2}
    bigram_dice = (2.0 * len(bigrams1 & bigrams2)) / (len(bigrams1) + len(bigrams2))

    return 0.4 * token_jaccard + 0.6 * bigram_dice


def check_type_compatibility(type1: str | None, type2: str | None) -> float:
    """
    Check if two entity types are compatible.
    Returns:
      1.0 for exact type match
      0.9 if one is generic 'Concept'
      0.0 if mutually incompatible (e.g. BiologicalEntity vs Organization)
    """
    t1 = type1 or "Concept"
    t2 = type2 or "Concept"
    if t1 == t2:
        return 1.0
    if t1 == "Concept" or t2 == "Concept":
        return 0.9

    incompatible_pairs = {
        ("BiologicalEntity", "Organization"),
        ("BiologicalEntity", "Method"),
        ("ChemicalEntity", "Organization"),
        ("ChemicalEntity", "Person"),
        ("Person", "ChemicalEntity"),
        ("Person", "BiologicalEntity"),
        ("Location", "Person"),
    }
    if (t1, t2) in incompatible_pairs or (t2, t1) in incompatible_pairs:
        return 0.0

    return 0.5


class EntityResolver:
    """
    Multi-stage entity resolution pipeline:
    1. Candidate generation (exact normalized match, bidirectional alias match, vector similarity).
    2. Multi-feature candidate scoring.
    3. Calibrated threshold clustering & contextual/type disambiguation.
    4. Canonical identity reuse within collection scope.
    """

    def __init__(
        self,
        collection_id: str = "default",
        high_confidence_threshold: float = 0.88,
        medium_confidence_threshold: float = 0.72,
    ):
        self.collection_id = collection_id
        self.high_threshold = high_confidence_threshold
        self.medium_threshold = medium_confidence_threshold
        # canonical_id -> CanonicalEntity
        self.canonical_entities: dict[str, CanonicalEntity] = {}
        # (normalized_name, entity_type) -> canonical_id
        self.typed_name_index: dict[tuple[str, str], str] = {}
        # normalized_name -> canonical_id (first registered or dominant)
        self.primary_name_index: dict[str, str] = {}
        # alias -> canonical_id
        self.alias_index: dict[str, str] = {}
        # canonical_id -> embedding
        self.entity_embeddings: dict[str, list[float]] = {}

    def register_existing_entity(
        self,
        canonical_id: str,
        canonical_name: str,
        entity_type: str = "Concept",
        aliases: list[str] | None = None,
        embedding: list[float] | None = None,
    ) -> None:
        """Register an existing canonical entity from the database."""
        alias_set = []
        for alias in aliases or [canonical_name]:
            text = str(alias).strip()
            if text and text not in alias_set:
                alias_set.append(text)

        entity = CanonicalEntity(
            canonical_id=canonical_id,
            canonical_name=canonical_name,
            entity_type=entity_type,
            aliases=alias_set,
            collection_id=self.collection_id,
        )
        self.canonical_entities[canonical_id] = entity
        norm = normalize_entity_name(canonical_name)
        self.typed_name_index[(norm, entity_type)] = canonical_id
        if norm not in self.primary_name_index:
            self.primary_name_index[norm] = canonical_id
        for alias in entity.aliases:
            norm_alias = normalize_entity_name(alias)
            self.alias_index[norm_alias] = canonical_id
        if embedding:
            self.entity_embeddings[canonical_id] = embedding

    def build_entity_embedding(self, surface_text: str, entity_type: str = "Concept", context: str = "") -> list[float] | None:
        """Generate a compact entity-specific embedding from the entity label and local context."""
        reference = build_entity_reference_text(surface_text, entity_type, context)
        try:
            vectors = embed_texts([reference])
            return vectors[0] if vectors else None
        except Exception:
            return None

    def resolve_mention(
        self,
        surface_text: str,
        entity_type: str = "Concept",
        *,
        context: str = "",
        mention_embedding: list[float] | None = None,
    ) -> CanonicalEntity:
        """
        Resolve an entity mention to an existing canonical entity or create a new one.
        Follows the staged candidate generation and scoring policy.
        """
        clean_surface = surface_text.strip()
        normalized = normalize_entity_name(clean_surface)
        if not normalized:
            normalized = "concept"
            clean_surface = "Concept"

        # 1. Exact match on (normalized, entity_type)
        if (normalized, entity_type) in self.typed_name_index:
            existing_id = self.typed_name_index[(normalized, entity_type)]
            existing = self.canonical_entities[existing_id]
            if clean_surface not in existing.aliases and clean_surface != existing.canonical_name:
                existing.aliases.append(clean_surface)
            self.alias_index[normalized] = existing_id
            return existing

        # Check primary name index with type compatibility
        if normalized in self.primary_name_index:
            existing_id = self.primary_name_index[normalized]
            existing = self.canonical_entities[existing_id]
            type_compat = check_type_compatibility(existing.entity_type, entity_type)
            if type_compat > 0.0:
                if clean_surface not in existing.aliases and clean_surface != existing.canonical_name:
                    existing.aliases.append(clean_surface)
                if existing.entity_type == "Concept" and entity_type != "Concept":
                    existing.entity_type = entity_type
                self.alias_index[normalized] = existing_id
                return existing

        # 2. Alias match
        if normalized in self.alias_index:
            existing_id = self.alias_index[normalized]
            existing = self.canonical_entities[existing_id]
            if check_type_compatibility(existing.entity_type, entity_type) > 0.0:
                if clean_surface not in existing.aliases and clean_surface != existing.canonical_name:
                    existing.aliases.append(clean_surface)
                self.alias_index[normalized] = existing_id
                return existing

        # Check domain synonym table (bidirectional)
        synonyms = KNOWN_SYNONYMS.get(normalized, set())
        for syn in synonyms:
            if syn in self.primary_name_index:
                existing_id = self.primary_name_index[syn]
                existing = self.canonical_entities[existing_id]
                if check_type_compatibility(existing.entity_type, entity_type) > 0.0:
                    if clean_surface not in existing.aliases:
                        existing.aliases.append(clean_surface)
                    self.alias_index[normalized] = existing_id
                    return existing

        # 3. Candidate Generation & Similarity Matching against registered entities
        best_candidate: CanonicalEntity | None = None
        best_score = 0.0
        candidate_limit = min(len(self.canonical_entities), 20)
        ranked_candidates = []

        for candidate_id, candidate in self.canonical_entities.items():
            type_compat = check_type_compatibility(candidate.entity_type, entity_type)
            if type_compat == 0.0:
                continue

            lexical_sim = compute_lexical_similarity(normalized, candidate.canonical_name)
            for alias in candidate.aliases:
                lexical_sim = max(lexical_sim, compute_lexical_similarity(normalized, alias))

            if lexical_sim == 0.0:
                continue

            embedding_sim = 0.0
            if mention_embedding and candidate_id in self.entity_embeddings:
                try:
                    embedding_sim = max(0.0, cosine_similarity(mention_embedding, self.entity_embeddings[candidate_id]))
                except Exception:
                    embedding_sim = 0.0

            if embedding_sim > 0.0:
                combined_score = 0.45 * lexical_sim + 0.40 * embedding_sim + 0.15 * type_compat
            else:
                combined_score = 0.75 * lexical_sim + 0.25 * type_compat

            ranked_candidates.append((combined_score, candidate))

        ranked_candidates.sort(key=lambda item: item[0], reverse=True)
        for combined_score, candidate in ranked_candidates[:candidate_limit]:
            if combined_score > best_score:
                best_score = combined_score
                best_candidate = candidate

        # 4. Decision Policy
        if best_candidate and best_score >= self.high_threshold:
            if clean_surface not in best_candidate.aliases and clean_surface != best_candidate.canonical_name:
                best_candidate.aliases.append(clean_surface)
            self.alias_index[normalized] = best_candidate.canonical_id
            return best_candidate

        if best_candidate and best_score >= self.medium_threshold:
            type_compat = check_type_compatibility(best_candidate.entity_type, entity_type)
            if type_compat >= 0.9:
                if clean_surface not in best_candidate.aliases and clean_surface != best_candidate.canonical_name:
                    best_candidate.aliases.append(clean_surface)
                self.alias_index[normalized] = best_candidate.canonical_id
                return best_candidate

        # 5. Low confidence / No match -> Create new canonical entity
        canonical_slug = slugify(clean_surface) or "concept"
        canonical_id = f"c:{self.collection_id}:{canonical_slug}"

        # Homonym handling: if canonical_id exists with incompatible entity type, disambiguate ID by type!
        if canonical_id in self.canonical_entities:
            existing = self.canonical_entities[canonical_id]
            if existing.entity_type != entity_type:
                canonical_id = f"c:{self.collection_id}:{canonical_slug}_{slugify(entity_type)}"
                if canonical_id in self.canonical_entities:
                    canonical_id = f"{canonical_id}_{len(self.canonical_entities)}"

        new_entity = CanonicalEntity(
            canonical_id=canonical_id,
            canonical_name=clean_surface,
            entity_type=entity_type,
            aliases=[clean_surface],
            collection_id=self.collection_id,
            resolution_method="new_canonical",
            resolution_status="verified",
        )

        self.canonical_entities[canonical_id] = new_entity
        self.typed_name_index[(normalized, entity_type)] = canonical_id
        self.alias_index[normalized] = canonical_id
        if normalized not in self.primary_name_index:
            self.primary_name_index[normalized] = canonical_id
        if mention_embedding:
            self.entity_embeddings[canonical_id] = mention_embedding

        return new_entity


def detect_graph_communities(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    max_iterations: int = 15,
) -> dict[str, int]:
    """
    Lightweight Label Propagation Algorithm (LPA) for graph community detection.
    Assigns a discrete community_id to each node based on network topology.
    Runs in pure Python without requiring Neo4j GDS or heavy libraries.
    """
    if not nodes:
        return {}

    node_ids = [str(n.get("id")) for n in nodes if n.get("id")]
    if not node_ids:
        return {}

    labels: dict[str, int] = {node_id: idx for idx, node_id in enumerate(node_ids)}

    adj: dict[str, list[str]] = defaultdict(list)
    for edge in edges:
        s = str(edge.get("source"))
        t = str(edge.get("target"))
        if s in labels and t in labels and s != t:
            adj[s].append(t)
            adj[t].append(s)

    for _ in range(max_iterations):
        changed = False
        for node in node_ids:
            neighbors = adj.get(node, [])
            if not neighbors:
                continue

            counts: dict[int, int] = defaultdict(int)
            for neighbor in neighbors:
                counts[labels[neighbor]] += 1

            max_count = max(counts.values())
            best_labels = [lbl for lbl, count in counts.items() if count == max_count]
            best_label = min(best_labels)

            if labels[node] != best_label:
                labels[node] = best_label
                changed = True

        if not changed:
            break

    unique_labels = sorted(set(labels.values()))
    label_map = {lbl: idx for idx, lbl in enumerate(unique_labels)}
    return {node_id: label_map[lbl] for node_id, lbl in labels.items()}
