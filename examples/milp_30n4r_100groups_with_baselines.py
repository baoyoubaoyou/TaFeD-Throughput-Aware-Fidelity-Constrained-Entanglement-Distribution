"""Run the 30-node / 4-request strict-aligned benchmark for 100 groups."""

from pathlib import Path

import milp_30n4r_10groups_with_baselines as benchmark


OUTPUT_DIR = Path(__file__).resolve().parent / "results"

benchmark.TARGET_GROUPS = 100
benchmark.RAW_CSV = OUTPUT_DIR / "milp_30n4r_100groups_with_baselines_raw.csv"
benchmark.SUMMARY_CSV = OUTPUT_DIR / "milp_30n4r_100groups_with_baselines_summary.csv"
benchmark.JSON_PATH = OUTPUT_DIR / "milp_30n4r_100groups_with_baselines.json"


if __name__ == "__main__":
    benchmark.main()
