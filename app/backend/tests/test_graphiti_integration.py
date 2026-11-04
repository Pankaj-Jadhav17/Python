from __future__ import annotations

import asyncio
from datetime import datetime
from types import SimpleNamespace

from GraphRAG.graphiti_integration import GraphitiAdapter, normalize_group_id


class FakeGraphiti:
    def __init__(self):
        self.calls = []

    def add_episode(self, name, episode_body, source_description, reference_time, source=None, group_id=None, uuid=None, **kwargs):
        self.calls.append(
            {
                "name": name,
                "episode_body": episode_body,
                "source_description": source_description,
                "reference_time": reference_time,
                "group_id": group_id,
                "source": source,
                "uuid": uuid,
            }
        )
        return SimpleNamespace(node=SimpleNamespace(uuid="episode-1"))

    def search(self, query, *, group_ids=None, num_results=10, **kwargs):
        return []

    def search_(self, query, *, group_ids=None, config=None, **kwargs):
        self.calls.append({"kind": "search_", "query": query, "group_ids": group_ids, "config": config})
        return SimpleNamespace(edges=[], nodes=[], episodes=[])


def test_graphiti_group_id_is_collection_scoped_and_stable():
    assert normalize_group_id("Sales Team") == "sales_team"
    assert normalize_group_id("sales-team") == "sales-team"


def test_graphiti_adapter_ingests_chunks_as_grouped_episodes():
    fake_graphiti = FakeGraphiti()
    adapter = GraphitiAdapter(graphiti=fake_graphiti)

    result = adapter.ingest_document_text(
        "Three Laws.txt",
        "A robot is a machine.\nA machine obeys a law.",
        collection_id="robotics",
    )

    assert result["collection_id"] == "robotics"
    assert result["passages"] >= 1
    assert fake_graphiti.calls
    assert fake_graphiti.calls[0]["group_id"] == "robotics"
    assert "Three Laws.txt" in fake_graphiti.calls[0]["source_description"]


def test_graphiti_adapter_search_uses_search_config_limit():
    fake_graphiti = FakeGraphiti()
    adapter = GraphitiAdapter(graphiti=fake_graphiti)

    asyncio.run(adapter.search_async("what is robotics?", collection_id="robotics", limit=7))

    assert fake_graphiti.calls[-1]["kind"] == "search_"
    assert fake_graphiti.calls[-1]["config"] is not None
    assert fake_graphiti.calls[-1]["config"].limit == 7
    assert fake_graphiti.calls[-1]["group_ids"] == ["robotics"]
