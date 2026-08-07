# ADR-005: React + Vite + Tailwind for the frontend

**Status:** Accepted
**Date:** December 2025

---

## Context

The project needs a user interface for two main features:
- **Conversational chat**: interface for asking the RAG system questions
- **Sync panel**: managing document ingestion (PDFs and Notion)

The interface should be modern and responsive.

## Alternatives evaluated

### 1. Server-Side Rendering (Next.js / Remix)
- SEO-optimized, server-side routing
- More complex to deploy (needs a Node.js server)
- Unnecessary for a private application with no SEO requirements

### 2. Vue.js + Nuxt
- Progressive framework, gentle learning curve
- Smaller ecosystem than React
- Less in-demand in the job market

### 3. React SPA + Vite
- Larger, more mature ecosystem
- Vite offers instant HMR and fast builds
- An SPA is enough for an internal-use application
- Directly applicable knowledge for the job market

## Decision

**React 19 + Vite 7 + Tailwind CSS v4**, because:

1. **React 19**: latest stable version, with rendering and hooks improvements
2. **Vite 7**: modern build tool, instant startup vs. webpack (Create React App is already deprecated)
3. **Tailwind CSS v4**: utility-first CSS with native dark mode, configured via `@theme` in CSS (no tailwind.config.js)
4. **SPA**: no SEO or SSR requirements. The app is private and local

### Full frontend stack

| Library | Version | Purpose |
|---------|---------|---------|
| React | 19.x | UI framework |
| Vite | 7.x | Build tool + dev server |
| Tailwind CSS | 4.x | Utility-first styling |
| React Router | 7.x | SPA routing |
| Axios | - | HTTP client for the API |

## Consequences

**Positive:**
- Instant Hot Module Replacement during development
- Dark mode implemented with Tailwind, no extra libraries
- Optimized final bundle (<500KB gzipped)
- Simple deployment: static files served by `npm run dev`

**Negative:**
- Requires Node.js 18+ on the machine running it
- An SPA has a heavier initial load than SSR (irrelevant for local use)
- Tailwind v4 is relatively new, less legacy documentation available
