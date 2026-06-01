from hashlib import sha256
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "fbclid",
    "gclid",
    "msclkid",
    "ref",
    "ref_src",
}
SEARCH_HOSTS = ("google.", "bing.com", "duckduckgo.com", "search.brave.com")


def normalize_url(url: str) -> str:
    if not url:
        return ""
    try:
        parsed = urlparse(url.strip())
    except Exception:
        return url.strip()
    scheme = parsed.scheme.lower()
    hostname = (parsed.hostname or "").lower()
    netloc = hostname
    if parsed.port:
        netloc = f"{netloc}:{parsed.port}"
    path = parsed.path or "/"
    if path != "/":
        path = path.rstrip("/")
    query_items = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key.lower() not in TRACKING_PARAMS
    ]
    query = urlencode(sorted(query_items), doseq=True)
    return urlunparse((scheme, netloc, path, "", query, ""))


def url_hash(normalized_url: str) -> str:
    return sha256(normalized_url.encode("utf-8")).hexdigest()[:24]


def classify_url_page_type(url: str, title: str | None = None, metadata: dict | None = None) -> dict:
    metadata = metadata or {}
    normalized = normalize_url(url)
    parsed = urlparse(normalized)
    host = parsed.hostname or ""
    path = parsed.path or "/"
    title_text = (title or "").lower()

    if _is_search(host, path, parsed.query):
        return {"page_type": "search", "reason": "Search URL."}
    if path in {"", "/"}:
        return {"page_type": "homepage", "reason": "Root/home page."}
    if any(word in path.lower() for word in ["/login", "/signin", "/sign-in", "/checkout", "/settings", "/account"]):
        return {"page_type": "action", "reason": "Action/account page."}
    if "huggingface.co" in host and path.startswith(("/datasets/", "/models/", "/spaces/", "/papers/", "/docs/")):
        return {"page_type": "content", "reason": "Hugging Face content page."}
    if "patents.google.com" in host and path.startswith("/patent/"):
        return {"page_type": "content", "reason": "Patent page."}
    if "github.com" in host:
        parts = [part for part in path.split("/") if part]
        if len(parts) >= 4 and parts[2] in {"issues", "pull"}:
            return {"page_type": "action", "reason": "GitHub issue or pull request."}
        if len(parts) >= 3 and parts[2] in {"issues", "pulls", "actions", "projects"}:
            return {"page_type": "listing", "reason": "GitHub listing page."}
        if len(parts) >= 2:
            return {"page_type": "content", "reason": "GitHub repository page."}
    if "atlassian.net" in host or "jira" in host or "/browse/" in path:
        return {"page_type": "action", "reason": "Jira issue/action page."}
    if any(marker in host for marker in ["docs.", "developer.", "readthedocs.io"]) or "documentation" in title_text:
        return {"page_type": "content", "reason": "Documentation page."}
    if any(marker in path.lower() for marker in ["/search", "/topics", "/explore", "/feed", "/home", "/dashboard", "/issues", "/pulls"]):
        return {"page_type": "listing", "reason": "Listing or dashboard page."}
    if metadata.get("selected_text_included") or metadata.get("text_excerpt_included"):
        return {"page_type": "content", "reason": "Readable page context included."}
    return {"page_type": "unknown", "reason": "No strong page type signal."}


def _is_search(host: str, path: str, query: str) -> bool:
    if not query:
        return False
    if "q=" not in query and "query=" not in query and "search=" not in query:
        return False
    return any(marker in host for marker in SEARCH_HOSTS) or path.startswith("/search")
