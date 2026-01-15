from flask import Flask, render_template, request, redirect, url_for
from pathlib import Path
import csv
from datetime import datetime, timedelta

from src.calculator import simulate_selected_system, is_many_times_applicable
from src.xolair import get_xolair_dose, load_xolair_table_for_ui
from src.biologic_monthly import integrate_biologic_monthly, apply_monthly_subsidy_to_monthly_map
from src.biologic_schedule import build_prescription_schedule
import unicodedata

app = Flask(__name__)

# Jinja filter to format numbers as Japanese yen with comma separators
def _format_yen(val):
    try:
        v = int(val or 0)
    except Exception:
        try:
            v = int(float(val))
        except Exception:
            v = 0
    return f"¥{v:,.0f}"

app.jinja_env.filters['yen'] = _format_yen

DATA_DIR = Path(__file__).parent.parent / "data"
EXISTING_CSV = Path(__file__).parent / "static" / "existing_drugs.csv"


def load_drugs():
    drug_price_path = DATA_DIR / "drug_price.csv"
    rows = []
    if drug_price_path.exists():
        with drug_price_path.open(encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for r in reader:
                rows.append(r)
    return rows


def load_existing_drugs():
    rows = []
    if EXISTING_CSV.exists():
        with EXISTING_CSV.open(encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for r in reader:
                # ensure numeric
                try:
                    r['weekly_cost_yen'] = int(r.get('weekly_cost_yen') or 0)
                except Exception:
                    r['weekly_cost_yen'] = 0
                rows.append(r)
    return rows


def load_inhaled_drugs():
    """Load inhaled drug master and price CSVs and join by drug_id.

    Returns list of dicts: { drug_id, display_name, weekly_price }
    """
    # Prefer the MHLW-canonical exact master when available.
    exact_master_path = DATA_DIR / 'inhaled_drug_master_exact.csv'
    master_path = exact_master_path if exact_master_path.exists() else (DATA_DIR / 'inhaled_drug_master.csv')
    price_path = DATA_DIR / 'inhaled_drug_price_2025-04.csv'
    master = {}
    prices_by_id = {}
    prices_by_norm = {}
    rows = []

    def _normalize(s):
        if s is None:
            return ''
        t = str(s)
        t = unicodedata.normalize('NFKC', t)
        t = t.replace(' ', '').replace('\u3000', '')
        return t

    def parse_package_units(name):
        # normalize then look for digits before '吸入' or '吸入用'
        n = _normalize(name)
        import re
        m = re.search(r"(\d+)[^0-9\uFF10-\uFF19]*吸入", n)
        if m:
            try:
                return int(m.group(1))
            except Exception:
                return None
        # fallback: look for digits anywhere
        m2 = re.search(r"(\d+)", n)
        if m2:
            try:
                return int(m2.group(1))
            except Exception:
                return None
        return None

    if master_path.exists():
        try:
            # Load either the exact master (preferred) or the legacy master
            with master_path.open(encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for r in reader:
                    did = (r.get('drug_id') or r.get('id') or '').strip()
                    if not did:
                        did = _normalize(r.get('drug_name') or r.get('exact_item_name') or r.get('display_name') or '')
                    if not did:
                        continue
                    master[did] = r
        except Exception:
            master = {}
    else:
        # If preferred exact master is missing or failed, try legacy master as a fallback
        legacy_path = DATA_DIR / 'inhaled_drug_master.csv'
        if legacy_path.exists():
            try:
                with legacy_path.open(encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    for r in reader:
                        did = (r.get('drug_id') or r.get('id') or '').strip()
                        if not did:
                            did = _normalize(r.get('drug_name') or r.get('exact_item_name') or r.get('display_name') or '')
                        if not did:
                            continue
                        master[did] = r
            except Exception:
                master = {}

    if price_path.exists():
        try:
            with price_path.open(encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for r in reader:
                    did = (r.get('drug_id') or r.get('id') or '').strip()
                    # get unit/package price if present
                    unit_price = None
                    for key in ('unit_price_yen','unit_price','price_per_unit','薬価'):
                        if key in r and r.get(key) not in (None, ''):
                            try:
                                unit_price = float(str(r.get(key)).replace(',', '').strip())
                                break
                            except Exception:
                                unit_price = None
                    # store by id if available
                    if did:
                        prices_by_id[did] = {'unit_price': unit_price, 'row': r}
                    else:
                        # normalize name candidates
                        name_candidate = r.get('exact_item_name') or r.get('品名') or r.get('display_name') or r.get('drug_name') or ''
                        n = _normalize(name_candidate)
                        if n:
                            prices_by_norm[n] = {'unit_price': unit_price, 'row': r}
        except Exception:
            prices_by_id = {}
            prices_by_norm = {}

    # compose result list; compute weekly price from package unit price when possible
    for did, m in master.items():
        display = (m.get('display_name') or m.get('drug_name') or m.get('name') or did)
        unit_price = None
        # try id lookup
        if did in prices_by_id:
            unit_price = prices_by_id[did].get('unit_price')
        # try exact normalized name
        if unit_price is None:
            name_key = _normalize(m.get('exact_item_name') or m.get('drug_name') or m.get('display_name') or '')
            p = prices_by_norm.get(name_key)
            if p:
                unit_price = p.get('unit_price')
        # fallback: try contains-match on price names
        if unit_price is None:
            for nkey, pdata in prices_by_norm.items():
                if name_key and nkey.find(name_key) != -1:
                    unit_price = pdata.get('unit_price')
                    break
        # compute weekly price: use master.daily_inhalations *7 and package units parsed from name
        weekly_price = 0
        try:
            daily = int(m.get('daily_inhalations') or 0)
        except Exception:
            daily = 0
        units_per_week = daily * 7
        pkg_units = None
        # look for package units in master exact_item_name or in matched price row
        pkg_units = parse_package_units(m.get('exact_item_name') or m.get('drug_name') or '')
        if pkg_units is None and unit_price is not None:
            # try to get package size from any matched price row
            # (search prices_by_norm keys for one that contains name_key)
            for nkey in prices_by_norm.keys():
                if name_key and nkey.find(name_key) != -1:
                    pkg_units = parse_package_units(nkey)
                    if pkg_units:
                        break
        if unit_price is not None:
            # assume patient copay 30% when presenting weekly price in UI
            if pkg_units and units_per_week > 0:
                # unit_price is package price -> scale by units needed per week / package units
                weekly_price = int(round(unit_price * 0.3 * (units_per_week / float(pkg_units))))
            else:
                # package size unknown. Treat unit_price as per-unit price (price per inhalation/capsule)
                # and compute weekly = per_unit * daily * 7 * burden.
                if units_per_week > 0:
                    weekly_price = int(round(unit_price * 0.3 * units_per_week))
                else:
                    weekly_price = int(round(unit_price))
        else:
            weekly_price = 0

        # extract strength from master if available (various possible keys)
        strength = (m.get('strength_mg') or m.get('strength') or m.get('規格') or m.get('含量') or m.get('規格・含量') or '')
        if isinstance(strength, float) or isinstance(strength, int):
            strength = str(strength)
        rows.append({'drug_id': did, 'display_name': display, 'weekly_price': weekly_price, 'class': m.get('class'), 'strength': strength})

    # include any price-only entries (by normalized name)
    for nkey, pdata in prices_by_norm.items():
        # only include if not already present
        if not any(r['drug_id'] == nkey for r in rows):
            try:
                w = int(round(pdata.get('unit_price') or 0))
            except Exception:
                w = 0
            rows.append({'drug_id': nkey, 'display_name': nkey, 'weekly_price': w, 'class': '', 'strength': ''})

    rows.sort(key=lambda x: x.get('display_name') or x.get('drug_id'))
    # Deduplicate by drug_id to avoid rendering duplicate checkboxes
    seen = set()
    deduped = []
    for r in rows:
        did = r.get('drug_id')
        if did in seen:
            continue
        seen.add(did)
        deduped.append(r)
    return deduped


def sort_controllers(controllers):
    """Sort controllers into two groups and return concatenated list.

    Group 1: items whose `class` contains 'TRIPLE' (ICS/LABA/LAMA)
    Group 2: the remaining controllers (ICS/LABA, LAMA を含まない)

    Within each group, sort by:
      1) normalized display name (五十音)
      2) numeric strength (降順)

    Does not modify the input dicts.
    """
    import re

    def _normalize(s):
        if s is None:
            return ''
        t = str(s)
        t = unicodedata.normalize('NFKC', t)
        t = t.replace(' ', '').replace('\u3000', '')
        # katakana -> hiragana for natural 五十音 order
        def kata2hira(txt):
            out = []
            for ch in txt:
                code = ord(ch)
                if 0x30A1 <= code <= 0x30F6:
                    out.append(chr(code - 0x60))
                else:
                    out.append(ch)
            return ''.join(out)
        t = kata2hira(t)
        # remove common punctuation
        t = re.sub(r'[\-–−()（）\[\]\u3000,.：:・]', '', t)
        return t

    def _extract_strength_from_field(val):
        if not val:
            return 0
        m = re.search(r"(\d+)", str(val))
        if m:
            try:
                return int(m.group(1))
            except Exception:
                return 0
        return 0

    def _strength(d):
        # prefer explicit strength field, fallback to digits in display_name
        s = d.get('strength')
        v = _extract_strength_from_field(s)
        if v:
            return v
        return _extract_strength_from_field(d.get('display_name') or d.get('drug_id') or '')

    def _base_name(d):
        # normalized display name with numeric tokens removed
        n = _normalize(d.get('display_name') or d.get('drug_id') or '')
        # remove digits that represent strength to get base name
        n = re.sub(r"\d+", '', n)
        # remove common tokens that don't affect name ordering
        n = re.sub(r'吸入|エアゾール|エアゾ', '', n)
        return n.strip()

    if not controllers:
        return []

    # Use explicit `d['group']` set on controllers to partition. Do not auto-detect.
    groups_order = ['TRIPLE', 'ICS_LABA', 'ICS', 'LAMA', 'OTHER']

    def _sort_key(d):
        return (_base_name(d), -_strength(d), _normalize(d.get('display_name') or d.get('drug_id') or ''))

    out = []
    for g in groups_order:
        members = [d for d in controllers if (d.get('group') or 'OTHER') == g]
        out.extend(sorted(members, key=_sort_key))
    # include any controllers with unexpected group values at the end
    remaining = [d for d in controllers if (d.get('group') or 'OTHER') not in groups_order]
    if remaining:
        out.extend(sorted(remaining, key=_sort_key))
    return out


def _parse_inhaled_spec(display_name: str):
    """Extract numeric strength, dosage level, and inhalation count from display_name.

    Returns (numeric_strength:int, dosage_rank:int, inhalation_count:int).
    Higher values mean stronger/larger and will be used with reverse=True sorting.
    """
    import re
    import unicodedata

    s = (display_name or '')
    t = unicodedata.normalize('NFKC', s).replace(' ', '').replace('\u3000', '')

    # numeric strength: prefer numbers that look like mg or standalone specs
    nums = [int(m.group(1) or 0) for m in re.finditer(r"(\d+)(?=\s*(?:mg|ｍｇ|MG|MG|mg)? )|(?<!\d)(\d+)(?!\d)", t)] if t else []
    # fallback: any digits anywhere
    if not nums:
        nums = [int(m.group(1) or 0) for m in re.finditer(r"(\d+)", t)] if t else []
    num_strength = max(nums) if nums else 0

    # dosage rank: 高用量 > 中用量 > 低用量
    if '高用量' in t or '高用' in t:
        dose = 3
    elif '中用量' in t or '中用' in t:
        dose = 2
    elif '低用量' in t or '低用' in t:
        dose = 1
    else:
        dose = 0

    # inhalation count: look for patterns like '1日8吸入' or '8吸入' or '1日8回'
    inh = 0
    m = re.search(r"1日\s*(\d+)\s*(?:吸入|回)", t)
    if not m:
        m = re.search(r"(\d+)\s*(?:吸入|回)", t)
    if m:
        try:
            inh = int(m.group(1))
        except Exception:
            inh = 0

    return (num_strength, dose, inh)


def inhaled_sort_key(d):
    """Return a tuple key for sorting inhaled drugs by drug-specific rules.

    Uses INHALED_DRUG_MASTER and get_drug_base_name to determine ordering mode.
    """
    # Accept either a dict item or a display_name string
    if isinstance(d, dict):
        disp = d.get('display_name') or d.get('drug_id') or ''
    else:
        disp = d or ''

    base = get_base_drug(disp)

    # 薬剤の五十音順キー
    base_key = base

    # 規格順位リスト
    order = INHALED_ORDER.get(base, [])

    rank = 999
    for i, token in enumerate(order):
        if token in disp:
            rank = i
            break

    return (base_key, rank)


# Inhaled drug master: maps base token -> group and ordering mode
INHALED_DRUG_MASTER = {
    "アドエアディスカス": {"group": "ICS_LABA", "order": "strength"},
    "アドエアエアゾール": {"group": "ICS_LABA", "order": "strength"},
    "レルベア": {"group": "ICS_LABA", "order": "strength"},
    "アテキュラ": {"group": "ICS_LABA", "order": "strength"},
    "テリルジー": {"group": "TRIPLE", "order": "strength"},
    "エナジア": {"group": "TRIPLE", "order": "strength"},
    "フルティフォーム": {"group": "ICS_LABA", "order": "dose"},
    "ブデホル": {"group": "ICS_LABA", "order": "dose"},
    "スピリーバ": {"group": "LAMA", "order": "none"},
}


def get_drug_base_name(display_name):
    name = display_name or ""
    # match by substring; keys in INHALED_DRUG_MASTER should be specific enough
    for key in INHALED_DRUG_MASTER:
        if key in name:
            return key
    return None


# Order master for display ordering (drug base -> list of tokens in preferred order)
INHALED_ORDER = {
    "アドエアディスカス": ["500", "250"],
    "アドエアエアゾール": ["250", "125"],
    "エナジア": ["高", "中"],
    "アテキュラ": ["高", "中", "低"],
    "テリルジー": ["200", "100"],
    "フルティフォーム125": ["8", "6", "4"],
    "フルティフォーム50": ["4"],
    "ブデホル": ["8", "6", "4"],
    "レルベア": ["200", "100"],
}


def get_base_drug(display_name):
    name = display_name or ""
    for k in INHALED_ORDER.keys():
        if k in name:
            return k
    return display_name



def load_oral_drugs():
    """Load oral drug price CSV and return list of {drug_id, display_name, weekly_price}.

    Expects `data/oral_drug_price_2025-04.csv` with columns including `drug_id` or `exact_item_name` and `weekly_price` or `unit_price`.
    """
    # Prefer a weekly price CSV if present (generated by scripts), else use the raw price CSV
    path = DATA_DIR / 'oral_drug_weekly_price_2025-04.csv'
    if not path.exists():
        path = DATA_DIR / 'oral_drug_price_2025-04.csv'
    rows = []
    if not path.exists():
        return rows
    # pre-load the more complete oral price CSV (if present) to support name-based lookup
    price_rows = []
    price_path = DATA_DIR / 'oral_drug_price_2025-04.csv'
    def _norm_name(s):
        if s is None:
            return ''
        t = str(s)
        import unicodedata
        t = unicodedata.normalize('NFKC', t)
        t = t.replace(' ', '').replace('\u3000','')
        return t

    if price_path.exists():
        try:
            with price_path.open(encoding='utf-8') as pf:
                preader = csv.DictReader(pf)
                for pr in preader:
                    price_rows.append(pr)
        except Exception:
            price_rows = []

    with path.open(encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for r in reader:
                # prefer explicit id fields, else use drug_name/品名/exact_item_name
                base_name = (r.get('drug_id') or r.get('id') or '').strip()
                if not base_name:
                    base_name = (r.get('drug_name') or r.get('exact_item_name') or r.get('品名') or r.get('display_name') or '').strip()

                # extract strength if present (prefer dedicated field)
                strength = (r.get('strength_mg') or r.get('strength') or r.get('規格') or r.get('含量') or r.get('規格・含量') or '')
                if isinstance(strength, float) or isinstance(strength, int):
                    strength = str(strength)
                if not strength:
                    try:
                        import re
                        name_src = (r.get('exact_item_name') or r.get('display_name') or r.get('drug_name') or '')
                        m = re.search(r"(\d+(?:\.\d+)?)\s*(mg|ｍｇ|MG|ug|μg|mcg|g|錠)\b", name_src, flags=re.I)
                        if m:
                            val = m.group(1)
                            strength = val
                    except Exception:
                        pass




                # compute weekly price: prefer provided weekly fields, else try price CSV lookup by name
                weekly = None
                for key in ('weekly_price','weekly_price_float','weekly_price_display','weekly','daily_price','unit_price_yen','unit_price','weekly_price_yen','price_yen'):
                    if key in r and r.get(key) not in (None, ''):
                        try:
                            weekly = float(str(r.get(key)).replace(',','').strip())
                            break
                        except Exception:
                            weekly = None
                if weekly is None or weekly == 0:
                    # try to find a matching price row in the fuller price CSV by normalized name
                    nbase = _norm_name(base_name)
                    found = None
                    for pr in price_rows:
                        pname = _norm_name(pr.get('drug_name') or pr.get('matched_price_name') or pr.get('display_name') or '')
                        if not pname:
                            continue
                        if nbase and pname.find(nbase) != -1:
                            found = pr
                            break
                    if found:
                        try:
                            weekly = float(str(found.get('weekly_price_float') or found.get('weekly_price') or found.get('weekly_price_display') or found.get('weekly') or found.get('weekly_price_yen') or found.get('daily_price') or 0).replace(',','').strip())
                        except Exception:
                            weekly = 0
                if weekly is None:
                    weekly = 0

                display = (r.get('display_name') or r.get('drug_name') or r.get('exact_item_name') or r.get('品名') or base_name)
                # form a unique drug_id that includes strength when available to avoid collapsing different specs
                did = base_name
                if strength:
                    did = f"{base_name}|{strength}"

                rows.append({'drug_id': did, 'display_name': display, 'weekly_price': int(round(weekly)), 'strength': strength})
    
    rows.sort(key=lambda x: (x.get('display_name') or x.get('drug_id'), x.get('strength') or ''))
    # Deduplicate by the generated drug_id (includes strength when available)
    seen = set()
    deduped = []
    for r in rows:
        did = r.get('drug_id')
        if did in seen:
            continue
        seen.add(did)
        deduped.append(r)
    return deduped


def determine_controller_group(display_name):
    # master-based classification (see INHALED_DRUG_MASTER)
    base = get_drug_base_name(display_name)
    if base and base in INHALED_DRUG_MASTER:
        return INHALED_DRUG_MASTER[base]['group']
    return 'OTHER'


def build_income_map():
    """Return a mapping of system_version -> list of (income_code, income_label).

    Uses `data/limit_table.csv` and collects rows grouped by age_group ('under70' and 'over70').
    """
    path = DATA_DIR / 'limit_table.csv'
    mapping = {}
    try:
        with path.open(encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                sv = (row.get('system_version') or '').strip()
                ag = (row.get('age_group') or '').strip()
                code = (row.get('income_code') or '').strip()
                label = (row.get('income_label') or '').strip()
                if not sv or not code:
                    continue
                # group by age_group to support selecting age first in UI
                mapping.setdefault(sv, {})
                mapping[sv].setdefault(ag, [])
                # avoid duplicates within the age_group
                if not any(code == ex[0] for ex in mapping[sv][ag]):
                    mapping[sv][ag].append((code, label))
    except Exception:
        # fallback: minimal defaults with empty age groups
        mapping = { 'R7': {'under70': [], 'over70': []}, 'R8': {'under70': [], 'over70': []}, 'R9': {'under70': [], 'over70': []} }
    # ensure keys for R7/R8/R9 exist
    for k in ('R7', 'R8', 'R9'):
        mapping.setdefault(k, {})
        mapping[k].setdefault('under70', [])
        mapping[k].setdefault('over70', [])

    # Post-process: if a given system+age_group contains single-letter codes (A/I/U/E/O),
    # prefer those and remove numeric 1..7 variants that may appear in the same file.
    import re
    single_letter_re = re.compile(r'^[A-Z]$')
    for sv, agmap in mapping.items():
        for ag, lst in agmap.items():
            # Only prefer single-letter codes for the 'under70' age group.
            # Do not modify the 'over70' list so LI1/LI2 (and other multi-letter
            # codes) remain available in the UI.
                if ag == 'under70' and any(single_letter_re.match(code) for code, _ in lst):
                    mapping[sv][ag] = [(c, l) for (c, l) in lst if single_letter_re.match(c)]
                # Retain original list for 'over70' age group
                elif ag == 'over70':
                    mapping[sv][ag] = lst
    return mapping


@app.route('/', methods=['GET'])
def index():
    drugs = load_drugs()
    existing_drugs = load_existing_drugs()

    inhaled_drugs = load_inhaled_drugs()
    # split into controllers (non-LAMA) and lamas
    controllers = [d for d in inhaled_drugs if (d.get('class') or '').upper() != 'LAMA']
    # set explicit group on each controller based on display_name and preserve original order
    for idx, d in enumerate(controllers):
        d['_orig_order'] = idx
        d['group'] = determine_controller_group(d.get('display_name') or d.get('drug_id'))
    lamas = [d for d in inhaled_drugs if (d.get('class') or '').upper() == 'LAMA']
    oral_drugs = load_oral_drugs()
    xolair_table = load_xolair_table_for_ui()
    # detect whether any xolair_* rows exist in the data and pass flag to template
    try:
        has_xolair = any((d.get('drug_id') or '').startswith('xolair_') for d in drugs)
    except Exception:
        has_xolair = False
    # Ensure controllers are consistently sorted server-side before rendering
    controllers = sort_controllers(controllers)
    controllers = sorted(controllers, key=inhaled_sort_key)
    lamas = sorted(lamas, key=inhaled_sort_key)
    return render_template('index.html', drugs=drugs, existing_drugs=existing_drugs,
                           controllers=controllers, lamas=lamas, oral_drugs=oral_drugs,
                           system_versions=['R7','R8','R9'], income_map=build_income_map(), selected_system='R9', selected_age_group='under70', selected_income_category='',
                           include_existing=True, selected_oral_ids=[], xolair_table=xolair_table, has_xolair=has_xolair)

@app.route('/calculate', methods=['POST'])
def calculate():
    form = request.form
    # selected system version for UI (R7/R8/R9)
    selected_system = form.get('system_version') or 'R9'
    # selected age group (under70/over70)
    age_group = form.get('age_group') or 'under70'
    # Basic biologic inputs (UI simplified)
    start_date = form.get('start_date') or ''
    drug_id = form.get('drug_id')
    # Read qty2/qty3; allow empty and apply drug-specific safe defaults later
    qty2_raw = form.get('qty2')
    qty3_raw = form.get('qty3')
    # income_category may be submitted as 'CODE|Label' for display; parse into code and display
    raw_income = form.get('income_category') or form.get('income') or ''
    income_category = raw_income
    income_display = ''
    if raw_income:
        try:
            if '|' in raw_income:
                income_code, income_display = raw_income.split('|', 1)
                income_category = income_code
            else:
                income_display = raw_income
                income_category = raw_income
        except Exception:
            income_display = raw_income
            income_category = raw_income
    prescription_interval_weeks = int(form.get('prescription_interval_weeks') or 12)

    # Optional override for biologic display name (used for Xolair computed dosing)
    forced_selected_biologic_name = None

    # Include existing treatments by default (UI no longer exposes a toggle)
    include_existing = True

    # parse copay / burden ratio and convert to percent for display
    try:
        copay_raw = float(form.get('burden_ratio') or form.get('copay_rate') or 0)
    except Exception:
        try:
            copay_raw = float(str(form.get('burden_ratio') or form.get('copay_rate') or 0).replace(',',''))
        except Exception:
            copay_raw = 0.0
    copay_rate_percent = int(round(copay_raw * 100))

    existing_weekly_cost_yen = 0
    existing_dispense_weeks = 12
    existing_drug_name = ''

    # existing drugs selection vs manual
    if include_existing:
        existing_mode = form.get('existing_mode')
        if existing_mode == 'csv':
            # support multiple inhaled selections: primary_drug_ids (list) and optional lama_drug_id
            primary_ids = form.getlist('primary_drug_ids') if hasattr(form, 'getlist') else ([] if not form.get('primary_drug_id') else [form.get('primary_drug_id')])
            lama_id = form.get('lama_drug_id')
            inhaled = load_inhaled_drugs()
            oral_list = load_oral_drugs()
            # sum any selected oral drugs' weekly prices
            oral_selected = form.getlist('oral_drug_ids') if hasattr(form, 'getlist') else []
            # ensure uniqueness (preserve order) to avoid duplicate counting if browser sent repeats
            try:
                seen_o = set()
                uniq_oral = []
                for oid in oral_selected:
                    if oid in seen_o:
                        continue
                    seen_o.add(oid)
                    uniq_oral.append(oid)
                oral_selected = uniq_oral
            except Exception:
                pass
            try:
                oral_sum = sum(int(next((o.get('weekly_price') for o in oral_list if o.get('drug_id') == oid), 0)) for oid in oral_selected)
            except Exception:
                oral_sum = 0
            # add oral sum to existing weekly cost
            existing_weekly_cost_yen = int(existing_weekly_cost_yen or 0) + int(oral_sum or 0)
            names = []
            # primary (allow multiple selected inhaled controllers)
            if primary_ids:
                for pid in primary_ids:
                    if not pid:
                        continue
                    sel_primary = next((d for d in inhaled if d.get('drug_id') == pid), None)
                    if sel_primary:
                        try:
                            existing_weekly_cost_yen += int(sel_primary.get('weekly_price') or 0)
                        except Exception:
                            pass
                        nm = sel_primary.get('display_name') or ''
                        if sel_primary.get('strength'):
                            try:
                                if nm:
                                    nm = nm + ' ' + str(sel_primary.get('strength'))
                                else:
                                    nm = str(sel_primary.get('strength'))
                            except Exception:
                                pass
                        names.append(nm)
                    else:
                        # fallback to legacy existing_drugs CSV if id not found in inhaled list
                        sel = next((d for d in load_existing_drugs() if d.get('drug_id') == pid), None)
                        if sel:
                            try:
                                existing_weekly_cost_yen += int(sel.get('weekly_cost_yen') or 0)
                            except Exception:
                                pass
                            names.append(sel.get('drug_name') or '')
            # lama (optional)
            if lama_id:
                sel_lama = next((d for d in inhaled if d.get('drug_id') == lama_id), None)
                if sel_lama:
                    try:
                        existing_weekly_cost_yen += int(sel_lama.get('weekly_price') or 0)
                    except Exception:
                        pass
                    nm2 = sel_lama.get('display_name') or ''
                    if sel_lama.get('strength'):
                        try:
                            nm2 = nm2 + ' ' + str(sel_lama.get('strength'))
                        except Exception:
                            pass
                    names.append(nm2)
                else:
                    sel2 = next((d for d in load_existing_drugs() if d.get('drug_id') == lama_id), None)
                    if sel2:
                        try:
                            existing_weekly_cost_yen += int(sel2.get('weekly_cost_yen') or 0)
                        except Exception:
                            pass
                        names.append(sel2.get('drug_name') or '')
            # backwards compatibility: single-field `existing_drug_id` or new multi `existing_drug_ids`
            if not names:
                selected_ids = form.getlist('existing_drug_ids') if hasattr(form, 'getlist') else ([] if not form.get('existing_drug_id') else [form.get('existing_drug_id')])
                if selected_ids:
                    for selected_id in selected_ids:
                        if not selected_id:
                            continue
                        sel_inh = next((d for d in inhaled if d.get('drug_id') == selected_id), None)
                        if sel_inh:
                            try:
                                existing_weekly_cost_yen += int(sel_inh.get('weekly_price') or 0)
                            except Exception:
                                pass
                            names.append(sel_inh.get('display_name') or '')
                        else:
                            sel = next((d for d in load_existing_drugs() if d.get('drug_id') == selected_id), None)
                            if sel:
                                try:
                                    existing_weekly_cost_yen += int(sel.get('weekly_cost_yen') or 0)
                                except Exception:
                                    pass
                                names.append(sel.get('drug_name') or '')

            # append oral drug names to existing_drug_name display
            oral_names = []
            for oid in oral_selected:
                ol = next((o for o in oral_list if o.get('drug_id') == oid), None)
                if ol:
                    oral_names.append(ol.get('display_name') or '')
            if oral_names:
                names.extend(oral_names)
            existing_drug_name = ' + '.join([n for n in names if n])
            # If Fasenra is present in the selected existing treatments, it is dosed every 8 weeks
            # and should be aggregated as an 8-week existing treatment rather than 12-week.
            try:
                nd = (existing_drug_name or '').lower()
                if 'fasenra' in nd or 'ファセンラ' in existing_drug_name:
                    existing_dispense_weeks = 8
            except Exception:
                pass
        else:
            # manual
            try:
                existing_weekly_cost_yen = int(form.get('existing_weekly_cost_yen') or 0)
            except Exception:
                existing_weekly_cost_yen = 0

    # Call backend calculation
    # Validate incompatible selection: Triple + LAMA is not allowed
    if include_existing and form.get('existing_mode') == 'csv':
        primary_ids_check = form.getlist('primary_drug_ids') if hasattr(form, 'getlist') else ([] if not form.get('primary_drug_id') else [form.get('primary_drug_id')])
        lama_id_check = form.get('lama_drug_id')
        # if any selected primary is Triple and a LAMA is also selected -> invalid
        if primary_ids_check and lama_id_check:
            inhaled_check = load_inhaled_drugs()
            any_triple = False
            for pid in primary_ids_check:
                sp = next((d for d in inhaled_check if d.get('drug_id') == pid), None)
                if sp and (sp.get('class') or '').lower() == 'triple':
                    any_triple = True
                    break
            if any_triple:
                # render index with an error message
                drugs = load_drugs()
                existing_drugs = load_existing_drugs()
                inhaled_all = load_inhaled_drugs()
                controllers = [d for d in inhaled_all if (d.get('class') or '').upper() != 'LAMA']
                for idx, d in enumerate(controllers):
                    d['_orig_order'] = idx
                    d['group'] = determine_controller_group(d.get('display_name') or d.get('drug_id'))
                lamas = [d for d in inhaled_all if (d.get('class') or '').upper() == 'LAMA']
                controllers = sort_controllers(controllers)
                controllers = sorted(controllers, key=inhaled_sort_key)
                lamas = sorted(lamas, key=inhaled_sort_key)
                return render_template('index.html', drugs=drugs, existing_drugs=existing_drugs,
                                       controllers=controllers, lamas=lamas,
                                       system_versions=['R7','R8','R9'], income_map=build_income_map(), selected_system=selected_system, selected_age_group=age_group,
                                       results=None, error_message='Triple と LAMA の併用はできません。主薬または LAMA を変更してください。',
                                       selected_oral_ids=[])
    # Special handling for Xolair: require IgE and weight and determine dose/schedule
    if drug_id and (str(drug_id).lower() == 'xolair' or 'xolair' in str(drug_id).lower()):
        ige_raw = form.get('xolair_ige') or form.get('ige')
        weight_raw = form.get('xolair_weight') or form.get('weight')
        dose_info = get_xolair_dose(ige_raw, weight_raw)
        if dose_info is None:
            # No recommended dose for provided inputs; re-render index with error
            drugs = load_drugs()
            existing_drugs = load_existing_drugs()
            inhaled_all = load_inhaled_drugs()
            controllers = [d for d in inhaled_all if (d.get('class') or '').upper() != 'LAMA']
            for idx, d in enumerate(controllers):
                d['_orig_order'] = idx
                d['group'] = determine_controller_group(d.get('display_name') or d.get('drug_id'))
            lamas = [d for d in inhaled_all if (d.get('class') or '').upper() == 'LAMA']
            controllers = sort_controllers(controllers)
            controllers = sorted(controllers, key=inhaled_sort_key)
            lamas = sorted(lamas, key=inhaled_sort_key)
            return render_template('index.html', drugs=drugs, existing_drugs=existing_drugs,
                                   controllers=controllers, lamas=lamas, oral_drugs=load_oral_drugs(),
                                   system_versions=['R7','R8','R9'], income_map=build_income_map(), selected_system=selected_system, selected_age_group=age_group,
                                   results=None, error_message='Xolair: No recommended dose for provided IgE/weight combination.',
                                   selected_oral_ids=[], xolair_table=load_xolair_table_for_ui())
        else:
            dose_mg, interval_weeks = dose_info
            forced_selected_biologic_name = f"Xolair: {dose_mg} mg every {interval_weeks} weeks"
    try:
        # If Xolair dose was determined above, pass it through so the
        # calculator can compute per-event cost via pen mapping.
        res = simulate_selected_system(
            system_version=selected_system,
            income_code=income_category,
            age_group=age_group,
            drug_id=drug_id,
            prescription_interval_weeks=prescription_interval_weeks,
            existing_weekly_cost_yen=existing_weekly_cost_yen,
            existing_dispense_weeks=existing_dispense_weeks,
            include_existing=include_existing,
            xolair_dose_info=dose_info if 'dose_info' in locals() else None,
        )
        try:
            import json as _json
            print('SIM_RES type=', type(res), ' keys=', list(res.keys()) if isinstance(res, dict) else None)
        except Exception:
            pass
    except Exception:
        # If backend calculation fails (e.g. missing lookup data),
        # fall back to a safe result shape that matches what the
        # template/view code expects. When `include_existing` is True
        # callers expect `biologic_only` and `biologic_plus_existing` keys.
        empty_event = {
            'event': 1,
            'applied': 0,
            'applied_limit': 0,
            'is_many_times': False,
        }
        base = {
            'events': [empty_event],
            'annual_cost': 0,
            'monthly_average_cost': 0,
            'is_many_times_applied': False,
        }
        if include_existing:
            res = {
                'biologic_only': dict(base),
                'biologic_plus_existing': dict(base),
                'events': base['events'],
                'annual_cost': 0,
            }
        else:
            res = base

    # Determine biologic raw per event (self_pay) from data/drug_price.csv
    biologic_raw_per_event = None
    drug_rows = load_drugs()
    sel_drug = next((d for d in drug_rows if d.get('drug_id') == drug_id), None)
    if sel_drug:
        try:
            price_per_unit = int(sel_drug.get('price_per_unit') or 0)
            units_per_12w = int(sel_drug.get('units_per_12w') or 0)
            biologic_raw_per_event = price_per_unit * units_per_12w * 0.3
        except Exception:
            biologic_raw_per_event = None

    # Build monthly table by mapping events to months using start_date
    events = res.get('events') or []
    # If include_existing, the top-level res is combined; if not, res is biologic_only
    biologic_only = res.get('biologic_only') if include_existing else res
    biologic_plus_existing = res.get('biologic_plus_existing') if include_existing else None

    # Compute dates for each event starting at start_date
    # ensure datetime utilities are available in this scope
    try:
        from datetime import datetime, timedelta
    except Exception:
        import datetime as _dt
        datetime = _dt.datetime
        timedelta = _dt.timedelta
    event_dates = []
    try:
        if start_date:
            sd = datetime.strptime(start_date, '%Y-%m-%d')
        else:
            sd = datetime.today()
    except Exception:
        sd = datetime.today()

    # Determine safe defaults per drug when inputs are missing
    def _default_qty_for(drug_key: str, which: int) -> int:
        k = (drug_key or '').lower()
        # which==2 or 3
        if 'dupixent' in k or 'デュピクセント' in k:
            return 1
        if 'nucala' in k or 'ヌーカラ' in k:
            return 3
        if 'teze' in k or 'tezespia' in k or 'tezspire' in k or 'テゼスパイア' in k:
            return 3
        if 'fasenra' in k or 'ファセンラ' in k:
            return 1
        return 1

    # coerce values or apply defaults
    try:
        qty2 = int(qty2_raw) if qty2_raw and qty2_raw.strip() != '' else _default_qty_for(drug_id, 2)
    except Exception:
        qty2 = _default_qty_for(drug_id, 2)
    try:
        qty3 = int(qty3_raw) if qty3_raw and qty3_raw.strip() != '' else _default_qty_for(drug_id, 3)
    except Exception:
        qty3 = _default_qty_for(drug_id, 3)

    # Prefer schedule computed from prescription quantities when possible
    event_dates = []
    biologic_schedule = None
    try:
        # build a 2-year horizon by default so rolling 13-24か月を集計可能にする
        end_date = (sd + timedelta(days=365 * 2)).date()
        # use drug_id or drug name to build schedule
        build_key = drug_id or ''
        presc = build_prescription_schedule(build_key, sd.date(), qty2, qty3, end_date)
        biologic_schedule = presc
        for pe in presc:
            # convert date to datetime for compatibility
            d = pe['date']
            event_dates.append(datetime.combine(d, datetime.min.time()))
    except Exception:
        # If build_prescription_schedule isn't applicable (e.g. unified 'xolair' key),
        # attempt a minimal fallback: for Xolair, use dose_info (interval_weeks)
        # to construct a schedule; otherwise fall back to interval-based generation
        try:
            if drug_id and 'xolair' in str(drug_id).lower() and ('dose_info' in locals() and dose_info):
                # dose_info is a tuple (dose_mg, interval_weeks)
                d_mg, interval_weeks_local = dose_info
                try:
                    interval_weeks_local = int(interval_weeks_local)
                except Exception:
                    interval_weeks_local = None
                # If dose_info provides an interval, use it as base_weeks; otherwise default 4 weeks.
                base_weeks = (interval_weeks_local if interval_weeks_local and interval_weeks_local > 0 else 4)

                # Build schedule where the first 3 administrations occur each
                # `base_weeks` apart (order1, order2, order3). Their qty values are
                # [1, qty2, qty3] respectively. After order3, maintenance events
                # repeat every (qty3 * base_weeks) weeks with qty=qty3.
                presc = []
                order = 1
                cur = sd.date()

                # Order 1
                if cur <= end_date:
                    try:
                        ev_days = int(1 * base_weeks * 7)
                    except Exception:
                        ev_days = int(base_weeks * 7)
                    presc.append({'order': order, 'date': cur, 'qty': 1, 'days': ev_days})
                    event_dates.append(datetime.combine(cur, datetime.min.time()))
                    order += 1

                # Order 2 (base_weeks after order1)
                next_date = cur + timedelta(weeks=base_weeks)
                if next_date <= end_date:
                    try:
                        ev_days = int(int(qty2) * base_weeks * 7)
                    except Exception:
                        ev_days = int(base_weeks * 7)
                    presc.append({'order': order, 'date': next_date, 'qty': int(qty2), 'days': ev_days})
                    event_dates.append(datetime.combine(next_date, datetime.min.time()))
                    order += 1
                    cur = next_date

                # Order 3 (base_weeks after order2)
                third_date = cur + timedelta(weeks=base_weeks)
                if third_date <= end_date:
                    try:
                        ev_days = int(int(qty3) * base_weeks * 7)
                    except Exception:
                        ev_days = int(base_weeks * 7)
                    presc.append({'order': order, 'date': third_date, 'qty': int(qty3), 'days': ev_days})
                    event_dates.append(datetime.combine(third_date, datetime.min.time()))
                    order += 1
                    cur = third_date

                # Maintenance: for Xolair, after the initial 3 doses, schedule
                # maintenance administrations every 12 weeks (like other biologics).
                maint_step_weeks = 12
                # number of administrations within a maintenance interval
                try:
                    num_admins = int(maint_step_weeks) // int(base_weeks) if base_weeks and int(base_weeks) > 0 else 1
                except Exception:
                    num_admins = 1
                while True:
                    cur = cur + timedelta(weeks=maint_step_weeks)
                    if cur > end_date:
                        break
                    # prescription qty: number of administrations in the 12-week window
                    # `qty` in prescription rows should represent the number of
                    # administrations in the prescription (e.g., 6回分 for 12週間隔
                    # when base_weeks==2). The per-event gross calculation multiplies
                    # per-event pen composition price by this administration count.
                    try:
                        qty_for_prescription = int(num_admins)
                    except Exception:
                        qty_for_prescription = 1
                    # days supply for the maintenance event: fixed 12 weeks
                    try:
                        ev_days = int(maint_step_weeks * 7)
                    except Exception:
                        ev_days = int(12 * 7)
                    presc.append({'order': order, 'date': cur, 'qty': qty_for_prescription, 'days': ev_days})
                    event_dates.append(datetime.combine(cur, datetime.min.time()))
                    order += 1
                biologic_schedule = presc
            else:
                # fallback to original interval-based generation using provided prescription_interval_weeks
                num_events = len(events)
                for i in range(num_events):
                    event_date = sd + timedelta(weeks=prescription_interval_weeks * i)
                    event_dates.append(event_date)
        except Exception:
            # last-resort fallback
            num_events = len(events)
            for i in range(num_events):
                event_date = sd + timedelta(weeks=prescription_interval_weeks * i)
                event_dates.append(event_date)

    # Aggregate per month — compute from schedule-derived `biologic_events` (10割 gross)
    # and then apply burden_rate and monthly cap per-month (correct application).
    monthly = {}

    # determine burden rate (ユーザ選択可). normalize input
    burden_rate = 0.3
    try:
        br_raw = form.get('burden_ratio')
        if br_raw:
            burden_rate = float(br_raw)
    except Exception:
        burden_rate = 0.3

    # Helper: load monthly caps from data/limit_table.csv
    def _load_monthly_limit(system_version, income_code, age_group):
        path = DATA_DIR / 'limit_table.csv'
        try:
            with path.open(encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get('system_version') == system_version and row.get('income_code') == income_code and row.get('age_group') == age_group:
                        return {
                            'monthly_limit': int(row.get('monthly_limit') or 0),
                            'monthly_limit_after_many': int(row.get('monthly_limit_after_many') or 0) if row.get('monthly_limit_after_many') else None,
                            'income_label': row.get('income_label') or '',
                        }
        except Exception:
            return None
        return None

    limit_info = _load_monthly_limit(selected_system, income_category or '', 'under70')
    if not limit_info:
        # fallback conservative
        limit_info = {'monthly_limit': 99999999, 'monthly_limit_after_many': None, 'income_label': ''}

    # Build a map month->list of biologic gross and add existing when present per event
    month_gross_map = {}
    # Detailed per-month events for per-prescription allocation
    month_events_map = {}
    # Ensure `biologic_events` exists before any potential early references.
    # It will be (re)constructed later for template output.
    biologic_events = []
    # determine price_per_unit for biologic events
    sel_drug_bp = next((d for d in load_drugs() if d.get('drug_id') == drug_id), None)
    try:
        price_per_unit_for_schedule = int(sel_drug_bp.get('price_per_unit') or 0) if sel_drug_bp else 0
    except Exception:
        price_per_unit_for_schedule = 0

    # If this is Xolair (unified 'xolair' id), compute per-event gross from pen composition
    per_event_gross_for_xolair = None
    xolair_display = None
    try:
        if drug_id and 'xolair' in str(drug_id).lower():
            # dose_info should have been set earlier when validating Xolair inputs
            dose_info_local = locals().get('dose_info') if 'dose_info' in locals() else None
            if dose_info_local:
                dose_mg, interval_weeks = dose_info_local
                from src.xolair import build_xolair_prescription
                presc = build_xolair_prescription(int(dose_mg))
                # build a price map from data/drug_price.csv via load_drugs()
                price_map = {}
                for r in load_drugs():
                    name = (r.get('drug_name') or '').strip()
                    try:
                        price_map[name] = int(r.get('price_per_unit') or 0)
                    except Exception:
                        price_map[name] = 0
                per_event_gross_for_xolair = 0
                for it in presc:
                    per_event_gross_for_xolair += int(price_map.get(it.get('drug_name'), 0)) * int(it.get('qty') or 0)
                # Build a human-readable composition string for the UI, e.g.
                # "ゾレア 375mg（300mg+75mg）を2週間毎"
                try:
                    mg_map = {'xolair_300': 300, 'xolair_150': 150, 'xolair_75': 75}
                    parts = []
                    for it in presc:
                        did = it.get('drug_id')
                        qty = int(it.get('qty') or 0)
                        mg = mg_map.get(did)
                        if mg:
                            if qty > 1:
                                parts.append(f"{mg}mg×{qty}")
                            else:
                                parts.append(f"{mg}mg")
                    comp_str = '+'.join(parts) if parts else ''
                    try:
                        admins = int(12 // int(interval_weeks)) if interval_weeks and int(interval_weeks) > 0 else 1
                    except Exception:
                        admins = 1
                    xolair_display = f"ゾレア {dose_mg}mg（{comp_str}）を{int(interval_weeks)}週間毎"
                except Exception:
                    xolair_display = None
    except Exception:
        per_event_gross_for_xolair = None

    # Use prescription schedule (if available) to determine event order and month grouping
    if biologic_schedule:
        for pe in biologic_schedule:
            d = pe.get('date')
            if not d:
                continue
            month = d.strftime('%Y-%m')
            month_gross_map.setdefault(month, {'biologic_gross': 0, 'existing_gross': 0, 'events_count': 0, 'orders': []})
            month_events_map.setdefault(month, [])
            qty = int(pe.get('qty') or 0)
            # If Xolair, use precomputed per-dose gross from pen composition
            if per_event_gross_for_xolair is not None:
                gross = int(per_event_gross_for_xolair) * int(qty or 0)
            else:
                gross = int(qty * price_per_unit_for_schedule)
            month_gross_map[month]['biologic_gross'] += gross
            month_gross_map[month]['events_count'] += 1
            month_gross_map[month]['orders'].append(int(pe.get('order') or 0))
            # store detailed event for later per-prescription allocation
            month_events_map[month].append({'order': int(pe.get('order') or 0), 'date': d, 'qty': qty, 'gross': gross})
    else:
        # When a prescription schedule is not available, fall back to the
        # backend-produced `events` (from simulate_selected_system). Use
        # those entries to build month grouping. `biologic_events` is
        # constructed later for template output, so iterate `events` here.
        for be in events:
            d = be.get('date')
            if not d:
                continue
            # `d` may be a datetime/date or a string; try to normalize
            if isinstance(d, str):
                try:
                    d_dt = datetime.strptime(d, '%Y-%m-%d')
                except Exception:
                    # skip unparseable date
                    continue
            else:
                d_dt = d
            month = d_dt.strftime('%Y-%m')
            month_gross_map.setdefault(month, {'biologic_gross': 0, 'existing_gross': 0, 'events_count': 0, 'orders': []})
            # Prefer explicit Xolair per-event gross when available (pen composition -> price),
            # otherwise fall back to any 'gross' value produced by the backend events.
            if per_event_gross_for_xolair is not None:
                gross_val = int(per_event_gross_for_xolair)
            else:
                gross_val = int(be.get('gross') or 0)
            month_gross_map[month]['biologic_gross'] += gross_val
            month_gross_map[month]['events_count'] += 1
            month_events_map.setdefault(month, [])
            month_events_map[month].append({'order': int(be.get('order') or 0) if be.get('order') else month_gross_map[month]['events_count'], 'date': d_dt, 'qty': 1, 'gross': gross_val})

    # If include_existing, assume existing cost is apportioned to the months where biologic events occur
    if include_existing:
        # existing cost per event
        existing_per_event = existing_weekly_cost_yen * existing_dispense_weeks
        # assign existing_per_event to same months as biologic events in chronological order
        months_sorted_keys = sorted(month_gross_map.keys())
        for k in months_sorted_keys:
            month_gross_map[k]['existing_gross'] += int(existing_per_event)

    # Now compute per-month patient costs and caps
    # Determine whether many-times logic applies (consult calculator helper)
    try:
        many_applicable = is_many_times_applicable(selected_system, income_category or '', 'under70', drug_id, prescription_interval_weeks)
    except Exception:
        many_applicable = False

    # Apply per-month caps by chronological month index.
    # Use `monthly_limit` for months 1..3 and `monthly_limit_after_many` for month 4+ when applicable.
    over_cap_count = 0
    months_keys_sorted = sorted(month_gross_map.keys())
    # Precompute cap per month using same logic as before
    cap_map = {}
    for idx, month in enumerate(months_keys_sorted, start=1):
        monthly_limit = int(limit_info.get('monthly_limit') or 0)
        many_limit = int(limit_info.get('monthly_limit_after_many') or 0) if limit_info.get('monthly_limit_after_many') else None
        if not many_applicable or not many_limit:
            cap = monthly_limit
            is_many = False
        else:
            if idx <= 3:
                cap = monthly_limit
                is_many = False
            else:
                cap = many_limit
                is_many = True
        cap_map[month] = {'cap': cap, 'is_many': is_many}

    # For each month, allocate per-prescription actual payments using running sum against cap.
    for month in months_keys_sorted:
        vals = month_gross_map[month]
        biologic_gross = int(vals['biologic_gross'])
        existing_gross = int(vals.get('existing_gross') or 0)
        cap = int(cap_map.get(month, {}).get('cap') or 0)
        is_many = bool(cap_map.get(month, {}).get('is_many'))

        # Prepare events list (sorted by date then order)
        events_list = sorted(month_events_map.get(month, []), key=lambda x: (x.get('date'), x.get('order')))
        running = 0
        month_raw_total = 0
        month_actual_total = 0
        # Allocate per-event
        for ev in events_list:
            gross = int(ev.get('gross') or 0)
            raw = int(round(gross * burden_rate))
            month_raw_total += raw
            # If no cap, just raw
            if cap and cap > 0:
                allowed = cap - running
                if allowed <= 0:
                    paid = 0
                else:
                    paid = max(0, min(raw, allowed))
            else:
                paid = raw
            running += paid
            month_actual_total += paid
            # annotate event
            ev['raw_self'] = raw
            ev['actual_payment'] = paid

        # record monthly buckets where biologic cap applies to biologic payments only
        monthly[month] = {
            'biologic_raw': biologic_gross,
            'existing_raw': existing_gross,
            'raw_self_pay': int(month_raw_total),
            'final_self_pay': int(month_actual_total),
            'applied_limit': cap,
            'is_many_times': many_applicable and is_many,
            'events': events_list,
        }

        if biologic_gross and month_raw_total > cap:
            over_cap_count += 1

    # Apply subsidy (付加給付) per month if requested: compute post_subsidy_self_pay
    use_subsidy = False
    subsidy_cap = None
    try:
        use_subsidy = True if (form.get('use_subsidy') == 'on' or form.get('use_subsidy') == 'true') else False
        subsidy_cap = int(form.get('subsidy_cap')) if form.get('subsidy_cap') else None
    except Exception:
        use_subsidy = False
        subsidy_cap = None

    # Ensure every event has a default final_pay (defaults to actual_payment)
    for month in months_keys_sorted:
        m = monthly.get(month)
        if not m:
            continue
        events_list = m.get('events', [])
        for ev in events_list:
            ev['final_pay'] = int(ev.get('actual_payment') or 0)
        # initialize post_subsidy_self_pay to biologic after-cap total (will be overridden when subsidy applied)
        m['post_subsidy_self_pay'] = int(m.get('final_self_pay') or 0)

    # When subsidy is enabled, apply monthly cap across biologic events and redistribute proportionally
    if use_subsidy:
        try:
            apply_monthly_subsidy_to_monthly_map(monthly, subsidy_cap)
        except Exception:
            # fallback: leave values as-is
            pass

        # Optional debug output for a common test cap
        try:
            if subsidy_cap is not None and int(subsidy_cap) == 20000:
                print('DEBUG_SUBSIDY_MONTHLY:')
                for month in months_keys_sorted:
                    mm = monthly.get(month)
                    if not mm:
                        continue
                    evs = mm.get('events', [])
                    ev_summary = []
                    for e in evs:
                        ev_summary.append((int(e.get('order') or 0), int(e.get('raw_self') or 0), int(e.get('actual_payment') or 0), int(e.get('final_pay') or 0)))
                    try:
                        sum_final = sum(int(e.get('final_pay') or 0) for e in mm.get('events', []))
                    except Exception:
                        sum_final = None
                    print(f"{month}: biologic_raw={mm.get('biologic_raw')} raw_self_pay={mm.get('raw_self_pay')} final_self_pay={mm.get('final_self_pay')} post_subsidy_stored={mm.get('post_subsidy_self_pay')} post_subsidy_computed={sum_final} events={ev_summary}")
        except Exception:
            pass

    # --- Debug logging for the requested case to prove where discrepancy occurred ---
    debug_case = (drug_id == 'dupixent_300' and start_date == sd.strftime('%Y-%m-%d') and income_category == 'R9_370_510')
    if debug_case:
        print('DEBUG: Running detailed breakdown for Dupixent case')
        print(f'Inputs: drug_id={drug_id}, start_date={start_date}, qty2={qty2}, qty3={qty3}, income={income_category}, include_existing={include_existing}')
        print('\n-- per-event values returned by simulate_selected_system (res["events"]) --')
        for i, ev in enumerate(events, start=1):
            print(f'Event {i}: applied={ev.get("applied")}, applied_limit={ev.get("applied_limit")}, is_many_times={ev.get("is_many_times")}, raw_event_dict={ev}')

        print('\n-- month grouping from biologic_events (10割 gross) and corrected cap application --')
        for m, v in monthly.items():
                # total_medical_cost is computed from biologic + existing gross
                total_medical_cost = int(v.get('biologic_raw', 0)) + int(v.get('existing_raw', 0))
                # raw_self_pay is already computed per-month (biologic_gross * burden_rate)
                patient_before = int(v.get('raw_self_pay', round(total_medical_cost * burden_rate)))
                cap_used = v.get('applied_limit')
                after = v.get('final_self_pay')
                print(f'Month {m}: total_medical_cost={total_medical_cost}, patient_before_cap={patient_before}, cap={cap_used}, patient_after_cap={after}, events_count={month_gross_map.get(m, {}).get("events_count")}')


    # --- Build derived monthly aggregates for period-based reporting ---
    # Create month->computed patient-self-pay values for existing and combined
    # existing_self_pay: existing_raw * burden_rate
    # biologic_self_pay_after_cap: monthly[month]['final_self_pay'] (already capped)
    per_month_patient = {}
    for mkey, v in monthly.items():
        try:
            existing_self = int(round((v.get('existing_raw') or 0) * burden_rate))
        except Exception:
            existing_self = 0
        # biologic_raw self-pay (raw, before cap) - derive from per-prescription allocation
        try:
            biologic_raw_self = int(v.get('raw_self_pay') or 0)
        except Exception:
            biologic_raw_self = 0
        # biologic actual after monthly cap (sum of per-prescription actual_payment)
        biologic_actual = int(v.get('final_self_pay') or 0)
        # combined patient payment before subsidy = existing_self + biologic_actual
        combined = existing_self + biologic_actual
        # combined after subsidy: if post_subsidy_self_pay stored, it represents
        # the biologic portion after subsidy (we apply subsidy to biologic events
        # aggregated per-month). Reconstruct combined_after accordingly.
        if v.get('post_subsidy_self_pay') is not None:
            biologic_after_subsidy = int(v.get('post_subsidy_self_pay'))
            combined_after = existing_self + biologic_after_subsidy
        else:
            biologic_after_subsidy = biologic_actual
            combined_after = combined
        per_month_patient[mkey] = {
            'existing_self': existing_self,
            'biologic_self_raw': biologic_raw_self,
            'biologic_self_after_cap': biologic_actual,
            'biologic_self_after_subsidy': biologic_after_subsidy,
            'combined_self': combined,
            'combined_self_after_subsidy': combined_after,
            'is_many_times': bool(v.get('is_many_times')),
            'applied_limit': int(v.get('applied_limit') or 0),
        }

    # Helper: iterate months between two dates (inclusive start, inclusive end by month)
    def months_between(start_dt, end_dt):
        # start_dt/end_dt are date or datetime
        from datetime import date
        s = start_dt if isinstance(start_dt, date) else start_dt.date()
        e = end_dt if isinstance(end_dt, date) else end_dt.date()
        months = []
        cur_year = s.year
        cur_month = s.month
        while True:
            months.append(f"{cur_year:04d}-{cur_month:02d}")
            # advance month
            if cur_year == e.year and cur_month == e.month:
                break
            cur_month += 1
            if cur_month > 12:
                cur_month = 1
                cur_year += 1
            # stop if we passed end month
            if (cur_year > e.year) or (cur_year == e.year and cur_month > e.month):
                break
        return months

    # Build ranges needed: rolling year1 (sd -> sd + 11 months), rolling year2 (sd+12 -> sd+23 months)
    try:
        from dateutil.relativedelta import relativedelta
    except Exception:
        # minimal fallback for adding months when python-dateutil is not available
        class relativedelta:
            def __init__(self, months=0):
                self.months = months
            def __radd__(self, other):
                # support date + relativedelta
                y = other.year
                m = other.month + self.months
                # normalize
                y += (m - 1) // 12
                m = ((m - 1) % 12) + 1
                day = min(other.day, 28)
                from datetime import date
                return date(y, m, day)
    sd_date = sd.date() if hasattr(sd, 'date') else sd
    ry1_start = sd_date.replace(day=1)
    ry1_end = (sd_date + relativedelta(months=11)).replace(day=1)
    ry1_months = months_between(ry1_start, ry1_end)

    ry2_start = (sd_date + relativedelta(months=12)).replace(day=1)
    ry2_end = (sd_date + relativedelta(months=23)).replace(day=1)
    ry2_months = months_between(ry2_start, ry2_end)

    # Calendar year of start_date and next calendar year (Jan-Dec)
    cal_start_year = sd_date.year
    cal_next_year = sd_date.year + 1
    cal_start_months = [f"{cal_start_year:04d}-{m:02d}" for m in range(1, 13)]
    cal_next_months = [f"{cal_next_year:04d}-{m:02d}" for m in range(1, 13)]

    def sum_period(month_list):
        ex = 0
        bio_raw = 0
        bio_after = 0
        bio_after_subsidy = 0
        comb = 0
        for mm in month_list:
            p = per_month_patient.get(mm)
            if p:
                ex += int(p.get('existing_self') or 0)
                bio_raw += int(p.get('biologic_self_raw') or 0)
                bio_after += int(p.get('biologic_self_after_cap') or 0)
                bio_after_subsidy += int(p.get('biologic_self_after_subsidy') or 0)
                comb += int(p.get('combined_self') or 0)
        # biologic_plus_annual: sum of biologic patient payments after high-cost cap
        # biologic_plus_annual_subsidy: sum after additional subsidy adjustment
        return {
            'existing_annual': ex,
            'biologic_plus_annual': bio_after,
            'biologic_plus_annual_subsidy': bio_after_subsidy,
            'biologic_annual_only': bio_raw,
            'biologic_after_cap_annual': bio_after,
            'difference': (bio_after - ex),
            'difference_subsidy': (bio_after_subsidy - ex),
        }

    rolling1 = sum_period(ry1_months)
    rolling2 = sum_period(ry2_months)
    # monthly equivalents (実質月額) as integer division (rounded)
    rolling2_monthly_equiv = {
        'existing_monthly': int(round(rolling2.get('existing_annual', 0) / 12.0)),
        'biologic_plus_monthly': int(round(rolling2.get('biologic_plus_annual', 0) / 12.0)),
        'biologic_plus_monthly_subsidy': int(round(rolling2.get('biologic_plus_annual_subsidy', 0) / 12.0)),
        'difference_monthly': int(round(rolling2.get('difference', 0) / 12.0)),
        'difference_monthly_subsidy': int(round(rolling2.get('difference_subsidy', 0) / 12.0)),
    }

    calendar_start = sum_period(cal_start_months)
    calendar_next = sum_period(cal_next_months)
    calendar_start_monthly_equiv = {
        'existing_monthly': int(round(calendar_start.get('existing_annual', 0) / 12.0)),
        'biologic_plus_monthly': int(round(calendar_start.get('biologic_plus_annual', 0) / 12.0)),
        'biologic_plus_monthly_subsidy': int(round(calendar_start.get('biologic_plus_annual_subsidy', 0) / 12.0)),
        'difference_monthly': int(round(calendar_start.get('difference', 0) / 12.0)),
        'difference_monthly_subsidy': int(round(calendar_start.get('difference_subsidy', 0) / 12.0)),
    }
    calendar_next_monthly_equiv = {
        'existing_monthly': int(round(calendar_next.get('existing_annual', 0) / 12.0)),
        'biologic_plus_monthly': int(round(calendar_next.get('biologic_plus_annual', 0) / 12.0)),
        'biologic_plus_monthly_subsidy': int(round(calendar_next.get('biologic_plus_annual_subsidy', 0) / 12.0)),
        'difference_monthly': int(round(calendar_next.get('difference', 0) / 12.0)),
        'difference_monthly_subsidy': int(round(calendar_next.get('difference_subsidy', 0) / 12.0)),
    }

    # attach these aggregates for template
    period_aggregates = {
        'rolling1': rolling1,
        'rolling2': rolling2,
        'rolling2_monthly_equiv': rolling2_monthly_equiv,
        'calendar_start': calendar_start,
        'calendar_start_monthly_equiv': calendar_start_monthly_equiv,
        'calendar_next': calendar_next,
        'calendar_next_monthly_equiv': calendar_next_monthly_equiv,
    }

    # Enforce strict monthly->annual->medical-deduction flow per spec:
    # monthly_self_pay[m] = monthly[m]['final_self_pay'] (after high-cost cap)
    # monthly_post_subsidy[m] = min(monthly_self_pay[m], subsidy_cap) if subsidy enabled
    # annual_post_subsidy = sum(monthly_post_subsidy for months in calendar year)
    # medical_deduction_base = max(0, annual_post_subsidy - 100000)
    # medical_tax_refund = medical_deduction_base * tax_rate
    # final_annual_self_pay = annual_post_subsidy - medical_tax_refund
    try:
        # ensure subsidy inputs available
        use_subsidy = True if (form.get('use_subsidy') == 'on' or form.get('use_subsidy') == 'true') else False
        subsidy_cap = int(form.get('subsidy_cap')) if form.get('subsidy_cap') else None
    except Exception:
        use_subsidy = False
        subsidy_cap = None

    # compute per-month post-subsidy biologic self-pay using strict min rule
    monthly_post = {}
    for mkey, mvals in monthly.items():
        monthly_self = int(mvals.get('final_self_pay') or 0)
        if use_subsidy and subsidy_cap is not None:
            post = min(monthly_self, int(subsidy_cap))
        else:
            post = monthly_self
        # store canonical post-subsidy biologic amount (per-month)
        mvals['post_subsidy_self_pay'] = int(post)
        monthly_post[mkey] = int(post)
        # update per_month_patient if exists
        if per_month_patient.get(mkey):
            per_month_patient[mkey]['biologic_self_after_subsidy'] = int(post)
            per_month_patient[mkey]['combined_self_after_subsidy'] = int(per_month_patient[mkey].get('existing_self', 0) + post)

    # read taxable income (for tax rate) if provided, else 0
    try:
        taxable_income = int(float(form.get('taxable_income') or 0))
    except Exception:
        taxable_income = 0

    def _tax_rate_for_income(ti):
        if ti <= 1950000:
            return 0.05
        if ti <= 3300000:
            return 0.10
        if ti <= 6950000:
            return 0.20
        if ti <= 9000000:
            return 0.23
        if ti <= 18000000:
            return 0.33
        if ti <= 40000000:
            return 0.40
        return 0.45

    tax_rate = _tax_rate_for_income(taxable_income)

    # compute annual post-subsidy and final values for calendar_start and calendar_next
    for (year, month_list, key) in ((cal_start_year, cal_start_months, 'calendar_start'), (cal_next_year, cal_next_months, 'calendar_next')):
        # Sum monthly post-subsidy values into annual totals (canonical month->annual)
        annual_post = sum(int(monthly.get(mm, {}).get('post_subsidy_self_pay') or 0) for mm in month_list)

        # Store annual post-subsidy amounts. Do NOT perform medical-deduction here
        # (that is handled only in the medical-deduction block to ensure income/taxes)
        period_aggregates[key]['annual_post_subsidy_self_pay'] = int(annual_post)

        # Compute and store existing-treatment annual post-subsidy (sum of per-month existing posts)
        existing_monthly_posts = []
        for mm in month_list:
            try:
                existing_m = int(per_month_patient.get(mm, {}).get('existing_self') or 0)
            except Exception:
                existing_m = 0
            if use_subsidy and subsidy_cap is not None:
                existing_post = min(existing_m, int(subsidy_cap))
            else:
                existing_post = existing_m
            existing_monthly_posts.append(int(existing_post))

        existing_annual_post_subsidy = int(sum(existing_monthly_posts))
        period_aggregates[key]['existing_annual_post_subsidy'] = int(existing_annual_post_subsidy)

        # --- biologic event-based annual self-pay (A: what UI should show) ---
        # Sum per-prescription (per-event) final_pay values that fall within the calendar year.
        bio_event_annual = 0
        for mm in month_list:
            for ev in month_events_map.get(mm, []):
                try:
                    d = ev.get('date')
                    # normalize date-like values
                    if isinstance(d, str):
                        try:
                            d_dt = datetime.strptime(d, '%Y-%m-%d')
                        except Exception:
                            continue
                    else:
                        d_dt = d if hasattr(d, 'year') else None
                    if not d_dt:
                        continue
                    if d_dt.year == year:
                        bio_event_annual += int(ev.get('final_pay') or ev.get('actual_payment') or ev.get('raw_self') or 0)
                except Exception:
                    continue

        # store the event-based biologic annual separately; do NOT overwrite annual_post_subsidy_self_pay
        period_aggregates[key]['biologic_plus_annual'] = int(bio_event_annual)

        # --- total self-pay per year (existing + biologic) ---
        # Sum the per-month `combined_self` (existing_self + biologic_actual)
        total_self_pay = 0
        for mm in month_list:
            try:
                total_self_pay += int(per_month_patient.get(mm, {}).get('combined_self', 0))
            except Exception:
                pass

        period_aggregates[key]['total_self_pay_annual'] = int(total_self_pay)
        # --- existing annual self-pay (sum of per-month existing_self) ---
        existing_total = 0
        for mm in month_list:
            try:
                existing_total += int(per_month_patient.get(mm, {}).get('existing_self', 0))
            except Exception:
                pass
        period_aggregates[key]['existing_total_self_pay_annual'] = int(existing_total)

        # difference based on event-sum total vs existing-only total
        try:
            period_aggregates[key]['difference_total_annual'] = int(period_aggregates[key].get('total_self_pay_annual', 0) - period_aggregates[key].get('existing_total_self_pay_annual', 0))
        except Exception:
            period_aggregates[key]['difference_total_annual'] = 0

    # --- Recompute canonical year-level aggregates from month-level values ---
    # Disabled: existing-treatment aggregation by simple weekly arithmetic
    # was causing inconsistencies with month-first subsidy/deduction logic.
    # The canonical monthly->annual->medical pipeline is preserved elsewhere
    # (per-month `monthly[...]['post_subsidy_self_pay']` -> annual sums -> medical calculation).

    # --- Medical deduction (確定申告：医療費控除) handling ---
    # If the form requested medical-deduction, compute deduction and estimated tax/refund
    try:
        use_md = bool(request.form.get('use_medical_deduction'))
    except Exception:
        use_md = False

    if use_md:
        try:
            # taxable income supplied by user (円)
            ti_raw = request.form.get('taxable_income') or 0
            taxable_income = int(float(ti_raw) or 0)
        except Exception:
            taxable_income = 0

        # compute for both calendar_start (④) and calendar_next (⑤)
        for period_key in ('calendar_start', 'calendar_next'):
            try:
                pd = period_aggregates.get(period_key, {})
                pre_existing = int(pd.get('existing_annual') or 0)
                # Use post-subsidy annual biologic self-pay as the sole basis
                # for medical-deduction calculations per policy.
                pre_bio_sub = int(pd.get('annual_post_subsidy_self_pay') or 0)
                pre_bio = int(pre_bio_sub)
                total_medical = int(pre_existing + pre_bio_sub)

                # snapshot pre-medical values
                period_aggregates[period_key]['_pre_medical'] = {
                    'existing_annual': pre_existing,
                    'annual_post_subsidy_self_pay': pre_bio_sub,
                    'total_medical': total_medical,
                }

                # --- Canonical medical-deduction calculation (income tax + resident tax) ---
                # Use `annual_post_subsidy_self_pay` as sole basis for biologic side
                annual_post_sub = int(pd.get('annual_post_subsidy_self_pay') or 0)
                medical_base = max(0, annual_post_sub - 100000)
                income_tax_refund = int(medical_base * tax_rate)
                resident_tax_refund = int(medical_base * 0.10)
                medical_tax_refund_total = int(income_tax_refund + resident_tax_refund)
                final_annual_self_pay = int(annual_post_sub - medical_tax_refund_total)

                # Existing-treatment side: use existing_annual_post_subsidy as basis
                existing_post = int(pd.get('existing_annual_post_subsidy') or 0)
                existing_medical_base = max(0, existing_post - 100000)
                existing_income_refund = int(existing_medical_base * tax_rate)
                existing_resident_refund = int(existing_medical_base * 0.10)
                existing_medical_tax_refund_total = int(existing_income_refund + existing_resident_refund)
                existing_final_annual = int(existing_post - existing_medical_tax_refund_total)

                # Store only allowed fields (do NOT overwrite biologic_plus_annual, existing_annual, difference, etc.)
                period_aggregates[period_key]['medical_tax_refund_income'] = int(income_tax_refund)
                period_aggregates[period_key]['medical_tax_refund_resident'] = int(resident_tax_refund)
                period_aggregates[period_key]['medical_tax_refund_total'] = int(medical_tax_refund_total)
                # compatibility key used by templates
                period_aggregates[period_key]['medical_tax_refund'] = int(medical_tax_refund_total)
                period_aggregates[period_key]['final_annual_self_pay'] = int(final_annual_self_pay)

                # Do NOT overwrite `biologic_plus_annual` here; it is computed from
                # per-prescription event `final_pay` sums in the calendar aggregation.

                # provide nested dict expected by templates
                period_aggregates[period_key]['medical_deduction'] = {
                    'income_tax_refund': int(income_tax_refund),
                    'resident_tax_refund': int(resident_tax_refund),
                    'total_refund': int(medical_tax_refund_total),
                }

                period_aggregates[period_key]['existing_medical_tax_refund_income'] = int(existing_income_refund)
                period_aggregates[period_key]['existing_medical_tax_refund_resident'] = int(existing_resident_refund)
                period_aggregates[period_key]['existing_medical_tax_refund_total'] = int(existing_medical_tax_refund_total)
                period_aggregates[period_key]['existing_final_annual'] = int(existing_final_annual)
                period_aggregates[period_key].setdefault('existing_medical_deduction', {
                    'income_tax_refund': int(existing_income_refund),
                    'resident_tax_refund': int(existing_resident_refund),
                    'total_refund': int(existing_medical_tax_refund_total),
                })

                # recompute diffs on final values only
                diff_after = int(final_annual_self_pay - existing_final_annual)
                diff_sub_after = int(final_annual_self_pay - existing_final_annual)
                period_aggregates[period_key]['difference_after_medical'] = int(diff_after)
                period_aggregates[period_key]['difference_subsidy_after_medical'] = int(diff_sub_after)
            except Exception:
                # ignore individual period failures
                continue

        # No calendar-monthly-equivalents recomputation here to avoid
        # overwriting canonical monthly-equivalent fields.

    # Disabled: keep previously computed biologic_plus_annual values intact.
    # Overriding these here would conflict with the canonical month->annual flow.

    # Monthly-equivalent adjustments left unchanged.

    # Ensure canonical period_aggregates fields are fixed from `final_annual_self_pay`
    # and do not get overwritten by legacy recomputation logic elsewhere.
    try:
        for pkey in ('rolling1', 'rolling2', 'calendar_start', 'calendar_next'):
            pd = period_aggregates.get(pkey)
            if not pd:
                continue
            # prefer final_annual_self_pay (computed by medical-deduction block),
            # fall back to annual_post_subsidy_self_pay if final not present.
            final = int(pd.get('final_annual_self_pay') or pd.get('annual_post_subsidy_self_pay') or 0)
            existing_final = int(pd.get('existing_final_annual') or pd.get('existing_annual_post_subsidy') or 0)

            # Ensure biologic_plus_annual values reflect the annual post-subsidy
            # amount (pre-medical-deduction). Use explicit annual_post_subsidy if present,
            # otherwise fall back to the final value.
            post = int(pd.get('annual_post_subsidy_self_pay') or final)

            pd['biologic_plus_annual_subsidy'] = int(post)
            diff = int(final - existing_final)
            pd['difference_subsidy'] = diff
            pd['difference'] = diff

            # ensure template compatibility key for medical refund exists
            if pd.get('medical_tax_refund_total') is not None:
                pd['medical_tax_refund'] = int(pd.get('medical_tax_refund_total') or 0)
    except Exception:
        pass

    # Sort months
    # Build a minimal placeholder `biologic_events` list so
    # `integrate_biologic_monthly` receives the expected format.
    # Expected event shape (per src/biologic_monthly.py):
    #   { 'date': datetime.date, 'gross': int }
    biologic_events = []
    # If we successfully built a prescription schedule, use it to create biologic_events
    if biologic_schedule:
        # Look up price_per_unit from data/drug_price.csv
        sel_drug = next((d for d in load_drugs() if d.get('drug_id') == drug_id), None)
        try:
            price_per_unit = int(sel_drug.get('price_per_unit') or 0) if sel_drug else None
        except Exception:
            price_per_unit = None

        for pe in biologic_schedule:
            ev_date = pe['date']
            qty = int(pe.get('qty') or 0)
            unit_price = price_per_unit or 100000
            # Try to find annotated event from month_events_map (allocated earlier)
            month = ev_date.strftime('%Y-%m')
            matched = None
            for ev in month_events_map.get(month, []):
                try:
                    if ev.get('date') == ev_date and int(ev.get('order') or 0) == int(pe.get('order') or 0):
                        matched = ev
                        break
                except Exception:
                    continue
            if matched:
                gross_val = int(matched.get('gross') or (qty * unit_price))
                pe['gross'] = gross_val
                pe['raw_self'] = int(matched.get('raw_self') or round(gross_val * burden_rate))
                pe['actual_payment'] = int(matched.get('actual_payment') or 0)
                # ensure final_pay (付加給付後) is propagated to the prescription entry
                if matched.get('final_pay') is not None:
                    pe['final_pay'] = int(matched.get('final_pay'))
                else:
                    pe['final_pay'] = int(pe['actual_payment'])
                biologic_events.append({'date': ev_date, 'gross': gross_val})
            else:
                gross_val = int(qty * unit_price)
                pe['gross'] = gross_val
                pe['raw_self'] = int(round(gross_val * burden_rate))
                pe['actual_payment'] = int(round(gross_val * burden_rate))
                pe['final_pay'] = int(pe['actual_payment'])
                biologic_events.append({'date': ev_date, 'gross': gross_val})
    else:
        for idx, _ev in enumerate(events):
            try:
                ev_date = event_dates[idx].date() if hasattr(event_dates[idx], 'date') else event_dates[idx]
            except Exception:
                ev_date = datetime.today().date()
            try:
                gross_val = int(biologic_raw_per_event) if biologic_raw_per_event is not None else 100000
            except Exception:
                gross_val = 100000
            biologic_events.append({'date': ev_date, 'gross': gross_val})

    # For now, keep the detailed per-month rows (template expects these fields).
    # We previously attempted to merge with `integrate_biologic_monthly`, but that
    # function expects simple int maps; to avoid type mismatches and keep this
    # a minimal, safe change, pass the existing detailed `monthly` buckets to the template.
    months_sorted = sorted(monthly.items())

    # (Removed previous per-year subsidy-from-events logic.)
    # Use month-level `monthly[...]['post_subsidy_self_pay']` when computing
    # calendar-year subsidy totals below.

    # Summary numbers
    biologic_only_annual = int(biologic_only.get('annual_cost', 0))
    biologic_plus_annual = int(biologic_plus_existing.get('annual_cost', 0)) if biologic_plus_existing else None
    # existing-only annual: calculate from reported existing weekly cost multiplied by 52
    existing_only_annual = None
    if include_existing:
        try:
            existing_only_annual = int(existing_weekly_cost_yen or 0) * 52
        except Exception:
            existing_only_annual = None

    # difference: how much the annual cost increases when adding biologic to existing treatment
    # i.e. (biologic + existing) - existing_only
    difference = 0
    # Robustly extract numeric values from result structure (accept both nested and top-level shapes)
    bpa = None
    try:
        if biologic_plus_annual is not None:
            bpa = int(biologic_plus_annual)
        elif include_existing and res and isinstance(res, dict):
            # try nested key
            bpa = int((res.get('biologic_plus_existing') or {}).get('annual_cost') or res.get('annual_cost') or 0)
    except Exception:
        bpa = None

    eoa = None
    try:
        if existing_only_annual is not None:
            eoa = int(existing_only_annual)
    except Exception:
        eoa = None

    # also ensure biologic_only_annual numeric
    boa = None
    try:
        boa = int(biologic_only_annual or 0)
    except Exception:
        boa = None

    # debug log to help troubleshooting
    if include_existing:
        try:
            print(f"DEBUG: bpa={bpa}, eoa={eoa}, boa={boa}, existing_weekly={existing_weekly_cost_yen}")
        except Exception:
            pass

    if include_existing and bpa is not None:
        if eoa is not None:
            difference = int(bpa - eoa)
        else:
            # fallback: use biologic_only if existing-only unavailable
            try:
                difference = int(bpa - int(biologic_only_annual or 0))
            except Exception:
                difference = 0
    elif bpa is not None:
        try:
            difference = int(bpa - int(biologic_only_annual or 0))
        except Exception:
            difference = 0
    else:
        difference = 0

    # (existing_only_annual already computed above)

    # determine days_per_unit for template convenience
    selected_drug = drug_id or ''
    sd_k = (selected_drug or '').lower()
    if 'dupixent' in sd_k or 'デュピクセント' in selected_drug:
        days_per_unit = 14
    elif 'nucala' in sd_k or 'ヌーカラ' in selected_drug:
        days_per_unit = 28
    elif 'teze' in sd_k or 'tezespia' in sd_k or 'tezspire' in sd_k or 'テゼスパイア' in selected_drug:
        days_per_unit = 28
    elif 'fasenra' in sd_k or 'ファセンラ' in selected_drug:
        days_per_unit = 56
    else:
        days_per_unit = None

    # compute controllers / lamas for template (ensure same variables as index())
    inhaled_all = load_inhaled_drugs()
    controllers = [d for d in inhaled_all if (d.get('class') or '').upper() != 'LAMA']
    for idx, d in enumerate(controllers):
        d['_orig_order'] = idx
        d['group'] = determine_controller_group(d.get('display_name') or d.get('drug_id'))
    lamas = [d for d in inhaled_all if (d.get('class') or '').upper() == 'LAMA']
    # determine biologic display name for UI
    selected_biologic_name = ''
    try:
        sd_row = next((d for d in load_drugs() if d.get('drug_id') == drug_id), None)
        if sd_row:
            selected_biologic_name = sd_row.get('drug_name') or sd_row.get('display_name') or drug_id
        else:
            selected_biologic_name = drug_id or ''
    except Exception:
        selected_biologic_name = drug_id or ''
    # If a forced display name (e.g., Xolair computed dose) was set earlier, prefer it
    try:
        if forced_selected_biologic_name:
            selected_biologic_name = forced_selected_biologic_name
    except Exception:
        pass

    # collect oral drugs list for template
    oral_drugs = load_oral_drugs()
    # preserve selected oral ids but filter to known oral_drugs to avoid accidental mismatches
    try:
        raw_selected_oral = form.getlist('oral_drug_ids') if hasattr(form, 'getlist') else []
    except Exception:
        raw_selected_oral = []
    known_oral_ids = {o.get('drug_id') for o in oral_drugs}
    # filter to known ids and make unique (preserve order)
    seen_sel = set()
    selected_oral_ids = []
    for s in raw_selected_oral:
        if s not in known_oral_ids:
            continue
        if s in seen_sel:
            continue
        seen_sel.add(s)
        selected_oral_ids.append(s)

    # ensure template knows whether xolair_* rows exist so JS can render options
    try:
        has_xolair = any((d.get('drug_id') or '').startswith('xolair_') for d in load_drugs())
    except Exception:
        has_xolair = False

    # --- Build year1/year2 dicts for the new compact table view ---
    def _get_year_dict(pd_key):
        pd = period_aggregates.get(pd_key, {})
        # base: existing-only annual (prefer explicit computed field)
        base = int(pd.get('existing_total_self_pay_annual') or pd.get('existing_annual') or 0)
        # bio: combined self-pay annual (existing + biologic)
        bio = int(pd.get('total_self_pay_annual') or (int(pd.get('existing_annual') or 0) + int(pd.get('biologic_plus_annual') or 0)))
        diff = int(bio - base)

        # after_benefit: use the canonical combined post-subsidy annual value
        # (match the value shown on the result card which uses
        # `annual_post_subsidy_self_pay` with fallback to `final_annual_self_pay`)
        after_benefit = int(pd.get('annual_post_subsidy_self_pay') or pd.get('final_annual_self_pay') or 0)
        diff_after_benefit = int(after_benefit - base)

        # medical deduction values (may be absent)
        deduction_total = int(pd.get('medical_tax_refund') or pd.get('medical_tax_refund_total') or 0)
        deduction_tax = int(pd.get('medical_tax_refund_income') or (pd.get('medical_deduction', {}).get('income_tax_refund') if pd.get('medical_deduction') else 0) or 0)
        deduction_resident = int(pd.get('medical_tax_refund_resident') or (pd.get('medical_deduction', {}).get('resident_tax_refund') if pd.get('medical_deduction') else 0) or 0)

        # after_deduction: combined final (biologic final + existing_final)
        bio_final = int(pd.get('final_annual_self_pay') or 0)
        existing_final = int(pd.get('existing_final_annual') or 0)
        after_deduction = int(bio_final + existing_final)
        final_diff = int(after_deduction - base)

        return {
            'base': base,
            'bio': bio,
            'diff': diff,
            'after_benefit': after_benefit,
            'diff_after_benefit': diff_after_benefit,
            'deduction_total': deduction_total,
            'tax': deduction_tax,
            'resident': deduction_resident,
            'after_deduction': after_deduction,
            'final_diff': final_diff,
        }

    year1 = _get_year_dict('calendar_start')
    year2 = _get_year_dict('calendar_next')

    # prepare display labels for summary
    if age_group == 'under70':
        age_label = '70歳未満'
    elif age_group == 'over70':
        age_label = '70歳以上'
    else:
        age_label = age_group or ''

    raw_income = form.get('income_category') or form.get('income') or ''
    income_display = ''
    try:
        if '|' in raw_income:
            income_code, income_display = raw_income.split('|', 1)
        else:
            income_display = raw_income
    except Exception:
        income_display = raw_income or ''

    base_treatment = existing_drug_name or ''

    # Final render: ensure controllers are sorted server-side
    controllers = sort_controllers(controllers)
    controllers = sorted(controllers, key=inhaled_sort_key)
    lamas = sorted(lamas, key=inhaled_sort_key)

    return render_template('index.html',
                           drugs=load_drugs(),
                           existing_drugs=load_existing_drugs(),
                           controllers=controllers,
                           lamas=lamas,
                           oral_drugs=oral_drugs,
                           system_versions=['R7','R8','R9'],
                           income_map=build_income_map(),
                           selected_system=selected_system,
                           selected_age_group=age_group,
                           selected_income_category=raw_income,
                           results=True,
                           include_existing=include_existing,
                           existing_drug_name=existing_drug_name,
                           existing_only_annual=existing_only_annual,
                           biologic_only_annual=biologic_only_annual,
                           biologic_plus_annual=biologic_plus_annual,
                           difference=difference,
                           months=months_sorted,
                           start_date=start_date,
                           qty2=qty2,
                           qty3=qty3,
                           prescription_schedule=biologic_schedule,
                           selected_drug=selected_drug,
                           days_per_unit=days_per_unit,
                           period_aggregates=period_aggregates,
                           # preserve selected existing-mode and inhaled/oral selections for UI
                           selected_existing_mode=form.get('existing_mode') or '',
                           selected_primary_ids=form.getlist('primary_drug_ids') if hasattr(form, 'getlist') else ([] if not form.get('primary_drug_id') else [form.get('primary_drug_id')]),
                           selected_lama_id=form.get('lama_drug_id') or '',
                           selected_oral_ids=selected_oral_ids,
                           selected_existing_drug_ids=form.getlist('existing_drug_ids') if hasattr(form, 'getlist') else [],
                           selected_biologic_name=selected_biologic_name,
                           xolair_table=load_xolair_table_for_ui(),
                           has_xolair=has_xolair,
                           xolair_display=xolair_display,
                           # input summary fields for UI display (template-only)
                           biologic_name=(selected_biologic_name or selected_drug),
                           base_treatment=base_treatment,
                           dose2=qty2,
                           dose3=qty3,
                           system=selected_system,
                           age_group=age_group,
                           age_label=age_label,
                           income_class=income_category,
                           income_display=income_display,
                           copay_rate_percent=copay_rate_percent,
                           taxable_income=taxable_income,
                           benefit_monthly=(subsidy_cap or 0),
                           benefit_enabled=use_subsidy,
                           medical_deduction_enabled=use_md,
                           year1=year1,
                           year2=year2,
                           )


if __name__ == '__main__':
    app.run(debug=True)
