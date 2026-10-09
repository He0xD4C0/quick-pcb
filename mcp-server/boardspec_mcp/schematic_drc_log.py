"""Decode EasyEDA's localized DRC log payloads without executing their HTML."""
from __future__ import annotations

import re
from html.parser import HTMLParser


class _Message(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.text = []
        self.params = {}
        self.objects = set()
        self.pages = set()

    def handle_starttag(self, tag, attrs):
        for key, value in attrs:
            if not value:
                continue
            if key.startswith('i18n-params-'):
                child = _Message()
                child.feed(value)
                self.params[key[len('i18n-params-'):].lower()] = child.render()
                self.objects.update(child.objects)
                self.pages.update(child.pages)
            elif key == 'data-log-find-id':
                self.objects.add(value)
            elif key == 'data-log-find-sheet':
                self.pages.add(value)

    def handle_data(self, value):
        self.text.append(value)

    def render(self):
        value = ''.join(self.text)
        return re.sub(r'\{([^{}]+)\}', lambda m: self.params.get(m[1].lower(), m[0]), value).strip()


def decode_drc_log(log):
    """Only accept errors emitted on the schematic DRC log channel."""
    if not isinstance(log, dict) or log.get('tabType') != 'schDrcLog':
        return None
    severity = log.get('type')
    if severity not in {'fatalError', 'error', 'warn', 'warning'}:
        return None
    values = log.get('msg', [])
    if not isinstance(values, list):
        values = [values]
    parsed = _Message()
    for value in values:
        if isinstance(value, str):
            parsed.feed(value)
        elif isinstance(value, dict) and isinstance(value.get('text'), str):
            parsed.feed(value['text'])
    message = parsed.render()
    if not message:
        return None
    return {'errorType': 'EDA_DRC_LOG', 'severity': severity, 'message': message,
            'objs': sorted(parsed.objects), 'pages': sorted(parsed.pages)}


def diagnostic_rows(raw):
    """Use captured details; retain any totals not accounted for by those details."""
    if raw is False or raw is None:
        return [{'errorType': 'EDA_DRC_RESULT_UNAVAILABLE',
                 'message': 'DRC did not return a successful check or usable diagnostics'}]
    if not isinstance(raw, dict) or raw.get('format') != 'easyeda-drc-capture/v1':
        return raw
    result = raw.get('result')
    logs = [row for item in raw.get('logs', []) if (row := decode_drc_log(item))]
    if isinstance(result, list) and all(isinstance(x, dict) and 'count' in x for x in result):
        totals = {x.get('type'): x.get('count') for x in result}
        output = list(logs)
        for severity, count in totals.items():
            if isinstance(count, (int, float)) and not isinstance(count, bool):
                missing = count - sum(row['severity'] == severity for row in logs)
                if missing > 0:
                    output.append({'type': severity, 'count': missing})
        return output
    # Newer versions supply native details; do not double count their log mirror.
    if isinstance(result, list):
        return result or logs
    if logs:
        return logs
    if result is True:
        return []
    return [{'errorType': 'EDA_DRC_RESULT_UNAVAILABLE',
             'message': 'DRC did not return a successful check or usable diagnostics'}]
