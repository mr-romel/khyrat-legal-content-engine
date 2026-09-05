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
    headers = {"Authorization": f"Bearer {token}", "Linkedin-Version": LINKEDIN_VERSION, "X-Restli-Protocol-Version": REST_PROTOCOL}
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
        label = "INSUFFICIENT_PERMISSION_OR_ACCESS"
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
    """Guarantee a substantive LinkedIn version; never allow a tiny title-only post through."""
    text = str(commentary or "").strip()
    if len(text) >= MIN_LINKEDIN_POST_CHARS:
        return text[:MAX_LINKEDIN_POST_CHARS].rstrip()
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
        raise LinkedInPublishError(f"LinkedIn commentary remained below required minimum ({len(text)} characters).")
    return text[:MAX_LINKEDIN_POST_CHARS].rstrip()


def create_post(*, token: str, author_urn: str, commentary: str, image_urn: str) -> str:
    endpoint = f"{LINKEDIN_REST_BASE}/posts"
    commentary = _strengthen_commentary(commentary)
    if len(commentary) < MIN_LINKEDIN_POST_CHARS:
        raise LinkedInPublishError(f"LinkedIn post rejected locally: only {len(commentary)} characters after expansion.")
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


def _comment_urn(post_urn: str, comment_id: str) -> str:
    return f"urn:li:comment:({post_urn},{comment_id})" if comment_id else ""


def add_comment(*, token: str, actor_urn: str, post_urn: str, message: str) -> LinkedInActionResult:
    endpoint = f"{LINKEDIN_REST_BASE}/socialActions/{quote(post_urn, safe='')}/comments"
    body = {"actor": actor_urn, "object": post_urn, "message": {"text": message}}
    result = _post_interaction_with_retry(endpoint=endpoint, token=token, body=body, action="comment")
    if isinstance(result, LinkedInActionResult):
        print(f"LinkedIn comment: {result.status} | http={result.http_status} | error={result.error}")
        return result
    comment_id = (result.headers.get("x-restli-id", "") or result.headers.get("X-RestLi-Id", "")).strip()
    if not comment_id:
        return LinkedInActionResult(status="FAILED", error="comment: LinkedIn returned no comment ID", http_status=result.status_code)
    comment_urn = _comment_urn(post_urn, comment_id)
    like = like_comment(token=token, actor_urn=actor_urn, comment_urn=comment_urn)
    print(f"LinkedIn comment: PUBLISHED | like={like.status} | like_http={like.http_status} | like_error={like.error}")
    return LinkedInActionResult(status="PUBLISHED", item_id=comment_urn, error=like.error, http_status=result.status_code)


def like_post(*, token: str, actor_urn: str, post_urn: str) -> LinkedInActionResult:
    return _create_reaction(token=token, actor_urn=actor_urn, root_urn=post_urn, action="like")


def like_comment(*, token: str, actor_urn: str, comment_urn: str) -> LinkedInActionResult:
    return _create_reaction(token=token, actor_urn=actor_urn, root_urn=comment_urn, action="like_comment")


def _create_reaction(*, token: str, actor_urn: str, root_urn: str, action: str) -> LinkedInActionResult:
    encoded_actor = quote(actor_urn, safe="")
    endpoint = f"{LINKEDIN_REST_BASE}/reactions?actor={encoded_actor}"
    body = {"root": root_urn, "reactionType": "LIKE"}
    result = _post_interaction_with_retry(endpoint=endpoint, token=token, body=body, action=action)
    if isinstance(result, LinkedInActionResult):
        print(f"LinkedIn {action}: {result.status} | http={result.http_status} | error={result.error}")
        return result
    reaction_id = ""
    try:
        payload = result.json()
        if isinstance(payload, dict):
            reaction_id = str(payload.get("id", "")).strip()
    except ValueError:
        pass
    return LinkedInActionResult(status="LIKED", item_id=reaction_id, http_status=result.status_code)


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
    comment = add_comment(token=token, actor_urn=author_urn, post_urn=post_urn, message=first_comment)
    like = like_post(token=token, actor_urn=author_urn, post_urn=post_urn)
    return {"image_urn": image_urn, "post_urn": post_urn, "comment": comment.as_dict(), "like": like.as_dict()}