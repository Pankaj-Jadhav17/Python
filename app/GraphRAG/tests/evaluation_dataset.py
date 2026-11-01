"""
Evaluation benchmark dataset for GraphRAG entity resolution, structured extraction,
multi-evidence preservation, and graph integrity.
"""

ENTITY_RESOLUTION_CASES = [
    # Exact duplicate mentions
    {
        "mention": "Mitochondria",
        "target": "mitochondria",
        "entity_type": "BiologicalEntity",
        "collection_id": "biology",
        "expected_merge": True,
        "category": "exact_casing",
    },
    {
        "mention": "mitochondria",
        "target": "mitochondria",
        "entity_type": "BiologicalEntity",
        "collection_id": "biology",
        "expected_merge": True,
        "category": "exact_casing",
    },
    # True domain aliases
    {
        "mention": "ATP",
        "target": "adenosine triphosphate",
        "entity_type": "ChemicalEntity",
        "collection_id": "biology",
        "expected_merge": True,
        "category": "alias",
    },
    {
        "mention": "DNA",
        "target": "deoxyribonucleic acid",
        "entity_type": "BiologicalEntity",
        "collection_id": "biology",
        "expected_merge": True,
        "category": "alias",
    },
    {
        "mention": "chondriosome",
        "target": "mitochondria",
        "entity_type": "BiologicalEntity",
        "collection_id": "biology",
        "expected_merge": True,
        "category": "alias",
    },
    # Similar names for different entities (Must NOT merge!)
    {
        "mention": "RNA polymerase I",
        "target": "RNA polymerase II",
        "entity_type": "BiologicalEntity",
        "collection_id": "biology",
        "expected_merge": False,
        "category": "similar_names_different_entities",
    },
    {
        "mention": "microspore",
        "target": "microsporangium",
        "entity_type": "BiologicalEntity",
        "collection_id": "biology",
        "expected_merge": False,
        "category": "similar_names_different_entities",
    },
    # Homonyms: Identical names with completely different meanings / types (Must NOT merge!)
    {
        "mention": "Apple",
        "target": "Apple",
        "entity_type": "Organization",
        "target_type": "BiologicalEntity",
        "collection_id": "general",
        "expected_merge": False,
        "category": "homonym_type_conflict",
    },
    {
        "mention": "Python",
        "target": "Python",
        "entity_type": "Method",
        "target_type": "BiologicalEntity",
        "collection_id": "general",
        "expected_merge": False,
        "category": "homonym_type_conflict",
    },
    # Cross-collection separation (Must NOT merge across collections!)
    {
        "mention": "Cell",
        "target": "Cell",
        "entity_type": "BiologicalEntity",
        "collection_id": "telecom",
        "target_collection_id": "biology",
        "expected_merge": False,
        "category": "cross_collection",
    },
]

RELATIONSHIP_EXTRACTION_CASES = [
    # Valid multi-relationship passage with shared subject
    {
        "text": "Mitochondria produce ATP and contain their own DNA.",
        "expected_triples": [
            {"subject": "mitochondria", "relation": "produces", "object": "atp", "polarity": "positive"},
            {"subject": "mitochondria", "relation": "contains", "object": "dna", "polarity": "positive"},
        ],
        "category": "multi_rel_shared_subject",
    },
    # Negated claim (Should be detected as negative polarity, not asserted as positive fact)
    {
        "text": "Mature red blood cells do not contain mitochondria.",
        "expected_negative": True,
        "category": "negation",
    },
    # Unsupported hallucinated relation (Evidence missing or mismatch)
    {
        "text": "The nucleus is surrounded by a double membrane.",
        "candidate": {
            "subject": "nucleus",
            "relation": "produces",
            "object": "atp",
            "evidence": "The nucleus is surrounded by a double membrane.",
            "confidence": 0.9,
        },
        "should_validate": False,
        "category": "unsupported_candidate",
    },
    # Directionality correctness
    {
        "text": "Microspores develop into pollen grains.",
        "candidate_correct": {
            "subject": "microspore",
            "relation": "develops into",
            "object": "pollen grain",
            "evidence": "Microspores develop into pollen grains.",
            "confidence": 0.9,
        },
        "candidate_reversed": {
            "subject": "pollen grain",
            "relation": "develops into",
            "object": "microspore",
            "evidence": "Microspores develop into pollen grains.",
            "confidence": 0.9,
        },
        "category": "directionality",
    },
]
