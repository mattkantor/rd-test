import unittest
from companyscan.scan.accessibility import check_html, summarize, render_report


class AccessibilityTests(unittest.TestCase):
    def test_missing_html_features_have_actionable_evidence(self):
        data = check_html('<html><head></head><body>\n<img src="x"><input placeholder="Email"><button></button><a href="/next"></a><iframe src="/embed"></iframe></body></html>')
        self.assertEqual({f['rule_id'] for f in data['findings']}, {'page-title', 'html-lang', 'image-alternative', 'control-name', 'button-name', 'link-name', 'frame-name'})
        for f in data['findings']:
            self.assertTrue(f['recommendation'])
            self.assertTrue(f['wcag']['reference'].startswith('https://www.w3.org/'))
        self.assertEqual(next(f for f in data['findings'] if f['rule_id'] == 'image-alternative')['evidence']['line'], 2)

    def test_labels_image_links_and_decorative_images(self):
        html = '''<html lang="en"><head><title>Contact</title></head><body>
        <img alt=""><img alt="The team"><label for="email">Email</label><input id="email">
        <label>Your name <input></label><input type="hidden"><input type="submit">
        <span id="label">Phone</span><input aria-labelledby="label">
        <button aria-label="Close"></button><a href="/"><img alt="Home"></a>
        <iframe title="Map"></iframe><div hidden><button></button><img></div>
        </body></html>'''
        self.assertEqual(check_html(html)['findings'], [])

    def test_invalid_label_reference_and_svg_title_not_page_title(self):
        data = check_html('<html lang="en"><body><svg><title>Icon</title></svg><input aria-labelledby="missing"><label for="other">Label</label><input id="field"></body></html>')
        self.assertEqual(sum(f['rule_id'] == 'control-name' for f in data['findings']), 2)
        self.assertIn('page-title', [f['rule_id'] for f in data['findings']])

    def test_hidden_button_text_and_valueless_attributes(self):
        data = check_html('<html lang><head><title></title></head><body><button aria-hidden><span hidden>Invisible name</span></button></body></html>')
        self.assertIn('button-name', [f['rule_id'] for f in data['findings']])

    def test_clean_checks_never_claim_conformance(self):
        page = {'id': '0001', 'url': 'https://example.com/', 'retrieved_at': '2026-09-23T00:00:00Z',
                'accessibility': check_html('<html lang="en"><head><title>Test</title></head></html>')}
        report = summarize([page])
        self.assertEqual(report['automated_status'], 'PASS')
        self.assertEqual(report['conformance_status'], 'UNKNOWN')
        self.assertTrue(report['manual_review_required'])
        self.assertIn('not WCAG compliance', render_report(report))

    def test_failed_old_truncated_and_duplicate_captures_are_unknown(self):
        for extra in ({}, {'error': 'HTTP 500'}, {'truncated': True, 'accessibility': check_html('')}, {'duplicate_of': 'https://example.com/', 'accessibility': check_html('')}):
            report = summarize([{'id': '0001', 'url': 'https://example.com/', **extra}])
            self.assertEqual(report['automated_status'], 'UNKNOWN')
            self.assertEqual(report['pages_checked'], 0)
            self.assertEqual(len(report['pages_excluded']), 1)
        self.assertEqual(summarize([])['automated_status'], 'UNKNOWN')

    def test_summary_keeps_sources_and_crawl_gaps(self):
        page = {'id': '0002', 'url': 'https://example.com/form', 'retrieved_at': '2026-09-23T00:00:00Z', 'accessibility': check_html('<input>')}
        report = summarize([page], [{'url': 'https://example.com/cart', 'reason': 'excluded_path_or_query'}])
        self.assertEqual(report['automated_status'], 'WARNING')
        self.assertEqual(report['findings'][0]['artifact'], 'pages/0002.json')
        self.assertEqual(len(report['urls_skipped']), 1)
