import io
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image

import sys

SRC_DIR = Path(__file__).resolve().parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import diet_advice
import featured_prototype as fp
import generalClassifier as gc


APP_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIR = APP_ROOT / "frontend"


@dataclass
class CachedPrediction:
    image_name: str
    image_bytes: bytes
    candidates: list[tuple[int, str, float, str, int]]
    low_conf: bool
    classifier_used: str


app = FastAPI(title="CM3070 Calorie Counter")
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

prediction_cache: dict[str, CachedPrediction] = {}


@app.on_event("startup")
def startup() -> None:
    # Load models and resources once
    app.state.device = fp.get_device()
    app.state.gate_pipe = fp.load_food_gate(app.state.device)
    app.state.food_pipe = fp.load_food_classifier(app.state.device)
    app.state.general_food_classifier = gc.load_general_classifier(app.state.device)
    app.state.encoder = fp.load_text_encoder()

    app.state.fernet = fp.get_fernet()
    app.state.conn = fp.get_db_connection(fp.DB_PATH)

    nutrition_table = fp.ensure_nutrition_table(
        app.state.conn,
        nutrition_csv=fp.NUTRITION_CSV,
        macros_csv=fp.GENERIC_OPENFOODFACTS_CSV,
    )
    app.state.nutrition_table = nutrition_table
    app.state.nutrition_keys = sorted(nutrition_table.keys())
    app.state.nutrition_macros_table = fp.ensure_nutrition_macros_table(app.state.conn)
    app.state.advice_generator = None

    try:
        key_vecs = app.state.encoder.encode(
            app.state.nutrition_keys, normalize_embeddings=True
        )
        app.state.key_embeddings = fp.torch.from_numpy(key_vecs).float()
    except Exception:
        app.state.key_embeddings = None


@app.on_event("shutdown")
def shutdown() -> None:
    conn = getattr(app.state, "conn", None)
    if conn is not None:
        conn.close()


@app.get("/")
def index() -> FileResponse:
    index_path = FRONTEND_DIR / "index.html"
    return FileResponse(index_path)


def _load_image(upload: UploadFile) -> Image.Image:
    try:
        data = upload.file.read()
        image = Image.open(io.BytesIO(data)).convert("RGB")
        return image, data
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid image: {exc}") from exc


@app.post("/api/predict")
def predict(file: UploadFile = File(...)) -> dict[str, Any]:
    image, image_bytes = _load_image(file)

    is_food, food_score, gate_label = fp.food_gate_decision(
        app.state.gate_pipe, image, threshold=fp.FOOD_GATE_THRESHOLD
    )
    if not is_food:
        return {
            "blocked": True,
            "gate_label": gate_label,
            "gate_score": round(food_score, 4),
            "message": "Non-food detected. Skipping classification.",
        }

    preds, low_conf, classifier_used = gc.classify_with_fallback(
        image,
        app.state.food_pipe,
        app.state.general_food_classifier,
        threshold=gc.GENERAL_CLASSIFIER_TRIGGER,
        top_k=3,
    )
    if not preds:
        raise HTTPException(status_code=500, detail="No predictions returned.")

    candidates: list[tuple[int, str, float, str, int]] = []
    for rank, (label, prob) in enumerate(preds, start=1):
        semantic_key = fp.semantic_match_key(
            label,
            app.state.nutrition_keys,
            encoder=app.state.encoder,
            key_embeddings=app.state.key_embeddings,
        )
        food_type, calories = fp.rough_cal_estimate(
            label,
            nutrition_table=app.state.nutrition_table,
            semantic_key=semantic_key,
        )
        candidates.append((rank, label, prob, food_type, calories))

    image_id = str(uuid.uuid4())
    prediction_cache[image_id] = CachedPrediction(
        image_name=file.filename or "upload.jpg",
        image_bytes=image_bytes,
        candidates=candidates,
        low_conf=low_conf,
        classifier_used=classifier_used,
    )

    return {
        "blocked": False,
        "image_id": image_id,
        "image_url": f"/api/image/{image_id}",
        "low_conf": low_conf,
        "classifier_used": classifier_used,
        "candidates": [
            {
                "rank": rank,
                "label": label,
                "prob": round(prob, 4),
                "food_type": food_type,
                "calories_per_100g": calories,
            }
            for rank, label, prob, food_type, calories in candidates
        ],
    }


@app.get("/api/image/{image_id}")
def get_image(image_id: str) -> Any:
    entry = prediction_cache.get(image_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Image not found.")
    return StreamingResponse(
        io.BytesIO(entry.image_bytes),
        media_type="image/jpeg",
        headers={"Content-Disposition": f'inline; filename="{entry.image_name}"'},
    )

@app.post("/api/log")
def log_choice(
    image_id: str,
    choice: int,
    portion_grams: float = 100.0,
    log_date: str | None = None,
) -> dict[str, Any]:
    entry = prediction_cache.pop(image_id, None)
    if entry is None:
        raise HTTPException(status_code=404, detail="Prediction not found or expired.")

    if portion_grams <= 0:
        raise HTTPException(status_code=400, detail="Portion size must be positive.")

    timestamp_iso = None
    if log_date:
        if len(log_date) != 10:
            raise HTTPException(status_code=400, detail="log_date must be YYYY-MM-DD")
        today = datetime.now().date().isoformat()
        if log_date == today:
            timestamp_iso = datetime.now().isoformat(timespec="seconds")
        else:
            timestamp_iso = f"{log_date}T23:59:00"

    if choice == 0:
        fp.log_prediction(
            app.state.conn,
            app.state.fernet,
            Path(entry.image_name),
            "unknown",
            "unknown",
            -1,
            portion_grams=portion_grams,
            timestamp_iso=timestamp_iso,
        )
        return {"status": "logged", "message": "Logged as unknown."}

    if not (1 <= choice <= len(entry.candidates)):
        raise HTTPException(status_code=400, detail="Choice out of range.")

    _, label, _, food_type, calories = entry.candidates[choice - 1]
    fp.log_prediction(
        app.state.conn,
        app.state.fernet,
        Path(entry.image_name),
        label,
        food_type,
        calories,
        portion_grams=portion_grams,
        timestamp_iso=timestamp_iso,
    )

    calories_total = None
    if calories >= 0:
        calories_total = round((portion_grams / 100.0) * calories, 2)
    return {
        "status": "logged",
        "food_type": food_type,
        "calories_per_100g": calories,
        "portion_grams": portion_grams,
        "calories_total": calories_total,
    }


@app.get("/api/trends")
def trends() -> dict[str, Any]:
    count, avg = fp.calculate_last_7_days_stats(app.state.conn)
    daily = fp.calculate_last_7_days_daily_totals(app.state.conn)
    total_7d = round(sum(day["total_calories"] for day in daily), 2)
    return {
        "count": count,
        "avg_kcal_per_100g": round(avg, 2),
        "total_7d": total_7d,
        "daily": daily,
    }


@app.get("/api/advice")
def advice() -> dict[str, Any]:
    generator = getattr(app.state, "advice_generator", None)
    if generator is None:
        try:
            generator = diet_advice.load_advice_generator(
                device=fp.get_hf_device(app.state.device)
            )
            app.state.advice_generator = generator
        except Exception:
            generator = None

    return diet_advice.build_diet_advice_payload(
        app.state.conn,
        generator=generator,
    )


@app.get("/api/logs")
def logs(day: str) -> dict[str, Any]:
    if not day or len(day) != 10:
        raise HTTPException(status_code=400, detail="day must be YYYY-MM-DD")

    rows = app.state.conn.execute(
        """
        SELECT
            id,
            timestamp,
            image_name_enc,
            raw_label_enc,
            food_type,
            calories_per_100g,
            portion_grams,
            calories_total
        FROM log
        WHERE substr(timestamp, 1, 10) = ?
        ORDER BY timestamp ASC
        """,
        (day,),
    ).fetchall()

    items: list[dict[str, Any]] = []
    for (
        log_id,
        ts,
        image_name_enc,
        raw_label_enc,
        food_type,
        calories_per_100g,
        portion_grams,
        calories_total,
    ) in rows:
        try:
            image_name = fp.decrypt_text(image_name_enc, app.state.fernet)
        except Exception:
            image_name = "unknown"
        try:
            label = fp.decrypt_text(raw_label_enc, app.state.fernet)
        except Exception:
            label = "unknown"
        items.append(
            {
                "id": log_id,
                "timestamp": ts,
                "image_name": image_name,
                "label": label,
                "food_type": food_type,
                "calories_per_100g": calories_per_100g,
                "portion_grams": portion_grams,
                "calories_total": calories_total,
            }
        )

    return {"day": day, "count": len(items), "items": items}


@app.delete("/api/logs/{log_id}")
def delete_log(log_id: int) -> dict[str, Any]:
    cur = app.state.conn.execute("DELETE FROM log WHERE id = ?", (log_id,))
    app.state.conn.commit()
    if cur.rowcount == 0:
        raise HTTPException(status_code=404, detail="Log entry not found.")
    return {"status": "deleted", "id": log_id}
