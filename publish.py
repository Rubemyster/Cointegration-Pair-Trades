"""
Stages the most recent run's outputs into a directory ready for GitHub
Pages, so the HTML report can be viewed at a URL instead of emailed as an
attachment (iOS Mail and Files both preview attachments with JavaScript
disabled, which leaves widget.py's script-rendered report blank).

Layout produced:

    public/
      index.html                            <- copy of the latest report
      reports/pairs_report_<stamp>.html     <- dated permalink for this run
      reports/pairs_screen_<stamp>.csv      <- the matching CSV
      .nojekyll                             <- skip Jekyll processing

`index.html` is overwritten every run, so the bare Pages URL always shows
the newest screen. The dated copies accumulate on the gh-pages branch
(the workflow publishes with keep_files: true), giving you a browsable
archive of past runs at the same host.

Run after main.py, from the repo root:  python publish.py
"""

import glob
import os
import shutil

import config

PUBLIC_DIR = "public"


def _latest(pattern):
    """Newest file matching `pattern` -- timestamped names sort chronologically."""
    matches = sorted(glob.glob(pattern))
    if not matches:
        raise FileNotFoundError(
            f"No file found matching {pattern} -- run main.py first."
        )
    return matches[-1]


def stage(public_dir=PUBLIC_DIR, output_dir=None):
    """
    Copies the latest CSV/HTML into `public_dir`. Returns the paths staged,
    so a caller (or the workflow) can log exactly what went out.
    """
    output_dir = output_dir or getattr(config, "OUTPUT_DIR", "output")

    html_src = _latest(os.path.join(output_dir, "pairs_report_*.html"))
    csv_src = _latest(os.path.join(output_dir, "pairs_screen_*.csv"))

    reports_dir = os.path.join(public_dir, "reports")
    os.makedirs(reports_dir, exist_ok=True)

    html_dated = os.path.join(reports_dir, os.path.basename(html_src))
    csv_dated = os.path.join(reports_dir, os.path.basename(csv_src))
    index_path = os.path.join(public_dir, "index.html")

    shutil.copy2(html_src, html_dated)
    shutil.copy2(csv_src, csv_dated)
    shutil.copy2(html_src, index_path)

    # Without this, GitHub runs the published directory through Jekyll,
    # which strips files/directories beginning with an underscore and adds
    # a build step we get nothing from -- everything here is already static.
    open(os.path.join(public_dir, ".nojekyll"), "w").close()

    return {
        "index": index_path,
        "html_dated": html_dated,
        "csv_dated": csv_dated,
        "html_src": html_src,
        "csv_src": csv_src,
    }


def main():
    staged = stage()
    size_mb = os.path.getsize(staged["index"]) / (1024 * 1024)
    print(f"Staged {staged['html_src']} -> {staged['index']} ({size_mb:.1f} MB)")
    print(f"Dated copy: {staged['html_dated']}")
    print(f"CSV copy:   {staged['csv_dated']}")


if __name__ == "__main__":
    main()
