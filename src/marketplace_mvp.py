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
    description = f"أقدم خدمة قانونية متخصصة في {topic} مع التركيز على حماية العميل، وضوح الالتزامات، رصد المخاطر والثغرات، واقتراح صياغات عملية قابلة للتنفيذ. يتم العمل على المستند وفقاً للمعلومات التي يقدمها العميل وبما يتناسب مع طبيعة معاملته."
    return ServiceDraft(id=f"svc-{_slug(topic)}", platform="khamsat", title=title, description=description, deliverables=["مراجعة قانونية منظمة للمستند أو المتطلبات", "تحديد البنود أو النقاط عالية المخاطر", "اقتراح تعديلات وصياغات واضحة", "ملاحظات تنفيذية مختصرة للعميل"], upgrades=["مراجعة عاجلة", "جلسة شرح ومناقشة", "صياغة نسخة معدلة كاملة"], faqs=["هل أحتاج لإرسال المستند كاملاً؟ نعم، كلما اكتملت البيانات كانت المراجعة أدق.", "هل الخدمة استشارة عامة؟ لا، يتم تحديد نطاق العمل قبل التنفيذ."], keywords=[topic, "صياغة عقود", "مراجعة عقود", "استشارة قانونية", "محامي"], source_topic=topic)


def generate_portfolio(topic: str) -> PortfolioItem:
    return PortfolioItem(id=f"port-{_slug(topic)}", title=f"دراسة حالة: {topic}", summary=f"نموذج أعمال يوضح منهجية التعامل مع {topic}: فهم المطلوب، تحديد المخاطر، ترتيب الأولويات، ثم تقديم مخرجات قانونية عملية دون كشف بيانات أي عميل حقيقي.", skills=["Legal Research", "Contract Review", "Legal Drafting", "Risk Analysis"], source_topic=topic)


def score_opportunity(title: str, description: str) -> tuple[int, list[str]]:
    text = f"{title} {description}".lower()
    keywords = {"عقد": 25, "عقود": 25, "قانون": 20, "قانونية": 20, "محامي": 25, "استشارة": 20, "صياغة": 20, "شركة": 10, "عمل": 10, "لائحة": 15, "مراجعة": 20, "شروط": 15}
    hits = [(word, points) for word, points in keywords.items() if word in text]
    score = min(100, 20 + sum(points for _, points in hits))
    rationale = [f"مطابقة مباشرة مع: {word}" for word, _ in hits[:5]] or ["لا توجد مطابقة قوية بعد"]
    return score, rationale


def add_opportunity(state: dict[str, Any], title: str, description: str) -> Opportunity:
    score, rationale = score_opportunity(title, description)
    item = Opportunity(id=f"opp-{_slug(title)}-{len(state.get('opportunities', [])) + 1}", platform="mostaql", title=title, description=description, match_score=score, rationale=rationale, suggested_price_egp=1500 if score >= 70 else 1000, suggested_days=2 if score >= 70 else 4)
    state.setdefault("opportunities", []).insert(0, asdict(item))
    _activity(state, f"تم تحليل مشروع مستقل: {title} — Match {score}%")
    return item


def build_offer(opportunity: dict[str, Any]) -> str:
    """Create a concise, human proposal suitable for Mostaql review/copy."""
    title = str(opportunity.get("title") or "المشروع").strip()
    days = int(opportunity.get("suggested_days", 3) or 3)
    price = int(opportunity.get("suggested_price_egp", 1500) or 1500)
    return (
        "أهلًا، اطلعت على طلبك، وأقدر أساعدك في المراجعة القانونية للمستند وتحليل البنود التي قد تسبب لك مخاطر أو التزامات غير واضحة.\n\n"
        "هراجع المستند بندًا بندًا، وأوضح أي نقاط تحتاج تعديل أو إعادة صياغة، مع تقديم البديل المقترح بشكل عملي وواضح. ولو فيه نقطة محتاجة تفاوض أو تستدعي الانتباه قبل التوقيع، هأشير إليها صراحة.\n\n"
        "هدفي إنك تخرج من المراجعة وأنت عارف بالضبط: إيه المشكلة؟ وإيه خطورتها؟ وإيه التعديل المناسب؟\n\n"
        f"أقدر أبدأ فورًا، والمدة المتوقعة {days} أيام، والميزانية {price} جنيه مصري كما هو محدد في العرض.\n\n"
        f"لو أرسلت المستند أو التفاصيل الأساسية الخاصة بـ{title}، أبدأ بمراجعته وتحديد نطاق العمل بدقة قبل التنفيذ."
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


def _card(title: str, value: str, note: str = "") -> str:
    return f'<div class="card"><div class="muted">{escape(title)}</div><div class="big">{escape(value)}</div><div class="note">{escape(note)}</div></div>'


def _status(value: str) -> str:
    return f'<span class="badge">{escape(value)}</span>'


def _list(items: list[str]) -> str:
    return "".join(f"<li>{escape(x)}</li>" for x in items) or "<li>لا توجد بيانات</li>"


def render_dashboard(state: dict[str, Any]) -> str:
    services = state.get("services", [])
    portfolio = state.get("portfolio", [])
    opportunities = state.get("opportunities", [])
    activity = state.get("activity", [])[:12]
    review_count = sum(x.get("status") in {"DRAFT", "OFFER_READY", "READY_FOR_REVIEW"} for x in services + opportunities)
    approved = sum(x.get("status") in {"APPROVED", "PUBLISHED", "SUBMITTED"} for x in services + opportunities)
    failures = sum(x.get("status") == "FAILED" for x in services + opportunities)
    service_cards = "".join(f'''<article class="item"><div class="row"><strong>{escape(x['title'])}</strong>{_status(x.get('status','DRAFT'))}</div><p>{escape(x['description'])}</p><h4>المخرجات</h4><ul>{_list(x.get('deliverables', []))}</ul><div class="tags">{' '.join(f'<span>{escape(k)}</span>' for k in x.get('keywords', [])[:5])}</div><div class="actions"><button disabled>مراجعة</button><button disabled>اعتماد</button></div></article>''' for x in services)
    opp_cards = "".join(f'''<article class="item"><div class="row"><strong>{escape(x['title'])}</strong><span class="score">{int(x.get('match_score',0))}% Match</span></div><p>{escape(x['description'])}</p><h4>لماذا مناسب؟</h4><ul>{_list(x.get('rationale', []))}</ul><div class="proposal"><b>المقترح:</b> {int(x.get('suggested_price_egp',0))} جنيه · {int(x.get('suggested_days',0))} أيام</div><details><summary>عرض الـ Offer الجاهز</summary><pre>{escape(x.get('offer',''))}</pre></details><div class="actions"><button disabled>مراجعة</button><button disabled>اعتماد</button><button disabled>إعادة توليد</button></div></article>''' for x in opportunities)
    portfolio_cards = "".join(f'''<article class="item"><div class="row"><strong>{escape(x['title'])}</strong>{_status(x.get('status','DRAFT'))}</div><p>{escape(x['summary'])}</p><div class="tags">{' '.join(f'<span>{escape(k)}</span>' for k in x.get('skills', []))}</div></article>''' for x in portfolio)
    activity_html = "".join(f"<li><span>{escape(x.get('time',''))}</span> {escape(x.get('message',''))}</li>" for x in activity) or "<li>لا يوجد نشاط</li>"
    return f'''<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Khyrat Marketplace Dashboard</title><style>
body{{font-family:Arial,Tahoma,sans-serif;background:#f4f6f8;margin:0;color:#20242a}}.wrap{{max-width:1180px;margin:28px auto;padding:0 18px}}header{{display:flex;justify-content:space-between;gap:20px;align-items:center}}h1{{margin-bottom:6px}}.muted,.note{{color:#69717d}}.grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:20px 0}}.card,section,.item{{background:#fff;border:1px solid #dfe3e8;border-radius:14px;padding:18px;box-sizing:border-box}}.big{{font-size:30px;font-weight:700;margin-top:7px}}.note{{font-size:12px;margin-top:5px}}section{{margin:14px 0}}.items{{display:grid;grid-template-columns:repeat(2,1fr);gap:12px}}.row{{display:flex;justify-content:space-between;gap:10px;align-items:flex-start}}.badge,.score,.tags span{{display:inline-block;background:#eef2f6;border-radius:999px;padding:5px 9px;font-size:12px}}.score{{font-weight:700}}h4{{margin-bottom:5px}}li{{margin:7px 0}}.tags{{display:flex;gap:6px;flex-wrap:wrap;margin-top:12px}}.actions{{display:flex;gap:8px;margin-top:14px}}button{{padding:8px 12px;border:1px solid #ccd2d8;border-radius:8px;background:#f2f3f5}}button:disabled{{opacity:.65}}pre{{white-space:pre-wrap;background:#f7f8fa;padding:12px;border-radius:8px;line-height:1.7}}.proposal{{margin-top:12px;padding:10px;border-radius:8px;background:#f7f8fa}}@media(max-width:800px){{.grid,.items{{grid-template-columns:1fr}}header{{display:block}}}}</style></head><body><div class="wrap"><header><div><h1>Khyrat Marketplace Dashboard</h1><div class="muted">Generate → Quality Check → Dashboard Review → Approval → Platform</div></div><div class="muted">آخر تحديث: {escape(state.get('updated_at',''))}</div></header>
<div class="grid">{_card('خدمات خمسات',str(len(services)),'Service drafts')}{_card('Portfolio',str(len(portfolio)),'أعمال قابلة للعرض')}{_card('فرص مستقل',str(len(opportunities)),'Opportunities')}{_card('بانتظار المراجعة',str(review_count),'تحتاج قرارك')}</div>
<section><h2>خدمات خمسات</h2><div class="items">{service_cards or '<div class="item">لا توجد خدمات بعد.</div>'}</div></section>
<section><h2>فرص مستقل + عروض جاهزة</h2><div class="items">{opp_cards or '<div class="item">لا توجد فرص بعد.</div>'}</div></section>
<section><h2>Portfolio</h2><div class="items">{portfolio_cards or '<div class="item">لا توجد أعمال بعد.</div>'}</div></section>
<section><h2>Activity Log</h2><ul>{activity_html}</ul></section>
<section><h2>System Health</h2><p>Marketplace مستقل عن Core. النشر والتقديم التلقائيان غير مفعّلين حالياً. Approved: {approved} · Failed: {failures}. أزرار المراجعة في ملف HTML توضيحية؛ التنفيذ التفاعلي سيتم عبر السيرفر المحلي في المرحلة التالية.</p></section>
</div></body></html>'''


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
