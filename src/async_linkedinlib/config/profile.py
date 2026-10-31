"""Versioned Android client metadata observed in the local login capture."""

import json
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ClientProfile:
    """App metadata, separate from per-account cookies and device identity."""

    app_version: str = "4.1.1267"
    version_code: int = 217500
    locale: str = "en_US"
    timezone: str = "Asia/Kolkata"
    timezone_offset: float = 5.5

    @property
    def user_agent(self) -> str:
        return (
            f"com.linkedin.android/{self.version_code} (Linux; U; Android 13; {self.locale}; "
            "sdk_gphone64_arm64; Build/TE1A.240213.009; Cronet/151.0.7922.47)"
        )

    def auth_headers(self, device_id: str) -> dict[str, str]:
        track = {
            "osName": "Android OS",
            "osVersion": "33",
            "clientVersion": self.app_version,
            "clientMinorVersion": self.version_code,
            "model": "Google_sdk_gphone64_arm64",
            "displayDensity": 2.625,
            "displayWidth": 1080,
            "displayHeight": 2209,
            "dpi": "xhdpi",
            "deviceType": "android",
            "appId": "com.linkedin.android",
            "deviceId": device_id,
            "timezoneOffset": self.timezone_offset,
            "timezone": self.timezone,
            "storeId": "us_googleplay",
            "isAdTrackingLimited": False,
            "mpName": "voyager-android",
            "mpVersion": "2.344.49",
        }
        return {
            "user-agent": "ANDROID OS",
            "x-udid": device_id,
            "x-restli-protocol-version": "2.0.0",
            "accept-language": self.locale.replace("_", "-"),
            "x-li-lang": self.locale,
            "x-li-track": json.dumps(track, separators=(",", ":")),
            "x-li-user-agent": (
                f"LIAuthLibrary:0.0.3 com.linkedin.android:{self.app_version} "
                "Google_sdk_gphone64_arm64:android_13"
            ),
        }
