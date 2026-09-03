"""One-time interactive Amazon login, via alexapy's local browser proxy.

Run this manually once (`py setup_login.py`). Amazon blocks the plain
email/password API flow as automated (it silently redirects it to a fake
"create account" page instead of actually signing in), so this instead
starts a small local proxy and has you sign in through your normal browser,
exactly as if you'd gone to amazon.<tld> yourself. That's what lets you
solve a captcha or approve 2FA if Amazon asks for one. Once you finish, the
proxy captures the login and this script saves the session to
.alexa_cookies/ so main.py can log in silently afterwards.
"""
from __future__ import annotations

import asyncio
import webbrowser

from alexapy import AlexaLogin, AlexaProxy

from config import load_config

_TIMEOUT_SECONDS = 600


async def main() -> None:
    config = load_config()

    login = AlexaLogin(
        url=config.amazon_url,
        email=config.amazon_email,
        password=config.amazon_password,
        outputpath=lambda filename: str(config.cookie_dir / filename),
        otp_secret=config.amazon_otp_secret,
        oauth_login=True,
    )

    proxy = AlexaProxy(login, "http://127.0.0.1")
    await proxy.start_proxy()
    url = str(proxy.access_url())

    print(f"Opening your browser to sign in: {url}")
    print(f"Email/password are pre-filled; just handle any captcha or 2FA prompt.")
    print(f"Waiting up to {_TIMEOUT_SECONDS // 60} minutes for you to finish...")
    webbrowser.open(url)

    waited = 0
    while login.authorization_code is None and waited < _TIMEOUT_SECONDS:
        await asyncio.sleep(1)
        waited += 1

    await proxy.stop_proxy()

    if login.authorization_code is None:
        print("Timed out waiting for login to complete. Run this again.")
        await login.close()
        return

    if await login.test_loggedin():
        print(f"Logged in as {config.amazon_email}. Session saved to {config.cookie_dir}")
    else:
        print(f"Login did not complete successfully. Status: {login.status}")

    await login.close()


if __name__ == "__main__":
    asyncio.run(main())
