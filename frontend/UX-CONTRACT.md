# Datavault UX Contract

## Canonical UI Map

| Capability | Canonical owner | Source of truth | Allowed variants | Verification |
|---|---|---|---|---|
| Application shell and navigation | `components/shell/*` | This contract + `DESIGN.md` | Desktop rail, mobile overlay | Keyboard, current route, narrow viewport |
| Authentication | `components/auth/*`, `app/api/v1/[...path]/route.ts` | Rust `crates/auth` and API auth handlers | Login, registration, session recovery, logout | Real isolated-DB browser test in `scripts/verify-auth.cjs` |
| CRUD | `app/collections/**` and `lib/api.ts` | Rust task routes in `src/main.rs` | Create, read, run, and export; destructive deletion is not exposed in this scope | New collection run, result load, export response |
| Form | `app/collections/new/page.tsx` | Route schema using React Hook Form + Zod | Inline field and submission errors | Invalid submit, inline error, first invalid focus |
| Select/Listbox | `components/collection/ModelSelector.tsx` | Authenticated `/me/models`, intelligence `validate_selection` | Native selects; OS popup geometry is accepted | Keyboard, popup, unavailable models, narrow viewport |
| Search field | Screen-local controlled field until a second remote-search consumer exists | This contract | Global collection search, local result search | Clear, IME-safe input, no-results |
| Table Selection | `components/dataset/DataTable.tsx` using TanStack table state | This contract | Current-page selection only | Select-page semantics and selected count |
| Table navigation | TanStack client pagination for loaded records | This contract | Previous and next controls | Honest range/page bounds |
| Evidence dialog | `EvidenceDrawer` | This contract | Right-side modal drawer | Focus containment, Escape, overlay, restoration |
| Tabs | `components/kokonutui/smooth-tab.tsx` | Kokonut UI source adapted to this contract | Collection detail navigation | Arrow keys, Home/End, selection, panel association |
| Export | Backend task export routes | Rust routes in `src/main.rs` | CSV and evidence JSON | CSV/JSON link response |
| Scrollbar | `app/globals.css` | `DESIGN.md` tokens | Standards plus WebKit fallback | Keyboard, pointer, forced colors |

## Behavior ledger

| Operation | Trigger | Pending | Success | Failure | Focus outcome |
|---|---|---|---|---|---|
| Create collection | `Create collection` / `Continue` | Stable busy button and workflow feed | Navigate to collection results | Persistent inline error with retryable form values | Results heading or first invalid field |
| Search loaded dataset | Search field | Immediate local filtering | Updated range and rows | No-results state with `Clear search` | Search field remains focused |
| Inspect evidence | Company/evidence action | None | Evidence drawer opens | N/A | Drawer title, then return to trigger |
| Export dataset | `Export` → format | Browser download | Menu closes | Browser/backend response remains visible | Export trigger |
| Cancel create | `Cancel` | None | Return to overview | N/A | Overview heading via route navigation |

## Route and navigation policy

- `/` is Overview. `/collections/new` is the only New Collection route.
- `/collections` owns collection detail routes; exactly one sidebar destination is current.
- Dataset detail currently resolves to the owning collection detail route.
- Browser Back preserves native history. Search state inside a loaded in-memory table is transient and intentionally not placed in the URL.
- Every route inherits a descriptive product title; collection detail derives its visible heading from the loaded record.

## Forms

### Collection model choice

- New collections default to the installed lightweight local Qwen model. Provider and model are explicit, per-collection choices, persisted in `data_contract._model_config`; no model preference or consent is stored in browser storage.
- The model catalog lists all installed Ollama models and the full live NVIDIA `/v1/models` catalog, not a guarantee that every hosted model can perform inference with the account. Refresh re-queries both providers without sending collection inputs. Embedding/reranking models and cloud-relayed Ollama models remain visible but disabled. A removed selection stays visible as unavailable until explicitly changed. API keys remain in the gitignored server-only `.env.llm.local` file and are never returned to the browser.
- Choosing NVIDIA requires an unchecked-by-default consent checkbox naming the outgoing prompt, requested fields, queries, and retrieved passages. Changing provider/model resets consent. The server rejects NVIDIA requests without consent and rejects unlisted models. No automatic local-to-hosted fallback is permitted.
- The shared `ModelSelector` uses labeled native selects with platform-owned popup appearance, typeahead, arrow keys, and Escape behavior. It owns loading, refresh/retry, catalog counts, disabled, and unavailable states. Refresh preserves the choice, blocks submission while checking, and ignores aborted responses. Review and running states display the selected provider/model.
- Pipeline progress follows backend stages; elapsed-time animation never marks a step complete. Model calls include bounded queue/network deadlines; whole workflows have a terminal timeout. Successful source chunks are not extracted again during replanning.
- Evidence validation remains deterministic and source-backed regardless of provider. Local model processing still uses public search engines/websites for source retrieval; “local” does not mean offline collection.

### Authentication and account access

- `/login` and `/register` are public and render without workspace navigation. Protected screens wait for `/auth/me` before mounting their data views.
- Login returns to a validated same-origin `next` path. External URLs, protocol-relative paths, and auth/API destinations are rejected.
- Credentials use the existing Rust email/password API. There are no decorative OAuth or password-reset buttons without backend support.
- `AuthForm` is the shared React Hook Form owner for both auth modes: labeled fields, first-invalid focus, inline errors, masked passwords with reveal, stable busy actions, and duplicate-submit prevention. No credential drafts or unsaved-change dialogs are used; passwords are intentionally ephemeral and cleared after failures.
- Session tokens live in a server-set HttpOnly, SameSite=Lax cookie, Secure over HTTPS. The same-origin API bridge forwards the bearer token server-side; tokens never enter URLs, JavaScript storage, or auth JSON responses. Mutations require a matching Origin.
- The Rust API requires active stored sessions and owner-workspace access for product data, downloads, and run events. Cross-workspace object IDs deliberately return 404 to avoid disclosing other customers’ resources. No new membership/role policy is inferred.
- The account menu shows the actual user and email. Log out revokes the current stored session, clears the cookie and client query cache, broadcasts to other tabs, and returns to login. Other devices remain signed in.
- Failed logout stays visible and retryable; the UI does not claim success before server acknowledgement. Expired sessions return to login without retry loops. Connection failures show a retry state instead of treating the user as signed out.
- Historical browser-readable `dv_token`/`dv_user` values are discarded; users sign in again once after this update.
- New auth surfaces reuse the existing CSS tokens and typography; no visual rebrand or new animation system is introduced.

- Product forms declare `noValidate` and use React Hook Form/Zod or an equivalent app-owned validation layer.
- Invalid controls expose an associated text error; entered non-sensitive values remain after failure.
- Collection submission is pessimistic: the interface does not claim completion before the backend responds.
- Duplicate submit is blocked while a collection runs.

## Tables and datasets

- The loaded dataset is bounded and paginated client-side because the current API returns the full in-memory task result.
- Range, page count, and navigation derive from the actual loaded rows; no synthetic page numbers are shown.
- Selection means the current loaded page. The select-all control states that scope in its accessible label.
- Narrow layouts use horizontal table scrolling because cross-column comparison matters.
- Empty dataset and no search results are distinct states.

## Dialogs and feedback

- Evidence uses an app-owned modal drawer with a labeled dialog, inert/obscured background, initial focus, focus trap, Escape and overlay dismissal, and focus restoration.
- Routine navigation does not use confirmation. There is no destructive action in the redesigned scope.
- Errors remain inline near the workflow they affect; transient acknowledgements must never be the only location for corrective information.

## Accessibility and motion

- Target WCAG 2.2 AA.
- Interactive controls use semantic HTML, visible focus, accessible names, and a practical 36–44px target.
- Status is expressed with text and shape in addition to color.
- Reduced-motion mode disables decorative transforms and continuous status animation except an essential low-motion progress indicator.

## Business context sources

| Rule area | Source |
|---|---|
| Collection workflow and exports | `src/main.rs` Rust route definitions |
| Evidence and confidence model | Repository `README.md` and `src/models.rs` |
| Frontend route structure | `frontend/app/**/page.tsx` |
