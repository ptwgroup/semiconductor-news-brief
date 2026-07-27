from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from semibrief.mailer import send_brief
from semibrief.models import Brief


def test_smtp_failure_propagates(monkeypatch) -> None:
    for key, value in {
        "SMTP_HOST": "smtp.test",
        "SMTP_PORT": "587",
        "EMAIL_FROM": "from@example.com",
        "EMAIL_TO": "to@example.com",
    }.items():
        monkeypatch.setenv(key, value)
    now = datetime.now(UTC)
    brief = Brief("Test", "Text", "<p>Text</p>", [], now, now, 0, 0)
    smtp = MagicMock()
    smtp.__enter__.return_value = smtp
    smtp.send_message.side_effect = OSError("rejected")
    with patch("smtplib.SMTP", return_value=smtp):
        try:
            send_brief(brief)
        except OSError:
            pass
        else:
            raise AssertionError("SMTP failure must propagate")
