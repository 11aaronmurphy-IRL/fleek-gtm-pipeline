# Fleek GTM Acquisition Pipeline

A working sales pipeline tool built for the Fleek GTM Acquisition case study.

Built by Aaron Murphy — June 2026

---

## What This Tool Does

Takes a messy inherited pipeline of 265 leads and turns it into a daily action list. It cleans the data, splits leads into two channels, prioritises who to contact today, drafts the actual outreach messages, and handles new leads coming in the next day without ever messaging the same person twice.

The tool runs every morning. Drop in the pipeline, run four scripts, get today's action list.

---

## How To Run It

**Requirements**
```
pip install pandas openpyxl
```

**Step 1 — Clean the pipeline (run once on day 1)**
```
python clean_pipeline.py
```
Reads the raw Excel file, cleans the mess, classifies lead types, outputs pipeline_clean.csv

**Step 2 — Prioritise leads**
```
python prioritise.py
```
Scores resellers, picks the top 40 for today's DMs, sequences shops by city and stage

**Step 3 — Draft messages**
```
python draft_messages.py
```
Writes a personalised DM or email for every lead based on their stage and last reply

**Step 4 — Handle new leads (run when a new batch arrives)**
```
python batch_handler.py
```
Checks new leads against the existing pipeline, flags duplicates, adds genuinely new ones

---

## What Each File Does

| File | What it does |
|------|-------------|
| clean_pipeline.py | Reads raw Excel, cleans handles, stages, dates, spend figures, removes duplicates, classifies lead type |
| prioritise.py | Scores resellers on 7 signals, picks top 40 for today, sequences shops by city |
| draft_messages.py | Drafts personalised DMs for resellers and emails for shops using Claude API |
| batch_handler.py | Handles new lead batches, exhaustive duplicate checking, flags not silently drops |

---

## How The System Fits Together

```
RAW EXCEL FILE
      |
      v
clean_pipeline.py
  - Reads pipeline tab only (day 2 handled separately)
  - Normalises handles, stages, dates, spend
  - Flags broken emails, removes duplicates
  - Classifies: reseller / reseller_with_email / physical_shop
      |
      v
pipeline_clean.csv  (265 leads → 252 after deduplication)
      |
      |-----> prioritise.py
      |         - Classifies replies: hot / warm / cold
      |         - Scores on 7 signals (reply type, spend,
      |           velocity, followers, listings, combined revenue)
      |         - Outputs top 40 resellers for today
      |         - Sequences shops by city and stage
      |
      |-----> draft_messages.py
      |         - Reads today's prioritised leads
      |         - Uses Claude API to draft personalised messages
      |         - Aaron's commercial logic baked in:
      |           hot reply = book call with specific times
      |           objection = handle it, never give up
      |           soft no = send content, set reminder
      |         - Outputs todays_messages.csv
      |
NEW LEADS (next day)
      |
      v
batch_handler.py
  - Checks 5 ways for duplicates:
    lead_id / handle / email / phone / store+city
  - Flags duplicates with reason (never silent)
  - Adds genuine new leads to pipeline_clean.csv
  - Run prioritise.py and draft_messages.py again
```

---

## The Two Channels

**Online Resellers (~60% of pipeline)**
Found on Instagram, Depop, Whatnot, eBay and Vinted. Usually only have a handle, no email or phone. Contacted via Instagram DM only. Rate limited to 40 DMs per day so prioritisation matters.

Prioritisation scoring (7 signals):
1. Reply type — hot buying signal (50 pts), warm objection (25 pts)
2. Estimated monthly spend (up to 30 pts)
3. Sales velocity — items sold in 30 days (up to 20 pts)
4. Followers (up to 10 pts)
5. Active listings (up to 5 pts)
6. Combined revenue — avg price × velocity (up to 15 pts)
7. Objection type — platform, timing, misunderstanding handled differently

**Physical Shops (~40% of pipeline)**
Have email, phone and city. Contacted by email first, then call, then in-person visit. Grouped by city for efficient visit planning. UK shops prioritised for visits, international shops get email and call only.

---

## Duplicate Detection

The batch handler checks five ways a duplicate could appear:

1. Same lead_id
2. Same Instagram handle (normalised — strips @, URL prefix, lowercased)
3. Same email (including broken emails like ines@@hotmail.com)
4. Same phone number (normalised — strips country codes and formatting)
5. Same store name + city combination

Nothing is ever silently dropped. Every flagged duplicate is logged to duplicates_flagged.csv with the exact reason.

---

## How AI Was Used

**Claude was used throughout this build.** Here is an honest account:

- **Data analysis:** Claude read the raw Excel file and identified all the cleaning problems — inconsistent handles, 8 different stage name formats, mixed date formats, broken emails, duplicates
- **Code generation:** Every Python script was written by Claude based on requirements I described. I described the commercial logic, Claude wrote the implementation
- **Commercial logic:** The reply classification, the prioritisation scoring, the message drafting rules — I defined the logic based on sales judgment, Claude translated it into code
- **Message drafting:** The Claude API is called at runtime to write personalised messages for each lead using the commercial rules baked into the system prompt
- **Testing and iteration:** I tested each script, spotted issues (like Step 1 incorrectly combining both tabs), described the problem to Claude, Claude fixed it

What I brought: commercial thinking, understanding of the ICP, judgment on what good outreach looks like, spotting gaps in the logic during testing.

What Claude brought: speed of implementation, ability to process messy data programmatically, consistent application of rules at scale.

---

## Scaling To 30,000 Leads

The tool handles scale because:

- pandas processes CSV row by row efficiently, same code runs on 265 or 30,000 leads
- Duplicate checking uses Python sets (O(1) lookup) not loops, stays fast at any size
- The 40 DM daily limit means the tool always outputs exactly 40 regardless of pipeline size
- The batch handler only processes new leads, not the whole pipeline every time
- Message drafting calls the Claude API per lead — at 30,000 leads this would be batched or run overnight

---

## Files In This Repo

```
clean_pipeline.py      — Step 1: Data cleaning
prioritise.py          — Step 2: Lead prioritisation  
draft_messages.py      — Step 3: Message drafting
batch_handler.py       — Step 4: New lead batch handling
README.md              — This file
```

Input file (not in repo — bring your own):
```
Fleek_-_Acquisition_Case_Study_-_Pipeline_Data.xlsx
```# fleek-gtm-pipeline
