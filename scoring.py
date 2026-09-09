"""Evidence-weighted qualification rules for BWC's target profile."""

from data import Confidence, Opportunity, Qualification, ResearchResult, TriState, LandscapeStatus


def _opportunity(score: int) -> Opportunity:
    if score >= 65:
        return Opportunity.HIGH
    if score >= 35:
        return Opportunity.MEDIUM
    if score > 0:
        return Opportunity.LOW
    return Opportunity.UNKNOWN


def _complexity_points(level: Opportunity, weight: int) -> int:
    if level == Opportunity.HIGH:
        return weight
    if level == Opportunity.MEDIUM:
        return weight // 2
    return 0


def _size_points(employee_range: str) -> int:
    digits = "".join(character for character in employee_range if character.isdigit())
    if not digits:
        return 0
    employees = int(digits)
    if employees >= 10000:
        return 5
    if employees >= 1000:
        return 4
    if employees >= 250:
        return 3
    if employees >= 50:
        return 1
    return 0


def _system_status(result: ResearchResult) -> list[LandscapeStatus]:
    return [item.status for item in result.plm_landscape]


def _greenfield(result: ResearchResult, need_score: int) -> tuple[Opportunity, int, str]:
    statuses = _system_status(result)
    if not statuses:
        return Opportunity.UNKNOWN, 0, "No PLM/PDM landscape evidence was collected."
    has_confirmed = any(status == LandscapeStatus.CONFIRMED for status in statuses)
    has_likely = any(status == LandscapeStatus.LIKELY for status in statuses)
    has_possible = any(status == LandscapeStatus.POSSIBLE for status in statuses)
    complexity = result.engineering_complexity
    strong_need = need_score >= 8 and any(
        level in {Opportunity.HIGH, Opportunity.MEDIUM}
        for level in (complexity.product_complexity, complexity.engineering_complexity, complexity.manufacturing_complexity)
    )
    if has_confirmed:
        return Opportunity.LOW, 2, "An enterprise PLM/PDM system is publicly identified; greenfield potential is reduced."
    if has_likely or has_possible:
        return Opportunity.MEDIUM if strong_need else Opportunity.LOW, 8 if strong_need else 4, "A PLM/PDM reference exists, so the opportunity requires platform-landscape discovery."
    if strong_need:
        return Opportunity.HIGH, 15, "Greenfield potential based on public evidence. No reliable public evidence of an enterprise PLM/PDM system was identified."
    if statuses and all(status == LandscapeStatus.NOT_FOUND for status in statuses):
        return Opportunity.LOW, 3, "No reliable public evidence of an enterprise PLM/PDM system was identified, but need evidence is limited."
    return Opportunity.UNKNOWN, 0, "The available PLM/PDM evidence is inconclusive."


def _services_opportunity(result: ResearchResult) -> Opportunity:
    statuses = _system_status(result)
    if any(status in {LandscapeStatus.CONFIRMED, LandscapeStatus.LIKELY} for status in statuses):
        return Opportunity.HIGH
    if any(status == LandscapeStatus.POSSIBLE for status in statuses):
        return Opportunity.MEDIUM
    if result.engineering_complexity.engineering_complexity in {Opportunity.HIGH, Opportunity.MEDIUM}:
        return Opportunity.MEDIUM
    return Opportunity.UNKNOWN


def _solution(result: ResearchResult, greenfield: Opportunity, services: Opportunity, msds: Opportunity, formulation: Opportunity) -> tuple[str, str]:
    chemical = msds in {Opportunity.HIGH, Opportunity.MEDIUM} and formulation in {Opportunity.HIGH, Opportunity.MEDIUM}
    if greenfield in {Opportunity.HIGH, Opportunity.MEDIUM} and chemical:
        return "PLM + MSDS", "Strong product and engineering need indicators combine with an evidence-backed chemical documentation opportunity."
    if greenfield == Opportunity.HIGH and formulation in {Opportunity.HIGH, Opportunity.MEDIUM}:
        return "PLM + Formulation", "Greenfield PLM potential and formulation relevance are both supported by public evidence."
    if greenfield in {Opportunity.HIGH, Opportunity.MEDIUM}:
        return "PLM/PDM", "Public evidence supports a PLM/PDM discovery conversation without a clear enterprise platform reference."
    if services in {Opportunity.HIGH, Opportunity.MEDIUM}:
        return "ENOVIA / 3DEXPERIENCE", "An existing or likely PLM/PDM landscape makes implementation, integration, migration, customization, or support discovery relevant."
    if msds in {Opportunity.HIGH, Opportunity.MEDIUM} and formulation in {Opportunity.HIGH, Opportunity.MEDIUM}:
        return "Multiple Solutions", "Public evidence supports both MSDS and formulation data-management conversations."
    if msds in {Opportunity.HIGH, Opportunity.MEDIUM}:
        return "MSDS Automation", "Public evidence supports a chemical-documentation and product-stewardship conversation."
    if formulation in {Opportunity.HIGH, Opportunity.MEDIUM}:
        return "Formulation Data Management", "Public evidence supports a formulation-heavy data-management conversation."
    return "Research Further", "The public evidence does not yet identify a specific BWC solution with confidence."


def qualify_company(result: ResearchResult) -> Qualification:
    breakdown: dict[str, int] = {}
    reasons: list[str] = []

    manufacturing_points = 10 if result.manufacturing == TriState.YES else 0
    engineering_points = 10 if result.engineering_rd == TriState.YES else 0
    breakdown["Manufacturing relevance"] = manufacturing_points
    breakdown["Engineering/R&D"] = engineering_points
    if manufacturing_points:
        reasons.append("Public evidence supports manufacturing relevance.")
    if engineering_points:
        reasons.append("Public evidence supports engineering or R&D activity.")

    complexity = result.engineering_complexity
    product_points = _complexity_points(complexity.product_complexity, 10)
    engineering_complexity_points = _complexity_points(complexity.engineering_complexity, 10)
    breakdown["Product complexity"] = product_points
    breakdown["Engineering complexity"] = engineering_complexity_points
    if product_points or engineering_complexity_points:
        reasons.append("Product and engineering complexity evidence increases lifecycle-management fit.")

    need_score = 0
    if result.domain_signals.get("PLM need indicators") in {Confidence.CONFIRMED, Confidence.LIKELY, Confidence.POSSIBLE}:
        need_score += 8
    need_score += min(7, len(result.pain_points) * 3 + (2 if complexity.change_management != Opportunity.UNKNOWN else 0))
    breakdown["PLM need indicators"] = need_score
    if need_score:
        reasons.append("Public evidence contains indicators of product-data or lifecycle-management need.")

    greenfield, greenfield_points, greenfield_reason = _greenfield(result, need_score)
    breakdown["Greenfield PLM potential"] = greenfield_points
    if greenfield_points:
        reasons.append(greenfield_reason)

    buying_points = min(10, len(result.buying_signals) * 5)
    hiring_points = min(10, len(result.hiring_signals) * 5)
    breakdown["Buying signals"] = buying_points
    breakdown["Hiring signals"] = hiring_points
    if buying_points:
        reasons.append("Recent public buying signals justify timely discovery.")
    if hiring_points:
        reasons.append("Public careers evidence indicates relevant capability expansion.")

    digital_points = 5 if result.domain_signals.get("Digital transformation") in {Confidence.CONFIRMED, Confidence.LIKELY, Confidence.POSSIBLE} else 0
    size_points = _size_points(result.overview.employee_range)
    breakdown["Digital transformation"] = digital_points
    breakdown["Company size / ability to buy"] = size_points
    if digital_points:
        reasons.append("Public material references digital transformation or modernization.")

    total_score = max(0, min(100, sum(breakdown.values())))
    services = _services_opportunity(result)
    msds = Opportunity.HIGH if result.domain_signals.get("MSDS / SDS") in {Confidence.CONFIRMED, Confidence.LIKELY, Confidence.POSSIBLE} else Opportunity.UNKNOWN
    formulation = Opportunity.HIGH if result.domain_signals.get("Formulation") in {Confidence.CONFIRMED, Confidence.LIKELY, Confidence.POSSIBLE} else Opportunity.UNKNOWN
    solution, solution_explanation = _solution(result, greenfield, services, msds, formulation)

    if total_score >= 80:
        action = "CALL NOW"
    elif total_score >= 65:
        action = "HIGH PRIORITY"
    elif total_score >= 40:
        action = "RESEARCH FURTHER"
    elif total_score >= 20:
        action = "NURTURE"
    else:
        action = "DO NOT PRIORITIZE"
    action_explanation = (
        f"{action} because the evidence-weighted qualification score is {total_score}/100. "
        f"Greenfield PLM is {greenfield.value.lower()} and PLM services is {services.value.lower()}."
    )

    overall = _opportunity(max(greenfield_points, 0) + max(buying_points, 0) + max(engineering_complexity_points, 0))
    contacts = ["Head of Engineering", "VP Engineering", "Head of R&D", "Digital Transformation Head", "CIO / CTO", "Engineering IT", "Product Development Head"]
    return Qualification(
        plm_opportunity=greenfield,
        msds_opportunity=msds,
        formulation_opportunity=formulation,
        overall_opportunity=overall,
        sales_score=total_score,
        recommendation=action,
        explanation=action_explanation,
        score_reasons=reasons,
        greenfield_opportunity=greenfield,
        plm_services_opportunity=services,
        solution_recommendation=solution,
        solution_explanation=solution_explanation,
        sales_action=action,
        sales_action_explanation=action_explanation,
        score_breakdown=breakdown,
        best_contacts=contacts,
    )

