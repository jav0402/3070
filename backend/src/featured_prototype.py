from __future__ import annotations

import argparse
import os
import random
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Tuple

try:
   import torch
except ImportError:
   torch = None

try:
   from PIL import Image
except ImportError:
   Image = None

try:
   from torchvision import models, transforms
except ImportError:
   models = None
   transforms = None

import csv

try:
   from sentence_transformers import SentenceTransformer, util
except ImportError:
   SentenceTransformer = None
   util = None

try:
   from transformers import pipeline
except ImportError:
   pipeline = None

try:
   from cryptography.fernet import Fernet
except ImportError:
   Fernet = None

import shutil


# cfg
DEFAULT_DATA_DIR = Path(__file__).resolve().parents[1] / "data"
DEFAULT_IMG_DIR = DEFAULT_DATA_DIR / "sample_images"
# DEFAULT_IMG_DIR = DEFAULT_DATA_DIR / "recreate"
ASIAN_OPENFOODFACTS_CSV = DEFAULT_DATA_DIR / "asian_openfoodfacts.csv"
NUTRITION_CSV = ASIAN_OPENFOODFACTS_CSV
LOG_CSV = DEFAULT_DATA_DIR / "featured_log.csv"
GENERIC_OPENFOODFACTS_CSV = DEFAULT_DATA_DIR / "generic_openfoodfacts.csv"
LOG_DIR = DEFAULT_DATA_DIR / "logs"
LOG_IMAGE_DIR = LOG_DIR / "images"
DB_PATH = LOG_DIR / "calorie_log.db"
DB_KEY_PATH = LOG_DIR / "db.key"
DB_KEY_ENV = "CALORIE_DB_KEY"

# food gate + classifier
FOOD_GATE_MODEL_ID = os.environ.get(
   "FOOD_GATE_MODEL_ID", "prithivMLmods/Food-or-Not-SigLIP2"
)
FOOD_CLASSIFIER_MODEL_ID = os.environ.get(
   "FOOD_CLASSIFIER_MODEL_ID", "Albertbeta123/resnet-50-chinese-food"
)
FOOD_GATE_THRESHOLD = 0.50

# minimum softmax probability to consider a prediction reasonably confident
CONFIDENCE_THRESHOLD = 0.25

def load_nutrition_from_csv(csv_path: Path) -> Dict[str, int]:
   """load nutritional table from CSV if available"""
   table: Dict[str, int] = {}
   if not csv_path.exists():
      return table
   try:
      with csv_path.open("r", newline="") as f:
         reader = csv.DictReader(f)
         for row in reader:
            name = (row.get("name") or "").strip().lower()
            cal_str = (row.get("calories_per_100g") or "").strip()
            if not name or not cal_str:
               continue
            try:
               table[name] = int(float(cal_str))
            except ValueError:
               continue
   except Exception as e:
      print(f"[WARN] failed to load nutritional CSV: {e}")
   return table


def load_macros_from_csv(csv_path: Path) -> Dict[str, Dict[str, float]]:
   """load name + macros + calories from CSV if available"""
   table: Dict[str, Dict[str, float]] = {}
   if not csv_path.exists():
      return table
   try:
      with csv_path.open("r", newline="") as f:
         reader = csv.DictReader(f)
         for row in reader:
            name = (row.get("name") or "").strip().lower()
            if not name:
               continue
            try:
               calories = float(row.get("calories_per_100g") or "")
               protein = float(row.get("protein_g_per_100g") or "")
               fat = float(row.get("fat_g_per_100g") or "")
               carbs = float(row.get("carbs_g_per_100g") or "")
            except ValueError:
               continue
            table[name] = {
               "calories_per_100g": calories,
               "protein_g_per_100g": protein,
               "fat_g_per_100g": fat,
               "carbs_g_per_100g": carbs,
            }
   except Exception as e:
      print(f"[WARN] failed to load macros CSV: {e}")
   return table


def build_nutrition_table(csv_path: Path) -> Dict[str, int]:
   """load nutrition data from CSV"""
   return load_nutrition_from_csv(csv_path)


def require_sentence_transformers() -> None:
   if SentenceTransformer is None or util is None:
      raise RuntimeError(
         "sentence-transformers is required for semantic retrieval. "
         "Install with: pip install sentence-transformers"
      )


def require_transformers() -> None:
   if pipeline is None:
      raise RuntimeError(
         "transformers is required for food gate/classification. "
         "Install with: pip install transformers"
      )


def require_cryptography() -> None:
   if Fernet is None:
      raise RuntimeError(
         "cryptography is required for SQLite field encryption. "
         "Install with: pip install cryptography"
      )


def require_ml_dependencies() -> None:
   if torch is None or Image is None or models is None or transforms is None:
      raise RuntimeError(
         "torch, torchvision, and pillow are required for image inference. "
         "Install the project environment before running the ML pipeline."
      )


def get_fernet(key_path: Path | None = None) -> "Fernet":
   require_cryptography()
   if key_path is None:
      key_path = DB_KEY_PATH

   env_key = os.environ.get(DB_KEY_ENV)
   if env_key:
      return Fernet(env_key.strip().encode("ascii"))

   if key_path.exists():
      key_text = key_path.read_text(encoding="utf-8").strip()
      return Fernet(key_text.encode("ascii"))

   key_bytes = Fernet.generate_key()
   key_path.parent.mkdir(parents=True, exist_ok=True)
   key_path.write_text(key_bytes.decode("ascii"), encoding="utf-8")
   return Fernet(key_bytes)


def encrypt_text(text: str, fernet: "Fernet") -> str:
   token = fernet.encrypt(text.encode("utf-8"))
   return token.decode("ascii")


def decrypt_text(token: str, fernet: "Fernet") -> str:
   return fernet.decrypt(token.encode("ascii")).decode("utf-8")


def init_db(db_path: Path) -> None:
   db_path.parent.mkdir(parents=True, exist_ok=True)
   with sqlite3.connect(db_path) as conn:
      conn.execute("PRAGMA foreign_keys = ON")
      conn.execute(
         """
         CREATE TABLE IF NOT EXISTS nutrition (
            name TEXT PRIMARY KEY,
            calories_per_100g INTEGER NOT NULL
         )
         """
      )
      conn.execute(
         """
         CREATE TABLE IF NOT EXISTS nutrition_macros (
            name TEXT PRIMARY KEY,
            calories_per_100g REAL NOT NULL,
            protein_g_per_100g REAL NOT NULL,
            fat_g_per_100g REAL NOT NULL,
            carbs_g_per_100g REAL NOT NULL
         )
         """
      )
      conn.execute(
         """
         CREATE TABLE IF NOT EXISTS log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            image_name_enc TEXT NOT NULL,
            raw_label_enc TEXT NOT NULL,
            food_type TEXT NOT NULL,
            calories_per_100g INTEGER NOT NULL,
            portion_grams REAL,
            calories_total REAL
         )
         """
      )
      conn.execute(
         "CREATE INDEX IF NOT EXISTS idx_log_timestamp ON log(timestamp)"
      )
      ensure_log_columns(conn)


def ensure_log_columns(conn: sqlite3.Connection) -> None:
   existing = {row[1] for row in conn.execute("PRAGMA table_info(log)").fetchall()}
   if "portion_grams" not in existing:
      conn.execute("ALTER TABLE log ADD COLUMN portion_grams REAL")
   if "calories_total" not in existing:
      conn.execute("ALTER TABLE log ADD COLUMN calories_total REAL")
   conn.commit()


def open_db(db_path: Path) -> sqlite3.Connection:
   conn = sqlite3.connect(db_path, check_same_thread=False)
   conn.execute("PRAGMA foreign_keys = ON")
   return conn


def get_db_connection(db_path: Path) -> sqlite3.Connection:
   init_db(db_path)
   return open_db(db_path)


def fetch_nutrition_table(conn: sqlite3.Connection) -> Dict[str, int]:
   rows = conn.execute(
      "SELECT name, calories_per_100g FROM nutrition"
   ).fetchall()
   return {name: int(calories) for name, calories in rows}


def fetch_nutrition_macros_table(
      conn: sqlite3.Connection
) -> Dict[str, Dict[str, float]]:
   rows = conn.execute(
      """
      SELECT name, calories_per_100g, protein_g_per_100g, fat_g_per_100g, carbs_g_per_100g
      FROM nutrition_macros
      """
   ).fetchall()
   return {
      name: {
         "calories_per_100g": float(calories),
         "protein_g_per_100g": float(protein),
         "fat_g_per_100g": float(fat),
         "carbs_g_per_100g": float(carbs),
      }
      for name, calories, protein, fat, carbs in rows
   }


def upsert_nutrition_table(
      conn: sqlite3.Connection,
      nutrition_table: Dict[str, int]
) -> None:
   if not nutrition_table:
      return
   conn.executemany(
      """
      INSERT OR REPLACE INTO nutrition (name, calories_per_100g)
      VALUES (?, ?)
      """,
      list(nutrition_table.items()),
   )
   conn.commit()


def upsert_nutrition_macros_table(
      conn: sqlite3.Connection,
      macros_table: Dict[str, Dict[str, float]]
) -> None:
   if not macros_table:
      return
   rows = []
   for name, macros in macros_table.items():
      rows.append(
         (
            name,
            float(macros["calories_per_100g"]),
            float(macros["protein_g_per_100g"]),
            float(macros["fat_g_per_100g"]),
            float(macros["carbs_g_per_100g"]),
         )
      )
   conn.executemany(
      """
      INSERT OR REPLACE INTO nutrition_macros (
         name,
         calories_per_100g,
         protein_g_per_100g,
         fat_g_per_100g,
         carbs_g_per_100g
      ) VALUES (?, ?, ?, ?, ?)
      """,
      rows,
   )
   conn.commit()


def ensure_nutrition_macros_table(
      conn: sqlite3.Connection,
      macros_csv: Path = GENERIC_OPENFOODFACTS_CSV,
      primary_macros_csv: Path = ASIAN_OPENFOODFACTS_CSV,
) -> Dict[str, Dict[str, float]]:
   table = fetch_nutrition_macros_table(conn)
   if table:
      return table
   table = load_macros_from_csv(primary_macros_csv)
   if not table:
      table = load_macros_from_csv(macros_csv)
   upsert_nutrition_macros_table(conn, table)
   return table


def nutrition_table_from_macros(
      macros_table: Dict[str, Dict[str, float]]
) -> Dict[str, int]:
   return {
      name: int(round(values["calories_per_100g"]))
      for name, values in macros_table.items()
   }


def ensure_nutrition_table(
      conn: sqlite3.Connection,
      nutrition_csv: Path = NUTRITION_CSV,
      macros_csv: Path = GENERIC_OPENFOODFACTS_CSV
) -> Dict[str, int]:
   table = fetch_nutrition_table(conn)
   if table:
      return table
   macros_table = ensure_nutrition_macros_table(
      conn,
      macros_csv=macros_csv,
      primary_macros_csv=nutrition_csv,
   )
   if macros_table:
      table = nutrition_table_from_macros(macros_table)
      upsert_nutrition_table(conn, table)
      return table
   table = build_nutrition_table(nutrition_csv)
   upsert_nutrition_table(conn, table)
   return table


def get_device() -> torch.device:
  """if gpu available chose gpu"""
  require_ml_dependencies()
  if torch.cuda.is_available():
    return torch.device("cuda")
  return torch.device("cpu")


def build_transform() -> transforms.Compose:
  """imagenet pipeline"""
  require_ml_dependencies()
  return transforms.Compose([
    transforms.Resize(256),
    transforms.CenterCrop(224),
    transforms.ToTensor(),
    transforms.Normalize(
      mean=[0.485, 0.456, 0.406],
      std=[0.229, 0.224, 0.225]
    )
  ])


def load_model(device: torch.device) -> Tuple[torch.nn.Module, List[str]]:
  """load pre-train models and class labels"""
  require_ml_dependencies()
  weights = models.ResNet18_Weights.DEFAULT
  model = models.resnet18(weights=weights)
  class_names = weights.meta.get("categories", [])
  model.eval()
  model.to(device)

  class_name: List[str] = weights.meta.get("categories", [])
  return model, class_name


def get_hf_device(device: torch.device) -> int:
   require_ml_dependencies()
   if device.type == "cuda":
      return 0
   return -1


def load_food_gate(device: torch.device):
   """load pretrained food vs non-food gate"""
   require_transformers()
   hf_device = get_hf_device(device)
   return pipeline(
      "image-classification",
      model=FOOD_GATE_MODEL_ID,
      device=hf_device,
   )


def load_food_classifier(device: torch.device):
   """load pretrained Food-101 classifier"""
   require_transformers()
   hf_device = get_hf_device(device)
   return pipeline(
      "image-classification",
      model=FOOD_CLASSIFIER_MODEL_ID,
      device=hf_device,
   )


def is_food_label(label: str) -> bool | None:
   label_l = label.lower()
   if "food" in label_l and ("not" in label_l or "non" in label_l):
      return False
   if "food" in label_l:
      return True
   return None


def food_gate_decision(
      gate_pipe,
      image: Image.Image,
      threshold: float
) -> Tuple[bool, float, str]:
   results = gate_pipe(image)
   if not results:
      return False, 0.0, "unknown"

   food_score = None
   best_label = results[0].get("label", "unknown")
   for item in results:
      label = item.get("label", "")
      score = float(item.get("score", 0.0))
      tag = is_food_label(label)
      if tag is True:
         food_score = score if food_score is None else max(food_score, score)
         best_label = label
      elif tag is False and food_score is None:
         best_label = label

   if food_score is None:
      top_label = results[0].get("label", "")
      top_score = float(results[0].get("score", 0.0))
      if is_food_label(top_label):
         return top_score >= threshold, top_score, top_label
      return False, top_score, top_label

   return food_score >= threshold, food_score, best_label


def load_image_path(image_dir: Path, num_images: int) -> List[Path]:
  """retrieve set amount of image from folder"""
  if not image_dir.exists():
    raise FileNotFoundError(f"folder does not exist: {image_dir}")
  image_paths = [
    p for p in image_dir.iterdir()
    if p.suffix.lower() in {".jpg", ".jpeg", ".png"}
  ]

  if not image_paths:
    raise RuntimeError(f"no images found in {image_dir}")
  random.shuffle(image_paths)
  return image_paths[:num_images]


def preprocess_image(path: Path, transform: transforms.Compose) -> torch.tensor:
  """load image and apply transforms"""
  img = Image.open(path).convert("RGB")
  return transform(img).unsqueeze(0)


def preprocess_pil_image(image: Image.Image, transform: transforms.Compose) -> torch.Tensor:
  """apply transforms to an already-loaded PIL image"""
  require_ml_dependencies()
  return transform(image.convert("RGB")).unsqueeze(0)


def open_image(path: Path) -> Image.Image:
   require_ml_dependencies()
   return Image.open(path).convert("RGB")


def predict(
    model: torch.nn.Module,
    input_tensor: torch.Tensor,
    device: torch.device,
    class_names: List[str],
    top_k: int = 3
) -> List[Tuple[str, float]]:
  """return top-k predictions (label, probability)."""
  input_tensor = input_tensor.to(device)

  with torch.no_grad():
    outputs = model(input_tensor)
    probs = torch.nn.functional.softmax(outputs, dim=1)

  top_probs, top_indices = probs.topk(top_k, dim=1)

  top_probs = top_probs.cpu().numpy()[0]
  top_indices = top_indices.cpu().numpy()[0]

  results = []
  for idx, prob in zip(top_indices, top_probs):
    label = class_names[idx] if idx < len(class_names) else f"class_{idx}"
    results.append((label, float(prob)))

  return results


def load_text_encoder() -> "SentenceTransformer":
   """load minilm text encoder (required)"""
   require_sentence_transformers()
   try:
      model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
      return model
   except Exception as e:
      raise RuntimeError(f"failed to load MiniLM model: {e}") from e


def semantic_match_key(
      label: str,
      nutrition_keys: list[str],
      encoder: "SentenceTransformer | None" = None,
      key_embeddings: torch.Tensor | None = None
) -> str:
   """return best matching nutritional key for given label"""
   label_l = label.lower()

   def simple_match() -> str:
      for k in nutrition_keys:
         if k in label_l:
            return k
      return "unknown"

   if encoder is None or util is None:
      return simple_match()

   try:
      require_ml_dependencies()
      query_emb = encoder.encode([label_l], normalize_embeddings=True)
      query_tensor = torch.from_numpy(query_emb).float()
      if key_embeddings is None:
         key_vecs = encoder.encode(nutrition_keys, normalize_embeddings=True)
         key_embeddings = torch.from_numpy(key_vecs).float()
      scores = util.cos_sim(query_tensor, key_embeddings)[0]
      best_index = int(torch.argmax(scores).item())
      return nutrition_keys[best_index]
   except Exception as e:
      print(f"[WARN] semantic match failed, falling back to simple match: {e}")
      return simple_match()


def rough_cal_estimate(
      label: str,
      nutrition_table: Dict[str, int],
      semantic_key: str | None = None
) -> Tuple[str, int]:
  """Map a label to a nutrition table entry; no hard-coded fallbacks."""
  if semantic_key is not None:
     sk = semantic_key.lower()
     if sk in nutrition_table:
        key = sk
        calories = nutrition_table.get(key, -1)
        return key, calories

  t = label.lower()
  for k in nutrition_table.keys():
     if k in t:
        key = k
        calories = nutrition_table.get(key, -1)
        return key, calories

  return "unknown", -1


def migrate_csv_log_to_sqlite(
      conn: sqlite3.Connection,
      fernet: "Fernet",
      csv_path: Path = LOG_CSV
) -> int:
   if not csv_path.exists():
      return 0

   existing = conn.execute("SELECT COUNT(*) FROM log").fetchone()
   if existing and existing[0] > 0:
      return 0

   rows_to_insert: list[tuple[str, str, str, str, int]] = []
   with csv_path.open("r", newline="") as f:
      reader = csv.DictReader(f)
      for row in reader:
         ts = (row.get("timestamp") or "").strip()
         image_name = (row.get("image_name") or "").strip()
         raw_label = (row.get("raw_label") or "").strip()
         food_type = (row.get("food_type") or "").strip()
         cal_str = (row.get("calories_per_100g") or "").strip()
         if not ts or not image_name or not raw_label or not food_type:
            continue
         try:
            calories = int(float(cal_str))
         except ValueError:
            continue
         rows_to_insert.append(
            (
               ts,
               encrypt_text(image_name, fernet),
               encrypt_text(raw_label, fernet),
               food_type,
               calories,
            )
         )

   if not rows_to_insert:
      return 0

   conn.executemany(
      """
      INSERT INTO log (
         timestamp, image_name_enc, raw_label_enc, food_type, calories_per_100g
      ) VALUES (?, ?, ?, ?, ?)
      """,
      rows_to_insert,
   )
   conn.commit()
   return len(rows_to_insert)


def log_prediction(
      conn: sqlite3.Connection,
      fernet: "Fernet",
      image_path: Path,
      label: str,
      food_type: str,
      calories_per_100g: int,
      portion_grams: float | None = None,
      timestamp_iso: str | None = None,
) -> None:
   # encrypt label/image fields; keep calories plaintext for aggregation
   enc_image_name = encrypt_text(image_path.name, fernet)
   enc_label = encrypt_text(label, fernet)
   calories_total = None
   if portion_grams is not None and calories_per_100g >= 0:
      calories_total = (portion_grams / 100.0) * calories_per_100g
   ts = timestamp_iso or datetime.now().isoformat(timespec="seconds")
   conn.execute(
      """
      INSERT INTO log (
         timestamp,
         image_name_enc,
         raw_label_enc,
         food_type,
         calories_per_100g,
         portion_grams,
         calories_total
      ) VALUES (?, ?, ?, ?, ?, ?, ?)
      """,
      (
         ts,
         enc_image_name,
         enc_label,
         food_type,
         calories_per_100g,
         portion_grams,
         calories_total,
      ),
   )
   conn.commit()


def log_prediction_csv(
      image_path: Path,
      label: str,
      food_type: str,
      calories_per_100g: int,
      csv_path: Path = LOG_CSV,
      timestamp_iso: str | None = None,
) -> None:
   csv_path.parent.mkdir(parents=True, exist_ok=True)
   is_new_file = not csv_path.exists()

   with csv_path.open("a", newline="") as f:
      writer = csv.writer(f)
      if is_new_file:
         writer.writerow(
            ["timestamp", "image_name", "raw_label", "food_type", "calories_per_100g"]
         )
      writer.writerow(
         [
            (timestamp_iso or datetime.now().isoformat(timespec="seconds")),
            image_path.name,
            label,
            food_type,
            calories_per_100g,
         ]
      )


def calculate_last_7_days_stats(conn: sqlite3.Connection) -> Tuple[int, float]:
   cutoff = (datetime.now() - timedelta(days=7)).isoformat(timespec="seconds")
   rows = conn.execute(
      """
      SELECT calories_per_100g
      FROM log
      WHERE timestamp >= ? AND calories_per_100g >= 0
      """,
      (cutoff,),
   ).fetchall()
   if not rows:
      return 0, 0.0
   total = sum(int(row[0]) for row in rows)
   count = len(rows)
   return count, total / count


def calculate_last_7_days_daily_totals(
      conn: sqlite3.Connection,
) -> list[dict[str, float | int | str]]:
   today = datetime.now().date()
   start_date = today - timedelta(days=6)
   cutoff = datetime.combine(start_date, datetime.min.time()).isoformat(timespec="seconds")

   rows = conn.execute(
      """
      SELECT
         substr(timestamp, 1, 10) AS day,
         SUM(
            CASE
               WHEN calories_total IS NOT NULL THEN calories_total
               ELSE calories_per_100g
            END
         ) AS total_calories,
         COUNT(*) AS count
      FROM log
      WHERE timestamp >= ? AND calories_per_100g >= 0
      GROUP BY day
      ORDER BY day ASC
      """,
      (cutoff,),
   ).fetchall()

   totals_by_day = {day: (float(total), int(count)) for day, total, count in rows}
   results: list[dict[str, float | int | str]] = []
   for i in range(7):
      day = (start_date + timedelta(days=i)).isoformat()
      total, count = totals_by_day.get(day, (0.0, 0))
      results.append(
         {
            "day": day,
            "total_calories": round(total, 2),
            "count": count,
         }
      )
   return results


def calculate_last_7_days_stats_csv(
      csv_path: Path = LOG_CSV
) -> Tuple[int, float]:
   if not csv_path.exists():
      return 0, 0.0

   cutoff = datetime.now() - timedelta(days=7)
   total = 0
   count = 0

   with csv_path.open("r", newline="") as f:
      reader = csv.DictReader(f)
      for row in reader:
         ts_str = row.get("timestamp")
         cal_str = row.get("calories_per_100g")
         if not ts_str or not cal_str:
            continue
         try:
            ts = datetime.fromisoformat(ts_str)
            cals = int(cal_str)
         except ValueError:
            continue
         if ts < cutoff or cals < 0:
            continue
         total += cals
         count += 1

   if count == 0:
      return 0, 0.0
   return count, total / count


def summarise_last_7_days(conn: sqlite3.Connection) -> None:
   count, avg = calculate_last_7_days_stats(conn)
   if count == 0:
      print("[INFO] no entries in the last 7 days")
      return
   print(f"[INFO] last 7 days: {count} logged items, avg {avg:.1f} kcal/100g")


def summarise_last_7_days_csv(csv_path: Path = LOG_CSV) -> None:
   count, avg = calculate_last_7_days_stats_csv(csv_path)
   if count == 0:
      print("[INFO] no entries in the last 7 days")
      return
   print(f"[INFO] last 7 days: {count} logged items, avg {avg:.1f} kcal/100g")


def save_last_image_copy(src_path: Path):
   # copy the processed image into backend/data/logs/images
   LOG_IMAGE_DIR.mkdir(parents=True, exist_ok=True)

   dst_path = LOG_IMAGE_DIR / src_path.name
   try:
      shutil.copy(src_path, dst_path)
      print(f"[INFO] saved a copy to {dst_path}")
   except Exception as e:
      print(f"[WARN] failed to save image copy: {e}")


def wipe_image_log_folder():
   # delete all files in backend/data/logs/images at the start of each run
   if not LOG_IMAGE_DIR.exists():
      return
   for item in LOG_IMAGE_DIR.iterdir():
      try:
         if item.is_file():
            item.unlink()
      except Exception as e:
         print(f"[WARN] failed to remove {item}: {e}")


def run_demo(image_dir: Path, num_images: int):
   import generalClassifier as gc

   device = get_device()
   print(f"[INFO] using device: {device}")

   # pipeline: preprocess -> classify -> semantic retrieval -> nutrition lookup -> logging -> trend
   wipe_image_log_folder()
   print("[INFO] log image folder wiped for new run")

   gate_pipe = load_food_gate(device)
   food_pipe = load_food_classifier(device)
   general_food_classifier = gc.load_general_classifier(device)

   encoder = load_text_encoder()

   use_sqlite = True
   fernet: "Fernet | None" = None
   conn: sqlite3.Connection | None = None
   try:
      try:
         fernet = get_fernet()
         conn = get_db_connection(DB_PATH)
         nutrition_table = ensure_nutrition_table(
            conn,
            nutrition_csv=NUTRITION_CSV,
            macros_csv=GENERIC_OPENFOODFACTS_CSV,
         )
         imported = migrate_csv_log_to_sqlite(conn, fernet, csv_path=LOG_CSV)
         if imported:
            print(f"[INFO] imported {imported} CSV log entries into SQLite")
      except Exception as e:
         use_sqlite = False
         if conn is not None:
            conn.close()
            conn = None
         print(f"[WARN] sqlite unavailable, using CSV fallback: {e}")
         nutrition_table = build_nutrition_table(NUTRITION_CSV)

      nutrition_keys = sorted(nutrition_table.keys())

      key_embeddings: torch.Tensor | None = None
      try:
         key_vecs = encoder.encode(nutrition_keys, normalize_embeddings=True)
         key_embeddings = torch.from_numpy(key_vecs).float()
      except Exception as e:
         print(f"[WARN] failed to precompute nutrition key embeddings: {e}")
         key_embeddings = None

      image_paths = load_image_path(image_dir, num_images)
      print(f"[INFO] found {len(image_paths)} images \n")

      for img_path in image_paths:
         print("=" * 60)
         print(f"image: {img_path.name}")

         img = open_image(img_path)
         is_food, food_score, gate_label = food_gate_decision(
            gate_pipe,
            img,
            threshold=FOOD_GATE_THRESHOLD,
         )
         if not is_food:
            print(
              f"[WARN] gate predicted non-food ({gate_label}, {food_score:.3f}); "
              "skipping classification."
            )
            if use_sqlite and conn is not None and fernet is not None:
               log_prediction(conn, fernet, img_path, "unknown", "non-food", -1)
            else:
               log_prediction_csv(img_path, "unknown", "non-food", -1)
            save_last_image_copy(img_path)
            continue

         preds, low_conf, classifier_used = gc.classify_with_fallback(
            img,
            food_pipe,
            general_food_classifier,
            threshold=gc.GENERAL_CLASSIFIER_TRIGGER,
            top_k=3,
         )
         if not preds:
            print("[WARN] no predictions returned for this image")
            continue

         candidates = []

         for rank, (label, prob) in enumerate(preds, start=1):
            semantic_key = semantic_match_key(
              label,
              nutrition_keys,
              encoder=encoder,
              key_embeddings=key_embeddings,
            )
            food_type, calories = rough_cal_estimate(
              label,
              nutrition_table=nutrition_table,
              semantic_key=semantic_key,
            )
            candidates.append((rank, label, prob, food_type, calories))

         for rank, label, prob, food_type, calories in candidates:
            cal_text = (
               f" {calories} kcal/100g (approx)" if calories > 0 else "N/A"
            )
            print(
              f"top {rank}: {label:30s}. "
              f"prob = {prob:.3f}. "
              f"type = {food_type:12s}. "
              f"calories = {cal_text}"
            )

         print(f"[INFO] classifier used: {classifier_used}")

         if low_conf:
            print(
              f"[WARN] primary classifier remained below fallback threshold "
              f"{gc.GENERAL_CLASSIFIER_TRIGGER:.2f}; predictions may be unreliable."
            )

         while True:
            try:
               choice_str = input(
                 f"Choose best match [1-{len(candidates)} or 0 for none]: "
               ).strip()
               choice = int(choice_str)
            except ValueError:
               print("Please enter a number.")
               continue

            if choice == 0:
               chosen = None
               break
            if 1 <= choice <= len(candidates):
               chosen = candidates[choice - 1]
               break
            print(f"Please enter a value between 0 and {len(candidates)}.")

         if chosen is not None:
            _, label, _, food_type, calories = chosen
            if use_sqlite and conn is not None and fernet is not None:
               log_prediction(conn, fernet, img_path, label, food_type, calories)
            else:
               log_prediction_csv(img_path, label, food_type, calories)
            save_last_image_copy(img_path)
            print(
              f"[INFO] logged choice: {food_type} "
              f"({calories} kcal/100g)"
            )
         else:
            if use_sqlite and conn is not None and fernet is not None:
               log_prediction(conn, fernet, img_path, "unknown", "unknown", -1)
            else:
               log_prediction_csv(img_path, "unknown", "unknown", -1)
            save_last_image_copy(img_path)
            print("[INFO] user selected 'none'; logged as unknown.")

         print()

      if use_sqlite and conn is not None:
         summarise_last_7_days(conn)
      else:
         summarise_last_7_days_csv()
   finally:
      if conn is not None:
         conn.close()


def parse_args():
   parser = argparse.ArgumentParser(description="CM3070 Featured prototype")
   parser.add_argument(
      "--image-dir",
      type=str,
      default=str(DEFAULT_IMG_DIR),
      help="Folder containing sample images"
   )
   parser.add_argument(
      "--num-images",
      type=int,
      default=3,
      help="how many images to test"
   )
   return parser.parse_args()


if __name__ == "__main__":
   args = parse_args()
   img_dir = Path(args.image_dir)
   run_demo(img_dir, args.num_images)
