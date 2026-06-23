# FoodRise NGO Monitor

Wekelijkse AI-nieuwsbrief van 11 NGO-bronnen. Draait automatisch elke maandag
via GitHub Actions, samenvat met Claude, stuurt per mail.

## Setup (eenmalig, ~10 minuten)

### 1. Repo aanmaken
Maak een **private** repo op github.com, upload deze bestanden.

### 2. Gmail app-wachtwoord
1. Ga naar myaccount.google.com/security → 2-stapsverificatie aan
2. Ga naar myaccount.google.com/apppasswords
3. Maak app-wachtwoord voor "Mail" → kopieer de 16 tekens

### 3. GitHub Secrets instellen
Settings → Secrets and variables → Actions → New repository secret:

| Naam | Waarde |
|---|---|
| `ANTHROPIC_API_KEY` | Je Anthropic API-sleutel (console.anthropic.com) |
| `GMAIL_USER` | Je Gmail-adres |
| `GMAIL_APP_PASSWORD` | Het app-wachtwoord uit stap 2 |
| `NEWSLETTER_TO` | Ontvangstadres nieuwsbrief |

### 4. Eerste test
Actions → FoodRise NGO Monitor → Run workflow

## Bronnen
11 actieve bronnen: Changing Markets, Foodrise EU, GRAIN, ClientEarth,
IATP, Ecologistas en Acción, Greenpeace Aotearoa, Mighty Earth,
Milieudefensie, Greenpeace Nordic, Justicia Alimentaria, Seastemik.

## Kosten
- GitHub Actions: gratis
- Anthropic API: ~€0,05–0,15 per week
