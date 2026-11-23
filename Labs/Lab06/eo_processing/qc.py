"""Append scientific assessments without rewriting execution history."""
from . import database as db
from .common import canonical, now
from .planning import load_manifest
from .runner import result_evidence


def evaluate(metrics, minimum):
    if metrics["valid_pixels"] == 0:
        return "rejected", "No usable observations in the AOI"
    if metrics["valid_fraction"] < minimum:
        return "rejected", "Usable observation fraction below this assessment policy"
    if not metrics["cloud_screened"]:
        return "review", "Cloud screening was disabled for this diagnostic product"
    if metrics["outside_nominal_range"] / metrics["valid_pixels"] > 0.02:
        return "review", "More than two percent of observations fall outside the product's nominal range"
    return "accepted", "Meets the recorded automatic coverage and range checks; visual/scientific interpretation still required"


def assess(manifest_path, minimum=0.5):
    if not 0 <= minimum <= 1:
        raise ValueError("Minimum valid fraction must be between zero and one")
    manifest = load_manifest(manifest_path)
    results = []
    with db.writer_lock(manifest["runtime"]["database"]), db.connect(manifest["runtime"]["database"]) as c:
        for m in manifest["frozen"]["members"]:
            evidence, _ = result_evidence(c, m)
            if evidence is None:
                results.append({"member_id":m["member_id"],"assessment":"unavailable","reason":"No verified completed product"})
                continue
            metrics = evidence["receipt"]["metrics"]
            outcome, reason = evaluate(metrics, minimum)
            policy = {"minimum_valid_fraction":float(minimum),"outside_nominal_fraction_review":0.02,"require_cloud_screening":True}
            with c:
                cursor = c.execute("INSERT INTO scientific_qc_assessments(request_id,attempt_id,assessed_at,policy_version,policy_json,outcome,reason,metrics_json) VALUES (?,?,?,'coverage-range-v1',?,?,?,?)",
                                   (m["request_id"],evidence["attempt_id"],now(),canonical(policy),outcome,reason,canonical(metrics)))
            results.append({"member_id":m["member_id"],"attempt_id":evidence["attempt_id"],"assessment_id":cursor.lastrowid,"outcome":outcome,"reason":reason})
    return {"assessments":results,"processing_attempts_started":0}
