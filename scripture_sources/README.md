# Private scripture PDF sources

The repository is public. Do not commit complete copyrighted book PDFs here.

The lookup adapter in `src/scripture_sources.py` expects the following files to be mounted privately in the workflow runner:

- `scripture_sources/pdfs/shiv_puran.pdf` — the Hindi Shiv Puran edition supplied by the channel owner.
- `scripture_sources/pdfs/bhagavad_gita_yatharoop.pdf` — the Hindi Bhagavad Gita Yatharoop edition supplied by the channel owner.

The current conversation uploads are not automatically available to GitHub Actions. A private runner-side provisioning mechanism must be configured before the lookup can return a match. Until then it reports `source_file_not_provisioned` and the AI must continue the existing 48-hour wait; it must not pretend that scripture lookup succeeded.

The adapter returns short, page-numbered evidence excerpts only. It labels the material as Hindi translation/explanatory text and instructs the AI not to misattribute commentary as a verbatim Sanskrit verse or divine statement. Verify OCR/extraction quality for the scanned Shiv Puran PDF before relying on a passage.

Do not store OAuth tokens, cloud credentials, signed download URLs, or other secrets in this folder or in Git.
