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

resellers = df[df['lead_type'].isin(['reseller', 'reseller_with_email'])].copy()
shops = df[df['lead_type'] == 'physical_shop'].copy()

print(f"  Resellers: {len(resellers)}")
print(f"  Physical shops: {len(shops)}")


# ============================================================
# CLASSIFY REPLIED LEADS BY MESSAGE CONTENT
# ============================================================
# We check every Replied lead to understand what kind of
# follow up is actually needed. A reply saying "yeah keen"
# is completely different to "not interested right now"
# but both sit in the Replied stage in the CRM.

print("\nClassifying replied leads by message content...")

replied_resellers = resellers[resellers['stage'] == 'Replied'].copy()
print(f"  Found {len(replied_resellers)} replied resellers to classify")

reply_classifications = []
for idx, row in replied_resellers.iterrows():
    classification = classify_reply(row.get('last_inbound_text', ''))
    reply_classifications.append({
        'lead_id': row['lead_id'],
        **classification
    })

reply_df = pd.DataFrame(reply_classifications)

# Merge classifications back into resellers
resellers = resellers.merge(reply_df, on='lead_id', how='left')

# Fill non-replied leads
resellers['reply_type'] = resellers['reply_type'].fillna('none')
resellers['follow_up_timing'] = resellers['follow_up_timing'].fillna('today')
resellers['objection_type'] = resellers['objection_type'].fillna('none')
resellers['recommended_response'] = resellers['recommended_response'].fillna('')

# Count classification results
hot = len(resellers[resellers['reply_type'] == 'hot'])
warm = len(resellers[resellers['reply_type'] == 'warm'])
cold = len(resellers[resellers['reply_type'] == 'cold'])
print(f"  Hot replies (contact today): {hot}")
print(f"  Warm replies (handle objection or set reminder): {warm}")
print(f"  Cold replies (move to Lost): {cold}")


# ============================================================
# SCORE AND PRIORITISE RESELLERS FOR TODAY
# ============================================================
# With only 40 DMs per day we score every reseller and take
# the top 40. The scoring reflects Aaron's commercial logic:
# replied leads with buying signals are worth more than a
# brand new high-follower account that has never been contacted.

DAILY_DM_LIMIT = 40

# Exclude Won, Lost, and cold replies from today's list
active_resellers = resellers[
    (~resellers['stage'].isin(['Won', 'Lost'])) &
    (resellers['reply_type'] != 'cold')
].copy()

def score_reseller(row):
    score = 0

    # Signal 1: Hot reply — buying signal, act immediately (50 points)
    # Aaron: "getting a stalled conversation moving is easier than
    # starting a new one from scratch"
    if row['reply_type'] == 'hot':
        score += 50

    # Signal 2: Warm reply — needs handling but do not give up (25 points)
    # Aaron: "nothing is dead unless they say a hard no"
    elif row['reply_type'] == 'warm':
        score += 25

    # Signal 3: Estimated monthly spend (up to 30 points)
    # Higher spend = bigger commercial opportunity
    max_spend = 9000
    spend_score = min(row['est_monthly_spend_gbp'] / max_spend * 30, 30)
    score += spend_score

    # Signal 4: Sales velocity (up to 20 points)
    # Fast sellers need more stock urgently = need Fleek more
    max_velocity = 213
    velocity_score = min(row['sales_velocity_30d'] / max_velocity * 20, 20)
    score += velocity_score

    # Signal 5: Followers (up to 10 points)
    # Bigger audience = bigger recurring stock need
    max_followers = 64798
    follower_score = min(row['followers'] / max_followers * 10, 10)
    score += follower_score

    # Signal 6: Active listings (up to 5 points)
    max_listings = 568
    listing_score = min(row['active_listings'] / max_listings * 5, 5)
    score += listing_score

    return round(score, 2)

active_resellers['priority_score'] = active_resellers.apply(score_reseller, axis=1)
active_resellers = active_resellers.sort_values('priority_score', ascending=False)
todays_resellers = active_resellers.head(DAILY_DM_LIMIT).copy()

def explain_priority(row):
    reasons = []
    if row['reply_type'] == 'hot':
        reasons.append(f"HOT REPLY: {row.get('recommended_response', 'Act now')}")
    elif row['reply_type'] == 'warm':
        obj = row.get('objection_type', '')
        if obj == 'platform_objection':
            reasons.append("OBJECTION: Already on another platform — handle it")
        elif obj == 'misunderstanding':
            reasons.append("MISUNDERSTANDING: Clarify Fleek is for sourcing not selling")
        elif obj == 'timing':
            reasons.append("TIMING: Set follow up reminder")
        elif obj == 'sceptical':
            reasons.append("SCEPTICAL: Needs reassurance — address concerns")
        else:
            reasons.append("WARM REPLY: Handle objection or follow up")
    if row['est_monthly_spend_gbp'] >= 5000:
        reasons.append(f"High spend: £{int(row['est_monthly_spend_gbp']):,}/mo")
    if row['sales_velocity_30d'] >= 100:
        reasons.append(f"Fast seller: {int(row['sales_velocity_30d'])} items/30d")
    if row['followers'] >= 10000:
        reasons.append(f"Large: {int(row['followers']):,} followers")
    if not reasons:
        reasons.append("Strong metrics across the board")
    return " | ".join(reasons)

todays_resellers['why_today'] = todays_resellers.apply(explain_priority, axis=1)

print(f"\nTop 40 resellers for today:")
print(f"  Hot replies: {len(todays_resellers[todays_resellers['reply_type'] == 'hot'])}")
print(f"  Warm replies: {len(todays_resellers[todays_resellers['reply_type'] == 'warm'])}")
print(f"  New/not yet replied: {len(todays_resellers[todays_resellers['reply_type'] == 'none'])}")


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
    'Lost': 6,
    'Won': 7,
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
    is_uk = str(row.get('country', '')).strip().upper() == 'UK'
    stage = row['stage']
    if stage == 'New':
        return 'Email — first contact'
    elif stage == 'Contacted':
        return 'Call — follow up on email'
    elif stage == 'Replied':
        return 'Visit in person' if is_uk else 'Call — book a video meeting'
    elif stage == 'Meeting Booked':
        return 'Visit — confirmed, add to route' if is_uk else 'Video call — confirmed'
    elif stage == 'Negotiating':
        return 'Visit — close it in person' if is_uk else 'Call — push to close'
    elif stage == 'Lost':
        return 'Hold — check back in 60 days'
    elif stage == 'Won':
        return 'Account management — onboarding'
    else:
        return 'Email — first contact'

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

print(f"\n✓ Saved todays_resellers.csv — {len(todays_resellers)} resellers to DM today")
print(f"✓ Saved todays_shops.csv — {len(all_shops_sequenced)} shops sequenced")
print(f"\nStep 2 complete. Ready for Step 3: Message drafting.")
