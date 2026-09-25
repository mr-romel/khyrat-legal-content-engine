from __future__ import annotations

import time
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests

LINKEDIN_VERSION = "202607"
REST_PROTOCOL = "2.0.0"
LINKEDIN_REST_BASE = "https://api.linkedin.com/rest"
LINKEDIN_USERINFO_URL = "https://api.linkedin.com/v2/userinfo"
TRANSIENT_STATUS_CODES = {408, 429, 500, 502, 503, 504}
INTERACTION_RETRIES = 3
INTERACTION_INITIAL_BACKOFF = 3.0
MIN_LINKEDIN_POST_CHARS = 1400
MAX_LINKEDIN_POST_CHARS = 2900


class LinkedInPublishError(RuntimeError):
    """Raised when a required LinkedIn operation fails."""


class LinkedInActionResult:
    def __init__(self, *, status: str, item_id: str = "", error: str = "", http_status: int | None = None) -> None:
        self.status = status
        self.item_id = item_id
        self.error = error
        self.http_status = http_status

    def as_dict(self) -> dict[str, Any]:
        return {"status": self.status, "id": self.item_id, "error": self.error, "http_status": self.http_status}


def _headers(token: str, *, json_content: bool = False) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {token}",
        "Linkedin-Version": LINKEDIN_VERSION,
        "X-Restli-Protocol-Version": REST_PROTOCOL,
    }
    if json_content:
        headers["Content-Type"] = "application/json"
    return headers


def _payload(response: requests.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return response.text


def _error_summary(response: requests.Response) -> str:
    payload = _payload(response)
    if isinstance(payload, dict):
        message = payload.get("message") or payload.get("error") or payload.get("serviceErrorCode")
        if message:
            return str(message)
    text = str(payload).strip()
    return text[:1200] if text else "No response body."


def _raise_required_error(action: str, response: requests.Response) -> None:
    raise LinkedInPublishError(f"{action} failed (HTTP {response.status_code}): {_error_summary(response)}")


def _interaction_result(action: str, response: requests.Response) -> LinkedInActionResult:
    status = response.status_code
    summary = _error_summary(response)
    if status == 401:
        label = "UNAUTHORIZED_TOKEN"
    elif status == 403:
        label = "DISABLED_PERMISSION"
    elif status == 404:
        label = "NOT_FOUND"
    elif status == 400:
        label = "BAD_REQUEST"
    elif status in TRANSIENT_STATUS_CODES:
        label = "TRANSIENT_FAILURE"
    else:
        label = "FAILED"
    return LinkedInActionResult(status=label, error=f"{action}: HTTP {status}: {summary}", http_status=status)


def _post_interaction_with_retry(*, endpoint: str, token: str, body: dict[str, Any], action: str) -> requests.Response | LinkedInActionResult:
    for attempt in range(1, INTERACTION_RETRIES + 1):
        try:
            response = requests.post(endpoint, headers=_headers(token, json_content=True), json=body, timeout=60)
        except requests.RequestException as exc:
            if attempt >= INTERACTION_RETRIES:
                return LinkedInActionResult(status="NETWORK_FAILED", error=f"{action}: {exc}")
            delay = INTERACTION_INITIAL_BACKOFF * (2 ** (attempt - 1))
            print(f"LinkedIn {action} network error; retry {attempt}/{INTERACTION_RETRIES - 1} in {delay:.0f}s...")
            time.sleep(delay)
            continue
        if response.ok:
            return response
        if response.status_code in TRANSIENT_STATUS_CODES and attempt < INTERACTION_RETRIES:
            delay = INTERACTION_INITIAL_BACKOFF * (2 ** (attempt - 1))
            print(f"LinkedIn {action} temporary error (HTTP {response.status_code}); retry {attempt}/{INTERACTION_RETRIES - 1} in {delay:.0f}s...")
            time.sleep(delay)
            continue
        return _interaction_result(action, response)
    return LinkedInActionResult(status="FAILED", error=f"{action}: retry loop exhausted")


def resolve_member_urn(token: str) -> str:
    token = (token or "").strip()
    if not token:
        raise LinkedInPublishError("LINKEDIN_ACCESS_TOKEN is empty.")
    try:
        response = requests.get(LINKEDIN_USERINFO_URL, headers={"Authorization": f"Bearer {token}"}, timeout=30)
    except requests.RequestException as exc:
        raise LinkedInPublishError(f"LinkedIn userinfo request failed: {exc}") from exc
    if not response.ok:
        _raise_required_error("LinkedIn userinfo", response)
    try:
        payload = response.json()
    except ValueError as exc:
        raise LinkedInPublishError("LinkedIn userinfo returned invalid JSON.") from exc
    sub = str(payload.get("sub", "")).strip()
    if not sub:
        raise LinkedInPublishError("LinkedIn userinfo did not return 'sub'. The LinkedIn token must include openid and profile.")
    return f"urn:li:person:{sub}"


def initialize_image_upload(*, token: str, owner_urn: str) -> tuple[str, str]:
    endpoint = f"{LINKEDIN_REST_BASE}/images?action=initializeUpload"
    body = {"initializeUploadRequest": {"owner": owner_urn}}
    try:
        response = requests.post(endpoint, headers=_headers(token, json_content=True), json=body, timeout=60)
    except requests.RequestException as exc:
        raise LinkedInPublishError(f"LinkedIn image initialization network error: {exc}") from exc
    if not response.ok:
        _raise_required_error("LinkedIn image initialization", response)
    try:
        payload = response.json()
    except ValueError as exc:
        raise LinkedInPublishError("LinkedIn image initialization returned invalid JSON.") from exc
    value = payload.get("value", {})
    upload_url = str(value.get("uploadUrl", "")).strip()
    image_urn = str(value.get("image", "")).strip()
    if not upload_url:
        raise LinkedInPublishError("LinkedIn image initialization returned no uploadUrl.")
    if not image_urn:
        raise LinkedInPublishError("LinkedIn image initialization returned no image URN.")
    return upload_url, image_urn


def upload_image(*, token: str, upload_url: str, image_path: str | Path) -> None:
    image = Path(image_path)
    if not image.is_file():
        raise LinkedInPublishError(f"LinkedIn image file not found: {image}")
    try:
        response = requests.put(upload_url, headers={"Authorization": f"Bearer {token}", "Content-Type": "image/jpeg"}, data=image.read_bytes(), timeout=180)
    except requests.RequestException as exc:
        raise LinkedInPublishError(f"LinkedIn image upload network error: {exc}") from exc
    if not response.ok:
        _raise_required_error("LinkedIn image upload", response)


def _strengthen_commentary(commentary: str) -> str:
    text = str(commentary or "").strip()
    if len(text) >= MIN_LINKEDIN_POST_CHARS:
        if len(text) > MAX_LINKEDIN_POST_CHARS:
            text = text[:MAX_LINKEDIN_POST_CHARS].rsplit(" ", 1)[0].rstrip()
        return text.rstrip()
    sections = [
        "المهم هنا إن القاعدة القانونية ما تتفهمش بمعزل عن الوقائع. نفس العبارة أو الموقف ممكن يختلف أثره القانوني بحسب صفة الشخص، مصلحته في الموضوع، المستندات الموجودة، والإجراء الذي تم اتخاذه. لذلك قبل أي قرار، لازم نفصل بين الانطباع الشخصي وبين المركز القانوني الفعلي.",
        "عمليًا، قبل اتخاذ القرار اسأل أولًا: مين صاحب الصفة في الموضوع؟ وهل له مصلحة قانونية حقيقية ومباشرة؟ وإيه المستند أو الواقعة اللي تثبت الكلام ده؟ الأسئلة دي بتمنع أخطاء شائعة، خصوصًا لما يكون القرار مبنيًا على افتراض إن مجرد وجود علاقة أو مصلحة شخصية كفاية لإثبات الحق أو السماح باتخاذ إجراء معين.",
        "ومن ناحية إدارة المخاطر، الأفضل إن القرار ما يعتمدش على معلومة منفردة. راجع الوقائع، حدد الأطراف، اجمع المستندات المؤيدة، وحدد الإجراء القانوني المناسب قبل التنفيذ. ولو فيه أكثر من تفسير محتمل، اختار المسار الذي يحافظ على الحقوق ويقلل احتمالات النزاع بدل ما تكتشف المشكلة بعد فوات الوقت.",
        "الخلاصة إن الوعي القانوني الحقيقي مش مجرد معرفة إجابة مختصرة بنعم أو لا. الأهم إنك تعرف الأسئلة الصحيحة قبل القرار، وتفرق بين وجود مصلحة وبين توافر الصفة، وبين الاعتقاد بوجود حق وبين القدرة على استعماله بالطريق القانوني الصحيح. المراجعة المبكرة غالبًا أوفر وأأمن من محاولة إصلاح قرار خاطئ بعد تنفيذه.",
    ]
    for section in sections:
        if len(text) >= MIN_LINKEDIN_POST_CHARS:
            break
        text = f"{text}\n\n{section}" if text else section
    if len(text) < MIN_LINKEDIN_POST_CHARS:
        text = (text + "\n\n" + "للاطلاع على التفاصيل القانونية، راجع الوقائع والمستندات والإجراءات ذات الصلة قبل اتخاذ أي خطوة.").strip()
    if len(text) > MAX_LINKEDIN_POST_CHARS:
        text = text[:MAX_LINKEDIN_POST_CHARS].rsplit(" ", 1)[0].rstrip()
    return text.rstrip()


def create_post(*, token: str, author_urn: str, commentary: str, image_urn: str) -> str:
    endpoint = f"{LINKEDIN_REST_BASE}/posts"
    commentary = _strengthen_commentary(commentary)
    body = {
        "author": author_urn,
        "commentary": commentary,
        "visibility": "PUBLIC",
        "distribution": {"feedDistribution": "MAIN_FEED", "targetEntities": [], "thirdPartyDistributionChannels": []},
        "content": {"media": {"id": image_urn, "altText": "Legal educational image"}},
        "lifecycleState": "PUBLISHED",
        "isReshareDisabledByAuthor": False,
    }
    try:
        response = requests.post(endpoint, headers=_headers(token, json_content=True), json=body, timeout=60)
    except requests.RequestException as exc:
        raise LinkedInPublishError(f"LinkedIn post network error: {exc}") from exc
    if not response.ok:
        _raise_required_error("LinkedIn post creation", response)
    post_urn = (response.headers.get("x-restli-id", "") or response.headers.get("X-RestLi-Id", "")).strip()
    if not post_urn:
        raise LinkedInPublishError("LinkedIn created the post but returned no post URN.")
    print(f"LinkedIn post length enforced: {len(commentary)} characters")
    return post_urn



def publish_text_to_linkedin(*, token: str, author_urn: str, commentary: str) -> dict[str, Any]:
    """Publish a text-only LinkedIn post when image generation is unavailable."""
    token = (token or "").strip()
    author_urn = (author_urn or "").strip()
    if not token or not author_urn:
        raise LinkedInPublishError("LinkedIn text publication credentials are incomplete.")
    commentary = _strengthen_commentary(commentary)
    endpoint = f"{LINKEDIN_REST_BASE}/posts"
    body = {
        "author": author_urn,
        "commentary": commentary,
        "visibility": "PUBLIC",
        "distribution": {"feedDistribution": "MAIN_FEED", "targetEntities": [], "thirdPartyDistributionChannels": []},
        "lifecycleState": "PUBLISHED",
        "isReshareDisabledByAuthor": False,
    }
    try:
        response = requests.post(endpoint, headers=_headers(token, json_content=True), json=body, timeout=60)
    except requests.RequestException as exc:
        raise LinkedInPublishError(f"LinkedIn text post network error: {exc}") from exc
    if not response.ok:
        _raise_required_error("LinkedIn text post creation", response)
    post_urn = (response.headers.get("x-restli-id", "") or response.headers.get("X-RestLi-Id", "")).strip()
    if not post_urn:
        raise LinkedInPublishError("LinkedIn text post created but returned no post URN.")
    print(f"LinkedIn text publication completed: post_urn={post_urn}")
    return {"post_urn": post_urn, "comment": {"status": "SKIPPED"}, "like": {"status": "SKIPPED"}}

def add_comment(*, token: str, actor_urn: str, post_urn: str, message: str) -> LinkedInActionResult:
    """
    Publish a comment as the authenticated personal member.

    This project uses a personal LinkedIn account with the member write scope
    that is already available to the app. Do not make the newer
    *_member_social_feed permission a prerequisite.

    The legacy member socialActions write route is deliberately attempted
    first because that is the path this token/app has successfully used.
    The versioned /rest route remains only as a compatibility fallback for
    tokens that can use it.
    """
    body = {"actor": actor_urn, "object": post_urn, "message": {"text": message}}

    # Personal member path: keep the known-working w_member_social route first.
    legacy_endpoint = f"https://api.linkedin.com/v2/socialActions/{quote(post_urn, safe='')}/comments"
    legacy_result = _post_legacy_interaction(
        legacy_endpoint,
        token=token,
        body=body,
        action="comment_v2",
    )
    if _is_http_response(legacy_result):
        comment_id = (
            legacy_result.headers.get("x-restli-id", "")
            or legacy_result.headers.get("X-RestLi-Id", "")
        ).strip()
        if comment_id:
            return LinkedInActionResult(
                status="PUBLISHED",
                item_id=f"urn:li:comment:({post_urn},{comment_id})",
                http_status=legacy_result.status_code,
            )
        return LinkedInActionResult(
            status="FAILED",
            error="comment_v2: LinkedIn returned no comment ID",
            http_status=legacy_result.status_code,
        )

    # Compatibility fallback. This is not required for the personal
    # w_member_social path; it is only useful when the token also has access
    # to the newer versioned socialActions API.
    if legacy_result.http_status not in {400, 401, 403, 404}:
        return legacy_result

    endpoint = f"{LINKEDIN_REST_BASE}/socialActions/{quote(post_urn, safe='')}/comments"
    result = _post_interaction_with_retry(
        endpoint=endpoint,
        token=token,
        body=body,
        action="comment",
    )
    if isinstance(result, LinkedInActionResult):
        print(
            f"LinkedIn comment: {result.status} | http={result.http_status} | "
            f"error={result.error}"
        )
        return result

    comment_id = (
        result.headers.get("x-restli-id", "")
        or result.headers.get("X-RestLi-Id", "")
    ).strip()
    if not comment_id:
        return LinkedInActionResult(
            status="FAILED",
            error="comment: LinkedIn returned no comment ID",
            http_status=result.status_code,
        )
    return LinkedInActionResult(
        status="PUBLISHED",
        item_id=f"urn:li:comment:({post_urn},{comment_id})",
        http_status=result.status_code,
    )


def _is_http_response(value: Any) -> bool:
    """Accept real requests responses and lightweight response doubles in tests."""
    return isinstance(value, requests.Response) or (
        hasattr(value, "status_code") and hasattr(value, "headers") and hasattr(value, "ok")
    )


def _post_legacy_interaction(endpoint: str, *, token: str, body: dict[str, Any], action: str):
    try:
        response = requests.post(
            endpoint,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json", "X-Restli-Protocol-Version": "2.0.0"},
            json=body,
            timeout=60,
        )
    except requests.RequestException as exc:
        return LinkedInActionResult(status="NETWORK_FAILED", error=f"{action}: {exc}")
    if response.ok:
        return response
    return _interaction_result(action, response)


def like_post(*, token: str, actor_urn: str, post_urn: str) -> LinkedInActionResult:
    return _create_reaction(token=token, actor_urn=actor_urn, root_urn=post_urn, action="like")


def like_comment(*, token: str, actor_urn: str, comment_urn: str) -> LinkedInActionResult:
    return _create_reaction(token=token, actor_urn=actor_urn, root_urn=comment_urn, action="like_comment")


def _create_reaction(*, token: str, actor_urn: str, root_urn: str, action: str) -> LinkedInActionResult:
    # Keep reactions on the same personal-member path as comments. This avoids
    # requiring *_member_social_feed merely to add a like from the member token.
    legacy_endpoint = f"https://api.linkedin.com/v2/socialActions/{quote(root_urn, safe='')}/likes"
    legacy_body = {"actor": actor_urn, "object": root_urn}
    legacy_result = _post_legacy_interaction(
        legacy_endpoint,
        token=token,
        body=legacy_body,
        action=f"{action}_v2",
    )
    if _is_http_response(legacy_result):
        reaction_id = ""
        try:
            payload = legacy_result.json()
            if isinstance(payload, dict):
                reaction_id = str(payload.get("id", "")).strip()
        except ValueError:
            pass
        return LinkedInActionResult(
            status="LIKED",
            item_id=reaction_id,
            http_status=legacy_result.status_code,
        )

    if legacy_result.http_status not in {400, 401, 403, 404}:
        return legacy_result

    encoded_actor = quote(actor_urn, safe="")
    endpoint = f"{LINKEDIN_REST_BASE}/reactions?actor={encoded_actor}"
    body = {"root": root_urn, "reactionType": "LIKE"}
    result = _post_interaction_with_retry(
        endpoint=endpoint,
        token=token,
        body=body,
        action=action,
    )
    if isinstance(result, LinkedInActionResult):
        print(
            f"LinkedIn {action}: {result.status} | http={result.http_status} | "
            f"error={result.error}"
        )
        return result

    reaction_id = ""
    try:
        payload = result.json()
        if isinstance(payload, dict):
            reaction_id = str(payload.get("id", "")).strip()
    except ValueError:
        pass
    return LinkedInActionResult(
        status="LIKED",
        item_id=reaction_id,
        http_status=result.status_code,
    )


def publish_to_linkedin(*, token: str, author_urn: str, image_path: str | Path, commentary: str, first_comment: str) -> dict[str, Any]:
    token = (token or "").strip()
    author_urn = (author_urn or "").strip()
    if not token:
        raise LinkedInPublishError("LINKEDIN_ACCESS_TOKEN is empty.")
    if not author_urn:
        raise LinkedInPublishError("LinkedIn author URN is empty.")

    upload_url, image_urn = initialize_image_upload(token=token, owner_urn=author_urn)
    upload_image(token=token, upload_url=upload_url, image_path=image_path)
    post_urn = create_post(token=token, author_urn=author_urn, commentary=commentary, image_urn=image_urn)

    # Engagement is intentionally decoupled from publishing.
    # The independent LinkedIn Engagement Worker decides whether/when to comment.
    comment = LinkedInActionResult(
        status="QUEUED",
        error="Post published. Independent LinkedIn Engagement Worker owns comments.",
    )
    like = LinkedInActionResult(
        status="NOT_HANDLED",
        error="Reactions are intentionally handled outside the publisher.",
    )
    print("LinkedIn post published; comments/reactions delegated to independent workers.")
    return {"image_urn": image_urn, "post_urn": post_urn, "comment": comment.as_dict(), "like": like.as_dict()}
