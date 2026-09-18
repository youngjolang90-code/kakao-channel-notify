# 카카오톡 채널 새 글 알림봇

광진교회 말씀의실재 채널(pf.kakao.com/_xoZxmMxb)에 새 글·영상이 올라오면
**내 카카오톡 '나와의 채팅'** 으로 알려주는 봇입니다.
GitHub가 15분마다 대신 확인해 주므로 컴퓨터를 꺼 두어도 동작합니다. 비용은 들지 않습니다.

준비물: 카카오 계정, GitHub 계정(무료). 전체 설정은 30분 정도 걸립니다.

---

## A. 카카오 개발자 앱 만들기

사이트: https://developers.kakao.com (메뉴 이름은 시기에 따라 조금 다를 수 있어요)

1. 카카오 계정으로 로그인 → **내 애플리케이션 → 애플리케이션 추가하기**
   - 앱 이름: `채널알림봇` (아무거나), 회사명: 본인 이름
2. 만든 앱 → **앱 키**에서 **REST API 키**를 복사해 메모장에 적어 두기
3. **카카오 로그인** 메뉴 → **활성화 설정 ON**
   - **Redirect URI** 에 `https://localhost:3000` 등록
4. **카카오 로그인 → 동의항목** → **카카오톡 메시지 전송(talk_message)** 을 **선택 동의**로 설정
5. **플랫폼 → Web** → 사이트 도메인에 `https://pf.kakao.com` 등록
   (알림의 '바로 보기' 버튼이 채널로 열리게 하는 설정)
6. **보안(Client Secret)** 메뉴에서 상태가 '사용함'이면 코드 값을 복사해 두기 (사용 안 함이면 건너뜀)

## B. GitHub에 올리기

1. https://github.com 로그인 → 오른쪽 위 **+ → New repository**
   - 이름: `kakao-channel-notify`, **Public** 선택 → Create
   - (Public이어야 자동 실행이 무료·무제한입니다. 비밀 값은 아래 Secrets에 따로 보관되니 노출되지 않아요.)
2. 만든 저장소 화면의 **uploading an existing file** 링크 클릭 →
   압축을 푼 폴더 **안의 내용 전체**(`.github` 폴더 포함)를 끌어다 놓기 → **Commit changes**
   - 맥에서 `.github` 폴더가 안 보이면 Finder에서 `Cmd + Shift + .` 을 누르세요.
   - 올린 뒤 저장소에 `.github/workflows/notify.yml` 이 보이면 성공입니다.
3. **토큰(PAT) 발급** — 봇이 카카오 토큰을 스스로 갱신하는 데 필요해요
   - GitHub 오른쪽 위 프로필 → **Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate new token**
   - Expiration: 가능한 가장 길게
   - Repository access: **Only select repositories** → `kakao-channel-notify`
   - Permissions → Repository permissions → **Secrets: Read and write** (다른 권한은 추가하지 않기)
   - 생성된 토큰(`github_pat_...`)을 복사
4. **비밀 값 등록** — 저장소 → **Settings → Secrets and variables → Actions → New repository secret**

   | Name | Value |
   |---|---|
   | `KAKAO_REST_API_KEY` | A-2의 REST API 키 |
   | `GH_PAT` | B-3의 토큰 |
   | `KAKAO_CLIENT_SECRET` | A-6의 값 (사용 안 함이면 등록하지 않음) |

## C. 최초 인증 (1번만)

1. 아래 주소에서 `REST키` 부분만 내 REST API 키로 바꿔서 브라우저 주소창에 넣기

   ```
   https://kauth.kakao.com/oauth/authorize?client_id=REST키&redirect_uri=https://localhost:3000&response_type=code&scope=talk_message
   ```
2. 카카오 동의 화면에서 **동의하고 계속하기**
3. "사이트에 연결할 수 없음" 화면이 뜨는 게 **정상**입니다. 이때 **주소창의 주소 전체를 복사** (`https://localhost:3000/?code=...`)
4. GitHub 저장소 → **Actions** 탭 → 왼쪽 **1회 설정: 카카오 토큰 발급** → **Run workflow** →
   복사한 주소를 붙여넣고 실행 (**10분 안에** 해야 해요)
5. 카카오톡 **나와의 채팅**에 "🔧 설정 완료!" 메시지가 오면 성공

## D. 동작 확인

Actions 탭 → **채널 새 글 알림** → **Run workflow** 에서 mode를 골라 실행:

1. `observe` — 전송 없이 채널 글 목록만 가져와 봅니다. 실행 기록을 눌러 로그에 글 제목들이 보이면 OK
2. `test` — 최신 글 1건을 `[테스트]` 표시와 함께 카톡으로 보냅니다
3. `normal` — 한 번 실행하면 "✅ 알림 연결 완료!" 메시지가 오고, 이후 15분마다 자동 확인합니다

---

## 문제가 생기면

- **observe에서 글이 0개로 나올 때**: 카카오 쪽 데이터 형식 문제일 수 있어요. 로그 아래쪽 응답 내용을 복사해서 Claude에게 보여주세요.
- **"토큰 갱신 실패" 오류**: C단계를 다시 하면 됩니다. (봇이 매일 토큰을 자동 연장하므로 보통은 생기지 않아요)
- **3시간 넘게 채널을 못 읽으면** 봇이 카톡으로 "⚠️ 확인 필요" 메시지를 보냅니다.
- 실행이 실패하면 GitHub가 가입 이메일로 알려줍니다.
- GitHub 무료 자동 실행은 가끔 몇십 분 늦어질 수 있어요.

## 다른 채널도 받고 싶다면

`notify.py` 위쪽의 `CHANNEL_ID`, `CHANNEL_NAME` 을 바꾸면 됩니다.
여러 채널을 동시에 보려면 Claude에게 요청하세요.
