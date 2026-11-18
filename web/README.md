# TanStack Start + shadcn/ui

This is a template for a new TanStack Start project with React, TypeScript, and shadcn/ui.

## Adding components

To add components to your app, run the following command:

```bash
npx shadcn@latest add button
```

This will place the ui components in the `components` directory.

## Using components

To use the components in your app, import them as follows:

```tsx
import { Button } from "@/components/ui/button";
```

## Terminal routes

The app is served at `/terminal`, a layout route (`src/routes/terminal.tsx`) with one file per section under
`src/routes/terminal/`:

- `market` — perps ranked by funding, move and crowding (`GET /api/market`).
- `coin` — single-coin dashboard.
- `charts/$tabId` — one chart workspace; the tab strip supports rename, duplicate, close and restore.
- `wallet/{scan,watch,check,lock}` — read-only wallet scan, watchlist, send check and lock panel.

Pure logic sits in `src/lib` (`market`, `wallet-scan`, `wallet-store`, `send-check`, `starred`, `format`) and is
covered by vitest (`pnpm --dir web test`).
