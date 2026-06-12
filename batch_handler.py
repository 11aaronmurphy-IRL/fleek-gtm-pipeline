"""
FLEEK PIPELINE — STEP 4: DAY 2 BATCH HANDLER
=============================================
This script handles new leads coming in after the initial
pipeline was built. It is the answer to the question:
"What happens when you run the tool again tomorrow?"

THE CORE PROBLEM:
-----------------
Every day new leads come in. If you just re-ran the whole
pipeline from scratch you would:
1. Try to contact people you already messaged yesterday
2. Lose track of where conversations are up to
3. Waste your 40 DM limit on people already in progress

THIS SCRIPT SOLVES THAT BY:
1. Reading the new batch of leads
2. Comparing every new lead against the existing pipeline
3. Skipping anyone already there
4. Adding only genuinely new leads to the pipeline
5. Never messaging the same person twice

DUPLICATE DETECTION — EXHAUSTIVE APPROACH:
-------------------------------------------
We spent time thinking through every possible way a duplicate
could creep in. Here are all the cases we handle:

COVERED:
1. Same lead_id — direct match
2. Same handle different format — @name vs name vs instagram.com/name
   Fixed by stripping @ and URL prefix before comparing
3. Same handle different capitalisation — @SepiA vs @sepia
   Fixed by lowercasing everything before comparing
4. Same email different capitalisation — Info@shop.com vs info@shop.com
   Fixed by lowercasing before comparing
5. Whitespace in handles or emails — " @name " vs "@name"
   Fixed by stripping whitespace before comparing

ADDED IN THIS VERSION:
6. Same store name + same city — Rusty Wardrobe Amsterdam entered
   twice by different BDRs with different contact names
   Fixed by checking store_name + city combination
7. Same phone number — same shop entered twice, one BDR saved
   email, another saved phone only
   Fixed by normalising and checking phone numbers
8. Broken email matching valid email — ines@@hotmail.com should
   still match ines@hotmail.com. We strip extra @ before comparing
   so a typo does not sneak a duplicate through

NOT DEDUPLICATED (intentionally):
9. Similar but different handles — @sepiacollective_ vs @sepiacollective
   These are genuinely different accounts, do not merge them

HOW TO RUN:
    python batch_handler.py

INPUT:
    pipeline_clean.csv           — the existing clean pipeline
    new_drop_day2 tab in Excel   — the fresh incoming leads

OUTPUT:
    pipeline_clean.csv           — updated with new leads added
    new_leads_today.csv          — only the new leads for today
"""

import pandas as pd
import re
import warnings
warnings.filterwarnings('ignore')


# ============================================================
# HELPER FUNCTIONS FOR DUPLICATE CHECKING
# ============================================================

def clean_handle_for_check(h):
    """
    Normalises a handle for comparison.
    Strips @, URL prefix, whitespace and lowercases.
    So @SepiACollective, instagram.com/sepiacollective and
    sepiacollective all become sepiacollective.
    """
    if pd.isna(h) or str(h).strip() in ['', 'nan']:
        return None
    h = str(h).strip().lower()
    h = h.replace('instagram.com/', '').replace('https://www.instagram.com/', '')
    h = h.lstrip('@').strip()
    return h or None


def clean_email_for_check(e):
    """
    Normalises an email for comparison.
    Handles broken emails like ines@@hotmail.com by stripping
    extra @ symbols so they still match the correct version.
    A typo should not allow a duplicate to sneak through.
    """
    if pd.isna(e) or str(e).strip() in ['', 'nan']:
        return None
    e = str(e).strip().lower()
    # Fix broken double @ — ines@@hotmail.com becomes ines@hotmail.com
    while '@@' in e:
        e = e.replace('@@', '@')
    # Must have exactly one @ to be valid
    if e.count('@') != 1:
        return None
    return e


def clean_phone_for_check(p):
    """
    Normalises a phone number for comparison.
    Strips all non-numeric characters so:
    +44 7737 683411, 0044 7737683411 and 07737683411
    all become the same number for comparison purposes.
    """
    if pd.isna(p) or str(p).strip() in ['', 'nan']:
        return None
    # Strip everything except digits
    digits = re.sub(r'\D', '', str(p))
    if len(digits) < 7:
        return None
    # Normalise UK numbers: strip leading 44 or 0044
    if digits.startswith('44') and len(digits) > 10:
        digits = '0' + digits[2:]
    elif digits.startswith('0044'):
        digits = '0' + digits[4:]
    return digits


def clean_store_city_for_check(store, city):
    """
    Creates a combined store+city key for duplicate checking.
    Same store name in the same city is likely the same business
    even if entered by different BDRs with different contact names.
    """
    if pd.isna(store) or str(store).strip() in ['', 'nan']:
        return None
    if pd.isna(city) or str(city).strip() in ['', 'nan']:
        return None
    return f"{str(store).strip().lower()}|{str(city).strip().lower()}"


# ============================================================
# STEP 1: READ THE EXISTING CLEAN PIPELINE
# ============================================================

print("Reading existing clean pipeline...")
try:
    existing = pd.read_csv('pipeline_clean.csv', dtype=str)
    print(f"  Existing pipeline: {len(existing)} leads")
except FileNotFoundError:
    print("ERROR: pipeline_clean.csv not found. Run clean_pipeline.py first.")
    exit(1)

# Build lookup sets for fast duplicate checking
# We check five different ways a duplicate could appear

existing_ids = set(existing['lead_id'].str.strip().tolist())

existing_handles = set(
    h for h in existing['handle'].apply(clean_handle_for_check)
    if h is not None
)

existing_emails = set(
    e for e in existing['email'].apply(clean_email_for_check)
    if e is not None
)

existing_phones = set(
    p for p in existing['phone'].apply(clean_phone_for_check)
    if p is not None
)

existing_store_cities = set(
    sc for sc in existing.apply(
        lambda r: clean_store_city_for_check(r.get('store_name'), r.get('city')), axis=1
    )
    if sc is not None
)

print(f"  Known lead IDs: {len(existing_ids)}")
print(f"  Known handles: {len(existing_handles)}")
print(f"  Known emails: {len(existing_emails)}")
print(f"  Known phones: {len(existing_phones)}")
print(f"  Known store+city combinations: {len(existing_store_cities)}")


# ============================================================
# STEP 2: READ THE NEW BATCH
# ============================================================

print("\nReading day 2 batch...")
try:
    new_batch = pd.read_excel(
        'Fleek_-_Acquisition_Case_Study_-_Pipeline_Data.xlsx',
        sheet_name='new_drop_day2',
        dtype=str
    )
    print(f"  New batch: {len(new_batch)} leads")
except FileNotFoundError:
    print("ERROR: Excel file not found.")
    exit(1)


# ============================================================
# STEP 3: EXHAUSTIVE DUPLICATE CHECKING
# ============================================================
# We check every possible way a duplicate could appear.
# We never silently skip — every skipped lead is logged with
# the exact reason so it can be reviewed if needed.

print("\nRunning exhaustive duplicate checks...")

new_leads = []
skipped = []

for idx, row in new_batch.iterrows():
    lead_id = str(row.get('lead_id', '')).strip()
    handle = clean_handle_for_check(row.get('handle', ''))
    email = clean_email_for_check(row.get('email', ''))
    phone = clean_phone_for_check(row.get('phone', ''))
    store_city = clean_store_city_for_check(
        row.get('store_name', ''), row.get('city', '')
    )

    skip_reason = None

    # Check 1: Same lead_id
    if lead_id in existing_ids:
        skip_reason = f"lead_id {lead_id} already in pipeline"

    # Check 2: Same handle (normalised)
    elif handle and handle in existing_handles:
        skip_reason = f"handle @{handle} already in pipeline"

    # Check 3: Same email (including broken email fix)
    elif email and email in existing_emails:
        skip_reason = f"email {email} already in pipeline"

    # Check 4: Same phone number (normalised)
    elif phone and phone in existing_phones:
        skip_reason = f"phone {phone} already in pipeline (possible duplicate store)"

    # Check 5: Same store name + city
    elif store_city and store_city in existing_store_cities:
        store = str(row.get('store_name', '')).strip()
        city = str(row.get('city', '')).strip()
        skip_reason = f"store '{store}' in {city} already in pipeline"

    if skip_reason:
        # FLAG the duplicate — never silently drop data.
        # The rep can see exactly what was found and why it was skipped.
        # This means nothing is ever lost without explanation.
        skipped.append({
            'lead_id': lead_id,
            'handle': handle or '',
            'store_name': str(row.get("store_name", "")).strip(),
            'reason': skip_reason,
            'action': "FLAGGED AS DUPLICATE — not added to pipeline"
        })
    else:
        new_leads.append(row)

print(f"  Duplicates found and skipped: {len(skipped)}")
for s in skipped:
    print(f"    SKIP {s['lead_id']} ({s['handle']}) — {s['reason']}")
print(f"  Genuinely new leads: {len(new_leads)}")


# ============================================================
# STEP 4: CLEAN AND ADD NEW LEADS
# ============================================================

if not new_leads:
    print("\nNo new leads to process today.")
    print("All day 2 leads were already in the pipeline.")
    exit(0)

new_df = pd.DataFrame(new_leads)

# Apply same cleaning as Step 1
new_df['handle'] = new_df['handle'].apply(
    lambda h: clean_handle_for_check(h) or ''
)

STAGE_MAP = {
    'new': 'New', 'new lead': 'New',
    'contacted': 'Contacted', 'no response': 'Contacted',
    'replied': 'Replied', 'reply': 'Replied', 'warm': 'Replied',
    'call booked': 'Meeting Booked', 'call-booked': 'Meeting Booked',
    'negotiating': 'Negotiating', 'in negotiation': 'Negotiating',
    'won': 'Won', 'closed won': 'Won',
    'lost': 'Lost', 'ghosted': 'Lost',
}

def clean_stage(stage):
    if pd.isna(stage) or str(stage).strip() == '':
        return 'New'
    return STAGE_MAP.get(str(stage).strip().lower(), 'New')

new_df['stage'] = new_df['stage'].apply(clean_stage)

def clean_date(date_val):
    if pd.isna(date_val) or str(date_val).strip() == '':
        return ''
    try:
        parsed = pd.to_datetime(str(date_val).strip(), dayfirst=True, errors='coerce')
        return '' if pd.isna(parsed) else parsed.strftime('%Y-%m-%d')
    except:
        return ''

new_df['first_seen_date'] = new_df['first_seen_date'].apply(clean_date)
new_df['last_touch_date'] = new_df['last_touch_date'].apply(clean_date)

def clean_spend(spend):
    if pd.isna(spend) or str(spend).strip() == '':
        return 0
    s = str(spend).replace('£', '').replace(',', '').strip()
    try:
        return float(s)
    except:
        return 0

new_df['est_monthly_spend_gbp'] = new_df['est_monthly_spend_gbp'].apply(clean_spend)

def classify_lead(row):
    has_followers = pd.notna(row.get('followers')) and str(row.get('followers', '')).strip() not in ['', '0', 'nan']
    has_velocity = pd.notna(row.get('sales_velocity_30d')) and str(row.get('sales_velocity_30d', '')).strip() not in ['', '0', 'nan']
    has_email = pd.notna(row.get('email')) and str(row.get('email', '')).strip() != ''
    if has_followers or has_velocity:
        return 'reseller_with_email' if has_email else 'reseller'
    return 'physical_shop'

new_df['lead_type'] = new_df.apply(classify_lead, axis=1)

# Extract personalisation signals from notes
def extract_personalisation(notes):
    if pd.isna(notes) or str(notes).strip() == '':
        return ''
    notes_lower = str(notes).lower()
    signals = []
    if 'menswear' in notes_lower:
        signals.append("Focus on menswear — Ralph Lauren, Carhartt, Levi's")
    if 'met at market' in notes_lower:
        signals.append('Met at market — reference the meeting')
    if 'price sensitive' in notes_lower:
        signals.append('Price sensitive — lead with value and no hidden fees')
    if 'ref from supplier' in notes_lower:
        signals.append('Referral — mention the connection')
    if 'high engagement' in notes_lower:
        signals.append('High engagement — acknowledge their community')
    if 'big consignment' in notes_lower:
        signals.append('Big consignment potential — mention bulk ordering')
    if 'follows competitor' in notes_lower:
        signals.append('Follows competitor — lead with Fleek differentiators')
    if 'owner travels' in notes_lower:
        signals.append('Owner travels — digital sourcing saves time on the road')
    if 'slow to reply' in notes_lower:
        signals.append('Slow to reply — keep message very short and direct')
    return ' | '.join(signals) if signals else str(notes)

new_df['personalisation_signals'] = new_df['notes'].apply(extract_personalisation)

# Align columns and append to pipeline
for col in existing.columns:
    if col not in new_df.columns:
        new_df[col] = ''

new_df_aligned = new_df[existing.columns]
updated_pipeline = pd.concat([existing, new_df_aligned], ignore_index=True)
updated_pipeline.to_csv('pipeline_clean.csv', index=False)
new_df.to_csv('new_leads_today.csv', index=False)

print(f"\nPipeline updated:")
print(f"  Before: {len(existing)} leads")
print(f"  Added: {len(new_df)} new leads")
print(f"  After: {len(updated_pipeline)} leads")

type_counts = new_df['lead_type'].value_counts()
for lead_type, count in type_counts.items():
    print(f"  {lead_type}: {count}")

signals_found = len(new_df[new_df['personalisation_signals'] != ''])
print(f"  Personalisation signals extracted: {signals_found} leads")

print(f"\n✓ pipeline_clean.csv updated")
print(f"✓ new_leads_today.csv saved — {len(new_df)} new leads")
# Save duplicates log — nothing is ever silently dropped.
# Aaron: flag it, explain why, then skip it.
# The rep can see exactly what was found and why it was not added.
if skipped:
    duplicates_df = pd.DataFrame(skipped)
    duplicates_df.to_csv("duplicates_flagged.csv", index=False)
    print(f"\n✓ duplicates_flagged.csv saved — {len(skipped)} duplicates flagged")
    print(f"  Review this file to see exactly why each lead was skipped:")
    for s in skipped:
        identifier = s.get("handle") or s.get("store_name") or "no identifier"
        print(f"  FLAGGED: {s['lead_id']} ({identifier}) — {s['reason']}")

print(f"\nStep 4 complete.")
print(f"Now run prioritise.py and draft_messages.py for today's updated action list.")
