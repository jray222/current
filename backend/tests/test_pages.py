from app.services.pages import extract_article_links, extract_meta

HTML_LISTING = """<!DOCTYPE html>
<html>
<body>
  <header>
    <a href="/category/tech">Tech Section</a>
    <a href="/privacy-policy">Privacy Policy</a>
    <a href="https://external-ad.com/click">Sponsored Link</a>
  </header>
  <main>
    <article>
      <h2><a href="/2026/11/10/quantum-breakthrough-announced">Quantum Breakthrough Announced by Researchers</a></h2>
    </article>
    <article>
      <h2><a href="/news/ai-models-autonomous-agents">New Generation of Autonomous AI Agents Unveiled</a></h2>
    </article>
    <article>
      <h2><a href="/tag/ai">More AI Tags</a></h2>
    </article>
  </main>
</body>
</html>
"""

HTML_ARTICLE_JSONLD = """<!DOCTYPE html>
<html>
<head>
  <title>Fallback Title</title>
  <script type="application/ld+json">
  {
    "@context": "https://schema.org",
    "@type": "NewsArticle",
    "headline": "Quantum Breakthrough Announced by Researchers",
    "description": "Scientists demonstrate unprecedented fault-tolerant qubits.",
    "datePublished": "2026-11-10T15:30:00Z",
    "author": {
      "@type": "Person",
      "name": "Alice Walker"
    },
    "image": "https://news.example.com/images/quantum.jpg",
    "keywords": ["quantum", "physics", "computing"]
  }
  </script>
</head>
<body>
  <h1>Quantum Breakthrough Announced by Researchers</h1>
</body>
</html>
"""

HTML_ARTICLE_OG = """<!DOCTYPE html>
<html>
<head>
  <title>Page Title</title>
  <meta property="og:title" content="OpenGraph Headline" />
  <meta property="og:description" content="OpenGraph description summary." />
  <meta property="og:image" content="/images/og.png" />
  <meta property="article:published_time" content="2026-11-09T08:00:00Z" />
  <meta property="article:author" content="Bob Evans" />
  <link rel="amphtml" href="https://news.example.com/article/amp" />
</head>
<body>
  <p>Article body</p>
</body>
</html>
"""


def test_extract_article_links():
    links = extract_article_links(HTML_LISTING, base_url="https://news.example.com")
    assert len(links) == 2
    assert "https://news.example.com/2026/11/10/quantum-breakthrough-announced" in links
    assert "https://news.example.com/news/ai-models-autonomous-agents" in links
    # Ensure privacy, tag, category, external ads are filtered
    for link in links:
        assert "category" not in link
        assert "privacy" not in link
        assert "tag" not in link
        assert "external-ad.com" not in link


def test_extract_article_links_custom_pattern():
    pattern = r"/2026/\d{2}/\d{2}/"
    links = extract_article_links(HTML_LISTING, base_url="https://news.example.com", link_pattern=pattern)
    assert len(links) == 1
    assert links[0] == "https://news.example.com/2026/11/10/quantum-breakthrough-announced"


def test_extract_meta_jsonld():
    meta = extract_meta(HTML_ARTICLE_JSONLD, page_url="https://news.example.com/article1")
    assert meta["title"] == "Quantum Breakthrough Announced by Researchers"
    assert "fault-tolerant" in meta["summary"]
    assert meta["author"] == "Alice Walker"
    assert meta["image_remote_url"] == "https://news.example.com/images/quantum.jpg"
    assert meta["published_at"] is not None
    assert "quantum" in meta["feed_tags"]


def test_extract_meta_opengraph():
    meta = extract_meta(HTML_ARTICLE_OG, page_url="https://news.example.com/article2")
    assert meta["title"] == "OpenGraph Headline"
    assert meta["summary"] == "OpenGraph description summary."
    assert meta["image_remote_url"] == "https://news.example.com/images/og.png"
    assert meta["author"] == "Bob Evans"
    assert meta["amp_url"] == "https://news.example.com/article/amp"
