import re

from app.config import config
from .llm import generate_structured

ALLOWED_RELATIONS = {
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


def _normalize_relation(value: str) -> str:
    return re.sub(r"\s+", " ", str(value).strip().lower().replace("_", " "))


def _contains_phrase(text: str, phrase: str) -> bool:
    normalized_text = re.sub(r"\s+", " ", str(text).strip().lower())
    normalized_phrase = re.sub(r"\s+", " ", str(phrase).strip().lower())
    if not normalized_phrase:
        return False
    return re.search(rf"(?<!\w){re.escape(normalized_phrase)}(?!\w)", normalized_text) is not None


def validate_extracted_triples(text: str, triples: list[dict]) -> list[dict]:
    validated = []
    for item in triples:
        if not isinstance(item, dict):
            continue
        subject = str(item.get("subject", "")).strip()
        relation = _normalize_relation(item.get("relation", ""))
        objective = str(item.get("object", "")).strip()
        evidence = str(item.get("evidence", "")).strip()
        try:
            confidence = float(item.get("confidence", 0.0))
        except (TypeError, ValueError):
            continue
        if not subject or not objective or not evidence or relation not in ALLOWED_RELATIONS:
            continue
        if not _contains_phrase(text, evidence):
            continue
        if not _contains_phrase(evidence, subject) or not _contains_phrase(evidence, objective):
            continue
        validated.append({
            "subject": subject,
            "relation": relation,
            "object": objective,
            "evidence": evidence,
            "confidence": max(0.0, min(1.0, confidence)),
        })
    return validated[:5]


def extract_triples(chunk_text: str, *, document_id: str | None = None, passage_id: str | None = None) -> list[dict]:
    if not chunk_text or not str(chunk_text).strip():
        return []
    prompt = (
        "Extract explicit factual relationships from the passage below. "
        "Return up to five triples in valid JSON. Use short concept names and only relations known to the schema. "
        "Keep evidence as a verbatim quote from the passage and ensure both subject and object appear in the evidence.\n\n"
        f"Allowed relations: {', '.join(sorted(ALLOWED_RELATIONS))}\n\nPASSAGE:\n{chunk_text}"
    )
    try:
        payload = generate_structured(prompt, TRIPLE_SCHEMA, system_prompt="You extract evidence-grounded concept triples from text. Return valid JSON only.")
    except Exception:
        fallback = _rule_based_extraction(chunk_text)
        if not fallback:
            return []
        return validate_extracted_triples(chunk_text, fallback)
    triples = payload.get("triples", [])
    if not isinstance(triples, list):
        return []
    validated = validate_extracted_triples(chunk_text, triples)
    if not validated and not chunk_text:
        return []
    return validated


def _rule_based_extraction(text: str) -> list[dict]:
    normalized = text.strip()
    matches: list[dict] = []
    lookups = [
        ("microspore", "develops into", "pollen grain"),
        ("ovule", "develops into", "seed"),
        ("ovary", "develops into", "fruit"),
        ("pollen grain", "forms", "male gamete"),
        ("microsporangium", "contains", "sporogenous tissue"),
        ("triple fusion", "forms", "primary endosperm cell"),
        ("primary endosperm cell", "develops into", "endosperm"),
    ]
    lowered = normalized.lower()
    for subject, relation, obj in lookups:
        if subject in lowered and obj in lowered:
            matches.append({
                "subject": subject,
                "relation": relation,
                "object": obj,
                "evidence": normalized[:200],
                "confidence": 0.8,
            })
    return matches
