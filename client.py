import json
from datetime import datetime
from typing import Union

import requests

from exceptions import IncorrectCredentials, TooManyWrongAttempts, BookingFailed


class AimHarderClient:
    def __init__(self, email: str, password: str, box_name: str, box_id: int):
        self.box_name = box_name
        self.box_id = box_id
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
            ),
            "X-Requested-With": "XMLHttpRequest",
        })
        self._login(email, password)

    def _base_url(self) -> str:
        return f"https://{self.box_name}.aimharder.com"

    def _date_str(self, date: datetime) -> str:
        return date.strftime("%Y%m%d")

    def _login(self, email: str, password: str):
        login_url = "https://login.aimharder.com/api/login"
        payload = {
            "username": email,
            "password": password,
            "fingerprint": "123456",
        }
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Origin": "https://login.aimharder.com",
            "Referer": "https://login.aimharder.com/",
        }

        resp = self.session.post(login_url, json=payload, headers=headers, allow_redirects=True)

        if not resp.ok:
            try:
                data = resp.json()
                msg = data.get("error", {}).get("message", resp.text[:200])
            except Exception:
                msg = resp.text[:200]
            if "LOGIN_ERROR_LOGIN" in msg:
                raise IncorrectCredentials("Login failed: incorrect credentials")
            raise RuntimeError(f"Login HTTP error {resp.status_code}: {msg}")

        # Visit the box's subdomain so AimHarder registers the session there
        self.session.get(self._base_url(), allow_redirects=True)

    def list_classes(self, date: datetime) -> list[dict]:
        url = f"{self._base_url()}/api/bookings"
        params = {"box": self.box_id, "day": self._date_str(date)}
        headers = {"Accept": "application/json", "Referer": self._base_url()}

        resp = self.session.get(url, params=params, headers=headers)
        if not resp.ok:
            raise RuntimeError(f"list_classes HTTP {resp.status_code}: {resp.text[:300]}")

        try:
            data = resp.json()
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"list_classes: invalid JSON – {exc}") from exc

        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return data.get("bookings", data.get("classes", data.get("sessions", [])))
        return []

    def book_class(self, class_id: Union[int, str], date: datetime, insist: int = 0) -> dict:
        url = f"{self._base_url()}/api/book"
        payload = {
            "id": str(class_id),
            "day": self._date_str(date),
            "insist": insist,
            "familyId": "",
        }
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "Referer": self._base_url(),
        }

        resp = self.session.post(url, data=payload, headers=headers)
        if not resp.ok:
            raise BookingFailed(f"book_class HTTP {resp.status_code}: {resp.text[:300]}")

        try:
            return resp.json()
        except json.JSONDecodeError:
            return {"raw": resp.text}

    def cancel_booking(self, class_id: Union[int, str], date: datetime) -> dict:
        url = f"{self._base_url()}/api/book"
        payload = {
            "id": str(class_id),
            "day": self._date_str(date),
            "insist": 0,
            "familyId": "",
            "delete": 1,
        }
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "Referer": self._base_url(),
        }

        resp = self.session.post(url, data=payload, headers=headers)
        if not resp.ok:
            raise RuntimeError(f"cancel_booking HTTP {resp.status_code}: {resp.text[:300]}")

        try:
            return resp.json()
        except json.JSONDecodeError:
            return {"raw": resp.text}

    def logout(self):
        try:
            self.session.get(
                f"{self._base_url()}/logout",
                headers={"Referer": self._base_url()},
                allow_redirects=True,
                timeout=10,
            )
        except Exception:
            pass
        self.session.cookies.clear()
