"""Generate synthetic German invoices as markdown, plus extractive QA pairs.

Modelled on real retail/B2B invoice layouts:
  - alphanumeric invoice numbers (M324-11857-4999-0-29082026)
  - both currency styles: "89,99 EUR" and "89,99 €"
  - both VAT styles: "19,00%" and "19 %"
  - four layouts, including the column-block form (labels row / values row)
  - distractors: several identical dates, near-identical order/delivery numbers,
    customer IDs, article numbers
  - "nicht relevant" fields: present but empty

Every answer is a literal substring of the rendered markdown.

Run:  python synthetic_invoice_v1.py --preview
      python synthetic_invoice_v1.py --n 2000
"""
import os, json, random, argparse
from datetime import date, timedelta

ROOT = "D:/Tasks/Project_SLM"
OUT = f"{ROOT}/sft"
NICHT_RELEVANT = "nicht relevant"
NR = NICHT_RELEVANT

FIRMEN = ["Muster GmbH", "Nordwind Logistik AG", "Alpen Technik GmbH & Co. KG",
          "Bergmann Handels GmbH", "Rheinbau Systeme AG", "Sonnental Verlag GmbH",
          "Weiss Maschinenbau GmbH", "Delta Elektronik AG", "Kranz & Partner GbR",
          "Hansa Spedition GmbH", "Lindner Chemie AG", "Vogel IT-Services GmbH",
          "MM Smart München", "Elektro Zentrum Nord GmbH", "TechnoPart AG"]
STRASSEN = ["Hauptstraße", "Bahnhofstraße", "Industrieweg", "Am Hafen",
            "Lindenallee", "Gewerbering", "Schulstraße", "Mühlenweg",
            "Kelheimer Straße", "Tal"]
ORTE = [("10115", "Berlin"), ("80331", "München"), ("20095", "Hamburg"),
        ("50667", "Köln"), ("70173", "Stuttgart"), ("60311", "Frankfurt am Main"),
        ("04109", "Leipzig"), ("01067", "Dresden"), ("30159", "Hannover"),
        ("80634", "München")]
VORNAMEN = ["Nikhil", "Anna", "Michael", "Sabine", "Thomas", "Julia", "Stefan",
            "Petra", "Andreas", "Katrin", "Lukas", "Miriam"]
NACHNAMEN = ["Mule", "Schmidt", "Müller", "Weber", "Fischer", "Wagner", "Becker",
             "Hoffmann", "Schulz", "Koch", "Richter", "Klein"]
ARTIKEL = [
    ("WDBHHG0010BBK 1TB BLACK ELEMENTS EX", "Stk"),
    ("SAMSUNG SSD 980 PRO 2TB NVME", "Stk"),
    ("LOGITECH MX MASTER 3S GRAPHITE", "Stk"),
    ("Beratungsleistung IT-Migration", "Std"),
    ("Wartungsvertrag Serverschrank", "Monat"),
    ("Transportkosten Teillieferung", "Fahrt"),
    ("Montagearbeiten vor Ort", "Std"),
    ("Softwarelizenz Jahresabo", "Stk"),
    ("Ersatzteile Sortiment B", "Stk"),
    ("Schulung Grundlagen", "Tag"),
]

GESCHAEFTSF = ["Alexander Major", "Petra Lindner", "Michael Braun",
               "Sabine Vogel", "Thomas Kranz"]

L_RECHNUNG = ["Rechnungsnummer", "Rechnung Nr.", "Rechnungs-Nr.", "Beleg-Nr.",
              "Rechnungsnr."]
L_BESTELL = ["Bestellnummer", "Bestell-Nr.", "Auftragsnummer", "Auftrags-Nr."]
L_DATUM = ["Rechnungsdatum", "Datum", "Belegdatum"]
L_NETTO = ["Nettobetrag", "Summe netto", "Zwischensumme netto", "Netto", "Total Amount Inkl MWST", "Nettowert"]
L_BRUTTO = ["Bruttobetrag", "Gesamtbetrag", "Rechnungsbetrag brutto", "Endbetrag", "Total Amount Inkl MWST"]
L_VATAMT = ["Steuerbetrag", "MwSt.-Betrag", "USt-Betrag", "Mehrwertsteuer", "Umsatzsteuer", 'Umsatzsteuerbetrag']
L_VATRATE = ["Steuersatz", "MwSt.-Satz", "USt-Satz"]
L_UST = ["USt-IdNr.", "USt-Id.Nr.", "Umsatzsteuer-ID", "UST-ID", 'Vat-ID']
L_IBAN = ["IBAN", "Bankverbindung IBAN", "Konto (IBAN)"]

VAT_RATES = [19, 7, 20, 0]
VAT_WEIGHTS = [0.60, 0.20, 0.10, 0.10]


# ---------------------------------------------------------------- formatting
def de_num(x):
    return f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
 
 
def money(x, style):
    return f"{de_num(x)} EUR" if style == "EUR" else f"{de_num(x)} €"
 
 
def vat_str(v, style):
    return f"{v},00%" if style == "comma" else f"{v} %"
 
 
def iban(rng):
    return "DE" + f"{rng.randint(0,99):02d} " + " ".join(
        f"{rng.randint(0,9999):04d}" for _ in range(4)) + f" {rng.randint(0,99):02d}"
 
 
def ust_id(rng):
    return f"DE{rng.randint(100000000, 999999999)}"
 
 
def firma(rng):
    plz, ort = rng.choice(ORTE)
    return (rng.choice(FIRMEN), f"{rng.choice(STRASSEN)} {rng.randint(1,199)}",
            f"{plz} {ort}")
 
 
def person(rng):
    plz, ort = rng.choice(ORTE)
    return (f"{rng.choice(VORNAMEN)} {rng.choice(NACHNAMEN)}",
            f"{rng.choice(STRASSEN)} {rng.randint(1,199)}", f"{plz} {ort}")
 
 
def rechnungsnummer(rng, d):
    k = rng.randint(0, 3)
    if k == 0:
        return (f"M{rng.randint(100,999)}-{rng.randint(10000,99999)}-"
                f"{rng.randint(1000,9999)}-{rng.randint(0,9)}-{d.strftime('%d%m%Y')}")
    if k == 1:
        return f"RE-{d.year}-{rng.randint(1,999999):06d}"
    if k == 2:
        return f"{d.year}/{d.month:02d}/{rng.randint(10000,99999)}"
    return f"{rng.randint(100000, 999999)}"
 
 
# ---------------------------------------------------------------- invoice
def make_invoice(rng):
    cur = rng.choice(["EUR", "EUR", "€"])
    vst = rng.choice(["comma", "space"])
    d = date(2024, 1, 1) + timedelta(days=rng.randint(0, 900))
 
    lief = firma(rng)
    empf = person(rng) if rng.random() < 0.5 else firma(rng)
    while empf[0] == lief[0]:
        empf = firma(rng)
 
    vat = rng.choices(VAT_RATES, VAT_WEIGHTS)[0]
    items, brutto_sum = [], 0.0
    for i in range(rng.randint(1, 4)):
        bez, einheit  = rng.choice(ARTIKEL)
        menge = rng.randint(1, 20)
        preis = round(rng.uniform(8, 950), 2)
        summe = round(menge * preis, 2)
        brutto_sum += summe
        items.append((i + 1, rng.randint(1000000, 9999999), bez, menge, einheit, preis, summe))
    brutto = round(brutto_sum, 2)
    netto = round(brutto / (1 + vat / 100), 2)
    vat_amt = round(brutto - netto, 2)
 
    bestellnr = f"{rng.randint(100000000, 999999999)}"
    liefernr = f"{bestellnr}_{rng.randint(1,3)}"
    kunden_id = f"{rng.randint(10**15, 10**16 - 1)}"
 
    # header USt-IdNr. is often "nicht relevant"; the FOOTER always carries the
    # supplier's real one. A model must pick the right occurrence.
    ust_header = NR if rng.random() < 0.5 else ust_id(rng)
    ust_footer = ust_id(rng)
    liefer_adr = NR if rng.random() < 0.6 else f"{empf[1]}, {empf[2]}"
 
    lr, lb, ld = rng.choice(L_RECHNUNG), rng.choice(L_BESTELL), rng.choice(L_DATUM)
    ln, lbr = rng.choice(L_NETTO), rng.choice(L_BRUTTO)
    lva, lvr = rng.choice(L_VATAMT), rng.choice(L_VATRATE)
    lu, li = rng.choice(L_UST), rng.choice(L_IBAN)
    gf = rng.choice(GESCHAEFTSF)
    hrb = f"{rng.randint(100000, 999999)}"
    domain = lief[0].split()[0].lower().replace("&", "").replace(".", "")
    email = f"INFO@{domain.upper()}.DE"
    seiten = rng.choice([1, 1, 1, 2])
 
    f = {
        "lieferant": lief[0], "empfaenger": empf[0],
        "datum": d.strftime("%d.%m.%Y"),
        "rechnungsnummer": rechnungsnummer(rng, d),
        "bestellnummer": bestellnr, "liefernummer": liefernr,
        "kunden_id": kunden_id,
        "netto": money(netto, cur), "brutto": money(brutto, cur),
        "vat_satz": vat_str(vat, vst), "vat_betrag": money(vat_amt, cur),
        "iban": iban(rng), "ust_header": ust_header, "ust_footer": ust_footer,
        "liefer_adresse": liefer_adr,
        "zahlungsmittel": rng.choice(["Onlinezahlung", "Überweisung",
                                      "Lastschrift", "Rechnung"]),
        "lieferart": rng.choice(["Abholung", "Standardversand", "Spedition"]),
        "geschaeftsfuehrer": gf, "hrb": hrb, "email": email,
    }
    lb_ = dict(lr=lr, lb=lb, ld=ld, ln=ln, lbr=lbr, lva=lva, lvr=lvr, lu=lu, li=li)
 
    # ------------------------------------------------- header (plumber shape)
    head = (f"{lief[0]} {lief[1]} {lief[2]}\n"
            f"Lieferadresse\n"
            f"{empf[0]} {f['liefer_adresse']}\n"
            f"{empf[1]}\n{empf[2]}\nDE\n"
            f"{lu} Kunden-ID\n"
            f"{ust_header} {kunden_id}\n"
            f"Rechnung\n"
            f"{lr} {f['rechnungsnummer']}\n")
 
    # ------------------------------------------------- meta block
    lay = rng.randint(0, 2)
    if lay == 0:        # column block, as pdfplumber emits it
        meta = (f"{ld} {lb} Bestelldatum Zahlungsmittel\n"
                f"{f['datum']} {bestellnr} {f['datum']} {f['zahlungsmittel']}\n"
                f"Lieferart Liefernummer Lieferdatum Vorgängerdokument\n"
                f"{f['lieferart']} {liefernr} {f['datum']} {NR}\n")
    elif lay == 1:      # key: value lines
        meta = (f"{ld}: {f['datum']}\n{lb}: {bestellnr}\n"
                f"Bestelldatum: {f['datum']}\nLieferart: {f['lieferart']}\n"
                f"Liefernummer: {liefernr}\nLieferdatum: {f['datum']}\n"
                f"Zahlungsmittel: {f['zahlungsmittel']}\n"
                f"Vorgängerdokument: {NR}\n")
    else:               # two-column pairs
        meta = (f"{ld} {f['datum']} {lb} {bestellnr}\n"
                f"Liefernummer {liefernr} Lieferdatum {f['datum']}\n"
                f"Zahlungsmittel {f['zahlungsmittel']} Lieferart {f['lieferart']}\n")
 
    # ------------------------------------------------- line items
    tbl = f"Position Artikelnummer Beschreibung Anzahl Einheit {lvr} Einzelpreis Gesamt\n"
    for pos, art, bez, menge, einheit, preis, summe in items:
        mengen_str = f"{menge} {einheit}" if rng.random() < 0.5 else f"{menge}"
        tbl += (f"{pos} {art} {bez} {mengen_str} {f['vat_satz']} "
                f"{money(preis, cur)} {money(summe, cur)}\n")
 
    # ------------------------------------------------- totals
    tot = (f"{lvr} {ln} {lva} {lbr} Gesamt {f['brutto']}\n"
           f"{f['vat_satz']} {f['netto']} {f['vat_betrag']} {f['brutto']} "
           f"Restbetrag {money(0, cur)}\n")
 
    # ------------------------------------------------- footer
    foot = (f"{lief[0]}\n"
            f"Web: www.{domain}.de E-Mail: {email}\n"
            f"Geschäftsführer: {gf}\n"
            f"Eingetragen beim Amtsgericht unter HRB {hrb} {lu}: {ust_footer}\n"
            f"{li}: {f['iban']}\n"
            f"Zahlbar innerhalb von {rng.choice([14, 30, 60])} Tagen ohne Abzug.\n"
            f"Seite 1/{seiten}\n")
 
    return head + meta + tbl + tot + foot, f, lb_
 
 
# ---------------------------------------------------------------- QA pairs
#def qa_for(md, f, lb_, rng, p_unans=0.22):
def qa_for(md, f, lb_, rng, p_unans=1.0):
    pairs = [
        (f"Was ist die {lb_['lr']}?", f["rechnungsnummer"]),
        (f"Wie lautet die {lb_['lb']}?", f["bestellnummer"]),
        ("Wie lautet die Liefernummer?", f["liefernummer"]),
        (f"Was ist das {lb_['ld']}?", f["datum"]),
        (f"Wie hoch ist der {lb_['ln']}?", f["netto"]),
        (f"Wie hoch ist der {lb_['lbr']}?", f["brutto"]),
        (f"Wie hoch ist der {lb_['lvr']}?", f["vat_satz"]),
        (f"Wie hoch ist der {lb_['lva']}?", f["vat_betrag"]),
        ("Wie lautet die IBAN?", f["iban"]),
        # the footer one is the supplier's real VAT id -- the header may say
        # "nicht relevant", so this question tests picking the right occurrence
        (f"Wie lautet die {lb_['lu']} des Lieferanten?", f["ust_footer"]),
        ("Wie lautet die Kunden-ID?", f["kunden_id"]),
        ("Wer ist der Rechnungssteller?", f["lieferant"]),
        ("Wer ist der Rechnungsempfänger?", f["empfaenger"]),
        ("Welches Zahlungsmittel wurde verwendet?", f["zahlungsmittel"]),
        ("Welche Lieferart wurde gewählt?", f["lieferart"]),
        ("Wer ist der Geschäftsführer?", f["geschaeftsfuehrer"]),
        ("Wie lautet die E-Mail-Adresse?", f["email"]),
        ("Wie lautet die HRB-Nummer?", f["hrb"]),
    ]
    out = []
    for q, a in pairs:
        assert a in md, f"answer not a span: {a!r}"
        out.append((q, a, True))
    absent = ["Wie lautet die Telefonnummer des Lieferanten?",
              "Wie hoch ist der gewährte Skonto?",
              "Wie lautet die Vertragsnummer?",
              "Wie hoch sind die Versandkosten?",
              "Wie lautet die Seriennummer des Artikels?",
              "Wie lautet die Kostenstelle?",
              "Wie lautet die Projektnummer?",
              "Wann ist das Zahlungsziel erreicht?"]
    for q in absent:
        if rng.random() < p_unans:
            out.append((q, "", False))
    return out
 
 
# ---------------------------------------------------------------- main
if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=2000)
    ap.add_argument("--test-frac", type=float, default=0.15)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--preview", action="store_true")
    args = ap.parse_args()
    rng = random.Random(args.seed)
 
    if args.preview:
        md, f, lb_ = make_invoice(rng)
        print(md)
        print("-" * 64)
        for q, a, ok in qa_for(md, f, lb_, rng):
            print(f"  {'Q' if ok else 'N'}: {q}\n     -> {a!r}")
        raise SystemExit
 
    rows = []
    for i in range(args.n):
        md, f, lb_ = make_invoice(rng)
        for q, a, ok in qa_for(md, f, lb_, rng):
            rows.append({"context": md, "question": q, "answer": a,
                         "lang": "de", "source": "invoice_synth",
                         "answerable": ok, "doc_id": i})
 
    n_test = int(args.n * args.test_frac)
    test_ids = set(rng.sample(range(args.n), n_test))
    train = [r for r in rows if r["doc_id"] not in test_ids]
    test = [r for r in rows if r["doc_id"] in test_ids]
    for r in rows:
        del r["doc_id"]
 
    os.makedirs(OUT, exist_ok=True)
    for tag, rs, nd in (("train", train, args.n - n_test), ("test", test, n_test)):
        rng.shuffle(rs)
        p = f"{OUT}/invoices_{tag}.jsonl"
        with open(p, "w", encoding="utf-8") as fh:
            for r in rs:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        un = sum(1 for r in rs if not r["answerable"])
        print(f"{tag}: {len(rs):,} pairs from {nd:,} invoices, "
              f"{un:,} unanswerable ({un/max(len(rs),1):.1%})  -> {p}")
 