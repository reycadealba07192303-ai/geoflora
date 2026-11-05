# Content UI refresh

Updated October 25, 2026. The identification content now follows the botanical glass/clay navigation style: separate rounded photo and result cards, a three-step workflow, a sculpted leaf upload illustration, clearer controls and more readable typography.

The photo area keeps the existing upload/drop, preview, remove and change actions. It prevents file changes while analysis or GPS handoff is running. Empty, loading, identified, uncertain and unavailable states are styled separately. Ready-state text now correctly prompts for a photo instead of claiming a model still needs installation. Results include model-score bars, species information, references, unverified feedback and current model scope. Scores retain their original meaning and abstention threshold.

Shared content cards, form fields, focus styles and small text were adjusted across the workspace. Form/fieldset minimum widths were corrected for mobile. The navigation styling stays scoped separately. The active model, dataset, consent defaults and report storage logic were not changed.

Validation:

- TypeScript and production build passed.
- Real Chrome uploads of existing held-out photos exercised an identified Hagonoy result and an uncertain water-hyacinth result.
- Verified the disabled initial identify action, upload-to-enabled transition, species descriptions, editable feedback, suggested-name handoff and auto-selection in Reported species.
- Verified optional training consent stays unchecked; the browser check did not submit any report.
- Checked desktop at 1440x1050 and mobile at 390x844. Identification and the report form with an uploaded photo both have document scrollWidth 390 at a 390px viewport.
- Preview screenshots are in storage/logs/ui-preview: identification-empty-desktop.png, identification-match-desktop.png, identification-uncertain-desktop.png, identification-empty-mobile.png, report-content-desktop.png and report-content-mobile.png.
