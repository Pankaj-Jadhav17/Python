from __future__ import annotations

import re
import unicodedata
from typing import Any

from app.config import config
from .llm import generate_structured
from .models.graph_models import EntityMention, RelationshipCandidate

ENTITY_TAXONOMY: dict[str, str] = {
    "Concept": "General conceptual entity, theory, or abstract idea.",
    "BiologicalEntity": "Organism, organ, cell, organelle, tissue, biological structure, or molecule.",
    "ChemicalEntity": "Chemical element, compound, molecule, hormone, or mineral.",
    "Process": "Biological, chemical, or physical process, pathway, or cycle.",
    "Organization": "Institution, company, university, agency, or consortium.",
    "Person": "Scientist, researcher, historical figure, or individual.",
    "Location": "Physical, geographical, cellular, or anatomical compartment.",
    "Method": "Algorithm, technique, protocol, formula, or mathematical method.",
}

ALLOWED_ENTITY_TYPES: set[str] = set(ENTITY_TAXONOMY.keys())

ALLOWED_RELATIONS: set[str] = {
    "associated with",
    "contains",
    "contributes to",
    "develops into",
    "enables",
    "forms",
    "fuses with",
    "inhibits",
    "is a stage of",
    "is part of",
    "is the site of",
    "leads to",
    "matures into",
    "nourishes",
    "occurs in",
    "participates in",
    "pollinates",
    "produces",
    "produces without fertilisation",
    "releases",
    "represents",
    "requires",
    "supports",
    "undergoes",
}

STRUCTURED_EXTRACTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "entities": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "mention": {"type": "string"},
                    "entity_type": {"type": "string"},
                },
                "required": ["mention", "entity_type"],
                "additionalProperties": False,
            },
        },
        "relationships": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "subject": {"type": "string"},
                    "predicate": {"type": "string"},
                    "object": {"type": "string"},
                    "evidence": {"type": "string"},
                    "polarity": {"type": "string"},
                    "confidence": {"type": "number"},
                },
                "required": ["subject", "predicate", "object", "evidence", "confidence"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["entities", "relationships"],
    "additionalProperties": False,
}

# Legacy fallback schema
TRIPLE_SCHEMA = {
    "type": "object",
    "properties": {
        "triples": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "subject": {"type": "string"},
                    "relation": {"type": "string"},
                    "object": {"type": "string"},
                    "evidence": {"type": "string"},
                    "confidence": {"type": "number"},
                },
                "required": ["subject", "relation", "object", "evidence", "confidence"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["triples"],
    "additionalProperties": False,
}

NEGATION_PATTERNS = [
    r"\bnot\b",
    r"\bnever\b",
    r"\bneither\b",
    r"\bnor\b",
    r"\bdoes not\b",
    r"\bdo not\b",
    r"\bcannot\b",
    r"\bfailed to\b",
    r"\bfails to\b",
    r"\bno longer\b",
    r"\bunable to\b",
    r"\bwithout\b",
]


def normalize_predicate(value: str) -> str:
    """Normalize predicate name to standard lowercased format."""
    return re.sub(r"[\s_]+", " ", str(value).strip().lower())


def validate_entity_type(raw_type: str | None) -> str:
    """Validate entity type against the taxonomy, defaulting to Concept."""
    if not raw_type:
        return "Concept"
    clean_type = str(raw_type).strip()
    # Normalize common variations
    type_map = {
        "biological_entity": "BiologicalEntity",
        "biological": "BiologicalEntity",
        "biology": "BiologicalEntity",
        "chemical_entity": "ChemicalEntity",
        "chemical": "ChemicalEntity",
        "chemistry": "ChemicalEntity",
        "process": "Process",
        "concept": "Concept",
        "organization": "Organization",
        "org": "Organization",
        "person": "Person",
        "location": "Location",
        "method": "Method",
        "technique": "Method",
    }
    normalized = type_map.get(clean_type.lower(), clean_type)
    return normalized if normalized in ALLOWED_ENTITY_TYPES else "Concept"


def contains_phrase(text: str, phrase: str) -> bool:
    """Check if phrase occurs in text, tolerating whitespace and punctuation variations."""
    if not text or not phrase:
        return False
    norm_text = re.sub(r"\s+", " ", unicodedata.normalize("NFKC", str(text)).strip().lower())
    norm_phrase = re.sub(r"\s+", " ", unicodedata.normalize("NFKC", str(phrase)).strip().lower())
    if not norm_phrase:
        return False
    # Direct substring or regex boundary match
    if norm_phrase in norm_text:
        return True
    pattern = rf"(?<!\w){re.escape(norm_phrase)}(?!\w)"
    return re.search(pattern, norm_text) is not None


def detect_negation(evidence: str) -> str:
    """Check if evidence text contains explicit negation markers."""
    evidence_lower = evidence.lower()
    for pattern in NEGATION_PATTERNS:
        # Don't falsely flag 'produces without fertilisation'
        if "without fertilisation" in evidence_lower or "without fertilization" in evidence_lower:
            continue
        if re.search(pattern, evidence_lower):
            return "negative"
    return "positive"


def validate_extracted_triples(
    text: str,
    triples: list[dict[str, Any]],
    *,
    entity_type_map: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Validate candidate relationship triples against the source text and allowed relations."""
    validated: list[dict[str, Any]] = []
    type_map = entity_type_map or {}

    sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+", str(text).strip()) if part.strip()]

    def find_supporting_evidence(subject: str, obj: str, relation: str) -> str:
        if not subject or not obj:
            return ""
        for sentence in sentences:
            sentence_lower = sentence.lower()
            if relation.lower() not in sentence_lower:
                continue
            if contains_phrase(sentence, subject) and contains_phrase(sentence, obj):
                return sentence
            if (contains_phrase(sentence, subject) or contains_phrase(text, subject)) and (
                contains_phrase(sentence, obj) or contains_phrase(text, obj)
            ):
                return sentence
        if relation.lower() in text.lower() and contains_phrase(text, subject) and contains_phrase(text, obj):
            return text.strip()
        return ""

    for item in triples:
        if not isinstance(item, dict):
            continue

        subject = str(item.get("subject", "")).strip()
        raw_rel = item.get("relation") or item.get("predicate", "")
        relation = normalize_predicate(raw_rel)
        obj = str(item.get("object", "")).strip()
        evidence = str(item.get("evidence", "")).strip()

        try:
            confidence = float(item.get("confidence", 0.0))
        except (TypeError, ValueError):
            continue

        if not subject or not obj or relation not in ALLOWED_RELATIONS:
            continue

        if subject.lower() == obj.lower():
            continue

        supporting_evidence = evidence if evidence and contains_phrase(text, evidence) else find_supporting_evidence(subject, obj, relation)
        if not supporting_evidence:
            continue

        if not contains_phrase(supporting_evidence, subject) and not contains_phrase(text, subject):
            continue
        if not contains_phrase(supporting_evidence, obj) and not contains_phrase(text, obj):
            continue

        polarity = item.get("polarity") or detect_negation(supporting_evidence)
        subj_type = validate_entity_type(item.get("subject_type") or type_map.get(subject.lower()))
        obj_type = validate_entity_type(item.get("object_type") or type_map.get(obj.lower()))

        validated.append({
            "subject": subject,
            "subject_type": subj_type,
            "relation": relation,
            "predicate": relation,
            "object": obj,
            "object_type": obj_type,
            "evidence": supporting_evidence,
            "confidence": max(0.0, min(1.0, confidence)),
            "polarity": polarity,
            "status": "verified" if polarity == "positive" else "needs_review",
        })

    return validated[:10]


def extract_triples(
    chunk_text: str,
    *,
    document_id: str | None = None,
    passage_id: str | None = None,
) -> list[dict[str, Any]]:
    """
    Extract structured entity mentions and relationship candidates from a text chunk.
    Returns a validated list of relationship candidates.
    """
    if not chunk_text or not str(chunk_text).strip():
        return []

    prompt = (
        "Extract explicit factual entities and relationships from the passage below.\n"
        f"Allowed relations: {', '.join(sorted(ALLOWED_RELATIONS))}\n"
        f"Allowed entity types: {', '.join(sorted(ALLOWED_ENTITY_TYPES))}\n\n"
        "Instructions:\n"
        "1. Extract concise entity mentions and assign each a valid entity_type.\n"
        "2. Extract factual relationships between entities. Only use relations from the allowed list.\n"
        "3. Provide evidence as a verbatim quote from the passage containing both the subject and object.\n"
        "4. Note polarity as 'positive' or 'negative'.\n"
        "5. Return valid JSON adhering strictly to the schema.\n\n"
        f"PASSAGE:\n{chunk_text}"
    )

    try:
        payload = generate_structured(
            prompt,
            STRUCTURED_EXTRACTION_SCHEMA,
            system_prompt="You extract evidence-grounded typed entities and relations from text. Return valid JSON only.",
        )
    except Exception:
        # Fallback to rule-based extraction
        fallback = _rule_based_extraction(chunk_text)
        if not fallback:
            return []
        return validate_extracted_triples(chunk_text, fallback)

    entities = payload.get("entities", [])
    relationships = payload.get("relationships", [])

    # Support legacy response key if returned
    if not relationships and "triples" in payload:
        relationships = payload.get("triples", [])

    if not isinstance(relationships, list):
        return []

    entity_type_map: dict[str, str] = {}
    if isinstance(entities, list):
        for ent in entities:
            if isinstance(ent, dict) and "mention" in ent:
                mention = str(ent.get("mention", "")).strip().lower()
                ent_type = validate_entity_type(ent.get("entity_type"))
                if mention:
                    entity_type_map[mention] = ent_type

    validated = validate_extracted_triples(
        chunk_text,
        relationships,
        entity_type_map=entity_type_map,
    )

    # If LLM returned empty or was rejected, try fallback rules
    if not validated:
        fallback = _rule_based_extraction(chunk_text)
        if fallback:
            return validate_extracted_triples(chunk_text, fallback, entity_type_map=entity_type_map)

    return validated


def _rule_based_extraction(text: str) -> list[dict[str, Any]]:
    """Rule-based extractor for common biological and general concepts."""
    normalized = text.strip()
    lowered = normalized.lower()
    matches: list[dict[str, Any]] = []

    lookups = [
        ("microspore", "BiologicalEntity", "develops into", "pollen grain", "BiologicalEntity"),
        ("ovule", "BiologicalEntity", "develops into", "seed", "BiologicalEntity"),
        ("ovary", "BiologicalEntity", "develops into", "fruit", "BiologicalEntity"),
        ("pollen grain", "BiologicalEntity", "forms", "male gamete", "BiologicalEntity"),
        ("microsporangium", "BiologicalEntity", "contains", "sporogenous tissue", "BiologicalEntity"),
        ("triple fusion", "Process", "forms", "primary endosperm cell", "BiologicalEntity"),
        ("primary endosperm cell", "BiologicalEntity", "develops into", "endosperm", "BiologicalEntity"),
        ("mitochondria", "BiologicalEntity", "produces", "ATP", "ChemicalEntity"),
        ("mitochondria", "BiologicalEntity", "contains", "DNA", "BiologicalEntity"),
        ("mitochondria", "BiologicalEntity", "participates in", "cellular respiration", "Process"),
        ("cellular respiration", "Process", "produces", "ATP", "ChemicalEntity"),
        ("cells", "BiologicalEntity", "contain", "mitochondria", "BiologicalEntity"),
        ("cell", "BiologicalEntity", "contains", "mitochondria", "BiologicalEntity"),
        ("chloroplast", "BiologicalEntity", "participates in", "photosynthesis", "Process"),
        ("photosynthesis", "Process", "produces", "glucose", "ChemicalEntity"),
    ]

    for subj, subj_type, rel, obj, obj_type in lookups:
        if subj.lower() in lowered and obj.lower() in lowered:
            sentences = re.split(r"(?<=[.!?])\s+", normalized)
            evidence = ""
            for sentence in sentences:
                s_low = sentence.lower()
                if subj.lower() in s_low and obj.lower() in s_low:
                    evidence = sentence.strip()
                    break

            if evidence:
                matches.append({
                    "subject": subj,
                    "subject_type": subj_type,
                    "relation": rel,
                    "predicate": rel,
                    "object": obj,
                    "object_type": obj_type,
                    "evidence": evidence,
                    "confidence": 0.85,
                    "polarity": "positive",
                })

    return matches
