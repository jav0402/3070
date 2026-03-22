from __future__ import annotations

import sys
import unittest
from datetime import datetime
from pathlib import Path


class TeeStream:
    def __init__(self, *streams) -> None:
        self.streams = streams

    def write(self, data: str) -> None:
        for stream in self.streams:
            stream.write(data)

    def flush(self) -> None:
        for stream in self.streams:
            stream.flush()


def main() -> int:
    tests_dir = Path(__file__).resolve().parent
    report_dir = tests_dir / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = report_dir / f"unit_test_report_{timestamp}.txt"

    suite = unittest.defaultTestLoader.discover(
        str(tests_dir),
        pattern="test_unit.py",
    )

    with report_path.open("w", encoding="utf-8") as report_file:
        stream = TeeStream(sys.stdout, report_file)
        runner = unittest.TextTestRunner(stream=stream, verbosity=2)
        result = runner.run(suite)

        stream.write(f"\nReport saved to: {report_path}\n")
        stream.flush()

    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
