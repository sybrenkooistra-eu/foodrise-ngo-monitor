"""
FoodRise NGO Monitor — test_sources.py (final)

Gebruik:
    python3 test_sources.py              # alle bronnen
    python3 test_sources.py "grain"      # één bron (case-insensitief)
"""

import sys
import re
import feedparser
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

SOURCES = [

    # ══════════════════════════════════════════
    # RSS
    # ══════════════════════════════════════════
    {"name": "Changing Markets",
     "type": "rss",
     "url": "https://changingmarkets.org/feed/"},

    {"name": "Foodrise EU",
     "type": "rss",
     "url": "https://foodrise.eu/feed/"},

    {"name": "GRAIN",
     "type": "rss",
     "url": "https://grain.org/en/home/entries.rss"},

    # ══════════════════════════════════════════
    # HTML — css selectors
    # ══════════════════════════════════════════
    {"name": "ClientEarth",
     "type": "html",
     "url": "https://www.clientearth.org/latest/news/",
     "item_sel": "a.newsitem, a.item",
     "title_sel": "h2, h3, .title",
     "link_sel": None},

    {"name": "IATP",
     "type": "html",
     "url": "https://www.iatp.org/publications/press_releases",
     "item_sel": "article, .view-row, .teaser",
     "title_sel": "h2, h3, .title",
     "link_sel": "a",
     "dedupe": True,
     "timeout": 30},

    {"name": "Ecologistas en Acción",
     "type": "html",
     "url": "https://www.ecologistasenaccion.org/",
     "item_sel": "article, .post, .entry",
     "title_sel": "h2, h3, .entry-title",
     "link_sel": "a"},

    {"name": "Greenpeace Aotearoa",
     "type": "html",
     "url": "https://www.greenpeace.org/aotearoa/news/",
     "item_sel": ".post",
     "title_sel": "h2, h3",
     "link_sel": "a"},

    # ══════════════════════════════════════════
    # HTML card links (href aanwezig, titel via slug)
    # ══════════════════════════════════════════
    {"name": "Mighty Earth",
     "type": "html_card_links",
     "url": "https://mightyearth.org/news/",
     "link_sel": "a.card-link"},

    # ══════════════════════════════════════════
    # HTML links (patroon op URL)
    # ══════════════════════════════════════════
    {"name": "Milieudefensie",
     "type": "html_links",
     "url": "https://milieudefensie.nl/actueel/",
     "link_pattern": r"milieudefensie\.nl/actueel/[^#?]+$",
     "exclude_pattern": r"milieudefensie\.nl/actueel/$"},

    {"name": "Greenpeace Nordic",
     "type": "html_links",
     "url": "https://www.greenpeace.org/denmark/pressemeddelelse/",
     "link_pattern": r"greenpeace\.org/denmark/(pressemeddelelse|nyhed)/[^#?]+/[^#?]+/$"},

    {"name": "Justicia Alimentaria",
     "type": "html_links",
     "url": "https://justiciaalimentaria.org/sala-de-prensa/",
     "link_pattern": r"justiciaalimentaria\.org/[a-z0-9-]{10,}/$",
     "exclude_pattern": r"/(que-hacemos|unete|hazte|donativo|voluntariado|legado|quienes|"
                         r"sala-de-prensa|actualidad|videos|observatorio|contacto|aviso|"
                         r"politica|cookies|transparencia|alianzas|trabaja|ca/)"},

    {"name": "Seastemik",
     "type": "html_links",
     "url": "https://seastemik.org/presse-and-actu",
     "link_pattern": r"https?://",
     "exclude_pattern": r"seastemik\.org|helloasso\.com|facebook|twitter|instagram|"
                         r"linkedin|youtube|mailto"},

    # ══════════════════════════════════════════
    # Skip — onoplosbaar zonder headless browser
    # ══════════════════════════════════════════
    {"name": "Naturskyddsföreningen",
     "type": "skip",
     "reason": "Volledig JS. Geen statische nieuwsitems beschikbaar."},

    {"name": "Greenpeace Canada",
     "type": "skip",
     "reason": "Volledig JS. Nieuws laadt niet in statische HTML."},

    {"name": "Food Foundation",
     "type": "skip",
     "reason": "Webflow zonder RSS. → nieuwsbrief op foodfoundation.org.uk"},

    {"name": "Friends of the Earth",
     "type": "skip",
     "reason": "SSL-fout op macOS Python. Werkt in GitHub Actions (Ubuntu)."},

    {"name": "CIWF",
     "type": "skip",
     "reason": "429 rate limiting. Testen in GitHub Actions."},
]


def abs_url(href, base):
    if not href or href.startswith("#") or href.startswith("mailto"):
        return ""
    if href.startswith("http"):
        return href
    parsed = urlparse(base)
    if href.startswith("/"):
        return f"{parsed.scheme}://{parsed.netloc}{href}"
    return base.rstrip("/") + "/" + href


def slug_to_title(url):
    path = urlparse(url).path.rstrip("/")
    slug = path.split("/")[-1]
    return slug.replace("-", " ").title()


def fetch(url, timeout=15):
    return requests.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True)


def test_rss(source):
    feed = feedparser.parse(source["url"])
    status = feed.get("status", "?")
    entries = feed.entries
    if status == 200 and entries:
        print(f"  ✅ RSS — {len(entries)} items")
        for e in entries[:3]:
            print(f"    • {e.get('title','?')[:80]}")
            print(f"      {e.get('link','?')[:80]}")
    elif status == 200:
        print(f"  ⚠️  RSS 200 maar geen items")
    else:
        print(f"  ❌ RSS mislukt — HTTP {status}")


def test_html(source):
    try:
        r = fetch(source["url"], timeout=source.get("timeout", 15))
        r.raise_for_status()
    except Exception as e:
        print(f"  ❌ HTTP-fout: {e}")
        return

    soup = BeautifulSoup(r.text, "html.parser")
    item_sel  = source.get("item_sel", "article")
    title_sel = source.get("title_sel", "h2, h3")
    link_sel  = source.get("link_sel", "a")
    dedupe    = source.get("dedupe", False)

    containers = soup.select(item_sel)
    if not containers:
        print(f"  ⚠️  Selector '{item_sel}' vond niets")
        for fb in ["article", ".post", ".card", "li"]:
            found = soup.select(fb)
            if found:
                print(f"     Fallback '{fb}': {len(found)}")
        return

    print(f"  ✅ Selector '{item_sel}' — {len(containers)} containers")
    seen_urls = set()
    parsed = 0
    for container in containers[:10]:
        if link_sel is None:
            link_tag = container if container.name == "a" else container.find("a")
        else:
            link_tag = container.select_one(link_sel)
        href = abs_url(link_tag.get("href", "") if link_tag else "", source["url"])
        if not href or (dedupe and href in seen_urls):
            continue
        seen_urls.add(href)
        title_tag = container.select_one(title_sel) if title_sel else None
        title = (title_tag or link_tag or container).get_text(strip=True)[:90]
        if len(title) < 4:
            continue
        print(f"    • {title}")
        print(f"      {href[:90]}")
        parsed += 1
        if parsed >= 5:
            break
    if parsed == 0:
        print(f"  ⚠️  Geen bruikbare items")
        print(f"     Eerste container: {str(containers[0])[:200]}")


def test_html_links(source):
    try:
        r = fetch(source["url"])
        r.raise_for_status()
    except Exception as e:
        print(f"  ❌ HTTP-fout: {e}")
        return

    soup = BeautifulSoup(r.text, "html.parser")
    include_pat = re.compile(source["link_pattern"])
    exclude_pat = re.compile(source.get("exclude_pattern", "^$"))

    seen = set()
    results = []
    for a in soup.find_all("a", href=True):
        full = abs_url(a["href"], source["url"])
        if not full or full in seen:
            continue
        if include_pat.search(full) and not exclude_pat.search(full):
            title = a.get_text(strip=True)[:90]
            if len(title) > 4:
                seen.add(full)
                results.append((title, full))

    if results:
        print(f"  ✅ Link-patroon — {len(results)} items")
        for title, url in results[:5]:
            print(f"    • {title}")
            print(f"      {url[:90]}")
    else:
        print(f"  ⚠️  Geen links met patroon")
        all_links = [(a.get_text(strip=True)[:40], abs_url(a["href"], source["url"]))
                     for a in soup.find_all("a", href=True)
                     if abs_url(a["href"], source["url"])][:6]
        print(f"     Sample:")
        for t, u in all_links:
            print(f"     {u[:80]}  ({t})")


def test_html_card_links(source):
    try:
        r = fetch(source["url"])
        r.raise_for_status()
    except Exception as e:
        print(f"  ❌ HTTP-fout: {e}")
        return

    soup = BeautifulSoup(r.text, "html.parser")
    tags = soup.select(source.get("link_sel", "a"))
    seen = set()
    results = []
    for tag in tags:
        href = abs_url(tag.get("href", ""), source["url"])
        if href and href not in seen:
            seen.add(href)
            results.append((slug_to_title(href), href))

    if results:
        print(f"  ✅ Card links — {len(results)} items")
        for title, url in results[:5]:
            print(f"    • {title}")
            print(f"      {url[:90]}")
    else:
        print(f"  ⚠️  Geen card links gevonden")


def main():
    filter_name = sys.argv[1].lower() if len(sys.argv) > 1 else None
    sources = SOURCES
    if filter_name:
        sources = [s for s in SOURCES if filter_name in s["name"].lower()]
        if not sources:
            print(f"Niet gevonden: '{filter_name}'")
            print("Beschikbaar:", ", ".join(s["name"] for s in SOURCES))
            return

    total = len(sources)
    print(f"Test {total} bron(nen)...\n")
    for source in sources:
        print(f"\n{'─'*60}")
        print(f"  {source['name'].upper()}  [{source['type']}]")
        if source.get("url"):
            print(f"  {source['url']}")
        print()
        t = source["type"]
        if t == "rss":
            test_rss(source)
        elif t == "html":
            test_html(source)
        elif t == "html_links":
            test_html_links(source)
        elif t == "html_card_links":
            test_html_card_links(source)
        elif t == "skip":
            print(f"  ⏭  {source['reason']}")

    print(f"\n{'─'*60}")
    print("Klaar.")


if __name__ == "__main__":
    main()
