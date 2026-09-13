"""
Emails the results of the most recent screener run.

Two modes, chosen by whether REPORT_BASE_URL is set:

  Link mode (REPORT_BASE_URL set -- what the GitHub Actions workflow does)
      Sends a link to the report published on GitHub Pages, plus the CSV
      as an attachment. This is the mode that works on a phone: iOS Mail
      and the Files app both preview attachments with JavaScript disabled,
      so the script-rendered HTML report from widget.py opens blank (or,
      on a large payload, hangs Quick Look). A normal browser tab has no
      such restriction.

  Attachment mode (REPORT_BASE_URL unset -- e.g. running locally)
      Falls back to the previous behaviour and attaches both files, so
      nothing breaks outside the workflow.

Required environment variables (set as GitHub Actions repo secrets --
Settings > Secrets and variables > Actions):

    SMTP_SERVER   e.g. smtp.gmail.com
    SMTP_PORT     e.g. 587
    SMTP_USER     the sending account's email address
    SMTP_PASS     an app password -- NOT the account's normal login password
                  (Gmail: turn on 2-Step Verification, then generate one at
                  myaccount.google.com/apppasswords)
    EMAIL_TO      where to send the report (can be the same as SMTP_USER)

Optional:

    REPORT_BASE_URL   root URL the report is published under, no trailing
                      slash, e.g. https://yourname.github.io/pairs-screener
"""

import glob
import os
import smtplib
from email.message import EmailMessage

import config

CAVEAT = (
    "This is a statistical screen only -- not a trade signal. "
    "Review flagged pairs manually before acting on anything."
)


def _latest(pattern):
    matches = sorted(glob.glob(pattern))
    if not matches:
        raise FileNotFoundError(f"No file found matching {pattern}")
    return matches[-1]  # timestamped filenames sort chronologically


def _run_stamp(html_path):
    """pairs_report_20260904_164812.html -> 20260904_164812"""
    base = os.path.basename(html_path)
    return base[len("pairs_report_"):-len(".html")]


def build_message(csv_path, html_path, base_url):
    """
    Returns (msg, attachments) where attachments is a list of
    (path, maintype, subtype) tuples still to be added.
    """
    msg = EmailMessage()
    msg["From"] = os.environ["SMTP_USER"]
    msg["To"] = os.environ["EMAIL_TO"]

    stamp = _run_stamp(html_path)

    if base_url:
        # ?v= busts any CDN/browser cache on the always-latest index copy,
        # which is overwritten in place every run and would otherwise be
        # liable to serve you yesterday's screen.
        latest_url = f"{base_url}/?v={stamp}"
        permalink = f"{base_url}/reports/{os.path.basename(html_path)}"

        msg["Subject"] = f"Pairs screen -- {stamp}"
        msg.set_content(
            "Today's interactive report:\n"
            f"  {latest_url}\n\n"
            "Permanent link to this specific run (the link above always\n"
            "shows the most recent screen):\n"
            f"  {permalink}\n\n"
            "Open either in Safari or Chrome. The charts and sector filter\n"
            "need JavaScript, which the previewers built into Mail and the\n"
            "Files app block -- that is why the attached version used to\n"
            "open blank.\n\n"
            "The CSV attached below covers every pair tested, including the\n"
            "ones that failed cointegration, and opens fine in Numbers.\n\n"
            + CAVEAT
        )
        attachments = [(csv_path, "text", "csv")]
    else:
        msg["Subject"] = f"Pairs screen -- {os.path.basename(csv_path)}"
        msg.set_content(
            "Attached: today's pairs-screening CSV (every pair tested, "
            "including failures) and the interactive HTML report (pairs "
            "that passed Benjamini-Hochberg).\n\n"
            "Note: the HTML report needs a real browser -- attachment "
            "previewers on mobile disable JavaScript and will show it "
            "blank.\n\n"
            + CAVEAT
        )
        attachments = [
            (csv_path, "text", "csv"),
            (html_path, "text", "html"),
        ]

    return msg, attachments


def main():
    csv_path = _latest(os.path.join(config.OUTPUT_DIR, "pairs_screen_*.csv"))
    html_path = _latest(os.path.join(config.OUTPUT_DIR, "pairs_report_*.html"))
    base_url = os.environ.get("REPORT_BASE_URL", "").strip().rstrip("/")

    msg, attachments = build_message(csv_path, html_path, base_url)

    for path, maintype, subtype in attachments:
        with open(path, "rb") as f:
            msg.add_attachment(
                f.read(),
                maintype=maintype,
                subtype=subtype,
                filename=os.path.basename(path),
            )

    port = int(os.environ.get("SMTP_PORT", "587"))
    with smtplib.SMTP(os.environ["SMTP_SERVER"], port) as server:
        server.starttls()
        server.login(os.environ["SMTP_USER"], os.environ["SMTP_PASS"])
        server.send_message(msg)

    mode = f"link to {base_url}" if base_url else "attachments"
    print(f"Emailed {mode}")


if __name__ == "__main__":
    main()
