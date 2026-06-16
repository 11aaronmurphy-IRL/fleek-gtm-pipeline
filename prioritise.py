"""
FLEEK PIPELINE — STEP 2: PRIORITISATION
========================================
This script reads the clean pipeline from Step 1 and answers
two questions:

1. Which 40 resellers do we DM on Instagram today?
2. Which physical shops do we contact next, and in what order?

KEY COMMERCIAL INSIGHT (Aaron Murphy):
---------------------------------------
Just because a lead has "Replied" does not mean they need a
follow up in the traditional sense. The last_inbound_text tells
the real story. We split replied leads into three buckets:

HOT REPLY — buying signal or open question. Contact today.
Examples: "yeah keen", "send me the bundle list", "can we talk fri"

WARM REPLY — objection or timing issue. Handle it, do not give up.
Examples:
- "already on another platform" = OBJECTION. Handle it.
  Response: most of our best customers use multiple platforms.
  Fleek gives you stock you cannot get anywhere else.
- "We already sell on Vinted" = MISUNDERSTANDING. Clarify.
  Fleek is a wholesale sourcing tool, not a selling platform.
- "maybe next month" = TIMING. Follow up in 30 days.
- "Too busy this season" = TIMING. Follow up in 6 weeks.
- "not interested right now" = SOFT NO. Follow up in 30 days.

COLD REPLY — explicit rejection with no opening left.
Examples: "stop messaging me", "remove me from your list"
Only these go to Lost. Nothing is dead unless they say a hard no.

HOW TO RUN:
    python prioritise.py

INPUT:
    pipeline_clean.csv — the output from Step 1

OUTPUT:
    todays_resellers.csv  — top 40 Instagram resellers to DM today
    todays_shops.csv      — physical shops sequenced by priority and city
"""

import pandas as pd
import json
import urllib.request
import warnings
warnings.filterwarnings('ignore')


# ============================================================
# REPLY CLASSIFICATION USING CLAUDE API
# ============================================================
# Instead of manually listing every possible reply phrase,
# we use Claude to read each last message and judge whether
# a follow up is needed and what type of response to send.
#
# This is more reliable than a static keyword list because
# human language is unpredictable. Claude understands context.
#
# Aaron's commercial logic is baked into the prompt so Claude
# makes decisions the way a good AE would, not like a robot.

def classify_reply(last_message):
    """
    Takes the last message a lead sent and returns:
    - reply_type: hot, warm, or cold
    - follow_up_timing: today, 7_days, 30_days, 60_days, never
    - objection_type: what objection to handle if any
    - recommended_response: what kind of message to send back
    """
    if not last_message or str(last_message).strip() == '' or str(last_message).strip() == 'nan':
        return {
            'reply_type': 'none',
            'follow_up_timing': 'today',
            'objection_type': None,
            'recommended_response': 'No reply yet — send first outreach'
        }

    prompt = f"""You are a sales analyst for Fleek, a B2B wholesale marketplace for secondhand vintage clothing.

A lead has sent this message: "{last_message}"

Classify this reply using these commercial rules:

HOT — buying signal or genuine question that needs an answer today
Examples: "yeah keen", "send me the bundle list", "can we do a call", "what brands do you take", "how does payout work", "interested", "sounds good"

WARM — objection or timing issue. Never give up on these. Handle them.
- "already on another platform" = objection, handle it (most customers use multiple platforms)
- "We already sell on Vinted" = misunderstanding, clarify (Fleek is for sourcing not selling)
- "maybe next month" = timing, follow up in 30 days
- "Too busy this season" = timing, follow up in 6 weeks
- "not interested right now" = soft no, follow up in 30 days
- "need to think about it" = undecided, follow up in 7 days
- "whats the catch" = sceptical, needs reassurance today

COLD — explicit hard rejection with no opening left
Examples: "stop messaging me", "remove me from your list", "definitely not for us ever"

Return ONLY a JSON object with no other text:
{{"reply_type": "hot|warm|cold", "follow_up_timing": "today|7_days|30_days|60_days|never", "objection_type": "platform_objection|timing|misunderstanding|sceptical|hard_no|none", "recommended_response": "one sentence describing what to say next"}}"""

    try:
        data = json.dumps({
            "model": "claude-sonnet-4-20250514",
            "max_tokens": 200,
            "messages": [{"role": "user", "content": prompt}]
        }).encode('utf-8')

        req = urllib.request.Request(
            'https://api.anthropic.com/v1/messages',
            data=data,
            headers={'Content-Type': 'application/json'},
            method='POST'
        )

        with urllib.request.urlopen(req, timeout=10) as response:
            result = json.loads(response.read().decode('utf-8'))
            text = result['content'][0]['text'].strip()
            # Extract JSON from response
            start = text.find('{')
            end = text.rfind('}') + 1
            if start >= 0 and end > start:
                return json.loads(text[start:end])
    except:
        pass

    # Fallback if API call fails — use simple keyword matching
    msg = str(last_message).lower()

    hard_no = ['stop messaging', 'remove me', 'not for us ever', 'never']
    buying = ['yeah keen', 'sounds good', 'send me', 'can we talk', 'interested',
              'bundle list', 'call fri', 'drop details', 'when can we']
    objections = ['another platform', 'already on', 'sell on vinted', 'too busy',
                  'not interested', 'maybe next month', 'try later', 'need to think']

    if any(phrase in msg for phrase in hard_no):
        return {'reply_type': 'cold', 'follow_up_timing': 'never',
                'objection_type': 'hard_no',
                'recommended_response': 'Move to Lost — explicit rejection'}
    elif any(phrase in msg for phrase in buying):
        return {'reply_type': 'hot', 'follow_up_timing': 'today',
                'objection_type': 'none',
                'recommended_response': 'Respond immediately — strong buying signal'}
    elif any(phrase in msg for phrase in objections):
        return {'reply_type': 'warm', 'follow_up_timing': '30_days',
                'objection_type': 'timing',
                'recommended_response': 'Handle objection or set follow up reminder'}
    else:
        return {'reply_type': 'hot', 'follow_up_timing': 'today',
                'objection_type': 'none',
                'recommended_response': 'Replied but unclear — follow up to keep momentum'}


# ============================================================
# READ THE CLEAN PIPELINE
# ============================================================

print("Reading clean pipeline...")
df = pd.read_csv('pipeline_clean.csv', dtype=str)

numeric_cols = ['followers', 'active_listings', 'sales_velocity_30d',
                'est_monthly_spend_gbp', 'num_touches']
for col in numeric_cols:
    df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

print(f"  Loaded {len(df)} clean leads")


# ============================================================
# SPLIT INTO RESELLERS AND PHYSICAL SHOPS
# ============================================================

# HYBRID LEADS appear in BOTH channels
# Primary: treated as physical shop for email/call/visit sequencing
# Secondary: also surface in DM queue because they have an Instagram
#            following that can be reached directly
# Priority boost: hybrid shops score 1.3x higher than standard shops
#                 in the city proposer because they have double the reach
# CHANNEL ALLOCATION
# DM queue: resellers only — people with NO physical address or email
#           Hybrid shops are NOT in the DM queue
#           They have email and an address so no DM slot wasted
# Shop sequencer: physical shops AND hybrid shops
#
# Aaron's rule: the 40 DM slots are for people you can ONLY reach
# via Instagram. The moment someone has an email or physical address
# they come out of the DM queue entirely.
resellers = df[df['lead_type'].isin(['reseller', 'reseller_with_email'])].copy()
shops = df[df['lead_type'].isin(['physical_shop', 'hybrid'])].copy()

print(f"  Resellers: {len(resellers)}")
print(f"  Physical shops: {len(shops)}")


# ============================================================
# CLASSIFY REPLIED LEADS BY MESSAGE CONTENT
# ============================================================
# We check every Replied lead to understand what kind of
# follow up is actually needed. A reply saying "yeah keen"
# is completely different to "not interested right now"
# but both sit in the Replied stage in the CRM.

# ============================================================
# USE REPLY TYPES FROM STEP 1
# ============================================================
# reply_type is now set in clean_pipeline.py using the
# three layer classification system. No need to re-classify
# here. Just use what Step 1 already determined.
# This also means reply_type is consistent across all scripts.

print("\nUsing reply types from Step 1 classification...")

# Ensure reply_type column exists with defaults
if 'reply_type' not in resellers.columns:
    resellers['reply_type'] = 'amber'
else:
    resellers['reply_type'] = resellers['reply_type'].fillna('amber')

if 'obj_type' not in resellers.columns:
    resellers['obj_type'] = 'none'
else:
    resellers['obj_type'] = resellers['obj_type'].fillna('none')

# Add follow_up_timing based on reply_type — vectorised
resellers['follow_up_timing'] = resellers['reply_type'].map({
    'hot': 'today',
    'warm': 'today',
    'amber': '7_days',
    'new': '7_days',
    'cold': 'never',
}).fillna('7_days')

resellers['recommended_response'] = resellers['reply_type'].map({
    'hot': 'Respond today — buying signal',
    'warm': 'Handle objection or set reminder',
    'amber': 'Re-engage — no reply received',
    'new': 'First touch — high value hook',
    'cold': 'SKIP — mark as Lost',
}).fillna('Follow up')

hot = len(resellers[resellers['reply_type'] == 'hot'])
warm = len(resellers[resellers['reply_type'] == 'warm'])
amber = len(resellers[resellers['reply_type'] == 'amber'])
new_leads = len(resellers[resellers['reply_type'] == 'new'])
print(f"  Hot replies: {hot}")
print(f"  Warm replies: {warm}")
print(f"  Amber (contacted, no reply): {amber}")
print(f"  New (never contacted): {new_leads}")


# ============================================================
# SCORE AND PRIORITISE RESELLERS FOR TODAY
# ============================================================
# With only 40 DMs per day we score every reseller and take
# the top 40. The scoring reflects Aaron's commercial logic:
# replied leads with buying signals are worth more than a
# brand new high-follower account that has never been contacted.

DAILY_DM_LIMIT = 40

# ============================================================
# INTENT-FIRST, WHALE-SECOND DAILY PRIORITISATION
# ============================================================
# The 40 DM slots are filled in strict order:
#
# STEP A — CLEAR THE DESK (active conversations first)
# Hot and Warm replies take the top slots automatically.
# Live deals must always get answered first.
# Within each group sorted descending by monthly spend.
# Hot replies come before Warm replies.
#
# STEP B — WHALE FILLER (fill remaining slots)
# If hot + warm is less than 40, fill remaining slots with
# Amber and New leads — highest spend first.
# These are the highest value uncontacted accounts.
#
# Goal: migrate conversations off Instagram to unlimited channels.
# The 40 DM cap is the reason channel migration matters.
# ============================================================

# Exclude Won, Lost, and cold replies — they are not in play
# All vectorised using .loc[] for performance at 30,000 rows
active_resellers = resellers.loc[
    (~resellers['stage'].isin(['Won', 'Lost'])) &
    (resellers['reply_type'] != 'cold')
].copy()

# Vectorised numeric conversion — no loops, scales to 30k rows
active_resellers['est_monthly_spend_gbp'] = pd.to_numeric(
    active_resellers['est_monthly_spend_gbp'], errors='coerce'
).fillna(0)
active_resellers['sales_velocity_30d'] = pd.to_numeric(
    active_resellers['sales_velocity_30d'], errors='coerce'
).fillna(0)
active_resellers['followers'] = pd.to_numeric(
    active_resellers['followers'], errors='coerce'
).fillna(0)
active_resellers['active_listings'] = pd.to_numeric(
    active_resellers['active_listings'], errors='coerce'
).fillna(0)
active_resellers['avg_listing_price_gbp'] = pd.to_numeric(
    active_resellers['avg_listing_price_gbp'], errors='coerce'
).fillna(0)

# STEP A: Active conversations — Hot and Warm replies
# Sorted by spend descending within each group
hot_replies = active_resellers.loc[
    active_resellers['reply_type'] == 'hot'
].sort_values('est_monthly_spend_gbp', ascending=False)

warm_replies = active_resellers.loc[
    active_resellers['reply_type'] == 'warm'
].sort_values('est_monthly_spend_gbp', ascending=False)

active_conversations = pd.concat([hot_replies, warm_replies])
slots_used = len(active_conversations)
slots_remaining = max(0, DAILY_DM_LIMIT - slots_used)

print(f"\nStep A — Clear the desk:")
print(f"  Hot replies: {len(hot_replies)}")
print(f"  Warm replies: {len(warm_replies)}")
print(f"  Total active conversations: {slots_used}")
print(f"  Slots remaining for new outreach: {slots_remaining}")

# STEP B: Whale filler — commercial scoring for uncontacted leads
# ============================================================
# These leads have no reply history so we cannot use last message.
# We score them purely on commercial signals from the scraped data.
#
# SCORING LOGIC FOR NEW AND AMBER LEADS:
#
# 1. Sales velocity (40 points max)
#    Most important signal. High velocity = they need stock urgently.
#    200 items/month = restocking constantly = needs Fleek right now.
#
# 2. Combined revenue — avg_price x velocity (30 points max)
#    Rewards quality sellers not just volume.
#    138 sales at £70 beats 200 sales at £8 every time.
#    This is the signal that separates premium resellers from bargain sellers.
#
# 3. Est monthly spend (20 points max)
#    Useful but treat as secondary — many rows have it blank or estimated.
#    Used as a tiebreaker not a primary signal.
#
# 4. Followers (15 points max)
#    Scale of operation. Bigger audience = bigger recurring need.
#
# 5. Stock turnover ratio — velocity / active_listings (10 points max)
#    NOT active listings alone. High listings + low velocity = stock
#    sitting unsold. High listings + high velocity = genuinely busy.
#    We want the ratio, not the raw number.
#
# 6. Touch point penalty
#    5 or more touches with no reply = deprioritise heavily.
#    Drop to bottom of Step B queue.
#    Fresh high value leads always beat cold ghosts.
# ============================================================

if slots_remaining > 0:
    filler_pool = active_resellers.loc[
        active_resellers['reply_type'].isin(['amber', 'new'])
    ].copy()

    # Calculate commercial score for each filler lead — vectorised
    max_velocity = active_resellers['sales_velocity_30d'].max() or 1
    max_combined = (active_resellers['avg_listing_price_gbp'] * active_resellers['sales_velocity_30d']).max() or 1
    max_spend = active_resellers['est_monthly_spend_gbp'].max() or 1
    max_followers = active_resellers['followers'].max() or 1

    # Signal 1: Sales velocity (40 points)
    filler_pool['score_velocity'] = (
        filler_pool['sales_velocity_30d'] / max_velocity * 40
    ).clip(0, 40)

    # Signal 2: Combined revenue (30 points)
    filler_pool['combined_revenue'] = (
        filler_pool['avg_listing_price_gbp'] * filler_pool['sales_velocity_30d']
    )
    filler_pool['score_combined'] = (
        filler_pool['combined_revenue'] / max_combined * 30
    ).clip(0, 30)

    # Signal 3: Est monthly spend (20 points)
    filler_pool['score_spend'] = (
        filler_pool['est_monthly_spend_gbp'] / max_spend * 20
    ).clip(0, 20)

    # Signal 4: Followers (15 points)
    filler_pool['score_followers'] = (
        filler_pool['followers'] / max_followers * 15
    ).clip(0, 15)

    # Signal 5: Stock turnover ratio (10 points)
    # velocity / active_listings — high ratio means stock moving fast
    # Cap listings at 1 to avoid divide by zero
    filler_pool['turnover_ratio'] = (
        filler_pool['sales_velocity_30d'] /
        filler_pool['active_listings'].clip(lower=1)
    )
    max_turnover = filler_pool['turnover_ratio'].max() or 1
    filler_pool['score_turnover'] = (
        filler_pool['turnover_ratio'] / max_turnover * 10
    ).clip(0, 10)

    # Signal 6: Touch point penalty
    # 5+ touches with no reply = they are ignoring us
    # Drop score by 50 points so fresh leads always rank higher
    filler_pool['touch_penalty'] = filler_pool['num_touches'].apply(
        lambda t: -50 if pd.to_numeric(t, errors='coerce') >= 5 else 0
    )

    # Total commercial score
    filler_pool['step_b_score'] = (
        filler_pool['score_velocity'] +
        filler_pool['score_combined'] +
        filler_pool['score_spend'] +
        filler_pool['score_followers'] +
        filler_pool['score_turnover'] +
        filler_pool['touch_penalty']
    ).round(2)

    # Sort by commercial score descending, take top slots
    filler_leads = filler_pool.sort_values(
        'step_b_score', ascending=False
    ).head(slots_remaining)

    print("Step B - Whale filler:")
    print(f"  Uncontacted leads in pool: {len(filler_pool)}")
    print(f"  Selected for today: {len(filler_leads)}")
    if len(filler_leads) > 0:
        top = filler_leads.iloc[0]
        print(f"  Top Step B lead: {top.get('handle','unknown')} | score: {top['step_b_score']:.0f} | velocity: {top['sales_velocity_30d']:.0f}/mo | spend: £{top['est_monthly_spend_gbp']:,.0f}/mo")
    deprioritised = len(filler_pool[filler_pool['touch_penalty'] < 0])
    if deprioritised > 0:
        print(f"  Deprioritised (5+ touches, no reply): {deprioritised} leads moved to bottom")

    todays_resellers = pd.concat([active_conversations, filler_leads]).copy()
else:
    todays_resellers = active_conversations.head(DAILY_DM_LIMIT).copy()
    print("Step B - Skipped: active conversations fill all 40 slots")

# Add priority rank and slot type for transparency
todays_resellers = todays_resellers.reset_index(drop=True)
todays_resellers['priority_rank'] = todays_resellers.index + 1
todays_resellers['slot_type'] = todays_resellers['reply_type'].map({
    'hot': 'Step A — Active conversation (Hot)',
    'warm': 'Step A — Active conversation (Warm)',
    'amber': 'Step B — Whale filler (Amber)',
    'new': 'Step B — Whale filler (New)',
}).fillna('Step B — Whale filler')

# Also compute priority score for reference
active_resellers['combined_revenue'] = (
    active_resellers['avg_listing_price_gbp'] * active_resellers['sales_velocity_30d']
)

# Vectorised why_today explanation — no row loops
def explain_priority(row):
    rt = row.get('reply_type', '')
    spend = row.get('est_monthly_spend_gbp', 0)
    if rt == 'hot':
        return f"Step A — HOT REPLY | Last said: {str(row.get('last_inbound_text',''))[:50]} | £{int(spend):,}/mo"
    elif rt == 'warm':
        obj = row.get('objection_type', '')
        obj_label = {
            'platform_objection': 'Platform objection — handle differentiation',
            'misunderstanding': 'Misunderstanding — clarify Fleek is for sourcing',
            'timing': 'Timing issue — send content, set reminder',
            'soft_no': 'Soft no — send content, follow up in 30 days',
        }.get(obj, 'Warm reply — handle it')
        return f"Step A — WARM REPLY | {obj_label} | £{int(spend):,}/mo"
    elif rt == 'amber':
        notes = str(row.get('notes', '') or '')
        note_str = f" | Note: {notes}" if notes and notes != 'nan' else ''
        return f"Step B — WHALE FILLER (Amber) | Contacted, no reply | £{int(spend):,}/mo{note_str}"
    else:
        return f"Step B — WHALE FILLER (New) | First touch | £{int(spend):,}/mo"

todays_resellers['why_today'] = todays_resellers.apply(explain_priority, axis=1)

print(f"\nToday's 40 DMs:")
print(f"  Step A — Hot replies: {len(todays_resellers[todays_resellers['reply_type']=='hot'])}")
print(f"  Step A — Warm replies: {len(todays_resellers[todays_resellers['reply_type']=='warm'])}")
print(f"  Step B — Amber filler: {len(todays_resellers[todays_resellers['reply_type']=='amber'])}")
print(f"  Step B — New filler: {len(todays_resellers[todays_resellers['reply_type']=='new'])}")


# ============================================================
# SEQUENCE PHYSICAL SHOPS
# ============================================================
# Physical shops have no daily limit so we sequence all of them.
# UK shops grouped by city for efficient visit planning.
# International shops get email and call only for now.
#
# Within each city:
# 1. Stage priority (Negotiating first, then Meeting Booked, etc)
# 2. Then by spend (highest value first within same stage)

STAGE_PRIORITY = {
    'Negotiating': 1,
    'Meeting Booked': 2,
    'Replied': 3,
    'Contacted': 4,
    'New': 5,
    'Hold': 6,  # Hold = soft no or timing issue, follow up later
    'Lost': 7,  # Lost = explicit hard no only
    'Won': 8,
}

shops['stage_priority'] = shops['stage'].map(STAGE_PRIORITY).fillna(5)

uk_shops = shops[shops['country'] == 'UK'].copy()
intl_shops = shops[shops['country'] != 'UK'].copy()

uk_shops = uk_shops.sort_values(
    ['city', 'stage_priority', 'est_monthly_spend_gbp'],
    ascending=[True, True, False]
)

intl_shops = intl_shops.sort_values(
    ['country', 'city', 'stage_priority', 'est_monthly_spend_gbp'],
    ascending=[True, True, True, False]
)

def recommend_channel(row):
    """
    Full visit booking logic for physical shops.
    UK shops: email → call → book visit → visit
    International: email → call → video meeting only
    Visit is only triggered when justified by stage, intent and spend.
    Online resellers never appear here — this is physical shops only.
    """
    is_uk = str(row.get('country', '')).strip().upper() == 'UK'
    stage = row['stage']
    spend = float(str(row.get('est_monthly_spend_gbp', 0) or 0).replace('£','').replace(',','') or 0)
    reply_type = str(row.get('reply_type', '') or '').strip()
    obj_type = str(row.get('obj_type', '') or '').strip()
    last_msg = str(row.get('last_inbound_text', '') or '').lower().strip().replace('nan','')

    # LOST AND HOLD — no visit ever
    if stage == 'Lost':
        return 'No contact — hard no received. Do not visit.'
    if stage == 'Hold':
        return 'Hold — send content, set reminder. Do not visit yet.'

    # WON — relationship visit for UK, email check in for international
    if stage == 'Won':
        if is_uk:
            return 'Relationship visit — already a customer. Visit to strengthen account and discuss next order.'
        return 'Account management — email check in on next order.'

    # MEETING BOOKED — confirmed, just show up
    if stage == 'Meeting Booked':
        if is_uk:
            return 'Confirmed visit — time agreed, add to city route. No need to rebook.'
        return 'Video call confirmed — join at agreed time.'

    # NEGOTIATING — book visit to close
    if stage == 'Negotiating':
        if is_uk:
            return 'Book visit — email to say you will be in the area, then visit in person. Face to face closes deals email cannot.'
        return 'Call — push to close. Video meeting if possible.'

    # REPLIED — visit depends on reply type and objection
    if stage == 'Replied':
        if is_uk:
            if reply_type == 'hot':
                return 'Book visit — hot reply received, high intent. Email to arrange a time before showing up.'
            if 'vinted' in last_msg or obj_type == 'misunderstanding':
                return 'Book visit — Vinted misunderstanding is easier to clear face to face in 2 minutes than over email.'
            if 'another platform' in last_msg or obj_type == 'platform':
                return 'Book visit — platform objection is easier to handle in person. Fleek differentiation lands better face to face.'
            return 'Book visit — warm reply received. Email to arrange before visiting.'
        return 'Call — warm reply received. Book a video meeting.'

    # CONTACTED — call first, high spend justifies cold visit
    if stage == 'Contacted':
        if is_uk:
            if spend >= 5000:
                return f'Book visit — high value account (£{int(spend):,}/mo). Cold visit justified. Email first to say you will be in the area.'
            return 'Call — follow up on email before visiting.'
        return 'Call — follow up on email sent.'

    # NEW — email first, never visit a new cold lead
    if stage == 'New':
        if is_uk and spend >= 5000:
            return 'Email — high value new account. Visit only after they reply.'
        return 'Email — first contact. Do not visit until they respond.'

    return 'Email — first contact.'

uk_shops['recommended_action'] = uk_shops.apply(recommend_channel, axis=1)
intl_shops['recommended_action'] = intl_shops.apply(recommend_channel, axis=1)

all_shops_sequenced = pd.concat([uk_shops, intl_shops], ignore_index=True)

print(f"\nUK shop visit plan:")
uk_city_counts = uk_shops.groupby('city').size()
for city, count in uk_city_counts.items():
    neg = len(uk_shops[(uk_shops['city'] == city) & (uk_shops['stage'] == 'Negotiating')])
    rep = len(uk_shops[(uk_shops['city'] == city) & (uk_shops['stage'] == 'Replied')])
    print(f"  {city}: {count} shops ({neg} negotiating, {rep} warm)")

print(f"\nInternational (email/call only): {len(intl_shops)}")


# ============================================================
# SAVE OUTPUT FILES
# ============================================================

reseller_cols = ['lead_id', 'handle', 'contact_name', 'stage',
                 'followers', 'sales_velocity_30d', 'est_monthly_spend_gbp',
                 'last_touch_date', 'last_inbound_text', 'priority_score',
                 'why_today', 'reply_type', 'follow_up_timing',
                 'objection_type', 'recommended_response', 'lead_type',
                 'email', 'notes']

shop_cols = ['lead_id', 'store_name', 'contact_name', 'email', 'phone',
             'city', 'country', 'stage', 'est_monthly_spend_gbp',
             'last_touch_date', 'last_inbound_text', 'recommended_action',
             'assigned_bdr', 'notes']

reseller_cols = [c for c in reseller_cols if c in todays_resellers.columns]
shop_cols = [c for c in shop_cols if c in all_shops_sequenced.columns]

todays_resellers[reseller_cols].to_csv('todays_resellers.csv', index=False)
all_shops_sequenced[shop_cols].to_csv('todays_shops.csv', index=False)

# ============================================================
# VISITS TODAY — CONFIRMED APPOINTMENTS ONLY
# ============================================================
# This file starts empty every morning.
# A shop only appears here when the owner has confirmed
# a specific time and the rep has ticked the confirmation
# box in the pipeline Kanban.
#
# The system requires a confirmed appointment before routing.
# That is the difference between showing up randomly
# and showing up to a meeting that is expected.
# ============================================================
confirmed_columns = shop_cols + ['appointment_confirmed']
confirmed_columns = list(dict.fromkeys(confirmed_columns))
visits_today = pd.DataFrame(columns=confirmed_columns)
visits_today.to_csv('visits_today.csv', index=False)

# Regional hubs — city cluster map for background field planning
# Groups shops by city so the team can see pipeline density
# WITHOUT scheduling visits until a time is confirmed
city_clusters = shops.groupby('city').agg(
    total_accounts=('lead_id', 'count'),
    total_pipeline=('est_monthly_spend_gbp', 'sum'),
    meeting_booked=('stage', lambda x: (x=='Meeting Booked').sum()),
    replied=('stage', lambda x: (x=='Replied').sum()),
    contacted=('stage', lambda x: (x=='Contacted').sum()),
).reset_index()
city_clusters['sequence_strategy'] = 'Static Hub — hold until appointment confirmed'
city_clusters = city_clusters.sort_values('total_pipeline', ascending=False)
city_clusters.to_csv('regional_hubs.csv', index=False)

print(f"\n✓ Saved todays_resellers.csv — {len(todays_resellers)} resellers to DM today")
print(f"✓ Saved todays_shops.csv — {len(all_shops_sequenced)} shops sequenced")
print(f"✓ visits_today.csv created — 0 confirmed visits (awaiting owner confirmation)")
print(f"✓ regional_hubs.csv created — {len(city_clusters)} city clusters for field planning")
print(f"\nStep 2 complete. Ready for Step 3: Message drafting.")
