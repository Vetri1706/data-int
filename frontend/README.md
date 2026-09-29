This is a [Next.js](https://nextjs.org) project bootstrapped with [`create-next-app`](https://nextjs.org/docs/app/api-reference/cli/create-next-app).

## Datavault authentication

- Open `http://127.0.0.1:3001/login`, or `/register` to create an account.
- The top-right account menu shows the real user and includes **Log out**.
- Browser API calls use the same-origin `/api/v1` bridge. Set server-only
  `RUST_API_BASE` to the Rust API URL (default `http://127.0.0.1:3000/v1`).
- JWTs are held in HttpOnly, SameSite=Lax cookies (Secure over HTTPS), not browser
  storage. Login/register return only the user to the browser. Product requests,
  downloads, and SSE are checked against the current session and owner's workspace.
- Logout revokes the current database session. Other devices remain signed in.
  An expired session returns to login; a network failure offers retry.
- Existing browser-readable tokens are discarded once; sign in again after this
  update. Existing accounts and datasets are not migrated or deleted.
- OAuth, email verification, and password reset are not implemented; no inactive
  controls are shown for them.

`scripts/verify-auth.cjs` exercises real registration/login/revocation and workspace
isolation using a **disposable database/API on port 3002**, plus a compiled frontend
on port 3011 configured with `RUST_API_BASE=http://127.0.0.1:3002/v1`. It requires
`AUTH_TEST_ISOLATED=true` and an installed Playwright package (`PLAYWRIGHT_MODULE`
may specify its absolute directory). Never point the test at the user database.

## Getting Started

First, run the development server:

```bash
npm run dev
# or
yarn dev
# or
pnpm dev
# or
bun dev
```

Open [http://localhost:3000](http://localhost:3000) with your browser to see the result.

You can start editing the page by modifying `app/page.tsx`. The page auto-updates as you edit the file.

This project uses [`next/font`](https://nextjs.org/docs/app/building-your-application/optimizing/fonts) to automatically optimize and load [Geist](https://vercel.com/font), a new font family for Vercel.

## Learn More

To learn more about Next.js, take a look at the following resources:

- [Next.js Documentation](https://nextjs.org/docs) - learn about Next.js features and API.
- [Learn Next.js](https://nextjs.org/learn) - an interactive Next.js tutorial.

You can check out [the Next.js GitHub repository](https://github.com/vercel/next.js) - your feedback and contributions are welcome!

## Deploy on Vercel

The easiest way to deploy your Next.js app is to use the [Vercel Platform](https://vercel.com/new?utm_medium=default-template&filter=next.js&utm_source=create-next-app&utm_campaign=create-next-app-readme) from the creators of Next.js.

Check out our [Next.js deployment documentation](https://nextjs.org/docs/app/building-your-application/deploying) for more details.
