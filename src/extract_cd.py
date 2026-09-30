"""extract_cd.py — automated extraction of CD measurements from annotated SEM images.

Pipeline (originally developed in Google Colab):
  1. Parse sample group and direction from file names like `plate_S12_A.bmp`.
  2. OCR the measurement annotations ("Length: XXX.XX nm") with EasyOCR.
  3. Validate readings and assign them to L1 / L3 / L5 / L3_TOP using domain rules.
  4. Write results into an Excel report: rows are grouped by S-number,
     four consecutive rows per group, one per direction A-D.

Runs locally. In Colab, mount Drive and pass the mounted paths via CLI.
"""

import argparse
import re
import shutil
from datetime import datetime
from pathlib import Path

import cv2
import pandas as pd

# ------------------------------------------------------------------- config
PROB_MIN = 0.4                      # EasyOCR confidence floor
VALUE_MIN, VALUE_MAX = 100, 450     # physically plausible CD range, nm
RANGE_MAX = 160                     # max spread between readings, nm
L3_TOP_DIFF_MIN = 50                # sanity window for L3 - L3_TOP, nm
L3_TOP_DIFF_MAX = 280

DIRECTION_ROW_OFFSET = {"A": 0, "B": 1, "C": 2, "D": 3}

# Excel headers; adjust if your report spells them differently
COLUMN_MAP = {
    "L1": "L1 [нм]",
    "L3": "L3 [нм]",
    "L5": "L5 [нм]",
    "L3_TOP": "L3_TOP [нм]",
}


def parse_filename(name):
    """'plate_S12_A.bmp' -> ('12', 'A')."""
    match = re.search(r"_S(\d+)_([ABCD])\.", str(name), re.IGNORECASE)
    if match:
        return match.group(1), match.group(2).upper()
    return None, None


def extract_measurements(reader, image_path):
    """OCR one image -> list of (value_nm, x_center, y_center)."""
    img = cv2.imread(str(image_path))
    if img is None:
        print(f"Не удалось прочитать: {image_path.name}")
        return []
    try:
        results = reader.readtext(img, detail=1, width_ths=0.7, height_ths=0.7)
    except Exception as e:
        print(f"Ошибка при обработке {image_path.name}: {e}")
        return []
    measurements = []
    for bbox, text, prob in results:
        if prob < PROB_MIN:
            continue
        numbers = re.findall(r"(\d+\.?\d*)", text.replace(",", "."))
        if numbers:
            x_center = sum(p[0] for p in bbox) / 4
            y_center = sum(p[1] for p in bbox) / 4
            measurements.append((float(numbers[0]), x_center, y_center))
    return measurements


def assign_values(expected, direction, measurements):
    """Domain rules: validate readings and assign L1/L3/L5/L3_TOP.

    Returns (values_dict, is_suspicious, reason).
    """
    if not measurements or len(measurements) < 2:
        return {}, True, "Мало измерений"

    valid = [m for m in measurements if VALUE_MIN < m[0] < VALUE_MAX]
    if len(valid) < len(expected):
        return {}, True, f"Найдено {len(valid)} из {len(expected)}"

    ordered = sorted(valid, key=lambda m: m[0])
    min_val = round(ordered[0][0])
    max_val = round(ordered[-1][0])
    value_range = max_val - min_val

    values = {}
    if "L3_TOP" in expected:
        values["L3_TOP"] = min_val
        remaining = ordered[1:]
    else:
        remaining = ordered
    if not remaining:
        return {}, True, "Нет оставшихся значений"

    # spatial assignment: the scan direction tells us which axis orders the lines
    if direction == "A":
        spatial = sorted(remaining, key=lambda m: -m[1])
    elif direction in ("B", "C"):
        spatial = sorted(remaining, key=lambda m: -m[2])
    elif direction == "D":
        spatial = sorted(remaining, key=lambda m: m[2])
    else:
        spatial = remaining

    vals = [round(m[0]) for m in spatial]
    if "L1" in expected:
        values["L1"] = vals[0]
    if "L5" in expected:
        values["L5"] = vals[-1]
    if "L3" in expected:
        values["L3"] = vals[len(vals) // 2] if len(vals) >= 2 else vals[0]

    # validation heuristics: flag for human review instead of failing silently
    is_suspicious = False
    reason = "OK"
    if set(expected) == {"L3", "L3_TOP"}:
        diff = values.get("L3", 0) - values.get("L3_TOP", 0)
        if diff < L3_TOP_DIFF_MIN:
            is_suspicious = True
            reason = f"L3 и L3_TOP слишком близко ({diff} нм)"
        elif diff > L3_TOP_DIFF_MAX:
            is_suspicious = True
            reason = f"Очень большой разброс ({diff} нм)"
    elif value_range > RANGE_MAX:
        is_suspicious = True
        reason = f"Большой разброс ({value_range} нм)"

    return values, is_suspicious, reason


def main():
    parser = argparse.ArgumentParser(
        description="Extract CD measurements from annotated SEM images into Excel."
    )
    parser.add_argument("--image-dir", required=True, type=Path,
                        help="folder with *_S<n>_<A-D>.bmp images")
    parser.add_argument("--excel", required=True, type=Path,
                        help="Excel report to fill in")
    parser.add_argument("--expected", default="L1,L3,L5,L3_TOP",
                        help="comma-separated columns present on the images")
    parser.add_argument("--backup-dir", type=Path, default=None,
                        help="defaults to <excel parent>/Backup")
    args = parser.parse_args()
    expected = [c.strip() for c in args.expected.split(",") if c.strip()]

    import easyocr  # lazy import: keeps the module testable without torch
    reader = easyocr.Reader(["en"], gpu=False, detector=True, recognizer=True)

    backup_dir = args.backup_dir or (args.excel.parent / "Backup")
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    shutil.copy2(args.excel, backup_dir / f"backup_{timestamp}.xlsx")

    df = pd.read_excel(args.excel, sheet_name=0)
    print("Столбцы:", df.columns.tolist())
    print(f"Ожидаемые измерения: {expected}\n")
    print("Начало обработки...\n")

    processed = 0
    suspicious = []

    for file_path in sorted(args.image_dir.glob("*.bmp")):
        s_number, direction = parse_filename(file_path.name)
        if not s_number or not direction:
            continue

        measurements = extract_measurements(reader, file_path)
        values, is_suspicious, reason = assign_values(expected, direction, measurements)

        flat = sorted(round(m[0]) for m in measurements if VALUE_MIN < m[0] < VALUE_MAX)
        print(f"{file_path.name} → {direction} | Значения: {flat}")

        required = [k for k in ("L3", "L3_TOP") if k in expected]
        if any(values.get(k) is None for k in required):
            suspicious.append((file_path.name, reason))
            print(f"   → {reason}\n" + "-" * 80)
            continue

        mask = df.iloc[:, 0].astype(str).str.contains(f"S{s_number}", na=False)
        rows = df[mask].index.tolist()
        if not rows:
            suspicious.append((file_path.name, "Группа S не найдена"))
            print(f"✗ Не найдена группа S{s_number}\n" + "-" * 80)
            continue

        target_row = rows[0] + DIRECTION_ROW_OFFSET[direction]
        try:
            for key in expected:
                if values.get(key) is not None:
                    df.iloc[target_row, df.columns.get_loc(COLUMN_MAP[key])] = values[key]
            status = "⚠️ СОМНИТЕЛЬНО" if is_suspicious else "✓ УСПЕШНО"
            line = " ".join(f"{k}={values.get(k)}" for k in expected)
            print(f"{status}: S{s_number} {direction} → {line} | {reason}")
            processed += 1
        except Exception as e:
            suspicious.append((file_path.name, f"Ошибка записи: {e}"))
            print(f"✗ Ошибка записи в строку {target_row}")
        print("-" * 80)

    df.to_excel(args.excel, index=False)

    print("\n" + "=" * 90)
    print("ЗАВЕРШЕНО")
    print(f"Успешно: {processed} | Сомнительных: {len(suspicious)}")
    print("=" * 90)
    if suspicious:
        print("\nСомнительные случаи:")
        for name, why in suspicious:
            print(f"   • {name} — {why}")


if __name__ == "__main__":
    main()
