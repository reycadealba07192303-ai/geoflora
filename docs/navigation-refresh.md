# Navigation refresh

Updated October 25, 2026. The existing GeoFlora navigation now uses a floating frosted-glass sidebar and top bar, subtle clay shadows, a botanical green palette and consistent Lucide outline icons. No extra icon or styling packages were added.

Desktop keeps the six workspace destinations. Mobile uses a drawer for the full menu plus a bottom Home / Identify / Map dock. The top-bar New sighting button opens the existing report form. Identification-to-report handoff and report-to-map callbacks remain in App.tsx. Static notification/search/settings placeholders and the stale navigation review count were removed from the shell.

Keyboard support includes a skip link, visible focus indicators, Escape to dismiss the drawer, focus return to its opener, a drawer focus loop, background scroll locking and reduced-motion styles. On short screens, the decorative field-note card is hidden to leave room for navigation.

Implementation: apps/web/src/components/app-shell.tsx, apps/web/src/styles.css and apps/web/src/App.tsx.

Validation: TypeScript and production build passed. A real headless Chrome session checked all five non-home destination buttons, the report action, mobile Identify action, drawer open/close and focus restoration. A 390px viewport had document scrollWidth 390, with no horizontal overflow. Desktop was visually inspected at 1440x1050 and mobile at 390x844. Preview screenshots are under storage/logs/ui-preview. These checks verify navigation behavior and rendering; existing placeholder catalog/review destinations were not implemented by this visual update.
