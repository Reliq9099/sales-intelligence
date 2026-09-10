"""Typed data contracts for company research and qualification."""

from dataclasses import dataclass, field
from enum import Enum


class Confidence(str, Enum):
    CONFIRMED = "CONFIRMED"
    LIKELY = "LIKELY"
    POSSIBLE = "POSSIBLE"
    UNKNOWN = "UNKNOWN"


class ResearchStatus(str, Enum):
    CONFIRMED = "CONFIRMED"
    LIKELY = "LIKELY"
    INFERENCE = "INFERENCE"
    NO_PUBLIC_EVIDENCE = "NO PUBLIC EVIDENCE"
    INSUFFICIENT_DATA = "INSUFFICIENT DATA"
    UNKNOWN = "UNKNOWN"


class TriState(str, Enum):
    YES = "YES"
    NO = "NO"
    UNKNOWN = "UNKNOWN"


class Opportunity(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    UNKNOWN = "UNKNOWN"


class LandscapeStatus(str, Enum):
    CONFIRMED = "CONFIRMED"
    LIKELY = "LIKELY"
    POSSIBLE = "POSSIBLE"
    NOT_FOUND = "NO PUBLIC EVIDENCE"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class Evidence:
    statement: str
    source_name: str
    source_url: str
    signal: str = ""
    confidence: str = "MEDIUM"
    source_date: str = "Unknown"
    source_type: str = "Public web"
    fact_or_inference: str = "FACT"


@dataclass(frozen=True)
class PLMLandscapeItem:
    system: str
    status: LandscapeStatus
    evidence: str = "No reliable public evidence found."
    source_name: str = ""
    source_url: str = ""
    source_date: str = "Unknown"
    confidence: str = "MEDIUM"


@dataclass(frozen=True)
class BuyingSignal:
    signal: str
    date: str = "Unknown"
    why_it_matters: str = ""
    source_name: str = ""
    source_url: str = ""
    evidence: str = ""
    confidence: str = "MEDIUM"
    source_type: str = "PUBLIC_WEB"
    recommended_action: str = "Validate in discovery."


@dataclass(frozen=True)
class HiringSignal:
    signal: str
    date: str = "Unknown"
    source_name: str = ""
    source_url: str = ""
    technology: str = ""
    recency: str = "UNKNOWN"
    confidence: str = "MEDIUM"
    current_or_historical: str = "UNKNOWN"


@dataclass
class EngineeringComplexity:
    product_complexity: Opportunity = Opportunity.UNKNOWN
    engineering_complexity: Opportunity = Opportunity.UNKNOWN
    manufacturing_complexity: Opportunity = Opportunity.UNKNOWN
    product_categories: Opportunity = Opportunity.UNKNOWN
    multi_site_engineering: Opportunity = Opportunity.UNKNOWN
    change_management: Opportunity = Opportunity.UNKNOWN
    explanation: str = "No reliable public evidence found."
    evidence: list[Evidence] = field(default_factory=list)


@dataclass(frozen=True)
class PainPointIndicator:
    statement: str
    source_name: str = ""
    source_url: str = ""


@dataclass
class CompanyOverview:
    name: str
    website: str = ""
    industry: str = "Unknown"
    headquarters: str = "Unknown"
    employee_range: str = "Unknown"
    description: str = "No reliable public evidence found."


@dataclass
class ResearchResult:
    overview: CompanyOverview
    manufacturing: TriState = TriState.UNKNOWN
    engineering_rd: TriState = TriState.UNKNOWN
    product_development: TriState = TriState.UNKNOWN
    physical_products: TriState = TriState.UNKNOWN
    technology_signals: dict[str, Confidence] = field(default_factory=dict)
    domain_signals: dict[str, Confidence] = field(default_factory=dict)
    evidence: list[Evidence] = field(default_factory=list)
    plm_landscape: list[PLMLandscapeItem] = field(default_factory=list)
    buying_signals: list[BuyingSignal] = field(default_factory=list)
    hiring_signals: list[HiringSignal] = field(default_factory=list)
    engineering_complexity: EngineeringComplexity = field(default_factory=EngineeringComplexity)
    pain_points: list[PainPointIndicator] = field(default_factory=list)
    assessment_confidence: dict[str, str] = field(default_factory=dict)
    research_performed: dict[str, list[str]] = field(default_factory=dict)
    useful_result_count: int = 0
    provider_name: str = "Unknown"
    research_note: str = ""
    canonical_name: str = ""
    legal_name: str = ""
    aliases: list[str] = field(default_factory=list)
    parent_company: str = ""
    identity_evidence: list[Evidence] = field(default_factory=list)
    research_quality_score: int = 0
    coverage: dict[str, str] = field(default_factory=dict)
    research_audit: dict[str, object] = field(default_factory=dict)
    gap_fields: list[str] = field(default_factory=list)
    research_analysis: dict[str, object] = field(default_factory=dict)


@dataclass
class SalesAction:
    primary_target: str = "Research Further"
    secondary_targets: list[str] = field(default_factory=list)
    supporting_target: str = ""
    persona_reasons: dict[str, str] = field(default_factory=dict)
    sales_angle: str = "Explore whether there is an opportunity relevant to Brainwave Consulting."
    discovery_questions: list[str] = field(default_factory=list)
    talking_points: list[str] = field(default_factory=list)
    opening_message: str = ""
    call_opener: str = ""
    email_subject: str = ""
    email_draft: str = ""
    linkedin_angle: str = ""
    research_confidence: str = "LOW"
    confidence_explanation: str = "Insufficient reliable evidence is available."
    sales_readiness: str = "INSUFFICIENT EVIDENCE"
    readiness_explanation: str = "Research further before outreach."
    priority_matrix: str = "LOW SIGNAL / LOW NEED"
    next_action: str = "Research further before outreach."


@dataclass
class Qualification:
    plm_opportunity: Opportunity
    msds_opportunity: Opportunity
    formulation_opportunity: Opportunity
    overall_opportunity: Opportunity
    sales_score: int
    recommendation: str
    explanation: str
    score_reasons: list[str] = field(default_factory=list)
    greenfield_opportunity: Opportunity = Opportunity.UNKNOWN
    plm_services_opportunity: Opportunity = Opportunity.UNKNOWN
    solution_recommendation: str = "Research Further"
    solution_explanation: str = "No reliable public evidence found."
    sales_action: str = "RESEARCH FURTHER"
    sales_action_explanation: str = "More evidence is needed before prioritizing outreach."
    score_breakdown: dict[str, int] = field(default_factory=dict)
    best_contacts: list[str] = field(default_factory=list)
    sales_action_layer: SalesAction = field(default_factory=SalesAction)