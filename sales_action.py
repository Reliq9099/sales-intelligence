"""Transparent sales actions derived from researched evidence and qualification."""

from data import Confidence, Opportunity, Qualification, ResearchResult, SalesAction


PLM_PERSONAS = [
    "VP Engineering", "Head of Engineering", "Director of Engineering", "Head of R&D",
    "VP R&D", "Engineering IT Head", "PLM Director", "Head of Digital Engineering",
    "Product Development Head", "Manufacturing Engineering Head", "CIO", "CTO",
    "Digital Transformation Head",
]
MSDS_PERSONAS = [
    "Head of Regulatory Affairs", "Regulatory Affairs Director", "Product Stewardship Head",
    "EHS Head", "Head of R&D", "Chemical R&D Head", "Quality Head", "Compliance Head",
]
FORMULATION_PERSONAS = [
    "Head of R&D", "R&D Director", "Formulation Head", "Product Development Head",
    "Technical Director", "Innovation Head",
]

PLM_QUESTIONS = [
    "How is product data currently managed across engineering teams?",
    "How are engineering changes controlled?",
    "How are BOMs managed?",
    "How do engineering teams collaborate across locations?",
    "How are CAD and product documents version-controlled?",
    "Is there a centralized product data environment?",
    "How does engineering data flow into ERP or manufacturing?",
]
MSDS_QUESTIONS = [
    "How are SDS/MSDS documents currently generated?",
    "Where is formulation data maintained?",
    "How are regulatory changes managed?",
    "How much manual data compilation is involved?",
    "How are SDS revisions and approvals controlled?",
]
FORMULATION_QUESTIONS = [
    "Where is formulation information currently stored?",
    "How are formula revisions managed?",
    "How are specifications linked to formulations?",
    "How are QC requirements managed?",
    "How is formulation data connected to ERP or SAP?",
]


def _has_opportunity(value: Opportunity) -> bool:
    return value in {Opportunity.HIGH, Opportunity.MEDIUM}


def _first_observation(result: ResearchResult) -> str:
    for evidence in result.evidence:
        if evidence.signal in {"Manufacturing", "Engineering / R&D", "Product development", "Physical products", "Company overview"}:
            return evidence.statement.replace("Public company summary: ", "")
    if result.overview.description != "No reliable public evidence found.":
        return result.overview.description
    return "no reliable public evidence was found in the sources reviewed"


def _personas(result: ResearchResult, qualification: Qualification) -> tuple[str, list[str], str, dict[str, str]]:
    ranked: list[tuple[str, str]] = []
    if _has_opportunity(qualification.greenfield_opportunity) or _has_opportunity(qualification.plm_services_opportunity):
        ranked.extend((role, "Relevant to product lifecycle, engineering data, or platform decisions.") for role in PLM_PERSONAS)
    if _has_opportunity(qualification.msds_opportunity):
        ranked.extend((role, "Relevant to safety-data, regulatory, stewardship, or compliance workflows.") for role in MSDS_PERSONAS)
    if _has_opportunity(qualification.formulation_opportunity):
        ranked.extend((role, "Relevant to formulation, R&D, product development, and technical data workflows.") for role in FORMULATION_PERSONAS)
    unique: list[tuple[str, str]] = []
    seen = set()
    for role, reason in ranked:
        if role not in seen:
            unique.append((role, reason))
            seen.add(role)
    if not unique:
        return "Research Further", [], "", {}
    reasons = dict(unique)
    return unique[0][0], [role for role, _ in unique[1:4]], unique[4][0] if len(unique) > 4 else "", reasons


def _confidence(result: ResearchResult, qualification: Qualification) -> tuple[str, str]:
    source_count = len({e.source_url for e in result.evidence if e.source_url})
    claim_count = len(result.evidence)
    if source_count >= 3 and claim_count >= 6 and qualification.sales_score >= 55:
        return "HIGH", "Multiple public sources support a clear opportunity and relevant company activity."
    if source_count >= 1 and claim_count >= 3 and qualification.sales_score >= 25:
        return "MEDIUM", "Some reliable public evidence supports a potential opportunity, but important details remain unverified."
    return "LOW", "Too little specific public evidence is available; research further before outreach."


def _priority_matrix(qualification: Qualification, confidence: str) -> str:
    high_need = qualification.sales_score >= 55 or qualification.greenfield_opportunity == Opportunity.HIGH
    high_signal = bool(qualification.score_breakdown.get("Buying signals") or qualification.score_breakdown.get("Hiring signals")) or confidence == "HIGH"
    if high_need and high_signal:
        return "HIGH NEED / HIGH SIGNAL - CALL NOW"
    if high_need:
        return "HIGH NEED / LOW SIGNAL - RESEARCH"
    if high_signal:
        return "LOW NEED / HIGH SIGNAL - NURTURE"
    return "LOW NEED / LOW SIGNAL - LOW PRIORITY"


def build_sales_action(result: ResearchResult, qualification: Qualification) -> SalesAction:
    primary, secondary, supporting, persona_reasons = _personas(result, qualification)
    confidence, confidence_explanation = _confidence(result, qualification)
    readiness = "READY TO CONTACT" if confidence == "HIGH" and qualification.sales_action in {"CALL NOW", "HIGH PRIORITY"} else "CONTACT AFTER MORE RESEARCH" if confidence == "MEDIUM" else "INSUFFICIENT EVIDENCE"
    observation = _first_observation(result)
    solution = qualification.solution_recommendation
    if solution in {"PLM/PDM", "ENOVIA / 3DEXPERIENCE"} or _has_opportunity(qualification.greenfield_opportunity) or _has_opportunity(qualification.plm_services_opportunity):
        angle = "Explore whether engineering teams are managing product data, BOMs, and engineering changes across disconnected systems, particularly as product development evolves."
        questions = PLM_QUESTIONS[:]
    else:
        angle = "Explore whether the company's current product, regulatory, or technical data workflows could benefit from more controlled information management."
        questions = []
    if _has_opportunity(qualification.msds_opportunity):
        angle = "Explore whether SDS/MSDS generation, regulatory change management, and product documentation are managed consistently across the organization."
        questions.extend(MSDS_QUESTIONS)
    if _has_opportunity(qualification.formulation_opportunity):
        questions.extend(FORMULATION_QUESTIONS)
    questions = list(dict.fromkeys(questions))[:7]
    talking_points = []
    for evidence in result.evidence[:5]:
        if evidence.statement not in talking_points:
            talking_points.append(f"{evidence.statement} -> potential {solution} conversation. Source: {evidence.source_name} ({evidence.source_url})")
    if not talking_points:
        talking_points = ["No public evidence found; treat the sales hypothesis as unverified."]
    if result.evidence:
        call_opener = (
            f"Hi, this is Akshar from Brainwave Consulting. We work with organizations around {solution.lower()} and engineering data management. "
            f"I was looking at {result.overview.name} and noted that {observation}. I wanted to understand how your team currently manages the related data and change process."
        )
    else:
        call_opener = "Research first: no reliable public evidence was found to support a company-specific call opener."
    email_subject = f"{result.overview.name}: {solution} discovery"
    if result.evidence:
        email_draft = (
            f"Subject: {email_subject}\n\nHello,\n\nI was looking at {result.overview.name} and noted that {observation.lower()} "
            f"That may make {solution.lower()} worth exploring, although I would first like to understand your current process. "
            f"How do your teams currently manage the relevant product, engineering, or regulatory data?\n\nWould a short discovery conversation be useful?\n\nBest,\nAkshar\nBrainwave Consulting"
        )
        opening = f"I was looking at {result.overview.name} and noted that {observation}. I wanted to understand how your team currently manages the related data."
        linkedin = f"Hi, I was reviewing {result.overview.name}'s public activity and noticed that {observation.lower()} I work with Brainwave Consulting on {solution.lower()} and would be interested in how your team approaches this today."
    else:
        email_draft = "Research first: no reliable public evidence was found to support a company-specific email draft."
        opening = "Research first: no reliable public evidence was found to support a company-specific opening message."
        linkedin = "Research first: no reliable public evidence was found to support a company-specific LinkedIn angle."
    readiness_explanation = "Strong company evidence and a clear opportunity support initial contact." if readiness == "READY TO CONTACT" else "The opportunity is plausible, but verify missing details before making a focused approach." if readiness == "CONTACT AFTER MORE RESEARCH" else "There is not enough reliable evidence for targeted outreach."
    next_action = f"Contact {primary} and begin with discovery around product data, BOM, engineering change, and related workflow management." if primary != "Research Further" else "Research further before outreach."
    return SalesAction(
        primary_target=primary,
        secondary_targets=secondary,
        supporting_target=supporting,
        persona_reasons=persona_reasons,
        sales_angle=angle,
        discovery_questions=questions,
        talking_points=talking_points[:5],
        opening_message=opening,
        call_opener=call_opener,
        email_subject=email_subject,
        email_draft=email_draft,
        linkedin_angle=linkedin,
        research_confidence=confidence,
        confidence_explanation=confidence_explanation,
        sales_readiness=readiness,
        readiness_explanation=readiness_explanation,
        priority_matrix=_priority_matrix(qualification, confidence),
        next_action=next_action,
    )