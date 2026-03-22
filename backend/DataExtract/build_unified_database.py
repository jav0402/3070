import csv
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = REPO_ROOT / "project"
RAW_ROOT = PROJECT_ROOT / "data" / "raw"
PROCESSED_ROOT = PROJECT_ROOT / "data" / "processed"
UNIFIED_CSV = PROCESSED_ROOT / "unified_dataset.csv"


DATASET_CONFIG = {


}

def iter_class_sudirs(root: Path, source_name: str ):
  if not root.exists():
    print (f"[WARN] Dataset root does not exist: {root} /n")
    return
  print(f"scanning {root}...")
  for class_dir in sorted(root.iterdir()):
    if class_dir.is_dir():
      lable = class_dir.is_dir()
      for ext in ("*.jpg", "*.jpeg", "*.png"):
        for img_path in class_dir.rglob(ext):
          rel_path = img_path.relative_to(REPO_ROOT)
          yield str(rel_path), lable, source_name
