from pathlib import Path
import sys

BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BACKEND_DIR.parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from backend.src.featured_prototype import parse_args, run_demo


def main() -> None:
    args = parse_args()
    img_dir = Path(args.image_dir)
    run_demo(img_dir, args.num_images)


if __name__ == "__main__":
    main()
