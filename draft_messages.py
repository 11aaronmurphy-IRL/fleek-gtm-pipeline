"""
FLEEK PIPELINE — STEP 3: MESSAGE DRAFTING
==========================================
This script reads today's prioritised leads from Step 2 and
drafts the actual outreach message for each one.

The rep opens this output every morning, reads the drafted
messages, tweaks if needed, and sends. Instead of spending
2 hours writing messages they spend 20 minutes reviewing
and sending. That is what makes this scalable.

AARON'S COMMERCIAL LOGIC (baked into every message):
-----------------------------------------------------
Never give up on a lead unless they explicitly say hard no.
Every reply type gets a specific response:

BUYING SIGNAL — book a call today with specific times offered
  "yeah keen", "ok sounds good", "when can we talk"
  → Respond immediately, offer two specific times, binary choice

QUESTION — answer it directly then book a call
  "how does payout work", "what brands do you take"
  → Answer the specific question, then offer specific times

MISUNDERSTANDING — clarify then book a call
  "We already sell on Vinted"
  → Clarify Fleek is for sourcing not selling, then book a call

PLATFORM OBJECTION — handle with differentiation then book
  "already on another platform"
  → Most customers use multiple platforms, Fleek has stock
    you cannot get anywhere else. Then offer specific times.

TIMING ISSUE — send content, set reminder, follow up later
  "Too busy this season", "maybe next month"
  → Acknowledge, send info, set follow up reminder

SOFT NO — send content, set 30 day reminder
  "not interested right now"
  → No pressure, send content, check back in 30 days

HARD NO — mark as Lost, no further contact
  "stop messaging me", "remove me from your list"
  → Only these get marked Lost. Nothing else.

THE ONE RULE:
Always end with a specific action. Either a booked call with
real times offered, content sent, or a reminder set.
Never leave a conversation with no next step.

HOW TO RUN:
    python draft_messages.py

INPUT:
    todays_resellers.csv — top 40 resellers from Step 2
    todays_shops.csv     — sequenced shops from Step 2

OUTPUT:
    todays_messages.csv  — every lead with a drafted message
                           and recommended next action
"""

import pandas as pd
import json
import urllib.request
import warnings
warnings.filterwarnings('ignore')


# ============================================================
# MESSAGE DRAFTING VIA CLAUDE API
# ============================================================
# Instead of static templates we use Claude to draft each
# message individually based on:
# - Who the lead is (handle, name, store)
# - What stage they are at
# - What they last said
# - What type of reply it was (hot/warm/cold/none)
# - What channel we are using (DM or email)
#
# Aaron's commercial rules are baked into the system prompt
# so every message reflects real sales judgment not generic
# template thinking.

SYSTEM_PROMPT = """You are drafting outreach messages for Fleek, a B2B wholesale marketplace for secondhand vintage clothing. Fleek connects resellers and vintage stores with wholesale suppliers globally.

YOUR COMMERCIAL RULES (follow these exactly):

1. BUYING SIGNAL ("yeah keen", "when can we talk", "sounds good"):
   Respond with genuine enthusiasm. Book a call immediately.
   Always offer TWO specific times. Binary choice makes it easy to say yes.
   Example close: "I'd love to walk you through it, I have time Thursday at 2pm or Friday morning, does either work for you?"

2. QUESTION ("how does payout work", "what brands do you take"):
   Answer the question directly and specifically. Then book a call.
   Key Fleek facts: everything included in listing price, BNPL up to 45 days no interest, buyer protection, FleekSort grades every item before delivery.
   End with specific times, not "want me to tell you more?"

3. MISUNDERSTANDING ("We already sell on Vinted"):
   Clarify immediately. Fleek is for SOURCING stock, not selling it.
   "Fleek is actually where you source the stock you sell on Vinted. Most of our sellers use both."
   Then book a call with specific times.

4. PLATFORM OBJECTION ("already on another platform"):
   Never accept this as a no. Handle it directly.
   "Most of our best customers were already using other platforms when they joined. Fleek gives you access to stock and suppliers you simply cannot get anywhere else."
   Then book a call with specific times.

5. TIMING ISSUE ("Too busy this season", "maybe next month", "Owner is back next week"):
   Acknowledge without pressure. Send content. Set reminder.
   "Completely understand. I will send over some info so you have it when the time is right. I will check back in with you in [timeframe]."

6. SOFT NO ("not interested right now"):
   No pressure. Send content. Set 30 day reminder.
   "No problem at all. I will send over some info in case it is useful down the line. I will check back in with you in a few weeks."

7. HARD NO ("stop messaging me", "remove me"):
   Do not draft a message. Return SKIP.

TONE RULES:
- Instagram DMs: casual, friendly, under 80 words, no corporate language
- Emails: professional but warm, under 150 words, personalised opener
- Never use "I hope this message finds you well"
- Never use "I wanted to reach out"
- Always end with a specific action, never an open question
- Reference something specific about the lead when possible"""


def draft_message(lead, channel='dm'):
    """
    Drafts a personalised outreach message for a lead.

    channel: 'dm' for Instagram DM, 'email' for physical shops
    """

    # Build context about this lead
    name = lead.get('contact_name', '') or lead.get('handle', '') or lead.get('store_name', '')
    last_message = lead.get('last_inbound_text', '') or ''
    stage = lead.get('stage', 'New')
    reply_type = lead.get('reply_type', 'none')
    objection_type = lead.get('objection_type', 'none')
    follow_up_timing = lead.get('follow_up_timing', 'today')
    store_name = lead.get('store_name', '')
    handle = lead.get('handle', '')
    followers = lead.get('followers', 0)
    spend = lead.get('est_monthly_spend_gbp', 0)
    city = lead.get('city', '')

    # Skip hard nos
    if reply_type == 'cold':
        return {
            'message': 'SKIP — hard no, mark as Lost',
            'next_action': 'Mark as Lost, no further contact',
            'follow_up_date': 'never',
            'channel': channel
        }

    # Build the prompt
    if channel == 'dm':
        lead_description = f"Instagram reseller @{handle}"
        if followers:
            lead_description += f" ({int(float(followers)):,} followers)"
        channel_instruction = "Write a casual Instagram DM under 80 words. Sound like a real person not a corporation."
    else:
        lead_description = f"{store_name} in {city}" if store_name else f"vintage store in {city}"
        channel_instruction = "Write a professional but warm email under 150 words. Include a subject line on the first line starting with 'Subject:'"

    context = f"""Lead: {lead_description}
Contact name: {name}
Current stage: {stage}
Last message they sent: "{last_message}"
Reply classification: {reply_type}
Objection type: {objection_type}
Recommended follow up: {follow_up_timing}
Channel: {channel_instruction}"""

    prompt = f"""{context}

Draft the outreach message following the commercial rules exactly.
Also provide:
- next_action: what to do after sending this (e.g. "Wait for reply", "Set 30 day reminder", "Book call for Thursday")
- follow_up_date: when to follow up (today, 7_days, 30_days, 60_days, never)

Return ONLY a JSON object:
{{"message": "the drafted message", "next_action": "what to do next", "follow_up_date": "timing", "channel": "{channel}"}}"""

    try:
        data = json.dumps({
            "model": "claude-sonnet-4-20250514",
            "max_tokens": 400,
            "system": SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": prompt}]
        }).encode('utf-8')

        req = urllib.request.Request(
            'https://api.anthropic.com/v1/messages',
            data=data,
            headers={'Content-Type': 'application/json'},
            method='POST'
        )

        with urllib.request.urlopen(req, timeout=15) as response:
            result = json.loads(response.read().decode('utf-8'))
            text = result['content'][0]['text'].strip()
            start = text.find('{')
            end = text.rfind('}') + 1
            if start >= 0 and end > start:
                return json.loads(text[start:end])

    except Exception as e:
        pass

    # Fallback if API fails — use rule based drafting
    return fallback_draft(lead, channel, stage, reply_type,
                         objection_type, last_message, name,
                         handle, store_name, city)


def fallback_draft(lead, channel, stage, reply_type, objection_type,
                   last_message, name, handle, store_name, city):
    """
    Rule based fallback if the Claude API call fails.
    Uses Aaron's commercial logic directly.
    """
    display_name = name or handle or store_name or 'there'
    greeting = f"Hey {display_name}" if channel == 'dm' else f"Hi {display_name}"

    msg = str(last_message).lower() if last_message and str(last_message) != 'nan' else ''

    # Buying signal
    if reply_type == 'hot' or any(phrase in msg for phrase in
       ['yeah keen', 'sounds good', 'when can we talk', 'ok sounds good']):
        message = f"{greeting}, really glad to hear it. I'd love to walk you through how Fleek works. I have time Thursday at 2pm or Friday morning, does either work for you?"
        return {'message': message, 'next_action': 'Book call — respond today',
                'follow_up_date': 'today', 'channel': channel}

    # Question about payout
    if 'payout' in msg or 'commission' in msg:
        message = f"{greeting}, great question. On Fleek everything is included in the listing price, shipping, duties and taxes, no hidden fees. We also offer buy now pay later up to 45 days with no interest. I'd love to walk you through your first order. I have time Thursday at 2pm or Friday morning, does either work?"
        return {'message': message, 'next_action': 'Book call — answer sent',
                'follow_up_date': 'today', 'channel': channel}

    # Question about brands
    if 'brand' in msg:
        message = f"{greeting}, we carry a wide range of branded vintage including Ralph Lauren, Nike, Carhartt, Adidas and more. FleekSort grades every item so you know exactly what you are getting before it arrives. I'd love to show you what is available. I have time Thursday or Friday morning, does either work?"
        return {'message': message, 'next_action': 'Book call — answer sent',
                'follow_up_date': 'today', 'channel': channel}

    # Misunderstanding — already sell on Vinted
    if 'vinted' in msg or 'sell on' in msg:
        message = f"{greeting}, great to hear you are on Vinted. Fleek is actually the other side of that equation, it is where you source the stock you sell on Vinted. Most of our sellers use both. I'd love to show you how it works. I have time Thursday or Friday morning, does either work?"
        return {'message': message, 'next_action': 'Book call — objection handled',
                'follow_up_date': 'today', 'channel': channel}

    # Platform objection
    if 'another platform' in msg or 'already on' in msg:
        message = f"{greeting}, totally get that. Most of our best customers were already using other platforms when they joined. Fleek gives you access to stock and suppliers you simply cannot get anywhere else. I'd love to show you. I have time Thursday or Friday morning, does either work?"
        return {'message': message, 'next_action': 'Book call — objection handled',
                'follow_up_date': 'today', 'channel': channel}

    # Timing objection
    if any(phrase in msg for phrase in ['busy', 'next month', 'try later', 'back next week']):
        message = f"{greeting}, completely understand, no pressure at all. I will send over some info so you have it when the time is right. I will check back in with you in a few weeks."
        return {'message': message, 'next_action': 'Send Fleek one-pager, set 30 day reminder',
                'follow_up_date': '30_days', 'channel': channel}

    # Soft no
    if 'not interested' in msg:
        message = f"{greeting}, no problem at all. I will send over some info in case it is useful down the line. I will check back in with you in a few weeks."
        return {'message': message, 'next_action': 'Send content, set 30 day reminder',
                'follow_up_date': '30_days', 'channel': channel}

    # Hold stage — was previously marked Lost but had an unanswered message
    # These were recovered by the stage reconciliation step in clean_pipeline.py
    # Treat them like warm leads — acknowledge, send content, follow up
    if stage == 'Hold':
        message = f"{greeting}, following up on our previous conversation. I wanted to send over some info about Fleek in case the timing is better now. I would love to show you how it works — I have time Thursday at 2pm or Friday morning, does either work?"
        return {'message': message, 'next_action': 'Send content, set 14 day reminder — previously marked Lost incorrectly',
                'follow_up_date': '14_days', 'channel': channel}

    # New lead — first contact DM
    if stage == 'New' and channel == 'dm':
        message = f"Hey {handle or display_name}, came across your page and love what you are doing. We work with resellers like you to make sourcing vintage wholesale easier. Fleek gives you access to graded stock you can browse and order digitally, no more market trips. I'd love to show you. I have time Thursday or Friday morning, does either work?"
        return {'message': message, 'next_action': 'Wait for reply',
                'follow_up_date': '7_days', 'channel': channel}

    # New lead — first contact email
    if stage == 'New' and channel == 'email':
        subject = f"Subject: Sourcing stock for {store_name or city}"
        message = f"{subject}\n\n{greeting},\n\nI came across {store_name or 'your store'} in {city} and wanted to reach out. We work with independent vintage stores to replace manual sourcing with a digital wholesale marketplace. Graded stock you can browse and order without the market trips, FleekSort means every item is categorised and priced before it arrives.\n\nI'd love to show you how it works. I have time Thursday at 2pm or Friday morning, does either work for you?\n\nAaron"
        return {'message': message, 'next_action': 'Wait for reply, follow up by call in 3 days',
                'follow_up_date': '7_days', 'channel': channel}

    # Default
    message = f"{greeting}, just following up on our conversation. I'd love to show you how Fleek works. I have time Thursday at 2pm or Friday morning, does either work for you?"
    return {'message': message, 'next_action': 'Wait for reply',
            'follow_up_date': '7_days', 'channel': channel}


# ============================================================
# READ TODAY'S LEADS FROM STEP 2
# ============================================================

print("Reading today's prioritised leads...")

try:
    resellers = pd.read_csv('todays_resellers.csv', dtype=str)
    shops = pd.read_csv('todays_shops.csv', dtype=str)
    print(f"  Resellers to message: {len(resellers)}")
    print(f"  Shops to message: {len(shops)}")
except FileNotFoundError:
    print("ERROR: Run prioritise.py first to generate today's leads")
    exit(1)


# ============================================================
# DRAFT MESSAGES FOR RESELLERS
# ============================================================
# Each reseller gets a personalised Instagram DM drafted
# based on their stage, last message and reply classification.

print("\nDrafting Instagram DMs for resellers...")
print("(Using Claude API for personalised messages)")

reseller_messages = []
for idx, row in resellers.iterrows():
    lead_dict = row.to_dict()
    result = draft_message(lead_dict, channel='dm')
    reseller_messages.append({
        'lead_id': row.get('lead_id', ''),
        'handle': row.get('handle', ''),
        'contact_name': row.get('contact_name', ''),
        'stage': row.get('stage', ''),
        'last_inbound_text': row.get('last_inbound_text', ''),
        'reply_type': row.get('reply_type', ''),
        'objection_type': row.get('objection_type', ''),
        'priority_score': row.get('priority_score', ''),
        'why_today': row.get('why_today', ''),
        'drafted_message': result.get('message', ''),
        'next_action': result.get('next_action', ''),
        'follow_up_date': result.get('follow_up_date', ''),
        'channel': 'Instagram DM',
        'lead_type': row.get('lead_type', ''),
        'email': row.get('email', ''),
    })

    # Show progress every 10 leads
    if (idx + 1) % 10 == 0:
        print(f"  Drafted {idx + 1}/{len(resellers)} DMs...")

print(f"  Done — {len(reseller_messages)} DMs drafted")


# ============================================================
# DRAFT MESSAGES FOR SHOPS
# ============================================================
# Each shop gets a personalised email or call note drafted
# based on their stage and last interaction.
# We only draft for shops that need contact today,
# not Won or already booked unless it is a visit reminder.

print("\nDrafting emails and call notes for shops...")

shop_messages = []
for idx, row in shops.iterrows():
    stage = row.get('stage', 'New')

    # Skip Won deals, they are in account management now
    if stage == 'Won':
        continue

    lead_dict = row.to_dict()
    result = draft_message(lead_dict, channel='email')

    shop_messages.append({
        'lead_id': row.get('lead_id', ''),
        'store_name': row.get('store_name', ''),
        'contact_name': row.get('contact_name', ''),
        'email': row.get('email', ''),
        'phone': row.get('phone', ''),
        'city': row.get('city', ''),
        'country': row.get('country', ''),
        'stage': stage,
        'last_inbound_text': row.get('last_inbound_text', ''),
        'recommended_action': row.get('recommended_action', ''),
        'drafted_message': result.get('message', ''),
        'next_action': result.get('next_action', ''),
        'follow_up_date': result.get('follow_up_date', ''),
        'channel': 'Email',
        'est_monthly_spend_gbp': row.get('est_monthly_spend_gbp', ''),
    })

print(f"  Done — {len(shop_messages)} shop messages drafted")


# ============================================================
# COMBINE AND SAVE
# ============================================================
# We save one unified output file with all messages for today.
# The rep reads through this every morning, reviews each
# message, makes any tweaks, and sends.

reseller_df = pd.DataFrame(reseller_messages)
shop_df = pd.DataFrame(shop_messages)

# Add a lead_category column so the rep can filter easily
reseller_df['lead_category'] = 'Online Reseller'
shop_df['lead_category'] = 'Physical Shop'

# Combine resellers first, then shops
all_messages = pd.concat([reseller_df, shop_df], ignore_index=True)

all_messages.to_csv('todays_messages.csv', index=False)

# Summary for the rep
print(f"\n{'='*50}")
print(f"TODAY'S ACTION LIST")
print(f"{'='*50}")
print(f"Instagram DMs to send:     {len(reseller_df)}")
print(f"Emails/calls for shops:    {len(shop_df)}")
print(f"Total actions today:       {len(all_messages)}")
print(f"\nBreakdown by urgency:")

if 'reply_type' in reseller_df.columns:
    hot = len(reseller_df[reseller_df['reply_type'] == 'hot'])
    warm = len(reseller_df[reseller_df['reply_type'] == 'warm'])
    new_leads = len(reseller_df[reseller_df['reply_type'] == 'none'])
    print(f"  Hot replies (act now):     {hot}")
    print(f"  Warm replies (handle):     {warm}")
    print(f"  New leads (first contact): {new_leads}")

print(f"\n✓ Saved todays_messages.csv")
print(f"\nStep 3 complete. Ready for Step 4: Day 2 batch handler.")
