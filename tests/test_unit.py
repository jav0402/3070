import base64
import importlib.util
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FEATURED_PATH = PROJECT_ROOT / "backend" / "src" / "featured_prototype.py"
APP_PATH = PROJECT_ROOT / "backend" / "src" / "app.py"
ADVICE_PATH = PROJECT_ROOT / "backend" / "src" / "diet_advice.py"
GENERAL_CLASSIFIER_PATH = PROJECT_ROOT / "backend" / "src" / "generalClassifier.py"

spec = importlib.util.spec_from_file_location("featured_prototype", FEATURED_PATH)
if spec is None or spec.loader is None:
    raise ImportError(f"Cannot load featured_prototype from {FEATURED_PATH}")
featured = importlib.util.module_from_spec(spec)
sys.modules["featured_prototype"] = featured
spec.loader.exec_module(featured)

advice_spec = importlib.util.spec_from_file_location("diet_advice", ADVICE_PATH)
if advice_spec is None or advice_spec.loader is None:
    raise ImportError(f"Cannot load diet_advice from {ADVICE_PATH}")
diet_advice = importlib.util.module_from_spec(advice_spec)
sys.modules["diet_advice"] = diet_advice
advice_spec.loader.exec_module(diet_advice)

general_spec = importlib.util.spec_from_file_location(
    "generalClassifier", GENERAL_CLASSIFIER_PATH
)
if general_spec is None or general_spec.loader is None:
    raise ImportError(f"Cannot load generalClassifier from {GENERAL_CLASSIFIER_PATH}")
general_classifier = importlib.util.module_from_spec(general_spec)
sys.modules["generalClassifier"] = general_classifier
general_spec.loader.exec_module(general_classifier)

try:
    from fastapi.testclient import TestClient
except ImportError as exc:
    TestClient = None
    APP_IMPORT_ERROR = exc
    app_module = None
else:
    try:
        app_spec = importlib.util.spec_from_file_location("project_backend_app", APP_PATH)
        if app_spec is None or app_spec.loader is None:
            raise ImportError(f"Cannot load app module from {APP_PATH}")
        app_module = importlib.util.module_from_spec(app_spec)
        sys.modules["project_backend_app"] = app_module
        app_spec.loader.exec_module(app_module)
        APP_IMPORT_ERROR = None
    except Exception as exc:
        app_module = None
        APP_IMPORT_ERROR = exc


PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8"
    "/x8AAwMCAO+j6X8AAAAASUVORK5CYII="
)

calculate_last_7_days_daily_totals = featured.calculate_last_7_days_daily_totals
calculate_last_7_days_stats = featured.calculate_last_7_days_stats
decrypt_text = featured.decrypt_text
encrypt_text = featured.encrypt_text
ensure_nutrition_table = featured.ensure_nutrition_table
get_fernet = featured.get_fernet
init_db = featured.init_db
log_prediction = featured.log_prediction
open_db = featured.open_db
rough_cal_estimate = featured.rough_cal_estimate
build_7_day_nutrition_summary = diet_advice.build_7_day_nutrition_summary
build_diet_advice_payload = diet_advice.build_diet_advice_payload


class BaseProjectTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._saved_env = os.environ.pop("CALORIE_DB_KEY", None)

    def tearDown(self) -> None:
        if self._saved_env is not None:
            os.environ["CALORIE_DB_KEY"] = self._saved_env


class EncryptionTests(BaseProjectTestCase):
    def test_encrypt_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            key_path = Path(tmpdir) / "db.key"
            fernet = get_fernet(key_path=key_path)
            text = "chicken rice"
            token = encrypt_text(text, fernet)
            self.assertNotEqual(text, token)
            self.assertEqual(text, decrypt_text(token, fernet))


class DatabaseTests(BaseProjectTestCase):
    def test_nutrition_seed_and_log(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            csv_path = tmp_path / "nutrition.csv"
            csv_path.write_text(
                "name,calories_per_100g\nchicken rice,123\n",
                encoding="utf-8",
            )

            db_path = tmp_path / "test.db"
            init_db(db_path)
            conn = open_db(db_path)
            try:
                table = ensure_nutrition_table(
                    conn,
                    nutrition_csv=csv_path,
                    macros_csv=tmp_path / "missing_macros.csv",
                )
                self.assertEqual(table["chicken rice"], 123)

                key_path = tmp_path / "db.key"
                fernet = get_fernet(key_path=key_path)
                log_prediction(
                    conn,
                    fernet,
                    Path("image.jpg"),
                    "label",
                    "chicken rice",
                    123,
                )
                count, avg = calculate_last_7_days_stats(conn)
                self.assertEqual(count, 1)
                self.assertAlmostEqual(avg, 123.0)

                row = conn.execute(
                    "SELECT image_name_enc, raw_label_enc FROM log"
                ).fetchone()
                self.assertIsNotNone(row)
                self.assertNotEqual(row[0], "image.jpg")
                self.assertNotEqual(row[1], "label")
                self.assertEqual(decrypt_text(row[0], fernet), "image.jpg")
                self.assertEqual(decrypt_text(row[1], fernet), "label")
            finally:
                conn.close()

    def test_rough_cal_estimate_prefers_semantic_key(self) -> None:
        food_type, calories = rough_cal_estimate(
            "fried noodles",
            {"ramen": 150, "fried rice": 290},
            semantic_key="ramen",
        )
        self.assertEqual(food_type, "ramen")
        self.assertEqual(calories, 150)

    def test_daily_totals_use_calories_total_when_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            db_path = tmp_path / "test.db"
            init_db(db_path)
            conn = open_db(db_path)
            try:
                key_path = tmp_path / "db.key"
                fernet = get_fernet(key_path=key_path)

                today = datetime.now().date().isoformat()
                yesterday = (datetime.now().date() - timedelta(days=1)).isoformat()

                log_prediction(
                    conn,
                    fernet,
                    Path("today.jpg"),
                    "label",
                    "ramen",
                    150,
                    portion_grams=200,
                    timestamp_iso=f"{today}T10:00:00",
                )
                log_prediction(
                    conn,
                    fernet,
                    Path("yesterday.jpg"),
                    "label",
                    "fried rice",
                    290,
                    portion_grams=None,
                    timestamp_iso=f"{yesterday}T12:00:00",
                )

                daily = calculate_last_7_days_daily_totals(conn)
                daily_map = {row["day"]: row for row in daily}
                self.assertEqual(daily_map[today]["total_calories"], 300.0)
                self.assertEqual(daily_map[today]["count"], 1)
                self.assertEqual(daily_map[yesterday]["total_calories"], 290.0)
            finally:
                conn.close()

    def test_diet_advice_summary_and_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            db_path = tmp_path / "test.db"
            init_db(db_path)
            conn = open_db(db_path)
            try:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO nutrition_macros (
                        name,
                        calories_per_100g,
                        protein_g_per_100g,
                        fat_g_per_100g,
                        carbs_g_per_100g
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    ("fried rice", 290.0, 6.0, 12.0, 45.0),
                )
                conn.commit()

                key_path = tmp_path / "db.key"
                fernet = get_fernet(key_path=key_path)
                today = datetime.now().date().isoformat()

                log_prediction(
                    conn,
                    fernet,
                    Path("meal.jpg"),
                    "fried rice",
                    "fried rice",
                    290,
                    portion_grams=400,
                    timestamp_iso=f"{today}T12:00:00",
                )

                summary = build_7_day_nutrition_summary(conn)
                self.assertEqual(summary["entries"], 1)
                self.assertEqual(summary["totals"]["calories"], 1160.0)
                self.assertEqual(summary["totals"]["protein_g"], 24.0)
                self.assertEqual(summary["totals"]["carbs_g"], 180.0)

                payload = build_diet_advice_payload(conn, generator=None)
                self.assertEqual(payload["source"], "fallback")
                self.assertTrue(payload["signals"])
                self.assertIn("Overall pattern:", payload["advice"])
            finally:
                conn.close()


@unittest.skipIf(
    app_module is None,
    f"FastAPI test dependencies unavailable: {APP_IMPORT_ERROR}",
)
class ApiTests(BaseProjectTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.original_startup = list(app_module.app.router.on_startup)
        cls.original_shutdown = list(app_module.app.router.on_shutdown)
        app_module.app.router.on_startup.clear()
        app_module.app.router.on_shutdown.clear()

    @classmethod
    def tearDownClass(cls) -> None:
        app_module.app.router.on_startup[:] = cls.original_startup
        app_module.app.router.on_shutdown[:] = cls.original_shutdown

    def setUp(self) -> None:
        super().setUp()
        self.tmpdir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmpdir.name)
        self.db_path = self.tmp_path / "test.db"
        self.key_path = self.tmp_path / "db.key"

        init_db(self.db_path)
        self.conn = open_db(self.db_path)
        self.fernet = get_fernet(key_path=self.key_path)

        app_module.prediction_cache.clear()
        app_module.app.state.conn = self.conn
        app_module.app.state.fernet = self.fernet
        app_module.app.state.nutrition_table = {
            "chicken rice": 123,
            "ramen": 150,
        }
        app_module.app.state.nutrition_macros_table = {
            "chicken rice": {
                "calories_per_100g": 123.0,
                "protein_g_per_100g": 8.0,
                "fat_g_per_100g": 4.0,
                "carbs_g_per_100g": 18.0,
            },
            "ramen": {
                "calories_per_100g": 150.0,
                "protein_g_per_100g": 6.0,
                "fat_g_per_100g": 5.0,
                "carbs_g_per_100g": 22.0,
            },
        }
        app_module.app.state.nutrition_keys = sorted(
            app_module.app.state.nutrition_table.keys()
        )
        if featured.torch is not None:
            app_module.app.state.device = featured.torch.device("cpu")
        app_module.app.state.encoder = None
        app_module.app.state.key_embeddings = None
        app_module.app.state.advice_generator = None
        app_module.app.state.gate_pipe = object()
        app_module.app.state.food_pipe = lambda image, top_k=3: [
            {"label": "chicken rice", "score": 0.91},
            {"label": "ramen", "score": 0.08},
            {"label": "fried rice", "score": 0.01},
        ]
        app_module.app.state.general_food_classifier = None

        self.client = TestClient(app_module.app)

    def tearDown(self) -> None:
        self.client.close()
        self.conn.close()
        self.tmpdir.cleanup()
        app_module.prediction_cache.clear()
        super().tearDown()

    def test_index_serves_frontend(self) -> None:
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.headers["content-type"])

    def test_predict_blocks_non_food(self) -> None:
        with patch.object(
            app_module.fp,
            "food_gate_decision",
            return_value=(False, 0.99, "non-food"),
        ):
            response = self.client.post(
                "/api/predict",
                files={"file": ("sample.png", PNG_BYTES, "image/png")},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["blocked"])
        self.assertEqual(payload["gate_label"], "non-food")
        self.assertEqual(app_module.prediction_cache, {})

    def test_predict_returns_candidates_and_image_preview(self) -> None:
        with patch.object(
            app_module.fp,
            "food_gate_decision",
            return_value=(True, 0.95, "food"),
        ), patch.object(
            app_module.fp,
            "semantic_match_key",
            side_effect=["chicken rice", "ramen", "unknown"],
        ):
            response = self.client.post(
                "/api/predict",
                files={"file": ("sample.png", PNG_BYTES, "image/png")},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload["blocked"])
        self.assertEqual(len(payload["candidates"]), 3)
        self.assertEqual(payload["candidates"][0]["food_type"], "chicken rice")

        image_response = self.client.get(payload["image_url"])
        self.assertEqual(image_response.status_code, 200)
        self.assertIn("image/jpeg", image_response.headers["content-type"])

    def test_predict_uses_general_fallback_when_primary_confidence_is_low(self) -> None:
        app_module.app.state.food_pipe = lambda image, top_k=3: [
            {"label": "uncertain asian dish", "score": 0.31},
            {"label": "ramen", "score": 0.20},
            {"label": "fried rice", "score": 0.10},
        ]
        app_module.app.state.general_food_classifier = {"ready": True}

        with patch.object(
            app_module.fp,
            "food_gate_decision",
            return_value=(True, 0.95, "food"),
        ), patch.object(
            app_module.gc,
            "predict_general_fallback",
            return_value=[
                ("plate", 0.74),
                ("bowl", 0.12),
                ("tray", 0.05),
            ],
        ), patch.object(
            app_module.fp,
            "semantic_match_key",
            side_effect=["unknown", "unknown", "unknown"],
        ):
            response = self.client.post(
                "/api/predict",
                files={"file": ("sample.png", PNG_BYTES, "image/png")},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["classifier_used"], "fallback_general")
        self.assertFalse(payload["low_conf"])
        self.assertEqual(payload["candidates"][0]["label"], "plate")

    def test_log_selected_choice_persists_entry(self) -> None:
        image_id = "predict-1"
        app_module.prediction_cache[image_id] = app_module.CachedPrediction(
            image_name="meal.jpg",
            image_bytes=PNG_BYTES,
            candidates=[
                (1, "chicken rice", 0.91, "chicken rice", 123),
                (2, "ramen", 0.08, "ramen", 150),
            ],
            low_conf=False,
            classifier_used="primary",
        )

        response = self.client.post(
            "/api/log",
            params={
                "image_id": image_id,
                "choice": 1,
                "portion_grams": 150,
                "log_date": datetime.now().date().isoformat(),
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["food_type"], "chicken rice")
        self.assertEqual(payload["calories_total"], 184.5)

        row = self.conn.execute(
            "SELECT food_type, calories_per_100g, portion_grams, calories_total FROM log"
        ).fetchone()
        self.assertEqual(row, ("chicken rice", 123, 150.0, 184.5))
        self.assertNotIn(image_id, app_module.prediction_cache)

    def test_log_unknown_choice(self) -> None:
        image_id = "predict-unknown"
        app_module.prediction_cache[image_id] = app_module.CachedPrediction(
            image_name="meal.jpg",
            image_bytes=PNG_BYTES,
            candidates=[(1, "chicken rice", 0.91, "chicken rice", 123)],
            low_conf=False,
            classifier_used="primary",
        )

        response = self.client.post(
            "/api/log",
            params={"image_id": image_id, "choice": 0, "portion_grams": 120},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["message"], "Logged as unknown.")

        row = self.conn.execute(
            "SELECT food_type, calories_per_100g, portion_grams FROM log"
        ).fetchone()
        self.assertEqual(row, ("unknown", -1, 120.0))

    def test_log_rejects_invalid_input(self) -> None:
        image_id = "predict-invalid"
        app_module.prediction_cache[image_id] = app_module.CachedPrediction(
            image_name="meal.jpg",
            image_bytes=PNG_BYTES,
            candidates=[(1, "chicken rice", 0.91, "chicken rice", 123)],
            low_conf=False,
            classifier_used="primary",
        )

        portion_response = self.client.post(
            "/api/log",
            params={"image_id": image_id, "choice": 1, "portion_grams": 0},
        )
        self.assertEqual(portion_response.status_code, 400)
        self.assertEqual(
            portion_response.json()["detail"], "Portion size must be positive."
        )

        app_module.prediction_cache[image_id] = app_module.CachedPrediction(
            image_name="meal.jpg",
            image_bytes=PNG_BYTES,
            candidates=[(1, "chicken rice", 0.91, "chicken rice", 123)],
            low_conf=False,
            classifier_used="primary",
        )
        date_response = self.client.post(
            "/api/log",
            params={
                "image_id": image_id,
                "choice": 1,
                "portion_grams": 100,
                "log_date": "20260311",
            },
        )
        self.assertEqual(date_response.status_code, 400)
        self.assertEqual(date_response.json()["detail"], "log_date must be YYYY-MM-DD")

    def test_log_rejects_missing_prediction_and_bad_choice(self) -> None:
        missing_response = self.client.post(
            "/api/log",
            params={"image_id": "missing", "choice": 1, "portion_grams": 100},
        )
        self.assertEqual(missing_response.status_code, 404)

        image_id = "predict-bad-choice"
        app_module.prediction_cache[image_id] = app_module.CachedPrediction(
            image_name="meal.jpg",
            image_bytes=PNG_BYTES,
            candidates=[(1, "chicken rice", 0.91, "chicken rice", 123)],
            low_conf=False,
            classifier_used="primary",
        )
        choice_response = self.client.post(
            "/api/log",
            params={"image_id": image_id, "choice": 5, "portion_grams": 100},
        )
        self.assertEqual(choice_response.status_code, 400)
        self.assertEqual(choice_response.json()["detail"], "Choice out of range.")

    def test_trends_and_daily_logs(self) -> None:
        today = datetime.now().date().isoformat()
        yesterday = (datetime.now().date() - timedelta(days=1)).isoformat()

        log_prediction(
            self.conn,
            self.fernet,
            Path("today.jpg"),
            "chicken rice",
            "chicken rice",
            123,
            portion_grams=200,
            timestamp_iso=f"{today}T08:00:00",
        )
        log_prediction(
            self.conn,
            self.fernet,
            Path("yesterday.jpg"),
            "ramen",
            "ramen",
            150,
            portion_grams=100,
            timestamp_iso=f"{yesterday}T09:00:00",
        )

        trend_response = self.client.get("/api/trends")
        self.assertEqual(trend_response.status_code, 200)
        trend_payload = trend_response.json()
        self.assertEqual(trend_payload["count"], 2)
        self.assertEqual(trend_payload["total_7d"], 396.0)
        self.assertEqual(len(trend_payload["daily"]), 7)

        logs_response = self.client.get("/api/logs", params={"day": today})
        self.assertEqual(logs_response.status_code, 200)
        logs_payload = logs_response.json()
        self.assertEqual(logs_payload["count"], 1)
        self.assertEqual(logs_payload["items"][0]["food_type"], "chicken rice")
        self.assertEqual(logs_payload["items"][0]["label"], "chicken rice")

    def test_logs_reject_invalid_day(self) -> None:
        response = self.client.get("/api/logs", params={"day": "20260311"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "day must be YYYY-MM-DD")

    def test_advice_endpoint_returns_payload(self) -> None:
        log_prediction(
            self.conn,
            self.fernet,
            Path("meal.jpg"),
            "chicken rice",
            "chicken rice",
            123,
            portion_grams=200,
        )

        with patch.object(
            app_module.diet_advice,
            "load_advice_generator",
            return_value=lambda prompt, **kwargs: [
                {"generated_text": "Add more vegetables and lean protein."}
            ],
        ):
            response = self.client.get("/api/advice")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("summary", payload)
        self.assertIn("signals", payload)
        self.assertEqual(payload["source"], "model")
        self.assertEqual(payload["advice"], "Add more vegetables and lean protein.")

    def test_delete_log_removes_entry(self) -> None:
        log_prediction(
            self.conn,
            self.fernet,
            Path("meal.jpg"),
            "chicken rice",
            "chicken rice",
            123,
        )
        log_id = self.conn.execute("SELECT id FROM log").fetchone()[0]

        response = self.client.delete(f"/api/logs/{log_id}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "deleted")

        missing_response = self.client.delete(f"/api/logs/{log_id}")
        self.assertEqual(missing_response.status_code, 404)
