# Goldvreneli TODO

Inputs for this backlog:
- Direct code review of the current worktree.
- `venv/bin/pytest -q`: `107 passed`.
- `python3 -m py_compile` on the tracked modules: passed.
- Updated `~/bin/codebot.sh` run in default all-model mode with a repo-specific prompt.
  Usable outputs were written under `answers/codebot_v2/` and converged on the same main issues below.

## P0

1. Fix the live Scanner crash in `goldvreneli.py`.
   Files: `goldvreneli.py`, `scanner.py`
   Why this matters:
   - The monolithic Scanner page does `st.session_state.scan_results = scan(...)`.
   - `scan()` returns `(df, skipped_history, skipped_no_data)`, not a DataFrame.
   - The next lines treat `scan_results` as a DataFrame (`results.empty`, `results.columns`, `results.index`), so the current runtime path is broken.
   Do:
   - Unpack the tuple correctly or, preferably, stop duplicating Scanner logic and delegate to `pages/scanner_page.py`.
   - Add a focused test or smoke check for this flow so it cannot regress silently again.

2. Pick one UI architecture and remove the competing one.
   Files: `goldvreneli.py`, `pages/`, `README.md`, `architecture.md`, `CHANGELOG.md`
   Why this matters:
   - `goldvreneli.py` is a 1,887-line monolith again.
   - The `pages/` modules still exist and are newer in several places.
   - The runtime does not delegate to those page modules, so the repo now contains two diverging applications.
   Do:
   - Make `goldvreneli.py` a thin router that delegates to `pages/`.
   - Or delete `pages/` and make the monolith the only source of truth.
   - Do not keep both active representations.

3. Restore advertised/runtime feature parity after the architecture decision.
   Files: `goldvreneli.py`, `pages/`, `README.md`, `architecture.md`, `CHANGELOG.md`
   Why this matters:
   - The current runtime no longer exposes features that the repo still documents and already has modular code for.
   - Regressions include:
     - no `Positions` page,
     - no `Statistics` page,
     - no Swiss scanner universe in the live UI,
     - no `Pause` / `Resume` / `Rescan` in Portfolio Mode,
     - no `Invest All` / `add_shares` flow in Scanner,
     - old `Backtest` flow instead of the newer `Test Mode`,
     - IBKR runtime nav reduced to `Portfolio`, `Settings`, `Help` despite docs claiming broader parity.
   Do:
   - Re-wire the runtime to the current feature set in `pages/`, or explicitly remove dead features and update docs.

4. Unify trading state around one shared `MultiTrader`.
   Files: `core.py`, `portfolio.py`, `goldvreneli.py`, `pages/portfolio_mode_page.py`
   Why this matters:
   - `core.get_multi_trader()` creates a session-wide `MultiTrader` with persisted daily-loss state and live fill logging.
   - `PortfolioManager` still creates its own private `MultiTrader`.
   - Manual trading, Portfolio Mode, live fill logging, and daily-loss enforcement are therefore split across different sources of truth.
   Do:
   - Inject the session-wide trader into `PortfolioManager`.
   - Make attach/stop/restart/fill logging/loss accounting operate on one shared trading session.

5. Fix `AutoTrader` close semantics so `ERROR` does not masquerade as a successful exit.
   Files: `autotrader.py`, `portfolio.py`, `core.py`
   Why this matters:
   - In the monitor loop, generic exceptions set `ERROR` and still call `_on_close(s.pnl)`.
   - In `MultiTrader`, that updates realized-loss accounting and closes fill sessions.
   - In `PortfolioManager`, that can trigger automatic refill logic.
   - A monitoring failure can therefore be treated as a completed exit even when no sell order happened.
   Do:
   - Distinguish `closed`, `errored`, and `errored_with_position_still_open`.
   - Only run close callbacks after a confirmed exit or explicit reconciliation.

6. Guard the whole `AutoTrader` lifecycle, not just the monitor loop.
   Files: `autotrader.py`, `tests/test_autotrader.py`
   Why this matters:
   - `_run()` protects the monitor loop but not the whole entry/exit lifecycle.
   - `place_buy`, `get_price`, and `place_sell` failures during entry/exit can still leave inconsistent state.
   Do:
   - Wrap entry and exit paths in a top-level guarded lifecycle.
   - Add tests for market-entry failure, limit-entry failure, sell failure, and restart/attach reconciliation.

## P1

7. Fix recovery workflows so they cannot double-buy or leave orphaned broker positions.
   Files: `goldvreneli.py`, `pages/positions_page.py`, `autotrader.py`
   Why this matters:
   - Restart/re-attach flows are currently inconsistent across the monolith and modular pages.
   - The wrong recovery action can submit a new buy when the old broker position still exists.
   Do:
   - Reconcile recovery against actual broker positions before restarting.
   - Prefer `attach()` when the position is still open.

8. Add app-level smoke tests for Streamlit routing and current live flows.
   Files: `goldvreneli.py`, `pages/`, `tests/`
   Why this matters:
   - The current suite is strong on unit logic but does not cover page assembly or current runtime flows.
   - That is why a broken Scanner page can coexist with `107 passed`.
   Do:
   - Add smoke coverage for:
     - app bootstrap,
     - page routing,
     - Scanner run path,
     - AutoTrader start path,
     - Portfolio Mode launch.

9. Add `pytest` discovery guardrails so page modules are not collected as tests.
   Files: `tests/`, `pages/test_mode_page.py`
   Why this matters:
   - `pages/test_mode_page.py` is vulnerable to pytest collection by filename.
   - That makes test collection sensitive to app dependencies and environment state.
   Do:
   - Add `pytest.ini` with `testpaths = tests`.
   - Rename the page module if needed to avoid ambiguity.

10. Fix installer/deployment packaging after the runtime architecture is chosen.
    Files: `goldvreneli-install.sh`
    Why this matters:
    - `PROD_FILES` still omits `pages/`, `activity_tracker.py`, and `ibkr_data.py`.
    - If the modular architecture is restored, the installer will deploy an incomplete application.
    Do:
    - Replace the manual allowlist with a package-aware deploy step or keep the manifest generated from the actual runtime tree.
    - Add an install smoke test in CI.

11. Harden `gateway_manager.py` subprocess handling and credential cleanup.
    Files: `gateway_manager.py`
    Why this matters:
    - The gateway is launched with `stdout=subprocess.PIPE` and no long-lived reader.
    - A chatty child can block on pipe backpressure.
    - Credentials are written to a temp config file and only cleaned on normal `stop()`.
    Do:
    - Add a dedicated log drainer or file-based logging.
    - Guarantee temp config cleanup on crash, abort, and abnormal exit.
    - Tighten file permissions and credential lifetime.

12. Remove blocking `time.sleep(...); st.rerun()` loops from page rendering.
    Files: `goldvreneli.py`, `pages/positions_page.py`, `pages/portfolio_mode_page.py`
    Why this matters:
    - These loops block the Streamlit worker thread and duplicate refresh behavior in multiple places.
    - They make the UI less responsive and harder to reason about.
    Do:
    - Switch to a consistent fragment/reactive refresh pattern.
    - Keep refresh scope narrow to live widgets.

13. Stop reaching into private implementation details from the UI.
    Files: `goldvreneli.py`, `portfolio.py`
    Why this matters:
    - The UI reads internals like `pm._target_slots`.
    - That couples page code to implementation details and makes refactors brittle.
    Do:
    - Expose public properties/methods for all values the UI needs.

## P2

14. Make `AutoTrader` status and log access truly thread-safe.
    Files: `autotrader.py`
    Why this matters:
    - `MultiTrader.statuses()` claims snapshot semantics, but `AutoTrader.status` is still mutated from worker threads without shared synchronization.
    - The UI can still observe half-updated state.
    Do:
    - Add per-trader synchronization or immutable snapshot generation.
    - Guard log appends and state reads consistently.

15. Replace ad hoc thread spawning in `PortfolioManager` with a controlled worker model.
    Files: `portfolio.py`
    Why this matters:
    - Startup, refill, and retry logic all spawn daemon threads.
    - Failures can fan out into more background work instead of backing off cleanly.
    Do:
    - Use a single worker loop or bounded executor.
    - Make `running`, `paused`, and `stopped` state transitions explicit.

16. Separate realized P&L reporting from loss-budget accounting.
    Files: `autotrader.py`, `portfolio.py`, `goldvreneli.py`, `pages/`
    Why this matters:
    - The code and UI still conflate realized losses with realized P&L in places.
    - Risk-budget enforcement and operator reporting should not share one ambiguous metric.
    Do:
    - Track real realized P&L separately from cumulative loss-budget consumed.
    - Use consistent naming across the runtime and pages.

17. Consolidate Backtest/Test Mode/replay flows.
    Files: `goldvreneli.py`, `pages/test_mode_page.py`, `replay.py`
    Why this matters:
    - The repo now contains both the old `Backtest` flow and the newer `Test Mode` abstraction.
    - Docs and runtime disagree on which one is canonical.
    Do:
    - Pick one testing/simulation surface.
    - Delete the obsolete flow once the preferred one is wired into the runtime.

18. Externalize and validate scanner universes.
    Files: `scanner.py`
    Why this matters:
    - `scanner.py` carries a very large hard-coded symbol universe.
    - This is brittle, hard to audit, and likely to drift over time.
    Do:
    - Move universes into data files.
    - Add validation for duplicates, invalid symbols, and stale assets.

19. Make env/config persistence atomic and cheaper to read.
    Files: `core.py`
    Why this matters:
    - `env_save()` writes key-by-key and `env_get()` reparses `.env` repeatedly.
    - This is noisy and harder to reason about under repeated reruns.
    Do:
    - Switch to batched atomic writes.
    - Cache parsed settings and invalidate on save.

20. Split oversized modules after the runtime is stabilized.
    Files: `goldvreneli.py`, `autotrader.py`, `scanner.py`
    Why this matters:
    - `goldvreneli.py` (~1887 lines), `autotrader.py` (~963 lines), and `scanner.py` (~585 lines) are carrying too many responsibilities.
    - Refactors are riskier while these files remain dense and cross-cutting.
    Do:
    - Break each module along domain seams after the architecture decision above.

21. Reconcile documentation with the actual shipped runtime.
    Files: `README.md`, `architecture.md`, `CHANGELOG.md`, `pages/help_page.py`
    Why this matters:
    - The docs currently describe a different app than the one the runtime exposes.
    - This is already visible in page names, broker parity, feature availability, and testing flows.
    Do:
    - Update docs only after the routing/architecture work is done.
    - Make one runtime shape authoritative and document that one only.
