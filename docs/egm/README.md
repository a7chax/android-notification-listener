# Elephant-Goldfish Model

This project uses Google's [Elephant-Goldfish Model](https://github.com/google/elephant-goldfish-model)
through the installed Codex plugin. Generated concept briefs, design drafts,
and review reports go in this directory, as configured in `AGENTS.md`.

Select an EGM skill in Codex or ask for it by name:

- `egm-brainstorm`: explore a feature and write a concept brief.
- `egm-draft`: turn a brief into a design draft.
- `egm-review`: review a design with fresh-context agents.
- `egm-resolve`: work through review findings.
- `egm-bootstrap`: create or update codebase documentation.
- `egm-review-loop`: run a configured group of reviewers.
- `egm-drift-report`: compare documentation with the implementation.

For a new development machine, install the complete plugin using the
[upstream Codex setup](https://github.com/google/elephant-goldfish-model/blob/main/docs/codex.md):

```sh
codex plugin marketplace add google/elephant-goldfish-model
codex plugin add egm@egm
```

Start a new Codex session after a fresh installation. Install the complete
plugin so its skills can access the bundled reviewer personas and standards.
