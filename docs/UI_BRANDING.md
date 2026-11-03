# Errand: UI and Visual System

*Written 2026-11-03. This doc covers how Errand looks and moves. `docs/BRANDING.md` stays the source of truth for name, voice and vocabulary; this doc replaces its "Visual direction (starting point)" section. Research notes and sources are at the end.*

---

## 0. TL;DR

- **Two colors and an accent:** **Paper** (warm cream) and **Forest** (deep green), with **Mandarin** (orange) as the only accent. Earthy, calm, editorial, in the spirit of Perplexity's cream-and-teal system, but warmer and more alive.
- **Type:** **Geist** for UI and body, **Instrument Serif** italic for one accent word per headline, **Geist Mono** for errand IDs, Lanes and money.
- **Signature object:** the **Receipt**. Perforated edges, mono figures, a verified stamp. It shows up everywhere: hero, dashboards, video.
- **Motion, two layers:** (1) **website interactions**: scroll-driven reveals, a line that draws as you scroll, a page that turns Forest for the results chapter, and hover states that feel crafted (sliding nav pill, growing underlines, receipts that lift); (2) **product story animations** in the demo and dashboards: an errand loop, receipts that print, a savings counter, escrow that holds and releases, a cheater caught. Everything respects `prefers-reduced-motion`.
- **Not slop:** no purple gradients, no glass blobs, no emoji icons, no generic three-icon feature grid, no Inter-everything, no stock 3D renders. Real numbers and real product screens instead.

---

## 1. Positioning the look

Errand is a money product (escrow, PayPal, slashing) wearing a friendly name. The look has to say **trustworthy and precise** first and **warm and human** second.

| We want | We avoid |
|---|---|
| Editorial calm: lots of cream space, few strong colors | Neon "AI" palettes, purple-to-pink gradients |
| Precision: mono numbers, hairlines, tabular figures | Rounded-everything toy UI, heavy drop shadows |
| A tactile motif (receipts, paper grain) | Abstract glowing orbs and meshes |
| Nature as metaphor (ants and bees run errands for the colony) | Robots, brains, circuit boards |
| One wink per page (BRANDING.md) | Copy full of hype words |

**Why Paper, Forest and Mandarin:** Perplexity proves that a cream canvas with one deep accent reads as "reference library you can trust" [P1][P2]. Forest replaces their teal so we don't look like a clone, and it carries "verified, settled, growth" (money and nature both). Mandarin is the errand in motion: dispatch, action, the thing happening right now. The first reference image (Mandarin Orange #FD550A, Forest Green #015D47) is exactly this pairing, and it is unusual enough in AI products to be recognizable.

**Considered and rejected:** the second reference (Onyx, Electric Indigo, Tropical Mint) is striking, but indigo and violet are the default "AI startup" palette and appear on the ui-ux-pro-max skill's anti-pattern lists ("AI purple/pink gradients") for trust-sensitive products like banking [P3]. We keep its best idea instead: mixing a heavy sans with an italic serif in one headline.

---

## 2. Color

### 2.1 Brand palette

| Role | Name | Hex | Use |
|---|---|---|---|
| Color 1 | **Paper** | `#F4F0E6` | Page background. Never pure white for the canvas. |
| Paper, lighter | Card | `#FBF9F4` | Cards, tables, inputs (depth comes from card on paper, not from shadows) |
| Paper, deeper | Paper Deep | `#E9E3D4` | Code blocks, secondary panels, hatched "held" state |
| Color 2 | **Forest** | `#015D47` | Brand mark, primary buttons, verified state, dark sections |
| Forest, darkest | Ink | `#0B2A21` | All body text (a forest-black, never `#000`) |
| Forest, muted | Moss | `#4F6B61` | Secondary text, captions, axis labels |
| Accent | **Mandarin** | `#FD550A` | Dispatch, live, "act now" fills, the moving dot in the logo. Rare. |
| Accent, text-safe | Mandarin Deep | `#B83F0A` | Mandarin when it must be text on Paper (links, inline highlights) |

Hairlines are warm and tinted, never grey: `rgba(11, 42, 33, 0.12)` default, `0.20` strong, `0.07` soft.

### 2.2 Rules

1. **Paper is ~70% of any screen, Forest ~25%, Mandarin under 5%.** If Mandarin appears more than two or three times in a viewport, remove one.
2. **Mandarin is a fill, not text.** Mandarin on Paper is 2.85:1, which fails WCAG for text. Use Mandarin Deep (4.92:1) for orange text, and **Ink text on Mandarin buttons** (4.74:1). White on Mandarin is 3.24:1 and only passes for large bold text.
3. **Never put Mandarin text on Forest** (2.44:1). Mandarin next to Forest is fine as a shape or dot.
4. **Status never relies on color alone.** Always pair a color with an icon or word [P3].

### 2.3 Contrast (measured, WCAG 2.x)

| Pair | Ratio | Verdict |
|---|---|---|
| Ink on Paper | 13.50 | AAA body text |
| Forest on Paper | 6.94 | AA body, AAA large |
| Paper on Forest | 6.94 | AA, for dark sections and primary buttons |
| Moss on Paper | 5.11 | AA secondary text |
| Mandarin Deep on Paper | 4.92 | AA, orange links |
| Ink on Mandarin | 4.74 | AA, accent buttons |
| White on Mandarin | 3.24 | Large text only |
| Mandarin on Paper | 2.85 | Not for text |
| Mandarin on Forest | 2.44 | Not for text |

### 2.4 Semantic states (Errand vocabulary)

| State | Look |
|---|---|
| **Verified** | Forest text on a 10% Forest wash, check icon, "verified" |
| **Delivered** (no verifier) | Moss outline chip, dot icon, "delivered" |
| **Agreed** (panel) | Forest outline chip with "2/3" in mono |
| **Held in escrow** | Paper Deep chip with slow diagonal hatching (section 5), lock icon |
| **Live / dispatching** | Mandarin dot that pulses, "running" |
| **Failed / slashed** | Brick `#9E2B1E` text on `#F4DCD6`, cross icon. Brick is semantic only, never a brand color. |

### 2.5 Dark mode ("Night Forest")

The same three colors, inverted around Forest instead of grey:

| Token | Hex | Contrast |
|---|---|---|
| Background | `#0B1F19` | |
| Surface | `#12291F` | |
| Text | `#F4F0E6` (Paper) | 15.07 |
| Muted text | `#9DB3AA` | 7.73 |
| Verified / brand | `#7FD1B0` (Forest, lifted) | 9.52 |
| Accent | `#FF6B2C` (Mandarin, lifted) | 6.04, safe as text here |

### 2.6 Optional highlight: Crest

Crest Yellow `#E0F354` (from the first reference) is allowed in exactly one place: highlighted numbers inside **Forest sections** (6.44:1 on Forest), such as "84% cheaper" on the dark results band. It is a highlighter, not a fourth brand color. Leave it out if in doubt.

---

## 3. Typography

| Role | Font | Notes |
|---|---|---|
| UI, body, headings | **Geist** (400, 500, 600) | Humanist-leaning grotesk, sharper than Inter, free on Google Fonts. Headings at 500, tracking `-0.02em`. |
| Accent word | **Instrument Serif** italic | One or two words per headline only: "Send your model on *fewer* errands." Echoes Perplexity's sparing serif [P2] and the sans-plus-italic-serif mix in the second reference. |
| Numbers, IDs, Lanes, money | **Geist Mono** | Always `font-variant-numeric: tabular-nums` so money columns align and counters don't jitter. |

### Scale (desktop; scale display sizes down ~30% on mobile with `clamp()`)

| Token | Size / line height | Use |
|---|---|---|
| display | 72 / 1.02 | Landing hero only |
| h1 | 44 / 1.08 | Page titles |
| h2 | 30 / 1.15 | Section titles |
| h3 | 20 / 1.3 | Card titles |
| body-lg | 18 / 1.55 | Landing paragraphs, max 640px wide |
| body | 15 / 1.5 | Dashboard |
| small | 13 / 1.45 | Captions, table cells |
| eyebrow | 12 / 1.4, uppercase, `+0.08em`, Geist Mono | Section labels like `LANE · MATH.FINAL-ANSWER` |

Use `text-wrap: balance` on headings as a progressive enhancement, never as a layout guarantee [P3].

---

## 4. Layout and components

### 4.1 Foundations

- **Spacing:** 4px base. Scale 4, 8, 12, 16, 24, 32, 48, 64, 96, 128. Landing sections 96 to 128 apart; dashboard cards 16 to 24.
- **Radius:** interactive things are pills (buttons, chips, the delegate composer). Reading surfaces are 12px (cards). Inputs and code are 8px. Same rule as Perplexity [P2].
- **Elevation:** contrast first (Card on Paper, 1px hairline). Shadows only for overlays: `0 12px 32px -8px rgba(11,42,33,0.12)`.
- **Grid:** max width 1200px, gutter `clamp(16px, 5vw, 64px)`. Test at 375, 768, 1024 and 1440px [P3].
- **Texture:** a fixed SVG noise layer at 3% to 4% opacity over Paper gives the paper feel. Disable it in print and on low-power devices if needed.

### 4.2 Components

| Component | Spec |
|---|---|
| Primary button | Forest pill, Paper text, 14 x 24 padding, 15/500. Hover darkens to Ink. No shadow. |
| Accent button | Mandarin pill, **Ink** text. At most one per screen ("Top up with PayPal", "Send errand"). |
| Ghost button | Transparent, 1px hairline, Ink text. |
| Chip / badge | 6px radius, 12/500, icon + word (section 2.4). |
| Card | Card color, 12px radius, 1px hairline, 24px padding. Hover changes the border to strong, never lifts. |
| **Receipt** | Card with a perforated top and bottom edge (CSS `radial-gradient` mask), Geist Mono figures, dotted leaders between label and value, a verified stamp in the corner. |
| Delegate composer | Full-width Card pill, Forest focus ring 2px, a Mandarin dot at the left that pulses while running. |
| Tables (AG Grid) | Quartz theme mapped to tokens: Card background, hairline borders, Moss headers in mono eyebrow style, tabular numbers right-aligned, row height 40. |
| Toast | Ink pill with Paper text, bottom center, 4s. |
| Icons | Lucide, 1.5px stroke, 16 or 20px. Never emoji [P3]. |
| Focus | Visible 2px Forest ring with 2px offset on every interactive element [P3]. |

### 4.3 Landing page structure

1. **Hero:** headline with one serif accent word, a single sentence, one Forest button plus one ghost button, and the animated errand loop (section 5) on the right. No stock image.
2. **Live receipts strip:** real receipts from the demo, printing in as errands complete.
3. **How it works:** three steps drawn as one continuous line (out and back), not three icon cards.
4. **Forest band (dark section):** measured results in huge mono numbers, with Crest highlights allowed.
5. **The villain:** Shady's card, showing the swap detected, the Bond slashed and the refund.
6. **Connect in one click:** client logos in monochrome Ink, with the copyable one-liner.
7. **PayPal flow:** the money diagram from `Paypal_hackathon.md`, redrawn in the palette.
8. **Footer:** small, cream, the tagline in serif italic.

**Nature imagery (optional, the "Perplexity nature" feel):** one or two full-bleed photographs as section breaks: ant trails, bees, a forest canopy. Errands are what colonies do. Show them as **Forest-and-Paper duotones** (an SVG `feColorMatrix` filter or a CSS blend over a Forest layer), so photos never add new colors. Use properly licensed images (Unsplash licence or our own) and credit them in the footer.

---

## 5. Motion and dynamic elements

### 5.1 Tokens

| Token | Value | Use |
|---|---|---|
| fast | 120ms | Hover, press |
| base | 200ms | Chips, toggles, tooltips |
| slow | 320ms | Cards entering, row re-sort |
| page | 480ms | Hero entrance, receipt print |
| ease-standard | `cubic-bezier(0.4, 0, 0.2, 1)` | Default |
| ease-out-soft | `cubic-bezier(0.32, 0.72, 0, 1)` | Things arriving |
| ease-emphasis | `cubic-bezier(0.2, 0, 0, 1)` | Stamps, counters landing |

Values follow the Perplexity system [P2]. Animate only `transform` and `opacity` (plus `stroke-dashoffset` and `clip-path` where noted), so nothing reflows.

### 5.2 Website interactions: scroll

The landing page should feel like it responds to the reader. Scroll effects are tied to scroll position (they scrub forward and back with the wheel) or fire once on entry. Use CSS scroll-driven animations (`animation-timeline: view()` and `scroll()`) where supported, and an `IntersectionObserver` fallback elsewhere. Scroll-driven timelines ship in Chrome and Edge 115+ and Safari 26+, while Firefox stable still has them behind a flag [P5][P6], so wrap them in `@supports (animation-timeline: view())`. No scroll event listeners, no animation libraries.

| # | Where | Effect | How |
|---|---|---|---|
| S1 | Top of page | A 2px Mandarin **reading-progress line** fills left to right as you scroll. | `animation-timeline: scroll(root)` on `scaleX` |
| S2 | Navbar | Starts transparent and roomy; after ~24px of scroll it gains the Card background, a hairline and shrinks from 72px to 56px. | A sentinel element plus `IntersectionObserver` toggling a class; 200ms transition |
| S3 | Hero headline | On load, words rise out of a mask one by one (40ms stagger); the serif accent word lands last and slightly slower. | `overflow: hidden` wrappers, `translateY(100%)` to `0`, 480ms ease-out-soft |
| S4 | Hero | As you scroll away, the errand-loop illustration drifts up slower than the text and fades (a light parallax). | `animation-timeline: view()` on `translateY` and `opacity`; max 40px of drift |
| S5 | How it works | **The out-and-back line draws itself as you scroll.** Each step lights up (Ink text, Forest dot) as the line reaches it; scrolling back undraws it. | SVG path, `stroke-dashoffset` bound to `view()`; steps use their own view timelines |
| S6 | Live receipts strip | The row of receipts slides sideways a little as you scroll past it, so the page feels alive even with no new errands. | `translateX` bound to `view()`, about 120px over the section |
| S7 | Results chapter | **The page background melts from Paper to Forest** as the results band enters, then back to Paper after it. Numbers count up when they become visible. | Background color keyed to a `view()` timeline on a full-bleed layer; count-up via `IntersectionObserver` (runs once) |
| S8 | Key phrases | Phrases like "only when it's verified" get a Mandarin underline that draws from the left when they reach the middle of the screen. | `background-size` from `0% 2px` to `100% 2px`, view timeline with `entry 40% cover 50%` range |
| S9 | Villain section | **Sticky storytelling:** Shady's card stays pinned while three short beats scroll past (swap detected, Bond slashed, refund sent), and the card updates at each beat. | `position: sticky` card plus `IntersectionObserver` on each beat |
| S10 | Nature photos | Duotone photos open with a clip reveal (an inset that widens) and settle from `scale(1.08)` to `1` as they pass. | `clip-path: inset()` and `scale` on a view timeline |
| S11 | Every section | Default entrance: fade up 16px, children staggered 60ms. Only once per element. | `IntersectionObserver` class toggle |

Rules for scroll effects: at most one "big" effect per screen height (S5, S7 or S9), small ones elsewhere; nothing may block reading or move text the user is reading; and scrolling must stay native, with no scroll-jacking or snap-trapping.

### 5.3 Website interactions: hover and press

Hover states are where polish shows. They live inside `@media (hover: hover) and (pointer: fine)`, so phones get clean tap states instead of stuck hovers.

| # | Element | Hover | Press / focus |
|---|---|---|---|
| H1 | Nav links | A Paper Deep **pill slides** under the hovered link and follows the cursor between links. | The active page keeps the pill |
| H2 | Text links | An underline grows from the left (Mandarin Deep); on leave it exits to the right. | Focus shows the 2px Forest ring |
| H3 | Primary and accent buttons | Background deepens and the trailing arrow icon nudges 3px right. | Scales to 0.98 for 120ms |
| H4 | Cards | Border goes from default to strong and the title shifts 2px right. No lift, no shadow (depth by contrast). | Whole card is the link target |
| H5 | **Receipts** | The receipt lifts 2px and tilts 0.5 degrees, a soft overlay shadow appears, and the perforated edge becomes visible. The one place a shadow is allowed. | |
| H6 | Runner cards (leaderboard) | A small pass-rate sparkline draws itself, and the price chip turns Mandarin. | |
| H7 | Lane chips | A tooltip (Ink pill) shows price, pass rate with sample size, and p95 latency. | Opens on focus too |
| H8 | Copy buttons on code snippets | Icon swaps to a check that draws itself, label says "Copied" for 1.5s. | Announced to screen readers |
| H9 | Client logos | Ink at 60% opacity, rising to 100% and Forest on hover. Never full brand colors. | |
| H10 | Forest band (optional) | A very soft lighter-Forest spotlight follows the cursor (radial gradient at about 8% opacity). | Off on touch and reduced motion |
| H11 | Footer tagline | The serif accent word slants a little more on hover. The page's one wink. | |

Timing: hovers use `--t-fast` (120ms) on enter and `--t-base` (200ms) on leave, so things respond instantly and settle gently.

### 5.4 Product story animations (demo, dashboards and video)

| # | Element | What it does | How |
|---|---|---|---|
| 1 | **Errand loop** (hero and logo) | A Mandarin dot leaves the big Sender circle, travels to the small Runner circle, and comes back. On return a Forest check draws itself. Loops every ~3s with a pause. | Inline SVG, `offset-path` or `stroke-dashoffset`, CSS keyframes |
| 2 | **Receipt print** | New receipts unroll top to bottom like a thermal printer, then the verified stamp lands (scale 1.15 to 1, slight rotation, 200ms). | `clip-path: inset()` animation over 480ms, then the stamp keyframe |
| 3 | **Savings counter** | "Saved $0.00" counts up to the real value whenever an errand settles. | `requestAnimationFrame` tween with an ease-out curve; Geist Mono with tabular numbers so digits don't jitter |
| 4 | **Escrow state** | While running, the amount chip shows slow-moving diagonal hatching ("held"). On verify, it fills Forest from left to right ("released"). On fail, it slides back to the wallet. | `repeating-linear-gradient` with an animated `background-position`; a `scaleX` fill |
| 5 | **Leaderboard re-sort** | When ratings change, rows glide to their new position instead of jumping. | FLIP: measure, invert with `transform`, play over 320ms |
| 6 | **Shady caught** | The Runner card does one small shake (two 4px cycles), the Bond bar drains by half, and a refund receipt prints in the Sender's feed. | Keyframes plus a `scaleX` drain; triggered once, never looped |
| 7 | **Scroll reveal** | Sections fade up 16px as they enter, children staggered by 60ms. | `IntersectionObserver` adding a class; runs once per element |
| 8 | **Composer placeholder** | The delegate box types example errands ("Solve: the sum of the first 50 primes...", "Write is_palindrome with tests...") and erases them. | A small JS loop, paused when the input has focus |
| 9 | **Live dot** | Mandarin dot pulses next to "running" and in the navbar when the demo is live. | `scale` and `opacity` keyframe at 1.6s |

### 5.5 Motion rules

- **Purpose test:** every animation must show a state change (sent, held, verified, slashed). Decoration-only motion gets cut.
- **One thing moves at a time** in a viewport, except the ambient live dot.
- **`prefers-reduced-motion: reduce`:** remove translations, shakes and loops. Keep opacity fades at half duration, and show the final state immediately (counters jump to the value, receipts appear printed) [P3].
- **Interruptible:** rapid updates may cancel an animation, but the final state and keyboard focus must always be correct [P3].
- **No scroll hijacking.** Perplexity's Comet launch page was criticized for it [P4].
- **Performance:** animate only `transform`, `opacity`, `clip-path`, `stroke-dashoffset` and background color on one layer. Use `will-change` only while an element animates. The whole interaction layer should fit in a few KB of vanilla JS in `app.js`.

---

## 6. Anti-slop checklist (before anything ships)

- [ ] Only Paper, Forest, Mandarin (plus semantic Brick and the optional Crest highlight) appear.
- [ ] No gradients except the escrow hatching and photo duotones. No glassmorphism, no glowing blobs.
- [ ] Headline has a specific claim with a real number, not "Supercharge your AI workflow".
- [ ] Every number shown is measured, and labelled with its sample size where it is a rate (BRANDING.md voice).
- [ ] Icons are Lucide SVGs, not emoji. Client logos are monochrome.
- [ ] No three-identical-icon-cards feature grid.
- [ ] Mandarin used as text only in Mandarin Deep. Ink text on Mandarin buttons.
- [ ] Visible focus ring, `cursor: pointer` on clickables, 4.5:1 text contrast [P3].
- [ ] Layout checked at 375, 768, 1024 and 1440px; chips and badges wrap instead of clipping [P3].
- [ ] Reduced motion tested: scroll effects become static, hovers keep color changes only.
- [ ] Scroll effects checked in Firefox (fallback path) and on a phone (no stuck hovers).
- [ ] Real product screens in the video and on the landing page, not mockups.

---

## 7. Implementation notes (for `errand/static/app.css`)

The current CSS already uses tokens (`--ink`, `--paper`, `--orange`...), so the reskin is mostly a token swap plus a few components:

```css
:root {
  --paper: #F4F0E6;  --card: #FBF9F4;  --paper-deep: #E9E3D4;
  --forest: #015D47; --ink: #0B2A21;   --moss: #4F6B61;
  --mandarin: #FD550A; --mandarin-deep: #B83F0A;
  --brick: #9E2B1E;  --brick-wash: #F4DCD6;  --crest: #E0F354;
  --line: rgba(11, 42, 33, 0.12); --line-strong: rgba(11, 42, 33, 0.20);
  --font-sans: "Geist", ui-sans-serif, system-ui, sans-serif;
  --font-serif: "Instrument Serif", Georgia, serif;
  --font-mono: "Geist Mono", ui-monospace, Menlo, Consolas, monospace;
  --t-fast: 120ms; --t-base: 200ms; --t-slow: 320ms; --t-page: 480ms;
  --ease: cubic-bezier(0.4, 0, 0.2, 1); --ease-out: cubic-bezier(0.32, 0.72, 0, 1);
}
:root[data-theme="dark"] {
  --paper: #0B1F19; --card: #12291F; --ink: #F4F0E6; --moss: #9DB3AA;
  --forest: #7FD1B0; --mandarin: #FF6B2C; --mandarin-deep: #FF6B2C;
}
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation-iteration-count: 1 !important; scroll-behavior: auto !important; }
  [data-scroll-fx] { animation: none !important; }  /* scroll-driven effects become static */
}
@supports (animation-timeline: view()) {
  @media (prefers-reduced-motion: no-preference) {
    .progress { transform-origin: left; animation: grow linear both; animation-timeline: scroll(root); }
    .reveal  { animation: fade-up linear both; animation-timeline: view(); animation-range: entry 0% entry 60%; }
  }
}
```

Mirror the dark tokens under `@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { ... } }`, as the current CSS does. Fonts load from Google Fonts (`Geist`, `Geist Mono`, `Instrument Serif`), replacing Inter and JetBrains Mono. AG Grid's Quartz theme reads CSS variables, so map `--ag-background-color`, `--ag-border-color`, `--ag-header-foreground-color` and `--ag-font-family` to these tokens. Update `logo.svg` to Forest strokes with a Mandarin dot.

---

## 8. Research notes

- **ui-ux-pro-max skill** [P3]: a searchable catalog (styles, 192 palettes, 74 font pairings, landing patterns) plus a pre-delivery checklist. The parts we adopted are its universal rules: no emoji icons, `cursor-pointer` on clickables, 4.5:1 contrast, visible focus, reduced motion, testing at 375/768/1024/1440, chips that wrap, status not by color alone, interruptible animations. Its anti-pattern lists flag "AI purple/pink gradients" for trust-sensitive domains, which is why the indigo reference was rejected.
- **Perplexity** [P1][P2]: rebrand by Smith & Diction, set in FK Display and FK Grotesk, palette of blues and teals with earthy tones. A third-party extraction of the site's tokens describes a warm cream canvas (`#fbf9f5`), warm charcoal text, one teal accent (`#20808d`), weights 400/500 only, pill buttons, 12px cards, depth from contrast rather than shadows, warm-tinted hairlines, and motion of 120/200/320/480ms with a 16px fade-up hero and 60ms stagger. We borrowed the structure (cream canvas, one deep color, sparing serif, quiet motion), not the colors or fonts. The hex values come from third-party extractions, not an official guideline.
- **Comet launch page** [P4]: a Hacker News thread criticized it for vague copy, giant hero images, scroll hijacking and no product screenshots. Errand does the opposite: specific copy, real screens.

### Sources

- [P1] Ebaq Design, "Perplexity rebrand" (Smith & Diction, FK Display and FK Grotesk). https://www.ebaqdesign.com/news/perplexity-rebrand
- [P2] Perplexity DESIGN.md (third-party token extraction: colors, type, spacing, motion). https://www.webdesignhot.com/design.md/perplexity/
- [P3] nextlevelbuilder, *UI UX Pro Max* skill (MIT). https://github.com/nextlevelbuilder/ui-ux-pro-max-skill
- [P4] Hacker News discussion of the Comet launch page. https://hn.nuxt.dev/item/44511527
- [P5] MDN / caniuse status as summarized in "Replace Your Scroll-Listener JS: CSS Scroll-Driven Animations Go Cross-Browser" (2026). https://www.buildmvpfast.com/blog/css-scroll-driven-animations-replace-js-2026
- [P6] ICS Media, "CSS Scroll-driven Animations without JavaScript". https://ics.media/en/entry/230718/
- Reference palettes: two images supplied by the founder (Mandarin Orange `#FD550A`, Forest Green `#015D47`, Crest Yellow `#E0F354`; Onyx Black, Electric Indigo, Tropical Mint).
