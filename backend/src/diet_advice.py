from __future__ import annotations

import os
import sqlite3
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

try:
    from transformers import pipeline
except ImportError:
    pipeline = None


ADVICE_MODEL_ID = os.environ.get("DIET_ADVICE_MODEL_ID", "google/flan-t5-base")


@dataclass
class AdviceSignal:
    category: str
    status: str
    detail: str


def _safe_round(value: float) -> float:
    return round(float(value), 2)


def build_7_day_nutrition_summary(
    conn: sqlite3.Connection,
    days: int = 7,
) -> dict[str, Any]:
    today = datetime.now().date()
    start_date = today - timedelta(days=days - 1)
    cutoff = datetime.combine(start_date, datetime.min.time()).isoformat(
        timespec="seconds"
    )

    rows = conn.execute(
        """
        SELECT
            log.timestamp,
            log.food_type,
            log.calories_per_100g,
            log.portion_grams,
            log.calories_total,
            macros.calories_per_100g,
            macros.protein_g_per_100g,
            macros.fat_g_per_100g,
            macros.carbs_g_per_100g
        FROM log
        LEFT JOIN nutrition_macros AS macros
            ON lower(log.food_type) = macros.name
        WHERE log.timestamp >= ?
          AND log.calories_per_100g >= 0
        ORDER BY log.timestamp ASC
        """,
        (cutoff,),
    ).fetchall()

    totals = {
        "calories": 0.0,
        "protein_g": 0.0,
        "fat_g": 0.0,
        "carbs_g": 0.0,
    }
    daily_totals: dict[str, dict[str, float | int | str]] = {
        (start_date + timedelta(days=i)).isoformat(): {
            "day": (start_date + timedelta(days=i)).isoformat(),
            "entries": 0,
            "calories": 0.0,
            "protein_g": 0.0,
            "fat_g": 0.0,
            "carbs_g": 0.0,
        }
        for i in range(days)
    }
    foods: Counter[str] = Counter()
    missing_macro_foods: Counter[str] = Counter()
    entries_with_macros = 0

    for (
        timestamp,
        food_type,
        logged_calories_per_100g,
        portion_grams,
        calories_total,
        macros_calories_per_100g,
        protein_g_per_100g,
        fat_g_per_100g,
        carbs_g_per_100g,
    ) in rows:
        day = str(timestamp)[:10]
        portion = float(portion_grams) if portion_grams is not None else 100.0
        daily = daily_totals.setdefault(
            day,
            {
                "day": day,
                "entries": 0,
                "calories": 0.0,
                "protein_g": 0.0,
                "fat_g": 0.0,
                "carbs_g": 0.0,
            },
        )

        entry_calories = (
            float(calories_total)
            if calories_total is not None
            else (portion / 100.0) * float(logged_calories_per_100g)
        )
        daily["entries"] = int(daily["entries"]) + 1
        daily["calories"] = float(daily["calories"]) + entry_calories
        totals["calories"] += entry_calories

        if food_type and food_type != "unknown":
            foods[str(food_type)] += 1

        if protein_g_per_100g is None or fat_g_per_100g is None or carbs_g_per_100g is None:
            if food_type and food_type != "unknown":
                missing_macro_foods[str(food_type)] += 1
            continue

        entries_with_macros += 1
        protein = (portion / 100.0) * float(protein_g_per_100g)
        fat = (portion / 100.0) * float(fat_g_per_100g)
        carbs = (portion / 100.0) * float(carbs_g_per_100g)

        daily["protein_g"] = float(daily["protein_g"]) + protein
        daily["fat_g"] = float(daily["fat_g"]) + fat
        daily["carbs_g"] = float(daily["carbs_g"]) + carbs

        totals["protein_g"] += protein
        totals["fat_g"] += fat
        totals["carbs_g"] += carbs

    active_days = max(1, sum(1 for day in daily_totals.values() if int(day["entries"]) > 0))
    averages = {
        "calories": _safe_round(totals["calories"] / active_days),
        "protein_g": _safe_round(totals["protein_g"] / active_days),
        "fat_g": _safe_round(totals["fat_g"] / active_days),
        "carbs_g": _safe_round(totals["carbs_g"] / active_days),
    }

    return {
        "window_days": days,
        "entries": len(rows),
        "entries_with_macros": entries_with_macros,
        "active_days": active_days,
        "totals": {key: _safe_round(value) for key, value in totals.items()},
        "averages": averages,
        "daily": [
            {
                "day": item["day"],
                "entries": int(item["entries"]),
                "calories": _safe_round(item["calories"]),
                "protein_g": _safe_round(item["protein_g"]),
                "fat_g": _safe_round(item["fat_g"]),
                "carbs_g": _safe_round(item["carbs_g"]),
            }
            for item in daily_totals.values()
        ],
        "top_foods": [
            {"food_type": food, "count": count}
            for food, count in foods.most_common(5)
        ],
        "missing_macro_foods": [
            {"food_type": food, "count": count}
            for food, count in missing_macro_foods.most_common()
        ],
        "unique_food_count": len(foods),
    }


def derive_advice_signals(summary: dict[str, Any]) -> list[AdviceSignal]:
    signals: list[AdviceSignal] = []
    averages = summary["averages"]

    if summary["entries"] == 0:
        signals.append(
            AdviceSignal(
                category="coverage",
                status="insufficient",
                detail="No logged meals were found in the last 7 days.",
            )
        )
        return signals

    if averages["protein_g"] < 50:
        signals.append(
            AdviceSignal(
                category="protein",
                status="low",
                detail="Average logged protein appears low across the 7-day period.",
            )
        )

    if averages["carbs_g"] > 300:
        signals.append(
            AdviceSignal(
                category="carbs",
                status="high",
                detail="Average logged carbohydrate intake appears relatively high.",
            )
        )

    if averages["fat_g"] > 80:
        signals.append(
            AdviceSignal(
                category="fat",
                status="high",
                detail="Average logged fat intake appears relatively high.",
            )
        )

    if summary["unique_food_count"] < 5:
        signals.append(
            AdviceSignal(
                category="variety",
                status="low",
                detail="The diet appears repetitive with limited meal variety.",
            )
        )

    if summary["entries_with_macros"] < summary["entries"]:
        signals.append(
            AdviceSignal(
                category="data",
                status="partial",
                detail="Some meals did not have macro data, so advice is based on partial nutrition coverage.",
            )
        )

    if not signals:
        signals.append(
            AdviceSignal(
                category="balance",
                status="ok",
                detail="The logged meals look broadly balanced from the available nutrition data.",
            )
        )

    return signals


def build_advice_prompt(summary: dict[str, Any], signals: list[AdviceSignal]) -> str:
    top_foods = ", ".join(
        f"{item['food_type']} ({item['count']})" for item in summary["top_foods"]
    ) or "No dominant meals logged"
    signal_lines = "\n".join(
        f"- {signal.category}: {signal.status} - {signal.detail}" for signal in signals
    )
    return (
        "You are generating general non-medical nutrition guidance.\n"
        "Use the 7-day meal summary below and provide:\n"
        "1. A short summary of the overall pattern.\n"
        "2. What may be lacking or too high.\n"
        "3. 3 practical food changes the user could make.\n"
        "Keep the advice concise and avoid medical claims.\n\n"
        f"7-day entries: {summary['entries']}\n"
        f"Active days: {summary['active_days']}\n"
        f"Average calories/day: {summary['averages']['calories']}\n"
        f"Average protein/day (g): {summary['averages']['protein_g']}\n"
        f"Average fat/day (g): {summary['averages']['fat_g']}\n"
        f"Average carbs/day (g): {summary['averages']['carbs_g']}\n"
        f"Top foods: {top_foods}\n"
        f"Signals:\n{signal_lines}\n"
    )


def load_advice_generator(device: int = -1):
    if pipeline is None:
        raise RuntimeError(
            "transformers is required for the diet advice generator. "
            "Install with: pip install transformers"
        )
    return pipeline(
        "text2text-generation",
        model=ADVICE_MODEL_ID,
        device=device,
    )


def fallback_advice(summary: dict[str, Any], signals: list[AdviceSignal]) -> str:
    if summary["entries"] == 0:
        return (
            "No 7-day meal data is available yet. Log meals across several days "
            "to receive dietary guidance."
        )

    lines = ["Overall pattern:"]
    top_foods = ", ".join(
        item["food_type"] for item in summary["top_foods"][:3]
    ) or "no repeated meals"
    lines.append(f"- Most common logged meals: {top_foods}.")

    for signal in signals:
        if signal.category == "protein" and signal.status == "low":
            lines.append("- Protein may be low. Add more eggs, tofu, fish, chicken, or beans.")
        elif signal.category == "carbs" and signal.status == "high":
            lines.append("- Carbohydrates may be high. Reduce refined rice or noodle portions and add more vegetables.")
        elif signal.category == "fat" and signal.status == "high":
            lines.append("- Fat intake may be high. Choose grilled, steamed, or broth-based meals more often.")
        elif signal.category == "variety" and signal.status == "low":
            lines.append("- Meal variety looks limited. Add more vegetables, fruit, and different protein sources.")
        elif signal.category == "balance" and signal.status == "ok":
            lines.append("- The logged meals look reasonably balanced from the available data.")

    if len(lines) == 1:
        lines.append("- More logged meals with macro data are needed for stronger guidance.")
    return "\n".join(lines)


def generate_diet_advice(
    summary: dict[str, Any],
    generator=None,
) -> dict[str, Any]:
    signals = derive_advice_signals(summary)
    prompt = build_advice_prompt(summary, signals)

    advice_text = None
    source = "fallback"
    if generator is not None:
        try:
            result = generator(prompt, max_new_tokens=180, do_sample=False)
            if result:
                advice_text = str(result[0].get("generated_text", "")).strip()
                source = "model"
        except Exception:
            advice_text = None

    if not advice_text:
        advice_text = fallback_advice(summary, signals)

    return {
        "summary": summary,
        "signals": [
            {
                "category": signal.category,
                "status": signal.status,
                "detail": signal.detail,
            }
            for signal in signals
        ],
        "advice": advice_text,
        "source": source,
        "model_id": ADVICE_MODEL_ID if source == "model" else None,
    }


def build_diet_advice_payload(
    conn: sqlite3.Connection,
    generator=None,
    days: int = 7,
) -> dict[str, Any]:
    summary = build_7_day_nutrition_summary(conn, days=days)
    return generate_diet_advice(summary, generator=generator)
