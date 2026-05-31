# -*- coding: utf-8 -*-

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REQUIRED_QUESTION_FIELDS = {
    "id",
    "question",
    "expected_route",
    "expected_answer_mode",
    "expected_doc_types",
    "gold_sources",
    "reference_answer",
    "notes",
}

REQUIRED_EVIDENCE_FIELDS = {
    "question_id",
    "source",
    "doc_type",
    "section",
    "must_contain_any",
    "evidence_note",
}


class TestRetrievalEvalSchema(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.questions_path = ROOT / "eval" / "golden_questions.jsonl"
        cls.evidence_path = ROOT / "eval" / "gold_evidence.jsonl"
        cls.questions = cls._load(cls.questions_path)
        cls.evidence = cls._load(cls.evidence_path)

    @staticmethod
    def _load(path: Path) -> list[dict]:
        rows: list[dict] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
        return rows

    def test_golden_questions_count_at_least_20(self) -> None:
        self.assertGreaterEqual(len(self.questions), 20)

    def test_golden_questions_schema_complete(self) -> None:
        ids: set[str] = set()
        for row in self.questions:
            missing = REQUIRED_QUESTION_FIELDS - set(row.keys())
            self.assertFalse(missing, f"{row.get('id')} missing {missing}")
            self.assertTrue(row.get("gold_sources"), f"{row.get('id')} gold_sources empty")
            qid = str(row["id"])
            self.assertNotIn(qid, ids, f"duplicate id {qid}")
            ids.add(qid)

    def test_gold_evidence_schema_complete(self) -> None:
        qids = {str(q["id"]) for q in self.questions}
        for row in self.evidence:
            missing = REQUIRED_EVIDENCE_FIELDS - set(row.keys())
            self.assertFalse(missing, f"{row.get('question_id')} missing {missing}")
            self.assertIn(str(row["question_id"]), qids)
            self.assertTrue(row.get("must_contain_any"), "must_contain_any should not be empty")

    def test_question_type_coverage(self) -> None:
        notes = " ".join(str(q.get("notes") or "") for q in self.questions)
        for tag in (
            "[paper-only]",
            "[paper-comparison]",
            "[sop-only]",
            "[hybrid]",
            "[missing-evidence]",
            "[ambiguous-anchor]",
        ):
            self.assertIn(tag, notes, f"missing category tag {tag}")


if __name__ == "__main__":
    unittest.main()
