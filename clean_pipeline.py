"""
FLEEK PIPELINE CLEANER — STEP 1
================================
This script takes the raw messy Excel pipeline and outputs a clean CSV.
It is the foundation everything else builds on top of.
Think of it like washing and sorting the laundry before you can fold it.

HOW TO RUN:
    python clean_pipeline.py

OUTPUT:
    pipeline_clean.csv — a clean version of the pipeline ready for the next steps
"""

import pandas as pd
import re
import os
import warnings
warnings.filterwarnings('ignore')


# ============================================================
# STEP 1: READ THE EXCEL FILE
# ============================================================
# We read both tabs, pipeline and new_drop_day2, then stack them
# together into one combined list. This means the tool handles
# both the original 265 leads and the fresh day-2 batch in one go.

print("Reading pipeline data...")

MASTER_FILE = 'raw_master_pipeline.csv'
EXCEL_FILE = 'Fleek_-_Acquisition_Case_Study_-_Pipeline_Data.xlsx'

if os.path.exists(MASTER_FILE):
    # Raw master exists — read from it so batch_handler additions are included
    pipeline = pd.read_csv(MASTER_FILE, dtype=str)
    print(f"  Loaded {len(pipeline)} leads from raw_master_pipeline.csv")
    print(f"  (includes all original leads plus any batch additions)")
else:
    # First run — read from Excel and create the master file
    pipeline = pd.read_excel(
        EXCEL_FILE,
        sheet_name="pipeline",
        dtype=str
    )
    print(f"  Loaded {len(pipeline)} leads from Excel (first run)")
    print(f"  raw_master_pipeline.csv will be created by batch_handler.py")

df = pipeline.copy()


# ============================================================
# STEP 2: CLEAN INSTAGRAM HANDLES
# ============================================================
# The handle column is a mess. Some reps typed @sepiacollective,
# some typed instagram.com/sepiacollective, some just typed
# sepiacollective. We strip everything down to just the plain
# lowercase username so the tool can reliably identify people.

def clean_handle(handle):
    if pd.isna(handle) or str(handle).strip() == '':
        return ''
    h = str(handle).strip().lower()
    # Remove full URL prefix
    h = h.replace('instagram.com/', '')
    h = h.replace('https://www.instagram.com/', '')
    h = h.replace('http://www.instagram.com/', '')
    # Remove @ symbol
    h = h.lstrip('@')
    return h.strip()

df['handle'] = df['handle'].apply(clean_handle)

print(f"  Handles cleaned")


# ============================================================
# STEP 3: STANDARDISE STAGE NAMES
# ============================================================
# Stage names were entered by three different BDRs with no
# consistent format. "contacted", "Contacted", "contacted "
# all mean the same thing. We collapse everything into seven
# clean stages that drive the next action for each lead.
#
# The seven stages are:
#   New          — never contacted
#   Contacted    — we reached out, no reply yet
#   Replied      — they responded
#   Meeting Booked — call or visit scheduled
#   Negotiating  — active commercial conversation
#   Won          — deal closed
#   Lost         — dead for now

STAGE_MAP = {
    # New
    'new': 'New',
    'new lead': 'New',
    'new_lead': 'New',

    # Contacted
    'contacted': 'Contacted',
    'contact': 'Contacted',
    'no response': 'Contacted',

    # Replied
    'replied': 'Replied',
    'reply': 'Replied',
    'warm': 'Replied',
    'warm lead': 'Replied',

    # Meeting Booked
    'call booked': 'Meeting Booked',
    'call-booked': 'Meeting Booked',
    'call_booked': 'Meeting Booked',

    # Negotiating
    'negotiating': 'Negotiating',
    'in negotiation': 'Negotiating',
    'negotiation': 'Negotiating',

    # Won
    'won': 'Won',
    'closed won': 'Won',
    'closed_won': 'Won',
    'wон': 'Won',

    # Lost
    'lost': 'Lost',
    'ghosted': 'Lost',
    'no reply': 'Lost',
}

def clean_stage(stage):
    if pd.isna(stage) or str(stage).strip() == '':
        return 'New'
    # Lowercase and strip whitespace for reliable matching
    s = str(stage).strip().lower()
    return STAGE_MAP.get(s, 'New')  # Default to New if unrecognised

df['stage'] = df['stage'].apply(clean_stage)

# Show what stages we now have
stage_counts = df['stage'].value_counts()
print(f"  Stages standardised: {dict(stage_counts)}")


# ============================================================
# STEP 4: FIX DATE FORMATS
# ============================================================
# Dates are stored in multiple formats: 2026-01-04, 04/12/2025,
# Dec 29, Jan 5, Feb 27. We convert everything to YYYY-MM-DD
# so the tool can sort and compare dates reliably.

def clean_date(date_val):
    if pd.isna(date_val) or str(date_val).strip() == '':
        return ''
    try:
        # pandas can parse most date formats automatically
        parsed = pd.to_datetime(str(date_val).strip(), dayfirst=True, errors='coerce')
        if pd.isna(parsed):
            return ''
        return parsed.strftime('%Y-%m-%d')
    except:
        return ''

df['first_seen_date'] = df['first_seen_date'].apply(clean_date)
df['last_touch_date'] = df['last_touch_date'].apply(clean_date)

print(f"  Dates standardised")


# ============================================================
# STEP 5: CLEAN SPEND FIGURES
# ============================================================
# The est_monthly_spend_gbp column has values like:
# £5,170 or 9000 or £9,000 or 140
# We strip the £ sign and commas and convert to a plain number
# so we can sort and prioritise leads by commercial value.

def clean_spend(spend):
    if pd.isna(spend) or str(spend).strip() == '':
        return 0
    # Remove £ sign, commas and whitespace
    s = str(spend).replace('£', '').replace(',', '').strip()
    try:
        return float(s)
    except:
        return 0

df['est_monthly_spend_gbp'] = df['est_monthly_spend_gbp'].apply(clean_spend)

print(f"  Spend figures cleaned")


# ============================================================
# STEP 6: FLAG BROKEN EMAILS
# ============================================================
# Some emails have obvious errors like double @ symbols:
# ines@@hotmail.com or liam@@hotmail.com
# We flag these rather than delete them so a human can fix them.
# We never silently drop data, we surface the problem instead.

def flag_email(email):
    if pd.isna(email) or str(email).strip() == '':
        return ''
    e = str(email).strip()
    # Count @ symbols — a valid email has exactly one
    if e.count('@') != 1:
        return f"INVALID: {e}"
    # Basic format check
    if not re.match(r'^[^@]+@[^@]+\.[^@]+$', e):
        return f"INVALID: {e}"
    return e

df['email'] = df['email'].apply(flag_email)

invalid_emails = df[df['email'].str.startswith('INVALID:', na=False)]['lead_id'].tolist()
if invalid_emails:
    print(f"  Flagged {len(invalid_emails)} invalid emails: {invalid_emails}")
else:
    print(f"  No invalid emails found")


# ============================================================
# STEP 6b: GEOGRAPHIC DATA SANITISATION
# ============================================================
# Some UK shops have US +1 phone codes due to data entry errors.
# We detect and correct these using three signals:
#
# Rule 1: Email domain check
#   .co.uk email = UK shop. Force country to UK.
#   Assign city to London unless a known UK city is already set.
#
# Rule 2: Keyword override
#   Shop name contains UK location keywords = UK shop.
#   Force country and assign correct city from the keyword.
#
# Rule 3: Data flagging
#   If country was forced to UK but phone still has +1,
#   prepend a warning to the notes field so the rep knows
#   to manually update the phone number.
# ============================================================

# Known UK city keywords mapped to their correct city name
UK_CITY_KEYWORDS = {
    'brick lane': 'London',
    'camden': 'London',
    'shoreditch': 'London',
    'hackney': 'London',
    'dalston': 'London',
    'peckham': 'London',
    'brixton': 'London',
    'london': 'London',
    'manchester': 'Manchester',
    'leeds': 'Leeds',
    'brighton': 'Brighton',
    'bristol': 'Bristol',
    'birmingham': 'Birmingham',
    'liverpool': 'Liverpool',
    'edinburgh': 'Edinburgh',
    'glasgow': 'Glasgow',
    'sheffield': 'Sheffield',
    'nottingham': 'Nottingham',
}

# Known UK cities for Rule 1 — if already set, do not override
KNOWN_UK_CITIES = set(UK_CITY_KEYWORDS.values())

geo_fixes = 0

for idx, row in df.iterrows():
    original_country = str(row.get('country', '') or '').strip()
    original_city = str(row.get('city', '') or '').strip()
    email = str(row.get('email', '') or '').strip().lower()
    store_name = str(row.get('store_name', '') or '').strip().lower()
    phone = str(row.get('phone', '') or '').strip()
    notes = str(row.get('notes', '') or '').strip()

    forced_uk = False
    assigned_city = original_city

    # Rule 1: Email domain check
    if email.endswith('.co.uk') and original_country.upper() not in ['UK', 'UNITED KINGDOM']:
        forced_uk = True
        df.at[idx, 'country'] = 'UK'
        # Only assign London if no specific UK city is already set
        if original_city.title() not in KNOWN_UK_CITIES:
            assigned_city = 'London'
            df.at[idx, 'city'] = 'London'

    # Rule 2: Keyword override — check store name for UK location keywords
    for keyword, city_name in UK_CITY_KEYWORDS.items():
        if keyword in store_name:
            df.at[idx, 'country'] = 'UK'
            df.at[idx, 'city'] = city_name
            assigned_city = city_name
            if original_country.upper() not in ['UK', 'UNITED KINGDOM']:
                forced_uk = True
            break

    # Rule 3: Flag phone mismatch
    # If country was forced to UK but phone starts with +1 (US code)
    phone_clean = phone.replace(' ', '').replace('-', '').replace('(', '').replace(')', '')
    if forced_uk and (phone_clean.startswith('+1') or phone_clean.startswith('001')):
        warning = '[Data Error: Phone country code requires manual update]'
        if notes and notes.lower() != 'nan':
            df.at[idx, 'notes'] = f"{warning} {notes}"
        else:
            df.at[idx, 'notes'] = warning
        geo_fixes += 1

if geo_fixes > 0:
    print(f"\n  Geographic sanitisation: {geo_fixes} leads had country forced to UK with US phone code flagged")
else:
    print(f"\n  Geographic sanitisation: no conflicts found")


# ============================================================
# Matches the dashboard JavaScript exactly.
# Checks: lead_id, handle, email, phone, store+city
# Keeps the first occurrence (most recent after date sort).
# ============================================================

# Sort by last_touch_date descending so most recent is kept
df['last_touch_date_sort'] = pd.to_datetime(df['last_touch_date'], errors='coerce')
df = df.sort_values('last_touch_date_sort', ascending=False, na_position='last')
df = df.drop(columns=['last_touch_date_sort'])

before = len(df)

seen_ids = set()
seen_handles = set()
seen_emails = set()
seen_phones = set()
seen_store_city = set()
clean_rows = []

for _, row in df.iterrows():
    lid = str(row.get('lead_id', '') or '').strip()

    # Normalised handle
    h = str(row.get('handle', '') or '').strip().lower()
    valid_handle = h and h not in ['', 'nan'] and len(h) > 1

    # Valid email — must contain @
    email = str(row.get('email', '') or '').strip().lower()
    while '@@' in email:
        email = email.replace('@@', '@')
    valid_email = '@' in email and len(email) > 3

    # Normalised phone — digits only, strip country codes
    phone_raw = str(row.get('phone', '') or '').strip()
    phone = ''.join(c for c in phone_raw if c.isdigit())
    if phone.startswith('44') and len(phone) > 10:
        phone = '0' + phone[2:]
    if phone.startswith('0044'):
        phone = '0' + phone[4:]
    valid_phone = len(phone) > 5

    # Store plus city
    store = str(row.get('store_name', '') or '').strip().lower()
    city = str(row.get('city', '') or '').strip().lower()
    sc = f'{store}|{city}' if store and city and store != 'nan' and city != 'nan' else ''

    is_dupe = (
        lid in seen_ids or
        (valid_handle and h in seen_handles) or
        (valid_email and email in seen_emails) or
        (valid_phone and phone in seen_phones) or
        (sc and sc in seen_store_city)
    )

    if is_dupe:
        continue

    clean_rows.append(row)
    seen_ids.add(lid)
    if valid_handle:
        seen_handles.add(h)
    if valid_email:
        seen_emails.add(email)
    if valid_phone:
        seen_phones.add(phone)
    if sc:
        seen_store_city.add(sc)

df = pd.DataFrame(clean_rows).reset_index(drop=True)
after = len(df)
print(f"  Removed {before - after} duplicates ({before} → {after} leads)")


# ============================================================
# STEP 8: CLASSIFY LEAD TYPE
# ============================================================
# We classify each lead as reseller or physical_shop based on
# the actual data in the row, NOT the source label.
# This is because the source column is inconsistent.
#
# The most reliable signal is the reseller metrics columns.
# followers, active_listings and sales_velocity_30d are ONLY
# populated for online resellers. Physical shops never have them.
#
# If a reseller ALSO has an email we flag them as
# reseller_with_email because they can be contacted two ways.

def classify_lead(row):
    has_followers = pd.notna(row['followers']) and str(row['followers']).strip() not in ['', '0', 'nan']
    has_velocity = pd.notna(row['sales_velocity_30d']) and str(row['sales_velocity_30d']).strip() not in ['', '0', 'nan']
    has_email = pd.notna(row['email']) and str(row['email']).strip() != '' and not str(row['email']).startswith('INVALID')
    has_handle = pd.notna(row['handle']) and str(row['handle']).strip() not in ['', 'nan']
    has_city = pd.notna(row.get('city', '')) and str(row.get('city', '')).strip() not in ['', 'nan']
    has_store = pd.notna(row.get('store_name', '')) and str(row.get('store_name', '')).strip() not in ['', 'nan']

    # HYBRID: physical store WITH online following
    # Has city/store name AND followers/velocity AND a handle
    # Gets treated as a physical shop for visits
    # AND surfaces in DM queue as secondary channel
    # Higher priority than a standard shop — double the reach
    if (has_city or has_store) and (has_followers or has_velocity) and has_handle:
        return 'hybrid'

    # Pure online reseller
    if has_followers or has_velocity:
        if has_email:
            return 'reseller_with_email'
        return 'reseller'

    # Physical shop only
    return 'physical_shop'

df['lead_type'] = df.apply(classify_lead, axis=1)

type_counts = df['lead_type'].value_counts()
print(f"  Lead types: {dict(type_counts)}")


# ============================================================
# STEP 9: STAGE RECONCILIATION — ADDED AFTER TESTING
# ============================================================
# This step was added after a critical finding during testing.
#
# When the visual deal pipeline was built and the data loaded,
# leads were spotted in the Lost column with Hot reply badges
# on them. Clicking into them revealed last messages like:
# "do you ship to EU" and "what brands do you carry" —
# genuine buying signals, not dead leads.
#
# What had happened: previous BDRs had marked leads as Lost
# without reading what the lead actually said last. The stage
# label in the CRM did not reflect the reality of the conversation.
#
# The fix: cross-check every Lost lead against their last inbound
# message. If the message contradicts the Lost stage, override it.
#
# The logic:
# Lost + hot reply (buying signal) → override to Replied, flag
# Lost + warm reply (objection/timing) → override to Hold, flag
# Lost + no message OR explicit hard no → keep as Lost
#
# This means the tool catches commercial errors made by previous
# reps, not just formatting errors in the data.

# ============================================================
# SIGNAL CLASSIFICATION — THREE LAYER APPROACH
# ============================================================
# Built to scale from 265 leads to 30,000+
#
# LAYER 1: Exact matches for all 25 known messages in this pipeline
# Zero ambiguity — every known message maps to exactly one bucket
# Based on manual review of every unique last_inbound_text
#
# LAYER 2: Keyword patterns for new messages not seen before
# Catches variations like "yeah sounds great when can we chat"
# even if that exact phrase is not in Layer 1
#
# LAYER 3: Claude API fallback for anything that does not match
# Any genuinely unknown message gets classified by AI
# One API call per unknown message — scales automatically
#
# THE BUCKETS (agreed after reviewing all 25 messages):
# MEETING BOOKED: specific day, time or clear call/visit commitment
# REPLIED HOT:    buying signal or question, act today
# REPLIED WARM:   replied but needs handling, not urgent
# HOLD:           timing issue or soft no, follow up later
# LOST:           explicit hard no only

# ---------------------------------------------------------------
# LAYER 1: EXACT MATCHES
# All 25 unique messages from this pipeline classified manually
# ---------------------------------------------------------------

EXACT_MEETING = [
    'happy to chat, mornings best.',
    'sure, pop in on thursday.',
    'can you do a call fri?',
    'ok sounds good when can we talk',
]

EXACT_HOT = [
    'interested - send pricing.',
    'thanks, can you email a one-pager?',
    "what's the fee structure?",
    'do you ship to eu?',
    'do you take menswear too',
    'how does payout work',
    'how much for the whole bundle?',
    'interested but busy this week',
    'send me the bundle list',
    'what brands do you take?',
    'whats the catch lol',
    'whats your commission?',
    'yeah keen, drop details',
]

EXACT_WARM = [
    'owner is back next week, call then.',
    'we already sell on vinted.',
    'already on another platform tbh',
    'need to think about it',
]

EXACT_HOLD = [
    'not taking on new channels currently.',
    'too busy this season, try later.',
    'maybe next month',
    'not interested right now',
]

EXACT_LOST = []

# ---------------------------------------------------------------
# LAYER 2: KEYWORD PATTERNS
# For new messages not seen before — catches variations
# Order matters: LOST first, then MEETING, then HOLD, then WARM, then HOT
# ---------------------------------------------------------------

LOST_KEYWORDS = [
    'stop messaging', 'stop contacting', 'remove me',
    'unsubscribe', 'do not contact', 'please stop',
    'leave us alone', 'never contact', 'not for us ever',
]

MEETING_KEYWORDS = [
    'pop in', 'mornings best', 'afternoons best', 'evenings best',
    'thursday', 'friday', 'monday', 'tuesday', 'wednesday', 'saturday',
    'morning works', 'afternoon works', 'can we meet', 'lets meet',
    "let's meet", 'can you do a call', 'do a call', 'schedule a call',
    'book a call', 'hop on a call', 'jump on a call',
    'when are you free', 'what time works', 'ok sounds good',
    'sounds good, when',
]

HOLD_KEYWORDS = [
    'too busy', 'busy season', 'next month', 'next quarter',
    'try again', 'try later', 'come back', 'check back',
    'not right now', 'not at the moment', 'not currently',
    'slow season', 'quiet period', 'not interested',
    'dont think', "don't think", 'not for us',
    'not what we need', 'not looking for',
]

WARM_KEYWORDS = [
    'vinted', 'already sell', 'we sell on', 'already on another',
    'another platform', 'already use', 'not taking on',
    'already have a supplier', 'need to think', 'think about it',
    'not sure yet', 'maybe', 'perhaps',
]

HOT_KEYWORDS = [
    'fee structure', 'commission', 'payout', 'how does it work',
    'what brands', 'do you ship', 'do you take', 'menswear',
    'womenswear', 'how much', 'bundle', 'catalogue', 'catalog',
    'minimum order', 'moq', 'sample', 'pricing', 'price list',
    'yeah keen', 'sounds good', 'interested', 'send me',
    'drop details', 'tell me more', 'more info',
    'whats the catch', "what's the catch",
    'one-pager', 'brochure', 'overview',
    'busy this week', 'busy today', 'busy tomorrow',
]

# ---------------------------------------------------------------
# LAYER 3: CLAUDE API FALLBACK
# Unknown messages get classified by AI — never miss a lead
# ---------------------------------------------------------------

def classify_with_api(message):
    try:
        import anthropic
        client = anthropic.Anthropic()
        response = client.messages.create(
            model='claude-sonnet-4-6',
            max_tokens=10,
            system="""You classify sales messages into exactly one category.
Reply with only the category name, nothing else.

MEETING_BOOKED - specific day, time or clear call/visit commitment
REPLIED_HOT - buying signal or product question, act today
REPLIED_WARM - replied but needs careful handling, not urgent
HOLD - timing issue or soft no, follow up in 30 days
LOST - explicit hard no, stop messaging

Context: Messages from vintage clothing resellers responding to
outreach from Fleek, a B2B vintage wholesale marketplace.""",
            messages=[{'role': 'user', 'content': f'Classify: "{message}"'}]
        )
        return response.content[0].text.strip()
    except:
        return 'REPLIED_HOT'

def classify_message(msg):
    """
    Three layer classification.
    Returns (stage, reply_type, layer_used)

    Reply types:
    - hot:   buying signal, act today
    - warm:  objection or timing, needs handling
    - amber: no message at all — we do not know where they stand
    - none:  new lead, no contact yet
    - cold:  hard no
    """
    if not msg or str(msg).strip().strip("'`\"") in ['', 'nan']:
        return None, 'amber', 0  # No message = amber, we do not know their intent

    msg_clean = str(msg).strip().lower()

    # Layer 1: Exact matches
    if msg_clean in [m.lower() for m in EXACT_MEETING]:
        return 'Meeting Booked', 'hot', 1
    if msg_clean in [m.lower() for m in EXACT_HOT]:
        return 'Replied', 'hot', 1
    if msg_clean in [m.lower() for m in EXACT_WARM]:
        return 'Replied', 'warm', 1
    if msg_clean in [m.lower() for m in EXACT_HOLD]:
        return 'Hold', 'warm', 1
    if msg_clean in [m.lower() for m in EXACT_LOST]:
        return 'Lost', 'cold', 1

    # Layer 2: Keywords (order: Lost → Meeting → Hold → Warm → Hot)
    if any(kw in msg_clean for kw in LOST_KEYWORDS):
        return 'Lost', 'cold', 2
    if any(kw in msg_clean for kw in MEETING_KEYWORDS):
        return 'Meeting Booked', 'hot', 2
    if any(kw in msg_clean for kw in HOLD_KEYWORDS):
        return 'Hold', 'warm', 2
    if any(kw in msg_clean for kw in WARM_KEYWORDS):
        return 'Replied', 'warm', 2
    if any(kw in msg_clean for kw in HOT_KEYWORDS):
        return 'Replied', 'hot', 2

    # Layer 3: API fallback
    api_result = classify_with_api(msg)
    bucket_map = {
        'MEETING_BOOKED': ('Meeting Booked', 'hot'),
        'REPLIED_HOT': ('Replied', 'hot'),
        'REPLIED_WARM': ('Replied', 'warm'),
        'HOLD': ('Hold', 'warm'),
        'LOST': ('Lost', 'cold'),
    }
    bucket, reply_type = bucket_map.get(api_result, ('Replied', 'hot'))
    return bucket, reply_type, 3

# Backward compatibility
MEETING_SIGNALS = EXACT_MEETING + MEETING_KEYWORDS
HOT_SIGNALS = EXACT_HOT + HOT_KEYWORDS
HARD_NOS = LOST_KEYWORDS
WARM_SIGNALS = EXACT_HOLD + EXACT_WARM + HOLD_KEYWORDS + WARM_KEYWORDS

def reconcile_stage(row):
    stage = row['stage']
    # Strip leading apostrophes and handle nan values
    raw_msg = str(row.get('last_inbound_text', '') or '').strip().strip("'`\"").strip()
    msg = '' if raw_msg.lower() in ['nan', 'none', ''] else raw_msg.lower()
    num_touches = int(row.get('num_touches', 0) or 0)
    spend = float(str(row.get('est_monthly_spend_gbp', 0) or 0).replace('£','').replace(',','') or 0)

    # ============================================================
    # FULL STAGE RECONCILIATION — REBUILT AFTER PIPELINE REVIEW
    # ============================================================
    # The stage labels in the inherited pipeline cannot be trusted.
    # Three stages were found to be systematically wrong:
    #
    # NEGOTIATING: Leads marked Negotiating who had never even
    # seen pricing. "Interested - send pricing" is not negotiating.
    # Negotiating is now merged into Replied since there is no
    # evidence of genuine term negotiation in this pipeline.
    #
    # WON: Leads marked Won with last messages like "whats your
    # commission" and "yeah keen drop details". These are not
    # closed deals. Previous BDRs marked Won prematurely.
    #
    # LOST: Leads marked Lost with active buying signals like
    # "do you ship to EU" and "how much for the whole bundle".
    # These are not dead leads, they are unanswered conversations.
    #
    # CONTACTED: Leads marked Contacted who had clearly replied
    # with messages like "Happy to chat, mornings best." That
    # is not just contacted, that is a meeting being booked.
    #
    # The new clean stage structure:
    # New           — never contacted
    # Contacted     — reached out, zero reply received
    # Replied       — any reply received, hot or warm
    # Meeting Booked — specific time or visit confirmed
    # Won           — genuinely closed post reconciliation
    # Hold          — soft no or timing issue, follow up later
    # Lost          — hard no only, stop messaging
    #
    # Negotiating is absorbed into Replied.
    # ============================================================

    # THE GOLDEN RULE: Last message always wins over stage label.
    # We check the message against every signal list regardless
    # of what stage the BDR assigned. This catches cases like:
    # - "call-booked" with last message "do you ship to EU?" → Replied
    # - "call-booked" with last message "Too busy this season" → Hold
    # - "Won" with last message "whats your commission?" → Replied
    # - "Lost" with last message "yeah keen drop details" → Replied

    # STEP 1: Hard no — only these are truly Lost, override everything
    if msg and any(phrase in msg for phrase in HARD_NOS):
        return 'Lost', stage != 'Lost'

    # STEP 2: Warm/Hold signals — override ANY stage including Meeting Booked
    # "Too busy this season" in call-booked = BDR was wrong → Hold
    # "We already sell on Vinted" in Negotiating = misunderstanding → Hold
    if msg and any(phrase in msg for phrase in WARM_SIGNALS):
        return 'Hold', stage != 'Hold'

    # STEP 3: Meeting confirmed — only after ruling out warm signals
    # A specific day, time or clear availability given
    if msg and any(phrase in msg for phrase in MEETING_SIGNALS):
        return 'Meeting Booked', stage != 'Meeting Booked'

    # STEP 4: Hot signals — buying signal or question → Replied
    # "do you ship to EU?" in call-booked = BDR was wrong → Replied
    if msg and any(phrase in msg for phrase in HOT_SIGNALS):
        return 'Replied', stage != 'Replied'

    # STEP 5: Replied/Warm/Negotiating with NO message
    # AND New with touches > 0 — both mean contacted but no reply
    # BDR marked stage without evidence of a real reply.
    #
    # num_touches = 0 → New (genuinely never contacted)
    # num_touches > 0 → Contacted (we reached out, no reply received)
    if not msg:
        if stage in ['Replied', 'Warm', 'Negotiating']:
            # BDR marked replied without getting a reply
            return ('New' if num_touches == 0 else 'Contacted'), True
        if stage == 'New' and num_touches > 0:
            # BDR marked New but touches show we already contacted them
            return 'Contacted', True

    # STEP 6: Won with no message = keep Won
    # Won with follow up language = move to Replied
    if stage == 'Won':
        if not msg:
            return 'Won', False
        follow_up = ['email', 'one-pager', 'send over', 'more info',
                    'details', 'pricing', 'price', 'how does', 'can you']
        if any(phrase in msg for phrase in follow_up):
            return 'Replied', True
        return 'Won', False

    # STEP 6: Negotiating with no message — merge into Replied
    if stage == 'Negotiating':
        return 'Replied', True

    # STEP 7: Lost with blank message — use touches and spend
    if stage == 'Lost':
        if not msg:
            if num_touches <= 1 and spend >= 3000:
                return 'Hold', True
            if num_touches >= 5:
                return 'Lost', False
            if spend >= 5000 and num_touches <= 4:
                return 'Hold', True
            return 'Lost', False
        if len(msg) > 3:
            return 'Hold', True
        return 'Lost', False

    # STEP 8: Contacted with any reply — move to Replied
    if stage == 'Contacted':
        if msg and len(msg) > 3:
            return 'Replied', True
        return 'Contacted', False

    # STEP 9: Keep everything else as is
    return stage, False

reconciliation_results = df.apply(
    lambda row: reconcile_stage(row), axis=1
)
df['stage'] = [r[0] for r in reconciliation_results]
df['stage_overridden'] = [r[1] for r in reconciliation_results]

# ============================================================
# ASSIGN REPLY TYPE TO EVERY LEAD — NO GAPS
# ============================================================
# Every lead must have a reply type. No lead should be uncategorised.
# Hot:   buying signal in last message, act today
# Warm:  objection or timing issue, needs handling
# Amber: no last message at all — we do not know their intent
# None:  physical shop (different channel, different logic)
# Cold:  explicit hard no

def get_reply_type(row):
    msg = str(row.get('last_inbound_text', '') or '').strip().strip("'`\"")
    num_touches = int(str(row.get('num_touches', 0) or 0).strip() or 0)

    # No message — determine if truly new or contacted with no reply
    # Blue  = num_touches is 0 AND no notes — genuinely never touched
    # Amber = num_touches > 0 OR has notes — we know something about them
    #         or we reached out and heard nothing back
    if not msg or msg.lower() in ['', 'nan']:
        notes = str(row.get('notes', '') or '').strip()
        has_notes = notes and notes.lower() not in ['', 'nan']
        if num_touches == 0 and not has_notes:
            return 'new'
        else:
            return 'amber'

    stage, reply_type, layer = classify_message(msg)

    # -------------------------------------------------------
    # DATE-BASED URGENCY ADJUSTMENT
    # -------------------------------------------------------
    # Commercial rule: hot and warm leads should never go
    # more than 7 days without contact. If they do the rep
    # dropped the ball. Surface them as urgent immediately.
    #
    # Uses last_touch_date — real data, not a proxy.
    #
    # Hot + last_touch within 7 days → Hot, actively worked
    # Hot + last_touch over 7 days → Hot OVERDUE, chase today
    # Warm + last_touch within 7 days → Warm, actively worked
    # Warm + last_touch over 7 days → Upgrade to Hot OVERDUE
    #   A warm lead ignored for over a week is now urgent
    #
    # Goal: turn hot leads into meetings, warm into hot.
    # 7 days is the maximum gap for any interested lead.
    # -------------------------------------------------------
    if reply_type in ['hot', 'warm']:
        try:
            current_stage = str(row.get('stage', '') or '').strip()
            if current_stage != 'Hold':
                last_touch = str(row.get('last_touch_date', '') or '').strip()
                if last_touch and last_touch.lower() not in ['', 'nan', 'none']:
                    last_touch_date = pd.to_datetime(last_touch, dayfirst=True, errors='coerce')
                    if pd.notna(last_touch_date):
                        days_since = (pd.Timestamp.now() - last_touch_date).days
                        # Only flag as overdue if date is in the past (days_since > 0)
                        # AND more than 7 days ago
                        # Future dates mean data entry error — ignore them
                        if 7 < days_since < 730:  # between 7 days and 2 years
                            reply_type = 'hot'
                # If no last_touch_date — do not change reply_type
                # Missing date means we cannot determine urgency
        except:
            pass

    return reply_type
def get_obj_type(row):
    msg = str(row.get('last_inbound_text', '') or '').strip().strip("'`\"").lower()
    if not msg or msg == 'nan':
        return 'none'
    if any(kw in msg for kw in ['vinted', 'already sell', 'sell on vinted']):
        return 'misunderstanding'
    if any(kw in msg for kw in ['another platform', 'already on another']):
        return 'platform'
    if any(kw in msg for kw in ['too busy', 'next month', 'try later', 'slow season', 'not right now']):
        return 'timing'
    if 'not interested' in msg:
        return 'soft_no'
    if any(kw in msg for kw in ['need to think', 'maybe', 'not sure']):
        return 'undecided'
    if 'not taking on' in msg:
        return 'channel_objection'
    return 'none'

df['reply_type'] = df.apply(get_reply_type, axis=1)
df['obj_type'] = df.apply(get_obj_type, axis=1)

# Print reply type breakdown
reply_counts = df[df['lead_type'] != 'physical_shop']['reply_type'].value_counts()
print(f"\nReply type breakdown (resellers only):")
for rt, count in reply_counts.items():
    print(f"  {rt}: {count}")

overridden = df[df['stage_overridden'] == True]
hot_recovered = df[(df['stage_overridden'] == True) & (df['stage'] == 'Replied')]
hold_recovered = df[(df['stage_overridden'] == True) & (df['stage'] == 'Hold')]

if len(overridden) > 0:
    print(f"\n⚠ Stage reconciliation found {len(overridden)} misclassified leads:")
    print(f"  {len(hot_recovered)} moved to Replied — had buying signals or open questions")
    print(f"  {len(hold_recovered)} moved to Hold — had unanswered messages, not hard nos")
    print(f"  Combined est. monthly spend recovered: £{overridden['est_monthly_spend_gbp'].sum():,.0f}")
    print(f"  Note: includes Won leads marked closed before the deal was actually done")
    for _, lead in overridden.iterrows():
        identifier = lead.get('handle') or lead.get('store_name') or lead.get('lead_id')
        last_msg = str(lead.get("last_inbound_text",""))[:60]
        stage_now = lead["stage"]
        print(f"    -> {identifier} | now: {stage_now} | last said: {last_msg}")
else:
    print(f"\n✓ Stage reconciliation: no misclassified Lost leads found")


# ============================================================
# STEP 10: SAVE THE CLEAN FILE
# ============================================================
# We output a clean CSV file. CSV is a simple text format that
# any tool can read. This becomes the input for every step
# that follows. Think of it as the clean version of the data
# that the rest of the pipeline runs on.

output_file = 'pipeline_clean.csv'
df.to_csv(output_file, index=False)

print(f"\n✓ Clean pipeline saved to {output_file}")
print(f"  Total leads: {len(df)}")
print(f"  Resellers: {len(df[df['lead_type'] == 'reseller'])}")
print(f"  Resellers with email: {len(df[df['lead_type'] == 'reseller_with_email'])}")
print(f"  Physical shops: {len(df[df['lead_type'] == 'physical_shop'])}")
print(f"  Hybrid (shop + online): {len(df[df['lead_type'] == 'hybrid'])}")
if len(df[df['lead_type'] == 'hybrid']) > 0:
    print(f"  Hybrid leads surface in BOTH shop sequencer AND DM queue")
print(f"\nStep 1 complete. Ready for Step 2: Prioritisation.")
