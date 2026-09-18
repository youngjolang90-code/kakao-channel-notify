#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""1회 설정: 카카오 동의 후 받은 인증 코드로 리프레시 토큰을 발급받는다."""
import json
import os
import sys
import urllib.parse

from notify import CLIENT_SECRET, NEW_TOKEN_FILE, REST_KEY, http, send_text

REDIRECT_URI = os.environ.get("KAKAO_REDIRECT_URI") or "https://localhost:3000"

HINTS = {
    "KOE320": "인증 코드가 만료됐거나 이미 사용됐어요. 동의 주소를 다시 열어 새 코드를 받아 10분 안에 넣어 주세요.",
    "KOE006": "Redirect URI가 카카오 앱에 등록된 값과 달라요. https://localhost:3000 으로 등록했는지 확인하세요.",
    "KOE010": "Client Secret이 틀렸거나 빠졌어요. KAKAO_CLIENT_SECRET 시크릿을 확인하세요.",
    "KOE101": "REST API 키가 틀렸어요. KAKAO_REST_API_KEY 시크릿을 확인하세요.",
}

raw = os.environ.get("AUTH_CODE", "").strip()
if "code=" in raw:
    raw = urllib.parse.parse_qs(raw.split("?", 1)[-1]).get("code", [""])[0]
code = raw.strip()
if not (code and REST_KEY):
    sys.exit("[error] 인증 코드 또는 KAKAO_REST_API_KEY 가 비어 있습니다.")

form = {"grant_type": "authorization_code", "client_id": REST_KEY,
        "redirect_uri": REDIRECT_URI, "code": code}
if CLIENT_SECRET:
    form["client_secret"] = CLIENT_SECRET

status, body = http("https://kauth.kakao.com/oauth/token", form)
try:
    j = json.loads(body)
except ValueError:
    j = {}

if "refresh_token" not in j:
    err = j.get("error_code", "")
    print(f"[error] 토큰 발급 실패 ({status}): {body[:300]}")
    if err in HINTS:
        print("→ " + HINTS[err])
    sys.exit(1)

if "talk_message" not in (j.get("scope") or ""):
    print("[warn] '카카오톡 메시지 전송' 동의가 빠져 있어요. 동의항목 설정을 확인하세요.")

with open(NEW_TOKEN_FILE, "w") as f:
    f.write(j["refresh_token"])

ok = send_text(j["access_token"], "🔧 설정 완료!\n이제 채널 알림을 이 '나와의 채팅'으로 보내드릴게요.")
print("[setup] 토큰 발급 성공, 확인 메시지 전송", "성공" if ok else "실패")
