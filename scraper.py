"""
FoodRise NGO Monitor — scraper.py
Scrapt 11 NGO-bronnen, vat samen met Claude, mailt wekelijkse digest.

Vereist omgevingsvariabelen:
    ANTHROPIC_API_KEY
    GMAIL_USER
    GMAIL_APP_PASSWORD
    NEWSLETTER_TO   (optioneel, default = GMAIL_USER)
"""

import os
import re
import json
import hashlib
import smtplib
import feedparser
import requests
try:
    import cloudscraper as _cloudscraper
    _cs = _cloudscraper.create_scraper()
except ImportError:
    _cs = None
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from anthropic import Anthropic
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────

SEEN_FILE = Path("seen_items.json")

OPINION_SOURCES = [
    {"name": "Grilled Media (EN)",
     "type": "html_links",
     "url": "https://www.grilled.media/",
     "link_pattern": r"grilled\.media/[a-z0-9-]{5,}/?$",
     "exclude_pattern": r"/(about|contact|subscribe|newsletter|tag|category|author|page)/?$"},

    {"name": "Lighthouse Reports (EN)",
     "type": "html_links",
     "url": "https://www.lighthousereports.com/investigations/",
     "link_pattern": r"lighthousereports\.com/investigation/[a-z0-9-]{5,}",
     "exclude_pattern": r"^$"},


    # ── Opinie & Analyse — websites ───────────────────────────────────────────
    {"name": "MO* (BE)",
     "type": "html_links",
     "url": "https://www.mo.be/themas/klimaat-duurzaamheid",
     "link_pattern": r"mo\.be/(artikel|opinie|analyse|interview|reportage)/[a-z0-9-]{5,}",
     "exclude_pattern": r"^$"},

    {"name": "Reporterre (FR)",
     "type": "rss",
     "url": "https://reporterre.net/spip.php?page=backend-simple"},

    {"name": "El Salto (ES)",
     "type": "html_links",
     "url": "https://www.elsaltodiario.com/alimentacion",
     "link_pattern": r"elsaltodiario\.com/[a-z-]{3,}/[a-z0-9-]{20,}",
     "exclude_pattern": r"/(suscrib|tienda|contacto|quienes|accesibil|salto-de-carro|"
                         r"de-salto-en-salto|formulario|encontrar|contrasena|autor|radio|"
                         r"podcast|agenda|hemeroteca)"},

    {"name": "Klimareporter (DE)",
     "type": "html_links",
     "url": "https://klimareporter.de/landwirtschaft",
     "link_pattern": r"klimareporter\.de/[a-z-]+/[a-z0-9-]{15,}",
     "exclude_pattern": r"/(ueber-uns|kontakt|newsletter|impressum|datenschutz|spenden|"
                         r"energiewende|klimapolitik|deutschland|europaeische|international|"
                         r"klimakonferenzen|landwirtschaft|verkehr|gebaeude|industrie|finanzen)/?$"},

    {"name": "The Guardian (EN)",
     "type": "rss",
     "url": "https://www.theguardian.com/commentisfree/commentisfree+environment/farming/rss"},

    {"name": "Le Monde Agriculture (FR)",
     "type": "rss",
     "url": "https://www.lemonde.fr/agriculture/rss_full.xml"},

    {"name": "Grist Food & Agriculture (EN)",
     "type": "rss",
     "url": "https://grist.org/food-and-agriculture/feed/"},

    {"name": "Dagens Nyheter Jordbruk (SE)",
     "type": "html_links",
     "url": "https://www.dn.se/om/jordbruk/",
     "link_pattern": r"dn\.se/(ekonomi|debatt|nyheter|kultur)/[a-z0-9-]{10,}",
     "exclude_pattern": r"/(prenumerera|kundservice|kontakt|om-dn)"},

    # ── Podcasts ──────────────────────────────────────────────────────────────
    {"name": "The BREAK—DOWN (EN)",
     "type": "rss",
     "url": "https://anchor.fm/s/f5684160/podcast/rss"},

    {"name": "Macrodose (EN)",
     "type": "rss",
     "url": "https://anchor.fm/s/b746ee18/podcast/rss"},

    {"name": "Overshoot Podcast (EN)",
     "type": "rss",
     "url": "https://anchor.fm/s/108013034/podcast/rss"},

    {"name": "Between Heat and Hope (NL/EN)",
     "type": "rss",
     "url": "https://media.rss.com/between-heat-and-hope/feed.xml"},

    {"name": "Dissens (DE)",
     "type": "rss",
     "url": "https://podcast.dissenspodcast.de/feed/mp3"},
    {"name": "Sentient Media (EN)",
     "type": "html_links",
     "url": "https://sentientmedia.org/category/agriculture/",
     "link_pattern": r"sentientmedia\.org/[a-z0-9-]{10,}/?$",
     "exclude_pattern": r"/(category|tag|author|page|donate|about|newsletter|contact|"
                         r"subscribe|membership|foodandfarm|inside-iowa|sustainable-agriculture|"
                         r"what-is|explainer|resource)"},

    {"name": "Freedom Food Alliance (EN)",
     "type": "html_links",
     "url": "https://www.freedomfoodalliance.org/unfork-food-system",
     "link_pattern": r"freedomfoodalliance\.org/unfork-the-food-system/[a-z0-9-]{5,}",
     "exclude_pattern": r"^$"},

    {"name": "Critical Takes (EN)",
     "type": "html_links",
     "url": "https://criticaltakes.org/society-and-nature/",
     "link_pattern": r"criticaltakes\.org/society-and-nature/[a-z0-9-]{5,}",
     "exclude_pattern": r"^$"},

]


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

SOURCES = [
    # RSS
    {"name": "Changing Markets",    "type": "rss",
     "url": "https://changingmarkets.org/feed/"},
    {"name": "Foodrise EU",         "type": "rss",
     "url": "https://foodrise.eu/feed/"},
    {"name": "GRAIN",               "type": "rss",
     "url": "https://grain.org/en/home/entries.rss"},

    # HTML — css selectors
    {"name": "ClientEarth",         "type": "html",
     "url": "https://www.clientearth.org/latest/news/",
     "item_sel": "a.newsitem, a.item",
     "title_sel": "h2, h3, .title",
     "link_sel": None},
    {"name": "IATP",                "type": "html",
     "url": "https://www.iatp.org/publications/press_releases",
     "item_sel": "article, .view-row, .teaser",
     "title_sel": "h2, h3, .title",
     "link_sel": "a",
     "dedupe": True, "timeout": 30},
    {"name": "Ecologistas en Acción", "type": "html",
     "url": "https://www.ecologistasenaccion.org/",
     "item_sel": "article, .post, .entry",
     "title_sel": "h2, h3, .entry-title",
     "link_sel": "a"},
    {"name": "Greenpeace Aotearoa", "type": "html",
     "url": "https://www.greenpeace.org/aotearoa/news/",
     "item_sel": ".post",
     "title_sel": "h2, h3",
     "link_sel": "a"},

    # HTML — card links (href aanwezig, titel via slug)
    {"name": "Mighty Earth",        "type": "html_card_links",
     "url": "https://mightyearth.org/news/",
     "link_sel": "a.card-link"},

    # HTML — links op URL-patroon
    {"name": "Milieudefensie",      "type": "html_links",
     "url": "https://milieudefensie.nl/actueel/",
     "link_pattern": r"milieudefensie\.nl/actueel/[^#?]+$",
     "exclude_pattern": r"milieudefensie\.nl/actueel/$"},
    {"name": "Greenpeace Nordic",   "type": "html_links",
     "url": "https://www.greenpeace.org/denmark/pressemeddelelse/",
     "link_pattern": r"greenpeace\.org/denmark/(pressemeddelelse|nyhed)/[^#?]+/[^#?]+/$"},
    {"name": "Justicia Alimentaria","type": "html_links",
     "url": "https://justiciaalimentaria.org/sala-de-prensa/",
     "link_pattern": r"justiciaalimentaria\.org/[a-z0-9-]{10,}/$",
     "exclude_pattern": (r"/(que-hacemos|unete|hazte|donativo|voluntariado|legado|"
                          r"quienes|sala-de-prensa|actualidad|videos|observatorio|"
                          r"contacto|aviso|politica|cookies|transparencia|alianzas|"
                          r"trabaja|ca|buzon|haz-un)"),
    },
    {"name": "Seastemik",           "type": "html_links",
     "url": "https://seastemik.org/presse-and-actu",
     "link_pattern": r"https?://",
     "exclude_pattern": (r"seastemik\.org|helloasso\.com|facebook|twitter|"
                          r"instagram|linkedin|youtube|mailto")},
    # ── Nieuwe bronnen ──────────────────────────────────────

    {"name": "Greenpeace UK",
     "type": "html_links",
     "url": "https://www.greenpeace.org.uk/news/",
     "link_pattern": r"greenpeace\.org\.uk/news/[a-z0-9-]{10,}/$",
     "exclude_pattern": r"greenpeace\.org\.uk/news/$"},

    {"name": "Greenpeace Africa",
     "type": "html_links",
     "url": "https://www.greenpeace.org/africa/en/news/",
     "link_pattern": r"greenpeace\.org/africa/en/press/\d+/[a-z0-9-]+",
     "exclude_pattern": r"^$"},

    {"name": "Greenpeace NL",
     "type": "html_links",
     "url": "https://www.greenpeace.org/nl/nieuws/nieuwsberichten/",
     "link_pattern": r"greenpeace\.org/nl/nieuws/[a-z0-9-]+/[a-z0-9-]{5,}",
     "exclude_pattern": r"/(nieuwsberichten|pers|onderzoek|blogs)/?$"},

    {"name": "Naturskyddsföreningen",
     "type": "html",
     "url": "https://www.naturskyddsforeningen.se/aktuella-kampanjer-och-projekt/",
     "item_sel": "div[data-block=\'theme/blurbs\'] a",
     "title_sel": "p, h2, h3",
     "link_sel": None},

    {"name": "Food Foundation",
     "type": "rss",
     "url": "https://foodfoundation.org.uk/feed/"},
    # ── Project Slingshot ─────────────────────────────────
    {"name": "Project Slingshot (UK)",
     "type": "rss",
     "url": "https://www.google.com/alerts/feeds/07615872391047467014/524339206574596607"},

    # ── CAFF ──────────────────────────────────────────────
    {"name": "CAFF (UK)",
     "type": "html_links",
     "url": "https://www.caff.org.uk/press",
     "link_pattern": r"caff\.org\.uk/press/[a-z0-9-]{5,}",
     "exclude_pattern": r"^$"},

    # ── ProVeg ────────────────────────────────────────────
    {"name": "ProVeg (INT)",
     "type": "html_links",
     "url": "https://proveg.org/about-us/media-room/",
     "link_pattern": r"proveg\.org/press-release/[a-z0-9-]{5,}",
     "exclude_pattern": r"^$"},

    # ── Madrebrava ────────────────────────────────────────
    {"name": "Madrebrava (EU)",
     "type": "html_links",
     "url": "https://www.madrebrava.org/latest",
     "link_pattern": r"madrebrava\.org/latest/[a-z0-9-]{5,}",
     "exclude_pattern": r"^$"},

    # ── Vegetarisk ────────────────────────────────────────
    {"name": "Vegetarisk (DK)",
     "type": "html_links",
     "url": "https://vegetarisk.dk/nyheder/",
     "link_pattern": r"vegetarisk\.dk/[a-z0-9-]{15,}/?$",
     "exclude_pattern": r"/(nyheder|soeger|kollega|telefundraiser|bliv|stillinger|job|vores|om-os|kontakt|presse|english|privat)/?$"},

    # ── The Protein Project ───────────────────────────────
    {"name": "The Protein Project (EU)",
     "type": "html_links",
     "url": "https://www.theproteinproject.eu/publications",
     "link_pattern": r"theproteinproject\.eu/publications/[a-z0-9-]{5,}",
     "exclude_pattern": r"/category/"},

    # ── BirdLife ──────────────────────────────────────────
    {"name": "BirdLife (INT)",
     "type": "html_links",
     "url": "https://www.birdlife.org/news/",
     "link_pattern": r"birdlife\.org/news/20\d\d/",
     "exclude_pattern": r"^$"},

    # ── Friends of the Earth EU ───────────────────────────
    {"name": "Friends of the Earth EU",
     "type": "html_links",
     "url": "https://friendsoftheearth.eu/media-centre/",
     "link_pattern": r"friendsoftheearth\.eu/press-release/[a-z0-9-]{5,}",
     "exclude_pattern": r"^$"},

    # ── Stop Financing Factory Farming ────────────────────
    {"name": "Stop Financing Factory Farming (INT)",
     "type": "html_links",
     "url": "https://stopfinancingfactoryfarming.com/news",
     "link_pattern": r"stopfinancingfactoryfarming\.com/news/[a-z0-9-]{5,}",
     "exclude_pattern": r"/category/"},

    # ── DeSmog ───────────────────────────────────────────
    {"name": "DeSmog Agriculture (EN)",
     "type": "html_links",
     "url": "https://www.desmog.com/topic/agriculture/",
     "link_pattern": r"desmog\.com/20\d\d/[0-9]{2}/[0-9]{2}/[a-z0-9-]{5,}",
     "exclude_pattern": r"^$"},

    # ── Unearthed Greenpeace ──────────────────────────────
    {"name": "Unearthed (Greenpeace, EN)",
     "type": "html_links",
     "url": "https://unearthed.greenpeace.org/",
     "link_pattern": r"unearthed\.greenpeace\.org/20\d\d/[0-9]{2}/[0-9]{2}/[a-z0-9-]{10,}/?$",
     "exclude_pattern": r"/(category|tag|author|page|about|contact)"},

    # ── World Animal Protection ───────────────────────────
    {"name": "World Animal Protection (INT)",
     "type": "html_links",
     "url": "https://www.worldanimalprotection.org/latest/news/",
     "link_pattern": r"worldanimalprotection\.org/latest/news/[a-z0-9-]{5,}",
     "exclude_pattern": r"^$"},

    # ── Four Paws ─────────────────────────────────────────
    {"name": "Four Paws (INT)",
     "type": "html_links",
     "url": "https://www.four-paws.org/press",
     "link_pattern": r"four-paws\.org/our-stories/press-releases/[a-z0-9/-]{5,}",
     "exclude_pattern": r"^$"},

    # ── Rainforest Action Network ─────────────────────────
    {"name": "Rainforest Action Network (EN)",
     "type": "html_links",
     "url": "https://www.ran.org/media-center/",
     "link_pattern": r"ran\.org/press-releases/[a-z0-9-]{5,}",
     "exclude_pattern": r"^$"},

    # ── Sinergia Animal ────────────────────────────────────
    {"name": "Sinergia Animal (EN)",
     "type": "html_links",
     "url": "https://www.media.sinergiaanimal.org/press-releases",
     "link_pattern": r"sinergiaanimal\.org/post/[a-z0-9-]{5,}",
     "exclude_pattern": r"^$"},

    # ── Deutsche Umwelthilfe ───────────────────────────────
    {"name": "Deutsche Umwelthilfe (DE)",
     "type": "html_links",
     "url": "https://www.duh.de/presse/pressemitteilungen/",
     "link_pattern": r"duh\.de/presse/pressemitteilungen/pressemitteilung/[a-z0-9-]{5,}",
     "exclude_pattern": r"^$"},

    # ── IPES Food ──────────────────────────────────────────
    {"name": "IPES Food (INT)",
     "type": "html_links",
     "url": "https://ipes-food.org/media-and-press/",
     "link_pattern": r"ipes-food\.org/[a-z0-9-]{5,}/?$",
     "exclude_pattern": r"/(media-and-press|report|about|contact|team|subscribe)/?$"},

    # ── Greenpeace Italia ──────────────────────────────────
    {"name": "Greenpeace Italia (IT)",
     "type": "html_links",
     "url": "https://www.greenpeace.org/italy/rapporto/",
     "link_pattern": r"greenpeace\.org/italy/rapporto/\d+/[a-z0-9-]{5,}",
     "exclude_pattern": r"^$"},

    # ── Food & Power ──────────────────────────────────────
    {"name": "Food & Power (EN)",
     "type": "html_links",
     "url": "https://www.foodandpower.net/latest",
     "link_pattern": r"foodandpower\.net/latest/[a-z0-9-]{5,}",
     "exclude_pattern": r"(/category/|\?author)"},

    # ── The Fern ───────────────────────────────────────────
    {"name": "The Fern (EN)",
     "type": "cloudscraper",
     "url": "https://thefern.org/category/international/",
     "link_pattern": r"thefern\.org/20[0-9]{2}/[a-z0-9-]{5,}",
     "exclude_pattern": r"^$"},

    # ── ETC Group ─────────────────────────────────────────
    {"name": "ETC Group (INT)",
     "type": "html_links",
     "url": "https://www.etcgroup.org/news",
     "link_pattern": r"etcgroup\.org/content/[a-z0-9-]{5,}",
     "exclude_pattern": r"^$"},

    # ── Seas at Risk ──────────────────────────────────────
    {"name": "Seas at Risk (EU)",
     "type": "html_links",
     "url": "https://seas-at-risk.org/news/",
     "link_pattern": r"seas-at-risk\.org/(general-news|press-releases)/[a-z0-9-]{5,}",
     "exclude_pattern": r"^$"},

    # ── CIWF ──────────────────────────────────────────────
    {"name": "CIWF UK",
     "type": "html_links",
     "url": "https://www.ciwf.org/media-and-news/latest-news/",
     "link_pattern": r"ciwf\.org/media-and-news/latest-news/[a-z0-9-]{5,}",
     "exclude_pattern": r"^$"},

    {"name": "CIWF EU",
     "type": "html_links",
     "url": "https://www.ciwf.eu/media-and-news/news/",
     "link_pattern": r"ciwf\.eu/media-and-news/news/[a-z0-9-]{5,}",
     "exclude_pattern": r"^$"},

    {"name": "CIWF FR",
     "type": "html_links",
     "url": "https://www.ciwf.fr/actualites-et-publications/actualites/",
     "link_pattern": r"ciwf\.fr/actualites-et-publications/actualites/[a-z0-9-]{5,}",
     "exclude_pattern": r"^$"},

    {"name": "CIWF IT",
     "type": "html_links",
     "url": "https://www.ciwf.it/news/",
     "link_pattern": r"ciwf\.it/news/[a-z0-9-]{5,}",
     "exclude_pattern": r"^$"},

]

SYSTEM_PROMPT = """Je bent een research-assistent voor Sybren Kooistra, Campaign Director van FoodRise.
FoodRise is een Nederlandse campagneorganisatie die de klimaat- en biodiversiteitsimpact van
industriële dierlijke landbouw (Big Ag / Big Agro) aanpakt. Doelwitten zijn onder andere
FrieslandCampina, Vion, Nutreco. FoodRise werkt aan greenwashing-onderzoek, juridische strategie
(ACM-klachten, Scope 3 aansprakelijkheid) en EU-beleidsdruk.

Geef een gestructureerde samenvatting van het nieuwsitem in het Nederlands.
Gebruik dit exacte formaat — geen extra tekst ervoor of erna:

Type: [één of twee van: rapport | campagne | rechtszaak | beleidsdruk | greenwashing | onderzoek | reactie | anders]
Onderwerp: [één of twee van: methaan | scope3 | kweekvis | ontbossing | subsidies | veehouderij | aquafeed | lobby | financiering | anders]
Relevantie: [hoog | midden | laag] — hoog = direct bruikbaar voor FoodRise campagnes (FrieslandCampina/Vion/Nutreco, methaan, kweekvis, Scope 3, EU-beleid); midden = relevante sector maar geen directe link met FoodRise's doelwitten/thema's; laag = raakt het onderwerp slechts zijdelings
Samenvatting: [bij hoog/midden: 2 zinnen wat het concreet is en wie het doet; bij laag: 1 zin wat het is. Geen toelichting over relevantie voor FoodRise.]"""

# ── Hulpfuncties ──────────────────────────────────────────────────────────────

def uid(text):
    return hashlib.md5(text.encode()).hexdigest()[:12]

def load_seen():
    if SEEN_FILE.exists():
        return set(json.loads(SEEN_FILE.read_text()))
    return set()

def save_seen(seen):
    SEEN_FILE.write_text(json.dumps(sorted(seen), indent=2))

def abs_url(href, base):
    if not href or href.startswith("#") or href.startswith("mailto"):
        return ""
    if href.startswith("http"):
        return href
    p = urlparse(base)
    if href.startswith("/"):
        return f"{p.scheme}://{p.netloc}{href}"
    return base.rstrip("/") + "/" + href

def slug_to_title(url):
    path = urlparse(url).path.rstrip("/")
    slug = path.split("/")[-1]
    return slug.replace("-", " ").title()

def clean_title(raw):
    """Verwijder datum en type-suffix die Milieudefensie aan titels plakt."""
    raw = re.sub(r"\d{1,2} (januari|februari|maart|april|mei|juni|juli|augustus|"
                  r"september|oktober|november|december) \d{4}", "", raw)
    raw = re.sub(r"\s*(Nieuws|Blog|Opinie|Agenda)$", "", raw.strip())
    return raw.strip()

def get_snippet(entry):
    for field in ("summary", "content"):
        val = entry.get(field, "")
        if isinstance(val, list):
            val = val[0].get("value", "") if val else ""
        if val:
            return BeautifulSoup(val, "html.parser").get_text(" ", strip=True)[:600]
    return ""

def fetch(url, timeout=15):
    return requests.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True)

def fetch_cs(url, timeout=15):
    """Fetch via cloudscraper voor Cloudflare-beschermde sites."""
    if _cs:
        return _cs.get(url, timeout=timeout)
    return fetch(url, timeout=timeout)

# ── Scrapers per type ─────────────────────────────────────────────────────────

def scrape_rss(source):
    feed = feedparser.parse(source["url"])
    if feed.get("status") != 200 or not feed.entries:
        return []
    items = []
    for e in feed.entries[:20]:
        link = e.get("link", "")
        title = e.get("title", "").strip()
        if not link or not title:
            continue
        # Datum ophalen
        published = e.get("published_parsed") or e.get("updated_parsed")
        if published:
            from time import strftime, mktime
            date_str = strftime("%-d %b %Y", published)
        else:
            date_str = ""
        items.append({
            "id": uid(link),
            "source": source["name"],
            "title": title,
            "link": link,
            "snippet": get_snippet(e),
            "date": date_str,
        })
    return items

def scrape_html(source):
    try:
        r = fetch(source["url"], timeout=source.get("timeout", 15))
        r.raise_for_status()
    except Exception as e:
        print(f"  ⚠ {source['name']}: {e}")
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    item_sel  = source.get("item_sel", "article")
    title_sel = source.get("title_sel", "h2, h3")
    link_sel  = source.get("link_sel", "a")
    dedupe    = source.get("dedupe", False)

    containers = soup.select(item_sel)
    if not containers:
        return []

    seen_urls = set()
    items = []
    for container in containers[:20]:
        if link_sel is None:
            link_tag = container if container.name == "a" else container.find("a")
        else:
            link_tag = container.select_one(link_sel)

        href = abs_url(link_tag.get("href", "") if link_tag else "", source["url"])
        if not href or (dedupe and href in seen_urls):
            continue
        seen_urls.add(href)

        title_tag = container.select_one(title_sel) if title_sel else None
        title = (title_tag or link_tag or container).get_text(strip=True)
        title = clean_title(title[:200])
        if len(title) < 5:
            continue

        snippet = container.get_text(" ", strip=True)[:500]
        items.append({
            "id": uid(href),
            "source": source["name"],
            "title": title,
            "link": href,
            "snippet": snippet,
        })
    return items

def scrape_html_card_links(source):
    try:
        r = fetch(source["url"])
        r.raise_for_status()
    except Exception as e:
        print(f"  ⚠ {source['name']}: {e}")
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    seen = set()
    items = []
    for tag in soup.select(source.get("link_sel", "a")):
        href = abs_url(tag.get("href", ""), source["url"])
        if not href or href in seen:
            continue
        seen.add(href)
        items.append({
            "id": uid(href),
            "source": source["name"],
            "title": slug_to_title(href),
            "link": href,
            "snippet": "",
        })
    return items

def scrape_html_links(source):
    try:
        r = fetch(source["url"])
        r.raise_for_status()
    except Exception as e:
        print(f"  ⚠ {source['name']}: {e}")
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    include_pat = re.compile(source["link_pattern"])
    exclude_pat = re.compile(source.get("exclude_pattern", "^$"))

    seen = set()
    items = []
    for a in soup.find_all("a", href=True):
        full = abs_url(a["href"], source["url"])
        if not full or full in seen:
            continue
        if include_pat.search(full) and not exclude_pat.search(full):
            title = clean_title(a.get_text(strip=True)[:200])
            if len(title) > 4:
                seen.add(full)
                items.append({
                    "id": uid(full),
                    "source": source["name"],
                    "title": title,
                    "link": full,
                    "snippet": "",
                })
    return items


def scrape_html_a_title(source):
    """Scrape <a> elementen waarbij de titel in het title-attribuut zit."""
    try:
        r = fetch(source["url"], timeout=source.get("timeout", 15))
        r.raise_for_status()
    except Exception as e:
        print(f"  ⚠ {source['name']}: {e}")
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    link_sel = source.get("link_sel", "a[title]")
    p = urlparse(source["url"])
    base = f"{p.scheme}://{p.netloc}"

    seen = set()
    items = []
    for a in soup.select(link_sel):
        href = a.get("href", "")
        title = a.get("title", "").strip() or a.get("aria-label", "").replace(" - Read more", "").strip()

        if not href or not title or len(title) < 5:
            continue

        # Maak absolute URL
        if href.startswith("http"):
            full_url = href
        elif href.startswith("/"):
            full_url = base + href
        else:
            continue

        if full_url in seen:
            continue
        seen.add(full_url)

        items.append({
            "id": uid(full_url),
            "source": source["name"],
            "title": title[:200],
            "link": full_url,
            "snippet": "",
        })
    return items

def scrape_html_a_img_alt(source):
    """Scrape <a> elementen waarbij de titel in het alt-attribuut van de eerste <img> zit."""
    try:
        r = fetch(source["url"], timeout=source.get("timeout", 15))
        r.raise_for_status()
    except Exception as e:
        print(f"  ⚠ {source['name']}: {e}")
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    link_sel = source.get("link_sel", "a")
    p = urlparse(source["url"])
    base = f"{p.scheme}://{p.netloc}"

    seen = set()
    items = []
    for a in soup.select(link_sel):
        href = a.get("href", "")
        img = a.find("img")
        title = ""
        if img:
            title = img.get("alt", "").strip()
        if not title:
            title = a.get("title", "").strip() or a.get("aria-label", "").strip()
        if not href or not title or len(title) < 5:
            continue
        full_url = base + href if href.startswith("/") else href
        if full_url in seen:
            continue
        seen.add(full_url)
        items.append({
            "id": uid(full_url),
            "source": source["name"],
            "title": title[:200],
            "link": full_url,
            "snippet": "",
        })
    return items


def scrape_cloudscraper(source):
    """Scrape via cloudscraper voor Cloudflare-beschermde sites."""
    import re as _re
    from urllib.parse import urlparse as _up
    try:
        r = fetch_cs(source["url"], timeout=source.get("timeout", 20))
        r.raise_for_status()
    except Exception as e:
        print(f"  ⚠ {source['name']}: {e}")
        return []
    soup = BeautifulSoup(r.text, "html.parser")
    inc = _re.compile(source["link_pattern"])
    exc = _re.compile(source.get("exclude_pattern", "^$"))
    p = _up(source["url"])
    base = f"{p.scheme}://{p.netloc}"
    seen = set()
    items = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        full = href if href.startswith("http") else base + href
        if full in seen: continue
        if inc.search(full) and not exc.search(full):
            title = a.get_text(strip=True)[:120]
            if len(title) > 8:
                seen.add(full)
                items.append({"id": uid(full), "source": source["name"],
                              "title": title, "link": full, "snippet": ""})
    return items


def scrape(source):
    t = source["type"]
    if t == "rss":
        return scrape_rss(source)
    elif t == "html":
        return scrape_html(source)
    elif t == "html_card_links":
        return scrape_html_card_links(source)
    elif t == "html_links":
        return scrape_html_links(source)
    elif t == "html_a_title":
        return scrape_html_a_title(source)
    elif t == "html_a_img_alt":
        return scrape_html_a_img_alt(source)
    elif t == "cloudscraper":
        return scrape_cloudscraper(source)
    return []

# ── AI samenvatting ───────────────────────────────────────────────────────────

def summarise(client, item):
    msg = (f"Bron: {item['source']}\n"
           f"Titel: {item['title']}\n"
           f"URL: {item['link']}\n"
           f"Context: {item.get('snippet') or '(geen)'}\n\n"
           "Geef de gestructureerde samenvatting.")
    try:
        resp = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=300,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": msg}],
        )
        return resp.content[0].text.strip()
    except Exception as e:
        return f"Type: anders\nOnderwerp: onbekend\nSamenvatting: Kon niet samenvatten ({e})"

def parse_summary(raw):
    result = {"types": [], "topics": [], "body": "", "relevance": "midden"}
    for line in raw.splitlines():
        if line.startswith("Type:"):
            result["types"] = [t.strip() for t in line.replace("Type:", "").split("|") if t.strip()]
        elif line.startswith("Onderwerp:"):
            result["topics"] = [t.strip() for t in line.replace("Onderwerp:", "").split("|") if t.strip()]
        elif line.startswith("Relevantie:"):
            val = line.replace("Relevantie:", "").strip().lower()
            if val in ("hoog", "midden", "laag"):
                result["relevance"] = val
        elif line.startswith("Samenvatting:"):
            result["body"] = line.replace("Samenvatting:", "").strip()
    if not result["body"]:
        result["body"] = raw
    return result

# ── HTML nieuwsbrief ──────────────────────────────────────────────────────────


# ── Nieuwe Oogst industrie monitor ───────────────────────────────────────────

NIEUWE_OOGST_TOPICS = [
    {"label": "Biomethaan & vergisting",
     "keywords": ["biomethaan", "biogasopwaardering", "groen gas", "biogas",
                  "mestvergisting", "monovergister", "vergister", "vergisting"]},
    {"label": "Nutreco / Trouw Nutrition",
     "keywords": ["nutreco", "trouw nutrition", "trouw"]},
    {"label": "FrieslandCampina",
     "keywords": ["frieslandcampina"]},
    {"label": "Vion",
     "keywords": ["vion"]},
    {"label": "Kabinet & bewindspersonen",
     "keywords": ["kabinet", "erkens", "minister", "staatssecretaris"]},
]

def scrape_nieuwe_oogst(max_pages=6):
    """Scrape Nieuwe Oogst (meerdere pagina's) en filter op industrietrefwoorden."""
    import re as _re

    cutoff_no = datetime.now() - timedelta(days=8)
    articles = []
    seen = set()
    stop = False

    def parse_page(html):
        """Parse artikelen uit HTML, geeft (articles, laatste_id, alles_te_oud) terug."""
        nonlocal stop
        soup = BeautifulSoup(html, "html.parser")
        found = []
        last_id = None
        for div in soup.find_all("div", attrs={"data-id": True}):
            last_id = div.get("data-id")
        for a in soup.find_all("a", href=True):
            href = a.get("href", "")
            if not _re.search(r"/nieuws/20[0-9]{2}/[0-9]{2}/[0-9]{2}/", href):
                continue
            full = href if href.startswith("http") else "https://www.nieuweoogst.nl" + href
            if full in seen:
                continue
            title = a.get_text(strip=True)
            if not title or len(title) < 8:
                continue
            m = _re.search(r"/nieuws/(20[0-9]{2})/([0-9]{2})/([0-9]{2})/", href)
            if m:
                try:
                    item_date = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
                    if item_date < cutoff_no:
                        stop = True
                        continue
                except Exception:
                    pass
            seen.add(full)
            found.append({"title": title, "link": full})
        return found, last_id

    # Startpagina's: algemeen nieuws + sectorpagina's
    START_URLS = [
        "https://www.nieuweoogst.nl/nieuws",
        "https://www.nieuweoogst.nl/sector/veehouderij",
        "https://www.nieuweoogst.nl/sector/akker-en-tuinbouw",
    ]

    for start_url in START_URLS:
        stop = False
        try:
            r = fetch(start_url, timeout=20)
            r.raise_for_status()
        except Exception as e:
            print(f"  ⚠ Nieuwe Oogst ({start_url}): {e}")
            continue

        found, last_id = parse_page(r.text)
        articles.extend(found)

        # Volgende pagina's via AJAX-endpoint
        offset = 49
        for _ in range(max_pages - 1):
            if stop or not last_id:
                break
            ajax_url = f"https://www.nieuweoogst.nl/data/page-49/articles/section-news/{offset}/last/{last_id}/"
            try:
                r2 = fetch(ajax_url, timeout=20)
                r2.raise_for_status()
            except Exception:
                break
            if len(r2.text.strip()) < 50:
                break
            found, new_last = parse_page(r2.text)
            if not found or new_last == last_id:
                break
            articles.extend(found)
            last_id = new_last
            offset += 49

    # Filter op trefwoorden
    results = {}
    for topic in NIEUWE_OOGST_TOPICS:
        matches = []
        for art in articles:
            tekst = (art["title"] + " " + art["link"]).lower()
            if any(kw in tekst for kw in topic["keywords"]):
                matches.append(art)
        if matches:
            results[topic["label"]] = matches

    return results


def build_nieuwe_oogst_section(results):
    """Bouw HTML voor de Nieuwe Oogst monitor sectie."""
    if not results:
        return ""

    sections = ""
    for label, items in results.items():
        cards = ""
        for art in items:
            cards += f"""
            <div style="padding:6px 0;border-bottom:1px solid #f0f0f0">
              <a href="{art['link']}" style="font-size:14px;color:#1C4332;text-decoration:none;font-weight:500">
                {art['title']}
              </a>
            </div>"""
        sections += f"""
        <div style="margin-bottom:20px">
          <p style="font-size:12px;font-weight:700;text-transform:uppercase;
                    letter-spacing:.5px;color:#C0492F;margin:0 0 8px">{label}</p>
          {cards}
        </div>"""

    return f"""
    <div style="margin-bottom:36px;border:1px solid #f0d0cc;border-radius:6px;padding:16px 20px">
      <h2 style="font-size:13px;font-weight:700;letter-spacing:1.5px;
                 text-transform:uppercase;color:#C0492F;
                 border-bottom:2px solid #C0492F;
                 padding-bottom:5px;margin-bottom:16px">
        Nieuwe Oogst — industrie monitor
      </h2>
      {sections}
      <p style="font-size:11px;color:#999;margin:12px 0 0">
        Bron: <a href="https://www.nieuweoogst.nl/nieuws" style="color:#999">nieuweoogst.nl</a>
        · alleen artikelen van de afgelopen 8 dagen
      </p>
    </div>"""

def build_html(items_by_source, week, opinion_html="", nieuwe_oogst_html="", source_stats=None):
    # Verzamel alle items en sorteer op relevantie
    all_items = []
    for source_name, items in items_by_source.items():
        for item in items:
            item["_source"] = source_name
            all_items.append(item)

    hoog   = [i for i in all_items if parse_summary(i["summary"])["relevance"] == "hoog"]
    midden = [i for i in all_items if parse_summary(i["summary"])["relevance"] == "midden"]
    laag   = [i for i in all_items if parse_summary(i["summary"])["relevance"] == "laag"]
    total  = len(all_items)

    def tag(text, bg, fg):
        return (f'<span style="background:{bg};color:{fg};padding:2px 9px;'
                f'border-radius:20px;font-size:11px;font-weight:700;'
                f'margin-right:4px;text-transform:uppercase;letter-spacing:.5px">'
                f'{text}</span>')

    REL_COLORS = {
        "hoog":   ("#1C4332", "#9FE870", "● Hoog"),
        "midden": ("#92660b", "#FCE9B8", "● Midden"),
        "laag":   ("#888",    "#eee",    "● Laag"),
    }

    def relevance_badge(level):
        fg, bg, label = REL_COLORS.get(level, REL_COLORS["midden"])
        return (f'<span style="background:{bg};color:{fg};padding:2px 10px;'
                f'border-radius:20px;font-size:11px;font-weight:700;'
                f'margin-right:6px;letter-spacing:.3px">{label}</span>')

    def render_item(item):
        p = parse_summary(item["summary"])
        source_name = item.get("_source", "")
        date_str = item.get("date", "")
        date_html = f'<span style="font-size:11px;color:#999;margin-left:6px">{date_str}</span>' if date_str else ""
        border_color = {"hoog": "#9FE870", "midden": "#FCE9B8", "laag": "#ddd"}.get(p["relevance"], "#9FE870")
        tags_html = (
            relevance_badge(p["relevance"]) +
            "".join(tag(t, "#9FE870", "#1C4332") for t in p["types"]) +
            "".join(tag(t, "#E8703A", "#fff")    for t in p["topics"])
        )
        return f"""
            <div style="border-left:3px solid {border_color};padding:10px 16px;
                        margin-bottom:18px;background:#fafafa">
              <div style="margin-bottom:5px">{tags_html}</div>
              <div style="font-size:11px;font-weight:700;color:#888;text-transform:uppercase;
                          letter-spacing:.5px;margin-bottom:4px">{source_name}{date_html}</div>
              <p style="margin:0 0 5px;font-weight:600;font-size:15px;
                        color:#1C4332;line-height:1.3">
                <a href="{item['link']}" style="color:#1C4332;text-decoration:none">
                  {item['title']}
                </a>
              </p>
              <p style="margin:0 0 6px;font-size:14px;color:#333;line-height:1.5">
                {p['body']}
              </p>
              <a href="{item['link']}" style="font-size:12px;color:#E8703A;text-decoration:none">
                → lees verder
              </a>
            </div>"""

    def render_section(title, items, border="#9FE870"):
        if not items:
            return ""
        cards = "".join(render_item(i) for i in items)
        return f"""
        <div style="margin-bottom:36px">
          <h2 style="font-size:13px;font-weight:700;letter-spacing:1.5px;
                     text-transform:uppercase;color:#1C4332;
                     border-bottom:2px solid {border};
                     padding-bottom:5px;margin-bottom:14px">{title}</h2>
          {cards}
        </div>"""

    sections = (
        render_section(f"Relevant — Hoog ({len(hoog)} items)", hoog, "#9FE870") +
        render_section(f"Relevant — Midden ({len(midden)} items)", midden, "#FCE9B8") +
        opinion_html +
        nieuwe_oogst_html +
        render_section(f"Overig — Laag ({len(laag)} items)", laag, "#ddd")
    )

    # ── Statustabel ───────────────────────────────────────────────────────────
    if source_stats:
        rows = ""
        for name, tot, fresh, error in source_stats:
            if error:
                kleur = "#C0492F"; status = "&#9888; fout"
            elif tot == 0:
                kleur = "#E8703A"; status = "0 gevonden"
            elif fresh == 0:
                kleur = "#888"; status = "geen nieuw"
            else:
                kleur = "#1C4332"; status = f"{fresh} nieuw"
            rows += (
                f'<tr>'
                f'<td style="padding:4px 10px;font-size:12px;border-bottom:1px solid #eee">{name}</td>'
                f'<td style="padding:4px 10px;font-size:12px;border-bottom:1px solid #eee;text-align:center">{tot}</td>'
                f'<td style="padding:4px 10px;font-size:12px;border-bottom:1px solid #eee;text-align:center;color:{kleur};font-weight:700">{status}</td>'
                f'</tr>'
            )
        stats_html = (
            '<div style="margin-top:40px;border-top:1px solid #ddd;padding-top:20px">'
            '<p style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:1px;color:#888;margin-bottom:8px">Bronstatus deze run</p>'
            '<table style="width:100%;border-collapse:collapse;font-family:sans-serif">'
            '<thead><tr style="background:#f5f5f5">'
            '<th style="padding:4px 10px;font-size:11px;text-align:left;color:#888">Bron</th>'
            '<th style="padding:4px 10px;font-size:11px;text-align:center;color:#888">Gevonden</th>'
            '<th style="padding:4px 10px;font-size:11px;text-align:center;color:#888">Status</th>'
            f'</tr></thead><tbody>{rows}</tbody></table></div>'
        )
    else:
        stats_html = ""

    return f"""<!DOCTYPE html>
<html lang="nl">
<head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
             max-width:660px;margin:0 auto;padding:20px;background:#fff;color:#222">
  <div style="background:#1C4332;padding:22px 26px;border-radius:6px;margin-bottom:28px">
    <h1 style="color:#9FE870;margin:0 0 4px;font-size:20px;font-weight:700">
      FoodRise NGO Monitor
    </h1>
    <p style="color:#c8e6c9;margin:0;font-size:13px">
      Week van {week} &nbsp;·&nbsp; {total} nieuwe items
    </p>
  </div>
  {sections if sections else '<p style="color:#888">Geen nieuwe items deze week.</p>'}
  <p style="color:#bbb;font-size:11px;border-top:1px solid #eee;
            padding-top:14px;margin-top:28px">
    FoodRise NGO Monitor · automatisch gegenereerd
  </p>
  {stats_html}
</body>
</html>"""

# ── Mail ──────────────────────────────────────────────────────────────────────

def send_mail(html, subject):
    sender    = os.environ["GMAIL_USER"]
    password  = os.environ["GMAIL_APP_PASSWORD"]
    recipient = os.environ.get("NEWSLETTER_TO", sender)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = sender
    msg["To"]      = recipient
    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as srv:
        srv.login(sender, password)
        srv.sendmail(sender, recipient, msg.as_string())
    print(f"✓ Verstuurd naar {recipient}")

# ── Main ──────────────────────────────────────────────────────────────────────

# ── Opinie & Analyse sectie ───────────────────────────────────────────────────

def scrape_opinion_source(source):
    """Scrape één opiniebron, geeft lijst van {title, link} terug."""
    import re as _re
    from urllib.parse import urlparse as _up

    def _abs(href, base):
        if not href or href.startswith("#") or href.startswith("mailto"):
            return ""
        if href.startswith("http"):
            return href
        p = _up(base)
        return f"{p.scheme}://{p.netloc}{href}" if href.startswith("/") else base.rstrip("/") + "/" + href

    t = source["type"]
    items = []

    if t == "rss":
        feed = feedparser.parse(source["url"])
        for e in feed.entries[:30]:
            link = e.get("link", "")
            title = e.get("title", "").strip()
            if link and title:
                items.append({"id": uid(link), "source": source["name"], "title": title, "link": link})

    elif t == "html_links":
        try:
            r = fetch(source["url"])
            r.raise_for_status()
        except Exception:
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        inc = _re.compile(source["link_pattern"])
        exc = _re.compile(source.get("exclude_pattern", "^$"))
        seen = set()
        for a in soup.find_all("a", href=True):
            full = _abs(a["href"], source["url"])
            if not full or full in seen:
                continue
            if inc.search(full) and not exc.search(full):
                title = a.get_text(strip=True)[:120]
                if len(title) > 8:
                    seen.add(full)
                    items.append({"id": uid(full), "source": source["name"], "title": title, "link": full})

    return items[:20]


def select_opinion(client, candidates):
    """Stuur alle kandidaten naar Claude, laat top 5 selecteren en samenvatten."""
    if not candidates:
        return []

    lijst = "\n".join(
        f"{i+1}. [{c['source']}] {c['title']} — {c['link']}"
        for i, c in enumerate(candidates)
    )

    prompt = f"""Je bent research-assistent voor FoodRise, een Nederlandse campagneorganisatie
die de klimaat- en biodiversiteitsimpact van industriële dierlijke landbouw (Big Ag) aanpakt.
Doelwitten zijn FrieslandCampina, Vion, Nutreco. Thema's: veehouderij, methaan, Scope 3,
greenwashing, EU-landbouwbeleid, kweekvis, ontbossing voor veevoer.

Hieronder staan opinie- en analyseartikelen uit Europese progressieve media.
Selecteer de 5 MEEST RELEVANTE voor FoodRise. Geef per artikel:
- Een Nederlandse samenvatting van precies 3 zinnen
- De originele link

Gebruik dit exacte formaat — vijf blokken, geen extra tekst:

ARTIKEL 1
Bron: [naam]
Titel: [originele titel]
Link: [url]
Samenvatting: [3 zinnen in het Nederlands]

ARTIKEL 2
[etc.]

Kandidaten:
{lijst}"""

    try:
        resp = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1500,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = resp.content[0].text.strip()
    except Exception as e:
        print(f"  ⚠ Opinie-selectie mislukt: {e}")
        return []

    # Parse de vijf blokken
    articles = []
    for block in raw.split("ARTIKEL ")[1:]:
        lines = block.strip().splitlines()
        entry = {}
        summary_lines = []
        in_summary = False
        for line in lines:
            if line.startswith("Bron:"):
                entry["source"] = line.replace("Bron:", "").strip()
            elif line.startswith("Titel:"):
                entry["title"] = line.replace("Titel:", "").strip()
            elif line.startswith("Link:"):
                entry["link"] = line.replace("Link:", "").strip()
            elif line.startswith("Samenvatting:"):
                summary_lines.append(line.replace("Samenvatting:", "").strip())
                in_summary = True
            elif in_summary and line.strip():
                summary_lines.append(line.strip())
        entry["summary"] = " ".join(summary_lines)
        if entry.get("title") and entry.get("link") and entry.get("summary"):
            articles.append(entry)

    return articles[:5]


def build_opinion_section(articles):
    """Bouw HTML voor de opinie-sectie."""
    if not articles:
        return ""

    cards = ""
    for art in articles:
        source = art.get("source", "")
        title = art.get("title", "")
        link = art.get("link", "#")
        summary = art.get("summary", "")
        cards += f"""
        <div style="border-left:3px solid #E8703A;padding:10px 16px;
                    margin-bottom:18px;background:#fafafa">
          <div style="font-size:11px;font-weight:700;color:#E8703A;
                      text-transform:uppercase;letter-spacing:.5px;margin-bottom:5px">
            {source}
          </div>
          <p style="margin:0 0 5px;font-weight:600;font-size:15px;
                    color:#1C4332;line-height:1.3">
            <a href="{link}" style="color:#1C4332;text-decoration:none">{title}</a>
          </p>
          <p style="margin:0 0 6px;font-size:14px;color:#333;line-height:1.5">
            {summary}
          </p>
          <a href="{link}" style="font-size:12px;color:#E8703A;text-decoration:none">
            → lees verder
          </a>
        </div>"""

    return f"""
    <div style="margin-bottom:32px">
      <h2 style="font-size:13px;font-weight:700;letter-spacing:1.5px;
                 text-transform:uppercase;color:#1C4332;
                 border-bottom:2px solid #E8703A;
                 padding-bottom:5px;margin-bottom:14px">
        Analyse &amp; Achtergrond — 5 geselecteerde stukken
      </h2>
      {cards}
    </div>"""



def main():
    print("FoodRise NGO Monitor — start")
    client = Anthropic()
    seen   = load_seen()
    week   = datetime.now().strftime("%-d %B %Y")

    items_by_source = {}
    new_seen = set()
    source_stats = []  # (naam, totaal, nieuw, fout)

    cutoff = datetime.now() - timedelta(days=14)

    def is_recent(item):
        if item.get("date"):
            try:
                for fmt in ["%-d %b %Y", "%d %b %Y"]:
                    try:
                        return datetime.strptime(item["date"], fmt) >= cutoff
                    except ValueError:
                        continue
            except Exception:
                pass
        url = item.get("link", "")
        m = re.search(r"/(20[0-9]{2})/([0-9]{2})/", url)
        if m:
            try:
                item_date = datetime(int(m.group(1)), int(m.group(2)), 1)
                return item_date >= cutoff.replace(day=1)
            except Exception:
                pass
        return True

    for source in SOURCES:
        print(f"  {source['name']} …", end=" ", flush=True)
        try:
            all_items = scrape(source)
            error = False
        except Exception as e:
            print(f"⚠ fout: {e}")
            source_stats.append((source["name"], 0, 0, True))
            continue

        fresh = [i for i in all_items if i["id"] not in seen and is_recent(i)]
        source_stats.append((source["name"], len(all_items), len(fresh), False))

        if not fresh:
            print("geen nieuw")
            continue

        print(f"{len(fresh)} nieuw — samenvatten …")
        summarised = []
        for item in fresh:
            item["summary"] = summarise(client, item)
            summarised.append(item)
            new_seen.add(item["id"])

        items_by_source[source["name"]] = summarised

    total = sum(len(v) for v in items_by_source.values())
    print(f"\nTotaal: {total} nieuwe items")

    save_seen(seen | new_seen)

    if total == 0:
        print("Niets te versturen.")
        return

    # Opinie & Analyse sectie
    print("\nOpinie & Analyse bronnen scrapen …")
    opinion_candidates = []
    for src in OPINION_SOURCES:
        items = scrape_opinion_source(src)
        # Filter al eerder getoonde opinie-items
        fresh = [i for i in items if i.get("id") and i["id"] not in seen and i["id"] not in new_seen and is_recent(i)]
        print(f"  {src['name']}: {len(fresh)} kandidaten ({len(items)} totaal)")
        opinion_candidates.extend(fresh)
    print(f"  Totaal {len(opinion_candidates)} nieuwe kandidaten → top 5 selecteren …")
    selected_opinion = select_opinion(client, opinion_candidates)
    # Sla ALLE kandidaten op in seen (niet alleen top 5)
    for item in opinion_candidates:
        if item.get("id"):
            new_seen.add(item["id"])
    opinion_html = build_opinion_section(selected_opinion)

    # Nieuwe Oogst industrie monitor
    print("\nNieuwe Oogst monitor scrapen …")
    no_results = scrape_nieuwe_oogst()
    for label, items in no_results.items():
        print(f"  {label}: {len(items)} artikel(en)")
    if not no_results:
        print("  Geen matches deze week")
    nieuwe_oogst_html = build_nieuwe_oogst_section(no_results)

    html    = build_html(items_by_source, week, opinion_html, nieuwe_oogst_html, source_stats)
    subject = f"FoodRise NGO Monitor · {week} · {total} items"
    send_mail(html, subject)
    print("Klaar.")


if __name__ == "__main__":
    main()
