import unittest

from companyscan.dimensions.identity import build, check


def page(*docs, phones=(), links=()):
    return {"url": "https://acme.test/", "json_ld": {"documents": list(docs)}, "telephone_numbers": list(phones),
            "links": [{"url": u} for u in links], "open_graph": {}}


DENTIST = {"@type": "Dentist", "name": "Acme Dental", "alternateName": "Acme", "telephone": "+1 (512) 555-0100",
           "address": {"@type": "PostalAddress", "addressLocality": "Austin", "addressRegion": "TX"},
           "sameAs": ["https://www.linkedin.com/company/acme-dental"]}


class BuildTest(unittest.TestCase):
    def test_profile_from_json_ld_links_and_user(self):
        profile = build("https://www.acme.test/", [page(DENTIST, {"@type": "WebSite", "name": "Acme blog"},
                                                        phones=["512.555.0100", "800-555-0199"])],
                        company_name="Acme Dental Group", location="Round Rock, TX, USA")
        self.assertEqual(profile["domain"], "acme.test")
        self.assertEqual(profile["names"], ["Acme Dental Group", "Acme Dental", "Acme"])  # User first; WebSite isn't a business.
        self.assertEqual(profile["cities"], ["Round Rock", "Austin"])
        self.assertEqual(profile["phones"], ["5125550100", "8005550199"])
        self.assertEqual(profile["categories"], ["Dentist"])
        self.assertEqual(profile["profiles"], ["https://www.linkedin.com/company/acme-dental"])

    def test_bare_site_has_only_the_domain(self):
        profile = build("acme.test")
        self.assertEqual(profile, {"domain": "acme.test", "names": [], "cities": [], "phones": [], "categories": [], "profiles": []})


class CheckTest(unittest.TestCase):
    profile = build("acme.test", [page(DENTIST)])

    def test_independent_fact_confirms(self):
        result = check(self.profile, {"website": "acme.test", "city": "Austin", "category": "family dentist"}, given={"website"})
        self.assertEqual(result, {"verdict": "confirmed", "agree": ["city", "category"], "echoed": ["website"], "conflict": []})

    def test_echoed_facts_alone_are_unconfirmed(self):
        result = check(self.profile, {"website": "www.acme.test", "city": "Austin, TX"}, given={"website", "city"})
        self.assertEqual(result["verdict"], "unconfirmed")

    def test_any_conflict_is_a_namesake(self):
        for stated in ({"city": "Denver", "category": "dentist"}, {"website": "acmedental.com"}, {"phone": "303-555-0100"}):
            self.assertEqual(check(self.profile, stated)["verdict"], "mismatch", stated)

    def test_vague_or_missing_facts_are_not_conflicts(self):
        self.assertEqual(check(self.profile, {"city": None, "phone": "call us", "category": "law firm"})["verdict"], "unconfirmed")
        self.assertEqual(check(self.profile, {"website": "linkedin.com/company/acme-dental"})["conflict"], [])
        self.assertEqual(check(build("acme.test"), {"city": "Denver"})["verdict"], "unconfirmed")  # Nothing to compare.


if __name__ == "__main__":
    unittest.main()
