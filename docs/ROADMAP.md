# 🦅 מצאן — The Unfair Vision

> This document replaces the previous roadmap entirely. It is the converged output of a five-agent skunkworks debate (OpenAI · Airbnb · Palantir · Anduril) stress-tested by a contrarian red-team.
> It contains ONLY: game-changing ideas, high-leverage architecture, autonomous-agent concepts, AI-native workflows, and ideas that would surprise an experienced engineer.
> Written: 2026-06-10.

---

## ⚡ The One Reframe That Changes Everything

Every "obvious" version of this product optimizes the **supply side**: find more listings, score them smarter, predict harder. The red-team killed that thesis:

> **The couple is already drowning in listings. Finding is 10%. The 10x is collapsing the time from "a great apartment exists in the world" to "the couple has sent a credible, human message and booked a viewing" — from hours to minutes — with the two-person indecision removed.**

In a university town's hot market, the apartment goes to **whoever views first and sounds most human.** So we don't build a better crawler. We build a **tenant-side super-broker that wins on demand-side execution speed and decision clarity.**

**The North-Star Metric:** ⏱️ *Time from a qualifying unit existing → a one-tap-sendable, personalized Hebrew message in the couple's hand, with the partner already aligned.* Today: hours. Target: **under 90 seconds, 24/7, zero missed high-value units.**

---

## 1. 🎯 GAME-CHANGING CAPABILITIES

### G1. One-Tap First Contact (the single highest-leverage capability)
The moment a 9/10 unit appears, the system has already drafted a warm, specific, *human* Hebrew message in the couple's voice ("שלום, אנחנו זוג עובדים, פנויים לראות עוד היום…") and assembled the 5 questions they always forget (ועד בית? חיות? תאריך כניסה? גמיש במחיר?). Telegram shows **one button: "אשר ושלח."** The human sends; the system never impersonates autonomously.
→ This is the whole game. Speed-to-credible-contact is the #1 predictor of getting the viewing.

### G2. Couple Mode — the Shared Decision Surface
The product talks to *two* people, not one. Each partner gets the same deck; a listing only graduates to the Shortlist when **both** swipe yes — a quiet mutual "yes." Votes stay hidden until both decide (no anchoring). Disagreement opens a gentle prompt ("אורי wasn't sure — what gave you pause?") instead of a silent veto.
→ Two people's indecision is the hidden delay in every apartment search. This removes it.

### G3. The "We" Taste Engine (the moat)
Every swipe trains a living model of *this couple* and — crucially — their **overlap**. It surfaces preferences they never stated: "You both reject ground floor," "You linger on bright kitchens," "You say budget matters but you saved three over-budget flats with balconies." The product gets sharper the longer they use it and is worthless to anyone else. The magic line — *"You agree on light and quiet; you disagree on whether a balcony is worth ₪200"* — is the screenshot moment.

### G4. Cross-Source Apartment Resolution + "Cheaper Elsewhere"
The same physical flat appears on Yad2, Homely, and 3 Facebook groups — different brokers, different prices, sometimes a fee vs. no-fee path. Collapse all observations into **one apartment** and surface the cheapest/no-fee route. Detecting "this exact unit is relisted ₪300 higher by a broker" is invisible to any human scrolling one feed.
→ Concrete money saved + instant decision clarity. Feasible today (phone + price-band + perceptual image hash).

### G5. Academic-Calendar Market Intelligence (the signal everyone misses)
Beer Sheva is a Ben-Gurion University town. Supply, price, and competition swing violently with the academic year (Aug–Oct crush, post-semester dumps, dorm-lottery dates). The system tells the couple **when to hunt, when to lowball, and when to pounce**: "Inventory in שכונה ב dries up in ~3 weeks — act now," or "Prices drop after exams; if you can wait 5 weeks, expect ₪200–400 less."
→ Timing leverage no generic product has. Unique to this town.

### G6. Off-Market Demand Broadcast (tap supply no scraper can reach)
The best שכונה ב flats never hit any website — they move through neighborhood WhatsApp groups, building boards, and "my cousin is leaving." The system generates a clean, shareable **"couple seeking" card** ("זוג עובדים מחפש 2.5–3 חד׳ בשכונה ב, תקציב 4100, פנויים מיד, ממליצים") for the couple to drop into local groups, plus tracks responses.
→ Turns the couple from passive searchers into a demand signal the market comes to.

### G7. Catastrophe Guard — Scam & Bait Detection
For an anonymous-landlord market, the one unrecoverable outcome is losing deposit money. A rules-based guard flags the classic signature: far-below-market price + deposit-requested-before-viewing + no phone + reused/stock photos. Not ML — a deterministic shield against the only catastrophic failure.

---

## 2. 🏗️ HIGH-LEVERAGE ARCHITECTURAL UPGRADES

### A1. From Scraper to Sensor-Fusion Track Table
Retire "list of listings." Adopt a **unified track table**: every source is a *sensor*; each real apartment is a *track* with a confidence score and the list of sensors confirming it. Join key = phone + image-hash + (street/rooms/price band). Two independent sources confirming one unit → high confidence; a lone low-trust FB post → "verify before waking the human."
→ This is the Palantir idea, *de-gold-plated* by the red-team: SQLite tables, not a graph database. Solves the only graph problem that matters (dedup) without the resume-driven engineering.

### A2. Event-Driven Ingestion, Not Polling
Replace fixed 30/400-minute scans with **change-detection daemons** on an *adaptive cadence* — tight during peak posting hours (08:00–23:00), relaxed overnight. React only to **deltas** (new ID, price drop, relist). Use the lowest-latency read-only feed each source exposes (mobile/JSON endpoints) before falling back to DOM scraping.
→ Cuts detection latency from hours to seconds while *reducing* load and noise.

### A3. Self-Healing Scrapers
Each sensor watches its own output. Zero results during peak hours or a parse-rate collapse = it diagnoses its own DOM breakage, falls back to alternate selectors, and asks an LLM to propose a re-mapped selector for one-tap human confirmation.
→ A Facebook redesign degrades the system for *minutes*, not days. This is the single biggest reliability upgrade and would surprise most engineers.

### A4. Always-On, Mission-Assured Deployment
24/7 operation with redundant overlapping sensors so no good unit is ever missed ("we will never miss the one" as a measured target), per-source heartbeats, dead-letter replay of failed fetches, and an explicit detection-to-alert latency SLO shown on the dashboard.
→ Ethics/ToS hard limits respected: read-only everywhere, human approves every outreach, human-like low-frequency cadence, rotating warm sessions.

---

## 3. 🤖 AUTONOMOUS AGENT CONCEPTS

A small society of agents that together behave like the most obsessive tenant-side broker the couple could hire — running for the price of tokens.

- **Scout** — casts a *wide, sloppy* net (deliberately over-pulls; the Analyst, not a regex, decides relevance), optimized for latency on hot sources.
- **Analyst** [the AI-native core] — an LLM reads each listing the way a broker who's seen 10,000 posts reads the *subtext*: "גמיש במחיר" + reposted twice = desperate, negotiate hard; "כניסה מיידית" mid-month = previous tenant left abruptly, ask why; too-cheap + vague = scam pattern. Emits a structured dossier: true-price estimate, negotiability, three implicit risks, and "what a broker would whisper to you."
- **Resolver** — fuses observations into apartment tracks (A1), detects relists and price drifts.
- **Memory** — the taste engine (G3); rewrites every other agent's priorities weekly from the couple's swipes.
- **Negotiator** — drafts the one-tap first-contact message (G1) in the couple's learned voice and tone.
- **Sentinel** — scam guard (G7) + self-healing watchdog (A3); the agent that keeps the couple safe and the system alive.

**Human-in-the-loop is a hard design constraint, not a limitation.** The red-team's sharpest cut: autonomous landlord *calls* would scream "bot" and destroy the human-stability signal that actually closes Israeli rentals. So agents do everything *up to* send — then hand the human a single tap. Autonomy serves speed; the human supplies trust.

---

## 4. 🧠 AI-NATIVE WORKFLOWS

### W1. The Conversational Broker (the new primary interface)
The dashboard stops being a grid of cards and becomes **a chat with your broker.** "Found one on רחוב מצדה — genuinely good, but the post smells like it's above a bar and the kitchen photo hides the stove. Want me to ask?" The couple replies in natural Hebrew; the agent acts.

### W2. The Decision-Grade Dossier (on demand, in seconds)
For any serious candidate, auto-generate the one-page brief a ₪200/hr due-diligence analyst would take a day to build: resolved price history across all sources, no-fee path, real door-to-door commute to BGU/Soroka via GTFS transit data, noise/main-road flags, comparable units on the same street, scam check, and a plain-Hebrew "why this / why not."

### W3. "A Day in This Apartment" (Airbnb's emotional layer, grounded in data)
Replace the spec sheet with a generated micro-story tied to *real* signals: "Morning coffee faces east — sun by 7. The שוק is an 8-minute walk for Friday produce. Bedroom is on the quiet inner side, away from the buses." Plus **commute-to-life**, not commute-to-work: the couple names the 3–4 places that anchor their life; every unit is scored against *their* geography of belonging.

### W4. The Friday Digest as an Artifact
Not a notification dump — a single beautiful weekly card ("This week in your search: 3 mutual matches, 1 rising star, 1 you almost missed") designed to be screenshotted and sent to a parent. The ritual builds shared momentum and is the organic growth loop: *that's* what makes them tell friends.

### W5. The Proactive Morning Standup
Each day: "3 new, 1 worth your time, 1 I already ruled out (scam), 1 I'm watching." Respect attention — surface the *one*, not the thirty.

---

## 5. 😲 IDEAS THAT WOULD SURPRISE AN EXPERIENCED ENGINEER

1. **Self-rewriting scrapers** that detect their own breakage and propose new selectors via LLM (A3) — most teams babysit scrapers manually; this one heals.
2. **Deliberately over-pulling junk** at the Scout layer and letting an LLM judge relevance — the opposite of the usual "tighten the filter" instinct, and it raises recall dramatically.
3. **Hiding the partner's votes until both decide** — a tiny UX rule that quietly solves the two-body decision problem that derails most couple-searches.
4. **A "couple seeking" broadcast card** — the system reaching *outward* into off-market supply instead of only scraping inward (G6). Search products almost never invert the direction of the funnel.
5. **Treating the academic calendar as a market oracle** (G5) — a domain signal so specific that no general product captures it, yet it's the dominant force in this exact market.
6. **The interface is a chat with a broker, not a search UI** (W1) — the listing grid, the thing everyone assumes is the product, disappears.
7. **Latency as the headline KPI of an apartment app** — "seconds from world to your phone" displayed like a trading system's SLO.

---

## 🏁 The Question: If מצאן became the best apartment-hunting system in Israel, what would it look like?

It would not look like a website with listings on it.

It would feel like **the couple hired a brilliant, tireless, slightly paranoid local broker who works only for them** — and who happens to operate at machine speed.

At 02:14 a near-perfect flat is posted in a Facebook group. By 02:15 מצאן has already: confirmed it isn't a duplicate or a scam, read between every line of the post, checked the real 7:40am bus time to Soroka, compared it to every flat ever seen on that street, drafted a warm message in the couple's own voice, and placed a single glowing card on both partners' phones with one button: **"אשר ושלח."** No one is awake. At 07:30 one partner taps it over coffee; by 07:31 the message is sent — *first in line, sounding human, partner already aligned.* By Friday, the digest they screenshot to their parents says "we found it."

The market would feel, to this one couple, **unfair** — as if everyone else were searching with their eyes closed. They wouldn't say "that app was useful." They'd say **"we found it together,"** and they wouldn't quite be able to explain to their friends why it felt like cheating.

That is the product: not search, not alerts, not a dashboard. **A demand-side weapon and a shared memory — a broker that never sleeps, remembers everything, and gets there first.**
