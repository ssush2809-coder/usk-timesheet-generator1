# USK Timesheet Generator (Improved Signature + Alignment Version)

This updated version adds:
- background removal for the employee signature
- option to trim empty margins around the signature
- support for most common image formats for signature upload
- a remove-saved-signature button
- improved date alignment on the PDF
- a slimmer employee signature placement so it looks closer to the supervisor signature style

## Files to upload to GitHub root
- app.py
- timesheet_engine.py
- storage.py
- requirements.txt
- runtime.txt
- default_overlay_config.json
- README.md
- template.pdf

## Notes
- Keep `template.pdf` in the repo root.
- The app saves the processed employee signature as a transparent PNG.
- If the signature still looks slightly off, use the **Advanced: adjust overlay positions** section in the app.
