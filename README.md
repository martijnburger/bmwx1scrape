# BMW X1 marktoverzicht

Live: https://bmwx1scrape.netlify.app

Verzamelt tweedehands BMW X1-advertenties van Nederlandse autosites in één JSON-array en toont
die in een webapp met filters en doorsnijdingen. Alleen de standaardbibliotheek van Python is
nodig; er is niets te installeren.

## Gebruik

```sh
python3 -m scraper                 # eerste keer ca. 2 uur, daarna veel korter dankzij de cache
python3 -m scraper --sites autoscout24   # AutoScout24 alleen op verzoek
python3 -m http.server 8000        # vanuit deze map
# open http://localhost:8000/web/
```

Handige opties:

| Optie | Betekenis |
|---|---|
| `--sites marktplaats,viabovag` | Alleen deze sites vernieuwen; de rest blijft staan |
| `--delay 3` | Seconden tussen verzoeken per site (minimaal 1) |
| `--max-requests 800` | Bovengrens aan verzoeken per site |
| `--merge-only` | Alleen `data/raw/` opnieuw samenvoegen |

Tests: `python3 -m unittest discover -s tests -t .`

## Uitvoer

- `data/listings.json`: de JSON-array, één object per auto.
- `data/report.json`: per site de status, en het aantal opgehaalde tegenover gemelde advertenties.
- `data/raw/<site>.json`: de advertenties per site, vóór het samenvoegen (niet in git).
- `data/cache/<site>.json`: opties per advertentie, zodat een nieuwe run alleen nieuwe pagina's ophaalt
  (niet in git).

Staat dezelfde auto op meerdere sites, dan wordt dat één object. `sources` bevat dan elke
advertentie met link en prijs, en `price_eur` is de laagste prijs. Herkenning gebeurt op kenteken, of
anders op bouwjaar en exacte kilometerstand samen met dezelfde prijs of plaats. Twee verschillende
kentekens worden nooit samengevoegd, en twee advertenties van één site alleen bij hetzelfde kenteken.
Een dubbel geplaatste advertentie zonder kenteken kan daardoor als twee auto's verschijnen.

## Sites

| Site | Standaard | Route |
|---|---|---|
| Marktplaats | ja | Paginering |
| viaBOVAG | ja | Gecombineerde filterpaden: bouwjaar, brandstof, kleur, transmissie |
| AutoTrack | ja | Filterpagina's uit de sitemap, onder meer per plaats |
| Gaspedaal | ja | Enkelvoudige filterpagina's: bouwjaar, brandstof, kleur enz. |
| AutoScout24 | nee, `--sites autoscout24` | Paginering, gesplitst op prijs |
| mobile.de, AutoWereld | niet opgenomen | Weigeren automatische verzoeken (HTTP 403) |

## Spelregels van de scraper

- Identificeert zich met een eigen user-agent en doet zich niet voor als browser.
- Volgt `robots.txt`, inclusief `*`- en `$`-patronen. Uitgesloten URL's worden overgeslagen.
- Stopt met een site bij HTTP 401/403 of aanhoudende 429/503, zonder te proberen dat te omzeilen.
- Slaat namen van particuliere verkopers niet op.

AutoScout24 sluit in `robots.txt` AI-crawlers zoals ClaudeBot en GPTBot uit. Deze scraper valt daar
technisch niet onder, omdat hij onder de algemene regels valt die `/lst` toestaan, maar de site
doet alleen mee als je er expliciet om vraagt.

De advertentiegegevens zijn van de betreffende sites en adverteerders. Dat de data hier staat,
betekent niet dat je ze zonder meer mag hergebruiken; controleer daarvoor de voorwaarden van die sites.

## Beperkingen

- **Dekking:** sites tonen niet alles via toegestane routes. Bekijk "Databronnen en dekking" in de
  webapp of `data/report.json`.
- **Opties** (`features`): komen uit de optielijsten van Marktplaats, AutoTrack, viaBOVAG en AutoScout24.
  Stopt een run met "parser is waarschijnlijk verouderd", dan is de paginastructuur van die site
  veranderd. Alleen als een auto op geen van die sites een lijst heeft, is de titel het laatste redmiddel (`features_source`).
  M Sport en het audiomerk mogen altijd uit de tekst komen, omdat optielijsten daar meestal geen plek
  voor hebben. Verkopers vullen lijsten zelf in, dus "niet gevonden" betekent niet dat de optie ontbreekt.
- **Generatie** is afgeleid uit het bouwjaar. Rond de wisseljaren 2015 en 2022 kan dat afwijken.
- **Gaspedaal** geeft geen directe advertentielink in de toegestane data; de link gaat naar het
  X1-overzicht.
- **Nieuwe auto's** worden herkend aan het label van de site; bij Marktplaats tellen advertenties
  zonder label met maximaal 100 km ook als nieuw.
- **Biedprijzen:** bij Marktplaats zetten autobedrijven hun prijs vaak bij "bieden vanaf". Dat bedrag
  telt mee als prijs en krijgt `price_is_bid: true`; de echte verkoopprijs kan afwijken.
- **Prijzen onder € 500** worden als ontbrekend behandeld, omdat dit lokprijzen zijn.
- Sites wijzigen hun pagina's; bij een lege of veel kleinere oogst is de parser waarschijnlijk aan
  onderhoud toe.
