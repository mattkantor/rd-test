"""Conservative static HTML accessibility checks; never a conformance certificate."""
from collections import Counter
from html.parser import HTMLParser
import re

STANDARD = 'https://www.w3.org/TR/WCAG22/'
RULES = {
    'page-title': ('2.4.2', 'Page Titled', 'page-titled', 'Give the page a nonempty, descriptive title.'),
    'html-lang': ('3.1.1', 'Language of Page', 'language-of-page', 'Set html lang to the correct language tag and verify it matches the content.'),
    'image-alternative': ('1.1.1', 'Non-text Content', 'non-text-content', 'Provide a meaningful text alternative; use alt="" only for decorative images.'),
    'control-name': ('4.1.2', 'Name, Role, Value', 'name-role-value', 'Associate a descriptive label with this control and verify its accessible name in a browser.'),
    'button-name': ('4.1.2', 'Name, Role, Value', 'name-role-value', 'Give the button a descriptive accessible name that includes its visible label.'),
    'link-name': ('2.4.4', 'Link Purpose (In Context)', 'link-purpose-in-context', 'Provide link text or a text alternative that communicates its purpose in context.'),
    'frame-name': ('4.1.2', 'Name, Role, Value', 'name-role-value', 'Give the frame a descriptive title or accessible label and audit its contents separately.'),
}
MANUAL = [
    ('Keyboard and focus', ['2.1.1', '2.1.2', '2.4.3', '2.4.7', '2.4.11'], 'Test every interactive control, focus order, visible focus, traps and obscured focus.'),
    ('Contrast, zoom and reflow', ['1.4.3', '1.4.4', '1.4.10', '1.4.11', '1.4.12'], 'Measure rendered contrast and test zoom, narrow viewports and text spacing.'),
    ('Screen readers and semantics', ['1.3.1', '1.3.2', '2.4.6', '4.1.2', '4.1.3'], 'Inspect the accessibility tree, reading order, headings, tables, widget states and status announcements.'),
    ('Text alternatives and language', ['1.1.1', '3.1.1', '3.1.2'], 'Check alternative-text quality, decorative intent, document language and language changes.'),
    ('Forms and complete journeys', ['1.3.5', '3.3.1', '3.3.2', '3.3.3', '3.3.4', '3.3.7', '3.3.8'], 'Test labels, errors, input purpose, repeated entry, authentication and complete critical user journeys.'),
    ('Media, motion and timing', ['1.2.1', '1.2.2', '1.2.3', '1.2.4', '1.2.5', '2.2.1', '2.2.2', '2.3.1'], 'Review captions, transcripts, audio descriptions, time limits, moving content and flashing.'),
    ('Pointer, touch and navigation', ['2.5.1', '2.5.2', '2.5.3', '2.5.7', '2.5.8', '2.4.1', '2.4.5', '3.2.6'], 'Test gestures, dragging alternatives, target sizes, label-in-name, bypass links, navigation and consistent help.'),
]
LIMITATIONS = [
    'Static HTML heuristics only: not axe-core, a browser audit, or a full accessible-name computation.',
    'No CSS, JavaScript, shadow DOM, iframe contents, computed visibility, contrast or keyboard behavior is evaluated.',
    'A passed check means only that its limited HTML condition passed; it does not establish that a WCAG criterion passed.',
    'Findings are potential barriers requiring rendered-page confirmation; no findings does not mean WCAG conformance.',
    'The manual-review checklist is a starting point, not an exhaustive list of WCAG 2.2 A/AA criteria.',
]
VOID = set('area base br col embed hr img input link meta param source track wbr'.split())


class Document(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.nodes, self.stack = [], []

    def handle_starttag(self, tag, attrs):
        attrs = {key: value or '' for key, value in attrs}
        parent = self.stack[-1] if self.stack else None
        hidden = (parent is not None and self.nodes[parent]['hidden']) or tag in {'script', 'style', 'template', 'noscript'} or 'hidden' in attrs or attrs.get('aria-hidden', '').lower() == 'true' or bool(re.search(r'display\s*:\s*none|visibility\s*:\s*hidden', attrs.get('style', ''), re.I))
        node = {'tag': tag, 'attrs': attrs, 'parent': parent, 'hidden': hidden, 'text': [],
                'line': self.getpos()[0], 'column': self.getpos()[1] + 1,
                'html': self.get_starttag_text()[:500]}
        self.nodes.append(node)
        if tag not in VOID:
            self.stack.append(len(self.nodes) - 1)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, -1, -1):
            if self.nodes[self.stack[i]]['tag'] == tag:
                del self.stack[i:]
                break

    def handle_data(self, data):
        for i in self.stack:
            if not self.nodes[self.stack[-1]]['hidden'] or self.nodes[i]['hidden']:
                self.nodes[i]['text'].append(data)


def text(node):
    return ' '.join(''.join(node['text']).split())


def check_html(html):
    document = Document()
    document.feed(html)
    nodes = document.nodes
    by_id = {n['attrs']['id']: n for n in nodes if n['attrs'].get('id')}
    findings, checked = [], Counter()

    def has_name(n, content=False):
        a = n['attrs']
        refs = a.get('aria-labelledby', '').split()
        if any(ref in by_id and text(by_id[ref]) for ref in refs):
            return True
        if (a.get('aria-label') or '').strip() or (a.get('title') or '').strip():
            return True
        if content and text(n):
            return True
        return False

    def record(rule, node, missing, reason):
        checked[rule] += 1
        if missing:
            sc, title, slug, fix = RULES[rule]
            findings.append({'rule_id': rule, 'severity': 'WARNING', 'kind': 'INFERRED',
                             'confidence': 'medium', 'message': reason, 'wcag': {'criterion': sc, 'title': title, 'level': 'A',
                             'reference': f'https://www.w3.org/WAI/WCAG22/Understanding/{slug}'},
                             'evidence': {'line': node['line'] if node else 1, 'column': node['column'] if node else 1,
                                          'html': node['html'] if node else None}, 'recommendation': fix})

    title = next((n for n in nodes if n['tag'] == 'title' and any(nodes[i]['tag'] == 'head' for i in ancestors(n, nodes))), None)
    root = next((n for n in nodes if n['tag'] == 'html'), None)
    record('page-title', title, title is None or not text(title), 'No nonempty title found in the document head.')
    record('html-lang', root, root is None or not (root['attrs'].get('lang') or '').strip(), 'No nonempty lang attribute found on html.')
    for n in nodes:
        if n['hidden']:
            continue
        tag, attrs = n['tag'], n['attrs']
        if tag == 'img':
            record('image-alternative', n, 'alt' not in attrs and not has_name(n) and attrs.get('role') not in {'none', 'presentation'}, 'Image has no detected text alternative or decorative role.')
        elif tag in {'input', 'select', 'textarea'}:
            kind = attrs.get('type', 'text').lower() if tag == 'input' else tag
            if kind == 'hidden':
                continue
            label = any(x['tag'] == 'label' and text(x) and attrs.get('id') and x['attrs'].get('for') == attrs['id'] for x in nodes)
            label = label or any(nodes[i]['tag'] == 'label' and text(nodes[i]) for i in ancestors(n, nodes))
            named = has_name(n) or label
            if kind in {'submit', 'reset'}:
                named = named or 'value' not in attrs or bool((attrs.get('value') or '').strip())
            elif kind == 'button':
                named = named or bool((attrs.get('value') or '').strip())
            elif kind == 'image':
                named = named or bool((attrs.get('alt') or '').strip())
            record('control-name', n, not named, 'Control has no detected associated label or accessible name; placeholder alone is insufficient.')
        elif tag in {'button', 'a', 'iframe'}:
            if tag == 'a' and 'href' not in attrs:
                continue
            named = has_name(n, content=tag in {'button', 'a'})
            # Image-only controls can have names supplied by descendants.
            if not named and tag in {'a', 'button'}:
                index = nodes.index(n)
                named = any(index in ancestors(child, nodes) and not child['hidden'] and
                            (child['attrs'].get('alt') or child['attrs'].get('aria-label') or child['tag'] == 'title' and text(child)) for child in nodes)
            rule = {'button': 'button-name', 'a': 'link-name', 'iframe': 'frame-name'}[tag]
            record(rule, n, not named, f'{tag} has no name detected by the static HTML checks.')
    return {'engine': 'companyscan-static-html', 'engine_version': '1.0', 'findings': findings,
            'checks': [{'rule_id': rule, 'elements_checked': count, 'status': 'WARNING' if any(f['rule_id'] == rule for f in findings) else 'PASS'} for rule, count in checked.items()]}


def ancestors(node, nodes):
    parent = node['parent']
    while parent is not None:
        yield parent
        parent = nodes[parent]['parent']


def summarize(pages, skipped=()):
    rows, findings, excluded = [], [], []
    for page in pages:
        reason = 'retrieval_error' if page.get('error') else 'truncated_response' if page.get('truncated') else 'duplicate_canonical' if page.get('duplicate_of') else 'no_accessibility_capture' if 'accessibility' not in page else None
        if reason:
            excluded.append({'url': page['url'], 'reason': reason})
            continue
        capture = page['accessibility']
        source = f"pages/{page['id']}.json"
        rows.append({'url': page['url'], 'artifact': source, 'retrieved_at': page['retrieved_at'], 'checks': capture['checks'], 'finding_count': len(capture['findings'])})
        findings.extend({**f, 'url': page['url'], 'artifact': source, 'retrieved_at': page['retrieved_at']} for f in capture['findings'])
    return {'schema_version': '1.0', 'target': 'WCAG 2.2 Level AA', 'standard_url': STANDARD,
            'engine': 'companyscan-static-html', 'engine_version': '1.0',
            'automated_status': 'UNKNOWN' if not rows else 'WARNING' if findings else 'PASS',
            'conformance_status': 'UNKNOWN', 'manual_review_required': True,
            'pages_checked': len(rows), 'pages_excluded': excluded, 'urls_skipped': list(skipped),
            'finding_count': len(findings), 'findings': findings, 'pages': rows,
            'manual_review': [{'area': name, 'criteria': criteria, 'status': 'UNKNOWN', 'instructions': instructions} for name, criteria, instructions in MANUAL],
            'limitations': LIMITATIONS}


def render_report(report):
    lines = ['# Accessibility review', '', f"Target: {report['target']}. Automated result: **{report['automated_status']}**.",
             '', '**WCAG conformance: UNKNOWN. Manual review required.**', '',
             f"Checked {report['pages_checked']} HTML pages; found {report['finding_count']} potential barriers. Excluded {len(report['pages_excluded'])} captured pages; {len(report['urls_skipped'])} URLs skipped.",
             '', 'PASS means no findings from this limited static check, not WCAG compliance.', '', '## Findings', '']
    for f in report['findings']:
        lines.extend([f"- **{f['rule_id']} — WCAG {f['wcag']['criterion']} ({f['severity']})**", f"  URL: {f['url']}",
                      f"  Evidence: {f['artifact']}, HTML line {f['evidence']['line']}, column {f['evidence']['column']}.",
                      f"  {f['message']} {f['recommendation']}", ''])
    if not report['findings']:
        lines.append('No findings recorded.' if report['pages_checked'] else 'No usable HTML was checked; no accessibility conclusion is available.')
    lines.extend(['', '## Manual review', ''])
    lines.extend(f"- **{item['area']} — UNKNOWN:** {item['instructions']}" for item in report['manual_review'])
    lines.extend(['', '## Limits', ''] + [f'- {item}' for item in report['limitations']])
    lines.extend(['', f"[WCAG 2.2]({STANDARD}) · [Conformance evaluation](https://www.w3.org/WAI/test-evaluate/conformance/)", ''])
    return '\n'.join(lines)
