from __future__ import annotations

import html
from pathlib import Path

from legal_decision_makers import load_leads

OUTPUT = Path("marketplace_pages/leads.html")


def esc(value: object) -> str:
    return html.escape(str(value or ""), quote=True)


def render(leads: list[dict]) -> str:
    rows = []
    for lead in leads:
        rows.append(
            "<tr>"
            f"<td><strong>{esc(lead.get('name'))}</strong><br><small>{esc(lead.get('title'))}</small></td>"
            f"<td>{esc(lead.get('company'))}</td>"
            f"<td>{esc(lead.get('normalized_role'))}</td>"
            f"<td>{esc(lead.get('industry'))}</td>"
            f"<td><b>{int(lead.get('score', 0))}</b></td>"
            f"<td>{esc(lead.get('legal_need'))}</td>"
            f"<td><a target='_blank' rel='noopener' href='{esc(lead.get('linkedin_url'))}'>LinkedIn</a></td>"
            f"<td>{esc(lead.get('status'))}</td>"
            "</tr>"
        )
    return f'''<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>خيرت — Legal Decision Makers</title>
<style>body{{font-family:Tahoma,Arial,sans-serif;background:#f4f6f8;color:#20242a;margin:0;padding:20px}}.wrap{{max-width:1500px;margin:auto}}header,.panel{{background:#fff;border:1px solid #dfe3e8;border-radius:14px;padding:18px;margin-bottom:14px}}input{{width:100%;padding:11px;border:1px solid #cbd1d8;border-radius:8px;font:inherit}}.table{{overflow:auto}}table{{width:100%;border-collapse:collapse;background:#fff}}th,td{{padding:11px;border-bottom:1px solid #e5e8eb;text-align:right;vertical-align:top;white-space:nowrap}}th{{background:#f8fafc}}a{{color:#20242a}}small{{color:#66717c}}.stat{{display:inline-block;background:#f8fafc;border-radius:9px;padding:10px 14px;margin-left:8px}}</style></head><body><div class="wrap"><header><h1>Decision Maker Engine</h1><p>صناع القرار المحتملون للتعاقد على الخدمات القانونية للشركات — بيانات مكتشفة من نتائج بحث عامة وليست Scraping لحساب LinkedIn.</p><div><span class="stat">إجمالي: {len(leads)}</span><span class="stat">أولوية 80+: {sum(int(x.get('score',0))>=80 for x in leads)}</span><span class="stat">Founder/CEO/Owner: {sum(x.get('normalized_role') in {'Founder','Co-Founder','CEO','Owner'} for x in leads)}</span></div></header><section class="panel"><input id="q" placeholder="ابحث بالاسم أو الشركة أو المنصب أو الصناعة" oninput="filterRows()"></section><section class="panel"><div class="table"><table id="t"><thead><tr><th>الشخص</th><th>الشركة</th><th>المنصب</th><th>الصناعة</th><th>Score</th><th>الخدمة القانونية المحتملة</th><th>LinkedIn</th><th>الحالة</th></tr></thead><tbody>{''.join(rows) or '<tr><td colspan="8">لا توجد Leads حتى الآن</td></tr>'}</tbody></table></div></section></div><script>function filterRows(){{const q=document.getElementById('q').value.toLowerCase();for(const r of document.querySelectorAll('#t tbody tr'))r.style.display=r.innerText.toLowerCase().includes(q)?'':'none';}}</script></body></html>'''


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(render(load_leads()), encoding="utf-8")
    print(OUTPUT)


if __name__ == "__main__":
    main()
