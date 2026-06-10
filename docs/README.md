# 📚 מצאן — Documentation Index

Start here. The docs are split by purpose:

| Doc | What it's for | Read it when… |
|-----|---------------|---------------|
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | The system: diagram, data flow, subsystem cards, concept map | You want to understand *how it works* |
| [`DECISIONS.md`](DECISIONS.md) | ADRs — every major choice with alternatives, tradeoffs, interview angle | You want to understand *why it's built this way* |
| [`INTERVIEW_GUIDE.md`](INTERVIEW_GUIDE.md) | Pitch, likely Q&A, honest weaknesses, learning path | You're prepping to *present it* |
| [`../DEPLOY.md`](../DEPLOY.md) | Exact deployment steps (Docker + systemd), checklist | You want to *ship it* |
| [`ROADMAP.md`](ROADMAP.md) | The ambitious long-term product vision | You want to dream about *what's next* |
| [`PROJECT_STATE.md`](PROJECT_STATE.md) | Current status snapshot | You're resuming work |
| [`SESSION_LOG.md`](SESSION_LOG.md) | History of what changed each session | You want the changelog |

## The one-line mental model
> Independent worker processes scrape sources → a deterministic classifier filters them → results land in a JSON store → a web dashboard and a Telegram bot read from it → a supervisor keeps it all alive.

## If you read only one thing
Read `INTERVIEW_GUIDE.md` §6 ("A learning path to truly own this code") and do the six steps. That's how you go from "Claude helped me build this" to "I own this."
