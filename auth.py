"""접속 비밀번호 확인 + 같은 브라우저는 1년간 기억 (쿠키).

비밀번호는 코드에 두지 않고 st.secrets["APP_PASSWORD"]에서 읽는다.
- 로컬: .streamlit/secrets.toml
- Streamlit Cloud: 앱 Settings → Secrets
쿠키에는 비밀번호가 아니라 비밀번호로 만든 서명값만 저장하므로,
비밀번호를 바꾸면 기존에 기억된 브라우저도 모두 다시 입력해야 한다.
"""
import hashlib
import hmac

import streamlit as st
import streamlit.components.v1 as components

COOKIE_NAME = "snuhfm_auth"
REMEMBER_SECONDS = 365 * 24 * 60 * 60  # 1년


def _get_password():
    try:
        return st.secrets.get("APP_PASSWORD")
    except Exception:  # secrets 파일 자체가 없는 경우
        return None


def _make_token(password):
    return hmac.new(password.encode("utf-8"), b"snuhfm-auth-v1", hashlib.sha256).hexdigest()


def _write_cookie(token):
    # Streamlit은 서버에서 쿠키를 쓸 수 없어 브라우저 JS로 저장한다.
    components.html(
        f"""<script>
        var doc = document, secure = "";
        try {{ doc = window.parent.document; if (window.parent.location.protocol === "https:") secure = "; Secure"; }} catch (e) {{}}
        doc.cookie = "{COOKIE_NAME}={token}; max-age={REMEMBER_SECONDS}; path=/; SameSite=Lax" + secure;
        </script>""",
        height=0,
    )


def require_password():
    """비밀번호가 확인되지 않았으면 로그인 화면을 보여주고 앱 실행을 멈춘다."""
    password = _get_password()
    if not password:
        st.error("접속 비밀번호(APP_PASSWORD)가 설정되지 않았습니다. secrets에 APP_PASSWORD를 추가하세요.")
        st.stop()

    token = _make_token(password)

    # 이전에 비밀번호를 입력한 브라우저: 쿠키로 바로 통과
    if hmac.compare_digest(st.context.cookies.get(COOKIE_NAME, ""), token):
        return

    if st.session_state.get("auth_ok"):
        if not st.session_state.get("auth_cookie_written"):
            _write_cookie(token)
            st.session_state.auth_cookie_written = True
        return

    st.title("🔒 의국 스케줄 마스터")
    with st.form("login_form"):
        entered = st.text_input("비밀번호", type="password")
        submitted = st.form_submit_button("접속")
    if submitted:
        if hmac.compare_digest(entered.encode("utf-8"), password.encode("utf-8")):
            st.session_state.auth_ok = True
            st.rerun()
        st.error("비밀번호가 틀렸습니다.")
    st.caption("한 번 입력하면 이 브라우저에서는 1년간 다시 묻지 않습니다.")
    st.stop()
