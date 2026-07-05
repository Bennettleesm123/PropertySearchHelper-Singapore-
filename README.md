# PropertySearchHelper

Personal decision-support tool for comparing CCR resale condos in Singapore — built to help shortlist, compare, and evaluate properties using structured data (URA/OneMap/LTA/etc.) rather than agent/portal marketing claims.

## Folder structure
- `data/raw/` — untouched downloaded datasets (not committed to Git)
- `data/processed/` — cleaned/merged data ready for scoring
- `data/manual_notes/` — viewing notes, feedback, post-viewing ratings
- `backend/ingestion/` — scripts to pull and clean raw data
- `backend/scoring/` — own-stay / investment scoring logic
- `backend/config/` — adjustable weight presets (JSON)
- `backend/eval/` — backtesting and evaluation scripts
- `ai_layer/` — LLM explanation generation
- `frontend/` — dashboard UI
- `notebooks/` — exploratory work, not production code
- `docs/` — dev notes and planning docs

See `docs/dev_notes.md` for the full project plan.
