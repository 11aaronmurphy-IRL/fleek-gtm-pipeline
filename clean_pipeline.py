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
import warnings
warnings.filterwarnings('ignore')


# ============================================================
# STEP 1: READ THE EXCEL FILE
# ============================================================
# We read both tabs, pipeline and new_drop_day2, then stack them
# together into one combined list. This means the tool handles
# both the original 265 leads and the fresh day-2 batch in one go.

print("Reading Excel file...")

pipeline = pd.read_excel(
    "Fleek_-_Acquisition_Case_Study_-_Pipeline_Data.xlsx",
    sheet_name="pipeline",
    dtype=str  # Read everything as text first, we'll convert later
)

# Day 2 leads are intentionally NOT read here.
# They are handled separately by batch_handler.py which
# checks for duplicates before adding them to the pipeline.
# This means the batch handler can properly simulate
# receiving new leads the next day without everything
# already being in the pipeline.
df = pipeline.copy()

print(f"  Loaded {len(df)} pipeline leads")
print(f"  Note: day 2 leads handled separately by batch_handler.py")


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
# STEP 7: REMOVE DUPLICATES
# ============================================================
# Some leads appear more than once with different lead_IDs.
# We keep the most recent version of each duplicate based on
# last_touch_date. If both have no date we keep the first one.
# We identify duplicates by matching on cleaned handle for
# resellers and on email for physical shops.

# For resellers: same handle = duplicate
# For shops: same email = duplicate
# We also catch exact lead_id duplicates

# First sort by last_touch_date descending so most recent is first
df['last_touch_date_sort'] = pd.to_datetime(df['last_touch_date'], errors='coerce')
df = df.sort_values('last_touch_date_sort', ascending=False, na_position='last')

before = len(df)

# Remove exact lead_id duplicates keeping most recent
df = df.drop_duplicates(subset=['lead_id'], keep='first')

# Remove duplicate handles (for resellers)
reseller_mask = df['handle'] != ''
df_resellers = df[reseller_mask].drop_duplicates(subset=['handle'], keep='first')
df_shops = df[~reseller_mask]
df = pd.concat([df_resellers, df_shops], ignore_index=True)

# Remove duplicate emails (for shops)
shop_with_email = df['email'].str.len() > 0
df_with_email = df[shop_with_email].drop_duplicates(subset=['email'], keep='first')
df_no_email = df[~shop_with_email]
df = pd.concat([df_with_email, df_no_email], ignore_index=True)

after = len(df)
print(f"  Removed {before - after} duplicates ({before} → {after} leads)")

# Drop the sorting helper column
df = df.drop(columns=['last_touch_date_sort'])


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
    has_handle = pd.notna(row['handle']) and str(row['handle']).strip() != ''

    if has_followers or has_velocity:
        if has_email:
            return 'reseller_with_email'
        return 'reseller'
    else:
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
# SIGNAL LISTS FOR STAGE RECONCILIATION
# ============================================================
# These lists power the reconciliation logic that cross-checks
# every lead's stage label against what was actually said.
# Built from real examples found in this pipeline during testing.

# Meeting confirmed — specific time or visit agreed
MEETING_SIGNALS = [
    'sure, pop in', 'pop in on', 'pop in thursday', 'pop in friday',
    'sure pop in', 'happy to chat', 'mornings best', 'morning best',
    'afternoons best', 'afternoon best', 'call at', 'call on',
    'confirmed', 'booked', 'see you', 'see you then',
    'thursday works', 'friday works', 'monday works',
    'tuesday works', 'wednesday works', 'works for me',
    'that works', 'sounds good for', 'lets do', "let's do",
    'ill be there', "i'll be there", 'we are free',
]

# Hot buying signals — need a response today
HOT_SIGNALS = [
    # Questions about the product
    'how does', 'do you ship', 'what brands', 'can you do',
    'how much', 'send me', 'when can', 'yeah keen',
    'ok sounds good', 'when can we talk', 'tell me more',
    'how does it work', 'payout', 'commission', 'bundle',
    'catalogue', 'catalog', 'demo', 'show me', 'more info',
    'call fri', 'pricing', 'ship to', 'fee structure',
    'menswear', 'womenswear', 'minimum order', 'moq',
    'delivery', 'returns', 'sample', 'interested',
    # Sceptical but engaged
    'whats the catch', "what's the catch", 'what is the catch',
    'sounds too good', 'tell me how',
]

# Hard nos — only these get marked Lost
HARD_NOS = [
    'stop messaging', 'remove me', 'not for us ever',
    'never contact', 'do not contact', 'unsubscribe',
    'please stop', 'leave us alone',
]

# Warm signals — objection or timing, needs handling not closing
WARM_SIGNALS = [
    'already on another platform', 'another platform',
    'already sell on vinted', 'sell on vinted',
    'already on vinted', 'we use vinted',
    'not interested right now', 'not right now',
    'too busy', 'next month', 'try later',
    'back next week', 'maybe later', 'slow season',
    'need to think', 'maybe next month',
]

def reconcile_stage(row):
    stage = row['stage']
    msg = str(row.get('last_inbound_text', '') or '').lower().strip()
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

    # STEP 1: Check for meeting confirmation signals first
    # These take priority over everything else
    # "Sure, pop in on Thursday" and "Happy to chat, mornings best"
    # are confirmed meetings regardless of what stage label says
    if msg and any(phrase in msg for phrase in MEETING_SIGNALS):
        return 'Meeting Booked', True

    # STEP 2: Hard no — only these are truly Lost
    if msg and any(phrase in msg for phrase in HARD_NOS):
        return 'Lost', False

    # STEP 3: Negotiating — merge into Replied
    # There is no evidence of genuine negotiation in this pipeline
    # Anyone in Negotiating either has a buying signal (Replied)
    # or a warm/timing signal (Hold/Replied)
    if stage == 'Negotiating':
        if not msg:
            return 'Replied', True
        if any(phrase in msg for phrase in WARM_SIGNALS):
            return 'Hold', True
        return 'Replied', True

    # STEP 4: Won — check if deal is actually closed
    if stage == 'Won':
        if not msg:
            return 'Won', False
        if any(phrase in msg for phrase in HOT_SIGNALS):
            return 'Replied', True
        follow_up = ['email', 'one-pager', 'send over', 'more info',
                    'details', 'pricing', 'price', 'how does', 'can you']
        if any(phrase in msg for phrase in follow_up):
            return 'Replied', True
        return 'Won', False

    # STEP 5: Lost — check if actually dead
    if stage == 'Lost':
        if not msg:
            # Blank message on Lost — use touches and spend
            if num_touches <= 1 and spend >= 3000:
                return 'Hold', True
            if num_touches >= 5:
                return 'Lost', False
            if spend >= 5000 and num_touches <= 4:
                return 'Hold', True
            return 'Lost', False
        if any(phrase in msg for phrase in HOT_SIGNALS):
            return 'Replied', True
        if any(phrase in msg for phrase in WARM_SIGNALS):
            return 'Hold', True
        if len(msg) > 3:
            return 'Hold', True
        return 'Lost', False

    # STEP 6: Contacted — check if they actually replied
    if stage == 'Contacted':
        if not msg:
            return 'Contacted', False
        if any(phrase in msg for phrase in HOT_SIGNALS):
            return 'Replied', True
        if any(phrase in msg for phrase in WARM_SIGNALS):
            return 'Hold', True
        if len(msg) > 3:
            return 'Replied', True
        return 'Contacted', False

    # STEP 7: Hold — check if actually a hot signal hiding in there
    if stage == 'Hold':
        if not msg:
            return 'Hold', False
        if any(phrase in msg for phrase in HOT_SIGNALS):
            return 'Replied', True
        return 'Hold', False

    # All other stages — keep as is
    return stage, False

reconciliation_results = df.apply(
    lambda row: reconcile_stage(row), axis=1
)
df['stage'] = [r[0] for r in reconciliation_results]
df['stage_overridden'] = [r[1] for r in reconciliation_results]

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
print(f"\nStep 1 complete. Ready for Step 2: Prioritisation.")
