#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Komponent Stok — evdeki elektronik komponent stoğunu takip eden program.

Çalıştırmak için:   python3 stok.py
Tarayıcıda http://127.0.0.1:8765 açılır. Veriler bu klasördeki stok.db dosyasında tutulur.
Yalnızca Python standart kütüphanesini kullanır; ek kurulum gerekmez.
"""
import base64
import csv
import html.parser
import io
import json
import os
import re
import sqlite3
import subprocess
import tempfile
import sys
import threading
import webbrowser
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(BASE_DIR, 'web')
DB_PATH = os.environ.get('STOK_DB', os.path.join(BASE_DIR, 'stok.db'))
PORT = int(os.environ.get('STOK_PORT', '8765'))
DB_LOCK = threading.Lock()


class UserError(Exception):
    """Kullanıcıya gösterilecek hata mesajı."""


def now():
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


# ---------------------------------------------------------------- Kategoriler

CATEGORIES = [
    'Dirençler', 'Kondansatörler', 'Endüktörler', 'Diyotlar', "LED'ler", 'Transistörler',
    'Entegreler', 'Mikrodenetleyiciler', 'Regülatörler', 'Konnektörler', 'Anahtar & Butonlar',
    'Kristal & Osilatörler', 'Koruma & Sigortalar', 'Röleler', 'Sensörler', 'Ekranlar',
    'Modüller', 'Mekanik', 'Alet & Sarf', 'Diğer',
]

# Sıra önemli: daha özel kurallar önce gelir (ör. "switching regulator" → Regülatör, Anahtar değil).
CATEGORY_RULES = [(cat, re.compile(rx)) for cat, rx in [
    ('Mikrodenetleyiciler', r'microcontroller|\bmcu\b|mikrodenetleyici|stm32|atmega|attiny|esp32|esp8266|'
                            r'\bpic1[0-8]|rp2040|nrf5\d|samd\d|gd32|ch32v'),
    ('Regülatörler', r'regulator|regülatör|\breg\b|\bldo\b|buck|boost|dc[-/ ]?dc|ams1117|lm317|lm78|\b78\d\d\b|'
                     r'lm2596|mp1584|ap2112|xc6206|ht73\d\d'),
    ("LED'ler", r'\bleds?\b(?!\s*(tutucu|holder|soket|yuva))|light emitting|ws2812|sk6812'),
    ('Kristal & Osilatörler', r'crystal|oscillator|resonator|kristal|osilatör|\bxtal'),
    ('Röleler', r'\brelay|\bröle'),
    ('Koruma & Sigortalar', r'\bfuse|polyfuse|resettable|\bptc\b|varistor|\besd\b|\btvs\b|sigorta'),
    ('Diyotlar', r'diode|schottky|zener|rectifier|diyot|1n4148|1n400\d|1n58\d\d|\bss[13]4\b|bat54'),
    ('Transistörler', r'transistor|transistör|mosfet|\bbjt\b|\bnpn\b|\bpnp\b|igbt|jfet|\b[np]-ch|\btrans\b|'
                      r'ao340\d|2n7002|bc54\d|bc55\d|2n2222|2n390\d|irlz|\birf\d'),
    ('Kondansatörler', r'capacitor|kondansatör|kapasitör|\bmlcc\b|\bcap\b|electrolytic|elektrolitik|tantal'),
    ('Dirençler', r'resistor|direnç|\bres\b|potentiometer|potansiyometre|trimmer|thick film|thin film'),
    ('Endüktörler', r'inductor|endüktör|bobin|ferrite|\bchoke|\bbead\b|fixed ind'),
    ('Sensörler', r'sensor|sensör|thermistor|\bntc\b|accelerometer|gyro|hall effect|bme280|bmp280|\bdht\d\d|mpu-?6050'),
    ('Ekranlar', r'display|\blcd\b|\boled\b|ekran|e-paper|7-segment'),
    ('Konnektörler', r'connector|konnektör|\bjak|header|socket|soket|terminal block|klemens|\bjst\b|usb[- ]?(type)?[- ]?c\b|'
                     r'receptacle|\bjack\b|\bidc\b|\bplug\b|\bfpc\b|\bffc\b|micro[- ]?usb|wire to board|board to board|\bconn\b'),
    ('Anahtar & Butonlar', r'switch|button|buton|anahtar|tactile|\btact\b'),
    ('Alet & Sarf', r'lehim|solder|desoldering|\bflux|kargaburun|pense|yan keski|cımbız|tweezer|tornavida|'
                    r'havya|multimetre|multimeter|sabitleyici|üçüncü el|helping hand|makaron|\bplier|\bwick\b'),
    ('Mekanik', r'\bvida|tutucu|holder|somun|\bpul\b|aralayıcı|standoff|spacer|\bscrew|\bnut\b|soğutucu|heatsink|'
                r'\bkutu|enclosure|organizer|kablo bağı|velkro|cırt'),
    ('Modüller', r'\bmodule\b|modül|breakout|development board|geliştirme kartı'),
    ('Entegreler', r'\bic\b|integrated|entegre|op[- ]?amp|amplifier|driver|interface|transceiver|\blogic\b|eeprom|'
                   r'flash|\bsram\b|memory|\badc\b|\bdac\b|comparator|\btimer\b|ne555|74hc|74lv|\bcd40|\bmcp\d|uart|'
                   r'\bi2c\b|rs-?485|ch340|cp210|ft232|buffer|multiplexer|shift register'),
]]

# BOM'larda referans harfinden kategori tahmini (R1 → direnç, C5 → kondansatör...).
DESIGNATOR_CATEGORIES = {
    'LED': "LED'ler", 'RN': 'Dirençler', 'FB': 'Endüktörler', 'SW': 'Anahtar & Butonlar', 'IC': 'Entegreler',
    'CN': 'Konnektörler', 'R': 'Dirençler', 'C': 'Kondansatörler', 'L': 'Endüktörler', 'D': 'Diyotlar',
    'Q': 'Transistörler', 'U': 'Entegreler', 'J': 'Konnektörler', 'P': 'Konnektörler', 'Y': 'Kristal & Osilatörler',
    'X': 'Kristal & Osilatörler', 'F': 'Koruma & Sigortalar', 'K': 'Röleler', 'S': 'Anahtar & Butonlar',
}


def classify(text, designators=()):
    if any(re.match(r'(RV|VR|POT)\d', d, re.I) for d in designators):
        return 'Dirençler'
    t = re.sub(r'[_:/\\|]+', ' ', (text or '').replace('İ', 'i').lower())
    for cat, rx in CATEGORY_RULES:
        if rx.search(t):
            return cat
    for d in designators:
        m = re.match(r'([A-Za-z]+)', d)
        if m and m.group(1).upper() in DESIGNATOR_CATEGORIES:
            return DESIGNATOR_CATEGORIES[m.group(1).upper()]
    return 'Diğer'


# ---------------------------------------------------------------- Değer / kılıf normalizasyonu

UNIT_FOR_CATEGORY = {'Dirençler': 'Ω', 'Kondansatörler': 'F', 'Endüktörler': 'H'}
MULTIPLIERS = {'p': 1e-12, 'P': 1e-12, 'n': 1e-9, 'N': 1e-9, 'u': 1e-6, 'U': 1e-6, 'µ': 1e-6, 'μ': 1e-6,
               'm': 1e-3, 'k': 1e3, 'K': 1e3, 'M': 1e6, 'G': 1e9, 'R': 1, 'r': 1, '': 1}
VALUE_RX = re.compile(r'(?<![\w.,])(\d+(?:[.,]\d+)?)\s?([pPnNuUµμmkKMGRr]?)(\d*)\s?'
                      r'(F|f|H|h|Ω|Ω|[oO][hH][mM][sS]?)?(?!\w)')
SI_PREFIXES = {
    'Ω': [(1e9, 'G'), (1e6, 'M'), (1e3, 'k'), (1, ''), (1e-3, 'm')],
    'F': [(1, ''), (1e-6, 'µ'), (1e-9, 'n'), (1e-12, 'p')],
    'H': [(1, ''), (1e-3, 'm'), (1e-6, 'µ'), (1e-9, 'n')],
}


def _value_from_match(m):
    num, mult, frac, unit = m.groups()
    s = num.replace(',', '.')
    if frac:  # 4k7, 1n5, 2R2 gösterimleri
        if '.' in s:
            return None
        s = s + '.' + frac
    try:
        x = float(s) * MULTIPLIERS[mult]
    except (ValueError, KeyError):
        return None
    u = None
    if unit:
        u = {'f': 'F', 'h': 'H', 'Ω': 'Ω'}.get(unit.lower(), unit.upper()[0])
        if unit.lower().startswith('ohm'):
            u = 'Ω'
    elif mult in ('R', 'r'):
        u = 'Ω'
    return x, u


def si_format(x, unit):
    if x <= 0:
        return '0' + unit
    prefixes = SI_PREFIXES[unit]
    f, p = prefixes[-1]
    for f2, p2 in prefixes:
        if x >= f2 * 0.9995:
            f, p = f2, p2
            break
    return f'{x / f:.3g}{p}{unit}'


def key(s):
    # O/0 karışıklığı (OCR, el yazısı kodlar) eşleşmeyi bozmasın diye O → 0
    return re.sub(r'[^A-Z0-9]', '', (s or '').upper()).replace('O', '0')


def normalize_value(raw, category, strict=False):
    """R/C/L için '10k', '10K Ohm', '10kΩ' → '10kΩ'; diğerleri için büyük harf alfanümerik anahtar.
    strict=True iken (açıklama metninden çıkarım) birimi açıkça yazılmış değerler aranır."""
    unit = UNIT_FOR_CATEGORY.get(category)
    if unit == 'Ω':
        raw = re.sub(r'(?<=\d[kKM])\s?[ABC](?![a-zA-Z])', '', raw or '')  # pot taper: 100kB → 100k
    if unit:
        for m in VALUE_RX.finditer(raw or ''):
            r = _value_from_match(m)
            if not r:
                continue
            x, u = r
            if u and u != unit:
                continue
            if strict and u != unit and not (unit == 'Ω' and m.group(2) in ('k', 'K', 'M', 'R')):
                continue  # açıklamada birimsiz değer sadece direnç için kabul (ör. "10K 1/4W Direnç")
            return si_format(x, unit)
        return '' if strict else key(raw)
    return '' if strict else key(raw)


PKG_RXS = [
    re.compile(r'(?<!\d)(01005|0201|0402|0603|0805|1206|1210|1812|2010|2512)(?!\d)'),
    re.compile(r'\b(SOT|SOD|SOIC|SOP|SSOP|TSSOP|HTSSOP|MSOP|QFN|VQFN|DFN|WSON|LQFP|TQFP|QFP|DIP|PDIP|LGA|BGA)'
               r'-?(\d+[A-Z]?)(?:-(\d+))?\b', re.I),
    re.compile(r'\b(TO|SC|DO)-(\d+[A-Z]*)(?:-(\d+))?\b', re.I),
    re.compile(r'\b(SMAF|SM[ABC]|MINIMELF|MELF)\b', re.I),
    re.compile(r'\b(\d+)-?(DIP|PDIP|SOIC|SOP|SSOP|TSSOP|MSOP|QFN|VQFN|DFN|LQFP|TQFP|QFP)\b', re.I),  # DigiKey: 8-DIP, 48LQFP
]


def normalize_package(raw, fallback=True):
    s = (raw or '').replace('_', ' ')
    best = None
    for rx in PKG_RXS:
        m = rx.search(s)
        if m and (best is None or m.start() < best.start()):
            best = m
    if best:
        g = best.groups()
        if len(g) == 1:
            return g[0].upper()
        if len(g) == 2:
            return f"{g[1].upper().replace('PDIP', 'DIP')}-{g[0]}"
        fam = g[0].upper().replace('PDIP', 'DIP')
        sub = g[2]
        if fam == 'SOT' and g[1] == '23' and sub == '3':
            sub = None
        return f'{fam}-{g[1].upper()}' + (f'-{sub}' if sub else '')
    if not fallback:
        return ''
    raw = (raw or '').strip()
    if ':' in raw:  # KiCad footprint: "Kütüphane:Footprint"
        raw = raw.split(':', 1)[1]
    return raw[:40]


# ---------------------------------------------------------------- Dosya okuma

def decode_text(data):
    encodings = ['utf-16', 'utf-8-sig'] if data[:2] in (b'\xff\xfe', b'\xfe\xff') else ['utf-8-sig']
    for enc in encodings:
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            pass
    return data.decode('cp1254', errors='replace')  # Türkçe Windows Excel çıktıları


def parse_delimited(text):
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    lines = [ln for ln in text.split('\n') if ln.strip()]
    if not lines:
        return []
    sample = '\n'.join(lines[:40])
    try:
        delim = csv.Sniffer().sniff(sample, delimiters='\t;,|').delimiter
    except csv.Error:
        delim = max('\t;,|', key=lambda d: sample.count(d))
    rows = list(csv.reader(io.StringIO('\n'.join(lines)), delimiter=delim))
    return [[c.strip() for c in r] for r in rows if any(c.strip() for c in r)]


def _col_index(ref):
    n = 0
    for ch in re.match(r'[A-Z]*', ref).group(0):
        n = n * 26 + ord(ch) - 64
    return n - 1


def read_xlsx(data):
    M = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
    R = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'
    z = zipfile.ZipFile(io.BytesIO(data))
    names = z.namelist()
    shared = []
    if 'xl/sharedStrings.xml' in names:
        for si in ET.fromstring(z.read('xl/sharedStrings.xml')).findall(M + 'si'):
            shared.append(''.join(t.text or '' for t in si.iter(M + 't')))
    sheet = None
    try:
        wb = ET.fromstring(z.read('xl/workbook.xml'))
        rid = wb.find(f'{M}sheets/{M}sheet').get(R + 'id')
        for rel in ET.fromstring(z.read('xl/_rels/workbook.xml.rels')):
            if rel.get('Id') == rid:
                t = rel.get('Target')
                sheet = t.lstrip('/') if t.startswith('/') else 'xl/' + t
    except Exception:
        pass
    if sheet not in names:
        sheets = sorted(n for n in names if n.startswith('xl/worksheets/sheet'))
        if not sheets:
            raise UserError('Excel dosyasında sayfa bulunamadı.')
        sheet = sheets[0]
    rows = []
    for row in ET.fromstring(z.read(sheet)).iter(M + 'row'):
        vals = {}
        nxt = 0
        for c in row.findall(M + 'c'):
            ref = c.get('r')
            idx = _col_index(ref) if ref else nxt
            nxt = idx + 1
            t = c.get('t')
            v = c.find(M + 'v')
            if t == 's':
                text = shared[int(v.text)] if v is not None and v.text else ''
            elif t == 'inlineStr':
                text = ''.join(x.text or '' for x in c.iter(M + 't'))
            else:
                text = v.text if v is not None and v.text else ''
                if re.fullmatch(r'-?\d+\.0', text):
                    text = text[:-2]
            vals[idx] = text.strip()
        if any(vals.values()):
            rows.append([vals.get(i, '') for i in range(max(vals) + 1)])
    return rows


class _TableParser(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows, self.row, self.cell = [], None, None

    def handle_starttag(self, tag, attrs):
        if tag == 'tr':
            self.row = []
        elif tag in ('td', 'th') and self.row is not None:
            self.cell = []
        elif tag == 'br' and self.cell is not None:
            self.cell.append(' ')

    def handle_endtag(self, tag):
        if tag in ('td', 'th') and self.cell is not None and self.row is not None:
            self.row.append(' '.join(''.join(self.cell).split()))
            self.cell = None
        elif tag == 'tr' and self.row is not None:
            if any(self.row):
                self.rows.append(self.row)
            self.row = None

    def handle_data(self, d):
        if self.cell is not None:
            self.cell.append(d)


# ---------------------------------------------------------------- Fatura fotoğrafı (OCR)

def is_image(data):
    return (data[:3] == b'\xff\xd8\xff' or data[:8] == b'\x89PNG\r\n\x1a\n' or data[:4] in (b'II*\x00', b'MM\x00*')
            or (data[4:8] == b'ftyp' and data[8:12] in (b'heic', b'heix', b'mif1', b'msf1', b'hevc', b'avif')))


def find_ocr_tool():
    for p in (os.path.join(BASE_DIR, 'ocr'), os.path.join(BASE_DIR, 'bin', 'ocr')):
        if os.access(p, os.X_OK):
            return p
    return None


def ocr_image(data):
    tool = find_ocr_tool()
    if not tool:
        raise UserError('Fotoğraf okuma aracı bulunamadı. Uygulamayı ./uygulamayi_derle.sh ile yeniden derleyin.')
    with tempfile.NamedTemporaryFile(suffix='.img', delete=False) as f:
        f.write(data)
        path = f.name
    try:
        r = subprocess.run([tool, path], capture_output=True, timeout=120)
    finally:
        os.unlink(path)
    if r.returncode != 0:
        raise UserError('Fotoğraf okunamadı: ' + r.stderr.decode('utf-8', 'replace').strip())
    return json.loads(r.stdout)


QTY_CELL_RX = re.compile(r'^\s*(\d+(?:[.,]\d+)?)\s*(adet|ad\.?|pcs?|pk|paket|mt|metre|m|kg|gr|takım|set)?\s*$', re.I)
QTY_STRICT_RX = re.compile(r'^\s*(\d+(?:[.,]\d+)?)\s*(adet|ad\.?|pcs)\s*$', re.I)
MERGED_QTY_RX = re.compile(r'^(.*\S)\s+(\d+)\s*(adet|ad\.?)(\s+[\d.,]+\s*TL.*)?$', re.I)
PRICE_RX = re.compile(r'\d[\d.]*,\d{2}\s*(TL|₺)', re.I)
TABLE_END_RX = re.compile(r'toplam|ettn|yalnız|iskonto|ara tutar|genel tutar|^not\b|iade bölümü', re.I)
NOISE_RX = re.compile(r'^\s*\d{1,3}\s*$|^[0-9A-F]{8}-[0-9A-F]{4}-|^%?\d+([.,]\d+)?\s*(TL|₺|%)?\s*$', re.I)
QTY_HEADER_RX = re.compile(r'^\s*(miktar[ıi]?|malın miktarı|adet|qty\.?|quantity)\s*$', re.I)
CODE_HEADER_RX = re.compile(r'^\s*((ürün|stok|malzeme|mal)\s*kodu?|kod|sku)\s*$', re.I)
DESC_HEADER_RX = re.compile(r'^\s*(açıklama|mal\s*/?\s*hizmet( cinsi)?|malın cinsi|ürün( adı)?|cinsi|description)\s*$', re.I)
ORIGIN_RX = re.compile(r'\s*/?\s*men[sşș]e[iİı]?\d*\s*:?\s*[A-Z]{0,3}(?![a-z])', re.I)


def ocr_rows(result):
    """OCR çıktısındaki her sayfadan ürün satırlarını çıkarıp [Açıklama, Adet, Ürün Kodu] tablosu yapar."""
    pages = result['pages'] if isinstance(result, dict) else [result]
    rows, errors = [], []
    for obs in pages:
        if not obs:
            continue
        try:
            rows += invoice_rows(obs)
        except UserError as e:
            errors.append(str(e))
    if not rows:
        raise UserError(errors[0] if errors else 'Belgede okunabilir metin bulunamadı.')
    out = [['Açıklama', 'Adet', 'Ürün Kodu']]
    for desc, qty, code in rows:
        desc = re.sub(r'\s*/\s*$', '', ORIGIN_RX.sub('', desc)).strip(' /')
        if desc:
            out.append([desc, qty, code])
    return out


def _pick_header(obs):
    """Adet sütun başlığını seçer; birden çok aday varsa (ör. altta "iade bölümü" tablosu) altında en çok
    adet hücresi olanı."""
    best, best_n = None, 0
    for h in (o for o in obs if QTY_HEADER_RX.match(o['text'])):
        n = sum(1 for o in obs if o['cy'] > h['cy'] and abs(o['cx'] - h['cx']) < 0.06 and QTY_CELL_RX.match(o['text']))
        if n > best_n:
            best, best_n = h, n
    return best


def invoice_rows(obs):
    """Fatura fotoğrafından/PDF sayfasından okunan metin kutularını (açıklama, adet, kod) satırlarına dönüştürür.
    Adet sütunundaki "5 Adet" gibi hücreler satır çapası olur; her satırın açıklaması, fotoğrafın eğikliği
    hesaba katılarak, aynı hizadaki sol taraftaki metinden alınır."""
    for o in obs:
        o['cx'], o['cy'] = o['x'] + o['w'] / 2, o['y'] + o['h'] / 2

    header = _pick_header(obs)
    top = header['cy'] + header['h'] / 2 if header else 0
    ends = [o['cy'] for o in obs if o['cy'] > top and TABLE_END_RX.search(o['text'])]
    bottom = min(ends) if ends else 1.0
    body = [o for o in obs if top < o['cy'] < bottom]
    hdr_row = [o for o in obs if header and abs(o['cy'] - header['cy']) < header['h'] * 1.5]
    code_h = next((o for o in hdr_row if CODE_HEADER_RX.match(o['text'])), None)
    desc_h = next((o for o in hdr_row if DESC_HEADER_RX.match(o['text'])), None)

    # Açıklama ile adedin aynı kutuya birleştiği durum: "10K Direnç 50 Adet"
    for o in list(body):
        m = MERGED_QTY_RX.match(o['text'])
        if m and (not header or o['x'] + o['w'] > header['x']):
            body.remove(o)
            frac = len(m.group(1)) / max(1, len(o['text']))
            body.append(dict(o, text=m.group(1), w=o['w'] * frac, cx=o['x'] + o['w'] * frac / 2))
            body.append(dict(o, text=f'{m.group(2)} Adet', x=o['x'] + o['w'] * frac, cx=o['x'] + o['w'] * (1 + frac) / 2))

    if header:
        anchors = [o for o in body if QTY_CELL_RX.match(o['text']) and abs(o['cx'] - header['cx']) < 0.06]
    else:
        anchors = [o for o in body if QTY_STRICT_RX.match(o['text'])]
    if not anchors:
        raise UserError('Belgede ürün tablosu bulunamadı. Fotoğrafsa, faturanın tamamı net ve düz görünecek '
                        'şekilde yeniden çekmeyi deneyin.')
    anchors.sort(key=lambda o: o['cy'])
    qx = min(a['x'] for a in anchors)
    def is_code(o):  # "Ürün Kodu" sütunu, açıklama sütunundan önce gelir
        return bool(code_h and desc_h and code_h['x'] < desc_h['x'] and o['cx'] < desc_h['x'] - 0.005)

    left = [o for o in body if o['x'] + o['w'] <= qx + 0.01 and o not in anchors
            and (is_code(o) or not NOISE_RX.match(o['text']))]
    # Adetin solunda aynı hizada metin yoksa liste düzenidir (ürün adı üstte, "N Adet" altında)
    same_row = sum(1 for a in anchors if any(abs(o['cy'] - a['cy']) < a['h'] for o in left))
    if not header and same_row < len(anchors) / 2:
        return stacked_rows(body, anchors)
    if not left:
        raise UserError('Belgede ürün açıklamaları okunamadı.')

    # Eğiklik: her çapanın en yakın soldaki metniyle yaptığı eğimin medyanı
    slopes = []
    for a in anchors:
        n = min(left, key=lambda o: abs(o['cy'] - a['cy']))
        if abs(a['cx'] - n['cx']) > 0.05:
            slopes.append((n['cy'] - a['cy']) / (n['cx'] - a['cx']))
    slopes.sort()
    slope = slopes[len(slopes) // 2] if slopes else 0.0
    gaps = sorted(b['cy'] - a['cy'] for a, b in zip(anchors, anchors[1:]))
    gap = gaps[len(gaps) // 2] if gaps else 0.03

    groups = {id(a): [] for a in anchors}
    for o in left:
        def dist(a):
            return abs(o['cy'] - slope * (o['cx'] - a['cx']) - a['cy'])
        a = min(anchors, key=dist)
        if dist(a) < gap * 0.9:
            groups[id(a)].append(o)

    rows = []
    for a in anchors:
        parts = sorted(groups[id(a)], key=lambda o: (round(o['cy'] - slope * o['cx'], 3), o['x']))
        desc = ' '.join(p['text'].strip() for p in parts if not is_code(p)).strip()
        code = ' '.join(p['text'].strip() for p in parts if is_code(p)).strip()
        if desc:
            rows.append((desc, a['text'].strip(), code))
    return rows


def stacked_rows(obs, anchors):
    """Web sitesi sipariş sayfası düzeni: her ürünün adı, altındaki "N Adet" satırıyla aynı hizadan başlar.
    Adetin hemen üstündeki, aynı sola hizalı satırlar (çok satırlı adlar dahil) ürün adı sayılır."""
    rows = []
    for a in anchors:
        above = sorted((o for o in obs if o['cy'] < a['cy'] and abs(o['x'] - a['x']) < 0.05 and o not in anchors
                        and not NOISE_RX.match(o['text']) and not PRICE_RX.search(o['text'])),
                       key=lambda o: -o['cy'])
        parts, ref = [], a
        for o in above:
            if ref['cy'] - o['cy'] > 2.6 * max(a['h'], o['h']):
                break
            parts.insert(0, o)
            ref = o
        desc = ' '.join(p['text'].strip() for p in parts)
        if desc:
            rows.append((desc, a['text'].strip(), ''))
    return rows


# ---------------------------------------------------------------- UBL-TR e-fatura / e-arşiv / e-irsaliye XML

UBL_LINE_TAGS = {'InvoiceLine': 'InvoicedQuantity', 'DespatchLine': 'DeliveredQuantity',
                 'ReceiptLine': 'ReceivedQuantity', 'CreditNoteLine': 'CreditedQuantity'}


def is_ubl(data):
    head = data[:4000].decode('utf-8', 'ignore')
    return head.lstrip('﻿ \r\n\t').startswith('<') and bool(
        re.search(r'urn:oasis:names:specification:ubl:schema:xsd:(Invoice|DespatchAdvice|CreditNote|ReceiptAdvice)', head))


def ubl_rows(data):
    """GİB UBL-TR XML'indeki her ürün satırından açıklama, adet, satıcı ürün kodu, MPN ve üreticiyi alır.
    XML'in içine gömülü PDF görünümü / imza gibi alanlar yok sayılır."""
    try:
        root = ET.fromstring(data)
    except ET.ParseError as e:
        raise UserError(f'XML dosyası okunamadı: {e}')

    def loc(e):
        return e.tag.rsplit('}', 1)[-1]

    def child(e, *path):
        for name in path:
            e = next((c for c in e if loc(c) == name), None) if e is not None else None
        return e

    def text(e, *path):
        e = child(e, *path)
        return (e.text or '').strip() if e is not None else ''

    rows = [['Ürün Kodu', 'Açıklama', 'Adet', 'MPN', 'Üretici', 'Kategori']]
    for line in root:
        qty_tag = UBL_LINE_TAGS.get(loc(line))
        if not qty_tag:
            continue
        item = child(line, 'Item')
        if item is None:
            continue
        code = text(item, 'SellersItemIdentification', 'ID')
        name, descr = text(item, 'Name'), text(item, 'Description')
        # Bazı satıcılar (ör. Robotistan) "Name" alanına ürün kodunu, asıl adı "Description"a yazar
        if descr and (not name or name == code or re.fullmatch(r'[\d\s-]+', name)):
            name = descr
        name = re.sub(r'\s*/\s*$', '', ORIGIN_RX.sub('', name)).strip(' /')
        mpn = text(item, 'ManufacturersItemIdentification', 'ID') or text(item, 'ModelName')
        brand = text(item, 'BrandName')
        cat = classify(name)
        if cat == 'Diğer':  # İngilizce anahtar kelimeler kategori için ek ipucu
            cat = classify(' '.join(k.text or '' for k in item if loc(k) == 'Keyword'))
        rows.append([code, name, text(line, qty_tag), mpn, brand, cat])
    if len(rows) == 1:
        raise UserError('XML dosyasında ürün satırı bulunamadı (UBL fatura/irsaliye bekleniyordu).')
    return rows


def load_table(payload):
    if payload.get('text'):
        return parse_delimited(payload['text'])
    if not payload.get('file_b64'):
        raise UserError('Dosya ya da yapıştırılmış tablo gerekli.')
    data = base64.b64decode(payload['file_b64'])
    if data[:4] == b'PK\x03\x04':
        try:
            z = zipfile.ZipFile(io.BytesIO(data))
            xml = [n for n in z.namelist() if n.lower().endswith('.xml') and not n.startswith(('xl/', '_rels/', '['))]
            if 'xl/workbook.xml' not in z.namelist() and xml:  # GİB portalından inen .zip içindeki UBL XML
                return ubl_rows(z.read(xml[0]))
            return read_xlsx(data)
        except (zipfile.BadZipFile, KeyError, ET.ParseError):
            raise UserError('Excel dosyası okunamadı.')
    if data[:8] == b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1':
        raise UserError('Eski .xls formatı desteklenmiyor. Dosyayı Excel/Numbers ile açıp .xlsx veya .csv olarak kaydedin.')
    if is_ubl(data):
        return ubl_rows(data)
    if is_image(data) or data[:5] == b'%PDF-':
        return ocr_rows(ocr_image(data))
    text = decode_text(data)
    if re.search(r'<table', text[:20000], re.I):
        p = _TableParser()
        p.feed(text)
        return p.rows
    return parse_delimited(text)


# ---------------------------------------------------------------- Sütun algılama

FIELDS = ['supplier_pn', 'mpn', 'manufacturer', 'description', 'quantity', 'package', 'value', 'designator', 'category']
FIELD_LABELS = {
    'mpn': 'Üretici parça no (MPN)', 'supplier_pn': 'Tedarikçi kodu', 'manufacturer': 'Üretici',
    'description': 'Açıklama', 'quantity': 'Adet', 'package': 'Kılıf / footprint', 'value': 'Değer',
    'designator': 'Referans (R1, C2…)', 'category': 'Kategori',
}
FIELD_SYNONYMS = {
    'supplier_pn': ['lcsc part number', 'lcsc part #', 'lcsc part', 'lcsc#', 'lcsc', 'jlcpcb part #', 'jlcpcb part',
                    'digi-key part number', 'digikey part number', 'digi-key part #', 'digi-key pn', 'dk part #',
                    'mouser #', 'mouser no', 'mouser part number', 'mouser part #', 'farnell part number',
                    'order code', 'supplier part number', 'supplier part', 'supplier pn',
                    'tedarikçi kodu', 'tedarikçi parça no', 'sipariş kodu', 'stok kodu', 'ürün kodu'],
    'mpn': ['manufacturer part number', 'manufacture part number', 'mfr part number', 'mfr. part #', 'mfr part #',
            'mfr. #', 'mfr #', 'mfr.#', 'mfg part number', 'mfg part #', 'mpn', 'manufacturer pn', 'manufacturer part',
            'üretici parça no', 'üretici parça numarası', 'üretici kodu', 'part number', 'part no', 'part #',
            'partnumber', 'parça no', 'parça numarası'],
    'manufacturer': ['manufacturer', 'manufacture', 'mfr', 'mfr.', 'mfg', 'brand', 'vendor', 'üretici', 'marka'],
    'description': ['description', 'product description', 'açıklama', 'tanım', 'ürün açıklaması', 'ürün adı',
                    'product name', 'desc'],
    'quantity': ['order qty.', 'order qty', 'quantity', 'qty', 'qty.', 'quantity shipped', 'shipped qty',
                 'qty shipped', 'ordered qty', 'ordered quantity', 'adet', 'miktar', 'sipariş adedi', 'quantity per pcb'],
    'package': ['package', 'footprint', 'case', 'case/package', 'package / case', 'supplier device package',
                'kılıf', 'paket'],
    'value': ['value', 'değer', 'comment', 'val', 'name'],
    'designator': ['designator', 'designators', 'reference', 'references', 'ref', 'refs', 'ref des', 'refdes',
                   'reference designator', 'referans'],
    'category': ['category', 'kategori'],
}


def _norm_header(h):
    return re.sub(r'\s+', ' ', (h or '').replace('﻿', '').strip().lower())


def guess_mapping(headers):
    hs = [_norm_header(h) for h in headers]
    mapping = {f: -1 for f in FIELDS}
    used = set()
    for f in FIELDS:  # birebir eşleşme
        for syn in FIELD_SYNONYMS[f]:
            hit = next((i for i, h in enumerate(hs) if i not in used and h == syn), None)
            if hit is not None:
                mapping[f] = hit
                used.add(hit)
                break
    for f in FIELDS:  # içerir eşleşmesi
        if mapping[f] >= 0:
            continue
        for syn in FIELD_SYNONYMS[f]:
            if len(syn) < 5:
                continue
            hit = next((i for i, h in enumerate(hs) if i not in used and syn in h
                        and not re.search(r'customer|müşteri|price|fiyat|\bmin\b|\bext', h)), None)
            if hit is not None:
                mapping[f] = hit
                used.add(hit)
                break
    # DigiKey: "Part Number" sütunu DigiKey kodudur, MPN ayrı sütundadır.
    if mapping['mpn'] >= 0 and mapping['supplier_pn'] < 0:
        hit = next((i for i, h in enumerate(hs) if i not in used and h in ('part number', 'part #')), None)
        if hit is not None:
            mapping['supplier_pn'] = hit
    return mapping


def detect_header(rows):
    best, best_n = -1, 1
    for i, r in enumerate(rows[:25]):
        n = sum(1 for v in guess_mapping(r).values() if v >= 0)
        if n > best_n:
            best, best_n = i, n
    return best


def parse_qty(s):
    s = (s or '').strip()
    m = re.search(r'\d[\d.,\s]*', s)
    if not m:
        return 0
    n = re.sub(r'\s', '', m.group(0)).rstrip('.,')
    if re.fullmatch(r'\d{1,3}([.,]\d{3})+', n):
        return int(re.sub(r'[.,]', '', n))
    try:
        return max(0, int(round(float(n.replace(',', '.')))))
    except ValueError:
        return 0


def split_designators(s):
    out = []
    for tok in re.split(r'[,;\s]+', s or ''):
        if not tok:
            continue
        m = re.fullmatch(r'([A-Za-z]+)(\d+)-(?:\1)?(\d+)', tok)
        if m and 0 < int(m.group(3)) - int(m.group(2)) <= 300:
            out += [f'{m.group(1)}{i}' for i in range(int(m.group(2)), int(m.group(3)) + 1)]
        else:
            out.append(tok)
    return out


SERVICE_RX = re.compile(r'\s*(kargo|nakliye|gönderim|teslimat|hizmet bedeli|kapıda ödeme|shipping|freight|handling)',
                        re.I)
PACK_RX = re.compile(r'(?:paket[iı]?|set[iİ]?|takım[ıi]?|[-–(x×])\s*[-–:]?\s*(\d+)\s*(?:adet|pcs|pieces)\b', re.I)
MPN_TOKEN_RX = re.compile(r'(?<![\w.])(\d?[A-Z]{1,6}[0-9O]{2,}[A-Z0-9O]*(?:[-/][A-Z0-9]+)*)(?![\w.])')


def mpn_from_text(text):
    """Açıklamadaki parça kodunu bulur: "TL072CP DIP-8 OpAmp Entegresi" → "TL072CP"."""
    for m in MPN_TOKEN_RX.finditer(text or ''):
        tok = m.group(1)
        if len(tok) < 5 or normalize_package(tok, fallback=False):
            continue
        # OCR'nin rakam yanındaki 0'ı O okuması: TLO72CP → TL072CP
        return re.sub(r'(?<=\d)O|O(?=\d)', '0', tok)
    return ''


DNP_RX = re.compile(r'\b(dnp|dnf|dni|do not (place|populate|fit)|not (fitted|populated|mounted)|takılmayacak)\b', re.I)


def analyze(kind, rows, mapping=None, header_row=None):
    if header_row is None:
        header_row = detect_header(rows)
    width = max((len(r) for r in rows), default=0)
    if header_row >= 0 and header_row < len(rows):
        headers = rows[header_row] + [''] * (width - len(rows[header_row]))
    else:
        header_row = -1
        headers = [''] * width
    headers = [h or f'Sütun {i + 1}' for i, h in enumerate(headers)]
    if not mapping:
        mapping = guess_mapping(headers) if header_row >= 0 else {f: -1 for f in FIELDS}
    mapping = {f: int(mapping.get(f, -1)) for f in FIELDS}

    items = []
    for row in rows[header_row + 1:]:
        def get(f):
            i = mapping[f]
            return row[i].strip() if 0 <= i < len(row) else ''

        mpn, spn, mfr, desc = get('mpn'), get('supplier_pn'), get('manufacturer'), get('description')
        val_raw, pkg_raw, des_raw, cat_raw = get('value'), get('package'), get('designator'), get('category')
        if not any([mpn, spn, desc, val_raw]):
            continue
        if re.match(r'(sub)?total|toplam|ara toplam|genel toplam', (mpn or spn or desc).lower()):
            continue
        designators = split_designators(des_raw)
        qty_raw = get('quantity')
        if qty_raw:
            qty = parse_qty(qty_raw)
        elif designators:
            qty = len(designators)
        else:
            qty = 1 if kind == 'bom' else 0

        cat_exact = next((c for c in CATEGORIES if c.lower() == cat_raw.lower()), None)
        category = cat_exact or classify(' '.join([cat_raw, desc, mpn, val_raw, pkg_raw]), designators)

        value = val_raw
        if category in UNIT_FOR_CATEGORY:
            value = normalize_value(val_raw, category, strict=False) if val_raw else ''
            if value and not re.search(r'[ΩFH]$', value):
                value = val_raw  # anlaşılamayan değer (ör. "DNP"), olduğu gibi bırak
            if not value:
                value = normalize_value(desc, category, strict=True)
        package = normalize_package(pkg_raw) if pkg_raw else normalize_package(desc, fallback=False)
        if not mpn and desc and category not in UNIT_FOR_CATEGORY:
            mpn = mpn_from_text(desc)
        pack = 1
        if kind == 'order' and qty:
            m = PACK_RX.search(desc)
            if m and int(m.group(1)) > 1:  # "Kondansatör Paketi - 10 Adet" × 1 → 10 adet
                pack = int(m.group(1))
                qty *= pack

        skip = ''
        if kind == 'bom' and (DNP_RX.search(' '.join(row)) or qty == 0):
            skip = 'DNP / takılmayacak'
        elif kind == 'order' and SERVICE_RX.match(desc or mpn):
            skip = 'Kargo / hizmet'
        elif kind == 'order' and qty == 0:
            skip = 'Adet okunamadı'

        items.append({
            'mpn': mpn, 'supplier_pn': spn, 'manufacturer': mfr, 'description': desc,
            'category': category, 'value': value, 'package': package, 'qty': qty,
            'designators': designators, 'skip_reason': skip, 'pack': pack,
            'attrs': passive_attrs(' '.join([pkg_raw, desc, val_raw, cat_raw, mpn]), category, designators),
        })
    return {'header_row': header_row, 'headers': headers, 'mapping': mapping, 'items': items}


# ---------------------------------------------------------------- Eşleştirme

# Pasif parçalarda (direnç / kondansatör / bobin) kılıf adı birebir karşılaştırılmaz; bunun yerine
# montaj tipi (THT/SMD), kondansatör türü, potansiyometre olup olmadığı ve voltaj karşılaştırılır.
SMD_RX = re.compile(r'(?<!\d)(01005|0201|0402|0603|0805|1206|1210|1812|2010|2512)(?!\d)|\bsmd\b|\bsmt\b|\bchip\b|'
                    r'\bmlcc\b|\bmelf\b|\bsm[abc]\b|\bsod-?[123]\d\d\b|\bsot-?\d|\bcp elec\b|\bsurface mount', re.I)
THT_RX = re.compile(r'\btht\b|axial|aksiyel|radial|radyal|through[- ]?hole|\bdip\b|\bdip-?\d|\bto-?92|\bto-?220|'
                    r'\bdisc\b|\bc rect\b|\bdin020\d|\b1/[248]\s?w\b|\b[12]\s?w\b|\bdo-?(35|41|15)\b', re.I)
PITCH_RX = re.compile(r'(?<![\d.])(2\.54|2\.5|5\.08|5|7\.5|10|15)\s?mm\b', re.I)  # kondansatör/direnç bacak aralığı
CAP_TYPES = [
    ('elektrolitik', re.compile(r'\bcp\b|elektrolitik|electrolytic|elco|elko|polarized|polarize|alüminyum|aluminum', re.I)),
    ('tantal', re.compile(r'tantal', re.I)),
    ('film', re.compile(r'polyester|polyprop|polipropilen|\bfilm\b|\bmk[tps]\d?\b|\bfk[ps]\d?\b|\bc rect\b|\bwima\b|'
                        r'mylar|\bbox\b', re.I)),
    ('seramik', re.compile(r'seramik|ceramic|\bmlcc\b|\bc disc\b|\bdisc\b|\bx[57][rs]\b|\bc0g\b|\bnp0\b|\by5v\b', re.I)),
]
POT_RX = re.compile(r'potan|potentiometer|\bpot\b|trimmer|trimpot|ayarlı direnç|^\s*\d+(\.\d+)?\s?[kKM]\s?[ABC]\s*$', re.I)
VOLT_RX = re.compile(r'(?<![\w.])(\d+(?:[.,]\d+)?)\s?v(?:dc)?(?!\w)', re.I)
POLAR = {'elektrolitik', 'tantal'}


def passive_attrs(text, category, designators=()):
    t = re.sub(r'[_:]+', ' ', text or '')
    a = {'mount': '', 'ctype': '', 'pot': False, 'volt': 0.0}
    if category not in UNIT_FOR_CATEGORY:
        return a
    if SMD_RX.search(t):
        a['mount'] = 'SMD'
    elif THT_RX.search(t) or PITCH_RX.search(t):
        a['mount'] = 'THT'
    if category == 'Kondansatörler':
        a['ctype'] = next((name for name, rx in CAP_TYPES if rx.search(t)), '')
        m = VOLT_RX.search(t)
        a['volt'] = float(m.group(1).replace(',', '.')) if m else 0.0
        # Montaj belirtilmemişse: film, elektrolitik ve (MLCC olmayan) seramik kondansatörler pratikte THT'dir
        if not a['mount'] and a['ctype'] in ('film', 'elektrolitik', 'seramik'):
            a['mount'] = 'THT'
        # Türü yazmayan çip boy (0402, 0603…) kondansatörler MLCC, yani seramiktir
        if not a['ctype'] and re.search(r'(?<!\d)(0201|0402|0603|0805|1206|1210)(?!\d)', t):
            a['ctype'] = 'seramik'
    if category == 'Dirençler':
        a['pot'] = bool(POT_RX.search(t)) or any(re.match(r'(RV|VR|POT)\d', d, re.I) for d in designators)
    return a


def comp_attrs(c):
    text = ' '.join([c['package'], c['description'], c['value'], c['notes'], c['mpn']])
    return passive_attrs(text, c['category'])


def comp_norms(c):
    cat = c['category']
    v = normalize_value(c['value'], cat) if c['value'] else normalize_value(c['description'], cat, strict=True)
    p = normalize_package(c['package'], fallback=True) if c['package'] else normalize_package(c['description'], False)
    return v, p


def value_number(canonical):
    m = VALUE_RX.search(canonical or '')
    r = _value_from_match(m) if m else None
    return r[0] if r else None


def passive_match(item, ia, c):
    """Pasif parça için (puan, gerekçe) döner; uyumsuzsa None."""
    c_vn, c_pkg = comp_norms(c)
    if not c_vn:
        return None
    i_vn = item['_vn']
    exact = c_vn == i_vn
    if not exact:
        x, y = value_number(i_vn), value_number(c_vn)
        if not (x and y and 0.85 <= y / x <= 1.18):  # komşu standart değerler (ör. 250p ↔ 220p)
            return None
    ca = comp_attrs(c)
    if ia['pot'] != ca['pot']:
        return None
    if ia['mount'] and ca['mount'] and ia['mount'] != ca['mount']:
        return None
    alt = ''
    # "emin": montaj tipi iki tarafta da biliniyor ve aynı; kondansatörde tür de biliniyor ve aynı
    sure = bool(ia['mount'] and ca['mount'])
    if item['category'] == 'Kondansatörler':
        if ia['ctype'] and ca['ctype'] and ia['ctype'] != ca['ctype']:
            if (ia['ctype'] in POLAR) != (ca['ctype'] in POLAR):
                return None  # elektrolitik yerine seramik/film önerilmez (ya da tersi)
            alt = f"tür farklı ({ca['ctype']})"
        sure = sure and bool(ia['ctype']) and ia['ctype'] == ca['ctype']

    if not exact:
        score, why = 25, f'yakın değer ({c_vn})'
    elif alt:
        score, why = 40, f'değer aynı, {alt}'
    elif sure:
        tags = [t for t in (ia['mount'], ia['ctype']) if t]
        score, why = 85, 'değer + ' + ' + '.join(tags) + ' aynı'
        if item['_pkg'] and c_pkg and key(item['_pkg']) == key(c_pkg):
            score, why = 90, why + ', kılıf da aynı'
    else:
        score, why = 65, 'değer aynı (montaj/tür belirsiz — kontrol edin)'
    if ia['volt'] and ca['volt'] and ca['volt'] < ia['volt']:
        score, why = min(score, 45), why + f" — ⚠ voltaj düşük ({ca['volt']:g}V < {ia['volt']:g}V)"
    return score, why


def find_candidates(item, comps):
    i_mpn, i_spn, i_val = key(item['mpn']), key(item['supplier_pn']), key(item['value'])
    passive = item['category'] in UNIT_FOR_CATEGORY
    item['_vn'] = normalize_value(item['value'], item['category']) if item['value'] else ''
    item['_pkg'] = normalize_package(item['package'], fallback=True) if item['package'] else ''
    ia = item.get('attrs') or passive_attrs(' '.join([item['package'], item['description'], item['value']]),
                                            item['category'], item.get('designators', ()))
    out = []
    for c in comps:
        c_mpn, c_spn = key(c['mpn']), key(c['supplier_pn'])
        score, why = 0, ''
        if i_mpn and i_mpn == c_mpn:
            score, why = 100, 'MPN aynı'
        elif i_spn and i_spn == c_spn:
            score, why = 95, 'tedarikçi kodu aynı'
        elif i_val and len(i_val) > 3 and i_val == c_mpn:
            score, why = 85, 'değer = MPN'
        elif i_mpn and i_mpn == key(c['value']):
            score, why = 85, 'MPN = değer'
        elif passive and item['_vn'] and c['category'] == item['category']:
            r = passive_match(item, ia, c)
            if r:
                score, why = r
        elif i_val and len(i_val) >= 6 and c_mpn and _wildcard_match(i_val, c_mpn):
            score, why = 75, 'MPN benzer'
        elif i_val and len(i_val) >= 4 and re.search(r'\d', i_val) and c_mpn.startswith(i_val):
            score, why = 75, f'MPN başı aynı ({c["mpn"]})'  # TL072 ↔ TL072CP, 2N3904 ↔ 2N3904BU
        if not score and c['category'] == item['category'] and not passive:
            c_pkg = comp_norms(c)[1]
            if len(c_mpn) >= 6 and c_mpn[:max(6, len(c_mpn) - 4)] in key(item['package']):
                score, why = 65, 'footprint adında MPN geçiyor'
            elif re.search(r'\d', item['value']) and len(i_val) >= 2 and \
                    re.search(r'(?<!\w)' + re.escape(item['value'].lower()) + r'(?!\w)', c['description'].lower()):
                score, why = 55, 'değer açıklamada geçiyor'
            elif item['_pkg'] and c_pkg and key(item['_pkg']) == key(c_pkg):
                score, why = 40, 'aynı kategori ve kılıf'
        if score:
            out.append({'id': c['id'], 'score': score, 'reason': why})
    item.pop('_vn'); item.pop('_pkg')
    out.sort(key=lambda x: -x['score'])
    return out[:8]


def _wildcard_match(pattern, mpn):
    """KiCad sembol adları 'STM32F103C8Tx' gibi x joker karakteri içerir; MPN'in başı bu desene uymalı."""
    if 'X' not in pattern[4:] or len(mpn) < len(pattern):
        return False
    return all(p == m or (p == 'X' and i >= 4) for i, (p, m) in enumerate(zip(pattern, mpn)))


def attach_matches(items, comps):
    for it in items:
        cands = find_candidates(it, comps)
        it['candidates'] = cands
        it['match_id'] = cands[0]['id'] if cands and cands[0]['score'] >= 55 else None
        if not it['match_id']:
            it['confidence'] = ''
        elif cands[0]['score'] >= 80 and (len(cands) == 1 or cands[1]['score'] < cands[0]['score']):
            it['confidence'] = 'high'
        else:
            it['confidence'] = 'low'


# ---------------------------------------------------------------- Veritabanı

SCHEMA = """
CREATE TABLE IF NOT EXISTS components(
  id INTEGER PRIMARY KEY,
  mpn TEXT NOT NULL DEFAULT '', supplier_pn TEXT NOT NULL DEFAULT '', manufacturer TEXT NOT NULL DEFAULT '',
  description TEXT NOT NULL DEFAULT '', category TEXT NOT NULL DEFAULT 'Diğer', value TEXT NOT NULL DEFAULT '',
  package TEXT NOT NULL DEFAULT '', quantity INTEGER NOT NULL DEFAULT 0, min_qty INTEGER NOT NULL DEFAULT 0,
  location TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT '', created_at TEXT, updated_at TEXT);
CREATE TABLE IF NOT EXISTS batches(
  id INTEGER PRIMARY KEY, kind TEXT NOT NULL, name TEXT NOT NULL DEFAULT '', multiplier INTEGER NOT NULL DEFAULT 1,
  info TEXT NOT NULL DEFAULT '', undone INTEGER NOT NULL DEFAULT 0, created_at TEXT);
CREATE TABLE IF NOT EXISTS transactions(
  id INTEGER PRIMARY KEY, batch_id INTEGER NOT NULL, component_id INTEGER NOT NULL, delta INTEGER NOT NULL,
  label TEXT NOT NULL DEFAULT '', note TEXT NOT NULL DEFAULT '', created_at TEXT);
CREATE INDEX IF NOT EXISTS tx_batch ON transactions(batch_id);
"""
TEXT_FIELDS = ['mpn', 'supplier_pn', 'manufacturer', 'description', 'category', 'value', 'package', 'location', 'notes']


def connect():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    return db


def init_db():
    with connect() as db:
        db.executescript(SCHEMA)


def comp_label(c):
    if c['mpn']:
        return c['mpn']
    vp = ' '.join(x for x in (c['value'], c['package']) if x)
    return vp or c['supplier_pn'] or (c['description'] or '')[:50] or f"#{c['id']}"


def clean_fields(data):
    out = {}
    for f in TEXT_FIELDS:
        if f in data:
            out[f] = str(data.get(f) or '').strip()[:500]
    if 'category' in out and not out['category']:
        out['category'] = 'Diğer'
    for f in ('quantity', 'min_qty'):
        if f in data:
            try:
                out[f] = max(0, int(data.get(f) or 0))
            except (TypeError, ValueError):
                raise UserError('Adet sayı olmalı.')
    return out


def get_comp(db, cid):
    row = db.execute('SELECT * FROM components WHERE id=?', (cid,)).fetchone()
    if not row:
        raise UserError('Parça bulunamadı (silinmiş olabilir).')
    return row


def insert_component(db, data):
    f = clean_fields(data)
    f.pop('quantity', None)
    if not f.get('category'):
        f['category'] = classify(' '.join([f.get('description', ''), f.get('mpn', ''), f.get('value', '')]))
    if not any(f.get(k) for k in ('mpn', 'supplier_pn', 'value', 'description')):
        raise UserError('En azından MPN, değer veya açıklama girilmeli.')
    cols = list(f) + ['quantity', 'created_at', 'updated_at']
    vals = list(f.values()) + [0, now(), now()]
    cur = db.execute(f"INSERT INTO components({','.join(cols)}) VALUES({','.join('?' * len(cols))})", vals)
    return cur.lastrowid


def new_batch(db, kind, name, multiplier=1, info=''):
    return db.execute('INSERT INTO batches(kind, name, multiplier, info, created_at) VALUES(?,?,?,?,?)',
                      (kind, name, multiplier, info, now())).lastrowid


def apply_delta(db, batch_id, cid, delta, note=''):
    c = get_comp(db, cid)
    newq = max(0, c['quantity'] + int(delta))
    actual = newq - c['quantity']
    if actual:
        db.execute('UPDATE components SET quantity=?, updated_at=? WHERE id=?', (newq, now(), cid))
        db.execute('INSERT INTO transactions(batch_id, component_id, delta, label, note, created_at) VALUES(?,?,?,?,?,?)',
                   (batch_id, cid, actual, comp_label(c), note, now()))
    return actual


def drop_batch_if_empty(db, bid):
    if not db.execute('SELECT 1 FROM transactions WHERE batch_id=?', (bid,)).fetchone():
        db.execute('DELETE FROM batches WHERE id=?', (bid,))
        return True
    return False


# ---------------------------------------------------------------- API işlemleri

def api_components(db, _):
    comps = [dict(r) for r in db.execute('SELECT * FROM components ORDER BY category, mpn, value, description')]
    extra = sorted({c['category'] for c in comps} - set(CATEGORIES))
    return {'components': comps, 'categories': CATEGORIES[:-1] + extra + ['Diğer']}


def api_create(db, data):
    with DB_LOCK, db:
        cid = insert_component(db, data)
        qty = clean_fields(data).get('quantity', 0)
        if qty:
            bid = new_batch(db, 'manuel', 'Yeni parça')
            apply_delta(db, bid, cid, qty, 'İlk stok')
    return {'id': cid}


def api_update(db, cid, data):
    with DB_LOCK, db:
        c = get_comp(db, cid)
        f = clean_fields(data)
        qty = f.pop('quantity', None)
        f.pop('id', None)
        if f:
            sets = ', '.join(f'{k}=?' for k in f)
            db.execute(f'UPDATE components SET {sets}, updated_at=? WHERE id=?', list(f.values()) + [now(), cid])
        if qty is not None and qty != c['quantity']:
            bid = new_batch(db, 'duzeltme', 'Stok düzeltme')
            apply_delta(db, bid, cid, qty - c['quantity'], 'Elle düzeltme')
    return {'ok': True}


def api_delete(db, cid):
    with DB_LOCK, db:
        get_comp(db, cid)
        db.execute('DELETE FROM components WHERE id=?', (cid,))
    return {'ok': True}


def api_adjust(db, cid, data):
    try:
        delta = int(data.get('delta') or 0)
    except (TypeError, ValueError):
        raise UserError('Miktar sayı olmalı.')
    if not delta:
        raise UserError('Miktar 0 olamaz.')
    note = str(data.get('note') or '').strip()[:200]
    with DB_LOCK, db:
        bid = new_batch(db, 'manuel', note or ('Elle ekleme' if delta > 0 else 'Elle düşme'))
        actual = apply_delta(db, bid, cid, delta, note)
        if drop_batch_if_empty(db, bid):
            raise UserError('Stok zaten 0, düşülecek parça yok.')
    return {'delta': actual}


def api_preview(db, data):
    kind = data.get('kind')
    if kind not in ('order', 'bom'):
        raise UserError('Geçersiz tür.')
    rows = load_table(data)
    if not rows:
        raise UserError('Dosyada okunabilir tablo bulunamadı.')
    hr = data.get('header_row')
    res = analyze(kind, rows, data.get('mapping'), None if hr is None else int(hr))
    comps = [dict(r) for r in db.execute('SELECT * FROM components')]
    attach_matches(res['items'], comps)
    res['fields'] = FIELD_LABELS
    return res


def api_commit(db, data):
    kind = data.get('kind')
    items = data.get('items') or []
    name = str(data.get('name') or '').strip()[:200]
    with DB_LOCK, db:
        if kind == 'order':
            bid = new_batch(db, 'siparis', name or 'Sipariş')
            created = lines = 0
            new_ids = {}  # aynı yeni parça birden çok faturada geçiyorsa tek kayıt açılır
            for it in items:
                act = it.get('action')
                qty = parse_qty(str(it.get('qty', 0)))
                if act == 'new':
                    k = next(((f, key(it.get(f))) for f in ('supplier_pn', 'mpn', 'description') if key(it.get(f))),
                             None)
                    if k and k in new_ids:
                        cid = new_ids[k]
                    else:
                        cid = insert_component(db, it)
                        created += 1
                        if k:
                            new_ids[k] = cid
                elif act == 'match':
                    cid = int(it['component_id'])
                    c = get_comp(db, cid)
                    fill = {k: v for k, v in clean_fields(it).items()
                            if k in ('mpn', 'supplier_pn', 'manufacturer', 'description', 'value', 'package')
                            and v and not c[k]}
                    if fill:
                        db.execute(f"UPDATE components SET {', '.join(f'{k}=?' for k in fill)} WHERE id=?",
                                   list(fill.values()) + [cid])
                else:
                    continue
                if qty and apply_delta(db, bid, cid, qty, 'Sipariş'):
                    lines += 1
            drop_batch_if_empty(db, bid)
            return {'lines': lines, 'created': created}

        if kind == 'bom':
            mult = max(1, int(data.get('multiplier') or 1))
            need, labels, shortages = {}, {}, []
            for it in items:
                q = parse_qty(str(it.get('qty', 0))) * mult
                if it.get('action') == 'match' and q:
                    cid = int(it['component_id'])
                    need[cid] = need.get(cid, 0) + q
                elif it.get('action') == 'none' and q:
                    shortages.append({'label': it.get('label') or '?', 'need': q, 'have': 0, 'short': q})
            bid = new_batch(db, 'proje', name or 'Proje', mult)
            used = 0
            for cid, n in need.items():
                c = get_comp(db, cid)
                taken = -apply_delta(db, bid, cid, -n, 'Proje')
                used += taken
                if n > taken:
                    shortages.insert(0, {'label': comp_label(c), 'need': n, 'have': taken, 'short': n - taken})
            db.execute('UPDATE batches SET info=? WHERE id=?',
                       (json.dumps({'shortages': shortages}, ensure_ascii=False), bid))
            if not need and not shortages:
                db.execute('DELETE FROM batches WHERE id=?', (bid,))
            return {'used': used, 'shortages': shortages}
    raise UserError('Geçersiz tür.')


def api_batches(db, _):
    batches = [dict(b) for b in db.execute('SELECT * FROM batches ORDER BY id DESC LIMIT 300')]
    if batches:
        ids = [b['id'] for b in batches]
        lines = {}
        for t in db.execute(f"SELECT * FROM transactions WHERE batch_id IN ({','.join('?' * len(ids))}) ORDER BY id",
                            ids):
            lines.setdefault(t['batch_id'], []).append({'label': t['label'], 'delta': t['delta'],
                                                        'component_id': t['component_id']})
        for b in batches:
            b['lines'] = lines.get(b['id'], [])
            b['info'] = json.loads(b['info']) if b['info'] else {}
    return {'batches': batches}


def api_undo(db, bid):
    with DB_LOCK, db:
        b = db.execute('SELECT * FROM batches WHERE id=?', (bid,)).fetchone()
        if not b:
            raise UserError('Kayıt bulunamadı.')
        if b['undone']:
            raise UserError('Bu işlem zaten geri alınmış.')
        for t in db.execute('SELECT * FROM transactions WHERE batch_id=?', (bid,)).fetchall():
            c = db.execute('SELECT quantity FROM components WHERE id=?', (t['component_id'],)).fetchone()
            if c:
                db.execute('UPDATE components SET quantity=?, updated_at=? WHERE id=?',
                           (max(0, c['quantity'] - t['delta']), now(), t['component_id']))
        db.execute('UPDATE batches SET undone=1 WHERE id=?', (bid,))
    return {'ok': True}


def export_csv(db):
    out = io.StringIO()
    w = csv.writer(out, delimiter=';')
    w.writerow(['Kategori', 'MPN', 'Tedarikçi Kodu', 'Üretici', 'Değer', 'Kılıf', 'Açıklama', 'Adet', 'Min. Adet',
                'Konum', 'Notlar'])
    for c in db.execute('SELECT * FROM components ORDER BY category, mpn, value'):
        w.writerow([c['category'], c['mpn'], c['supplier_pn'], c['manufacturer'], c['value'], c['package'],
                    c['description'], c['quantity'], c['min_qty'], c['location'], c['notes']])
    return ('﻿' + out.getvalue()).encode('utf-8')


# ---------------------------------------------------------------- HTTP sunucu

STATIC = {'/': ('index.html', 'text/html'), '/app.js': ('app.js', 'text/javascript'),
          '/style.css': ('style.css', 'text/css')}
ROUTES = [
    ('GET', r'/api/components', lambda db, m, d: api_components(db, d)),
    ('POST', r'/api/components', lambda db, m, d: api_create(db, d)),
    ('PUT', r'/api/components/(\d+)', lambda db, m, d: api_update(db, int(m[1]), d)),
    ('DELETE', r'/api/components/(\d+)', lambda db, m, d: api_delete(db, int(m[1]))),
    ('POST', r'/api/components/(\d+)/adjust', lambda db, m, d: api_adjust(db, int(m[1]), d)),
    ('POST', r'/api/import/preview', lambda db, m, d: api_preview(db, d)),
    ('POST', r'/api/import/commit', lambda db, m, d: api_commit(db, d)),
    ('GET', r'/api/batches', lambda db, m, d: api_batches(db, d)),
    ('POST', r'/api/batches/(\d+)/undo', lambda db, m, d: api_undo(db, int(m[1]))),
]


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send(self, code, body, ctype, extra=None):
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False).encode('utf-8'), 'application/json; charset=utf-8')

    def _handle(self, method):
        path = urlparse(self.path).path
        if method == 'GET' and path in STATIC:
            fname, ctype = STATIC[path]
            with open(os.path.join(WEB_DIR, fname), 'rb') as fh:
                return self._send(200, fh.read(), ctype + '; charset=utf-8')
        if method == 'GET' and path == '/api/export.csv':
            with connect() as db:
                body = export_csv(db)
            fname = f"stok_{datetime.now():%Y%m%d}.csv"
            return self._send(200, body, 'text/csv; charset=utf-8',
                              {'Content-Disposition': f'attachment; filename="{fname}"'})
        for meth, rx, fn in ROUTES:
            m = re.fullmatch(rx, path)
            if m and meth == method:
                try:
                    n = int(self.headers.get('Content-Length') or 0)
                    data = json.loads(self.rfile.read(n) or b'{}') if n else {}
                    db = connect()
                    try:
                        return self._json(fn(db, m, data))
                    finally:
                        db.close()
                except UserError as e:
                    return self._json({'error': str(e)}, 400)
                except Exception as e:  # beklenmeyen hata: sunucuyu düşürme
                    import traceback
                    traceback.print_exc()
                    return self._json({'error': f'Beklenmeyen hata: {e}'}, 500)
        self._json({'error': 'Bulunamadı'}, 404)

    def do_GET(self):
        self._handle('GET')

    def do_POST(self):
        self._handle('POST')

    def do_PUT(self):
        self._handle('PUT')

    def do_DELETE(self):
        self._handle('DELETE')


def main():
    init_db()
    server = None
    for port in range(PORT, PORT + 20):
        try:
            server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
            break
        except OSError:
            continue
    if not server:
        sys.exit('Boş port bulunamadı.')
    url = f'http://127.0.0.1:{server.server_address[1]}'
    print(f'Komponent Stok çalışıyor: {url}')
    print(f'Veritabanı: {DB_PATH}')
    print('Kapatmak için Ctrl+C')
    if '--no-browser' not in sys.argv:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\nKapatıldı.')


if __name__ == '__main__':
    main()
