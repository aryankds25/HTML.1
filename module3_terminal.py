"""
Module 3 (Utility 3) - Contact (vCard) QR Code   [name, phone, email -> QR]
Run:  python module3_terminal.py

NOTHING EXTRA IS REQUIRED: this file has its own QR engine built in, so it runs in any
Python terminal and on mobile (Pydroid 3, Termux). If the libraries qrcode / Pillow /
OpenCV happen to be installed, they are used automatically.
"""
# ======================================================================
#  BUILT-IN QR ENGINE  (used automatically when qrcode / OpenCV are not installed)
#  You do NOT need to edit this part. The simple "main program" is at the bottom.
# ======================================================================
import os
import math
import struct
import zlib

try:
    import qrcode
except Exception:
    qrcode = None
try:
    import cv2
    import numpy as np
except Exception:
    cv2 = None
    np = None
try:
    from PIL import Image
except Exception:
    Image = None

# ---- maths used by QR error correction (Galois field 256) ----
_EXP = [0] * 512
_LOG = [0] * 256
_x = 1
for _i in range(255):
    _EXP[_i] = _x
    _LOG[_x] = _i
    _x <<= 1
    if _x & 0x100:
        _x ^= 0x11D
for _i in range(255, 512):
    _EXP[_i] = _EXP[_i - 255]


def gf_mul(a, b):
    return 0 if a == 0 or b == 0 else _EXP[_LOG[a] + _LOG[b]]


def gf_inv(a):
    return _EXP[255 - _LOG[a]]


# ---- QR size tables (index = version 1..40) ----
_ECC = {
    'L': (-1, 7, 10, 15, 20, 26, 18, 20, 24, 30, 18, 20, 24, 26, 30, 22, 24, 28, 30, 28, 28, 28, 28, 30, 30, 26, 28, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30),
    'M': (-1, 10, 16, 26, 18, 24, 16, 18, 22, 22, 26, 30, 22, 22, 24, 24, 28, 28, 26, 26, 26, 26, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28),
    'Q': (-1, 13, 22, 18, 26, 18, 24, 18, 22, 20, 24, 28, 26, 24, 20, 30, 24, 28, 28, 26, 30, 28, 30, 30, 30, 30, 28, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30),
    'H': (-1, 17, 28, 22, 16, 22, 28, 26, 26, 24, 28, 24, 28, 22, 24, 24, 30, 28, 28, 26, 28, 30, 24, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30),
}
_BLK = {
    'L': (-1, 1, 1, 1, 1, 1, 2, 2, 2, 2, 4, 4, 4, 4, 4, 6, 6, 6, 6, 7, 8, 8, 9, 9, 10, 12, 12, 12, 13, 14, 15, 16, 17, 18, 19, 19, 20, 21, 22, 24, 25),
    'M': (-1, 1, 1, 1, 2, 2, 4, 4, 4, 5, 5, 5, 8, 9, 9, 10, 10, 11, 13, 14, 16, 17, 17, 18, 20, 21, 23, 25, 26, 28, 29, 31, 33, 35, 37, 38, 40, 43, 45, 47, 49),
    'Q': (-1, 1, 1, 2, 2, 4, 4, 6, 6, 8, 8, 8, 10, 12, 16, 12, 17, 16, 18, 21, 20, 23, 23, 25, 27, 29, 34, 34, 35, 38, 40, 43, 45, 48, 51, 53, 56, 59, 62, 65, 68),
    'H': (-1, 1, 1, 2, 4, 4, 4, 5, 6, 8, 8, 11, 11, 16, 16, 18, 16, 19, 21, 25, 25, 25, 34, 30, 32, 35, 37, 40, 42, 45, 48, 51, 54, 57, 60, 63, 66, 70, 74, 77, 81),
}
_FMT = {'L': 1, 'M': 0, 'Q': 3, 'H': 2}


def _raw_modules(ver):
    r = (16 * ver + 128) * ver + 64
    if ver >= 2:
        na = ver // 7 + 2
        r -= (25 * na - 10) * na - 55
        if ver >= 7:
            r -= 36
    return r


def _data_codewords(ver, lvl):
    return _raw_modules(ver) // 8 - _ECC[lvl][ver] * _BLK[lvl][ver]


def _align_pos(ver):
    if ver == 1:
        return []
    na = ver // 7 + 2
    step = 26 if ver == 32 else (ver * 4 + na * 2 + 1) // (na * 2 - 2) * 2
    res = [ver * 4 + 10 - i * step for i in range(na - 1)] + [6]
    return res[::-1]


def _format_word(data):
    rem = data
    for _ in range(10):
        rem = (rem << 1) ^ ((rem >> 9) * 0x537)
    return ((data << 10) | rem) ^ 0x5412


def _put_format(mod, fun, size, lvl, mask):
    bits = _format_word((_FMT[lvl] << 3) | mask)

    def setf(x, y, d):
        mod[y][x] = d
        fun[y][x] = True
    gb = lambda i: ((bits >> i) & 1) != 0
    for i in range(0, 6):
        setf(8, i, gb(i))
    setf(8, 7, gb(6))
    setf(8, 8, gb(7))
    setf(7, 8, gb(8))
    for i in range(9, 15):
        setf(14 - i, 8, gb(i))
    for i in range(0, 8):
        setf(size - 1 - i, 8, gb(i))
    for i in range(8, 15):
        setf(8, size - 15 + i, gb(i))
    setf(8, size - 8, True)


def _new_grid(ver):
    size = ver * 4 + 17
    mod = [[False] * size for _ in range(size)]
    fun = [[False] * size for _ in range(size)]

    def setf(x, y, d):
        mod[y][x] = d
        fun[y][x] = True
    for i in range(size):
        setf(6, i, i % 2 == 0)
        setf(i, 6, i % 2 == 0)
    for cx, cy in ((3, 3), (size - 4, 3), (3, size - 4)):
        for dy in range(-4, 5):
            for dx in range(-4, 5):
                xx, yy = cx + dx, cy + dy
                if 0 <= xx < size and 0 <= yy < size:
                    setf(xx, yy, max(abs(dx), abs(dy)) not in (2, 4))
    pos = _align_pos(ver)
    n = len(pos)
    for i in range(n):
        for j in range(n):
            if (i == 0 and j == 0) or (i == 0 and j == n - 1) or (i == n - 1 and j == 0):
                continue
            for dy in range(-2, 3):
                for dx in range(-2, 3):
                    setf(pos[i] + dx, pos[j] + dy, max(abs(dx), abs(dy)) != 1)
    _put_format(mod, fun, size, 'M', 0)
    if ver >= 7:
        rem = ver
        for _ in range(12):
            rem = (rem << 1) ^ ((rem >> 11) * 0x1F25)
        bits = (ver << 12) | rem
        for i in range(18):
            bit = ((bits >> i) & 1) != 0
            a = size - 11 + i % 3
            b = i // 3
            setf(a, b, bit)
            setf(b, a, bit)
    return mod, fun


def _zigzag(size):
    """Order in which data bits are placed in the QR grid."""
    order = []
    for right in range(size - 1, 0, -2):
        if right <= 6:
            right -= 1
        for vert in range(size):
            for j in range(2):
                x = right - j
                upward = ((right + 1) & 2) == 0
                y = (size - 1 - vert) if upward else vert
                order.append((x, y))
    return order


def _mask_cond(mask, x, y):
    if mask == 0: return (x + y) % 2 == 0
    if mask == 1: return y % 2 == 0
    if mask == 2: return x % 3 == 0
    if mask == 3: return (x + y) % 3 == 0
    if mask == 4: return (x // 3 + y // 2) % 2 == 0
    if mask == 5: return x * y % 2 + x * y % 3 == 0
    if mask == 6: return (x * y % 2 + x * y % 3) % 2 == 0
    return ((x + y) % 2 + x * y % 3) % 2 == 0


# ======================================================================
#  ENCODER  : text -> QR matrix (list of rows of True/False)
# ======================================================================
_GEN_CACHE = {}


def _rs_generator(n):
    if n in _GEN_CACHE:
        return _GEN_CACHE[n]
    g = [1]
    for i in range(n):
        ng = [0] * (len(g) + 1)
        for j, c in enumerate(g):
            ng[j] ^= c
            ng[j + 1] ^= gf_mul(c, _EXP[i])
        g = ng
    _GEN_CACHE[n] = g
    return g


def _rs_encode(data, n):
    gen = _rs_generator(n)
    rem = [0] * n
    for b in data:
        f = b ^ rem[0]
        rem = rem[1:] + [0]
        if f:
            for i in range(n):
                rem[i] ^= gf_mul(gen[i + 1], f)
    return rem


def _interleave(data, ver, lvl):
    nb, ecl = _BLK[lvl][ver], _ECC[lvl][ver]
    rawcw = _raw_modules(ver) // 8
    nshort = nb - rawcw % nb
    shortlen = rawcw // nb
    blocks = []
    k = 0
    for i in range(nb):
        dat = data[k:k + shortlen - ecl + (0 if i < nshort else 1)]
        k += len(dat)
        ecc = _rs_encode(dat, ecl)
        if i < nshort:
            dat = dat + [0]
        blocks.append(dat + ecc)
    out = []
    for i in range(len(blocks[0])):
        for j, blk in enumerate(blocks):
            if i != shortlen - ecl or j >= nshort:
                out.append(blk[i])
    return out


def _penalty(m):
    n = len(m)
    score = 0
    rows = [''.join('1' if c else '0' for c in r) for r in m]
    cols = [''.join('1' if m[y][x] else '0' for y in range(n)) for x in range(n)]
    for line in rows + cols:
        run = 1
        for i in range(1, n):
            if line[i] == line[i - 1]:
                run += 1
            else:
                if run >= 5:
                    score += 3 + run - 5
                run = 1
        if run >= 5:
            score += 3 + run - 5
        score += 40 * (line.count('10111010000') + line.count('00001011101'))
    for y in range(n - 1):
        for x in range(n - 1):
            if m[y][x] == m[y][x + 1] == m[y + 1][x] == m[y + 1][x + 1]:
                score += 3
    dark = sum(sum(1 for c in r if c) for r in m)
    total = n * n
    k = (abs(dark * 20 - total * 10) + total - 1) // total - 1
    return score + max(k, 0) * 10


def make_matrix(text, lvl='M'):
    """Build a QR code (byte mode, UTF-8) and return it as rows of True/False."""
    data = text.encode('utf-8')
    for ver in range(1, 41):
        cc = 8 if ver <= 9 else 16
        if 4 + cc + 8 * len(data) <= _data_codewords(ver, lvl) * 8:
            break
    else:
        raise ValueError("Text is too long for one QR code.")
    cap = _data_codewords(ver, lvl) * 8
    bits = []

    def put(val, n):
        for i in range(n - 1, -1, -1):
            bits.append((val >> i) & 1)
    put(4, 4)
    put(len(data), cc)
    for b in data:
        put(b, 8)
    put(0, min(4, cap - len(bits)))
    while len(bits) % 8:
        bits.append(0)
    cw = [int(''.join(str(b) for b in bits[i:i + 8]), 2) for i in range(0, len(bits), 8)]
    pad = 0xEC
    while len(cw) < cap // 8:
        cw.append(pad)
        pad ^= 0xEC ^ 0x11
    final = _interleave(cw, ver, lvl)
    mod, fun = _new_grid(ver)
    size = ver * 4 + 17
    i = 0
    for x, y in _zigzag(size):
        if not fun[y][x] and i < len(final) * 8:
            mod[y][x] = ((final[i >> 3] >> (7 - (i & 7))) & 1) != 0
            i += 1
    best, best_score = None, None
    for mask in range(8):
        m2 = [row[:] for row in mod]
        for y in range(size):
            for x in range(size):
                if not fun[y][x] and _mask_cond(mask, x, y):
                    m2[y][x] = not m2[y][x]
        _put_format(m2, fun, size, lvl, mask)
        s = _penalty(m2)
        if best is None or s < best_score:
            best, best_score = m2, s
    return best


def save_png(matrix, filename, scale=10, border=4):
    """Write the QR matrix as a black & white PNG (no extra library needed)."""
    n = len(matrix)
    rows = []
    for y in range(-border, n + border):
        line = bytearray()
        for x in range(-border, n + border):
            dark = 0 <= x < n and 0 <= y < n and matrix[y][x]
            line += (b'\x00' if dark else b'\xff') * scale
        rows += [b'\x00' + bytes(line)] * scale
    dim = (n + 2 * border) * scale

    def chunk(t, d):
        c = struct.pack('>I', len(d)) + t + d
        return c + struct.pack('>I', zlib.crc32(t + d) & 0xffffffff)
    png = (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', dim, dim, 8, 0, 0, 0, 0)) +
           chunk(b'IDAT', zlib.compress(b''.join(rows), 9)) + chunk(b'IEND', b''))
    with open(filename, 'wb') as f:
        f.write(png)


def matrix_to_text(m, border=2):
    """Draw the QR with text blocks (best on a dark/black terminal)."""
    n = len(m)

    def dark(x, y):
        return 0 <= x < n and 0 <= y < n and m[y][x]
    lines = []
    for y in range(-border, n + border, 2):
        s = ''
        for x in range(-border, n + border):
            t, b = dark(x, y), dark(x, y + 1)
            s += '\u2588' if (not t and not b) else '\u2580' if (not t and b) else '\u2584' if (t and not b) else ' '
        lines.append(s)
    return '\n'.join(lines)


def save_path(name):
    """Prefer the phone's Download folder so the gallery / file manager can see it."""
    if os.path.dirname(name):
        return name
    for d in ('/storage/emulated/0/Download', '/sdcard/Download'):
        if os.path.isdir(d) and os.access(d, os.W_OK):
            return os.path.join(d, name)
    return os.path.abspath(name)


def generate(text, filename):
    """Make the QR, save it as an image, and show it in the terminal."""
    matrix = None
    if qrcode is not None:                       # use the qrcode library if installed
        try:
            qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=10, border=4)
            qr.add_data(text)
            qr.make(fit=True)
            matrix = [[bool(c) for c in row] for row in qr.modules]
        except Exception:
            matrix = None
    if matrix is None:                           # otherwise use the built-in engine
        matrix = make_matrix(text)
    target = save_path(filename)
    try:
        save_png(matrix, target)
    except Exception:
        target = os.path.abspath(filename)
        save_png(matrix, target)
    print("\nQR code (scan it from the screen, best on a dark terminal):\n")
    print(matrix_to_text(matrix))
    print("\nSaved as:", target)
    return target


# ======================================================================
#  CONTACT CARD (vCard) HELPERS
# ======================================================================
def esc(t):
    """vCard needs ; , and new-lines escaped with a backslash."""
    return t.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def make_vcard(name, phone="", email="", org="", title="", url="", address=""):
    p = name.split()
    last = p[-1] if len(p) > 1 else ""
    first = " ".join(p[:-1]) if len(p) > 1 else name
    lines = ["BEGIN:VCARD", "VERSION:3.0", "N:%s;%s;;;" % (esc(last), esc(first)), "FN:" + esc(name)]
    if phone:   lines.append("TEL;TYPE=CELL:" + esc(phone))
    if email:   lines.append("EMAIL:" + esc(email))
    if org:     lines.append("ORG:" + esc(org))
    if title:   lines.append("TITLE:" + esc(title))
    if url:     lines.append("URL:" + url)
    if address: lines.append("ADR;TYPE=HOME:;;" + esc(address) + ";;;;")
    lines.append("END:VCARD")
    return "\n".join(lines)


def parse_vcard(text):
    names = {"FN": "Name", "TEL": "Phone", "EMAIL": "Email", "ORG": "Organization",
             "TITLE": "Job title", "URL": "Website", "ADR": "Address"}
    out = {}
    for line in text.splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            k = k.split(";")[0].upper()
            if k in names:
                out[names[k]] = v.replace("\\n", " ").replace("\\,", ",").replace("\\;", ";").replace(";", " ").strip()
    return out


def ask_contact_and_generate():
    name = input("Full name *  : ").strip()
    if not name:
        print("Name is required.")
        return
    card = make_vcard(name, input("Phone       : ").strip(), input("Email       : ").strip(),
                      input("Organization: ").strip(), input("Job title   : ").strip(),
                      input("Website     : ").strip(), input("Address     : ").strip())
    out = input("File name [contact_qr.png]: ").strip() or "contact_qr.png"
    if not out.lower().endswith((".png", ".jpg", ".jpeg")):
        out += ".png"
    generate(card, out)
    print("\nScan it with a phone camera - it offers 'Add to Contacts'.")


def show_result(text):
    """Show what was found inside a QR code (text, link or contact)."""
    import webbrowser
    print("\n========== QR CODE FOUND ==========")
    if text.upper().startswith("BEGIN:VCARD"):
        print("Type: CONTACT CARD")
        for k, v in parse_vcard(text).items():
            print("  %-13s: %s" % (k, v))
        if input("\nSave as contact file (.vcf)? (y/n): ").strip().lower() == "y":
            path = save_path("contact.vcf")
            try:
                open(path, "w", encoding="utf-8").write(text)
            except Exception:
                path = os.path.abspath("contact.vcf")
                open(path, "w", encoding="utf-8").write(text)
            print("Saved as", path)
    elif text.upper().startswith(("HTTP://", "HTTPS://", "WWW.")):
        print("Type: LINK\n ", text)
        if input("\nOpen in browser? (y/n): ").strip().lower() == "y":
            webbrowser.open(text if not text.upper().startswith("WWW.") else "https://" + text)
    else:
        print("Type: TEXT\n ", text)


# ======================================================================
#  MAIN PROGRAM  (Module 3)
# ======================================================================
def main():
    print("===== MODULE 3 : CONTACT (vCard) QR CODE =====")
    while True:
        if input("\nPress Enter to create a contact QR (0 = exit): ").strip() == "0":
            print("Goodbye!")
            break
        try:
            ask_contact_and_generate()
        except Exception as error:
            print("Something went wrong:", error)


if __name__ == "__main__":
    main()
