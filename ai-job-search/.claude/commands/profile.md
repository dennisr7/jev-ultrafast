# /profile - Show or Switch the Active Candidate

This workspace can serve more than one candidate. The active profile is the symlink `profiles/active`; it persists across sessions until switched again.

Arguments: `$ARGUMENTS`

1. Run `tools/profile.sh $ARGUMENTS` (no argument shows the active profile; `list` lists them; a profile name switches).
2. Read `profiles/active/profile.md` in full. From now on, in this session, that file is the candidate profile: it overrides whatever profile CLAUDE.md loaded at session start, and every evaluation, CV, cover letter, interview prep and form answer is for that person.
3. Reply in one or two lines: who is now active, plus that person's open unknowns, if the profile lists any.

Never mix candidates: different emails, phones, documents, accounts and memory.
