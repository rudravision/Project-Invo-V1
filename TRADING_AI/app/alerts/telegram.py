"""
Telegram alerts (spec step 13).

Refuses to send a trading recommendation when the data-quality gate has
failed -- it sends the SIGNAL DISABLED notice instead. This is deliberate:
a silent bad signal is far more dangerous than a loud warning.
"""

from __future__ import annotations

import datetime as dt
import logging
from typing import Any

import requests

log = logging.getLogger(__name__)

API = "https://api.telegram.org/bot{token}/{method}"
MAX_LEN = 4000          # Telegram hard limit is 4096


class TelegramNotifier:
    def __init__(self, token: str | None, chat_id: str | None,
                 timeout: int = 15):
        self.token = token
        self.chat_id = chat_id
        self.timeout = timeout

    @property
    def configured(self) -> bool:
        return bool(self.token and self.chat_id)

    def health_check(self) -> tuple[bool, str]:
        if not self.configured:
            return False, ("Not configured. Set TELEGRAM_BOT_TOKEN and "
                           "TELEGRAM_CHAT_ID in config/.env")
        try:
            r = requests.get(API.format(token=self.token, method="getMe"),
                             timeout=self.timeout)
            if r.status_code == 200 and r.json().get("ok"):
                return True, f"bot @{r.json()['result'].get('username')}"
            return False, f"HTTP {r.status_code}: {r.text[:120]}"
        except requests.RequestException as e:
            return False, f"{type(e).__name__}: {e}"

    def send(self, text: str, silent: bool = False) -> bool:
        """Send a message. Returns False on failure rather than raising."""
        if not self.configured:
            log.warning("Telegram not configured; message not sent.")
            return False
        ok = True
        for chunk in _chunks(text, MAX_LEN):
            try:
                r = requests.post(
                    API.format(token=self.token, method="sendMessage"),
                    json={"chat_id": self.chat_id, "text": chunk,
                          "parse_mode": "HTML",
                          "disable_notification": silent,
                          "disable_web_page_preview": True},
                    timeout=self.timeout)
                if r.status_code != 200:
                    log.error("Telegram send failed: %s %s",
                              r.status_code, r.text[:200])
                    ok = False
            except requests.RequestException as e:
                log.error("Telegram send error: %s", e)
                ok = False
        return ok

    # -- structured messages ----------------------------------------------
    def send_signal_disabled(self, reasons: str) -> bool:
        return self.send(
            "<b>&#9888; SIGNAL DISABLED - DATA QUALITY FAILURE</b>\n\n"
            f"<pre>{_esc(reasons)}</pre>\n"
            f"<i>{dt.datetime.now():%Y-%m-%d %H:%M}</i>\n"
            "No trading recommendation will be issued until this is resolved."
        )

    def send_ranking(self, ranked: Any, top_n: int = 10,
                     quality_ok: bool = True, synthetic: bool = False,
                     quality_note: str = "") -> bool:
        """Send the ranking, but ONLY if it is safe to act on."""
        if synthetic:
            return self.send(
                "<b>TRADING_AI - demo run</b>\n\n"
                "Pipeline executed on <b>synthetic</b> data. "
                "No market signal produced.")
        if not quality_ok:
            return self.send_signal_disabled(quality_note)

        if ranked is None or len(ranked) == 0:
            return self.send("TRADING_AI: no stocks passed the filters today.")

        lines = [f"<b>TRADING_AI - Top {top_n}</b>",
                 f"<i>as of {ranked['date'].iloc[0]}</i>", ""]
        for r in ranked.head(top_n).itertuples():
            r21 = (r.ret_21 * 100) if r.ret_21 == r.ret_21 else 0.0
            lines.append(
                f"{r.rank}. <b>{_esc(r.symbol)}</b>  "
                f"score {r.score:+.2f}  |  21d {r21:+.1f}%  |  "
                f"{r.close:,.2f}")
        lines += ["", "<i>Research output, not investment advice. "
                      "Verify before acting.</i>"]
        if quality_note:
            lines.append(f"<i>{_esc(quality_note)}</i>")
        return self.send("\n".join(lines))

    def send_heatmap(self, text: str, synthetic: bool = False) -> bool:
        head = ("<b>Sector Heatmap</b>" if not synthetic
                else "<b>Sector Heatmap (SYNTHETIC DEMO)</b>")
        return self.send(f"{head}\n<pre>{_esc(text)}</pre>")

    def send_source_failure(self, source: str, error: str,
                            fallback: str | None) -> bool:
        return self.send(
            "<b>Data source failure</b>\n"
            f"Source: <code>{_esc(source)}</code>\n"
            f"Time: {dt.datetime.now():%Y-%m-%d %H:%M}\n"
            f"Error: <code>{_esc(error[:300])}</code>\n"
            f"Fallback: <code>{_esc(fallback or 'none available')}</code>",
            silent=True)


def _esc(s: Any) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;"))


def _chunks(s: str, n: int):
    if len(s) <= n:
        yield s
        return
    cur = []
    size = 0
    for line in s.splitlines(keepends=True):
        if size + len(line) > n and cur:
            yield "".join(cur)
            cur, size = [], 0
        cur.append(line)
        size += len(line)
    if cur:
        yield "".join(cur)
