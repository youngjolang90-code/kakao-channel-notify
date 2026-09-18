#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
카카오톡 채널 새 글 알림봇
- 공개 카카오톡 채널의 '소식' 글/영상을 주기적으로 확인하고
- 새 글이 있으면 카카오톡 '나와의 채팅'으로 알려줍니다 (카카오 '나에게 보내기' API).

실행 모드
  python notify.py --mode normal    # 평소 동작 (GitHub Actions 가 15분마다 실행)
  python notify.py --mode observe   # 전송 없이 가져온 글 목록만 출력 (진단용)
  python notify.py --mode test      # 최신 글 1건을 강제로 카톡 전송 (배선 점검용)
"""
import argparse
import datetime
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

# ── 설정 ─────────────────────────────────────────────
CHANNEL_ID = os.environ.get("CHANNEL_ID") or "_xoZxmMxb"
CHANNEL_NAME = os.environ.get("CHANNEL_NAME") or "광진교회 말씀의실재"
CHANNEL_URL = f"https://pf.kakao.com/{CHANNEL_ID}"

REST_KEY = os.environ.get("KAKAO_REST_API_KEY", "").strip()
CLIENT_SECRET = os.environ.get("KAKAO_CLIENT_SECRET", "").strip()
REFRESH_TOKEN = os.environ.get("KAKAO_REFRESH_TOKEN", "").strip()

STATE_FILE = "state/seen.json"
NEW_TOKEN_FILE = "new_refresh_token.txt"
MAX_SEEN = 500            # 기억해 둘 글 개수
MAX_SEND_PER_RUN = 5      # 한 번에 최대 몇 건까지 보낼지
MAX_AGE_DAYS = 3          # 이보다 오래된 글은 '새 글'로 치지 않음 (오발송 방지)
FAIL_ALERT_AT = 12        # 연속 12회(약 3시간) 못 가져오면 카톡으로 경고

KST = datetime.timezone(datetime.timedelta(hours=9))
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

# 채널 글을 읽어올 공개 주소들 (앞에서부터 시도, 결과는 합침)
SOURCES = [
    f"https://pf.kakao.com/rocket-web/web/profiles/{CHANNEL_ID}/posts",
    f"https://pf.kakao.com/rocket-web/web/v2/profiles/{CHANNEL_ID}",
]
DATE_KEYS = ("published_at", "created_at", "publishedAt", "createdAt", "updated_at")
WEEKDAYS = "월화수목금토일"


# ── 공통 HTTP ────────────────────────────────────────
def http(url, form=None, headers=None):
    h = {"User-Agent": UA, "Accept": "application/json, text/plain, */*"}
    if headers:
        h.update(headers)
    data = None
    if form is not None:
        data = urllib.parse.urlencode(form).encode("utf-8")
        h["Content-Type"] = "application/x-www-form-urlencoded;charset=utf-8"
    req = urllib.request.Request(url, data=data, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception as e:  # 네트워크 오류 등
        return 0, f"{type(e).__name__}: {e}"


# ── 채널 글 읽기 ─────────────────────────────────────
def looks_like_post(d):
    if not isinstance(d, dict) or "id" not in d:
        return False
    has_text = any(k in d for k in ("title", "contents", "content", "text"))
    has_date = any(k in d for k in DATE_KEYS)
    return has_text and has_date


def walk(obj, out):
    """JSON 어디에 있든 '글처럼 생긴' 객체를 모두 찾는다 (구조가 바뀌어도 버티도록)."""
    if isinstance(obj, dict):
        if looks_like_post(obj):
            out.append(obj)
            return
        for v in obj.values():
            walk(v, out)
    elif isinstance(obj, list):
        for v in obj:
            walk(v, out)


def flatten_text(v):
    if isinstance(v, str):
        return v
    if isinstance(v, list):
        return "\n".join(t for t in (flatten_text(x) for x in v) if t)
    if isinstance(v, dict):
        for k in ("v", "text", "value", "title", "contents", "content"):
            if k in v:
                return flatten_text(v[k])
    return ""


def clean(s):
    s = re.sub(r"<[^>]+>", " ", s or "")          # 혹시 섞인 HTML 태그 제거
    s = re.sub(r"[ \t\u00a0]+", " ", s)
    return "\n".join(line.strip() for line in s.splitlines() if line.strip())


def to_dt(v):
    try:
        if isinstance(v, (int, float)) or (isinstance(v, str) and v.isdigit()):
            n = float(v)
            if n > 1e12:
                n /= 1000
            return datetime.datetime.fromtimestamp(n, KST)
        if isinstance(v, str):
            d = datetime.datetime.fromisoformat(v.replace("Z", "+00:00"))
            if d.tzinfo is None:
                d = d.replace(tzinfo=KST)
            return d.astimezone(KST)
    except Exception:
        pass
    return None


def fmt(d):
    if not d:
        return ""
    ampm = "오전" if d.hour < 12 else "오후"
    h = d.hour % 12 or 12
    return f"{d.month}월 {d.day}일 ({WEEKDAYS[d.weekday()]}) {ampm} {h}:{d.minute:02d}"


def find_image(dump):
    m = re.search(r'https?://[^"\s\\]*kakaocdn\.net/[^"\s\\]+', dump)
    return m.group(0).replace("http://", "https://", 1) if m else None


def normalize(raw):
    pid = str(raw.get("id"))
    title = clean(flatten_text(raw.get("title")))
    body = clean(flatten_text(raw.get("contents") or raw.get("content") or raw.get("text")))
    if not title:
        title = body.splitlines()[0] if body else "(제목 없음)"
    when = None
    for k in DATE_KEYS:
        if raw.get(k) is not None:
            when = to_dt(raw[k])
            if when:
                break
    dump = json.dumps(raw, ensure_ascii=False)
    link = raw.get("permalink")
    url = link if isinstance(link, str) and link.startswith("http") else f"{CHANNEL_URL}/{pid}"
    return {
        "id": pid,
        "title": title,
        "when": when,
        "video": bool(re.search(r'"(type|media_type)"\s*:\s*"[^"]*video|youtube|youtu\.be|kakaotv', dump, re.I)),
        "image": find_image(dump),
        "url": url,
    }


def fetch_posts(verbose=False):
    found, debug = {}, []
    for url in SOURCES:
        code, body = http(url, headers={"Referer": CHANNEL_URL})
        if verbose:
            print(f"[fetch] {code} {url} ({len(body)} bytes)")
        debug.append((url, code, body[:1500]))
        if code != 200:
            continue
        try:
            data = json.loads(body)
        except ValueError:
            if verbose:
                print("  → JSON 형식이 아님")
            continue
        raws = []
        walk(data, raws)
        for r in raws:
            p = normalize(r)
            found.setdefault(p["id"], p)
        if verbose:
            print(f"  → 글 {len(raws)}개 인식")
    oldest = datetime.datetime.min.replace(tzinfo=KST)
    posts = sorted(found.values(), key=lambda p: p["when"] or oldest, reverse=True)
    return posts, debug


# ── 상태 저장 ────────────────────────────────────────
def load_state():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            s = json.load(f)
    except (OSError, ValueError):
        s = {}
    s.setdefault("seen", [])
    s.setdefault("initialized", False)
    s.setdefault("fail_count", 0)
    return s


def save_state(s):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    s["seen"] = s["seen"][-MAX_SEEN:]
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False, indent=2)
        f.write("\n")


def today_kst():
    return datetime.datetime.now(KST).strftime("%Y-%m-%d")


# ── 카카오 '나에게 보내기' ───────────────────────────
def get_access_token(state):
    if not (REST_KEY and REFRESH_TOKEN):
        sys.exit("[error] KAKAO_REST_API_KEY / KAKAO_REFRESH_TOKEN 시크릿이 비어 있습니다. "
                 "'1회 설정' 워크플로를 먼저 실행하세요.")
    form = {"grant_type": "refresh_token", "client_id": REST_KEY, "refresh_token": REFRESH_TOKEN}
    if CLIENT_SECRET:
        form["client_secret"] = CLIENT_SECRET
    code, body = http("https://kauth.kakao.com/oauth/token", form)
    try:
        j = json.loads(body)
    except ValueError:
        j = {}
    if code != 200 or "access_token" not in j:
        sys.exit(f"[error] 카카오 토큰 갱신 실패 ({code}): {body[:300]}\n"
                 "→ 리프레시 토큰이 만료됐다면 README의 'C. 최초 인증'을 다시 해 주세요.")
    if j.get("refresh_token"):  # 만료 1개월 전부터 새 토큰이 나옴 → 시크릿 자동 갱신
        with open(NEW_TOKEN_FILE, "w") as f:
            f.write(j["refresh_token"])
        print("[token] 새 리프레시 토큰 발급 → 시크릿 자동 갱신 예정")
    state["last_token_refresh"] = today_kst()
    return j["access_token"]


def send_memo(token, template):
    code, body = http(
        "https://kapi.kakao.com/v2/api/talk/memo/default/send",
        {"template_object": json.dumps(template, ensure_ascii=False)},
        {"Authorization": f"Bearer {token}"},
    )
    ok = code == 200 and '"result_code":0' in body.replace(" ", "")
    if not ok:
        print(f"[send-fail] {code} {body[:300]}")
    return ok


def link(url):
    return {"web_url": url, "mobile_web_url": url}


def send_text(token, text, url=CHANNEL_URL, button="채널 열기"):
    return send_memo(token, {"object_type": "text", "text": text[:200],
                             "link": link(url), "button_title": button})


def post_message(token, p, prefix=""):
    label = "🎬 새 영상" if p["video"] else "📖 새 글"
    when = fmt(p["when"])
    if p["image"]:  # 사진이 있으면 카드 형태로
        feed = {
            "object_type": "feed",
            "content": {
                "title": f"{prefix}{p['title'][:60]}",
                "description": f"{label} · {CHANNEL_NAME}" + (f"\n{when}" if when else ""),
                "image_url": p["image"],
                "image_width": 800,
                "image_height": 400,
                "link": link(p["url"]),
            },
            "buttons": [{"title": "바로 보기", "link": link(p["url"])}],
        }
        if send_memo(token, feed):
            return True
    text = f"{prefix}{label} · {CHANNEL_NAME}\n\n{p['title'][:120]}" + (f"\n\n{when}" if when else "")
    return send_text(token, text, p["url"], "바로 보기")


# ── 메인 ─────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="normal", choices=["normal", "observe", "test"])
    mode = ap.parse_args().mode

    state = load_state()
    posts, debug = fetch_posts(verbose=True)

    if mode == "observe":
        print(f"\n=== 인식한 글 {len(posts)}개 (최신순) ===")
        for p in posts[:15]:
            kind = "영상" if p["video"] else "글"
            print(f"- [{p['id']}] {fmt(p['when']) or '날짜?'} | {kind} | {p['title'][:50]} | {p['url']}")
        if not posts:
            print("\n글을 하나도 인식하지 못했습니다. 아래 응답 내용을 Claude에게 보여주세요:")
            for url, code, head in debug:
                print(f"\n--- {code} {url}\n{head}")
        return

    if not posts:
        state["fail_count"] += 1
        print(f"[warn] 글 목록을 가져오지 못했습니다 (연속 {state['fail_count']}회)")
        if state["fail_count"] == FAIL_ALERT_AT:
            send_text(get_access_token(state),
                      f"⚠️ 채널 알림봇 확인 필요\n{CHANNEL_NAME} 채널 글을 3시간째 못 가져오고 있어요. "
                      "GitHub Actions 기록을 확인해 주세요.")
        save_state(state)
        return
    state["fail_count"] = 0

    if mode == "test":
        ok = post_message(get_access_token(state), posts[0], prefix="[테스트] ")
        print("[test] 전송", "성공" if ok else "실패")
        save_state(state)
        sys.exit(0 if ok else 1)

    # 첫 실행: 지금 있는 글은 '이미 본 글'로 기록만 하고 연결 완료 메시지 1건
    if not state["initialized"]:
        state["seen"] = [p["id"] for p in posts]
        state["initialized"] = True
        send_text(get_access_token(state),
                  f"✅ 알림 연결 완료!\n{CHANNEL_NAME} 채널에 새 글·영상이 올라오면 여기로 알려드릴게요."
                  f"\n\n현재 최신 글: {posts[0]['title'][:60]}")
        save_state(state)
        print("[init] 초기화 완료")
        return

    seen = set(state["seen"])
    cutoff = datetime.datetime.now(KST) - datetime.timedelta(days=MAX_AGE_DAYS)
    new = []
    for p in posts:
        if p["id"] in seen:
            continue
        if p["when"] and p["when"] < cutoff:   # 오래된 글이 뒤늦게 보이는 경우 → 조용히 기록만
            state["seen"].append(p["id"])
            continue
        new.append(p)
    new.reverse()  # 오래된 것부터 차례로

    token = None
    if new:
        token = get_access_token(state)
        for p in new[:-MAX_SEND_PER_RUN]:      # 너무 많으면 최신 5건만 보내고 나머지는 기록만
            state["seen"].append(p["id"])
        for p in new[-MAX_SEND_PER_RUN:]:
            if post_message(token, p):
                state["seen"].append(p["id"])
                print(f"[send] {p['title'][:50]}")
            else:
                print(f"[retry-later] {p['title'][:50]}")
    else:
        print("[ok] 새 글 없음")

    # 하루 1번은 토큰을 갱신해 두기 (리프레시 토큰이 만료되지 않도록)
    if token is None and state.get("last_token_refresh") != today_kst():
        get_access_token(state)

    save_state(state)


if __name__ == "__main__":
    main()
