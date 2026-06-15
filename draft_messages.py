"""
FLEEK PIPELINE, STEP 3: MESSAGE DRAFTING
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

BUYING SIGNAL, book a call today with specific times offered
  "yeah keen", "ok sounds good", "when can we talk"
  → Respond immediately, offer two specific times, binary choice

QUESTION, answer it directly then book a call
  "how does payout work", "what brands do you take"
  → Answer the specific question, then offer specific times

MISUNDERSTANDING, clarify then book a call
  "We already sell on Vinted"
  → Clarify Fleek is for sourcing not selling, then book a call

PLATFORM OBJECTION, handle with differentiation then book
  "already on another platform"
  → Most customers use multiple platforms, Fleek has stock
    you cannot get anywhere else. Then offer specific times.

TIMING ISSUE, send content, set reminder, follow up later
  "Too busy this season", "maybe next month"
  → Acknowledge, send info, set follow up reminder

SOFT NO, send content, set 30 day reminder
  "not interested right now"
  → No pressure, send content, check back in 30 days

HARD NO, mark as Lost, no further contact
  "stop messaging me", "remove me from your list"
  → Only these get marked Lost. Nothing else.

THE ONE RULE:
Always end with a specific action. Either a booked call with
real times offered, content sent, or a reminder set.
Never leave a conversation with no next step.

HOW TO RUN:
    python draft_messages.py

INPUT:
    todays_resellers.csv, top 40 resellers from Step 2
    todays_shops.csv    , sequenced shops from Step 2

OUTPUT:
    todays_messages.csv , every lead with a drafted message
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

# ============================================================
# CHANNEL MIGRATION STRATEGY
# ============================================================
# The 40 DM daily cap on Instagram is a hard constraint.
# The goal of every DM is to migrate the conversation to an
# unlimited channel, email or WhatsApp, as fast as possible.
#
# TWO MESSAGE CATEGORIES:
#
# CATEGORY 1, Cold/New/Amber leads (no reply yet)
# Goal: get a response. Hook them with something specific
# about their account. Do NOT ask for WhatsApp or email on
# first touch, looks automated and kills trust.
#
# CATEGORY 2, Hot/Warm replies (active conversations)
# Goal: answer their question directly, then immediately
# migrate the conversation to email or WhatsApp.
#
# IF/ELSE on existing contact data:
# IF email or phone already known → skip migration ask,
#    tell them we proactively sent info to that address.
# ELSE → ask for best email or WhatsApp to send info to.
# ============================================================

SYSTEM_PROMPT = """You are drafting outreach messages for Fleek, a B2B wholesale marketplace for secondhand vintage clothing. Fleek connects resellers and vintage stores with wholesale suppliers globally.

CHANNEL MIGRATION STRATEGY:
The Instagram DM limit is 40 per day. Every message must work toward moving the conversation to email or WhatsApp (unlimited channels) as fast as possible.

CATEGORY 1, Cold outreach (reply_type is new or amber, no previous reply):
- Lead with a high-value hook specific to their account
- Mention something real about their curation, volume or niche
- Do NOT ask for WhatsApp or email on first touch, looks like a bot
- End with a soft question that invites a reply
- Under 60 words, casual, sounds like a real person

CATEGORY 2, Active conversation (reply_type is hot or warm):
- Read their last message carefully
- Answer their specific question directly and completely
- Immediately append channel migration CTA
- IF their email or phone is already known: tell them you have proactively sent the info to that specific address
- ELSE: ask "what is the best email or WhatsApp to send that straight over to?"
- Under 80 words for DMs, under 150 words for emails

COMMERCIAL RULES:

1. BUYING SIGNAL: Answer with enthusiasm. Book call with two specific times OR ask for contact details to send info.
2. QUESTION: Answer it directly and completely. Then migrate to unlimited channel.
3. MISUNDERSTANDING (Vinted): Clarify Fleek is for sourcing not selling. "Fleek is where you source the stock you sell on Vinted."
4. PLATFORM OBJECTION: Handle directly. "Most customers use multiple platforms. Fleek gives you stock you cannot get anywhere else."
5. TIMING: Acknowledge, send content, set specific reminder date.
6. SOFT NO: No pressure. Content sent. 30 day reminder.
7. HARD NO: Return SKIP only.

KEY FLEEK FACTS:
- Everything included in listing price, no hidden fees
- Buy now pay later up to 45 days, no interest
- FleekSort grades every item before delivery
- Exclusive wholesale stock not available elsewhere

TONE:
- DMs: casual, under 80 words, no corporate language, real person
- Emails: professional but warm, personalised opener
- Never: "I hope this finds you well" or "I wanted to reach out"
- Always end with a specific action"""


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
            'message': 'SKIP, hard no, mark as Lost',
            'next_action': 'Mark as Lost, no further contact',
            'follow_up_date': 'never',
            'channel': channel
        }

    # -------------------------------------------------------
    # CONTACT DATA CHECK, IF/ELSE for channel migration
    # -------------------------------------------------------
    # If we already have their email or phone, skip asking
    # for it. Instead tell them we proactively sent the info
    # to that address. Much more impressive than asking.
    existing_email = lead.get('email', '') or ''
    existing_phone = lead.get('phone', '') or ''
    notes = lead.get('notes', '') or ''

    # Extract email from notes if present
    import re
    notes_email = ''
    email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
    if notes:
        matches = re.findall(email_pattern, str(notes))
        if matches:
            notes_email = matches[0]

    known_contact = existing_email or existing_phone or notes_email
    known_contact = str(known_contact).strip()
    has_contact = bool(known_contact and known_contact not in ['nan', ''])

    if has_contact:
        channel_migration = f"contact_known: We already have their details ({known_contact}). Tell them you have proactively sent the wholesale information to that specific address. Do not ask for contact details."
    else:
        channel_migration = "contact_unknown: Ask for their best email or WhatsApp to send wholesale info. Use: 'what is the best email or WhatsApp to drop that straight into?'"

    # Determine message category
    if reply_type in ['hot', 'warm']:
        category = "CATEGORY 2, Active conversation. Answer their question directly, then migrate to unlimited channel."
    else:
        category = "CATEGORY 1, Cold outreach. High-value hook specific to their account. No contact request on first touch."

    # Build the prompt
    if channel == 'dm':
        lead_description = f"Instagram reseller @{handle}"
        if followers:
            lead_description += f" ({int(float(followers)):,} followers)"
        channel_instruction = "Write a casual Instagram DM. Sound like a real person not a corporation."
    else:
        lead_description = f"{store_name} in {city}" if store_name else f"vintage store in {city}"
        channel_instruction = "Write a professional but warm email. Include a subject line on the first line starting with 'Subject:'"

    context = f"""Lead: {lead_description}
Contact name: {name}
Current stage: {stage}
Last message they sent: "{last_message}"
Reply classification: {reply_type}
Message category: {category}
Objection type: {objection_type}
Channel migration instruction: {channel_migration}
Notes about this lead: {notes}
Channel: {channel_instruction}"""

    prompt = f"""{context}

Draft the outreach message following the commercial rules and channel migration strategy exactly.
Also provide:
- next_action: what to do after sending this
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

    # Fallback if API fails, use rule based drafting
    return fallback_draft(lead, channel, stage, reply_type,
                         objection_type, last_message, name,
                         handle, store_name, city)


def fallback_draft(lead, channel, stage, reply_type, objection_type,
                   last_message, name, handle, store_name, city):
    """
    Rule based fallback if the Claude API call fails.
    Implements full channel migration strategy and contact data check.
    """
    display_name = name or handle or store_name or 'there'
    greeting = f"Hey @{handle or display_name}" if channel == 'dm' else f"Hi {display_name}"
    msg = str(last_message).lower() if last_message and str(last_message) != 'nan' else ''

    # -------------------------------------------------------
    # CONTACT DATA CHECK for channel migration
    # -------------------------------------------------------
    existing_email = str(lead.get('email', '') or '').strip()
    existing_phone = str(lead.get('phone', '') or '').strip()
    has_email = existing_email and existing_email not in ['nan', '']
    has_phone = existing_phone and existing_phone not in ['nan', '']

    if has_email:
        migration_line = f"I'll get that sent straight over to {existing_email} now."
        has_contact = True
    elif has_phone:
        migration_line = f"I'll drop that straight into WhatsApp on {existing_phone} now."
        has_contact = True
    else:
        migration_line = "What's the best email or WhatsApp to send that straight over to?"
        has_contact = False

    # -------------------------------------------------------
    # CATEGORY 1, Cold outreach (new or amber, no reply yet)
    # High value hook. No contact request on first touch.
    # -------------------------------------------------------
    if reply_type in ['new', 'amber', 'none']:
        if channel == 'dm':
            notes = str(lead.get('notes', '') or '').lower()
            if 'menswear' in notes:
                hook = "love your menswear curation"
            elif 'high engagement' in notes:
                hook = "love the engagement your drops are getting"
            elif 'big consignment' in notes:
                hook = "love the volume you are moving"
            else:
                hook = "love what you are doing with your page"
            message = f"{greeting}, {hook}. We work with resellers like you to make sourcing vintage wholesale easier, graded stock, no market trips, exclusive drops you cannot get elsewhere. Worth a quick look?"
            return {'message': message, 'next_action': 'Wait for reply, follow up in 7 days',
                    'follow_up_date': '7_days', 'channel': channel}
        else:
            subject = f"Subject: Wholesale sourcing for {store_name or city}"
            message = f"{subject}\n\n{greeting},\n\nI came across {store_name or 'your store'} in {city} and wanted to reach out. We work with independent vintage stores to replace manual sourcing with a digital wholesale marketplace. Graded stock, FleekSort categorised, no market trips.\n\nWorth a quick call? I have time Thursday at 2pm or Friday morning.\n\nAaron"
            return {'message': message, 'next_action': 'Follow up by call in 3 days',
                    'follow_up_date': '7_days', 'channel': channel}

    # -------------------------------------------------------
    # CATEGORY 2, Active conversations (hot or warm replies)
    # Answer their question, then migrate to unlimited channel.
    # -------------------------------------------------------

    # Hard no
    if reply_type == 'cold':
        return {'message': 'SKIP, hard no, mark as Lost',
                'next_action': 'Mark as Lost, no further contact',
                'follow_up_date': 'never', 'channel': channel}

    # Payout or commission question
    if 'payout' in msg or 'commission' in msg or 'fee structure' in msg:
        if has_contact:
            message = f"{greeting}, great question, everything is included in the listing price, no hidden fees, BNPL up to 45 days with no interest. {migration_line}"
        else:
            message = f"{greeting}, great question, everything is included in the listing price, no hidden fees, BNPL up to 45 days no interest. {migration_line}"
        return {'message': message, 'next_action': 'Send price sheet to contact details',
                'follow_up_date': 'today', 'channel': channel}

    # EU shipping question
    if 'ship' in msg or 'eu' in msg:
        if has_contact:
            message = f"{greeting}, yes we ship to EU, duties and taxes all included in the listing price, no surprises on delivery. Would love to walk you through more on a quick call, would you have 10 minutes this week? I can send the full shipping breakdown to {existing_email or existing_phone} beforehand."
        else:
            message = f"{greeting}, yes we ship to EU, duties and taxes all included in the listing price, no surprises on delivery. Would love to walk you through more on a quick call, would you have 10 minutes this week?"
        return {'message': message, 'next_action': 'Book a call, EU shipping answered',
                'follow_up_date': 'today', 'channel': channel}

    # Brands question
    if 'brand' in msg or 'menswear' in msg:
        if has_contact:
            message = f"{greeting}, we carry Ralph Lauren, Carhartt, Nike, Levi's, Adidas and more. FleekSort grades everything before delivery. Sending the full catalogue to {existing_email or existing_phone} now."
        else:
            message = f"{greeting}, we carry Ralph Lauren, Carhartt, Nike, Levi's and more. FleekSort grades every item before delivery. {migration_line}"
        return {'message': message, 'next_action': 'Send catalogue',
                'follow_up_date': 'today', 'channel': channel}

    # Bundle or catalogue request
    if 'bundle' in msg or 'catalogue' in msg or 'send me' in msg:
        if has_contact:
            message = f"{greeting}, on it, sending the bundle list and wholesale catalogue straight to {existing_email or existing_phone} now."
        else:
            message = f"{greeting}, absolutely. {migration_line} I'll get the bundle list sent straight over."
        return {'message': message, 'next_action': 'Send bundle list',
                'follow_up_date': 'today', 'channel': channel}

    # Buying signal
    if reply_type == 'hot':
        if has_contact:
            message = f"{greeting}, great to hear it. Getting our wholesale info sent straight to {existing_email or existing_phone} now, take a look and let me know when works for a call."
        else:
            message = f"{greeting}, great to hear it. {migration_line} Once you have got our info I can walk you through the rest on a call, Thursday at 2pm or Friday morning work?"
        return {'message': message, 'next_action': 'Send info, book call',
                'follow_up_date': 'today', 'channel': channel}

    # Misunderstanding, Vinted
    if 'vinted' in msg or 'sell on' in msg:
        message = f"{greeting}, great to hear you are on Vinted, Fleek is actually the other side of that. It is where you source the stock you sell on Vinted. Most of our sellers use both. {migration_line}"
        return {'message': message, 'next_action': 'Send info, clarification sent',
                'follow_up_date': 'today', 'channel': channel}

    # Platform objection
    if 'another platform' in msg or 'already on' in msg:
        message = f"{greeting}, totally get that. Where Fleek stands apart is the stock itself, graded vintage wholesale you cannot source anywhere else, with FleekSort categorising every item before it arrives. Would love to show you what is coming through. Would you have a quick 10 minutes for a call this week?"
        return {'message': message, 'next_action': 'Book a call, objection handled with differentiation',
                'follow_up_date': 'today', 'channel': channel}

    # Timing objection
    if any(phrase in msg for phrase in ['busy', 'next month', 'try later', 'back next week', 'slow season']):
        message = f"{greeting}, completely understand, no pressure. I will send over some info so you have it when the time is right. I will check back in with you in a few weeks."
        return {'message': message, 'next_action': 'Send content, set 30 day reminder',
                'follow_up_date': '30_days', 'channel': channel}

    # Not taking on new channels
    if 'not taking on' in msg or 'not interested right now' in msg:
        message = f"{greeting}, no problem at all. I will send over some info in case it is useful down the line. I will check back in with you in a few weeks."
        return {'message': message, 'next_action': 'Send content, set 30 day reminder',
                'follow_up_date': '30_days', 'channel': channel}

    # Hold stage, recovered from Lost, re-engagement
    if stage == 'Hold':
        message = f"{greeting}, following up as promised. I wanted to send over some info about Fleek in case the timing is better now. {migration_line}"
        return {'message': message, 'next_action': 'Send info, 14 day reminder',
                'follow_up_date': '14_days', 'channel': channel}

    # Default warm follow up
    message = f"{greeting}, just following up. {migration_line} Happy to walk you through everything on a quick call, Thursday at 2pm or Friday morning?"
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

print(f"  Done, {len(reseller_messages)} DMs drafted")


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

print(f"  Done, {len(shop_messages)} shop messages drafted")


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
