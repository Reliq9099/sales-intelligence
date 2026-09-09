"""BWC Sales Intelligence Streamlit application."""

from html import escape

import streamlit as st

from config import settings
from data import Confidence, Opportunity, TriState
from research import research_company
from sales_action import build_sales_action
from scoring import qualify_company
from utils import normalize_company_name, score_color


def _assessment_value(result, label, value):
    if value.value != "UNKNOWN":
        return value.value
    if result.research_performed:
        return "NO PUBLIC EVIDENCE"
    return "INSUFFICIENT DATA"

st.set_page_config(page_title=settings.app_title, page_icon="◈", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;700&family=Space+Grotesk:wght@500;700&display=swap');
:root { --ink:#14242d; --muted:#60727c; --line:#dbe5e5; --mint:#d8f0e7; --teal:#167c70; --cream:#f7f8f3; }
html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; color: var(--ink); }
.stApp { background: radial-gradient(circle at 88% 4%, #e3f4ee 0, #f7f8f3 34%, #f7f8f3 100%); }
h1, h2, h3 { font-family: 'Space Grotesk', sans-serif; letter-spacing: 0; }
.hero { padding: 1.5rem 0 1rem; border-bottom: 1px solid var(--line); margin-bottom: 1.25rem; }
.eyebrow { color: var(--teal); font-size: .75rem; font-weight: 700; letter-spacing: .12em; text-transform: uppercase; }
.hero h1 { font-size: 2.25rem; margin: .25rem 0 .35rem; }
.hero p { color: var(--muted); margin: 0; max-width: 720px; }
.metric { background: white; border: 1px solid var(--line); border-radius: 8px; padding: 1rem 1.1rem; min-height: 108px; }
.metric-label { color: var(--muted); font-size: .78rem; text-transform: uppercase; letter-spacing: .08em; }
.metric-value { font-family: 'Space Grotesk'; font-size: 1.45rem; font-weight: 700; margin-top: .55rem; }
.score { background: var(--ink); color: white; border-radius: 10px; padding: 1.25rem; text-align: center; }
.score-number { color: #a9ecd5; font-family: 'Space Grotesk'; font-size: 3.2rem; line-height: 1; font-weight: 700; }
.score-caption { color: #c4d4d5; font-size: .78rem; margin-top: .35rem; }
.evidence { border-left: 3px solid var(--teal); padding: .25rem 0 .25rem .8rem; margin: .75rem 0; }
.evidence p { margin: 0 0 .25rem; }
.source { color: var(--teal); font-size: .82rem; }
.unknown { color: var(--muted); }
.brief { background: #14242d; color: white; border-radius: 10px; padding: 1.2rem 1.35rem; margin: 1rem 0 1.35rem; }
.brief-title { color: #a9ecd5; font-family: 'Space Grotesk'; font-size: 1.1rem; font-weight: 700; }
.brief-why { color: #d7e3e3; margin-top: .85rem; }
div[data-testid="stSidebar"] { background: #eef4f0; border-right: 1px solid var(--line); }
</style>
""", unsafe_allow_html=True)

with st.sidebar:
    st.markdown("### BWC Intelligence")
    st.caption("Prospect qualification workspace")
    st.divider()
    st.markdown("**Research settings**")
    st.selectbox("Provider", [settings.research_provider.title()], disabled=True)
    st.checkbox("Show evidence", value=True)
    st.checkbox("Include unknown signals", value=True)
    st.divider()
    st.caption("Evidence is directional and should be verified before outreach.")

st.markdown('<div class="hero"><div class="eyebrow">Brainwave Consulting</div><h1>BWC Sales Intelligence</h1><p>Turn a company name into a transparent, evidence-led qualification brief for PLM, engineering data, MSDS, and formulation conversations.</p></div>', unsafe_allow_html=True)

with st.form("research_form"):
    search_col, button_col = st.columns([5, 1], vertical_alignment="bottom")
    with search_col:
        company_name = st.text_input("Company to research", placeholder="Try Tata Motors", label_visibility="visible")
    with button_col:
        submitted = st.form_submit_button("Research", type="primary", width="stretch")

if submitted:
    if not company_name.strip():
        st.warning("Enter a company name to begin research.")
        st.stop()
    with st.spinner("Building the qualification brief..."):
        try:
            result = research_company(company_name)
            qualification = qualify_company(result)
            qualification.sales_action_layer = build_sales_action(result, qualification)
            st.session_state["result"] = result
            st.session_state["qualification"] = qualification
            st.session_state["normalized_name"] = normalize_company_name(company_name)
        except Exception as error:
            st.error("Research could not be completed. Please try again.")
            st.caption(f"Specific error: {error}")

if "result" not in st.session_state:
    st.info("Enter a company above to generate a prospect qualification brief.")
    st.stop()

result = st.session_state["result"]
qualification = st.session_state["qualification"]
sales_action = qualification.sales_action_layer
st.caption(f"Normalized search: `{st.session_state['normalized_name']}` · Provider: {result.provider_name}")

st.markdown(f"## {result.overview.name}")
st.markdown("### Sales action")
st.markdown(
    f'<div class="brief"><div class="brief-title">PRIORITY: {escape(sales_action.sales_readiness)}</div>'
    f'<div class="brief-why"><strong>RECOMMENDED SOLUTION:</strong> {escape(qualification.solution_recommendation)} &nbsp; '
    f'<strong>GREENFIELD POTENTIAL:</strong> {escape(qualification.greenfield_opportunity.value)} &nbsp; '
    f'<strong>BEST PERSONA:</strong> {escape(sales_action.primary_target)} &nbsp; '
    f'<strong>RESEARCH CONFIDENCE:</strong> {escape(sales_action.research_confidence)}</div>'
    f'<div class="brief-why"><strong>SALES ANGLE:</strong> {escape(sales_action.sales_angle)}</div>'
    f'<div class="brief-why"><strong>NEXT ACTION:</strong> {escape(sales_action.next_action)}</div></div>',
    unsafe_allow_html=True,
)
st.markdown("### Sales brief")
why = qualification.solution_explanation
if qualification.score_reasons:
    why += " " + qualification.score_reasons[0]
st.markdown(
    f'<div class="brief"><div class="brief-title">TARGET: {escape(qualification.solution_recommendation)}</div>'
    f'<div class="brief-why"><strong>PRIORITY:</strong> {escape(qualification.sales_action)} &nbsp; '
    f'<strong>GREENFIELD PLM:</strong> {escape(qualification.greenfield_opportunity.value)} &nbsp; '
    f'<strong>PLM SERVICES:</strong> {escape(qualification.plm_services_opportunity.value)} &nbsp; '
    f'<strong>MSDS:</strong> {escape(qualification.msds_opportunity.value)} &nbsp; '
    f'<strong>FORMULATION:</strong> {escape(qualification.formulation_opportunity.value)}</div>'
    f'<div class="brief-why"><strong>WHY:</strong> {escape(why)}</div></div>',
    unsafe_allow_html=True,
)

score_col, action_col, solution_col = st.columns([1.15, 1.5, 1.5])
with score_col:
    st.markdown(f'<div class="score"><div class="score-number">{qualification.sales_score}</div><div class="score-caption">SALES SCORE / 100</div></div>', unsafe_allow_html=True)
with action_col:
    st.markdown(f'<div class="metric"><div class="metric-label">Recommended sales action</div><div class="metric-value">{escape(qualification.sales_action)}</div></div>', unsafe_allow_html=True)
with solution_col:
    st.markdown(f'<div class="metric"><div class="metric-label">Recommended BWC solution</div><div class="metric-value">{escape(qualification.solution_recommendation)}</div></div>', unsafe_allow_html=True)

overview_col, opportunity_col = st.columns([1.15, 1])
with overview_col:
    st.markdown("### Company overview")
    st.table({"Field": ["Website", "Industry", "Headquarters", "Employees"], "Value": [result.overview.website or "Unknown", result.overview.industry, result.overview.headquarters, result.overview.employee_range]})
    st.write(result.overview.description)
with opportunity_col:
    st.markdown("### BWC opportunity")
    st.table({"Area": ["PLM/PDM", "PLM services", "MSDS", "Formulation", "Overall"], "Opportunity": [qualification.greenfield_opportunity.value, qualification.plm_services_opportunity.value, qualification.msds_opportunity.value, qualification.formulation_opportunity.value, qualification.overall_opportunity.value]})
    st.info(qualification.sales_action_explanation)

st.markdown("### Manufacturing & engineering")
status_cols = st.columns(4)
for column, label, value in zip(status_cols, ["Manufacturing", "Engineering / R&D", "Product development", "Physical products"], [result.manufacturing, result.engineering_rd, result.product_development, result.physical_products]):
    with column:
        confidence = result.assessment_confidence.get(label, "LOW")
        st.markdown(f'<div class="metric"><div class="metric-label">{label}</div><div class="metric-value">{_assessment_value(result, label, value)}</div></div>', unsafe_allow_html=True)
        st.caption(f"Confidence: {confidence}")

st.markdown("### Existing PLM / PDM landscape")
landscape_rows = [{
    "System": item.system,
    "Status": item.status.value,
    "Confidence": item.confidence,
    "Evidence": item.evidence,
    "Date": item.source_date,
    "Source": f"[{item.source_name}]({item.source_url})" if item.source_url else "No reliable public evidence found",
} for item in result.plm_landscape]
if landscape_rows:
    st.table(landscape_rows)
else:
    st.info("No reliable public evidence found.")
st.caption("NO PUBLIC EVIDENCE means the system was not identified in the sources reviewed; it does not mean the company does not use it.")

st.markdown("### Engineering complexity")
complexity = result.engineering_complexity
st.table({"Dimension": ["Product complexity", "Engineering complexity", "Manufacturing complexity", "Product categories", "Multi-site engineering", "Change management"], "Assessment": [complexity.product_complexity.value, complexity.engineering_complexity.value, complexity.manufacturing_complexity.value, complexity.product_categories.value, complexity.multi_site_engineering.value, complexity.change_management.value]})
st.info(complexity.explanation)

st.markdown("### Buying signals")
if result.buying_signals:
    st.table([{"Signal": item.signal, "Date": item.date, "Evidence": item.evidence or item.why_it_matters, "Sales relevance": item.why_it_matters, "Source": f"[{item.source_name}]({item.source_url})"} for item in result.buying_signals])
else:
    st.info("None identified in the recent public sources searched.")

st.markdown("### Hiring signals")
if result.hiring_signals:
    st.table([{"Signal": item.signal, "Date": item.date, "Source": f"[{item.source_name}]({item.source_url})"} for item in result.hiring_signals])
else:
    st.info("None identified in the public hiring sources searched.")

st.markdown("### Pain-point indicators")
if result.pain_points:
    st.table([{"Indicator": item.statement, "Source": f"[{item.source_name}]({item.source_url})"} for item in result.pain_points])
else:
    st.info("No public evidence found.")

st.markdown("### Technology signals")
signal_rows = [{"Signal": signal, "Assessment": confidence.value} for signal, confidence in result.technology_signals.items()]
st.dataframe(signal_rows, width="stretch", hide_index=True)

with st.expander("Score breakdown and recommendation reasoning", expanded=True):
    if qualification.score_breakdown:
        st.table([{"Category": category, "Points": points} for category, points in qualification.score_breakdown.items()])
    if qualification.score_reasons:
        for reason in qualification.score_reasons:
            st.markdown(f"- {reason}")
    else:
        st.markdown('<span class="unknown">No positive scoring evidence was identified.</span>', unsafe_allow_html=True)

with st.expander("Research performed", expanded=False):
    research_log = result.research_performed
    st.metric("Useful results", result.useful_result_count)
    st.write(f"**Queries searched:** {len(research_log.get('Queries searched', []))}")
    for query in research_log.get("Queries searched", []):
        st.markdown(f"- `{query}`")
    st.write(f"**Sources checked:** {len(research_log.get('Sources checked', []))}")
    st.write(", ".join(research_log.get("Sources checked", [])) or "None")
    st.write("**Technology platforms checked:**")
    st.write(", ".join(research_log.get("Technology platforms checked", [])) or "None")
    st.write(f"**Job searches performed:** {len(research_log.get('Job searches performed', []))}")

with st.expander("Best contacts to target", expanded=False):
    st.markdown(f"**Primary target:** {sales_action.primary_target}")
    if sales_action.persona_reasons.get(sales_action.primary_target):
        st.caption(sales_action.persona_reasons[sales_action.primary_target])
    if sales_action.secondary_targets:
        st.markdown("**Secondary targets**")
        for contact in sales_action.secondary_targets:
            st.markdown(f"- {contact}: {sales_action.persona_reasons.get(contact, 'Relevant to the qualified opportunity.')}")
    if sales_action.supporting_target:
        st.markdown(f"**Supporting target:** {sales_action.supporting_target}")

st.markdown("### Recommended sales angle")
st.info(sales_action.sales_angle)

st.markdown("### Why this company?")
for talking_point in sales_action.talking_points:
    st.markdown(f"- {talking_point}")

st.markdown("### Discovery questions")
if sales_action.discovery_questions:
    for question in sales_action.discovery_questions:
        st.markdown(f"- {question}")
else:
    st.info("No solution-specific discovery questions generated until a clearer opportunity is identified.")

st.markdown("### Outreach preparation")
outreach_tabs = st.tabs(["Opening message", "Call opener", "Email draft", "LinkedIn angle"])
with outreach_tabs[0]:
    st.write(sales_action.opening_message)
with outreach_tabs[1]:
    st.write(sales_action.call_opener)
with outreach_tabs[2]:
    st.text_area("Email draft", value=sales_action.email_draft, height=220, label_visibility="collapsed")
with outreach_tabs[3]:
    st.write(sales_action.linkedin_angle)

readiness_col, matrix_col = st.columns(2)
with readiness_col:
    st.markdown("### Research confidence")
    st.markdown(f'<div class="metric"><div class="metric-label">Confidence</div><div class="metric-value">{escape(sales_action.research_confidence)}</div></div>', unsafe_allow_html=True)
    st.caption(sales_action.confidence_explanation)
with matrix_col:
    st.markdown("### Sales readiness")
    st.markdown(f'<div class="metric"><div class="metric-label">Readiness</div><div class="metric-value">{escape(sales_action.sales_readiness)}</div></div>', unsafe_allow_html=True)
    st.caption(sales_action.readiness_explanation)

st.markdown("### Priority matrix")
st.info(sales_action.priority_matrix)

with st.expander("Evidence and sources", expanded=True):
    if result.research_note:
        st.caption(result.research_note)
    if result.evidence:
        for item in result.evidence:
            st.markdown(f'<div class="evidence"><p>{escape(item.statement)}</p><a class="source" href="{escape(item.source_url)}" target="_blank">Source: {escape(item.source_name)}</a></div>', unsafe_allow_html=True)
    else:
        st.warning("No reliable public evidence found.")