"""Smoke test with a stubbed EasyOCR reader — no torch needed.

Run:  python tests/smoke_test.py
Verifies the domain rules (assign_values) and the full pipeline
(filename parsing -> assignment -> Excel write -> backup).
"""
import sys
import tempfile
import types
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO))

# canned OCR output: (bbox, text, prob); bbox centers:
# 320nm@(530,110) 300nm@(330,210) 280nm@(130,310) 180nm@(430,410)
CANNED = [
    (((480, 100), (580, 100), (580, 120), (480, 120)), "Length: 320.00 nm", 0.95),
    (((280, 200), (380, 200), (380, 220), (280, 220)), "Length: 300.00 nm", 0.95),
    (((80, 300), (180, 300), (180, 320), (80, 320)), "Length: 280.00 nm", 0.95),
    (((380, 400), (480, 400), (480, 420), (380, 420)), "Length: 180.00 nm", 0.95),
    (((10, 10), (60, 10), (60, 30), (10, 30)), "noise", 0.2),  # below PROB_MIN
]


def install_stub():
    fake = types.ModuleType("easyocr")

    class Reader:
        def __init__(self, *a, **k):
            pass

        def readtext(self, img, **k):
            return CANNED

    fake.Reader = Reader
    sys.modules["easyocr"] = fake


def test_assign_rules():
    import extract_cd as ec

    m = [(320, 530, 110), (300, 330, 210), (280, 130, 310), (180, 430, 410)]
    values, susp, reason = ec.assign_values(["L1", "L3", "L5", "L3_TOP"], "A", m)
    assert not susp, reason
    assert values == {"L1": 320, "L3": 300, "L5": 280, "L3_TOP": 180}, values

    _, susp, reason = ec.assign_values(["L1", "L3"], "A", [(300, 1, 1)])
    assert susp and reason == "Мало измерений"

    _, susp, reason = ec.assign_values(["L1", "L3", "L5"], "A",
                                       [(300, 1, 1), (280, 2, 2)])
    assert susp and "из" in reason

    _, susp, reason = ec.assign_values(["L3", "L3_TOP"], "A",
                                       [(300, 1, 1), (280, 2, 2)])
    assert susp and "слишком близко" in reason

    _, susp, reason = ec.assign_values(["L1", "L3", "L5"], "A",
                                       [(150, 1, 1), (300, 2, 2), (440, 3, 3)])
    assert susp and "разброс" in reason

    vals, susp, _ = ec.assign_values(["L1", "L3", "L5", "L3_TOP"], "A",
                                     [(320, 1, 1), (999, 2, 2)])  # 999 out of range
    assert susp  # only one valid reading left
    print("assign rules OK")


def test_end_to_end():
    install_stub()
    import extract_cd as ec
    import make_demo_data

    with tempfile.TemporaryDirectory() as tmp:
        demo = Path(tmp)
        make_demo_data.main(demo)
        sys.argv = ["extract_cd.py",
                    "--image-dir", str(demo / "img"),
                    "--excel", str(demo / "results.xlsx")]
        ec.main()

        df = pd.read_excel(demo / "results.xlsx")
        row_a = df.iloc[0]  # S1, direction A
        assert row_a["L1 [нм]"] == 320 and row_a["L3 [нм]"] == 300, row_a
        assert row_a["L5 [нм]"] == 280 and row_a["L3_TOP [нм]"] == 180, row_a
        assert (demo / "Backup").glob("backup_*.xlsx") is not None
        assert list((demo / "Backup").glob("backup_*.xlsx")), "backup missing"
    print("end-to-end OK")


if __name__ == "__main__":
    test_assign_rules()
    test_end_to_end()
    print("ALL SMOKE TESTS PASSED")
