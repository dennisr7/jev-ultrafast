# Job Evaluation Framework

<!-- SETUP: Skill match areas and career goals are personalized by running /setup -->

## Scoring Dimensions

Evaluate each job posting against these five dimensions:

### 1. Technical Skills Match (0-100)
How well do the required/preferred skills align with the candidate's capabilities?

| Score | Meaning |
|-------|---------|
| 80-100 | Core requirements are primary skills |
| 60-79 | Most requirements match, 1-2 gaps that are learnable |
| 40-59 | Partial match, significant upskilling needed |
| 0-39 | Fundamental mismatch |

**Strong match areas:** Embedded systems (PCB design, firmware, rapid prototyping), cross-platform app development (Flutter, React), C/C++/Python/Swift, agentic AI / multi-agent systems, Retrieval-Augmented Generation (RAG), HCI/UX prototyping methodology, hardware+software co-design, applied data engineering (Databricks, data lakes/lakehouses, OLTP/OLAP)
**Moderate match areas:** [areas where the candidate has partial exposure but no direct professional experience; filled in by /setup]
**Weak match areas:** Reinforcement learning specifically (explicitly a stated growth interest, not current experience - see 02-behavioral-profile.md), large-scale/production ML systems, formal enterprise software engineering processes beyond a single internship

### 2. Experience Match (0-100)
Does work history align with what they're looking for?

| Score | Meaning |
|-------|---------|
| 80-100 | Direct experience in the same domain and role type |
| 60-79 | Related experience, transferable skills clear |
| 40-59 | Adjacent experience, would need to make the case |
| 0-39 | Unrelated experience |

**Strong:** [role types that match the candidate's direct experience]
**Moderate:** [role types with transferable experience but no dedicated role yet]
**Entry-level:** Candidate is still a student but is prioritizing full-time/new-grad-friendly postings by default; only evaluate internship/co-op postings when compensation clears the bar for the role's location (see Employment Type Filter, dimension 4b)

### 3. Behavioral/Culture Fit (0-100)
Does the role and company culture match the behavioral profile?

| Score | Meaning |
|-------|---------|
| 80-100 | Culture strongly matches behavioral preferences |
| 60-79 | Mixed signals but mostly compatible |
| 40-59 | Some friction areas |
| 0-39 | Significant culture mismatch |

**Red flags to research:** Department disorganization, work dominated by maintenance over development, poor chemistry with leadership, culture mismatches. Check reviews, media coverage, LinkedIn connections, and network contacts for insider perspective.

### 4. Location & Logistics (Pass/Fail + Notes)
- Within commute range: PASS
- Remote with occasional office: PASS
- Requires relocation: FAIL (deal-breaker)
- Frequent international travel: FLAG (discuss with user)

### 4b. Employment Type Filter (Pass/Fail)
**Default: full-time roles only.** Internships/co-ops are a FAIL by default, with one exception:

- **Full-time:** PASS
- **Internship/co-op with compensation sufficient for the job's location:** PASS - check the posted pay (or research typical pay for that title/company/location if not listed) against that location's cost of living before including it. A high-paying internship in a high-cost-of-living area (e.g. a well-paid SF/NYC tech internship) can clear this bar; a modest-stipend internship in an expensive metro generally will not.
- **Internship/co-op without disclosed pay, or pay that looks insufficient for the location:** FAIL - do not present unless the user explicitly asks to see internships regardless of pay.
- When in doubt on whether an internship's pay clears the bar, do a quick cost-of-living/comparable-pay check rather than guessing, and note the reasoning in the evaluation output.

### 4c. Minimum Qualifications Gate (Pass/Fail)
**A hard pass/fail check, separate from the fuzzy 0-100 Experience Match score.** Postings often state an explicit minimum bar ("BS and 3+ years", "BS and 5+ years / MS and 3+ years / PhD and 1+ year", "PhD required", "10+ years of industry experience"). This dimension exists because Experience Match alone is not a substitute for checking a literal stated gate - a role can score high on transferable-skills judgment while still requiring a credential or years-of-experience floor the candidate cannot currently claim.

- **PASS:** No explicit minimum stated, or a stated minimum the candidate's degree/experience timeline genuinely clears (e.g. "BS or equivalent practical experience" with no years attached; "BS + 0-2 years").
- **FAIL:** An explicit stated minimum the candidate does not meet - e.g. a hard year count beyond what the candidate's actual work history supports (see 01-candidate-profile.md for current experience), or a graduate degree required (not just preferred) when the candidate holds a BS.
- **UNCLEAR:** The posting's qualifications section could not be read (fetch failed, page didn't render, or the source data is known-incomplete) - do not default this to PASS. Treat UNCLEAR the same as FAIL for shortlisting purposes (excluded pending manual verification) until it's actually been read.

**This check requires the posting's real Minimum Qualifications text, not a summary or a bulk-imported description field that may be truncated.** Bulk CSV/spreadsheet imports of job postings frequently capture only a team-summary blurb and omit the qualifications section entirely - if the source data for a batch does not reliably contain a "Minimum Qualifications" or "Key Qualifications" marker (spot-check a sample), treat that whole batch's Experience scores as provisional and gate this dimension separately via a live fetch of each candidate posting before it is presented as Strong/Good Fit or sent to `/apply`.

**Do not delegate the final PASS/FAIL judgment to a cheap/fast model without also spot-checking its output.** Extracting the right quote is necessary but not sufficient - the model must also correctly classify what that quote means for this specific candidate's timeline. A model that quotes "3+ years relevant industry experience" but somehow doesn't act on it is a failure mode to watch for, not a hypothetical.

### 5. Career Alignment & Motivation (0-100)
Does this role advance career goals and contain tasks that energize?

| Score | Meaning |
|-------|---------|
| 80-100 | Strongly aligned with career direction, clear growth path |
| 60-79 | Good role but only partially aligned with long-term goals |
| 40-59 | Decent job but doesn't build toward career goals |
| 0-39 | Dead end or backwards step |

**Career goals:**
- Intentionally broad at this stage: open to software engineering, embedded/firmware, hardware/IoT, HCI/UX, ML, and agentic AI roles - not narrowing to one track yet.
- Particularly drawn to roles that blend engineering with a user-experience or human-factors problem (accessibility, medical/health tech, human-computer interaction), where he can shape both the technical build and the UX research question.
- Actively building toward reinforcement learning / reward-design / alignment skills as a growth direction, with interest in eventually working on products with large real-world usage so he can observe the gap between intended and optimized model behavior firsthand.
- Still a student, but prioritizing **full-time roles** in the search regardless - see the Employment Type Filter (4b) above for the internship exception (pay must be sufficient for the role's location).

**Motivation filter:** Evaluate not just whether you *can* do the tasks, but whether the tasks will *energize* you. Consider:
- Tasks that energize: [what kinds of work energize the candidate; filled in by /setup]
- Tasks that drain: None identified - candidate is deliberately keeping an open mind at this early career stage rather than ruling things out.
- Non-task factors: Freedom to question requirements and investigate root causes rather than build to spec; access to AI coding tools (e.g. Claude Code) to offload implementation grunt-work.

**Life situation alignment:** Consider personal constraints:
- **Security**: Currently a full-time student; internships/part-time work acceptable, full financial situation not yet captured.
- **Flexibility**: [location, relocation and commute constraints; filled in by /setup]
- **Professional development**: High priority on roles/teams that support growing into reinforcement learning and alignment-adjacent work over time.

### 6. Salary Benchmark (Optional)

If the salary lookup tool is configured (`salary_data.json` exists), look up the company:
```
python salary_lookup.py "<Company Name>" --json
```

If a city is known from the posting, add `--city "<City>"` to narrow results.

Present findings as:
```
### Salary Benchmark
| Metric | Value |
|--------|-------|
| [Category] index | XX.X (+/-X.X% vs baseline) |
| Overall index | XX.X (+/-X.X% vs baseline) |
```

Interpret results relative to the baseline defined in the data file's metadata. For index-based data, higher typically means above-market compensation.

If the salary tool is not configured, skip this section.

## Output Format

Present the evaluation as:

```
## Job Fit Evaluation: [Role] at [Company]

| Dimension | Score | Notes |
|-----------|-------|-------|
| Technical Skills | XX/100 | [brief note] |
| Experience Match | XX/100 | [brief note] |
| Behavioral Fit | XX/100 | [brief note] |
| Location | PASS/FAIL | [brief note] |
| Employment Type | PASS/FAIL | [brief note] |
| Minimum Qualifications | PASS/FAIL/UNCLEAR | [quote the stated minimum, or note none stated] |
| Career Alignment | XX/100 | [brief note] |

**Overall Score: XX/100** (weighted average of scored dimensions)

### Verdict: [Strong Fit / Good Fit / Moderate Fit / Weak Fit / Poor Fit]

### Key Strengths for This Role
- [bullet points]

### Gaps to Address
- [bullet points]

### Recommendation
[1-2 sentences: apply/skip/apply with caveats]

### Company Research Checklist
- [ ] Checked company website (mission, values, recent news)
- [ ] Checked review sites (Glassdoor, Jobindex, etc.)
- [ ] Checked LinkedIn for team size, recent hires, connections
- [ ] Checked media for restructuring, growth, or workplace issues
- [ ] Identified network contacts who may know the team/manager
```

## Weighting
- Technical Skills: 30%
- Experience Match: 25%
- Behavioral Fit: 15%
- Career Alignment: 30%

(Location, Employment Type, and Minimum Qualifications are pass/fail, not weighted)

## Verdict Override
A **FAIL or UNCLEAR on Minimum Qualifications overrides the computed verdict** the same way Location FAIL does - the job is excluded from Strong/Good Fit presentation regardless of the weighted score, and listed separately with the stated requirement quoted. This is a hard gate, not an input to the 0-100 Experience score.

## Thresholds
- **Strong Fit** (75+): Definitely apply, tailor everything
- **Good Fit** (60-74): Apply, address gaps in cover letter
- **Moderate Fit** (45-59): Consider carefully, discuss with user
- **Weak Fit** (30-44): Probably skip unless strategic reasons
- **Poor Fit** (<30): Skip

## Pre-Application: Call the Employer (Best Practice)

Before writing the application, consider whether the candidate should call the contact person listed in the posting. **Only call if there are substantive questions** - never call just to "be remembered."

### When to Suggest Calling
- The posting has unclear or ambiguous requirements
- It's unclear which competencies are essential vs. nice-to-have
- The role description is vague about day-to-day tasks
- There's a named contact person who invites questions

### Good Questions to Ask
- "What are the primary challenges in this role?"
- "How is time typically divided across the listed responsibilities?"
- "Which competencies are most critical for success in this position?"
- "What does success look like in the first 6-12 months?"

### Rules for the Call
- Prepare a 30-second "elevator pitch" about your background in case they ask
- The call's purpose is **gathering information**, not delivering a pitch
- Take notes - use what you learn to tailor the application
- Reference the conversation naturally in the cover letter ("After speaking with [name], I was especially drawn to...")
