from app.services.feeds import parse_feed_bytes, discover_feed_urls, clean_html_snippet

SAMPLE_RSS = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/">
  <channel>
    <title>Sample Tech Feed</title>
    <link>https://techfeed.example.com</link>
    <description>Latest tech dispatches</description>
    <item>
      <title>Autonomous Drones Set New Speed Record</title>
      <link>https://techfeed.example.com/articles/drones</link>
      <description>&lt;p&gt;Engineers demonstrated high-speed navigation today.&lt;/p&gt;</description>
      <author>Jane Doe</author>
      <pubDate>Mon, 10 Nov 2026 14:00:00 GMT</pubDate>
      <category>Hardware</category>
      <category>Robotics</category>
      <media:content url="https://techfeed.example.com/images/drone.jpg" medium="image" />
    </item>
  </channel>
</rss>
"""

SAMPLE_ATOM = b"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Sample Atom Feed</title>
  <link href="https://atom.example.com"/>
  <entry>
    <title>Quantum Computing Breakthrough Announced</title>
    <link href="https://atom.example.com/quantum"/>
    <summary>A 1000-qubit processor shows error suppression.</summary>
    <updated>2026-11-10T12:00:00Z</updated>
    <author><name>Dr. Smith</name></author>
    <category term="Quantum"/>
  </entry>
</feed>
"""

SAMPLE_HTML = """<!DOCTYPE html>
<html>
<head>
  <title>News Publication</title>
  <link rel="alternate" type="application/rss+xml" title="Main RSS Feed" href="/rss.xml" />
  <link rel="alternate" type="application/atom+xml" title="Atom Feed" href="https://news.example.com/atom" />
</head>
<body>
  <h1>Welcome to the News</h1>
</body>
</html>
"""


def test_clean_html_snippet():
    raw = "<p>Hello &amp; <b>welcome</b> to the &quot;news&quot;!</p>"
    clean = clean_html_snippet(raw)
    assert clean == 'Hello & welcome to the "news"!'


def test_parse_rss_bytes():
    info, entries = parse_feed_bytes(SAMPLE_RSS, fallback_url="https://techfeed.example.com")
    assert info["title"] == "Sample Tech Feed"
    assert len(entries) == 1

    entry = entries[0]
    assert entry.title == "Autonomous Drones Set New Speed Record"
    assert entry.url == "https://techfeed.example.com/articles/drones"
    assert "high-speed navigation" in entry.summary
    assert entry.image_remote_url == "https://techfeed.example.com/images/drone.jpg"
    assert "Hardware" in entry.tags


def test_parse_atom_bytes():
    info, entries = parse_feed_bytes(SAMPLE_ATOM, fallback_url="https://atom.example.com")
    assert info["title"] == "Sample Atom Feed"
    assert len(entries) == 1

    entry = entries[0]
    assert entry.title == "Quantum Computing Breakthrough Announced"
    assert entry.url == "https://atom.example.com/quantum"
    assert "1000-qubit" in entry.summary
    assert "Quantum" in entry.tags


def test_discover_feed_urls():
    urls = discover_feed_urls(SAMPLE_HTML, base_url="https://news.example.com")
    assert len(urls) == 2
    assert urls[0] == "https://news.example.com/rss.xml"
    assert urls[1] == "https://news.example.com/atom"
