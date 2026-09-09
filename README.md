# BWC Sales Intelligence

Sales intelligence and prospect qualification for Brainwave Consulting. The app evaluates a company against BWC's PLM/PDM, ENOVIA, 3DEXPERIENCE, engineering data, MSDS/SDS, and formulation opportunities.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
streamlit run app.py
```

The default provider is `live`, using public Wikidata, Wikipedia, first-party company pages, public careers pages, public LinkedIn pages discovered through web search, DuckDuckGo/Bing web discovery, Google News RSS, and GDELT-indexed public coverage. Optionally set `GEMINI_API_KEY` or `GOOGLE_API_KEY` to add Gemini with Google Search grounding. No key is required for the default free-search path. Research combines multiple sources into `FACT`, `INFERENCE`, or insufficient-evidence states; `NO PUBLIC EVIDENCE` means the relevant search was performed without finding a match, not that a platform or capability is absent.

## Configuration

Environment variables are loaded from `.env`:

- `BWC_RESEARCH_PROVIDER`: provider name, currently `live` or `demo`
- `BWC_APP_TITLE`: optional browser/page title override
- `BWC_REQUEST_TIMEOUT`: HTTP timeout for future providers, in seconds
- `GEMINI_API_KEY` or `GOOGLE_API_KEY`: optional Google AI Studio key for Gemini + Google Search grounding
- `GEMINI_MODEL`: optional Gemini model, default `gemini-2.0-flash`

No API keys are stored in source code. Add provider credentials to `.env` or your deployment secret manager when a live provider is implemented.

## Project layout

- `app.py`: Streamlit presentation layer
- `data.py`: dataclasses and enums for research and qualification results
- `research.py`: provider interfaces and public-source signal extraction
- `scoring.py`: 100-point qualification, greenfield, and services opportunity rules
- `sales_action.py`: role-based personas, sales hypotheses, discovery questions, and outreach drafts
- `utils.py`: normalization and formatting helpers
- `config.py`: environment-backed configuration