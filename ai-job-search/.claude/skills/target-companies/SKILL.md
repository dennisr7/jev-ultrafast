---
name: target-companies
description: >
  Builds and maintains a large target-company list (hundreds of companies) across
  the candidate's domains of interest, seeded from known major players and padded
  with relevant startups found via web search. Output feeds /greenhouse-sweep.
  Trigger phrases: target companies, company list, build company list, find companies
  hiring, /target-companies
---

# Target Companies

Builds `company_targets.csv` at the project root: a large, deduplicated list of
companies the candidate could plausibly apply to, tagged by sector. This is a
**breadth tool**, not a fit filter — it intentionally includes companies across every
domain in the candidate's profile, from household names to startups, without
pre-judging fit. `/greenhouse-sweep` consumes this file to find actual open roles;
`/rank` and `/apply` do the fit judgment later.

## Invocation

- `/target-companies` — full build or idempotent re-run (merges, does not duplicate)
- `/target-companies --add <sector>` — pad one sector further without touching the rest
- `/target-companies --list` — print current counts by sector and stop

---

## Step 0: Handle `--list`

If invoked with `--list`, read `company_targets.csv` if it exists, print a per-sector
count table, and stop. If the file doesn't exist, say so and suggest running
`/target-companies` with no arguments.

## Step 1: Read Candidate Domains

Read `.claude/skills/job-application-assistant/01-candidate-profile.md` and
`.claude/skills/job-application-assistant/04-job-evaluation.md` for the candidate's
actual skill/domain areas (don't hardcode a generic list — pull from what's actually
in the profile). As of this candidate's profile, the domains are:

- **Cybersecurity** (CompTIA A+/Network+/Security+/CSIS/CIOS certifications)
- **Agentic AI / ML** (multi-agent systems, RAG, agentic workflows, Claude Code usage)
- **Power generation / energy** (utilities, energy tech)
- **Embedded systems / hardware** (PCB design, firmware, rapid prototyping, JTAG)
- **VR / AR** (AR/VR research and prototypes)
- **HCI / UX / human factors** (research assistant roles, gesture-control projects)
- **IoT** (embedded + connectivity overlap)

If the profile has changed since this list was last generated, use the current
profile content, not this snapshot.

## Step 2: Seed List — Known Major Players

For each domain, compile as many established, recognizable companies as you can
from general knowledge. Err toward inclusion — this list is deliberately wide, and
irrelevant entries get filtered out later by `/greenhouse-sweep` (no Greenhouse
board) or by the candidate's own judgment, not by you pre-guessing fit here. Aim for
at least 25-40 companies per domain where the domain supports it (cybersecurity, AI,
and embedded/hardware are large enough to go well beyond that). Cover:

- **Cybersecurity:** major vendors (e.g. Cisco, Palo Alto Networks, CrowdStrike,
  Fortinet, SentinelOne, Okta, Zscaler, Rapid7, Tenable, Mandiant, Proofpoint,
  Check Point, Darktrace), defense/government-adjacent (Booz Allen Hamilton, Leidos,
  ManTech, SAIC), and cloud-security-adjacent teams at major cloud providers.
- **Agentic AI / ML:** AI labs (Anthropic, OpenAI, Google DeepMind, Meta AI, Mistral,
  Cohere, xAI), infrastructure/tooling (Scale AI, Databricks, Hugging Face, LangChain,
  Weights & Biases, Together AI, Perplexity), and major tech companies' AI orgs
  (Microsoft, Google, Amazon, Apple, NVIDIA, Salesforce).
- **Power generation / energy:** utilities (NextEra Energy, Duke Energy, Southern
  Company, Dominion Energy, Exelon, American Electric Power, PG&E, Con Edison),
  energy tech/equipment (GE Vernova, Siemens Energy, Schneider Electric, ABB,
  Eaton), and clean-energy/grid startups broadly (Tesla Energy, Sunrun, Fervo Energy).
- **Embedded systems / hardware:** semiconductor/device makers (Texas Instruments,
  Analog Devices, Qualcomm, NVIDIA, Broadcom, STMicroelectronics, NXP, Infineon,
  Microchip Technology), consumer/industrial hardware (Apple, Garmin, Bose, Dell,
  HP, Bosch, Honeywell, Emerson, Zebra Technologies), and robotics/autonomy
  (Zoox, Waymo, Anduril, Boston Dynamics).
- **VR / AR:** Meta (Reality Labs), Apple (Vision Pro), Magic Leap, Varjo, Valve,
  HTC (Vive), Niantic, Snap, Unity, Epic Games, Qualcomm (XR chipsets).
- **HCI / UX / human factors:** design-forward consumer tech (Google, Microsoft,
  Adobe, Roblox), medical-device/aviation human factors (Gulfstream Aerospace,
  Boeing, Medtronic, Terumo, Philips Healthcare, Stryker), and defense human-factors
  teams (Raytheon/RTX, Northrop Grumman, Lockheed Martin, L3Harris).
- **Aerospace/defense (cross-cutting — embedded + power + cybersecurity overlap):**
  Lockheed Martin, Northrop Grumman, RTX (Raytheon), General Dynamics, L3Harris,
  Anduril, Blue Origin, SpaceX, Textron.

This is a starting reference, not a ceiling — add more within each domain from your
own knowledge, and don't stop at the examples listed here.

## Step 3: Pad with Startups via Web Search

Run WebSearch queries to find startups and smaller/newer companies the seed list
above wouldn't naturally include, roughly 2-3 queries per domain, e.g.:
- `"embedded systems startup" hiring 2026`
- `"agentic AI startup" Series A OR "Series B" hiring engineers`
- `VR OR AR startup hiring firmware OR hardware engineer 2026`
- `"power grid" OR "clean energy" startup engineering jobs 2026`
- `cybersecurity startup hiring 2026`
- `"human factors" OR "UX engineer" medical device startup`

Extract company names from the results (not the individual job postings — just the
company names) and add them to the appropriate sector(s). Skip results that are job
board aggregators, not actual companies.

## Step 4: Deduplicate and Tag

Build the merged list. A company can carry multiple sector tags (e.g. Anduril is
both "embedded_hardware" and "aerospace_defense"). If `company_targets.csv` already
exists, merge additively — do not drop or overwrite existing rows, only add new
ones, and do not duplicate a company already present (case-insensitive match on
company name).

Write `company_targets.csv` at the project root with columns:

```
company,sector,greenhouse_token,greenhouse_status,workday_tenant,workday_instance,workday_site,workday_status,last_swept_date
```

- `sector`: one or more of `cybersecurity`, `agentic_ai_ml`, `power_energy`,
  `embedded_hardware`, `vr_ar`, `hci_ux`, `aerospace_defense`, `iot` (semicolon-
  separated if multiple apply)
- `greenhouse_token`: leave blank — `/greenhouse-sweep` resolves this
- `greenhouse_status`: `pending` for every new row
- `workday_tenant`, `workday_instance`, `workday_site`: leave blank — `/workday-sweep` resolves these
- `workday_status`: `pending` for every new row
- `last_swept_date`: leave blank

Two independent ATS-status columns exist because a company can be `no_board`
on one and reachable on the other (that's the whole point of the
`/greenhouse-sweep` → `/workday-sweep` → raw-HTML fallback chain) — never
collapse them back into a single status column.

## Step 5: Present Summary

```
## Target Company List Built/Updated

**Total companies:** N (M new this run)

| Sector | Count |
|--------|-------|
| Cybersecurity | ... |
| Agentic AI / ML | ... |
| Power / Energy | ... |
| Embedded / Hardware | ... |
| VR / AR | ... |
| HCI / UX | ... |
| Aerospace / Defense | ... |
| IoT | ... |

File: `company_targets.csv`
```

Then note plainly: **most large/established companies (Apple, Meta, Lockheed, Cisco,
etc.) do not use Greenhouse** for their primary hiring pipeline — they run their own
ATS. `/greenhouse-sweep` will only find real postings for the subset of this list
that actually hosts a public Greenhouse board (mostly startups and mid-size tech
companies), and will mark the rest `no_board` rather than silently dropping them —
they stay in the list for the record and for a possible future `/add-portal` skill
covering their actual ATS.

Suggest running `/greenhouse-sweep` next.

## Design Notes

- This list is intentionally broad — resist the urge to pre-filter for fit here.
  Fit judgment belongs to `/rank` and `/apply`, working from actual postings, not
  from a company name alone.
- Re-running `/target-companies` is additive/idempotent, so it's safe to run again
  after the candidate's profile changes or interests shift.
- `--add <sector>` only runs Steps 2-4 scoped to that one sector, for topping up
  without redoing the whole list.
