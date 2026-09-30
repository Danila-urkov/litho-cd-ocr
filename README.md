# litho-cd-ocr

**Automated extraction of CD measurements ("Length: XXX.XX nm") from annotated SEM images of resist structures, written into an Excel metrology report — with validation and human-review flagging.**

Python · EasyOCR · OpenCV · pandas

A personal automation prototype built while working as a design engineer in an optical lithography group. The metrology workflow used to require manually re-typing measurement values from ~100 annotated SEM images per batch into an Excel report — about 30 minutes of error-prone typing. This tool does it in 10–15 minutes, unattended, and flags anything suspicious for human review instead of failing silently.

## How it works

1. **Parse** the file name: `plate_S12_A.bmp` → sample group `S12`, scan direction `A`.
2. **OCR** the annotations with EasyOCR (confidence floor 0.4), extracting the first number of each label and the label's position on the image.
3. **Validate** readings: physically plausible CD window 100–450 nm; enough readings for the expected columns.
4. **Assign** values to `L1 / L3 / L5 / L3_TOP` using domain rules:
   - `L3_TOP` = minimum reading;
   - the remaining readings are ordered **spatially**, and the axis depends on the scan direction (`A`: −x, `B`/`C`: −y, `D`: +y); then `L1` = first, `L5` = last, `L3` = middle.
5. **Flag** suspicious results instead of writing them blindly:
   - fewer readings than expected columns;
   - overall spread > 160 nm;
   - in L3+L3_TOP-only mode: the L3−L3_TOP difference must stay inside 50–280 nm.
   Suspicious images are listed at the end for manual review.
6. **Write** results into the Excel report: rows are grouped by S-number, four consecutive rows per group (directions A–D). A timestamped backup of the report is made before every run.

## Input contract

- Images: `*.bmp` named `..._S<number>_<A|B|C|D>.<ext>`.
- Excel: first column contains the group label (`S12`), headers as in `COLUMN_MAP` (`L1 [нм]`, `L3 [нм]`, `L5 [нм]`, `L3_TOP [нм]` — adjust the map if your report spells them differently).

## Quick start (no accounts, no real data)

```bash
pip install -r requirements.txt

python make_demo_data.py          # demo/ with template Excel + synthetic images
python tests/smoke_test.py        # runs the pipeline with a stubbed OCR reader
```

The synthetic images mimic the annotation layout; real metrology images belong to the employer and are never published here.

## Real usage

```bash
python src/extract_cd.py --image-dir ./photos --excel ./report.xlsx \
    --expected L1,L3,L5,L3_TOP
```

In Google Colab: mount Drive, then pass the mounted paths via the same CLI flags.

## Status & known limitations

- Prototype, tuned to one annotation style and one report layout.
- EasyOCR can confuse visually similar digits (e.g. 6 vs 8) at low contrast — logged, not hidden; the suspicious-flag pipeline is the mitigation layer.
- Validation thresholds (100–450 nm window, 160 nm spread, 50–280 nm L3 window) are empirical values observed on real data.

### Fixed vs. the original notebook

- Edge case: with an expected-columns list that did not include `L3_TOP`, the original skip-check would have dropped every file; the check now only covers expected columns.
- Hard-coded Colab paths replaced by CLI arguments; EasyOCR import made lazy so the module is testable without torch.

## Honesty note

The first draft of the code was produced with AI coding assistants. The pipeline architecture, domain rules and validation were designed and verified by me — and I can walk through every function (see `tests/smoke_test.py` for the rules I consider load-bearing).

## License

MIT
