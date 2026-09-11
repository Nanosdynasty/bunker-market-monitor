# Bunker Market Monitor design system

## Product and information architecture

- Private-evaluation operational web app for comparing bunker fuel price observations from Bulugo and OilPriceAPI.
- Three primary destinations only: Dashboard, Compare, Sources.
- First scan answers: whether data is current, which ports have coverage, latest prices by grade and provider, and how providers differ.
- Dashboard contains a compact status/navigation bar, a responsive grid of up to 15 port cards, and one dominant selected-port time-series chart.
- Compare contains a compact filter row and one sortable provider-comparison table.
- Sources contains provider status/diagnostic cards and a dense normalized-observation grid.
- Never present demo or cached data as live. Current, stale, partial, rate-limited, unavailable, no-data, and demo states require text plus an icon or dot.

## Visual direction

- Match the supplied Howe Robinson references closely in hierarchy, density, spacing, and proportions while using original markup and components.
- Technical-minimalist structure: flat 2D surfaces, generous page whitespace, precise 1px hairlines, compact controls, restrained rounding, no decorative imagery, no gradients, and no heavy shadows.
- Light theme: canvas `#F6F9FC`, cards `#FFFFFF`, primary ink `#0B2245`, secondary text `#64748B`, borders `#DCE4EE`.
- Dark theme: canvas `#071828`, cards `#0D2236`, elevated cards `#112A41`, primary text `#F2F7FC`, secondary text `#9CB0C5`, borders `#294258`.
- Brand/accent blue `#0B5DBB`; active navigation underline `#1268D6`; restrained red accent `#F04455` only for negative movement and errors.
- Semantic colors: positive/current `#159A55`, warning/stale `#D78A12`, error/negative `#E8404D`, neutral/info `#4D79A7`.
- Series colors: Bulugo `#0B5DBB`; OilPriceAPI `#159A55`. Fuel-grade context may use VLSFO blue, HSFO red, MGO green, but provider comparison is always distinguishable by labels and line styles as well as color.

## Typography and spacing

- Use the system sans stack `Inter, Segoe UI, Arial, sans-serif`; do not load external fonts.
- Page title 32px/700; section title 20px/700; card port name 18px/700; values 16px/650; body 14px; metadata 12px.
- Use tabular numerals for prices, deltas, dates, and quotas.
- Base spacing unit 4px; page gutters 32px desktop, 20px tablet, 16px mobile.
- Cards use 20px padding desktop and 16px mobile. Major vertical gaps 24px; internal rows 12px.

## Components

- Header is 72px desktop with wordmark left, three navigation links, connection state and refresh/theme controls right. On mobile use a 56px header and a compact second-row tab bar.
- Buttons are 36px high, 1px bordered, 6px radius, clear focus ring, no shadow. Primary buttons use brand blue; secondary buttons remain transparent.
- Cards use 1px borders, 8px radius, and no shadow. Port cards keep equal heights and divide fuel rows with hairlines.
- Status chips are compact inline-flex controls with a 7px dot, concise text, and a lightly tinted background.
- Tables use sticky headers, 40px rows, tabular numerals, horizontal scrolling inside the card, and no zebra striping.
- Chart is one focal Chart.js canvas in a large bordered card. Use direct end labels where feasible, a nearby legend/toggle row, restrained grid lines, and a visible `USD/MT` unit.

## Responsive behavior

- Port grid: five columns at 1400px+, three at 1024px, two at 700px, one below 560px.
- Never place filters before the live state on mobile. Dashboard cards appear before the chart; chart controls wrap without covering the plot.
- Compare and Sources tables remain within horizontally scrollable cards with sticky first columns.
- Touch targets are at least 40px. No interaction may depend on hover.

## Motion and accessibility

- Motion is limited to 120–180ms color, border, and opacity transitions. Respect `prefers-reduced-motion`.
- Provide visible keyboard focus, semantic headings, labelled controls, table captions, and live-region refresh messages.
- Maintain WCAG AA contrast. Never encode freshness, source, or price direction by color alone.

## Hard constraints

- Use only the colors, fonts, spacing, and component styles defined here.
- No sidebars, hero marketing section, news, maps, trading widgets, glassmorphism, gradients, large illustrations, or decorative animations.
- Keep the UI visually close to the supplied references while adapting Files into Sources and adding the Compare workspace.
