import argparse
import csv
import sys
from pathlib import Path


ASIAN_COUNTRIES = {
    "singapore",
    "malaysia",
    "indonesia",
    "thailand",
    "vietnam",
    "philippines",
    "china",
    "hong kong",
    "taiwan",
    "japan",
    "south korea",
    "korea",
    "india",
    "pakistan",
    "bangladesh",
    "sri lanka",
    "myanmar",
    "cambodia",
    "laos",
    "nepal",
}

ASIAN_KEYWORDS = {
    "bibimbap",
    "bulgogi",
    "kimchi",
    "ramen",
    "udon",
    "soba",
    "pho",
    "banh mi",
    "laksa",
    "nasi lemak",
    "nasi goreng",
    "satay",
    "rendang",
    "tom yum",
    "pad thai",
    "dim sum",
    "dumpling",
    "gyoza",
    "sushi",
    "sashimi",
    "miso",
    "biryani",
    "biryani",
    "dosa",
    "idli",
    "curry",
    "chai",
    "mochi",
    "matcha",
    "mango sticky rice",
    "kaya",
}


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


def is_asian_row(row: dict[str, str]) -> bool:
    countries = (row.get("countries_en") or "").lower()

    for country in ASIAN_COUNTRIES:
        if country in countries:
            return True

    return False


def extract_asian_openfoodfacts(src: Path, dst: Path) -> tuple[int, int]:
    csv.field_size_limit(min(sys.maxsize, 1_000_000_000))
    fields = [
        "name",
        "calories_per_100g",
        "protein_g_per_100g",
        "fat_g_per_100g",
        "carbs_g_per_100g",
        "is_asian",
    ]

    written = 0
    seen = 0

    with src.open("r", encoding="utf-8", errors="replace", newline="") as f_in:
        reader = csv.DictReader(f_in, delimiter="\t")
        with dst.open("w", encoding="utf-8", newline="") as f_out:
            writer = csv.DictWriter(f_out, fieldnames=fields)
            writer.writeheader()

            for row in reader:
                seen += 1
                if not is_asian_row(row):
                    continue

                name = (
                    (row.get("generic_name") or "")
                    or (row.get("product_name") or "")
                    or (row.get("abbreviated_product_name") or "")
                ).strip()
                if not name:
                    continue

                calories = parse_num(row.get("energy-kcal_100g"))
                protein = parse_num(row.get("proteins_100g"))
                fat = parse_num(row.get("fat_100g"))
                carbs = parse_num(row.get("carbohydrates_100g"))

                if (
                    calories is None
                    or protein is None
                    or fat is None
                    or carbs is None
                ):
                    continue

                writer.writerow(
                    {
                        "name": name,
                        "calories_per_100g": calories,
                        "protein_g_per_100g": protein,
                        "fat_g_per_100g": fat,
                        "carbs_g_per_100g": carbs,
                        "is_asian": 1,
                    }
                )
                written += 1

    return seen, written


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract Asian cuisine rows from OpenFoodFacts CSV"
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
        / "asian_openfoodfacts.csv",
        help="Output CSV path",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.src.exists():
        raise SystemExit(f"Source file not found: {args.src}")
    args.dst.parent.mkdir(parents=True, exist_ok=True)
    seen, written = extract_asian_openfoodfacts(args.src, args.dst)
    print(f"Processed {seen} rows, wrote {written} rows to {args.dst}")


if __name__ == "__main__":
    main()
