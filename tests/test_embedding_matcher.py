# -*- coding: utf-8 -*-
"""
tests/test_embedding_matcher.py
Unit tests for the semantic embedding matcher, including cosine similarity and score merging.
"""
import sys
import os
import unittest
import tempfile
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.matching.embedding_matcher import (
    cosine_similarity,
    build_index,
    load_index,
    query_index,
    merge_candidate_lists,
)

class TestEmbeddingMatcher(unittest.TestCase):

    def test_cosine_similarity(self):
        v1 = [1.0, 0.0, 0.0]
        v2 = [1.0, 0.0, 0.0]
        self.assertAlmostEqual(cosine_similarity(v1, v2), 1.0)

        v3 = [0.0, 1.0, 0.0]
        self.assertAlmostEqual(cosine_similarity(v1, v3), 0.0)

        v4 = [1.0, 1.0, 0.0]
        # cosine similarity between [1,0,0] and [1,1,0] should be 1 / sqrt(2)
        self.assertAlmostEqual(cosine_similarity(v1, v4), 2**-0.5)

    @patch("src.matching.embedding_matcher.fetch_embedding_ollama")
    def test_build_and_load_index(self, mock_fetch):
        # Setup mock embeddings vectors
        mock_fetch.side_effect = lambda text, url, model, is_query: [0.1, 0.2, 0.3]

        candidates = [
            ("abamectin", "Abamectin", {"substance_id": "1"}),
            ("chlorpyrifos", "Chlorpyrifos", {"substance_id": "2"}),
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            index_path = os.path.join(tmpdir, "test_index.pkl")
            index = build_index(
                candidates,
                index_path,
                ollama_url="http://localhost:11434",
                model="nomic-embed-text"
            )

            self.assertIsNotNone(index)
            self.assertEqual(len(index["embeddings"]), 2)
            self.assertEqual(index["embeddings"][0]["display_name"], "Abamectin")
            self.assertEqual(index["embeddings"][0]["embedding"], [0.1, 0.2, 0.3])

            # Test loading index
            loaded = load_index(index_path)
            self.assertIsNotNone(loaded)
            self.assertEqual(len(loaded["embeddings"]), 2)

    def test_merge_candidate_lists(self):
        fuzzy = [
            ("Chlorpyrifos", 80, {"id": 1}),
            ("Deltamethrin", 90, {"id": 2}),
        ]
        # Semantic scores range 0..1.0
        semantic = [
            ("Chlorpyrifos", 0.85, {"id": 1}),
            ("Cypermethrin", 0.75, {"id": 3}),
        ]

        merged = merge_candidate_lists(fuzzy, semantic, top_k=5)
        
        # Deduplicated display names
        names = [item[0] for item in merged]
        self.assertIn("Chlorpyrifos", names)
        self.assertIn("Deltamethrin", names)
        self.assertIn("Cypermethrin", names)
        self.assertEqual(len(names), 3)

        # "Chlorpyrifos" is in both lists, so it should receive a boost
        # Combined score calculation: max(80, 85) * 0.7 + min(80, 85) * 0.3 + 5 = 85*0.7 + 80*0.3 + 5 = 59.5 + 24 + 5 = 88.5
        chlor_item = [x for x in merged if x[0] == "Chlorpyrifos"][0]
        self.assertEqual(chlor_item[1], 88.5)

if __name__ == "__main__":
    unittest.main()
