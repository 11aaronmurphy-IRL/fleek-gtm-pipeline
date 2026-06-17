# Fleek GTM Acquisition Pipeline

Built by Aaron Murphy — June 2026

---

## What This Tool Does

This tool takes a messy inherited pipeline of 265 leads and turns it into a daily action list that an agent can run every morning without human intervention.

The pipeline contains two completely different types of buyer that need completely different approaches:

**Channel 1 — Online Resellers (roughly 60% of the pipeline)**
These are individual sellers on Instagram, Depop, Vinted, TikTok and eBay. They usually have no email address and no phone number. The only way to reach them is via Instagram DM. Instagram rate-limits accounts to around 40 DMs per day — any more and the account gets flagged or banned. This means choosing who to message today actually matters. You cannot just blast everyone.

**Channel 2 — Physical Shops (roughly 40% of the pipeline)**
These are independent vintage stores with a registered address, an email, a phone number and a city. They can be emailed, called and visited in person. Unlike resellers there is no daily limit, so the tool sequences them by commercial priority and groups them by city so a rep can plan an efficient day of visits.

**Channel 3 — Hybrid (physical shop with an online following)**
A shop can have both a registered address AND an active Instagram presence. These get treated as a physical shop for visits and emails — they already have a proper contact method, so they do not compete for one of the 40 limited DM slots. The classification simply recognises that double-reach exists, it does not change the contact priority.

The tool determines lead type from the actual data in the row, not from any label a BDR typed in:
```
Has followers/velocity data AND city/store name AND a handle  → hybrid
Has followers/velocity data only                               → reseller
Has followers/velocity data AND an email                        → reseller_with_email
Has city/store name, no follower or velocity data               → physical_shop
```

The tool handles all three categories automatically, applies different logic to each, and produces a single daily action list every morning.

---

## Your Morning Routine — How To Use This Every Day

**Day 1 only (first time setup):**
```
pip3 install pandas openpyxl
```

**Every morning — run in this order:**

**Step 1: Clean the pipeline**
```
python3 clean_pipeline.py
```
Run this once on day 1. It reads the raw Excel file, cleans all the mess, and produces pipeline_clean.csv. You do not need to run this again unless the base pipeline changes.

**Step 2: Prioritise today's leads**
```
python3 prioritise.py
```
Reads pipeline_clean.csv. Scores every reseller, picks the top 40 for today's DMs. Sequences all physical shops by city and stage. Outputs todays_resellers.csv and todays_shops.csv.

**Step 3: Draft today's messages**
```
python3 draft_messages.py
```
Reads today's prioritised leads. Drafts a personalised message for every single lead based on their stage, their last reply, and your commercial logic. Outputs todays_messages.csv.

**Step 4: Open todays_messages.csv and send**
Every message is drafted and ready. Read each one, tweak if needed, and send. Instead of spending 2 hours writing messages you spend 20 minutes reviewing and sending.

**If new leads arrived overnight:**
```
python3 batch_handler.py
```
Run this before prioritise.py. It checks the new leads against everyone already in the pipeline, flags any duplicates, adds genuinely new leads, and updates pipeline_clean.csv and the permanent raw_master_pipeline.csv base file. Then run prioritise.py and draft_messages.py as normal.

**Step 5: Decide where to visit next week**
```
python3 city_proposer.py
```
Reads pipeline_clean.csv. Scores every UK city by pipeline value and stage priority, recommends the single best city to visit this week, and produces the full visit order for every shop in that city. Outputs city_rankings.csv, todays_visit_plan.csv, regional_hubs.csv and visits_today.csv.

---

## What Each File Does

| File | What it does | Output |
|------|-------------|--------|
| clean_pipeline.py | Reads raw Excel, cleans everything, classifies lead types, applies geographic sanitisation | pipeline_clean.csv |
| prioritise.py | Scores resellers, picks top 40 with meeting confirmations first, sequences shops | todays_resellers.csv, todays_shops.csv |
| draft_messages.py | Drafts personalised messages for every lead, including time-locking messages for Meeting Booked | todays_messages.csv |
| batch_handler.py | Handles new lead batches, exhaustive duplicate checking | raw_master_pipeline.csv, pipeline_clean.csv (updated), duplicates_flagged.csv |
| city_proposer.py | Scores UK cities by pipeline value, recommends weekly visit city and order | city_rankings.csv, todays_visit_plan.csv, visits_today.csv |

---

## How The System Fits Together

```
RAW EXCEL FILE (messy: 265 leads across pipeline tab)
      |
      v
clean_pipeline.py
  - Reads from raw_master_pipeline.csv if it exists, otherwise the Excel pipeline tab
  - Normalises handles: @SepiaCollective → sepiacollective
  - Standardises stages: "contaced", "Contacted", "contacted" → Contacted
  - Fixes dates: Dec 29, 04/12/2025, 2025-12-29 → 2025-12-29
  - Cleans spend: £9,000 or "9000" or "£9000" → 9000.0
  - Flags broken emails: ines@@hotmail.com → INVALID: flagged, not deleted
  - Geographic sanitisation: .co.uk email or UK city keyword in store
    name forces country to UK, flags any remaining +1 phone mismatch
  - Removes duplicates: five-way check, never silently dropped
  - Stage reconciliation: last message always beats the stage label.
    Lost only happens on a genuine hard no, or silence after enough
    real attempts. Won is scrutinised the same way — a Won label with
    no message, low touches and low spend moves to Hold instead of
    being trusted blindly.
  - Classifies lead type based on actual data not the label:
      has followers/velocity + city/store + handle = hybrid
      has followers/velocity data only = reseller
      has email + followers = reseller_with_email  
      has city/store name, no metrics = physical_shop
      |
      v
pipeline_clean.csv (clean, classified, ready)
      |
      |-----> prioritise.py
      |         RESELLERS:
      |         - STEP ZERO: Meeting Booked leads with no email (handle
      |           only) take absolute top priority, above even hot
      |           replies. A confirmed meeting stuck waiting on a time
      |           is more urgent than a fresh hot conversation.
      |         - Reads last message from each replied lead
      |         - Classifies reply as hot / warm / amber / new
      |         - Scores all active resellers on commercial signals
      |         - Picks top 40 for today's DMs
      |         - Remaining resellers wait for tomorrow
      |
      |         PHYSICAL SHOPS (and hybrid shops):
      |         - Sorts by stage priority (Meeting Booked first)
      |         - Then by monthly spend within each stage
      |         - Groups by city for visit planning
      |         - UK shops: email → call → visit
      |         - International shops: email and call only
      |
      |-----> draft_messages.py
      |         - For each of today's 40 resellers:
      |           reads last message, applies commercial logic,
      |           writes personalised Instagram DM. Meeting Booked
      |           leads get a message focused on locking in the
      |           exact day and time, not a generic reply.
      |         - For each shop:
      |           writes personalised email with subject line
      |           and clear call to action. Same time-locking
      |           logic applies for Meeting Booked shops.
      |         - Outputs one unified daily action list
      |
NEW LEADS (day 2 batch arrives)
      |
      v
batch_handler.py
  - Checks 5 ways for duplicates (see Duplicate Detection below)
  - Flags duplicates to duplicates_flagged.csv with exact reason
  - Adds genuinely new leads to raw_master_pipeline.csv (the
    permanent base, appended to, never overwritten)
  - Updates pipeline_clean.csv so today's run includes them
  - Run prioritise.py and draft_messages.py again for updated list
      |
      v
city_proposer.py
  - Scores every UK city: confirmed meetings ×3.0, Negotiating ×2.5,
    Replied Hot ×2.0, Replied Warm ×1.5, Contacted ×1.0, New £5k+ ×0.8
  - Recommends the single highest-value city to visit this week
  - Produces the full visit order for every shop in that city
  - visits_today.csv starts empty every morning — only fills once a
    rep manually confirms a specific appointment time
```

---

## How Resellers Are Scored — The Priority Scoring System

With only 40 DMs available per day from 150+ active resellers, the tool cannot just message everyone. It needs to decide who gets a DM today and who waits until tomorrow.

**Step Zero comes before any scoring at all.**

Any reseller in Meeting Booked with no email on file — meaning the only way to reach them is Instagram — takes the absolute top slots, above even hot replies. This is not just interest, it is an almost closed appointment stuck waiting purely on logistics. Locking in the exact day and time matters more than starting a fresh hot conversation, so these go out first regardless of spend.

If a Meeting Booked lead does have an email, the confirmation goes by email instead and never touches the 40 DM limit at all — it is handled entirely on the shop sequencer side.

After Step Zero, everyone remaining is given a priority score out of 130. The 40 resellers with the highest scores (after Step Zero slots are filled) get a DM today. Everyone else waits.

The score is built from seven signals. Each signal comes from a specific column in the pipeline data. Here is exactly what each signal is, where it comes from, and why it matters:

---

### Signal 1: Reply type — up to 50 points

**Where it comes from:** The `last_inbound_text` column in the pipeline. This is the last message the reseller sent to Fleek.

**Why it matters:** A conversation that has already started is always easier to close than a cold outreach. Someone who replied "yeah keen" three weeks ago and never got a follow up is the lowest hanging fruit in the entire pipeline. They already showed interest. The conversation just died because nobody followed up. Getting that conversation moving again takes priority over everything else.

**How the tool reads it:** The tool does not just check whether there is a message. It reads what the message actually says and classifies it into one of four categories:

**HOT = 50 points**
The reseller sent a genuine buying signal or asked a specific question. This means they are already interested and need a response today. Not tomorrow. Today.

Real examples from this pipeline:
- "how does payout work" — they are already thinking about placing an order
- "ok sounds good when can we talk" — they said yes without even being asked directly
- "do you take menswear too" — they are asking about specific stock
- "yeah keen" — buying signal, act immediately
- "can we do a call this week" — they want to talk, book it

**WARM = 25 points**
The reseller replied but with an objection or a timing issue. This does NOT mean they are dead. It means they need a specific response that handles what they said. Nothing is dead unless they say a hard no. See Message Drafting below for exactly how each objection type is handled.

Real examples from this pipeline:
- "not interested right now" — soft no, follow up in 30 days, send content
- "already on another platform tbh" — objection, handle it directly
- "We already sell on Vinted" — misunderstanding, clarify what Fleek actually is
- "Too busy this season, try later" — timing issue, follow up in 6 weeks
- "Owner is back next week, call then" — scheduling, call back next week

**COLD = 0 points, removed from list entirely**
An explicit hard rejection. These are the only replies that result in a lead being marked Lost.

Examples:
- "stop messaging me"
- "remove me from your list"
- "definitely not for us"

**NO REPLY YET = 0 reply points**
The reseller has never responded. They still get scored on the five commercial signals below. A brand new reseller with £9,000 monthly spend and 200 sales per month will still score high enough to break into the top 40.

---

### Signal 2: Estimated monthly spend — up to 30 points

**Where it comes from:** The `est_monthly_spend_gbp` column. This is a rough estimate of how much the reseller spends on wholesale stock per month, scraped from their selling activity.

**Why it matters:** This is the most direct indicator of commercial value. A reseller spending £9,000 a month on stock is worth ten times more to Fleek than one spending £900. Higher spend means a bigger recurring order once they convert.

**How it scores:**
- £9,000/month (highest in this dataset) → 30 points
- £4,500/month → 15 points
- £900/month → 3 points

The score scales proportionally. The tool divides the reseller's spend by the maximum spend in the dataset and multiplies by 30.

---

### Signal 3: Sales velocity — up to 20 points

**Where it comes from:** The `sales_velocity_30d` column. This is how many items the reseller sold in the last 30 days across all platforms.

**Why it matters:** Fast sellers run out of stock faster. A reseller selling 200 items a month needs to restock constantly. That means they need a reliable wholesale supplier urgently. A reseller selling 10 items a month can wait. Sales velocity is a measure of how urgently they need Fleek right now.

**How it scores:**
- 213 items/30 days (highest in this dataset) → 20 points
- 100 items/30 days → 9 points
- 30 items/30 days → 3 points

---

### Signal 4: Followers — up to 10 points

**Where it comes from:** The `followers` column. Total Instagram followers.

**Why it matters:** Follower count is a proxy for the size of the operation. A reseller with 60,000 followers is running a serious business. They drop new stock regularly, have a loyal customer base that sells out quickly, and need a consistent supply. A reseller with 500 followers is likely casual. Follower count alone does not tell the full story — which is why combined revenue was added as Signal 6 — but it is a useful secondary indicator.

**How it scores:**
- 65,000 followers → 10 points
- 30,000 followers → 5 points
- 5,000 followers → 1 point

---

### Signal 5: Active listings — up to 5 points

**Where it comes from:** The `active_listings` column. How many items the reseller currently has listed for sale right now.

**Why it matters:** More active listings means they are running a high volume operation with a lot of stock in motion at any given time. This signals consistent sourcing behaviour and recurring wholesale need. This signal carries the least weight (only 5 points maximum) because it is the least reliable indicator on its own — a reseller could have many listings but slow sales.

---

### Signal 6: Combined monthly revenue — up to 15 points

**Where it comes from:** Calculated from `avg_listing_price_gbp` multiplied by `sales_velocity_30d`. Neither column alone tells the full story.

**Why it matters:** This signal was added after noticing a problem with scoring by volume alone. Two resellers with the same sales velocity can have completely different commercial value:

- Reseller A: 200 sales per month at £8 average = £1,600 monthly revenue
- Reseller B: 50 sales per month at £65 average = £3,250 monthly revenue

Reseller B is worth twice as much to Fleek despite selling four times fewer items. They are buying higher quality graded stock, they are less price sensitive, and they are more likely to place premium orders. Scoring by velocity alone would rank Reseller A higher, which is the wrong commercial call.

Combined revenue = avg_listing_price_gbp × sales_velocity_30d

This rewards quality sellers, not just high volume sellers.

---

### Signal 7: Objection type — adjusts the message, not the score

**Where it comes from:** Also read from `last_inbound_text`, same as Signal 1.

**Why it matters:** Not all warm replies need the same response. Someone who said "We already sell on Vinted" needs a completely different message to someone who said "Too busy this season." The tool detects five types of objection and routes each one to a different message template:

- **Platform objection** ("already on another platform") → handle differentiation
- **Misunderstanding** ("We already sell on Vinted") → clarify Fleek is for sourcing not selling
- **Timing** ("busy this season", "next month") → acknowledge, send content, set reminder
- **Soft no** ("not interested right now") → send content, set 30-day reminder
- **Undecided** ("need to think about it") → follow up in 7 days

This does not change the priority score. It changes the message that gets drafted.

---

### Full worked example from the actual pipeline

**@tonicstitchthreads — scored as #1 priority**

| Signal | Data | Points |
|--------|------|--------|
| Reply type | "do you take menswear too" = HOT | +50 |
| Monthly spend | £9,000/month | +30 |
| Sales velocity | 189 items sold in 30 days | +18 |
| Followers | 46,640 | +7 |
| Active listings | 559 listings | +5 |
| Combined revenue | 189 × £30 avg = £5,670/month | +12 |
| **Total** | | **122 points** |

They get DM #1 today. The tool drafted:
"Hey @tonicstitchthreads — yes, we have a strong menswear range coming through regularly — Ralph Lauren, Carhartt, Levi's. I'd love to show you what's available. I have time Thursday at 2pm or Friday morning, does either work?"

---

### How the scoring handles 30,000 leads

At 30,000 leads the majority will have no reply history because they have never been contacted. The tool handles this automatically.

For leads with no reply history, the score is built entirely from Signals 2 through 6 — spend, velocity, followers, listings and combined revenue. These signals work just as well for a brand new lead as for one that has been in the pipeline for months.

A brand new reseller with £9,000 monthly spend and 200 sales per month scores approximately 78 points from commercial signals alone. That is high enough to break into the top 40 every single day until they are contacted and reply.

Once they reply, their reply type gets added to the score. A hot reply pushes them to 128 points — the very top of the list. A warm reply gives them 103 points — still high priority. No reply yet means they keep scoring on commercial metrics alone until they do respond.

The 40 DM daily limit means the tool always outputs exactly 40 regardless of pipeline size. The code does not change. The infrastructure does not change. pandas processes 30,000 rows as efficiently as 265.

---

## How Messages Are Drafted

### The commercial logic behind every message

Aaron's rule: **nothing is dead unless they say a hard no.**

Every reply type gets a specific response. The tool never leaves a conversation hanging with no next step.

**Rule 1: Buying signal → book a call with two specific times**

Never ask "want me to tell you more?" — that is a question that can be answered with no. Always offer two specific times and ask them to pick one.

Example:
- They said: "how does payout work"
- Tool drafts: "Hey @cindersupply — on Fleek everything is included in the listing price, no hidden fees, and we offer buy now pay later up to 45 days with no interest. I'd love to walk you through your first order. I have time Thursday at 2pm or Friday morning, does either work?"

**Rule 2: Question → answer it directly, then book a call**

Example:
- They said: "do you take menswear too"
- Tool drafts: "Hey @tonicstitchthreads — yes, we have a strong menswear range coming through regularly — Ralph Lauren, Carhartt, Levi's. I'd love to show you what's available. I have time Thursday at 2pm or Friday morning, does either work?"

**Rule 3: Misunderstanding → clarify, then book a call**

The most common misunderstanding: sellers think Fleek is a selling platform like Vinted. It is not. Fleek is a wholesale sourcing tool — they buy stock through Fleek to sell elsewhere.

Example:
- They said: "We already sell on Vinted"
- Tool drafts: "Hey @loomthriftfinds — great to hear you're on Vinted! Fleek is actually the other side of that — it's where you source the stock you sell on Vinted. Most of our sellers use both. I'd love to show you how it works. I have time Thursday or Friday morning, does either work?"

**Rule 4: Platform objection → handle with differentiation, then book**

Example:
- They said: "already on another platform tbh"
- Tool drafts: "Hey @emberretrovintage — totally get that. Most of our best customers were already on other platforms when they joined. Fleek gives you access to stock you simply can't get anywhere else. I have time Thursday or Friday morning, does either work?"

**Rule 5: Timing issue → acknowledge, send content, set 30-day reminder**

Example:
- They said: "Too busy this season, try later"
- Tool drafts: "Hey @relicvintage — completely understand, no pressure at all. I'll send over some info so you have it when the time is right. I'll check back in with you in a few weeks."

**Rule 6: Soft no → send content, set 30-day reminder**

Example:
- They said: "not interested right now"
- Tool drafts: "Hey @hazelfaded__ — no problem at all. I'll send over some info in case it's useful down the line. I'll check back in with you in a few weeks."

**Rule 7: Hard no → mark as Lost, no further contact**

Only "stop messaging me" or "remove me from your list" or similar explicit rejections get marked Lost. Everything else is a follow up.

---

## Duplicate Detection — Exhaustive 5-Way Checking

Every new lead that arrives is checked five different ways before being added to the pipeline. Nothing is ever silently dropped — every flagged duplicate is logged to duplicates_flagged.csv with the exact reason so it can be reviewed.

**Check 1: Same lead_id**
The most basic check. If the same ID appears twice, flag the second one.

**Check 2: Same Instagram handle (normalised)**
@SepiaCollective, instagram.com/sepiacollective and sepiacollective are all the same person. The tool strips the @ symbol, strips the URL prefix, and lowercases everything before comparing. This catches duplicates that would be missed by a simple text match.

Real example caught in testing: L0295 @heritagefinds in the day 2 batch was a duplicate of L0130 @heritagefinds in the main pipeline. Different lead IDs, same person. A lead-ID-only check would have missed this entirely.

**Check 3: Same email (including broken emails)**
ines@@hotmail.com is a broken version of ines@hotmail.com. The tool fixes the double @ before comparing so a typo does not allow a duplicate through.

**Check 4: Same phone number (normalised)**
The pipeline contains UK and international numbers across multiple formats. The same number can appear as:
- UK: +44 7737 683411, 0044 7737683411, 07737683411
- France: +33 489 6004150, 0033 489 6004150
- Germany: +49 813 5200091
- Netherlands: +31 192 5081201
- US: +1 878 3983612

The tool strips all non-numeric characters and normalises country code prefixes before comparing. +44 7737 683411 and 07737683411 become the same string. +33 489 6004150 and 0033489604150 become the same string. A formatting difference in how a BDR entered the number does not allow a duplicate through.

**Check 5: Same store name + city**
The same shop can be entered twice by different BDRs with different contact names. A store called Rusty Wardrobe in Manchester entered by Maya and again by Tomas with a different email would pass all four checks above but get caught by this one.

**What happens when a duplicate is found:**
- It is NOT added to the pipeline
- It is logged to duplicates_flagged.csv with the lead_id, the identifier that matched, and the exact reason
- The log is reviewed every morning before outreach begins

---

## Scaling To 30,000 Leads

The tool is built to scale without any changes to the code or workflow.

- **pandas** processes CSV row by row efficiently. The same scripts that handle 265 leads handle 30,000 identically.
- **Duplicate checking uses Python sets** (O(1) lookup time). Checking 30,000 leads takes the same fraction of a second as checking 265.
- **The 40 DM daily limit** means the tool always outputs exactly 40 regardless of pipeline size. The prioritisation logic handles the queue automatically.
- **The batch handler** only processes new leads, not the whole pipeline every time. At 30,000 leads a daily batch of 50 new leads gets processed in seconds.
- **Message drafting** calls the Claude API per lead. At 30,000 leads this would be run as an overnight batch rather than in real time, using Anthropic's batch API for cost efficiency.

---

## How AI Was Used

Claude was used throughout this entire build. Here is an honest account:

**What Claude did:**
- Read and analysed the raw Excel file before any code was written
- Identified all the data quality problems: inconsistent handles, 8 different stage name formats, mixed date formats, broken emails, duplicates across 5 different dimensions
- Wrote every Python script based on requirements I described
- Built the message drafting logic using the commercial rules I defined
- Wrote the Claude API integration that classifies reply types at runtime
- Fixed bugs when they appeared during testing

**What I did:**

Before writing a single line of code I spent time reading the raw data myself. The Readme told me what the columns were supposed to be. The actual data told me what they really looked like. There was a significant gap between the two. I made a deliberate decision to understand the problem before building the solution.

Specific commercial decisions I made and why:

**Defined the reply classification logic from sales experience, not guesswork.**
The initial approach was to mark anything without a recent reply as low priority. I pushed back on this. A lead that replied "when can we talk" three weeks ago and never got a follow up is not low priority — it is the highest priority lead in the pipeline. Someone already showed interest and the conversation died because nobody followed up. I designed the hot/warm/cold classification to surface these first.

**Insisted that nothing is dead unless they say a hard no.**
The first version of the tool was marking "not interested right now" as Lost. I changed this. "Not interested right now" is a 30-day follow up with content sent. "Too busy this season" is a 6-week follow up. "Already on another platform" is an objection to handle, not a rejection to accept. I defined every objection type and exactly what to do with each one based on how I would handle it on a real sales call.

**Spotted the Vinted misunderstanding pattern from reading the actual data.**
While going through the pipeline manually I noticed several resellers had replied "We already sell on Vinted" or similar. They thought Fleek was a competitor to Vinted — a selling platform. It is not. Fleek is a wholesale sourcing tool. This is a misunderstanding not a rejection, and it needs a completely different response to a platform objection. I designed the specific clarification message: "Fleek is actually the other side of that — it's where you source the stock you sell on Vinted."

**Added combined revenue after noticing velocity alone rewarded the wrong sellers.**
The initial scoring ranked sellers by sales volume. I noticed this would rank a reseller selling 200 items at £8 each higher than one selling 50 items at £65 each, even though the second reseller is worth twice as much commercially. I added the combined revenue signal to correct this. Average listing price multiplied by sales velocity gives a better proxy for actual monthly turnover.

**Insisted on flagging duplicates rather than silently dropping them.**
The first version of the batch handler silently skipped duplicates. I changed this. Never silently drop data. Every flagged duplicate gets logged with the exact reason — which check caught it, which lead ID it matched, and why it was not added. That way nothing is ever lost without a trace.

**Spotted that Step 1 was incorrectly combining both Excel tabs.**
During testing I noticed the batch handler was reporting all 30 day-2 leads as already in the pipeline. I investigated and found that Step 1 was reading both tabs and combining them, which meant by the time the batch handler ran there was nothing new to find. I redesigned Step 1 to only read the pipeline tab and leave the day-2 tab exclusively for the batch handler. This is the correct architecture — day 1 you process the pipeline, day 2 new leads arrive and get checked properly.

**Found the same blind-trust problem in Won that I'd already found in Lost.**
After fixing the Lost reconciliation I went looking for the same pattern elsewhere and found it. One lead, marked Won, had six touches, no message at all, and only £160 a month in spend. That is not a closed deal — that is someone who gave up labelling it properly. I applied the same evidence-based logic Lost already had: a Won label with no message and weak commercial signal (under £1,000 spend or fewer than 2 touches) gets moved to Hold for a genuine follow up instead of being trusted blindly.

**Built a Step Zero priority above the existing hot/warm/cold scoring.**
While reviewing the daily DM queue I realised the existing logic treated a confirmed meeting the same as any other hot reply. That undervalues it — someone who has already agreed to meet but only has an Instagram handle on file is one message away from a locked appointment, which is more urgent than a fresh hot conversation. I introduced Step Zero so these jump to the very top of the 40 slots, and made sure anyone with an email instead gets the same priority handled through the shop sequencer's email channel, so it never wastes a DM slot unnecessarily.

**Pushed back on the duplicate checking being ID-only.**
The first duplicate check only looked at lead_id. I identified four other ways a duplicate could appear — same handle in a different format, same email with a typo, same phone number formatted differently, same store in the same city entered by a different BDR. I insisted on checking all five. This is what caught L0295 @heritagefinds as a duplicate of L0130 — different lead IDs, same person. An ID-only check would have missed it entirely.

**The division of labour in plain terms:**
I brought the commercial judgment. Claude brought the implementation speed. Neither alone would have produced this tool in the time available.

---

## Files In This Repo

```
clean_pipeline.py      Step 1: Data cleaning, geographic sanitisation, lead classification, stage reconciliation
prioritise.py           Step 2: Step Zero meeting confirmations, scoring, top 40 selection, shop sequencing
draft_messages.py       Step 3: Personalised message drafting via Claude API, including time-locking messages
batch_handler.py        Step 4: New batch handling, duplicate detection, permanent base pipeline updates
city_proposer.py        Step 5: City scoring, weekly visit recommendation, visit order
README.md               This file
```

**Files generated by the scripts (not in repo, created on first run):**
```
raw_master_pipeline.csv   The permanent base. Every lead ever seen lives here, appended to,
                          never overwritten. clean_pipeline.py reads from this once it exists.
pipeline_clean.csv        Today's cleaned, classified, reconciled pipeline.
visits_today.csv          Starts empty every morning. Only fills once a rep manually confirms
                          a specific appointment time in the Kanban.
```

**Input file (not in repo — bring your own):**
```
Fleek_-_Acquisition_Case_Study_-_Pipeline_Data.xlsx
```

Place this file in the same folder as the scripts before running.

---

## Quick Reference — Scoring Weights

| Signal | Max points | Why it matters |
|--------|-----------|----------------|
| Hot reply (buying signal) | 50 | Active conversation beats cold outreach every time |
| Warm reply (objection) | 25 | Still worth pursuing — never give up without a hard no |
| Estimated monthly spend | 30 | Biggest predictor of deal value |
| Sales velocity (items/30d) | 20 | Fast sellers need stock urgently |
| Combined revenue (price × velocity) | 15 | Rewards quality sellers not just high volume |
| Followers | 10 | Audience size signals operation scale |
| Active listings | 5 | More listings = more recurring need |
| **Maximum possible score** | **130** | |
