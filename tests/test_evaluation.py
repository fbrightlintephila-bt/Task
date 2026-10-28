import pytest
from evaluator import DEFAULT_RUBRIC, EvaluationValidationError, validate_report, validate_rubric


def report(score=90):
    return {
        "overall_score": score, "summary": "Reviewed against the rubric.",
        "completed_requirements": ["Input collected"], "partially_completed_requirements": [],
        "missing_requirements": [], "mistakes": [],
        "output_comparison": {"expected_output": None, "actual_output": None,
                              "comparison_verified": False, "explanation": "No execution performed."},
        "criteria_scores": [{"name": "Requirements", "score": 40, "maximum": 40}],
        "strengths": [], "improvement_suggestions": [], "next_steps": [],
    }


@pytest.mark.parametrize("score,expected", [(0, False), (45, False), (89, False), (90, True), (95, True), (100, True)])
def test_score_threshold_is_inclusive(score, expected):
    result = validate_report(report(score), DEFAULT_RUBRIC, 90)
    assert (result["evaluation_status"] == "passed") is expected
    assert result["resubmission_required"] is (not expected)


def test_rejects_invalid_score_and_missing_fields():
    with pytest.raises(EvaluationValidationError):
        validate_report(report(101), DEFAULT_RUBRIC, 90)
    with pytest.raises(EvaluationValidationError):
        validate_report({"overall_score": 50}, DEFAULT_RUBRIC, 90)


def test_rubric_weights_are_validated():
    assert sum(validate_rubric({"A": 60, "B": 40}).values()) == 100
    with pytest.raises(EvaluationValidationError):
        validate_rubric({"A": -1})


def test_unverified_output_is_not_promoted_to_verified():
    result = validate_report(report(87), DEFAULT_RUBRIC, 90)
    assert result["output_comparison"]["comparison_verified"] is False
