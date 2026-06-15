import json
import re
from datetime import datetime


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def lambda_handler(event, context):
    textract_response = event['textract_response']
    expense_id        = event['expense_id']
    bucket            = event['bucket']
    key               = event['key']
    user_id           = event.get('user_id', 'test-user')

    blocks    = textract_response.get('Blocks', [])
    full_text = extract_text_from_blocks(blocks)
    parsed    = parse_receipt_text(full_text, blocks)
    category  = auto_categorize(parsed)

    expense_record = {
        'user_id':      user_id,
        'expense_id':   expense_id,
        'original_key': key,
        'upload_date':  datetime.utcnow().isoformat(),
        'category':     category,
        'amount':       parsed.get('total', 0.0),
        'vendor':       parsed.get('vendor', 'Unknown'),
        'expense_date': parsed.get('date', ''),
        'raw_text':     full_text[:3500],
        'parse_meta':   parsed.get('meta', {}),   # debug info
        'status':       'processed',
    }

    return {'statusCode': 200, 'expense_record': expense_record}


# ---------------------------------------------------------------------------
# Text extraction
# ---------------------------------------------------------------------------

def extract_text_from_blocks(blocks):
    """Return every LINE block joined by newlines, preserving original case."""
    lines = [
        b.get('Text', '').strip()
        for b in blocks
        if b.get('BlockType') == 'LINE' and b.get('Text', '').strip()
    ]
    return '\n'.join(lines)


# ---------------------------------------------------------------------------
# Main parser
# ---------------------------------------------------------------------------

def parse_receipt_text(full_text: str, blocks: list = None) -> dict:
    lines  = full_text.split('\n')
    upper  = full_text.upper()          # used only for keyword matching
    u_lines = [l.upper() for l in lines]

    data = {
        'vendor': _detect_vendor(lines, u_lines),
        'total':  _detect_total(lines, u_lines, upper),
        'date':   _detect_date(lines),
        'meta':   {},
    }

    # Surface which strategy found the total (useful for debugging / improving)
    data['meta']['total_strategy'] = getattr(_detect_total, '_last_strategy', 'unknown')
    return data


# ---------------------------------------------------------------------------
# Vendor detection
# ---------------------------------------------------------------------------

# Well-known Indian vendors / chains — extend freely
_KNOWN_VENDORS = [
    'SWIGGY', 'ZOMATO', 'AMAZON', 'FLIPKART', 'MEESHO', 'MYNTRA',
    'RELIANCE', 'DMART', 'BIGBASKET', 'BLINKIT', 'ZEPTO', 'INSTAMART',
    'DOMINOS', 'PIZZA HUT', 'KFC', 'MCDONALDS', 'SUBWAY', 'BURGER KING',
    'STARBUCKS', 'CAFE COFFEE DAY', 'CHAAYOS',
    'IOCL', 'BPCL', 'HPCL', 'INDIAN OIL', 'HP GAS',
    'HDFC', 'ICICI', 'SBI', 'AXIS', 'KOTAK',
    'APOLLO', 'MEDPLUS', 'NETMEDS',
    'LIFESTYLE', 'PANTALOONS', 'WESTSIDE', 'ZARA', 'H&M',
]

# Generic receipt header words — a line containing only these is probably the vendor
_HEADER_KEYWORDS = {
    'STORE', 'RESTAURANT', 'HOTEL', 'SUPER', 'MARKET', 'BAZAAR',
    'PHARMACY', 'MEDICAL', 'CLINIC', 'PETROL', 'FUEL', 'BAKERY',
    'CAFE', 'COFFEE', 'FOODS', 'FRESH', 'MART', 'MALL',
}

# Lines that are definitely NOT the vendor name
_SKIP_PATTERNS = re.compile(
    r'(GST|GSTIN|TAX|INVOICE|RECEIPT|BILL|DATE|TIME|PHONE|ADDRESS|'
    r'THANK|WELCOME|VISIT|CUSTOMER|CASHIER|\d{6,})',
    re.IGNORECASE,
)


def _detect_vendor(lines: list, u_lines: list) -> str:
    # Pass 1 — exact match against known vendors
    for ul, line in zip(u_lines, lines):
        for vendor in _KNOWN_VENDORS:
            if vendor in ul:
                return line.strip()[:100]

    # Pass 2 — first non-trivial line in the header region (top 15 lines)
    for line in lines[:15]:
        clean = line.strip()
        if len(clean) < 3:
            continue
        if _SKIP_PATTERNS.search(clean):
            continue
        # Prefer lines that look like a name (mostly letters, length 4–60)
        if re.match(r'^[A-Za-z0-9 &\'.\-]{4,60}$', clean):
            return clean[:100]

    return 'Unknown'


# ---------------------------------------------------------------------------
# Total / amount detection
# ---------------------------------------------------------------------------

# Patterns applied to EACH LINE (not the whole blob) — line already uppercased
# Group 1 must capture the numeric amount string.
_TOTAL_LABEL_PATTERNS = [
    # Explicit grand / net total labels
    r'(?:GRAND\s+)?TOTAL\s*(?:AMT|AMOUNT)?\s*[:\-=]?\s*(?:RS\.?|INR|₹)?\s*([\d,]+\.?\d*)',
    r'NET\s+(?:TOTAL|AMOUNT|PAYABLE)\s*[:\-=]?\s*(?:RS\.?|INR|₹)?\s*([\d,]+\.?\d*)',
    r'(?:AMOUNT|AMT)\s+(?:DUE|PAID|PAYABLE)\s*[:\-=]?\s*(?:RS\.?|INR|₹)?\s*([\d,]+\.?\d*)',
    r'(?:BALANCE|BAL)\s+DUE\s*[:\-=]?\s*(?:RS\.?|INR|₹)?\s*([\d,]+\.?\d*)',
    r'YOU\s+(?:PAY|PAID)\s*[:\-=]?\s*(?:RS\.?|INR|₹)?\s*([\d,]+\.?\d*)',
    # Currency symbol followed by amount anywhere on the line
    r'(?:RS\.?|INR|₹)\s*([\d,]+\.?\d*)',
]

# Minimum credible receipt total (₹1) — filters out item counts, barcodes, etc.
_MIN_AMOUNT = 1.0
_MAX_AMOUNT = 9_99_999.0   # ₹9.99 lakh upper sanity cap


def _parse_amount(s: str) -> float:
    """Parse '1,234.50' or '1234' into float; return 0.0 on failure."""
    try:
        return float(s.replace(',', ''))
    except (ValueError, AttributeError):
        return 0.0


def _detect_total(lines: list, u_lines: list, upper_blob: str) -> float:
    """
    Strategy 1 – labeled line scan (high confidence, picks LAST / LARGEST match
                  so grand total wins over sub-totals).
    Strategy 2 – largest standalone currency amount in entire text.
    """
    _detect_total._last_strategy = 'none'

    candidates = []  # (amount, line_index, pattern_priority)

    for idx, (ul, line) in enumerate(zip(u_lines, lines)):
        combined = ul  # already upper

        for priority, pattern in enumerate(_TOTAL_LABEL_PATTERNS):
            m = re.search(pattern, combined)
            if m:
                amount = _parse_amount(m.group(1))
                if _MIN_AMOUNT <= amount <= _MAX_AMOUNT:
                    candidates.append((amount, idx, priority))
                break  # one pattern per line is enough

    if candidates:
        _detect_total._last_strategy = 'labeled_line'
        # Prefer lower-priority (more specific) patterns; break ties by taking
        # the LAST occurrence (grand total is usually printed after sub-totals).
        candidates.sort(key=lambda c: (c[2], c[1]))
        return candidates[0][0]   # highest-priority pattern, first match wins
        # If you want the largest value instead: return max(c[0] for c in candidates)

    # Strategy 2 — scan for all ₹/Rs amounts and return the largest
    fallback_amounts = []
    for m in re.finditer(
        r'(?:RS\.?|INR|₹)\s*([\d,]+\.?\d*)', upper_blob
    ):
        amount = _parse_amount(m.group(1))
        if _MIN_AMOUNT <= amount <= _MAX_AMOUNT:
            fallback_amounts.append(amount)

    if fallback_amounts:
        _detect_total._last_strategy = 'largest_currency_amount'
        return max(fallback_amounts)

    # Strategy 3 — largest standalone decimal number on the page
    all_numbers = [
        _parse_amount(m.group())
        for m in re.finditer(r'\b\d{1,6}(?:,\d{3})*\.\d{2}\b', upper_blob)
    ]
    plausible = [n for n in all_numbers if _MIN_AMOUNT <= n <= _MAX_AMOUNT]
    if plausible:
        _detect_total._last_strategy = 'largest_decimal_number'
        return max(plausible)

    return 0.0


# ---------------------------------------------------------------------------
# Date detection
# ---------------------------------------------------------------------------

_DATE_PATTERNS = [
    # ISO: 2024-07-15
    (r'\b(\d{4}[-/]\d{1,2}[-/]\d{1,2})\b', '%Y-%m-%d', '-'),
    # DD/MM/YYYY or DD-MM-YYYY
    (r'\b(\d{1,2}[/-]\d{1,2}[/-]\d{4})\b', '%d/%m/%Y', '/'),
    # DD/MM/YY
    (r'\b(\d{1,2}[/-]\d{1,2}[/-]\d{2})\b', '%d/%m/%y', '/'),
    # 15 Jul 2024 / 15-Jul-24
    (r'\b(\d{1,2}[\s\-](?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*[\s\-]\d{2,4})\b', None, None),
]


def _detect_date(lines: list) -> str:
    for line in lines:
        for pattern, fmt, sep in _DATE_PATTERNS:
            m = re.search(pattern, line, re.IGNORECASE)
            if m:
                raw = m.group(1)
                if fmt:
                    try:
                        normalized = raw.replace('-', sep).replace('/', sep)
                        dt = datetime.strptime(normalized, fmt)
                        return dt.strftime('%Y-%m-%d')
                    except ValueError:
                        pass
                return raw   # return as-is for natural-language dates
    return ''


# ---------------------------------------------------------------------------
# Auto-categorisation
# ---------------------------------------------------------------------------

_CATEGORY_RULES = [
    ('Food & Dining',     ['swiggy', 'zomato', 'restaurant', 'cafe', 'hotel', 'food',
                           'dominos', 'pizza', 'kfc', 'mcdonalds', 'subway', 'burger',
                           'starbucks', 'chaayos', 'bakery', 'dhaba', 'canteen']),
    ('Groceries',         ['reliance', 'dmart', 'bigbasket', 'blinkit', 'zepto',
                           'grocery', 'supermarket', 'vegetables', 'fresh', 'mart',
                           'provisions', 'kirana']),
    ('Online Shopping',   ['amazon', 'flipkart', 'meesho', 'myntra', 'snapdeal', 'nykaa']),
    ('Fuel & Transport',  ['petrol', 'fuel', 'iocl', 'bpcl', 'hpcl', 'indian oil',
                           'diesel', 'cng', 'auto', 'cab', 'ola', 'uber', 'rapido']),
    ('Health & Pharmacy', ['apollo', 'medplus', 'netmeds', '1mg', 'pharmacy',
                           'medical', 'clinic', 'hospital', 'diagnostic']),
    ('Utilities',         ['electricity', 'bescom', 'msedcl', 'tata power', 'gas',
                           'water', 'internet', 'broadband', 'airtel', 'jio', 'bsnl']),
    ('Fashion',           ['lifestyle', 'pantaloons', 'westside', 'zara', 'h&m',
                           'myntra', 'clothing', 'apparel', 'garments']),
]


def auto_categorize(parsed_data: dict) -> str:
    vendor = parsed_data.get('vendor', '').lower()
    for category, keywords in _CATEGORY_RULES:
        if any(kw in vendor for kw in keywords):
            return category
    return 'Miscellaneous'