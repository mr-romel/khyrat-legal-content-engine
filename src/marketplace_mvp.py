from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "marketplace_data"
DATA_FILE = DATA_DIR / "marketplace.json"
DASHBOARD_FILE = DATA_DIR / "dashboard.html"

PLATFORMS = ("khamsat", "mostaql")


@dataclass
class ServiceDraft:
    id: str
    platform: str
    title: str
    description: str
    deliverables: list[str]
    upgrades: list[str] = field(default_factory=list)
    faqs: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    status: str = "DRAFT"
    source_topic: str = ""


@dataclass
class PortfolioItem:
    id: str
    title: str
    summary: str
    skills: list[str]
    status: str = "DRAFT"
    source_topic: str = ""


@dataclass
class Opportunity:
    id: str
    platform: str
    title: str
    description: str
    match_score: int
    rationale: list[str]
    suggested_price_egp: int
    suggested_days: int
    status: str = "NEW"
    offer: str = ""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _slug(value: str) -> str:
    value = re.sub(r"[^\w\u0600-\u06ff]+", "-", value.strip().lower())
    return value.strip("-")[:50] or "item"


def load_state() -> dict[str, Any]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not DATA_FILE.exists():
        return {"updated_at": _now(), "services": [], "portfolio": [], "opportunities": [], "activity": []}
    return json.loads(DATA_FILE.read_text(encoding="utf-8"))


def save_state(state: dict[str, Any]) -> None:
    state["updated_at"] = _now()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _activity(state: dict[str, Any], message: str) -> None:
    state.setdefault("activity", []).insert(0, {"time": _now(), "message": message})
    state["activity"] = state["activity"][:100]


def generate_service(topic: str, angle: str = "احترافي") -> ServiceDraft:
    title = f"صياغة ومراجعة {topic} باحترافية قانونية"
    description = (
        f"أقدم خدمة قانونية متخصصة في {topic} مع التركيز على حماية العميل، وضوح الالتزامات، "
        "رصد المخاطر والثغرات، واقتراح صياغات عملية قابلة للتنفيذ. يتم العمل على المستند وفقاً "
        "للمعلومات التي يقدمها العميل وبما يتناسب مع طبيعة معاملته."
    )
    return ServiceDraft(
        id=f"svc-{_slug(topic)}",
        platform="khamsat",
        title=title,
        description=description,
        deliverables=[
            "مراجعة قانونية منظمة للمستند أو المتطلبات",
            "تحديد البنود أو النقاط عالية المخاطر",
            "اقتراح تعديلات وصياغات واضحة",
            "ملاحظات تنفيذية مختصرة للعميل",
        ],
        upgrades=["مراجعة عاجلة", "جلسة شرح ومناقشة", "صياغة نسخة معدلة كاملة"],
        faqs=[
            "هل أحتاج لإرسال المستند كاملاً؟ نعم، كلما اكتملت البيانات كانت المراجعة أدق.",
            "هل الخدمة استشارة عامة؟ لا، يتم تحديد نطاق العمل قبل التنفيذ.",
        ],
        keywords=[topic, "صياغة عقود", "مراجعة عقود", "استشارة قانونية", "محامي"],
        source_topic=topic,
    )


def generate_portfolio(topic: str) -> PortfolioItem:
    return PortfolioItem(
        id=f"port-{_slug(topic)}",
        title=f"دراسة حالة: {topic}",
        summary=(
            f"نموذج أعمال يوضح منهجية التعامل مع {topic}: فهم المطلوب، تحديد المخاطر، "
            "ترتيب الأولويات، ثم تقديم مخرجات قانونية عملية دون كشف بيانات أي عميل حقيقي."
        ),
        skills=["Legal Research", "Contract Review", "Legal Drafting", "Risk Analysis"],
        source_topic=topic,
    )


def score_opportunity(title: str, description: str) -> tuple[int, list[str]]:
    text = f"{title} {description}".lower()
    keywords = {
        "عقد": 25, "عقود": 25, "قانون": 20, "قانونية": 20, "محامي": 25,
        "استشارة": 20, "صياغة": 20, "شركة": 10, "عمل": 10, "لائحة": 15,
        "مراجعة": 20, "شروط": 15,
    }
    hits = [(word, points) for word, points in keywords.items() if word in text]
    score = min(100, 20 + sum(points for _, points in hits))
    rationale = [f"مطابقة مباشرة مع: {word}" for word, _ in hits[:5]] or ["لا توجد مطابقة قوية بعد"]
    return score, rationale


def add_opportunity(state: dict[str, Any], title: str, description: str) -> Opportunity:
    score, rationale = score_opportunity(title, description)
    item = Opportunity(
        id=f"opp-{_slug(title)}-{len(state.get('opportunities', [])) + 1}",
        platform="mostaql",
        title=title,
        description=description,
        match_score=score,
        rationale=rationale,
        suggested_price_egp=1500 if score >= 70 else 1000,
        suggested_days=2 if score >= 70 else 4,
    )
    state.setdefault("opportunities", []).insert(0, asdict(item))
    _activity(state, f"تم تحليل مشروع مستقل: {title} — Match {score}%")
    return item


def build_offer(opportunity: dict[str, Any]) -> str:
    return (
        "مرحباً، قرأت تفاصيل المشروع وأرى أن المطلوب يتوافق مباشرة مع خبرتي في الأعمال القانونية، "
        "خصوصاً تحليل المخاطر وصياغة ومراجعة المستندات.\n\n"
        "سأبدأ بفهم المستند أو المتطلبات وتحديد النقاط القانونية المؤثرة، ثم أقدم الملاحظات "
        "والصياغات المقترحة بشكل واضح ومنظم، مع الالتزام بنطاق العمل المتفق عليه.\n\n"
        f"المدة المقترحة: {opportunity.get('suggested_days', 3)} أيام. "
        f"والميزانية المقترحة: {opportunity.get('suggested_price_egp', 1500)} جنيه مصري.\n\n"
        "إذا أرسلت التفاصيل الأساسية أو نموذج المستند، أستطيع تحديد نطاق العمل النهائي بدقة قبل البدء."
    )


def seed_demo(state: dict[str, Any]) -> None:
    if not state["services"]:
        state["services"].append(asdict(generate_service("مراجعة العقود التجارية")))
    if not state["portfolio"]:
        state["portfolio"].append(asdict(generate_portfolio("مراجعة عقد تجاري")))
    if not state["opportunities"]:
        add_opportunity(state, "مطلوب محامي لمراجعة عقد شركة", "مراجعة عقد وتحديد المخاطر واقتراح تعديلات وصياغة البنود القانونية")
    for opp in state["opportunities"]:
        if not opp.get("offer"):
            opp["offer"] = build_offer(opp)
            opp["status"] = "OFFER_READY"
    _activity(state, "تم تجهيز بيانات MVP للعرض والمراجعة")


def _card(title: str, value: str) -> str:
    return f'<div class="card"><div class="muted">{escape(title)}</div><div class="big">{escape(value)}</div></div>'


def render_dashboard(state: dict[str, Any]) -> str:
    services = state.get("services", [])
    portfolio = state.get("portfolio", [])
    opportunities = state.get("opportunities", [])
    rows = []
    for item in services:
        rows.append(f"<tr><td>خمسات</td><td>{escape(item['title'])}</td><td>{escape(item['status'])}</td><td>خدمة</td></tr>")
    for item in opportunities:
        rows.append(f"<tr><td>مستقل</td><td>{escape(item['title'])}</td><td>{escape(item['status'])}</td><td>{item['match_score']}%</td></tr>")
    activity = "".join(f"<li>{escape(x['time'])} — {escape(x['message'])}</li>" for x in state.get("activity", [])[:12])
    return f'''<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Khyrat Marketplace</title><style>body{{font-family:Arial,sans-serif;background:#f5f6f8;margin:0;color:#20242a}}.wrap{{max-width:1100px;margin:30px auto;padding:0 18px}}.top{{display:flex;justify-content:space-between;align-items:center}}.grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:20px 0}}.card{{background:#fff;border:1px solid #ddd;border-radius:12px;padding:18px}}.big{{font-size:28px;font-weight:700;margin-top:8px}}.muted{{color:#68707b}}section{{background:#fff;border:1px solid #ddd;border-radius:12px;padding:18px;margin:14px 0}}table{{width:100%;border-collapse:collapse}}td,th{{padding:11px;border-bottom:1px solid #eee;text-align:right}}.badge{{padding:4px 8px;border-radius:10px;background:#eef2f7}}li{{margin:8px 0}}</style></head><body><div class="wrap"><div class="top"><div><h1>Khyrat Marketplace</h1><div class="muted">لوحة مراجعة أولية — لا يوجد نشر تلقائي حتى الآن</div></div><div class="muted">آخر تحديث: {escape(state.get('updated_at',''))}</div></div><div class="grid">{_card('خدمات خمسات',str(len(services)))}{_card('Portfolio',str(len(portfolio)))}{_card('فرص مستقل',str(len(opportunities)))}{_card('بانتظار المراجعة',str(sum(x.get('status') in {'DRAFT','OFFER_READY'} for x in services + opportunities)))}</div><section><h2>العناصر الحالية</h2><table><tr><th>المنصة</th><th>العنوان</th><th>الحالة</th><th>التقييم</th></tr>{''.join(rows) or '<tr><td colspan="4">لا توجد عناصر</td></tr>'}</table></section><section><h2>سجل النشاط</h2><ul>{activity or '<li>لا يوجد نشاط</li>'}</ul></section><section><h2>مبدأ التشغيل</h2><p>Generate → Quality Check → Dashboard Review → Approval → Platform. هذه النسخة لا تنفذ تسجيل دخول أو ضغط أزرار أو نشر نيابة عن الحساب.</p></section></div></body></html>'''


def run(seed: bool = False) -> Path:
    state = load_state()
    if seed:
        seed_demo(state)
    save_state(state)
    DASHBOARD_FILE.write_text(render_dashboard(state), encoding="utf-8")
    return DASHBOARD_FILE


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Khyrat Marketplace MVP")
    parser.add_argument("--seed-demo", action="store_true")
    args = parser.parse_args()
    print(run(seed=args.seed_demo))
