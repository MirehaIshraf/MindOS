from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse


IMPORTANT_DOMAINS = [
    "github.com",
    "gitlab.com",
    "bitbucket.org",
    "stackoverflow.com",
    "stackexchange.com",
    "readthedocs.io",
    "dev.to",
    "arxiv.org",
    "scholar.google.com",
    "patents.google.com",
    "lens.org",
    "ieee.org",
    "acm.org",
    "springer.com",
    "huggingface.co",
    "ollama.com",
    "platform.openai.com",
    "docs.anthropic.com",
    "cloud.google.com",
    "aws.amazon.com",
    "learn.microsoft.com",
    "azure.microsoft.com",
    "atlassian.net",
    "linear.app",
]
NOISY_DOMAINS = ["youtube.com", "facebook.com", "instagram.com", "x.com", "twitter.com", "netflix.com", "spotify.com", "web.whatsapp.com"]
PRIVATE_DOMAINS = ["accounts.google.com", "mail.google.com", "paypal.com", "stripe.com"]
IMPORTANT_KEYWORDS = [
    "api",
    "docs",
    "documentation",
    "error",
    "exception",
    "stack trace",
    "github",
    "pull request",
    "issue",
    "commit",
    "jira",
    "ticket",
    "patent",
    "arxiv",
    "paper",
    "research",
    "webrtc",
    "kurento",
    "mediasoup",
    "spring",
    "fastapi",
    "chromadb",
    "ollama",
    "embedding",
    "llm",
    "ai",
    "security",
    "cve",
    "auth",
    "jwt",
    "docker",
    "kubernetes",
    "aws",
    "azure",
]


@dataclass(frozen=True)
class BrowserImportanceResult:
    importance: str
    reason: str
    category: str
    should_capture_context: bool


class BrowserImportanceService:
    def classify_browser_page(
        self,
        url: str,
        title: str = "",
        content_preview: str = "",
        metadata: dict | None = None,
    ) -> BrowserImportanceResult:
        metadata = metadata or {}
        domain = str(metadata.get("domain") or domain_from_url(url)).lower()
        text = f"{url} {title} {content_preview}".lower()
        ignored_domains = [str(item).lower() for item in metadata.get("ignored_domains", []) if str(item).strip()]
        important_domains = [str(item).lower() for item in metadata.get("important_domains", []) if str(item).strip()]

        if is_private_url(url, domain, text):
            return BrowserImportanceResult("private", "Sensitive/login/payment page blocked.", "private", False)
        if any(marker in domain for marker in ignored_domains):
            return BrowserImportanceResult("noisy", "Domain is in ignored domains.", "unknown", False)
        if is_search_url(url):
            return BrowserImportanceResult("normal", "Search result page; store query only.", "search", False)
        if any(marker in domain for marker in important_domains):
            return BrowserImportanceResult("important", "Domain is user-marked important.", "research", True)
        if any(marker in domain for marker in NOISY_DOMAINS):
            return BrowserImportanceResult("noisy", "Noisy or entertainment domain.", "entertainment", False)
        huggingface_category = huggingface_category_for(url, domain)
        if huggingface_category:
            return BrowserImportanceResult("important", "Hugging Face AI/model/dataset page", huggingface_category, True)
        category = category_for(domain, text)
        if category != "unknown":
            return BrowserImportanceResult("important", f"Matched {category} work/research pattern.", category, True)
        if any(keyword in text for keyword in IMPORTANT_KEYWORDS):
            return BrowserImportanceResult("important", "Matched work/research keyword.", "research", True)
        return BrowserImportanceResult("normal", "No strong work/research signal.", "unknown", False)

    def extract_search_query(self, url: str) -> tuple[str | None, str | None]:
        parsed = urlparse(url)
        domain = parsed.hostname or ""
        params = parse_qs(parsed.query)
        query = (params.get("q") or [""])[0].strip()
        if not query:
            return None, None
        if "google." in domain and parsed.path.startswith("/search"):
            return query, "google"
        if "bing.com" in domain and parsed.path.startswith("/search"):
            return query, "bing"
        if "duckduckgo.com" in domain:
            return query, "duckduckgo"
        if "search.brave.com" in domain:
            return query, "brave"
        return None, None


def is_search_url(url: str) -> bool:
    query, _ = browser_importance_service.extract_search_query(url)
    return bool(query)


def is_private_url(url: str, domain: str, text: str) -> bool:
    lowered = url.lower()
    if lowered.startswith(("chrome:", "edge:", "about:", "file:")):
        return True
    if any(marker in domain for marker in PRIVATE_DOMAINS):
        return True
    return any(marker in text for marker in ["login", "signin", "sign-in", "checkout", "billing", "payment", "bank"])


def category_for(domain: str, text: str) -> str:
    if any(marker in domain for marker in ["github.com", "gitlab.com", "bitbucket.org"]):
        return "github"
    if "stackoverflow.com" in domain or "stackexchange.com" in domain:
        return "stackoverflow"
    if "atlassian.net" in domain or "jira" in domain:
        return "jira"
    if "patents.google.com" in domain or "lens.org" in domain:
        return "patent"
    if any(marker in domain for marker in ["arxiv.org", "scholar.google.com", "ieee.org", "acm.org", "springer.com"]):
        return "research"
    if any(marker in domain for marker in ["platform.openai.com", "docs.anthropic.com", "huggingface.co", "ollama.com"]):
        return "ai"
    if any(marker in domain for marker in ["cloud.google.com", "aws.amazon.com", "learn.microsoft.com", "azure.microsoft.com"]):
        return "cloud"
    if domain.startswith("docs.") or domain.startswith("developer.") or "readthedocs.io" in domain or "documentation" in text:
        return "docs"
    return "unknown"


def huggingface_category_for(url: str, domain: str) -> str | None:
    if "huggingface.co" not in domain:
        return None
    try:
        path = urlparse(url).path.lower()
    except Exception:
        return "ai"
    if path.startswith("/datasets/"):
        return "ai_dataset"
    if path.startswith("/models/"):
        return "ai_model"
    if path.startswith("/docs/"):
        return "ai_docs"
    if path.startswith("/spaces/"):
        return "ai"
    if path.startswith("/papers/"):
        return "research"
    return "ai"


def domain_from_url(url: str) -> str:
    try:
        return urlparse(url).hostname or ""
    except Exception:
        return ""


browser_importance_service = BrowserImportanceService()
