import unittest
from unittest.mock import patch

from katala_web_research.evaluation import (
    build_eval_report,
    default_eval_cases,
    mrr_at_k,
    ndcg_at_k,
    recall_at_k,
    run_eval,
)

LABELS = {"a": 3, "b": 2, "c": 0}


class RankingMetricTests(unittest.TestCase):
    def test_ndcg_is_one_for_the_ideal_order_and_drops_when_grades_invert(self):
        self.assertAlmostEqual(ndcg_at_k(["a", "b", "c"], LABELS, 10), 1.0)
        self.assertLess(ndcg_at_k(["b", "a", "c"], LABELS, 10), 1.0)
        self.assertLess(ndcg_at_k(["c", "b", "a"], LABELS, 10), ndcg_at_k(["b", "a", "c"], LABELS, 10))

    def test_ndcg_separates_graded_relevance_not_just_relevant_or_not(self):
        # "b" is relevant too, so a binary metric would call both orders perfect.
        self.assertGreater(ndcg_at_k(["a", "b"], LABELS, 10), ndcg_at_k(["b", "a"], LABELS, 10))

    def test_recall_counts_labelled_relevants_missing_from_the_cut(self):
        self.assertAlmostEqual(recall_at_k(["a", "b"], LABELS, 5), 1.0)
        self.assertAlmostEqual(recall_at_k(["a"], LABELS, 5), 0.5)
        self.assertAlmostEqual(recall_at_k(["a", "b"], LABELS, 1), 0.5)
        self.assertAlmostEqual(recall_at_k(["c"], LABELS, 5), 0.0)

    def test_mrr_is_the_reciprocal_of_the_first_relevant_position(self):
        self.assertAlmostEqual(mrr_at_k(["a", "b"], LABELS, 5), 1.0)
        self.assertAlmostEqual(mrr_at_k(["c", "b"], LABELS, 5), 0.5)
        self.assertAlmostEqual(mrr_at_k(["c", "b"], LABELS, 1), 0.0)

    def test_unlabelled_documents_score_as_irrelevant(self):
        self.assertAlmostEqual(mrr_at_k(["unseen", "a"], LABELS, 5), 0.5)
        self.assertAlmostEqual(recall_at_k(["unseen"], LABELS, 5), 0.0)


class LabelledBenchmarkTests(unittest.TestCase):
    def test_every_default_case_carries_relevance_labels_for_its_candidates(self):
        for case in default_eval_cases():
            labelled = {url for url, _grade in case.relevance}
            self.assertEqual(
                labelled,
                {candidate.url for candidate in case.candidates},
                f"{case.name} has candidates without a relevance grade",
            )
            self.assertTrue(any(grade >= 1 for _url, grade in case.relevance), case.name)

    def test_summary_reports_retrieval_metrics_over_every_labelled_case(self):
        summary = run_eval(min_score=80)

        self.assertEqual(summary.retrieval["labeled_cases"], len(summary.cases))
        self.assertGreater(summary.retrieval["recall@5"], 0.0)
        self.assertGreater(summary.retrieval["mrr@5"], 0.0)
        self.assertLessEqual(summary.retrieval["ndcg@10"], 1.0)

    def test_ranking_beats_provider_order_and_the_gate_notices_when_it_does_not(self):
        summary = run_eval(min_score=80)
        self.assertGreater(summary.retrieval["ndcg@10"], summary.retrieval["baseline_ndcg@10"])
        self.assertTrue(summary.passed)

        with patch(
            "katala_web_research.evaluation.rank_results",
            lambda query, results: sorted(results, key=lambda item: item.rank),
        ):
            passthrough = run_eval(min_score=0)

        self.assertAlmostEqual(
            passthrough.retrieval["ndcg@10"], passthrough.retrieval["baseline_ndcg@10"]
        )
        self.assertLess(passthrough.retrieval["ndcg@10"], summary.retrieval["ndcg@10"])
        self.assertFalse(passthrough.passed)

    def test_report_records_the_retrieval_metrics(self):
        report = build_eval_report(run_eval(min_score=80))

        self.assertIn("Retrieval Metrics", report)
        self.assertIn("ndcg@10", report)
        self.assertIn("baseline_ndcg@10", report)


if __name__ == "__main__":
    unittest.main()
