# Private scripture PDF sources

The source PDFs are stored only in the private repository
[`lettermanagementorthosgpgi-coder/jyotirling-scripture-storage`](https://github.com/lettermanagementorthosgpgi-coder/jyotirling-scripture-storage).

The `channel-audit.yml` workflow checks out that private repository into a temporary GitHub Actions runner directory using the repository secret `SCRIPTURE_STORAGE_TOKEN`. It then copies the two files into the exact local paths expected by `src/scripture_sources.py`:

- `scripture_sources/pdfs/shiv_puran.pdf` — provisioned from `468980196-शिव-पुराण-shiv-puran-complete-pdf.pdf`.
- `scripture_sources/pdfs/bhagavad_gita_yatharoop.pdf` — provisioned from `bhagvat_gita_as_it_is_-_hindi.pdf`.

The token must be a fine-grained GitHub Personal Access Token restricted to the private scripture repository with **Contents: Read-only** permission. Add it only as an Actions secret named `SCRIPTURE_STORAGE_TOKEN` in the AI Channel Manager repository. Never commit the token or either PDF to this public repository.

The PDFs are present only on the ephemeral runner during a workflow run; they are not uploaded as workflow artifacts or committed to Git. If the secret is missing or access is denied, the workflow fails at the private checkout rather than silently pretending that scripture lookup succeeded.

The adapter returns short, page-numbered evidence excerpts only. It labels the material as Hindi translation/explanatory text and instructs the AI not to misattribute commentary as an original Sanskrit verse or a verbatim divine statement. Verify OCR/extraction quality for the Shiv Puran PDF before relying on a passage.
