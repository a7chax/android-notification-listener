# Accessible editorial inbox

The user supplied an Officevibe style reference and requested larger, more
accessible typography. Apply that reference to the existing notification
inbox, retaining its app icons, history and live updates.

## Design and implementation

- Warm canvas `#f9f8f6`, white paper cards, cream `#f0e9e1` dividers, navy
  `#0c1754` headings, charcoal body, lavender selection, and cobalt actions.
- A centered 1200px workspace with top navigation, a large serif headline
  containing one italic phrase, 16px rounded cards and pill action buttons.
- Use local serif/sans fallbacks. Body and notification history: 18px with
  at least 1.6 line height. Controls and navigation: at least 16px. Secondary
  metadata: at least 14px, including on mobile. Darken the reference's pale
  Stone helper color so information remains readable.
- Controls have at least 44px targets, visible keyboard focus and adequate
  contrast. Add a skip link and keyboard access to scrollable history areas.
- Reflow at narrow widths and when text is enlarged; preserve all controls,
  live data, saved history and app identity. No marketing-only chat widget,
  fabricated statistics or unrelated product features.

## Verification

The interface agent owns `website/styles.css` and `website/index.html`.
The primary agent verifies computed text sizes/line heights, text contrast,
target sizes, keyboard navigation, narrow-screen reflow, enlarged text and
the existing fictional-data browser smoke flow. Use screenshots containing
fictional notifications only. This styling change needs no Android update.

Reference checks follow W3C's explanations of
[contrast](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html),
[reflow](https://www.w3.org/WAI/WCAG22/Understanding/reflow.html), and
[target size](https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html).
The 44px target is this project's more comfortable design choice.

## Completed checks

The live page was checked in headless Chrome at 1440, 1280, 768, 640, 390
and 320 CSS pixels. In the fictional-data fixture, all visible information
was at least 14px, normal text contrast was at least 5.26:1, controls met
the 44px target, and no horizontal page overflow occurred. Notification and
timeline body text is 18px with 1.7 line height at default settings.

Font sizes now use relative units with a 112.5% root. A 200% enlarged-root
text check produced 36px reading text with no horizontal overflow. Keyboard
checks verified the skip link, main-content focus, search shortcut, filter
navigation and a visible focus outline on the scrollable timeline.

The primary agent also fixed two accessibility issues in `website/app.js`:
unchanged polling status no longer replaces live-region text, and redrawing
a notification after a live update retains focus on the same notification.
Both behaviors were reproduced before the fixes and verified afterwards.

The existing browser smoke flow passed after the change, including search,
app filters/icons, history, export, refresh, mobile layout, offline/reconnect,
corrupt storage, cross-tab clearing and text safety. JavaScript syntax and
diff checks passed. Backend, Android and storage protocols were unchanged.

Visual checks used `/tmp/notification-editorial.png`,
`/tmp/notification-editorial-mobile.png`, and
`/tmp/notification-editorial-200-percent.png`, with fictional content only.
