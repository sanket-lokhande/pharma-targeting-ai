from __future__ import annotations

import json
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from typing import List


def _http_get(url: str, timeout: int = 8) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) PharmaTargetingAI/1.0",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def _fetch_google_news_titles(query: str, max_items: int = 3) -> List[str]:
    encoded = urllib.parse.quote_plus(query)
    rss_url = f"https://news.google.com/rss/search?q={encoded}"
    xml_text = _http_get(rss_url)

    root = ET.fromstring(xml_text)
    items = root.findall(".//item/title")

    titles: List[str] = []
    for item in items[:max_items]:
        text = (item.text or "").strip()
        if text:
            titles.append(text)
    return titles


def _fetch_clinical_trials_count(query: str) -> int:
    encoded = urllib.parse.quote_plus(query)
    url = (
        "https://clinicaltrials.gov/api/query/study_fields"
        f"?expr={encoded}&fields=NCTId&min_rnk=1&max_rnk=1&fmt=json"
    )
    payload = _http_get(url)
    data = json.loads(payload)
    return int(data.get("StudyFieldsResponse", {}).get("NStudiesFound", 0))


def fetch_live_market_insights(disease_market: str) -> List[str]:
    """Fetch lightweight live web context to enrich business insights."""
    market = disease_market.strip()
    if not market:
        return []

    insights: List[str] = []

    try:
        trials_count = _fetch_clinical_trials_count(market)
        insights.append(
            f"Live signal: ClinicalTrials.gov currently lists about {trials_count} studies for '{market}'."
        )
    except Exception:
        insights.append("Live signal: Could not fetch ClinicalTrials.gov study count right now.")

    try:
        titles = _fetch_google_news_titles(f"{market} pharma market")
        if titles:
            insights.append("Live signal: Recent market headlines include:")
            for title in titles:
                insights.append(f"- {title}")
        else:
            insights.append("Live signal: No recent market headlines were found for this query.")
    except Exception:
        insights.append("Live signal: Could not fetch recent market headlines right now.")

    return insights
