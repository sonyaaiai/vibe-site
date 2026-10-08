#!/usr/bin/env python3
"""從證交所、櫃買中心的公開資料(免金鑰),整理成 data/companies.js 給網頁使用。

執行方式:  python3 update_data.py
只用 Python 內建功能,不用安裝任何套件。金額單位: 億元新台幣。
"""
import json, os, statistics, sys, urllib.request
from datetime import date

TWSE = "https://openapi.twse.com.tw/v1/opendata/"
TPEX = "https://www.tpex.org.tw/openapi/v1/mopsfin_"


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def num(v):
    try:
        return float(str(v).replace(",", "").strip())
    except ValueError:
        return None


def yi(v):  # 千元 -> 億元
    n = num(v)
    return None if n is None else round(n / 100000, 2)


def cap_yi(v):  # 元 -> 億元
    n = num(v)
    return None if n is None else round(n / 1e8, 1)


def pick(row, *keys):
    for k in keys:
        if k in row and row[k] not in ("", None):
            return row[k]
    return None


def pct(a, b):
    return None if a is None or b in (None, 0) else round(a / b * 100, 1)


def load(market):
    """回傳 {代號: 公司資料}"""
    if market == "上市":
        basic, inc, bal, rev, eps = (get(TWSE + p) for p in
            ("t187ap03_L", "t187ap06_L_ci", "t187ap07_L_ci", "t187ap05_L", "t187ap14_L"))
        code = "公司代號"
        f = dict(code="公司代號", name="公司簡稱", full="公司名稱", chair="董事長", est="成立日期",
                 web="網址", cap="實收資本額")
    else:
        basic, inc, bal, rev, eps = (get(TPEX + p) for p in
            ("t187ap03_O", "t187ap06_O_ci", "t187ap07_O_ci", "t187ap05_O", "t187ap14_O"))
        f = dict(code="SecuritiesCompanyCode", name="CompanyAbbreviation", full="CompanyName",
                 chair="Chairman", est="DateOfIncorporation", web="WebAddress", cap="Paidin.Capital.NTDollars")
    ccode = "SecuritiesCompanyCode" if market == "上櫃" else "公司代號"
    by = lambda rows, key: {r[key]: r for r in rows}
    inc_d = by(inc, "SecuritiesCompanyCode" if market == "上櫃" else "公司代號")
    bal_d = by(bal, ccode)
    rev_d = by(rev, "公司代號")
    eps_d = by(eps, ccode)

    out = {}
    for b in basic:
        cid = b[f["code"]].strip()
        rec = {"i": cid, "n": b[f["name"]].strip(), "f": b[f["full"]].strip(), "m": market,
               "c": (b.get(f["chair"]) or "").strip(), "e": (b.get(f["est"]) or "").strip(),
               "w": (b.get(f["web"]) or "").strip(), "cap": cap_yi(b.get(f["cap"]))}
        r = rev_d.get(cid)
        rec["d"] = (r or {}).get("產業別", "")
        if r:
            rec["rv"] = {"ym": r["資料年月"], "cur": yi(r["營業收入-當月營收"]),
                         "ly": yi(r["營業收入-去年當月營收"]), "yoy": num(r["營業收入-去年同月增減(%)"]),
                         "cum": yi(r["累計營業收入-當月累計營收"]), "cumly": yi(r["累計營業收入-去年累計營收"]),
                         "cumyoy": num(r["累計營業收入-前期比較增減(%)"])}
        i, bl, e = inc_d.get(cid), bal_d.get(cid), eps_d.get(cid)
        season = int((i or e or {}).get("季別") or (i or e or {}).get("Season") or 0) or None
        year = (i or e or {}).get("年度") or (i or e or {}).get("Year")
        if i and bl:
            rec["t"] = "ci"
            rev_, gp, op = yi(i.get("營業收入")), yi(i.get("營業毛利（毛損）")), yi(i.get("營業利益（損失）"))
            ni = yi(i.get("本期淨利（淨損）"))
            nip = yi(i.get("淨利（淨損）歸屬於母公司業主"))
            eqp = yi(bl.get("歸屬於母公司業主之權益合計"))
            ta, tl = yi(bl.get("資產總計")), yi(bl.get("負債總計"))
            rec.update(rev=rev_, gp=gp, op=op, ni=ni, ta=ta, tl=tl,
                       eps=num(pick(i, "基本每股盈餘（元）")),
                       gm=pct(gp, rev_), om=pct(op, rev_), nm=pct(ni, rev_), debt=pct(tl, ta),
                       roe=pct(nip * 4 / season, eqp) if nip is not None and season else None)
        elif e:
            rec["t"] = "fin"  # 金融業等報表格式不同,只有簡版數字
            rec.update(rev=yi(e.get("營業收入")), ni=yi(e.get("稅後淨利")),
                       eps=num(pick(e, "基本每股盈餘(元)", "基本每股盈餘")))
        else:
            rec["t"] = "none"
        if season and year:
            rec["p"] = [int(year) + 1911, season]
        out[cid] = rec
    return out


def main():
    companies = {}
    for m in ("上市", "上櫃"):
        companies.update(load(m))
        print(m, "完成", file=sys.stderr)
    rows = sorted(companies.values(), key=lambda r: r["i"])

    # 同業中位數:每個產業用該產業一般公司的數字,產業少於 3 家就用全體
    def med(vals):
        vals = [v for v in vals if v is not None]
        return round(statistics.median(vals), 1) if vals else None
    keys = ("gm", "om", "nm", "roe", "debt")
    ci = [r for r in rows if r["t"] == "ci"]
    stats = {"_all": {k: med([r[k] for r in ci]) for k in keys}}
    for ind in {r["d"] for r in ci if r["d"]}:
        grp = [r for r in ci if r["d"] == ind]
        if len(grp) >= 3:
            stats[ind] = {k: med([r[k] for r in grp]) for k in keys}
            stats[ind]["n"] = len(grp)

    # 最近一期
    pers = [r["p"] for r in rows if "p" in r]
    latest = max(pers) if pers else None
    payload = {"updated": date.today().isoformat(), "period": latest, "stats": stats, "companies": rows}
    os.makedirs("data", exist_ok=True)
    with open("data/companies.js", "w", encoding="utf-8") as fh:
        fh.write("window.TW_DATA=" + json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + ";\n")
    print("寫入 data/companies.js:", len(rows), "家公司", file=sys.stderr)


if __name__ == "__main__":
    main()
