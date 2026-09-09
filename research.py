"""Research provider interfaces and live public-source research."""

from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor, as_completed
from html import unescape
import re
import xml.etree.ElementTree as ET
from urllib.parse import parse_qs, quote, unquote, urljoin, urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from config import settings
from data import (
    BuyingSignal,
    CompanyOverview,
    Confidence,
    EngineeringComplexity,
    Evidence,
    HiringSignal,
    LandscapeStatus,
    PainPointIndicator,
    PLMLandscapeItem,
    ResearchResult,
    TriState,
    Opportunity,
)
from utils import normalize_company_name


class CompanyResearchProvider(ABC):
    """Provider boundary for company, web, technology, and hiring research."""

    name = "Unknown provider"

    @abstractmethod
    def research_company(self, company_name: str) -> ResearchResult:
        raise NotImplementedError


class LiveResearchProvider(CompanyResearchProvider):
    """Research a company from public structured and first-party sources.

    Wikidata supplies normalized company facts, Wikipedia supplies a readable
    public summary, and the company's own site is used only for corroborating
    business and technology language. A missing source never becomes a guess.
    """

    name = "Live public-source research"
    wikidata_api = "https://www.wikidata.org/w/api.php"
    wikipedia_api = "https://en.wikipedia.org/api/rest_v1/page/summary/"
    gdelt_api = "https://api.gdeltproject.org/api/v2/doc/doc"
    web_search_api = "https://html.duckduckgo.com/html/"
    bing_search_api = "https://www.bing.com/search"
    google_news_rss = "https://news.google.com/rss/search"
    gemini_api = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    plm_systems = {
        "PLM": ("plm", "PLM"),
        "PDM": ("pdm", "PDM"),
        "ENOVIA": ("enovia", "Dassault Systèmes ENOVIA"),
        "3DEXPERIENCE": ("3dexperience", "Dassault Systèmes 3DEXPERIENCE"),
        "Dassault Systèmes": ("dassault systèmes", "Dassault Systèmes"),
        "CATIA": ("catia", "CATIA"),
        "Teamcenter": ("teamcenter", "Siemens Teamcenter"),
        "Siemens PLM": ("siemens plm", "Siemens PLM"),
        "Windchill": ("windchill", "PTC Windchill"),
        "PTC": ("ptc", "PTC"),
        "Aras": ("aras", "Aras Innovator"),
        "Autodesk Vault": ("autodesk vault", "Autodesk Vault"),
        "Arena PLM": ("arena plm", "Arena PLM"),
        "SAP PLM": ("sap plm", "SAP PLM"),
        "Oracle PLM": ("oracle plm", "Oracle PLM"),
    }
    signal_names = [
        "PLM", "PDM", "ENOVIA", "3DEXPERIENCE", "Dassault Systèmes", "SAP",
        "CAD", "ERP", "Engineering Data Management",
    ]
    _cache: dict[str, ResearchResult] = {}

    def __init__(self) -> None:
        self.session = requests.Session()
        retry_policy = Retry(
            total=0,
            status_forcelist=(),
            allowed_methods=("GET",),
            respect_retry_after_header=False,
        )
        self.session.mount("https://", HTTPAdapter(max_retries=retry_policy))
        self.session.headers.update({"User-Agent": "BWC-Sales-Intelligence/1.0 public-research"})
        self.timeout = settings.request_timeout

    def _get_json(self, url: str, params: dict[str, str]) -> dict:
        response = self.session.get(url, params=params, timeout=min(self.timeout, 3))
        response.raise_for_status()
        return response.json()

    def _search_entity(self, company_name: str) -> dict | None:
        payload = self._get_json(self.wikidata_api, {
            "action": "wbsearchentities", "search": company_name,
            "language": "en", "uselang": "en", "limit": "5", "format": "json",
        })
        results = payload.get("search", [])
        normalized = normalize_company_name(company_name)
        exact = next((item for item in results if normalize_company_name(item.get("label", "")) == normalized), None)
        if exact:
            return exact
        related = next((item for item in results if normalized in normalize_company_name(item.get("label", "")) or normalize_company_name(item.get("label", "")) in normalized), None)
        return related

    def _get_entity(self, entity_id: str) -> dict:
        payload = self._get_json(self.wikidata_api, {
            "action": "wbgetentities", "ids": entity_id,
            "props": "claims|labels|descriptions|sitelinks", "languages": "en", "format": "json",
        })
        return payload["entities"][entity_id]

    @staticmethod
    def _claim(entity: dict, property_id: str) -> list:
        values = []
        for statement in entity.get("claims", {}).get(property_id, []):
            mainsnak = statement.get("mainsnak", {})
            if mainsnak.get("snaktype") == "value":
                values.append(mainsnak.get("datavalue", {}).get("value"))
        return values

    def _labels(self, entity_ids: list[str]) -> dict[str, str]:
        if not entity_ids:
            return {}
        payload = self._get_json(self.wikidata_api, {
            "action": "wbgetentities", "ids": "|".join(entity_ids[:20]),
            "props": "labels", "languages": "en", "format": "json",
        })
        return {
            entity_id: entity.get("labels", {}).get("en", {}).get("value", entity_id)
            for entity_id, entity in payload.get("entities", {}).items()
        }

    @staticmethod
    def _clean_html(value: str) -> str:
        return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", value))).strip()

    def _official_text(self, website: str) -> tuple[str, str]:
        if not website:
            return "", ""
        try:
            response = self.session.get(website, timeout=min(self.timeout, 3))
            response.raise_for_status()
            text = self._clean_html(response.text)
            return text[:500000], website
        except requests.RequestException:
            return "", ""

    def _official_pages(self, website: str) -> tuple[str, list[str]]:
        """Read a small, relevant first-party page set instead of only the homepage."""
        if not website:
            return "", []
        try:
            response = self.session.get(website, timeout=min(self.timeout, 3))
            response.raise_for_status()
            raw_homepage = response.text
            homepage = self._clean_html(raw_homepage)[:500000]
        except requests.RequestException:
            return "", []
        homepage_url = website
        candidate_paths = (
            "about", "company", "products", "solutions", "engineering", "research",
            "r-and-d", "manufacturing", "careers", "investors", "annual-report",
            "sustainability", "technology", "digital-transformation", "innovation",
        )
        links = set()
        for match in re.findall(r'href=["\']([^"\']+)', raw_homepage, flags=re.IGNORECASE):
            absolute = urljoin(homepage_url, match)
            parsed = urlparse(absolute)
            if parsed.netloc == urlparse(homepage_url).netloc and any(path in absolute.lower() for path in candidate_paths):
                links.add(absolute.split("#", 1)[0])
        urls = [homepage_url] + sorted(links)[:3]
        texts = [homepage]
        successful_urls = [homepage_url]
        for url in urls[1:]:
            text, successful_url = self._fetch_text(url)
            if text:
                texts.append(text)
                successful_urls.append(successful_url)
        return " ".join(texts)[:1000000], successful_urls

    def _fetch_text(self, url: str) -> tuple[str, str]:
        try:
            response = self.session.get(url, timeout=min(self.timeout, 3))
            response.raise_for_status()
            return self._clean_html(response.text)[:500000], url
        except requests.RequestException:
            return "", ""

    def _web_search(self, query: str, limit: int = 6) -> list[dict]:
        try:
            response = self.session.get(self.web_search_api, params={"q": query}, timeout=min(self.timeout, 3))
            response.raise_for_status()
        except requests.RequestException:
            return []
        anchors = re.findall(r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', response.text, flags=re.IGNORECASE)
        snippets = re.findall(r'class="result__snippet"[^>]*>(.*?)</(?:a|div)>', response.text, flags=re.IGNORECASE)
        results = []
        for index, (raw_url, raw_title) in enumerate(anchors[:limit]):
            url = raw_url
            parsed = urlparse(url)
            if "uddg" in parse_qs(parsed.query):
                url = unquote(parse_qs(parsed.query)["uddg"][0])
            title = self._clean_html(raw_title)
            snippet = self._clean_html(snippets[index]) if index < len(snippets) else ""
            if title and url.startswith(("http://", "https://")):
                domain = urlparse(url).netloc
                source = "LinkedIn public page" if "linkedin.com" in domain else "DuckDuckGo web search"
                results.append({"title": title, "snippet": snippet, "url": url, "domain": domain, "source": source})
        return results

    def _bing_search(self, query: str, limit: int = 6) -> list[dict]:
        try:
            response = self.session.get(self.bing_search_api, params={"q": query, "count": limit}, timeout=min(self.timeout, 3))
            response.raise_for_status()
        except requests.RequestException:
            return []
        matches = re.findall(r'<li class="b_algo".*?<h2><a href="([^"]+)"[^>]*>(.*?)</a>.*?(?:<p>(.*?)</p>)?', response.text, flags=re.IGNORECASE | re.DOTALL)
        results = []
        for raw_url, raw_title, raw_snippet in matches[:limit]:
            url = unescape(raw_url)
            title = self._clean_html(raw_title)
            snippet = self._clean_html(raw_snippet)
            domain = urlparse(url).netloc
            if title and url.startswith(("http://", "https://")):
                source = "LinkedIn public page" if "linkedin.com" in domain else "Bing web search"
                results.append({"title": title, "snippet": snippet, "url": url, "domain": domain, "source": source})
        return results

    def _parallel_web_search(self, company_name: str, suffixes: tuple[str, ...], queries: list[str], limit: int = 6) -> list[dict]:
        query_values = [f'"{company_name}" {suffix}' for suffix in suffixes]
        queries.extend(query_values)
        results: list[dict] = []
        with ThreadPoolExecutor(max_workers=min(8, len(query_values))) as executor:
            futures = []
            for query in query_values:
                futures.append(executor.submit(self._web_search, query, limit))
                futures.append(executor.submit(self._bing_search, query, limit))
            for future in as_completed(futures):
                results.extend(future.result())
        unique = {}
        for result in results:
            unique[result["url"]] = result
        return list(unique.values())

    @staticmethod
    def _source_name(article: dict) -> str:
        return article.get("source", article.get("domain", "Public publication"))

    def _google_news_search(self, query: str, limit: int = 6) -> list[dict]:
        """Use Google's free News RSS endpoint; no API key or paid search service required."""
        try:
            response = self.session.get(
                self.google_news_rss,
                params={"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"},
                timeout=min(self.timeout, 3),
            )
            response.raise_for_status()
            root = ET.fromstring(response.content)
        except (requests.RequestException, ET.ParseError):
            return []
        results = []
        for item in root.findall("./channel/item")[:limit]:
            title = item.findtext("title", "").strip()
            url = item.findtext("link", "").strip()
            published = item.findtext("pubDate", "").strip()
            source = item.findtext("source", "Google News")
            description = self._clean_html(item.findtext("description", ""))
            if title and url:
                results.append({
                    "title": title,
                    "snippet": description,
                    "url": url,
                    "domain": source,
                    "source": "Google News",
                    "date": published or "Unknown",
                })
        return results

    def _gemini_grounded_search(self, company_name: str) -> list[dict]:
        """Use Gemini's Google Search grounding when an API key is explicitly configured."""
        if not settings.gemini_api_key:
            return []
        prompt = (
            f"Research {company_name} for a B2B sales qualification brief. Search the web and return only "
            "verifiable facts about manufacturing, engineering/R&D, product development, physical products, "
            "PLM/PDM technology, recent expansion or hiring, and chemical/pharma/formulation relevance. "
            "Do not infer unverified facts. Cite the supporting web sources."
        )
        try:
            response = self.session.post(
                self.gemini_api.format(model=settings.gemini_model),
                params={"key": settings.gemini_api_key},
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "tools": [{"google_search": {}}],
                    "generationConfig": {"temperature": 0.1, "maxOutputTokens": 1200},
                },
                timeout=min(self.timeout, 12),
            )
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError):
            return []
        candidate = (payload.get("candidates") or [{}])[0]
        text = " ".join(part.get("text", "") for part in candidate.get("content", {}).get("parts", [])).strip()
        grounding = candidate.get("groundingMetadata", {})
        chunks = grounding.get("groundingChunks", [])
        results = []
        for chunk in chunks:
            web = chunk.get("web", {})
            url = web.get("uri", "")
            title = web.get("title", "") or "Gemini grounded web source"
            if url:
                results.append({
                    "title": title,
                    "snippet": text,
                    "url": url,
                    "domain": urlparse(url).netloc,
                    "source": "Gemini + Google Search grounding",
                    "date": "Unknown",
                })
        if not results and text:
            results.append({"title": "Gemini grounded research summary", "snippet": text, "url": "", "domain": "Google Search", "source": "Gemini + Google Search grounding", "date": "Unknown"})
        return results

    def _parallel_google_news_search(self, company_name: str, suffixes: tuple[str, ...], queries: list[str], limit: int = 6) -> list[dict]:
        query_values = [f"{company_name} {suffix}" for suffix in suffixes]
        queries.extend(query_values)
        results: list[dict] = []
        with ThreadPoolExecutor(max_workers=min(6, len(query_values))) as executor:
            futures = [executor.submit(self._google_news_search, query, limit) for query in query_values]
            for future in as_completed(futures):
                results.extend(future.result())
        unique = {}
        for result in results:
            unique[f"{result['title']}|{result['url']}"] = result
        return list(unique.values())

    def _public_search(self, company_name: str, query_suffix: str, queries: list[str], limit: int = 6) -> list[dict]:
        query = f'"{company_name}" {query_suffix}'
        try:
            response = self.session.get(self.gdelt_api, params={
                "query": query, "mode": "artlist", "format": "json",
                "maxrecords": str(limit), "sort": "datedesc",
            }, timeout=min(self.timeout, 2.5))
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError):
            return []
        return [article for article in payload.get("articles", []) if article.get("url") and article.get("title")]

    def _parallel_public_search(self, company_name: str, suffixes: tuple[str, ...], queries: list[str], limit: int = 6) -> list[dict]:
        queries.extend(f'"{company_name}" {suffix}' for suffix in suffixes)
        results: list[dict] = []
        with ThreadPoolExecutor(max_workers=min(6, len(suffixes))) as executor:
            futures = [executor.submit(self._public_search, company_name, suffix, [], limit) for suffix in suffixes]
            for future in as_completed(futures):
                results.extend(future.result())
        return results

    @staticmethod
    def _normalize_industry(value: str, text: str) -> str:
        raw_value = value.lower()
        categories = (
            ("Pharmaceuticals", ("pharmaceutical", "drug manufacturer", "medicine")),
            ("Paints & Coatings", ("paint", "coating")),
            ("Specialty Chemicals", ("specialty chemical", "chemical manufacturer")),
            ("Chemicals", ("chemical", "materials")),
            ("Medical Devices", ("medical device", "medtech")),
            ("Automotive Components", ("auto component", "automotive component", "vehicle parts")),
            ("Automotive", ("automotive", "vehicle", "car manufacturer", "cars")),
            ("Aerospace", ("aerospace", "aircraft")),
            ("Industrial Equipment", ("industrial equipment", "machinery", "industrial products")),
            ("Electronics", ("electronics", "semiconductor")),
            ("Energy", ("energy", "oil and gas", "renewable")),
            ("IT Services", ("technology", "software", "information technology", "it services", "cloud services")),
            ("IT Services", ("information technology", "it services", "software services", "cloud services")),
            ("Consulting", ("consulting", "professional services")),
        )
        raw_match = next((label for label, terms in categories if any(term in raw_value for term in terms)), None)
        if raw_match:
            return raw_match
        haystack = text.lower()
        return next((label for label, terms in categories if any(term in haystack for term in terms)), "Industrial Manufacturing" if re.search(r"manufactur|factory|production|plant", haystack) else "Unknown")

    @staticmethod
    def _employee_range(employee_range: str, text: str) -> str:
        if employee_range != "Unknown":
            digits = "".join(character for character in employee_range if character.isdigit())
            if digits:
                count = int(digits)
                if count >= 10000:
                    return "10,000+"
                if count >= 5001:
                    return "5,001-10,000"
                if count >= 1001:
                    return "1,001-5,000"
                if count >= 501:
                    return "501-1,000"
                if count >= 201:
                    return "201-500"
                if count >= 51:
                    return "51-200"
                return "1-50"
        match = re.search(r"(?:over|more than|approximately|about)\s+([\d,]+)\s+(?:employees|people|staff)", text.lower())
        return f"{int(match.group(1).replace(',', '')):,}+" if match else "Unknown"

    @staticmethod
    def _synthesized_state(indicators: list[bool]) -> tuple[TriState, str]:
        count = sum(indicators)
        if count >= 2:
            return TriState.YES, "HIGH"
        if count == 1:
            return TriState.YES, "MEDIUM"
        return TriState.UNKNOWN, "LOW"

    def _fallback_public_result(self, company_name: str) -> ResearchResult:
        """Use public search evidence when structured entity data is unavailable."""
        queries = [company_name]
        articles = self._parallel_public_search(
            company_name,
            ("engineering R&D", "product development manufacturing", "digital engineering technology", "jobs careers"),
            queries,
            limit=5,
        )
        web_articles = self._parallel_web_search(company_name, ("engineering R&D", "product development", "PLM PDM", "manufacturing plants", "annual report investor presentation", "engineering jobs careers", "LinkedIn company", "LinkedIn jobs engineering", "LinkedIn jobs PLM PDM"), queries, limit=5)
        articles.extend(web_articles)
        articles.extend(self._parallel_google_news_search(company_name, ("manufacturing", "engineering R&D", "product launch", "digital transformation", "technology investment"), queries, limit=5))
        gemini_articles = self._gemini_grounded_search(company_name)
        articles.extend(gemini_articles)
        text = " ".join(f"{article.get('title', '')} {article.get('snippet', '')}" for article in articles)
        source_url = articles[0].get("url", "") if articles else ""
        source_name = articles[0].get("domain", "Public publication") if articles else ""
        evidence = [Evidence(f"External source reports: {article.get('title', '')}. {article.get('snippet', '')}".strip(), self._source_name(article), article.get("url", ""), "External research", "LOW", article.get("date", "Unknown")) for article in articles[:8]]
        source_texts = [text.lower()]
        manufacturing, manufacturing_confidence = self._synthesized_state([bool(re.search(r"manufactur|production|factory|plant", value)) for value in source_texts])
        engineering, engineering_confidence = self._synthesized_state([bool(re.search(r"engineer|research|r&d|design|cad", value)) for value in source_texts])
        product_development, product_confidence = self._synthesized_state([bool(re.search(r"product|develop|launch|prototype|portfolio", value)) for value in source_texts])
        physical_products, physical_confidence = self._synthesized_state([bool(re.search(r"vehicle|product|equipment|chemical|pharmaceutical|machinery", value)) for value in source_texts])
        plm_landscape = self._plm_landscape(text, source_name, source_url, searched=True)
        industry = self._normalize_industry("Unknown", text)
        description = "Public search evidence was gathered, but structured company facts were unavailable." if evidence else "No reliable public evidence found."
        return ResearchResult(
            overview=CompanyOverview(name=company_name, industry=industry, description=description),
            manufacturing=manufacturing,
            engineering_rd=engineering,
            product_development=product_development,
            physical_products=physical_products,
            technology_signals={signal: Confidence.POSSIBLE if signal.lower() in text.lower() else Confidence.UNKNOWN for signal in self.signal_names},
            evidence=evidence,
            plm_landscape=plm_landscape,
            assessment_confidence={"Manufacturing": manufacturing_confidence, "Engineering / R&D": engineering_confidence, "Product development": product_confidence, "Physical products": physical_confidence},
            research_performed={"Queries searched": queries, "Sources checked": list(dict.fromkeys(["LinkedIn public search"] + [article.get("domain", "Public publication") for article in articles])), "Technology platforms checked": list(self.plm_systems), "Job searches performed": [query for query in queries if "job" in query.lower() or "linkedin" in query.lower()]},
            useful_result_count=len(evidence),
            provider_name=self.name,
            research_note="Structured entity data was unavailable; conclusions are based on limited public search evidence." if evidence else "No reliable public evidence found after the available searches.",
        )

    @staticmethod
    def _level(score: int) -> Opportunity:
        if score >= 3:
            return Opportunity.HIGH
        if score >= 1:
            return Opportunity.MEDIUM
        return Opportunity.UNKNOWN

    def _plm_landscape(self, text: str, source_name: str, source_url: str, searched: bool = True) -> list[PLMLandscapeItem]:
        if not text and not searched:
            return [PLMLandscapeItem(system, LandscapeStatus.UNKNOWN) for system in self.plm_systems]
        lower_text = text.lower()
        landscape = []
        for system, (term, label) in self.plm_systems.items():
            term_pattern = rf"(?<!\w){re.escape(term)}(?!\w)"
            if re.search(term_pattern, lower_text):
                explicit_use = re.search(
                    rf"(?:uses|using|implemented|adopted|deployed|running|powered by).{{0,60}}{re.escape(term)}",
                    lower_text,
                )
                status = LandscapeStatus.CONFIRMED if explicit_use else LandscapeStatus.POSSIBLE
                evidence = f"Public source text references {label}."
                landscape.append(PLMLandscapeItem(system, status, evidence, source_name, source_url, "Unknown", "HIGH" if explicit_use else "MEDIUM"))
            else:
                landscape.append(PLMLandscapeItem(system, LandscapeStatus.NOT_FOUND))
        return landscape

    def _buying_signals(self, company_name: str, queries: list[str]) -> list[BuyingSignal]:
        articles = self._parallel_public_search(company_name, ("manufacturing plant expansion", "new product launch", "R&D engineering investment", "digital transformation Industry 4.0", "acquisition technology investment", "ERP CAD modernization"), queries, limit=4)
        articles.extend(self._parallel_google_news_search(company_name, ("plant expansion", "new product launch", "R&D engineering", "digital transformation", "acquisition", "technology modernization"), queries, limit=4))
        signals = []
        seen_urls = set()
        for article in articles:
            title = article.get("title", "").strip()
            url = article.get("url", "")
            if not title or not url or url in seen_urls:
                continue
            seen_urls.add(url)
            title_lower = title.lower()
            categories = [
                ("New manufacturing or plant activity", ("plant", "manufactur", "factory")),
                ("Engineering or R&D expansion", ("engineering", "r&d", "research")),
                ("Product launch or development", ("launch", "new model", "product")),
                ("Digital transformation or modernization", ("digital", "industry 4.0", "technology modernization")),
                ("Acquisition activity", ("acquire", "acquisition", "merger")),
            ]
            category = next(((label, words) for label, words in categories if any(word in title_lower for word in words)), None)
            if not category:
                continue
            raw_date = article.get("seendate", "")
            date = article.get("date", "") or (f"{raw_date[0:4]}-{raw_date[4:6]}-{raw_date[6:8]}" if len(raw_date) >= 8 else "Unknown")
            signals.append(BuyingSignal(category[0], date, f"Recent public coverage may warrant discovery on {category[0].lower()}.", article.get("domain", "Public publication"), url, title))
        return signals

    def _hiring_signals(self, company_name: str, website: str, official_text: str, queries: list[str]) -> list[HiringSignal]:
        if not website:
            return []
        careers_url = website.rstrip("/") + "/careers"
        careers_text, source_url = self._fetch_text(careers_url)
        text = f"{official_text} {careers_text}".lower()
        terms = [
            ("PLM-related hiring", ("plm", "product lifecycle management", "enovia", "3dexperience")),
            ("Engineering data or CAD hiring", ("engineering data", "cad", "digital engineering")),
            ("Product development hiring", ("product development", "configuration management", "bom")),
            ("Engineering expansion", ("engineering", "research and development", "r&d")),
        ]
        signals = [HiringSignal(label, "Unknown", "Company careers page", source_url) for label, keywords in terms if source_url and any(keyword in text for keyword in keywords)]
        articles = self._parallel_public_search(company_name, ("engineering jobs", "PLM PDM ENOVIA jobs", "CAD product development jobs", "digital engineering R&D jobs"), queries, limit=4)
        for article in articles:
            title = article.get("title", "")
            lower_title = title.lower()
            if any(term in lower_title for term in ("engineer", "engineering", "r&d", "research", "product development", "cad", "plm", "pdm")):
                signals.append(HiringSignal("Engineering hiring" if not any(term in lower_title for term in ("plm", "pdm", "enovia", "3dexperience")) else "PLM-related hiring", "Unknown", article.get("domain", "Public publication"), article.get("url", "")))
        unique = {}
        for signal in signals:
            unique[signal.signal] = signal
        return list(unique.values())

    def _complexity(self, text: str, source_name: str, source_url: str) -> EngineeringComplexity:
        lower_text = text.lower()
        evidence = []
        def assess(label: str, level: Opportunity, pattern: str) -> Opportunity:
            if level != Opportunity.UNKNOWN:
                evidence.append(Evidence(f"Public source text supports {label.lower()} ({pattern}).", source_name, source_url, label))
            return level

        product = self._level(3 if re.search(r"vehicle|aircraft|industrial|complex product|product portfolio", lower_text) else 1 if re.search(r"product|manufacturer", lower_text) else 0)
        engineering = self._level(3 if re.search(r"engineering.*(?:research|design|development)|research.*development", lower_text) else 1 if re.search(r"engineering|design|develop", lower_text) else 0)
        manufacturing = self._level(3 if re.search(r"multiple.*(?:plant|factory|facility)|manufactur.*(?:global|complex)|production facilities", lower_text) else 1 if re.search(r"manufactur|production|factory|plant", lower_text) else 0)
        categories = self._level(3 if re.search(r"passenger.*commercial|multiple product|portfolio|segments|divisions", lower_text) else 1 if "product" in lower_text else 0)
        multi_site = self._level(3 if re.search(r"multiple.*(?:site|location|facility|plant)|global operations|worldwide", lower_text) else 0)
        change = self._level(3 if re.search(r"engineering change|change management|configuration management|bill of materials|bom", lower_text) else 0)
        product = assess("Product complexity", product, "products or product portfolio")
        engineering = assess("Engineering complexity", engineering, "engineering, research, design, or development")
        manufacturing = assess("Manufacturing complexity", manufacturing, "manufacturing or production")
        categories = assess("Product categories", categories, "multiple products, segments, or portfolio")
        multi_site = assess("Multi-site engineering", multi_site, "multiple locations or global operations")
        change = assess("Change management complexity", change, "change, configuration, or BOM language")
        levels = [product, engineering, manufacturing, categories, multi_site, change]
        summary = "Public evidence indicates " + ", ".join(level.value.lower() for level in levels[:3]) + " complexity across product, engineering, and manufacturing dimensions."
        if not evidence:
            summary = "No reliable public evidence found."
        return EngineeringComplexity(product, engineering, manufacturing, categories, multi_site, change, summary, evidence)

    def _pain_points(self, text: str, source_name: str, source_url: str) -> list[PainPointIndicator]:
        patterns = {
            "Manual or disconnected processes": r"manual process|disconnected system|data silo|excel-based|spreadsheet",
            "Engineering change or BOM challenge": r"engineering change|change management|bill of materials|\bbom\b",
            "Document control or collaboration challenge": r"document control|multiple versions|poor collaboration|legacy system",
        }
        lower_text = text.lower()
        return [PainPointIndicator(f"Public source text references {label.lower()}.", source_name, source_url) for label, pattern in patterns.items() if re.search(pattern, lower_text)]

    def _wikipedia_summary(self, entity: dict) -> tuple[str, str]:
        title = entity.get("sitelinks", {}).get("enwiki", {}).get("title")
        if not title:
            return "", ""
        try:
            payload = self._get_json(self.wikipedia_api + quote(title.replace(" ", "_"), safe=""), {})
            return payload.get("extract", ""), payload.get("content_urls", {}).get("desktop", {}).get("page", "")
        except requests.RequestException:
            return "", ""

    @staticmethod
    def _format_quantity(value: dict) -> str:
        amount = str(value.get("amount", "")).lstrip("+").split(".")[0]
        if not amount:
            return "Unknown"
        try:
            number = int(amount)
            return f"{number:,}+" if number >= 1000 else str(number)
        except ValueError:
            return "Unknown"

    def research_company(self, company_name: str) -> ResearchResult:
        requested_name = company_name.strip()
        if not requested_name:
            raise ValueError("Company name is required.")

        cache_key = normalize_company_name(requested_name)
        if cache_key in self._cache:
            return self._cache[cache_key]

        unknown_signals = {signal: Confidence.UNKNOWN for signal in self.signal_names}
        try:
            search_result = self._search_entity(requested_name)
            if not search_result:
                fallback = self._fallback_public_result(requested_name)
                self._cache[cache_key] = fallback
                return fallback
            entity_id = search_result["id"]
            entity = self._get_entity(entity_id)
            company_label = entity.get("labels", {}).get("en", {}).get("value", search_result.get("label", requested_name))
            wikidata_url = f"https://www.wikidata.org/wiki/{entity_id}"
            summary, wikipedia_url = self._wikipedia_summary(entity)

            website_values = self._claim(entity, "P856")
            website = next((value for value in website_values if isinstance(value, str)), "")
            official_text, official_urls = self._official_pages(website)
            official_url = official_urls[0] if official_urls else ""
            queries: list[str] = []
            technology_articles: list[dict] = []
            technology_articles = self._parallel_public_search(company_label, tuple(f'"{platform}"' for platform in self.plm_systems), queries, limit=3)
            external_articles = technology_articles[:]
            external_articles.extend(self._parallel_public_search(company_label, ("engineering R&D", "product development manufacturing", "digital engineering technology"), queries, limit=4))
            web_suffixes = ["engineering R&D", "product development", "PLM PDM", "ENOVIA 3DEXPERIENCE", "Teamcenter Windchill", "CAD engineering jobs", "annual report investor presentation", "manufacturing expansion digital transformation", "LinkedIn company", "LinkedIn jobs engineering", "LinkedIn jobs PLM PDM", "LinkedIn jobs product development"]
            if website:
                domain = urlparse(website).netloc
                web_suffixes.extend((f"site:{domain} annual report investor presentation", f"site:{domain} careers engineering", f"site:{domain} manufacturing R&D technology"))
            web_articles = self._parallel_web_search(company_label, tuple(web_suffixes), queries, limit=4)
            external_articles.extend(web_articles)
            external_articles.extend(self._parallel_google_news_search(company_label, ("manufacturing", "engineering R&D", "product launch", "digital transformation", "technology investment", "PLM PDM"), queries, limit=4))
            gemini_articles = self._gemini_grounded_search(company_label)
            external_articles.extend(gemini_articles)
            external_text = " ".join(f"{article.get('title', '')} {article.get('snippet', '')}" for article in external_articles)
            combined_text = f"{summary} {official_text} {external_text}".lower()

            industry_ids = [value["id"] for value in self._claim(entity, "P452") if isinstance(value, dict) and "id" in value]
            headquarters_ids = [value["id"] for value in self._claim(entity, "P159") if isinstance(value, dict) and "id" in value]
            labels = self._labels(industry_ids + headquarters_ids)
            raw_industry = labels.get(industry_ids[0], "Unknown") if industry_ids else "Unknown"
            industry = self._normalize_industry(raw_industry, combined_text)
            headquarters = labels.get(headquarters_ids[0], "Unknown") if headquarters_ids else "Unknown"
            employee_values = [value for value in self._claim(entity, "P1128") if isinstance(value, dict)]
            employee_range = self._employee_range(self._format_quantity(employee_values[-1]) if employee_values else "Unknown", combined_text)
            source_url = wikipedia_url or wikidata_url
            evidence: list[Evidence] = []
            if summary and wikipedia_url:
                evidence.append(Evidence(f"Public company summary: {summary}", "Wikipedia", wikipedia_url, "Company overview"))
            if website:
                evidence.append(Evidence("A first-party website is listed for the company.", "Wikidata", wikidata_url, "Website"))
            if industry != "Unknown":
                evidence.append(Evidence(f"Wikidata classifies the company under {industry}.", "Wikidata", wikidata_url, "Industry"))
            if headquarters != "Unknown":
                evidence.append(Evidence(f"Wikidata lists {headquarters} as a headquarters location.", "Wikidata", wikidata_url, "Headquarters"))
            if employee_range != "Unknown":
                evidence.append(Evidence(f"Wikidata reports approximately {employee_range} employees.", "Wikidata", wikidata_url, "Employees"))

            source_texts = [summary.lower(), official_text.lower(), external_text.lower(), industry.lower()]
            manufacturing, manufacturing_confidence = self._synthesized_state([
                bool(re.search(r"manufactur|production|factory|plant|production line|capacity", text)) for text in source_texts
            ])
            engineering, engineering_confidence = self._synthesized_state([
                bool(re.search(r"engineer|research|r&d|design|technical center|innovation|testing|patent|cad", text)) for text in source_texts
            ])
            product_development, product_confidence = self._synthesized_state([
                bool(re.search(r"develop|product|model|vehicle|portfolio|launch|prototype|platform", text)) for text in source_texts
            ])
            physical_products, physical_confidence = self._synthesized_state([
                bool(re.search(r"manufacturer|vehicle|product|equipment|automotive|chemical|pharmaceutical|machinery", text)) for text in source_texts
            ])
            for label, state in (("Manufacturing", manufacturing), ("Engineering / R&D", engineering), ("Product development", product_development), ("Physical products", physical_products)):
                if state == TriState.YES and source_url:
                    evidence.append(Evidence(f"Public source text supports {label.lower()} activity.", "Public company summary", source_url, label))

            signals = dict(unknown_signals)
            for signal in self.signal_names:
                if re.search(rf"(?<!\w){re.escape(signal.lower())}(?!\w)", combined_text):
                    signals[signal] = Confidence.POSSIBLE
                    signal_source = official_url or source_url
                    if signal_source:
                        evidence.append(Evidence(f"Public source text contains the term {signal}.", "Company website" if official_url else "Wikipedia", signal_source, signal))

            for article in external_articles[:12]:
                article_title = article.get("title", "").strip()
                article_url = article.get("url", "")
                if article_title and article_url:
                    statement = f"External source reports: {article_title}"
                    if article.get("snippet"):
                        statement += f". {article['snippet']}"
                    evidence.append(Evidence(statement, self._source_name(article), article_url, "External research", "MEDIUM", article.get("date", "Unknown")))

            primary_source_name = "Company website" if official_url else "Wikipedia"
            primary_source_url = official_url or source_url
            plm_landscape = self._plm_landscape(combined_text, primary_source_name, primary_source_url, searched=True)
            buying_signals = self._buying_signals(company_label, queries)
            hiring_signals = self._hiring_signals(company_label, website, official_text, queries)
            complexity = self._complexity(combined_text, primary_source_name, primary_source_url)
            pain_points = self._pain_points(combined_text, primary_source_name, primary_source_url)
            domain_text = f"{combined_text} {industry.lower()}"
            domain_signals = {
                "MSDS / SDS": Confidence.POSSIBLE if re.search(r"\bmsds?\b|safety data sheet|chemical safety|product stewardship|regulatory affairs|chemical|paint|coating|pharmaceutical", domain_text) else Confidence.UNKNOWN,
                "Formulation": Confidence.POSSIBLE if re.search(r"formulat|coating|paint|specialty chemical|chemical|pharmaceutical", domain_text) else Confidence.UNKNOWN,
                "Digital transformation": Confidence.POSSIBLE if re.search(r"digital transformation|industry 4\.0|digital engineering|technology modernization", combined_text) else Confidence.UNKNOWN,
                "PLM need indicators": Confidence.POSSIBLE if pain_points or complexity.engineering_complexity in {Opportunity.HIGH, Opportunity.MEDIUM} else Confidence.UNKNOWN,
            }
            assessment_confidence = {
                "Manufacturing": manufacturing_confidence,
                "Engineering / R&D": engineering_confidence,
                "Product development": product_confidence,
                "Physical products": physical_confidence,
                "Industry": "HIGH" if industry != "Unknown" else "LOW",
                "Employees": "HIGH" if employee_range != "Unknown" else "LOW",
            }
            for domain, confidence in domain_signals.items():
                if confidence != Confidence.UNKNOWN and primary_source_url:
                    evidence.append(Evidence(f"Public source text supports {domain.lower()} relevance.", primary_source_name, primary_source_url, domain))

            note = "Sources were retrieved live from public endpoints. Verify time-sensitive details before outreach."
            if not summary and not official_text:
                note = "Structured company data was found, but narrative public sources were unavailable."
            result = ResearchResult(
                overview=CompanyOverview(
                    name=company_label,
                    website=website,
                    industry=industry,
                    headquarters=headquarters,
                    employee_range=employee_range,
                    description=summary or "No reliable public evidence found.",
                ),
                manufacturing=manufacturing,
                engineering_rd=engineering,
                product_development=product_development,
                physical_products=physical_products,
                technology_signals=signals,
                domain_signals=domain_signals,
                evidence=evidence,
                plm_landscape=plm_landscape,
                buying_signals=buying_signals,
                hiring_signals=hiring_signals,
                engineering_complexity=complexity,
                pain_points=pain_points,
                assessment_confidence=assessment_confidence,
                research_performed={
                    "Queries searched": queries,
                    "Sources checked": list(dict.fromkeys(["Wikidata", "Wikipedia", "LinkedIn public search"] + (["Gemini + Google Search grounding"] if settings.gemini_api_key else []) + official_urls + [article.get("domain", "Public publication") for article in external_articles if article.get("domain")])),
                    "Technology platforms checked": list(self.plm_systems),
                    "Job searches performed": [query for query in queries if "job" in query.lower() or "hiring" in query.lower()],
                },
                useful_result_count=len(evidence),
                provider_name=self.name,
                research_note=note,
            )
            self._cache[cache_key] = result
            return result
        except (requests.RequestException, KeyError, ValueError) as error:
            return ResearchResult(
                overview=CompanyOverview(name=requested_name),
                technology_signals=unknown_signals,
                provider_name=self.name,
                research_note=f"Live research could not be completed: {error}. No reliable public evidence found.",
            )


class DemoResearchProvider(CompanyResearchProvider):
    """Offline provider for a usable foundation without pretending to browse the web."""

    name = "Demo research provider"

    def research_company(self, company_name: str) -> ResearchResult:
        normalized = normalize_company_name(company_name)
        if normalized == "tata motors":
            return ResearchResult(
                overview=CompanyOverview(
                    name="Tata Motors",
                    website="https://www.tatamotors.com/",
                    industry="Automotive manufacturing",
                    headquarters="Mumbai, India",
                    employee_range="100,000+",
                    description="Automotive manufacturer developing and producing passenger and commercial vehicles.",
                ),
                manufacturing=TriState.YES,
                engineering_rd=TriState.YES,
                product_development=TriState.YES,
                physical_products=TriState.YES,
                technology_signals={
                    "PLM": Confidence.POSSIBLE,
                    "PDM": Confidence.UNKNOWN,
                    "ENOVIA": Confidence.UNKNOWN,
                    "3DEXPERIENCE": Confidence.UNKNOWN,
                    "Dassault Systèmes": Confidence.UNKNOWN,
                    "SAP": Confidence.POSSIBLE,
                    "CAD": Confidence.LIKELY,
                    "ERP": Confidence.POSSIBLE,
                    "Engineering Data Management": Confidence.POSSIBLE,
                },
                evidence=[
                    Evidence(
                        "Company describes vehicle design, development, and manufacturing activities.",
                        "Tata Motors official website",
                        "https://www.tatamotors.com/",
                        "Manufacturing / engineering",
                    ),
                    Evidence(
                        "The company publishes a broad passenger and commercial vehicle product portfolio.",
                        "Tata Motors official website",
                        "https://www.tatamotors.com/",
                        "Physical products",
                    ),
                ],
                provider_name=self.name,
                research_note="Demo fixture: verify all signals and current company details before outreach.",
            )

        return ResearchResult(
            overview=CompanyOverview(name=company_name.strip()),
            technology_signals={signal: Confidence.UNKNOWN for signal in [
                "PLM", "PDM", "ENOVIA", "3DEXPERIENCE", "Dassault Systèmes", "SAP", "CAD", "ERP", "Engineering Data Management"
            ]},
            provider_name=self.name,
            research_note="The demo provider has no verified fixture for this company.",
        )


def get_research_provider() -> CompanyResearchProvider:
    """Return the configured provider without coupling the UI to provider selection."""
    providers = {"demo": DemoResearchProvider, "live": LiveResearchProvider}
    provider_class = providers.get(settings.research_provider, DemoResearchProvider)
    return provider_class()


def research_company(company_name: str) -> ResearchResult:
    return get_research_provider().research_company(company_name)