import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from scraper.details import EMPTY_LIMIT, enrich

from scraper.features import detect_features
from scraper.merge import merge_listings
from scraper.parsing import generation, make_listing, norm_fuel, parse_variant
from scraper.robots import RobotRules
from scraper.sources import autoscout24, autotrack, marktplaats, viabovag

AGENT = "bmw-x1-marktoverzicht"


def flight_page(payload: str) -> str:
    return f"<script>self.__next_f.push([1,{json.dumps(payload)}])</script>"


class RobotsTest(unittest.TestCase):
    def test_wildcards_and_longest_match(self):
        rules = RobotRules("User-agent: *\nDisallow: /*?\nAllow: /auto*?page=*\n", AGENT)
        self.assertFalse(rules.allowed("/bmw/x1?page=2"))
        self.assertTrue(rules.allowed("/auto/x?page=2"))
        self.assertTrue(rules.allowed("/bmw/x1"))

    def test_end_anchor(self):
        rules = RobotRules("User-agent: *\nDisallow: /lst*\nAllow: /lst$\n", AGENT)
        self.assertTrue(rules.allowed("/lst"))
        self.assertFalse(rules.allowed("/lst/bmw"))

    def test_group_of_other_agent_does_not_apply(self):
        text = "User-agent: GPTBot\nUser-agent: ClaudeBot\nDisallow: /\n\nUser-agent: *\nDisallow: /private\n"
        rules = RobotRules(text, AGENT)
        self.assertTrue(rules.allowed("/lst/bmw/x1"))
        self.assertFalse(rules.allowed("/private/x"))

    def test_named_ai_agent_is_disallowed(self):
        text = "User-agent: GPTBot\nUser-agent: ClaudeBot\nDisallow: /\n\nUser-agent: *\nDisallow: /private\n"
        self.assertFalse(RobotRules(text, "ClaudeBot").allowed("/lst/bmw/x1"))


class NormalisationTest(unittest.TestCase):
    def test_fuel(self):
        self.assertEqual(norm_fuel("Elektro/Benzine"), "Hybride")
        self.assertEqual(norm_fuel("BENZINE"), "Benzine")
        self.assertEqual(norm_fuel("Hybride", plugin=True), "Plug-in hybride")

    def test_variant(self):
        parsed = parse_variant("BMW X1 SDrive20i Centennial High Executive")
        self.assertEqual(parsed, {"variant": "sDrive20i", "drivetrain": "sDrive", "trim": "High Executive"})

    def test_e_variant_with_hybrid_fuel_is_plugin(self):
        listing = make_listing("x", 1, "u", title="BMW X1 xDrive25e", fuel="Hybride")
        self.assertEqual(listing["fuel"], "Plug-in hybride")

    def test_bait_price_is_dropped(self):
        self.assertIsNone(make_listing("x", 1, "u", price_eur=1)["price_eur"])
        self.assertEqual(make_listing("x", 1, "u", price_eur=2850)["price_eur"], 2850)

    def test_plugin_from_variant_when_fuel_is_vague(self):
        listing = make_listing("x", 1, "u", title="BMW X1 xDrive25e", fuel="Overig")
        self.assertEqual(listing["fuel"], "Plug-in hybride")
        self.assertEqual(make_listing("x", 1, "u", title="X1 M35i xDrive")["variant"], "M35i")

    def test_e_variant_labelled_as_petrol_is_plugin(self):
        listing = make_listing("x", 1, "u", title="BMW X1 xDrive25e", fuel="Benzine")
        self.assertEqual(listing["fuel"], "Plug-in hybride")

    def test_placeholders_are_cleared(self):
        listing = make_listing("x", 1, "u", seller_name="Onbekende dealer", power_hp=0)
        self.assertIsNone(listing["seller_name"])
        self.assertIsNone(listing["power_hp"])

    def test_generation(self):
        self.assertEqual(generation(2012), "E84 (2009-2015)")
        self.assertEqual(generation(2019), "F48 (2015-2022)")
        self.assertEqual(generation(2024), "U11 (2022-nu)")
        self.assertIsNone(generation(None))


class MarktplaatsTest(unittest.TestCase):
    def raw(self, **overrides):
        base = {
            "itemId": "m1", "title": "BMW X1 sDrive18i", "vipUrl": "/v/a",
            "priceInfo": {"priceCents": 1500000, "priceType": "FIXED"},
            "location": {"cityName": "Breda"}, "imageUrls": ["//img/1.jpg"],
            "sellerInformation": {"sellerName": "Jan Jansen"},
            "attributes": [{"key": "model", "value": "X1"}, {"key": "mileage", "value": "100000"},
                           {"key": "constructionYear", "value": "2018"}],
            "extendedAttributes": [{"key": "advertiser", "value": "Particulier"}],
        }
        base.update(overrides)
        return base

    def test_private_seller_name_is_not_stored(self):
        listing = marktplaats.parse_listing(self.raw())
        self.assertEqual(listing["seller_type"], "Particulier")
        self.assertIsNone(listing["seller_name"])

    def test_min_bid_amount_is_kept_and_marked(self):
        listing = marktplaats.parse_listing(self.raw(priceInfo={"priceCents": 795000, "priceType": "MIN_BID"}))
        self.assertEqual(listing["price_eur"], 7950)
        self.assertTrue(listing["price_is_bid"])

    def test_see_description_has_no_price(self):
        listing = marktplaats.parse_listing(self.raw(priceInfo={"priceCents": 0, "priceType": "SEE_DESCRIPTION"}))
        self.assertIsNone(listing["price_eur"])
        self.assertFalse(listing["price_is_bid"])

    def test_other_model_is_skipped(self):
        raw = self.raw(attributes=[{"key": "model", "value": "iX1"}])
        self.assertIsNone(marktplaats.parse_listing(raw))

    def test_new_cars_are_skipped_even_without_label(self):
        attrs = [{"key": "model", "value": "X1"}, {"key": "mileage", "value": "10"}]
        self.assertIsNone(marktplaats.parse_listing(self.raw(attributes=attrs)))
        labelled = attrs + [{"key": "condition", "value": "Gebruikt"}]
        self.assertIsNotNone(marktplaats.parse_listing(self.raw(attributes=labelled)))

    def test_image_url_gets_scheme(self):
        self.assertEqual(marktplaats.parse_listing(self.raw())["image_url"], "https://img/1.jpg")


class ViaBovagTest(unittest.TestCase):
    def test_parse_page_from_flight_data(self):
        payload = '"searchResults":"vertaling","x":1,"searchResults":{"results":[{"id":"a","url":"https://v/a","title":"BMW X1 sDrive20i","price":20000,"vehicle":{"model":"X1","condition":"Occasion","mileage":5000,"year":2020,"fuelType":"Benzine","licensePlate":"AB-123-C","enginePower":192,"color":"zwart"},"company":{"name":"Dealer","city":"Ede"}},{"id":"b","vehicle":{"model":"X1","condition":"Nieuw"}}],"count":7}'
        items, count = viabovag.parse_page(flight_page(payload))
        self.assertEqual(count, 7)
        self.assertEqual([i["source_id"] for i in items], ["a"])
        self.assertEqual(items[0]["license_plate"], "AB123C")
        self.assertEqual(items[0]["color"], "Zwart")


class AutoTrackTest(unittest.TestCase):
    def test_parse_ad(self):
        ad = {"beschikbaarheidsStatus": "beschikbaar", "advertentieId": 9, "soortAuto": "OCCASION", "kenteken": "PN901V",
              "prijs": {"totaalInclusiefBtw": 20900},
              "autogegevens": {"algemeen": {"modelnaam": "X1", "brandstofsoort": "BENZINE", "brandstofsoortSlug": "benzine",
                                            "transmissietype": "AUTOMATISCH", "kleur": "ZWART", "commercieleUitvoering": "sDrive20i M-Sport"},
                               "motor": {"vermogenPk": 192, "vermogenKw": 141},
                               "geschiedenis": {"bouwjaar": 2017, "kilometerstand": 124071, "catalogusprijs": 53651}},
              "aanbieder": {"aanbiedergegevens": {"naam": "Garage", "plaatsnaam": "Spierdijk", "provincie": "Noord-Holland"}}}
        items, _ = autotrack.parse_page(flight_page("x:" + json.dumps(ad) + ",y"))
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["variant"], "sDrive20i")
        self.assertEqual(items[0]["catalog_price_eur"], 53651)
        self.assertEqual(items[0]["url"], "https://www.autotrack.nl/a/bmw-x1-benzine-2017-9")

    def test_sitemap_only_keeps_x1(self):
        xml = ("<loc>https://www.autotrack.nl/aanbod/merk/bmw/model/x1/provincie/a/plaatsnaam/b</loc>"
               "<loc>https://www.autotrack.nl/aanbod/merk/bmw/model/x1</loc>"
               "<loc>https://www.autotrack.nl/aanbod/merk/bmw/model/x10</loc>"
               "<loc>https://www.autotrack.nl/aanbod/merk/bmw/model/x4</loc>")
        self.assertEqual(len(autotrack.slices_from_sitemap(xml)), 2)


class AutoScout24Test(unittest.TestCase):
    def test_parse_listing(self):
        raw = {"id": "a", "url": "/aanbod/a", "images": ["i"], "price": {"priceRaw": 4850, "suggestedRetailPrice": "€ 48.846"},
               "vehicle": {"model": "X1", "offerType": "U", "modelVersionInput": "xDrive20i Business", "fuel": "Benzine",
                           "transmission": "Handgeschakeld"},
               "vehicleDetails": [{"iconName": "speedometer", "data": "135 kW (184 PK)"}],
               "tracking": {"firstRegistration": "06-2012", "mileage": "195492"},
               "location": {"city": "HARDERWIJK"}, "seller": {"type": "Dealer", "companyName": "Garage"}}
        listing = autoscout24.parse_listing(raw)
        self.assertEqual((listing["year"], listing["power_hp"], listing["city"]), (2012, 184, "Harderwijk"))


def ad(source, source_id, **fields):
    return make_listing(source, source_id, f"https://{source}/{source_id}", **fields)


class FeaturesTest(unittest.TestCase):
    def test_labels_of_all_sites(self):
        found, source = detect_features(["Adaptive Cruise Control", "Parkeercamera", "Head-up Display", "Dakraam",
                                         "Trekhaak met afneembare kogel", "Elektrische achterklep"], [])
        self.assertEqual(source, "optielijst")
        for name in ("Adaptive cruise control", "Achteruitrijcamera", "Head-up display", "Panorama-/schuifdak",
                     "Trekhaak", "Elektrische achterklep"):
            self.assertIn(name, found)

    def test_title_is_used_only_without_any_list(self):
        self.assertEqual(detect_features([], ["BMW X1 Pano | ACC"]),
                         (["Adaptive cruise control", "Panorama-/schuifdak"], "titel"))
        self.assertEqual(detect_features(["Radio"], ["BMW X1 Pano | ACC"]), ([], "optielijst"))
        self.assertEqual(detect_features([], ["BMW X1"]), ([], None))

    def test_m_sport_comes_from_text_even_with_list(self):
        self.assertEqual(detect_features(["Radio"], ["BMW X1 M-Sport"])[0], ["M Sport"])

    def test_title_abbreviations(self):
        found, _ = detect_features([], ["BMW X1 | HuD | Afn.Trekhaak | Elek.A-klep | Active Cruise Control"])
        for name in ("Head-up display", "Trekhaak", "Elektrische achterklep", "Adaptive cruise control"):
            self.assertIn(name, found)

    def test_plain_cruise_control_is_not_adaptive(self):
        self.assertNotIn("Adaptive cruise control", detect_features(["Cruise Control"], ["Accu nieuw"])[0])

    def test_negation_and_leather_steering_wheel(self):
        found, _ = detect_features([], ["BMW X1 geen trekhaak, lederen stuurwiel"])
        self.assertNotIn("Trekhaak", found)
        self.assertNotIn("Leder", found)
        self.assertNotIn("Leder", detect_features(["Stuurwiel leer"], [])[0])
        self.assertIn("Leder", detect_features(["lederen interieur"], [])[0])


class DetailParsingTest(unittest.TestCase):
    def test_autotrack_flattens_categories(self):
        payload = 'x,"options":[{"categoryName":"Exterieur","options":[{"name":"Dak","suboptions":["Panoramadak","Open dak"]},{"name":"Alarmsysteem"}]},{"categoryName":"Overig","options":[{"name":"lederen interieur"}]}],"y":1'
        self.assertEqual(autotrack.parse_detail(flight_page(payload)),
                         ["Panoramadak", "Open dak", "Alarmsysteem", "lederen interieur"])
        self.assertEqual(autotrack.parse_detail(flight_page('"options":[{"name":"x"}]')), [])

    def test_viabovag_keeps_only_present_values(self):
        payload = 'x,"accessories":[{"value":"a","hasValue":true,"formattedValue":"Panoramadak"},{"value":"b","hasValue":false,"formattedValue":"Radio"}],"y":1'
        self.assertEqual(viabovag.parse_detail(flight_page(payload)), ["Panoramadak"])


class FakeFetcher:
    def __init__(self, pages):
        self.pages = pages
        self.urls = []

    def get(self, url):
        self.urls.append(url)
        result = self.pages.get(url, "leeg")
        if isinstance(result, Exception):
            raise result
        return None if result is None else SimpleNamespace(text=result)


class FakeRun:
    site = "testsite"
    status = "ok"
    options_missing = None

    def __init__(self, count):
        self.listings = {str(i): {"source_id": str(i), "url": f"u{i}", "options": []} for i in range(count)}
        self.notes = []

    def note(self, text):
        self.notes.append(text)


class EnrichTest(unittest.TestCase):
    parse = staticmethod(lambda text: [] if text == "leeg" else [text])

    def test_second_run_only_fetches_new_ads(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = FakeFetcher({"u0": "A", "u1": "B"})
            enrich(first, FakeRun(2), self.parse, Path(tmp))
            self.assertEqual(first.urls, ["u0", "u1"])
            second, run = FakeFetcher({"u2": "C"}), FakeRun(3)
            enrich(second, run, self.parse, Path(tmp))
            self.assertEqual(second.urls, ["u2"])
            self.assertEqual([l["options"] for l in run.listings.values()], [["A"], ["B"], ["C"]])

    def test_block_keeps_what_was_fetched_and_resumes(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = FakeRun(3)
            with self.assertRaises(RuntimeError):
                enrich(FakeFetcher({"u0": "A", "u1": RuntimeError("geblokkeerd")}), run, self.parse, Path(tmp))
            self.assertEqual(run.listings["0"]["options"], ["A"])
            resumed = FakeFetcher({"u1": "B", "u2": "C"})
            enrich(resumed, FakeRun(3), self.parse, Path(tmp))
            self.assertEqual(resumed.urls, ["u1", "u2"])

    def test_removed_ad_is_not_cached(self):
        with tempfile.TemporaryDirectory() as tmp:
            enrich(FakeFetcher({"u0": None}), FakeRun(1), self.parse, Path(tmp))
            again = FakeFetcher({"u0": "A"})
            enrich(again, FakeRun(1), self.parse, Path(tmp))
            self.assertEqual(again.urls, ["u0"])

    def test_stale_parser_stops_early_without_poisoning_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            fetcher, run = FakeFetcher({}), FakeRun(EMPTY_LIMIT + 20)
            enrich(fetcher, run, self.parse, Path(tmp))
            self.assertEqual(len(fetcher.urls), EMPTY_LIMIT)
            self.assertEqual(run.status, "fout")
            self.assertEqual(json.loads((Path(tmp) / "testsite.json").read_text()), {})


class MergeTest(unittest.TestCase):
    def test_same_plate_merges_and_keeps_lowest_price(self):
        cars = merge_listings([
            ad("autotrack", 1, license_plate="AB123C", price_eur=21000, year=2019, mileage_km=50000),
            ad("viabovag", 2, license_plate="AB123C", price_eur=20500, year=2019, mileage_km=50100, color="Zwart"),
        ])
        self.assertEqual(len(cars), 1)
        self.assertEqual(cars[0]["price_eur"], 20500)
        self.assertEqual(cars[0]["color"], "Zwart")
        self.assertEqual({s["site"] for s in cars[0]["sources"]}, {"autotrack", "viabovag"})

    def test_exact_mileage_with_same_city_links_site_without_plate(self):
        cars = merge_listings([
            ad("autotrack", 1, license_plate="AB123C", year=2019, mileage_km=51234, price_eur=20000, city="Breda"),
            ad("marktplaats", 2, year=2019, mileage_km=51234, price_eur=20500, city="Breda"),
        ])
        self.assertEqual(len(cars), 1)

    def test_same_demo_mileage_elsewhere_is_a_different_car(self):
        cars = merge_listings([
            ad("gaspedaal", 1, year=2026, mileage_km=2500, price_eur=64815, city="Ede"),
            ad("marktplaats", 2, year=2026, mileage_km=2500, price_eur=72950, city="Goes"),
        ])
        self.assertEqual(len(cars), 2)

    def test_two_ads_on_same_site_need_a_plate_to_merge(self):
        cars = merge_listings([
            ad("marktplaats", 1, year=2026, mileage_km=2500, price_eur=64815),
            ad("marktplaats", 2, year=2026, mileage_km=2500, price_eur=64815),
        ])
        self.assertEqual(len(cars), 2)

    def test_chain_through_soft_key_does_not_join_different_plates(self):
        cars = merge_listings([
            ad("autotrack", 1, license_plate="AB123C", year=2019, mileage_km=51234, price_eur=20000),
            ad("marktplaats", 2, year=2019, mileage_km=51234, price_eur=20000),
            ad("viabovag", 3, license_plate="XY987Z", year=2019, mileage_km=51234, price_eur=20000),
        ])
        self.assertEqual(len(cars), 2)

    def test_different_plates_never_merge(self):
        cars = merge_listings([
            ad("autotrack", 1, license_plate="AB123C", year=2019, mileage_km=51234),
            ad("viabovag", 2, license_plate="XY987Z", year=2019, mileage_km=51234),
        ])
        self.assertEqual(len(cars), 2)

    def test_round_mileage_requires_equal_price(self):
        cars = merge_listings([
            ad("gaspedaal", 1, year=2019, mileage_km=50000, price_eur=20000),
            ad("marktplaats", 2, year=2019, mileage_km=50000, price_eur=25000),
        ])
        self.assertEqual(len(cars), 2)

    def test_features_use_titles_of_all_sites(self):
        cars = merge_listings([
            ad("viabovag", 1, license_plate="AB123C", title="BMW X1 sDrive18i"),
            ad("autotrack", 2, license_plate="AB123C", title="BMW X1 sDrive18i Pano"),
            ad("marktplaats", 3, license_plate="AB123C", title="BMW X1", options=["Adaptive Cruise Control"]),
        ])
        # De lijst van Marktplaats telt; "Pano" uit de titel van AutoTrack dus niet.
        self.assertEqual(cars[0]["features"], ["Adaptive cruise control"])
        self.assertEqual(cars[0]["features_source"], "optielijst")

    def test_options_of_all_sites_are_combined(self):
        cars = merge_listings([
            ad("autotrack", 1, license_plate="AB123C", options=["Panoramadak", "Radio"]),
            ad("viabovag", 2, license_plate="AB123C", options=["Radio", "Trekhaak"]),
        ])
        self.assertEqual(cars[0]["options"], ["Radio", "Trekhaak", "Panoramadak"])
        self.assertEqual(cars[0]["features"], ["Panorama-/schuifdak", "Trekhaak"])

    def test_province_is_filled_from_city(self):
        cars = merge_listings([
            ad("autotrack", 1, license_plate="AB123C", city="Breda", province="Noord-Brabant"),
            ad("marktplaats", 2, city="BREDA"),
        ])
        self.assertEqual({c["province"] for c in cars}, {"Noord-Brabant"})


if __name__ == "__main__":
    unittest.main()
