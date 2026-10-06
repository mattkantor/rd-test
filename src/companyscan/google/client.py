"""Thin Business Profile API wrapper: takes an access token, returns plain dicts. Retries once on 401 (after asking `renew`
for a fresh token) and up to three times with backoff on 429/5xx. Never log tokens, review text or reply drafts."""
import json
import logging
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

log = logging.getLogger(__name__)

ACCOUNTS = "https://mybusinessaccountmanagement.googleapis.com/v1/"
INFO = "https://mybusinessbusinessinformation.googleapis.com/v1/"
VERIFY = "https://mybusinessverifications.googleapis.com/v1/"
REVIEWS = "https://mybusiness.googleapis.com/v4/"
QNA = "https://mybusinessqanda.googleapis.com/v1/"
READ_MASK = "name,title,phoneNumbers,storefrontAddress,websiteUri,regularHours,categories,profile"


class ApiError(ValueError):
    """A request Google refused; the message is Google's, safe to show the customer."""


def sleep(seconds):  # Replaced in tests.
    time.sleep(seconds)


class Client:
    def __init__(self, token, renew=None):
        self.token, self.renew = token, renew

    def call(self, method, url, body=None):
        renewed = False
        for attempt in range(4):
            request = Request(url, method=method, data=None if body is None else json.dumps(body).encode(),
                              headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"})
            try:
                with urlopen(request, timeout=30) as r:
                    return json.loads(r.read() or b"{}")
            except HTTPError as exc:
                if exc.code == 401 and self.renew and not renewed:
                    self.token, renewed = self.renew(), True
                    continue
                if exc.code in (429, 500, 502, 503, 504) and attempt < 3:
                    sleep(2 ** attempt)
                    continue
                raise ApiError(self.message(exc)) from exc
        raise ApiError("Google did not answer")

    @staticmethod
    def message(exc):
        try:
            return str(json.load(exc)["error"]["message"])[:300]
        except (ValueError, KeyError, TypeError):
            return f"Google returned HTTP {exc.code}"

    def locations(self):
        """Every location of every account this user manages: [{"account", "name", "title", "websiteUri", "phoneNumbers"}]."""
        found = []
        for account in self.call("GET", ACCOUNTS + "accounts").get("accounts", []):
            data = self.call("GET", f"{INFO}{account['name']}/locations?readMask=name,title,websiteUri,phoneNumbers&pageSize=100")
            found += [{**loc, "account": account["name"]} for loc in data.get("locations", [])]
        return found

    def location(self, name):
        return self.call("GET", f"{INFO}{name}?readMask={READ_MASK}")

    def patch_location(self, name, mask, body):
        return self.call("PATCH", f"{INFO}{name}?updateMask={mask}", body)

    def claimed(self, name):
        return bool(self.call("GET", f"{VERIFY}{name}/VoiceOfMerchantState").get("hasVoiceOfMerchant"))

    def verifications(self, name):
        return self.call("GET", f"{VERIFY}{name}/verifications").get("verifications", [])

    def verification_options(self, name):
        return self.call("POST", f"{VERIFY}{name}:fetchVerificationOptions", {"languageCode": "en"}).get("options", [])

    def start_verification(self, name, method):
        return self.call("POST", f"{VERIFY}{name}:verify", {"method": method})

    def reviews(self, account, name):
        return self.call("GET", f"{REVIEWS}{account}/{name}/reviews").get("reviews", [])

    def reply_to_review(self, review, text):
        return self.call("PUT", f"{REVIEWS}{review}/reply", {"comment": text})

    def questions(self, name):
        return self.call("GET", f"{QNA}{name}/questions").get("questions", [])

    def answer_question(self, question, text):
        return self.call("POST", f"{QNA}{question}/answers:upsert", {"answer": {"text": text}})
