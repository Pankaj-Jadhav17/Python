from __future__ import annotations

import pytest
from GraphRAG.entity_resolution import EntityResolver, normalize_entity_name
from GraphRAG.extractor import detect_negation, extract_triples, validate_extracted_triples
from GraphRAG.tests.evaluation_dataset import ENTITY_RESOLUTION_CASES, RELATIONSHIP_EXTRACTION_CASES


def test_entity_resolution_metrics():
    """
    Evaluate entity resolution performance:
    Precision, Recall, F1, False-merge rate, and False-split rate.
    """
    tp = 0
    fp = 0
    tn = 0
    fn = 0

    for case in ENTITY_RESOLUTION_CASES:
        col_id = case.get("collection_id", "biology")
        target_col = case.get("target_collection_id", col_id)

        resolver = EntityResolver(collection_id=col_id)
        target_target = case["target"]
        target_type = case.get("target_type", case["entity_type"])
        target_id = f"c:{target_col}:{target_target.lower().replace(' ', '_')}"

        # Register target in the respective collection
        if col_id == target_col:
            resolver.register_existing_entity(
                canonical_id=target_id,
                canonical_name=target_target,
                entity_type=target_type,
            )
        else:
            # Different collection resolver
            other_resolver = EntityResolver(collection_id=target_col)
            other_resolver.register_existing_entity(
                canonical_id=target_id,
                canonical_name=target_target,
                entity_type=target_type,
            )

        resolved = resolver.resolve_mention(case["mention"], entity_type=case["entity_type"])
        actual_merge = (resolved.canonical_id == target_id)
        expected_merge = case["expected_merge"]

        if expected_merge and actual_merge:
            tp += 1
        elif not expected_merge and actual_merge:
            fp += 1
        elif not expected_merge and not actual_merge:
            tn += 1
        elif expected_merge and not actual_merge:
            fn += 1

    precision = tp / max(1, tp + fp)
    recall = tp / max(1, tp + fn)
    f1 = (2 * precision * recall) / max(1e-9, precision + recall)
    false_merge_rate = fp / max(1, fp + tn)
    false_split_rate = fn / max(1, tp + fn)

    print("\n--- ENTITY RESOLUTION EVALUATION METRICS ---")
    print(f"Total Test Cases: {len(ENTITY_RESOLUTION_CASES)}")
    print(f"True Positives: {tp}, False Positives: {fp}, True Negatives: {tn}, False Negatives: {fn}")
    print(f"Pairwise Precision: {precision:.4f}")
    print(f"Pairwise Recall:    {recall:.4f}")
    print(f"Pairwise F1 Score:  {f1:.4f}")
    print(f"False-Merge Rate:   {false_merge_rate:.4f}")
    print(f"False-Split Rate:   {false_split_rate:.4f}")

    assert precision == 1.0, f"Precision was {precision}"
    assert recall == 1.0, f"Recall was {recall}"
    assert f1 == 1.0, f"F1 score was {f1}"
    assert false_merge_rate == 0.0, f"False merge rate was {false_merge_rate}"
    assert false_split_rate == 0.0, f"False split rate was {false_split_rate}"


def test_relationship_extraction_and_negation_metrics():
    """
    Evaluate relationship extraction, negation detection, and candidate filtering.
    """
    # 1. Multi-relationship extraction from single chunk
    multi_case = RELATIONSHIP_EXTRACTION_CASES[0]
    extracted = extract_triples(multi_case["text"])
    assert len(extracted) >= 2, f"Expected at least 2 triples, got {len(extracted)}"
    subjects = {item["subject"].lower() for item in extracted}
    assert "mitochondria" in subjects

    # 2. Negation detection
    neg_case = RELATIONSHIP_EXTRACTION_CASES[1]
    polarity = detect_negation(neg_case["text"])
    assert polarity == "negative", f"Expected negative polarity for: {neg_case['text']}"

    # 3. Unsupported candidate rejection
    unsupported_case = RELATIONSHIP_EXTRACTION_CASES[2]
    val_res = validate_extracted_triples(
        unsupported_case["text"],
        [unsupported_case["candidate"]],
    )
    assert len(val_res) == 0, "Unsupported candidate should have been rejected."

    # 4. Directionality verification
    dir_case = RELATIONSHIP_EXTRACTION_CASES[3]
    correct_val = validate_extracted_triples(dir_case["text"], [dir_case["candidate_correct"]])
    assert len(correct_val) == 1
    assert correct_val[0]["subject"].lower() == "microspore"
    assert correct_val[0]["object"].lower() == "pollen grain"
