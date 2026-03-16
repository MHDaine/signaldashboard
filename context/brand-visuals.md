# MarketerHire Brand Visual Identity

**Source**: https://marketerhire.com/
**Extracted**: February 2026
**Platform**: Webflow (site.marketerhire.com)

---

## Color System

### CSS Root Variables (Design Tokens)
```css
--gray: #f8f8f8;
--black: #141414;
--white: white;
--primary-1: #6affdd;          /* Mint/Aqua - primary CTA color */
--primary-2: #ff44fe;          /* Hot pink/magenta - secondary accent */
--primary-3: yellow;           /* Tertiary accent */
--danger: #da2424;
--warning: #ff9f1c;
--50-black: #00000080;         /* 50% black overlay */
--light-green: #eafff7;        /* Honeydew - trusted-by section bg */
--mh-purple: #440177;          /* MarketerHire brand purple */
--honeydew: #eafff7;
--darker-grey: #8d8d8d;
--light-pink: #ffe1ff;
--light-purple: #e1dff9;
--ghost-white: #f0effc;
--true-black: black;
--faded-green: #eafff76e;      /* Transparent honeydew */
--ghost-white-2: #f7f6fe;
--aqua: #6bfcdc;
--fcde3d: #fcde3d;             /* Gold */
--fadf5c-gold: #fadf5c;        /* Light gold */
--760064-purple: #760064;      /* Deep purple */
--green: #00645e;              /* Dark green */
--ff52e5-orchid: #ff52e5;      /* Orchid pink */
--mint-cream: #ecfbf5;
--eefef7-mint-cream: #eefef7;
--1b0030-midnight-blue: #1b0030;
--057030-dark-green: #057030;
--de3939-crimson: #de3939;
--c7f1df-pale-turquoise: #c7f1df;
```

### Primary Brand Colors

| Role | Hex | Name | Usage |
|------|-----|------|-------|
| **Primary CTA** | `#6AFFDD` / `#6BFFDC` | Mint/Aqua | All CTA buttons ("Hire Marketers"), nav buttons, links |
| **Secondary Accent** | `#FF44FE` / `#FF52E5` | Hot Pink/Orchid | Energy accents, highlight moments |
| **Gold Accent** | `#FCDE3D` / `#FADF5C` | Gold/Yellow | Newsletter section background, tertiary highlights |
| **Brand Purple** | `#440177` / `#760064` | MH Purple | Legacy brand accent, help center headers |
| **Dark (Body/Headings)** | `#141414` | Near-Black | Primary text color, dark sections |
| **Light Background** | `#F8F8F8` | Off-White/Gray | Standard section backgrounds |
| **White** | `#FFFFFF` | White | Page background, card backgrounds, navbar |
| **Honeydew** | `#EAFFF7` | Mint-Tinted White | Trusted-by section, social proof areas |

### Text Colors

| Role | Hex | Usage |
|------|-----|-------|
| **Primary Text** | `#141414` (var: `--black`) | Headings, body copy on light backgrounds |
| **Secondary Text** | `#00000080` (50% black) | Stat labels, subtext, deemphasized copy |
| **Darker Grey** | `#8D8D8D` | Tertiary text, logo marquee labels |
| **White Text** | `#FFFFFF` | Text on dark sections, button text on dark bg |
| **Orange** | (class: `text-color-orange`) | Accent text highlights |
| **Pink** | (class: `text-color-pink`) | Accent text highlights |
| **Purple** | (class: `text-color-purple`) | Accent text highlights |

---

## Typography

### Font Family
```css
font-family: Work Sans, sans-serif;
```
**Work Sans** is the primary typeface across the entire site. Used for all headings, body text, navigation, buttons, and UI elements.

Webflow also loads **PT Serif** and **Open Sans** (visible in the `<html>` class attributes), but **Work Sans** is the only font applied to visible elements.

### Heading Scale

| Level | Size (Desktop) | Size (Mobile) | Weight | Line-Height |
|-------|---------------|---------------|--------|-------------|
| **H1** | `4rem` (64px) | `3.25rem` (52px) | 700 (Bold) | 1.2 |
| **H2** | `4rem` (64px) | `2.75rem` (44px) | 700 | 1.2 |
| **H3** | `2.5rem` (40px) | `2.25rem` (36px) | 700 | 1.2 |
| **H4** | `1.9rem` (30.4px) | `1.75rem` (28px) | 700 | 1.2 |
| **H5** | `1.5rem` (24px) | `1.25rem` (20px) | 700 | 1.4 |
| **H6** | `1.25rem` (20px) | `1.125rem` (18px) | 700 | 1.4 |

### Body Text Scale

| Type | Size (Desktop) | Size (Mobile) | Weight | Line-Height |
|------|---------------|---------------|--------|-------------|
| **Large** | `1.25rem` (20px) | `1.1rem` | 400 | 150% |
| **Medium** | `1.125rem` (18px) | `1rem` | 400 | - |
| **Regular** | `1rem` (16px) | - | 400 | - |
| **Small** | `0.875rem` (14px) | - | 400 | - |
| **Stat Numbers** | Large display | - | 700 | - |
| **Stat Labels** | `1.125rem` (18px) | `1rem` | 500 (Medium) | - |

### Hero Subheading
```css
.hero__subheading {
  font-size: 24px;
  line-height: 33px;
}
```
Used for descriptive text below the main hero headline.

### Tagline/Section Label Style
```css
.text-style-tagline {
  font-weight: 600;
  display: inline-block;
}
```
Section labels like "WHY MH?", "pricing", "how it works" use semi-bold weight as inline tags.

### Key Typography Traits
- **All headings bold (700)** with tight 1.2 line-height for H1-H4
- **Semi-bold (600)** for buttons, taglines, nav links, pill labels
- **Medium (500)** for stat labels and secondary emphasis
- **No letter-spacing adjustments** on the main site headings (unlike MH-1 which uses `-0.05em`)
- **No italic or decorative styles** used anywhere
- **FAQ questions**: `font-size: 22px; font-weight: 800` (extra bold for accordion headers)

---

## Button Styles

### Primary CTA (Mint Green)
```css
.button {
  background-color: var(--primary-1);  /* #6affdd */
  color: var(--white);
  text-align: center;
  cursor: pointer;
  border-radius: 0;
}

.button.button-large {
  background-color: var(--primary-1);
  color: var(--black);
  border-radius: 0;
  margin-top: 32px;
  padding: 18px 64px;
  font-family: Work Sans, sans-serif;
}
```
- **Mint/aqua green** (`#6BFFDC`) background
- **Sharp corners** - `border-radius: 0` (no rounding on main site buttons)
- **Dark text** on light button background
- **Large padding** for primary CTAs
- Labels: **"Hire Marketers"** (primary), **"Learn More"** (secondary)

### Nav Bar CTA
```css
.nav-bar-button {
  background-color: #6bffdc;
  border-style: none;
  border-color: #14141400;
  border-radius: 0;
  font-family: Work Sans, sans-serif;
}
```
Same mint green, sharp corners, integrated into navbar.

### Reassurance Text (Below CTAs)
- "Only pay if you hire. Two-week trial"
- "No commitment, two-week trial"
- Pattern: brief risk-reversal statement immediately below every CTA

### Key Button Difference from MH-1
The main MarketerHire site uses **sharp-cornered (border-radius: 0)** mint buttons, while the MH-1 landing page uses **8px rounded corners with a 3D border effect**. The main site buttons are flatter and more minimal.

---

## Layout & Spacing

### Navbar
```css
.navbar {
  z-index: 1;
  background-color: var(--white);
  height: 90px;
  font-family: Work Sans, sans-serif;
  display: flex;
}
```
- White background, 90px tall
- 3-column grid: logo | nav links | CTA button
- Nav links: `font-weight: 600`, with hover opacity fade (`opacity: 0.5`)
- Dropdown menus: gray background (`var(--gray)`)

### Section Padding
```css
/* Standard sections */
.section {
  background-color: var(--gray);  /* #f8f8f8 */
  padding-top: 72px;
  padding-bottom: 72px;
  font-family: Work Sans, sans-serif;
}

/* Hero */
.hero-section.hero-home {
  margin-top: 30px;
  padding-top: 40px;
  padding-bottom: 10px;
}

/* White hero wrapper */
.white-section {
  padding-top: 192px;    /* Desktop */
  padding-bottom: 128px;
  /* Mobile: 148px / 96px */
}
```

### Border Radius

| Element | Radius |
|---------|--------|
| Standard cards | `8px` |
| Testimonial cards | `20px` |
| FAQ accordion | `16px` |
| Buttons (primary) | `0px` (sharp) |
| Help center cards | `0px` + `1px solid border` |

### Card Design
```css
.card {
  background-color: var(--gray);  /* #f8f8f8 */
  direction: ltr;
  border-radius: 8px;
  flex-direction: column;
  display: flex;
}

.card-body {
  padding: 36px;
  /* small variant: 25px */
}
```
- Light gray backgrounds on white page backgrounds
- 8px border radius
- 36px internal padding
- Flex column layout

---

## Component Patterns

### Hero Section
```
[Trustpilot widget - 4.9/5 rating badge]
[H1 Headline - "Elite Marketing Experts On Demand"]
[Subheading - descriptive paragraph, 24px]
[Bullet features with checkmarks]
[Primary CTA button - "Hire Marketers"]
[Risk reversal text]
[Stats row: 30,000+ | 6,000+ | 95%+ | Top 1%]
```
The hero uses a light/white background with the primary headline centered above social proof elements.

### Stat Display
```css
.stats8-mh_number {
  /* Large bold display number */
}
.stat-text-mh {
  color: #00000080;   /* 50% black */
  font-size: 1.125rem;
  font-weight: 500;
}
```
Stats shown: "30,000+ Successful matches", "6,000+ Happy customers", "95%+ Trial-to-hire rate", "Top 1% Marketing Talent"

### Logo Marquee (Social Proof)
```css
.logo-wall__line {
  flex-wrap: nowrap;
  align-content: flex-start;
  align-items: center;
  display: flex;
  overflow: hidden;
}
```
- Scrolling/wrapping row of client logos
- Brands: Stripe, Netflix, Airbnb, Perplexity, Palantir, Plaid, Deel, Lyft, Glassdoor, GoFundMe, Skillshare, True Classic, Square, Tinuiti
- Set against honeydew (`#EAFFF7`) or white backgrounds

### Bento Grid (Dream Marketers Section)
Three feature cards in a grid layout:
1. **Experts Who Have Done What You Need** - with "results bento" image
2. **Matched to Your Industry, Scale & Tools** - with "proven bento" image
3. **Available Now, Satisfaction Guaranteed** - with "speed bento" image

Cards use webp images as visual backgrounds with overlay text.

### Tabbed Roles Section
```css
.layout491-mh_tab-link {
  /* Tab navigation for role categories */
}
.layout491-mh_tab-pane {
  /* Tab content panels */
}
```
Four tabs: Full-Stack Growth | Performance Paid | C-Suite Leadership | Other Specialists
Each tab shows: description, bullet features, and a role card image.

### How It Works (Timeline Steps)
```css
.hiw-card-mh {
  /* Step cards with images */
}
.step-pill {
  /* "Today" / "This Week" / "This Month" labels */
}
```
Three-step timeline: Describe Your Needs > Meet Your Expert > Watch Results Roll In

### Testimonial Cards
```css
.testimonial18-mh_card {
  /* Individual testimonial card */
}
.testimonials-card__paragraph {
  padding: 30px;
  font-family: Work Sans, sans-serif;
  font-size: 16px;
  font-weight: 400;
  line-height: 150%;
}
.testimonial__cards--container {
  grid-column-gap: 32px;
  grid-template-columns: 1fr 1fr 1fr;
  display: grid;
}
```
- Headline metric: "3x More Profitable Campaigns", "18 Months Work in 1 Week"
- Quote text in 16px regular weight
- Person photo + name + title + company logo
- 3-column grid on desktop

### Comparison Table
```css
.comparison11-mh_component {
  /* MH vs In-House vs Freelance comparison */
}
.table-grid {
  background-color: #fff;
  grid-template-rows: auto auto auto auto auto auto auto;
  grid-template-columns: 1.5fr 1fr 1fr;
}
```
Three-column comparison: MarketerHire | In-House Hire | Freelance Platform
Rows: Time to Hire, Pre-vetted, Cost, Cost of Failure, Free Rematching, Termination Fees

### FAQ Accordion
```css
.faq2-mh_accordion { /* Wrapper */ }
.faq-question {
  cursor: pointer;
  align-items: center;
  height: 90px;
  font-size: 22px;
  font-weight: 800;
}
.faq-question-wrap-2 {
  background-color: #fff;
  border-radius: 16px;
  margin-bottom: 20px;
  overflow: hidden;
}
```
- White card background with 16px radius
- Extra-bold (800) question text at 22px
- Collapsible answer panels

### Join/CTA Footer Section
```css
.join-mh-section { /* Full-width CTA block */ }
.join-mh__big-text { /* Large headline */ }
.join-mh__buttons { /* Dual CTA: Hire Marketers | Apply as Freelancer */ }
```

### Newsletter Section
- Yellow/gold background (`#FCDE3D`)
- "Get the best marketing newsletter by the best marketers"
- Email signup form

### Footer
```css
.main-footer-black {
  /* Dark footer section */
}
.footer-menu__link {
  /* Navigation links */
}
```
- Dark/black background
- Multi-column link layout: Roles for hire | About MH | Contact us
- Social icons: Facebook, X/Twitter, LinkedIn, Instagram
- Locations: San Francisco, Chicago, Los Angeles

---

## Visual Language & Imagery

### Light Mode Dominant
The main MarketerHire site uses a **light/white aesthetic** as its primary mode. Key backgrounds:
- **White** (`#FFFFFF`) - hero, cards, FAQ
- **Off-white/gray** (`#F8F8F8`) - standard sections
- **Honeydew** (`#EAFFF7`) - social proof/trust sections
- **Green** (`#E2FFF2`) - accent sections
- **Black** (`#141414`) - footer, select dark sections
- **Gold** (`#FCDE3D`) - newsletter section

### Key Visual Elements

1. **Trustpilot Widget**: 4.9/5 star rating prominently displayed in the hero with green Trustpilot branding

2. **Bento-Style Image Cards**: WebP images with rounded corners showing abstract/illustrated marketing concepts (results charts, matching UI, speed indicators)

3. **Role Specialty Cards**: Visual cards for each marketing discipline showing the available talent types

4. **Step-by-Step Timeline**: "Today > This Week > This Month" progression with pill labels and descriptive cards

5. **Client Logo Wall**: Horizontal scrolling band of grayscale/muted client logos on honeydew background

6. **Testimonial Grid**: 3-column grid of quote cards with headshot photos, client metrics as headlines

7. **Comparison Table**: Clean grid comparing MH vs alternatives with checkmarks and cost indicators

### Photography Style
- **Real headshots** of testimonial clients and marketers (not stock photography)
- **Illustrated/abstract cards** for feature explanations (bento-style webp graphics)
- **Company logos** in muted/grayscale treatment

### Iconography
- **Checkmark icon** (`icon_check.svg`) for feature lists and comparison table
- **Minimal line-style icons** for navigation and UI elements
- **Star rating** display for Trustpilot integration

---

## Overall Brand Aesthetic

| Attribute | Description |
|-----------|-------------|
| **Mood** | Professional, trustworthy, results-oriented |
| **Color Palette** | White/light backgrounds + mint green CTAs + honeydew social proof |
| **Typography** | Clean, bold sans-serif (Work Sans), high contrast hierarchy |
| **Layout** | Generous whitespace, grid-based cards, horizontal logo scrolling |
| **Visual Effects** | Minimal - no gradients or glows on main site (unlike MH-1) |
| **Imagery** | Mix of real headshots + illustrated bento cards |
| **Tone** | Confident but approachable, metrics-driven, trust-building |
| **CTA Style** | Sharp-cornered mint green buttons with risk-reversal text |

### Design Personality
- **Trustworthy** - Trustpilot rating, real client testimonials, enterprise logos
- **Results-focused** - Metric-led headlines ("3x More Profitable", "+400% Demo Calls")
- **Simple/clean** - White backgrounds, single font, generous spacing, sharp button edges
- **Accessible** - Clear hierarchy, large touch targets, readable contrast
- **Professional but friendly** - FAQ tone is conversational, CTA copy reduces friction

### Key Differences: Main Site vs MH-1 Landing Page

| Element | Main Site (marketerhire.com) | MH-1 (/mh1) |
|---------|----------------------------|--------------|
| **Background** | Light/white dominant | Dark mode dominant |
| **Button radius** | 0px (sharp corners) | 8px (rounded) |
| **Button style** | Flat mint, no border | 3D border + gradient |
| **Visual effects** | None (clean/minimal) | Glows, gradients, orbs |
| **Imagery** | Real photos + illustrations | Abstract data viz only |
| **Mood** | Professional/trustworthy | Futuristic/premium tech |
| **CTA label** | "Hire Marketers" | "Book Appointment" |
| **Pricing** | $5K-$20K+/mo range | $30K/mo single tier |
| **Hero heading letter-spacing** | Normal | -0.05em (tight) |

---

## Logo

- **Primary Logo (Horizontal, White BG)**: `https://cdn.prod.website-files.com/5ec70e2719e95acb889006a3/63bdb49e64e30aef66616690_MH-full-logo-lockup-horizontal-on-white%20(2).png`
- **Primary Logo (Vertical, Black BG)**: `https://cdn.prod.website-files.com/5ec70e2719e95acb889006a3/65a6e13ee1e6ba04543475ab_MH-full-logo-lockup-vertical-on-black%201%20(1).svg`
- **OG Image**: `https://cdn.prod.website-files.com/5ec70e2719e95acb889006a3/6250be9b66c2423cf2d71534_MH-full-logo-lockup-horizontal-on-white.png`
- **Favicon**: `https://cdn.prod.website-files.com/5ec70e2719e95acb889006a3/64e60315b0e64d79268779bd_Safeimagekit-resized-img.png`

---

## Quick Reference: Color Palette

```
PRIMARY BRAND COLORS
#6AFFDD  ████  Mint green - primary CTA / link color
#6BFFDC  ████  Mint green - button backgrounds
#FF44FE  ████  Hot pink - secondary accent
#FF52E5  ████  Orchid pink - accent variant
#440177  ████  MH Purple - brand purple
#FCDE3D  ████  Gold - newsletter section / tertiary

TEXT COLORS
#141414  ████  Near-black - primary headings & body
#000000  ████  True black - bold emphasis
#00000080 ████  50% black - stat labels, secondary text
#8D8D8D  ████  Darker grey - tertiary text
#FFFFFF  ████  White - text on dark backgrounds

BACKGROUNDS
#FFFFFF  ████  White - hero, cards, navbar
#F8F8F8  ████  Off-white - standard sections
#EAFFF7  ████  Honeydew - trust/social proof sections
#E2FFF2  ████  Light green - accent sections
#141414  ████  Near-black - footer, dark sections
#000000  ████  Black - dark sections

ACCENT BACKGROUNDS
#FFE1FF  ████  Light pink
#E1DFF9  ████  Light purple
#F0EFFC  ████  Ghost white
#ECFBF5  ████  Mint cream
#C7F1DF  ████  Pale turquoise
```
