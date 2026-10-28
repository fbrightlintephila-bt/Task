import json
from typing import Any

DEFAULT_RUBRIC = {
    "Requirement completion": 40,
    "Logic and correctness": 30,
    "Output accuracy": 15,
    "Code quality and readability": 10,
    "Error handling and edge cases": 5,
}


class EvaluationValidationError(ValueError):
    pass


def validate_rubric(rubric: dict[str, Any]) -> dict[str, float]:
    if not isinstance(rubric, dict) or not rubric:
        raise EvaluationValidationError("Rubric must be a non-empty object.")
    validated = {}
    for name, weight in rubric.items():
        if not isinstance(name, str) or not name.strip() or isinstance(weight, bool):
            raise EvaluationValidationError("Rubric names and weights must be valid.")
        try:
            value = float(weight)
        except (TypeError, ValueError) as exc:
            raise EvaluationValidationError("Rubric weights must be numeric.") from exc
        if value < 0:
            raise EvaluationValidationError("Rubric weights cannot be negative.")
        validated[name.strip()] = value
    if sum(validated.values()) <= 0:
        raise EvaluationValidationError("Rubric must have a positive total weight.")
    return validated


def validate_report(report: Any, rubric: dict[str, Any], passing_score: float) -> dict[str, Any]:
    if isinstance(report, str):
        try:
            report = json.loads(report)
        except json.JSONDecodeError as exc:
            raise EvaluationValidationError("AI returned invalid JSON.") from exc
    if not isinstance(report, dict):
        raise EvaluationValidationError("Evaluation must be a JSON object.")
    required = ("overall_score", "summary", "completed_requirements", "partially_completed_requirements",
                "missing_requirements", "mistakes", "output_comparison", "criteria_scores",
                "strengths", "improvement_suggestions", "next_steps")
    missing = [key for key in required if key not in report]
    if missing:
        raise EvaluationValidationError("Evaluation is missing required fields: " + ", ".join(missing))
    try:
        score = float(report["overall_score"])
    except (TypeError, ValueError) as exc:
        raise EvaluationValidationError("Overall score must be numeric.") from exc
    if not 0 <= score <= 100:
        raise EvaluationValidationError("Overall score must be between 0 and 100.")
    for key in ("completed_requirements", "partially_completed_requirements", "missing_requirements",
                "mistakes", "criteria_scores", "strengths", "improvement_suggestions", "next_steps"):
        if not isinstance(report[key], list):
            raise EvaluationValidationError(f"{key} must be a list.")
    if not isinstance(report["output_comparison"], dict):
        raise EvaluationValidationError("output_comparison must be an object.")
    criteria = report["criteria_scores"]
    rubric_weights = validate_rubric(rubric)
    if criteria:
        total_awarded = 0.0
        for criterion in criteria:
            if not isinstance(criterion, dict) or "name" not in criterion or "score" not in criterion:
                raise EvaluationValidationError("Each criterion score needs a name and score.")
            try:
                value = float(criterion["score"])
            except (TypeError, ValueError) as exc:
                raise EvaluationValidationError("Criterion scores must be numeric.") from exc
            maximum = float(criterion.get("maximum", rubric_weights.get(criterion["name"], 0)))
            if maximum < 0 or value < 0 or value > maximum:
                raise EvaluationValidationError("Criterion score exceeds its permitted marks.")
            total_awarded += value
        if total_awarded > 100:
            raise EvaluationValidationError("Criterion totals cannot exceed 100.")
    report["overall_score"] = round(score, 2)
    report["maximum_score"] = 100
    report["passing_score"] = float(passing_score)
    report["evaluation_status"] = "passed" if score >= passing_score else "needs_improvement"
    report["task_status"] = "completed" if score >= passing_score else "resubmission_required"
    report["resubmission_required"] = score < passing_score
    report.setdefault("output_comparison", {}).setdefault("comparison_verified", False)
    report["output_comparison"]["comparison_verified"] = bool(
        report["output_comparison"].get("comparison_verified", False)
    )
    return report
