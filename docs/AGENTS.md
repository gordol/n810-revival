# Documentation instructions

Read the root [AGENTS.md](../AGENTS.md). The documentation rules below apply throughout this directory.

- Keep the site focused on using, building, and understanding the project.
  Put GitHub administration, CI setup, publication reviews, writing instructions,
  and agent procedures in `maintainers/` or root contributor files. The homepage
  introduces the project, demonstrates Pocket, and helps readers start; dated
  hardware investigations and benchmarks belong in the journal and references.
- Write reader instructions for the published project. Local review and delayed
  pushing are workflow constraints; keep that status out of reader-facing pages.
  Getting-started guides include prerequisites, download, extraction or cloning,
  the working directory, Makefile targets, expected output, and how to quit.
  Use `make` from inside `pocket` for normal startup. Keep the first-run path
  simple; introduce named instances only in guides that need them. State Python
  and Make as prerequisites; keep generic Python and OS package-manager setup
  out of the Pocket walkthrough. Respect the reader's existing environment.
- Remove relocated pages from the built output and search index as well as
  navigation. Import reader-facing manuals through the explicit list in
  `tools/docs_hooks.py` and inspect affected routes in the local preview.
- Use full sentences, familiar words, and concrete explanations. State what the
  system does. Remove marketing language, vague claims, and summaries that omit
  the investigation. Put conversational asides in parentheses.
- Keep the journal chronological. Keep Markdown table rows contiguous and inspect
  the rendered table after adding entries; a strict build can pass with a stray row.
  Introduce hardware, protocols, abbreviations,
  and symbols before relying on them. Link authoritative manuals or source at
  the first useful explanation (including unfamiliar kernel flags).
- Explain the symptom, attempted change, observed result, and next decision.
  Include failed attempts when they explain the engineering. Distinguish the
  historical implementation from a later implementation used as an example.
- Give each page a purpose: a tutorial teaches through an exercise; a how-to
  completes a task; reference records facts and interfaces; explanation develops
  mechanisms. The dated journal connects those forms through the investigation.
- Keep documentation links inside the site. Link implementation claims to the
  actual patch or source, and provide the relevant build/test guide. Verify both
  the target and its presence in the selected repository checkpoint.
- Include code only when it explains a consequential mechanism or gives runnable
  instructions with supplied inputs. Label pseudocode. Replace contextless
  fragments and generic inspection scripts with the actual finding.
- Put visuals beside the claims they explain. Show the complete relevant UI
  (for example a map and workspace as well as a packet inspector). Use Mermaid
  for relationships and real screenshots or recordings for application behavior.
- Captions identify date, platform, workload, and whether the scene is synthetic,
  historical, or reconstructed. Distinguish a pictured sample from an average.
  Explain the metric and any material limitation next to the result.
- Add a recording when interaction is the point. Preserve real timing and label
  edits. Inspect reflections, audio, overlays, metadata, and identifiers before
  including media. Preserve original research artifacts outside the release tree.
- Update `tools/journal-sources.json` for new posts and regenerate navigation
  with `python3 tools/check-journal.py --write`. Review the generated diff.
- Edit canonical manuals under `pocket/docs/` when the site hook includes them.
  Do not edit generated `site/` output or generated source copies as originals.
- Run `make docs-check` after reviewing and staging intended changes, then inspect
  affected pages in the local preview. Verify readability, media, and navigation.

Use the same voice in guides and code-review comments. A useful comment identifies
a concrete problem, its consequence, and the evidence needed to resolve it.
