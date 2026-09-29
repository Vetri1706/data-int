---
version: alpha
name: "Datavault"
description: "A restrained data-intelligence workbench for turning business questions into verified, source-backed datasets."
colors:
  canvas: "#E9EEF4"
  background: "#F7F9FC"
  surface: "#FFFFFF"
  surface-subtle: "#F6F8FB"
  text: "#10213A"
  text-muted: "#607089"
  border: "#DDE5EF"
  border-strong: "#C9D4E2"
  primary: "#246BDE"
  primary-hover: "#1959C2"
  primary-soft: "#EAF2FF"
  success: "#238A59"
  warning: "#B97908"
  danger: "#C64B57"
  focus: "#2F75E8"
typography:
  sans:
    fontFamily: "var(--font-plus-jakarta), -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
  mono:
    fontFamily: "var(--font-jetbrains-mono), ui-monospace, monospace"
rounded:
  DEFAULT: "0.5rem"
  sm: "0.375rem"
  md: "0.625rem"
  lg: "0.875rem"
spacing:
  control: "2.5rem"
  panel: "1.5rem"
  section-gap: "2rem"
  page-max: "80rem"
components:
  shell: {}
  sidebar: {}
  button: {}
  input: {}
  card: {}
  table: {}
  badge: {}
  dialog: {}
---

# Datavault Design System

## Overview

### Creative North Star

Datavault should feel like a well-made research instrument: a compact field notebook crossed with a dependable enterprise data console. The signature is a quiet layered ridgeline in the overview hero, representing source discovery and the progressive refinement of raw information into structured evidence.

### Product context and register

- **Audience and primary job:** Analysts, operators, researchers, and program teams use the product to turn a natural-language requirement into a defensible dataset with visible provenance.
- **Target market(s) and evidence:** The repository examples target Indian business research and enterprise workflows, but the interface remains globally legible and domain-agnostic.
- **Locale(s) and language policy:** English is the current product locale. Interface copy uses plain sentence case and preserves room for longer localized strings.
- **Usage scene:** Desktop-first, high-frequency research work with dense tables; narrow layouts support review and lightweight actions without hiding data.
- **Register:** Product. Clarity, density, and predictable state treatment lead; brand expression is confined to the logo and overview ridgeline.
- **Memorable signature:** The monochrome evidence ridgeline in the overview hero.
- **Restraint:** Tables, forms, navigation, and workflow states remain flat, quiet, and familiar.
- **Anti-references:** Avoid neon gradients, glass panels, colored icon confetti, perpetual animation, excessive pills, deep card nesting, inflated marketing copy, and ornamental AI imagery.
- **Token ownership/runtime mapping:** Runtime CSS variables in `app/globals.css` are canonical. This file mirrors their accepted values and explains intent. Shared shell and component classes consume semantic variables; route code may use Tailwind utilities for layout but should not introduce new raw brand colors.

## Colors

The interface uses cool white and mist-grey surfaces with navy text. `primary` is the only expressive action color. Green, amber, and red are semantic only. Borders, not shadows, define most containers. Focus uses a visible blue outline; selection uses `primary-soft`.

## Typography

Plus Jakarta Sans is the primary interface family and JetBrains Mono is reserved for identifiers, latency, percentages, and machine-readable contract values. Headings use 650–700 weight rather than extra-black weights. Labels and buttons use sentence case. Dense tables use 12–13px text with generous line height; reading copy remains at least 14px.

## Layout

The application sits inside a framed workspace on wide screens: a fluid 216–260px navigation rail, a 56–68px utility bar, and a content region that expands with the browser instead of stopping at a 1600px shell. Standard desktops retain a comfortable 1280–1680px reading width; at 1536px and above the overview, collection list, dataset, source, and detail surfaces may use the full available work area. Type, control height, table rows, panel spacing, and the hero scale up one measured step at the `2xl` breakpoint so 4K displays do not render the product as a small centered mockup. Overview content uses one full-width hero followed by a table/metrics split. At narrow widths the sidebar becomes an overlay drawer, tables scroll horizontally, and controls wrap without hiding actions.

## Elevation & Depth

The outer workspace uses one soft ambient shadow against the canvas. Static cards are flat and use borders. Menus and modal drawers may use a stronger shadow because they sit above content. Blur is reserved for the mobile navigation backdrop and modal overlay.

## Shapes

Controls use 6–8px radii, panels use 10–14px radii, and status badges may use a full pill only when their compact shape communicates state. Tables stay visually rectilinear. Avoid stacking rounded panels inside other rounded panels.

## Components

### Foundational visual states

Every interactive control has default, hover, focus-visible, active, disabled, and busy treatment. Loading indicators reserve space and reduced-motion mode removes nonessential transforms and repeated animation.

### Buttons and actions

Primary actions use solid blue. High-emphasis neutral actions such as Export use solid navy. Secondary actions use a white surface and border. Icon-only controls require an accessible name and a 36px minimum target. Busy buttons keep their dimensions.

### Navigation and data display

The sidebar uses a soft blue current-page field and quiet monochrome inactive items. Tables use sentence-case headers, 44px rows, subtle hover, semantic status dots with text, and truthful pagination derived from actual data.

### Forms and overlays

Fields use visible labels, white surfaces, 40px control height, and a blue focus ring. Product forms own validation with `noValidate`. Search fields provide an explicit clear action. Drawers use app-owned dialog semantics, focus containment, Escape dismissal, and focus restoration.

### Iconography

Lucide is the sole icon family, using 1.75px strokes at 14–18px. Icons support labels and do not replace unfamiliar text.

### Motion

Motion communicates navigation or state change only. Hover/focus transitions use 120–160ms. The running workflow spinner is the only continuous motion. `prefers-reduced-motion` removes transforms, ping effects, and decorative transitions.

Kokonut UI owns the shared sliding-tab motion used by collection detail views. Magic UI owns the count-up metric treatment and the dashboard's single coordinated blur-fade entrance. Both registry components are locally owned source, restyled to Datavault tokens, and must honor reduced motion. Particle, spotlight, glow, rainbow, and perpetual ambient effects are outside the product register.

### Content and data visualization

Copy is direct and operational: “Create collection,” “Run collection,” “Export CSV,” and “Clear search.” Counts and confidence values use tabular numerals. Evidence language distinguishes verified, review-required, loading, empty, and failed states without hype.

## Do's and Don'ts

- **Do:** Use one strong blue action per decision area and let spacing and type carry hierarchy.
- **Do:** Preserve source, status, and evidence access in every responsive representation.
- **Don't:** Add gradients, glow shadows, animated pings, or colored card collections to imply intelligence.
- **Don't:** Ship actionless buttons, fake pagination, or status claims the system has not verified.
