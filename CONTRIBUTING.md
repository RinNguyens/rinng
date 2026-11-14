# Contributing to rinng

Thanks for your interest. Anyone can clone, run and propose changes. Only the repo owner
(@RinNguyens) can merge into `main` and `dev`. Every change goes through a pull request and needs
the owner's review.

## Branches

| Branch | Role |
|---|---|
| `main` | stable release, protected |
| `dev` | integration branch, protected. Target your PRs here |
| `feat/...`, `fix/...`, `docs/...` | your working branches |

## Workflow

1. **Fork** the repo on GitHub (outside contributors cannot push to this repo directly).
2. Clone your fork, then branch off `dev`:
   ```bash
   git clone https://github.com/<your-username>/rinng.git
   cd rinng
   git remote add upstream https://github.com/RinNguyens/rinng.git
   git fetch upstream
   git checkout -b feat/feature-name upstream/dev
   ```
3. Write the code with tests, then check:
   ```bash
   uv sync
   uv run pytest
   uv run ruff check && uv run ruff format --check
   pnpm --dir web lint && pnpm --dir web typecheck   # if you changed web/
   ```
4. Push to your fork and open a **pull request against `dev`** of `RinNguyens/rinng`. Describe clearly what changed and why.
5. The owner reviews it. Address feedback by pushing more commits to the same branch. Once the PR is approved,
   the owner merges it.

## Conventions

- One concern per PR. Keep commit messages short, in the imperative mood ("Add OKX funding poller").
- Do not commit data (`data/`), `.env`, API keys or build output.
- rinng only analyzes; it never places orders. PRs that add automated trading will not be accepted.
- To report a bug or request a feature, open an [issue](https://github.com/RinNguyens/rinng/issues).

By submitting a contribution, you agree that your code is released under the [MIT license](LICENSE).
