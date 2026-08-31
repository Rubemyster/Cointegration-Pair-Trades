"""
Output: writes the per-pair results table to a timestamped CSV.
"""

import os
from datetime import datetime


def write_results(results_df, output_dir="output"):
    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"pairs_screen_{timestamp}.csv"
    path = os.path.join(output_dir, filename)
    results_df.to_csv(path, index=False)
    return path
