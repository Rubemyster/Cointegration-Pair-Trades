"""
Emails the most recent CSV + HTML report from output/ as attachments.
Run this right after main.py (same job, same output/ directory).

Required environment variables (set as GitHub Actions repo secrets --
Settings > Secrets and variables > Actions):

    SMTP_SERVER   e.g. smtp.gmail.com
    SMTP_PORT     e.g. 587
    SMTP_USER     the sending account's email address
    SMTP_PASS     an app password -- NOT the account's normal login password
                  (Gmail: turn on 2-Step Verification, then generate one at
                  myaccount.google.com/apppasswords)
    EMAIL_TO      where to send the report (can be the same as SMTP_USER)
"""

import glob
import os
import smtplib
from email.message import EmailMessage

import config


def _latest(pattern):
    matches = sorted(glob.glob(pattern))
    if not matches:
        raise FileNotFoundError(f"No file found matching {pattern}")
    return matches[-1]  # timestamped filenames sort chronologically


def main():
    csv_path = _latest(os.path.join(config.OUTPUT_DIR, "pairs_screen_*.csv"))
    html_path = _latest(os.path.join(config.OUTPUT_DIR, "pairs_report_*.html"))

    msg = EmailMessage()
    msg["Subject"] = f"Pairs screen -- {os.path.basename(csv_path)}"
    msg["From"] = os.environ["SMTP_USER"]
    msg["To"] = os.environ["EMAIL_TO"]
    msg.set_content(
        "Attached: today's pairs-screening CSV (every pair tested, "
        "including failures) and the interactive HTML report (pairs "
        "that passed Benjamini-Hochberg).\n\n"
        "This is a statistical screen only -- not a trade signal. "
        "Review flagged pairs manually before acting on anything."
    )

    attachments = [
        (csv_path, "text", "csv"),
        (html_path, "text", "html"),
    ]
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

    print(f"Emailed {csv_path} and {html_path} to {os.environ['EMAIL_TO']}")


if __name__ == "__main__":
    main()
