import argparse
import csv
import sys
from pathlib import Path


def parse_num(value: str | None) -> float | None:
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    value = value.replace(",", ".")
    try:
        return float(value)
    except ValueError:
        return None


def extract_openfoodfacts(src: Path, dst: Path) -> tuple[int, int]:
    csv.field_size_limit(min(sys.maxsize, 1_000_000_000))
    fields = [
        "name",
        "calories_per_100g",
        "protein_g_per_100g",
        "fat_g_per_100g",
        "carbs_g_per_100g",
    ]

    seen = 0
    totals: dict[str, dict[str, float]] = {}
    counts: dict[str, int] = {}

    with src.open("r", encoding="utf-8", errors="replace", newline="") as f_in:
        reader = csv.DictReader(f_in, delimiter="\t")
        for row in reader:
            seen += 1
            name = (
                (row.get("generic_name") or "")
                or (row.get("product_name") or "")
                or (row.get("abbreviated_product_name") or "")
            ).strip()

            calories = parse_num(row.get("energy-kcal_100g"))
            protein = parse_num(row.get("proteins_100g"))
            fat = parse_num(row.get("fat_100g"))
            carbs = parse_num(row.get("carbohydrates_100g"))

            if (
                not name
                or calories is None
                or protein is None
                or fat is None
                or carbs is None
            ):
                continue

            if name not in totals:
                totals[name] = {
                    "calories_per_100g": 0.0,
                    "protein_g_per_100g": 0.0,
                    "fat_g_per_100g": 0.0,
                    "carbs_g_per_100g": 0.0,
                }
                counts[name] = 0

            totals[name]["calories_per_100g"] += calories
            totals[name]["protein_g_per_100g"] += protein
            totals[name]["fat_g_per_100g"] += fat
            totals[name]["carbs_g_per_100g"] += carbs
            counts[name] += 1

    with dst.open("w", encoding="utf-8", newline="") as f_out:
        writer = csv.DictWriter(f_out, fieldnames=fields)
        writer.writeheader()

        for name, sums in totals.items():
            count = counts.get(name, 1)
            writer.writerow(
                {
                    "name": name,
                    "calories_per_100g": sums["calories_per_100g"] / count,
                    "protein_g_per_100g": sums["protein_g_per_100g"] / count,
                    "fat_g_per_100g": sums["fat_g_per_100g"] / count,
                    "carbs_g_per_100g": sums["carbs_g_per_100g"] / count,
                }
            )

    return seen, len(totals)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract name + macros + calories from OpenFoodFacts CSV"
    )
    parser.add_argument(
        "--src",
        type=Path,
        default=Path(__file__).resolve().parents[1]
        / "data"
        / "en.openfoodfacts.org.products.csv",
        help="Path to OpenFoodFacts CSV (tab-delimited)",
    )
    parser.add_argument(
        "--dst",
        type=Path,
        default=Path(__file__).resolve().parents[1]
        / "data"
        / "generic_openfoodfacts.csv",
        help="Output CSV path",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.src.exists():
        raise SystemExit(f"Source file not found: {args.src}")
    args.dst.parent.mkdir(parents=True, exist_ok=True)
    seen, written = extract_openfoodfacts(args.src, args.dst)
    print(f"Processed {seen} rows, wrote {written} rows to {args.dst}")


if __name__ == "__main__":
    main()
