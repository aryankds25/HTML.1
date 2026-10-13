"""
QR CODE ENCODER / DECODER - Module 4 (Utility 4): complete application
1 text/URL -> QR | 2 contact QR | 3 decode image | 4 decode webcam
Run:  python module4_qr_terminal.py

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
#  DECODER : image file -> text
# ======================================================================
def _read_png(path):
    """Tiny PNG reader (used only when Pillow is not installed)."""
    data = open(path, 'rb').read()
    if data[:8] != b'\x89PNG\r\n\x1a\n':
        raise ValueError("Not a PNG file (JPG needs Pillow: pip install pillow).")
    pos, idat, plte = 8, b'', None
    while pos < len(data):
        ln = struct.unpack('>I', data[pos:pos + 4])[0]
        typ, body = data[pos + 4:pos + 8], data[pos + 8:pos + 8 + ln]
        pos += 12 + ln
        if typ == b'IHDR':
            w, h, depth, ctype, _, _, inter = struct.unpack('>IIBBBBB', body)
        elif typ == b'PLTE':
            plte = body
        elif typ == b'IDAT':
            idat += body
        elif typ == b'IEND':
            break
    if inter:
        raise ValueError("Interlaced PNG is not supported.")
    raw = zlib.decompress(idat)
    chans = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[ctype]
    bpp = max(1, chans * depth // 8)
    stride = (w * chans * depth + 7) // 8
    prev = bytearray(stride)
    p = 0
    gray = []
    for y in range(h):
        f = raw[p]
        line = bytearray(raw[p + 1:p + 1 + stride])
        p += 1 + stride
        if f == 1:
            for i in range(bpp, stride):
                line[i] = (line[i] + line[i - bpp]) & 255
        elif f == 2:
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 255
        elif f == 3:
            for i in range(stride):
                left = line[i - bpp] if i >= bpp else 0
                line[i] = (line[i] + ((left + prev[i]) >> 1)) & 255
        elif f == 4:
            for i in range(stride):
                a = line[i - bpp] if i >= bpp else 0
                b = prev[i]
                c = prev[i - bpp] if i >= bpp else 0
                pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                line[i] = (line[i] + pr) & 255
        prev = line
        g = []
        if depth >= 8:
            st = depth // 8
            for i in range(w):
                o = i * chans * st
                if ctype == 0:
                    v = line[o]
                elif ctype == 2:
                    v = (line[o] * 299 + line[o + st] * 587 + line[o + 2 * st] * 114) // 1000
                elif ctype == 3:
                    q = line[o] * 3
                    v = (plte[q] * 299 + plte[q + 1] * 587 + plte[q + 2] * 114) // 1000
                elif ctype == 4:
                    a = line[o + st]
                    v = (line[o] * a + 255 * (255 - a)) // 255
                else:
                    a = line[o + 3 * st]
                    v = ((line[o] * 299 + line[o + st] * 587 + line[o + 2 * st] * 114) // 1000 * a + 255 * (255 - a)) // 255
                g.append(v)
        else:
            mx = (1 << depth) - 1
            for i in range(w):
                bit = i * depth
                v = (line[bit // 8] >> (8 - depth - bit % 8)) & mx
                if ctype == 0:
                    v = v * 255 // mx
                else:
                    q = v * 3
                    v = (plte[q] * 299 + plte[q + 1] * 587 + plte[q + 2] * 114) // 1000
                g.append(v)
        gray.append(g)
    return gray


def _shrink(rows, f):
    h, w = len(rows), len(rows[0])
    out = []
    for y in range(0, h - f + 1, f):
        r = []
        for x in range(0, w - f + 1, f):
            s = 0
            for dy in range(f):
                rr = rows[y + dy]
                for dx in range(f):
                    s += rr[x + dx]
            r.append(s // (f * f))
        out.append(r)
    return out


def _enlarge(rows, f):
    out = []
    for r in rows:
        rr = [v for v in r for _ in range(f)]
        out.extend([rr] * f)
    return out


def _gray_rows(path, max_side):
    """Return the picture as rows of gray values (0..255), resized to a sensible size."""
    if Image is not None:
        im = Image.open(path).convert('L')
        w, h = im.size
        s = max_side / float(max(w, h))
        if s < 1:
            im = im.resize((max(1, int(w * s)), max(1, int(h * s))), Image.LANCZOS)
        elif max(w, h) < 400:
            f = int(math.ceil(400.0 / max(w, h)))
            im = im.resize((w * f, h * f), Image.NEAREST)
        w, h = im.size
        raw = im.tobytes()
        return [list(raw[y * w:(y + 1) * w]) for y in range(h)]
    rows = _read_png(path)
    big = max(len(rows), len(rows[0]))
    if big > max_side:
        rows = _shrink(rows, int(math.ceil(big / float(max_side))))
    elif big < 400:
        rows = _enlarge(rows, int(math.ceil(400.0 / big)))
    return rows


def _otsu(rows):
    hist = [0] * 256
    for r in rows:
        for v in r:
            hist[v] += 1
    total = sum(hist)
    sum_all = sum(i * c for i, c in enumerate(hist))
    wb = sb = 0
    best, thr = -1, 127
    for t in range(256):
        wb += hist[t]
        if wb == 0:
            continue
        wf = total - wb
        if wf == 0:
            break
        sb += t * hist[t]
        d = wb * wf * (sb / wb - (sum_all - sb) / wf) ** 2
        if d > best:
            best, thr = d, t
    return thr


def _runs(row):
    runs, start, cur = [], 0, row[0]
    for i in range(1, len(row)):
        if row[i] != cur:
            runs.append((cur, start, i - start))
            cur, start = row[i], i
    runs.append((cur, start, len(row) - start))
    return runs


def _ratio(lens):
    total = sum(lens)
    if total < 7 or min(lens) == 0:
        return 0
    mod = total / 7.0
    for l, r in zip(lens, (1, 1, 3, 1, 1)):
        if abs(l - r * mod) > r * mod * 0.55:
            return 0
    return mod


def _vcount(bw, h, x, y, d):
    res, col, yy = [], 1, y
    for _ in range(3):
        n = 0
        while 0 <= yy < h and bw[yy][x] == col:
            n += 1
            yy += d
        res.append(n)
        col = 1 - col
    return res


def _find_centers(bw):
    """Find the three big corner squares (finder patterns) of the QR code."""
    h, w = len(bw), len(bw[0])
    cands = []
    for y in range(h):
        runs = _runs(bw[y])
        for k in range(len(runs) - 4):
            if runs[k][0] != 1:
                continue
            lens = [runs[k + i][2] for i in range(5)]
            mod = _ratio(lens)
            if not mod:
                continue
            cx = runs[k][1] + sum(lens) / 2.0
            x = min(w - 1, int(cx))
            up = _vcount(bw, h, x, y, -1)
            dn = _vcount(bw, h, x, y, 1)
            vl = [up[2], up[1], up[0] + dn[0] - 1, dn[1], dn[2]]
            mv = _ratio(vl)
            if not mv:
                continue
            cy = (y - up[0] + 1) + (up[0] + dn[0] - 1) / 2.0
            cands.append((cx, cy, (mod + mv) / 2.0))
    clusters = []
    for x, y, m in cands:
        for c in clusters:
            if abs(c[0] / c[3] - x) <= 1.0 * m and abs(c[1] / c[3] - y) <= 1.0 * m:
                c[0] += x; c[1] += y; c[2] += m; c[3] += 1
                break
        else:
            clusters.append([x, y, m, 1])
    out = [(c[0] / c[3], c[1] / c[3], c[2] / c[3], c[3]) for c in clusters if c[3] >= 2]
    out.sort(key=lambda c: -c[3])
    return out[:8]


def _triples(cents):
    res = []
    n = len(cents)
    for i in range(n):
        for j in range(i + 1, n):
            for k in range(j + 1, n):
                pts = [cents[i], cents[j], cents[k]]
                d = []
                for a in range(3):
                    b, c = [t for t in range(3) if t != a]
                    d.append(math.hypot(pts[b][0] - pts[c][0], pts[b][1] - pts[c][1]))
                order = sorted(range(3), key=lambda t: d[t])
                a_, b_, c_ = d[order[0]], d[order[1]], d[order[2]]
                if a_ == 0:
                    continue
                score = abs(a_ - b_) / a_ + abs(c_ - a_ * 1.4142) / c_
                ms = [p[2] for p in pts]
                score += (max(ms) - min(ms)) / max(ms)
                tl = pts[order[2]]          # opposite to the longest side
                o1, o2 = [pts[t] for t in range(3) if pts[t] is not tl]
                cross = (o1[0] - tl[0]) * (o2[1] - tl[1]) - (o1[1] - tl[1]) * (o2[0] - tl[0])
                tr, bl = (o1, o2) if cross > 0 else (o2, o1)
                res.append((score, tl, tr, bl, sum(ms) / 3.0))
    res.sort(key=lambda r: r[0])
    return [r for r in res if r[0] < 0.6][:4]


def _sample(bw, tl, tr, bl, dim):
    h, w = len(bw), len(bw[0])
    ux = ((tr[0] - tl[0]) / (dim - 7.0), (tr[1] - tl[1]) / (dim - 7.0))
    uy = ((bl[0] - tl[0]) / (dim - 7.0), (bl[1] - tl[1]) / (dim - 7.0))
    offs = ((0, 0), (0.25, 0), (-0.25, 0), (0, 0.25), (0, -0.25))
    m = []
    for v in range(dim):
        row = []
        for u in range(dim):
            dark = 0
            for ou, ov in offs:
                a, b = u - 3.0 + ou, v - 3.0 + ov
                px = tl[0] + a * ux[0] + b * uy[0]
                py = tl[1] + a * ux[1] + b * uy[1]
                xi, yi = int(math.floor(px)), int(math.floor(py))
                if 0 <= xi < w and 0 <= yi < h and bw[yi][xi]:
                    dark += 1
            row.append(dark >= 3)
        m.append(row)
    return m


def _rs_decode(block, nsym):
    """Fix damaged bytes (Reed-Solomon). Returns the data bytes, or None."""
    n = len(block)
    synd = []
    for j in range(nsym):
        s = 0
        for c in block:
            s = gf_mul(s, _EXP[j]) ^ c
        synd.append(s)
    if not any(synd):
        return block[:n - nsym]
    C, B, L, m, b = [1], [1], 0, 1, 1
    for i in range(nsym):
        d = synd[i]
        for j in range(1, L + 1):
            if j < len(C):
                d ^= gf_mul(C[j], synd[i - j])
        if d == 0:
            m += 1
            continue
        T = C[:]
        coef = gf_mul(d, gf_inv(b))
        if len(C) < len(B) + m:
            C = C + [0] * (len(B) + m - len(C))
        for j, bv in enumerate(B):
            C[j + m] ^= gf_mul(coef, bv)
        if 2 * L <= i:
            L, B, b, m = i + 1 - L, T, d, 1
        else:
            m += 1

    def ev(poly, x):
        acc, pw = 0, 1
        for c in poly:
            acc ^= gf_mul(c, pw)
            pw = gf_mul(pw, x)
        return acc
    locs = [p for p in range(n) if ev(C, _EXP[(255 - (n - 1 - p)) % 255]) == 0]
    if len(locs) != L or L == 0 or L > nsym // 2:
        return None
    om = []
    for i in range(nsym):
        s = 0
        for j in range(i + 1):
            if j < len(C):
                s ^= gf_mul(C[j], synd[i - j])
        om.append(s)
    fixed = block[:]
    for p in locs:
        k = n - 1 - p
        xinv = _EXP[(255 - k) % 255]
        den, lx = 0, (255 - k) % 255
        for j in range(1, len(C), 2):
            den ^= gf_mul(C[j], _EXP[(lx * (j - 1)) % 255])
        if den == 0:
            return None
        e = gf_mul(_EXP[k % 255], gf_mul(ev(om, xinv), gf_inv(den)))
        fixed[p] ^= e
    for j in range(nsym):
        s = 0
        for c in fixed:
            s = gf_mul(s, _EXP[j]) ^ c
        if s:
            return None
    return fixed[:n - nsym]


def _read_format(m):
    size = len(m)
    c1 = [(8, 0), (8, 1), (8, 2), (8, 3), (8, 4), (8, 5), (8, 7), (8, 8), (7, 8), (5, 8), (4, 8), (3, 8), (2, 8), (1, 8), (0, 8)]
    c2 = [(size - 1 - i, 8) for i in range(8)] + [(8, size - 15 + i) for i in range(8, 15)]
    best, best_d = None, 99
    for cp in (c1, c2):
        word = 0
        for i, (x, y) in enumerate(cp):
            if m[y][x]:
                word |= 1 << i
        for data in range(32):
            d = bin(word ^ _format_word(data)).count('1')
            if d < best_d:
                best_d, best = d, data
    if best_d > 3:
        return None
    return {1: 'L', 0: 'M', 3: 'Q', 2: 'H'}[best >> 3], best & 7


_ALNUM = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ $%*+-./:"
_CCBITS = {1: (10, 12, 14), 2: (9, 11, 13), 4: (8, 16, 16), 8: (8, 10, 12)}


def _parse(data, ver):
    bits = ''.join(format(b, '08b') for b in data)
    pos = [0]

    def take(n):
        v = int(bits[pos[0]:pos[0] + n], 2)
        pos[0] += n
        return v
    idx = 0 if ver <= 9 else 1 if ver <= 26 else 2
    out = ''
    while pos[0] + 4 <= len(bits):
        mode = take(4)
        if mode == 0:
            break
        if mode == 7:
            b = int(bits[pos[0]:pos[0] + 8], 2)
            pos[0] += 8 if b < 128 else 16 if b < 192 else 24
            continue
        if mode not in _CCBITS:
            raise ValueError("unsupported QR mode")
        n = take(_CCBITS[mode][idx])
        if mode == 1:
            while n >= 3:
                out += '%03d' % take(10); n -= 3
            if n == 2:
                out += '%02d' % take(7)
            elif n == 1:
                out += '%d' % take(4)
        elif mode == 2:
            while n >= 2:
                v = take(11); out += _ALNUM[v // 45] + _ALNUM[v % 45]; n -= 2
            if n == 1:
                out += _ALNUM[take(6)]
        elif mode == 4:
            raw = bytes(take(8) for _ in range(n))
            try:
                out += raw.decode('utf-8')
            except UnicodeDecodeError:
                out += raw.decode('latin-1')
        else:
            raw = b''
            for _ in range(n):
                v = take(13)
                w = ((v // 0xC0) << 8) | (v % 0xC0)
                w += 0x8140 if w + 0x8140 <= 0x9FFC else 0xC140
                raw += bytes([w >> 8, w & 255])
            out += raw.decode('shift_jis', 'replace')
    return out


def _decode_matrix(m):
    size = len(m)
    ver = (size - 17) // 4
    fmt = _read_format(m)
    if fmt is None:
        return None
    lvl, mask = fmt
    _, fun = _new_grid(ver)
    bits = []
    for x, y in _zigzag(size):
        if not fun[y][x]:
            bits.append(1 if (m[y][x] != _mask_cond(mask, x, y)) else 0)
    cw = [int(''.join(str(b) for b in bits[i:i + 8]), 2) for i in range(0, len(bits) // 8 * 8, 8)]
    nb, ecl = _BLK[lvl][ver], _ECC[lvl][ver]
    rawcw = _raw_modules(ver) // 8
    cw = cw[:rawcw]
    nshort, shortlen = nb - rawcw % nb, rawcw // nb
    blocks = [[] for _ in range(nb)]
    k = 0
    for i in range(shortlen - ecl + 1):
        for j in range(nb):
            if i == shortlen - ecl and j < nshort:
                continue
            blocks[j].append(cw[k]); k += 1
    for i in range(ecl):
        for j in range(nb):
            blocks[j].append(cw[k]); k += 1
    data = []
    for blk in blocks:
        fixed = _rs_decode(blk, ecl)
        if fixed is None:
            return None
        data += fixed
    try:
        return _parse(data, ver)
    except Exception:
        return None


def _try_bw(bw):
    cents = _find_centers(bw)
    if len(cents) < 3:
        return ''
    for _, tl, tr, bl, mod in _triples(cents):
        d = (math.hypot(tr[0] - tl[0], tr[1] - tl[1]) + math.hypot(bl[0] - tl[0], bl[1] - tl[1])) / 2.0
        v0 = int(round(((d / mod + 7) - 17) / 4.0))
        for ver in (v0, v0 - 1, v0 + 1):
            if not 1 <= ver <= 40:
                continue
            m = _sample(bw, tl, tr, bl, ver * 4 + 17)
            for mm in (m, [list(r) for r in zip(*m)]):
                text = _decode_matrix(mm)
                if text:
                    return text
    return ''


def decode_builtin(path):
    """Read a QR code from an image file using only the built-in engine."""
    for side in (1200, 700):
        rows = _gray_rows(path, side)
        thr = _otsu(rows)
        for invert in (False, True):
            bw = [[1 if ((v <= thr) != invert) else 0 for v in r] for r in rows]
            text = _try_bw(bw)
            if text:
                return text
    return ''


def decode_frame_cv(frame):
    """OpenCV version (used first when OpenCV is installed)."""
    detector = cv2.QRCodeDetector()
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    tries = [frame,
             cv2.copyMakeBorder(frame, 40, 40, 40, 40, cv2.BORDER_CONSTANT, value=(255, 255, 255)),
             cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC),
             cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]]
    for picture in tries:
        text, points, _ = detector.detectAndDecode(picture)
        if text:
            return text
    return ""


def decode_image(path):
    """Try OpenCV first (if installed), then the built-in engine."""
    if cv2 is not None:
        try:
            frame = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
            if frame is not None:
                text = decode_frame_cv(frame)
                if text:
                    return text
        except Exception:
            pass
    return decode_builtin(path)


# ======================================================================
#  SMALL HELPERS : find image files on the phone / computer
# ======================================================================
def find_images():
    dirs = [os.getcwd(), '/storage/emulated/0/Download', '/storage/emulated/0/Pictures',
            '/storage/emulated/0/Pictures/Screenshots', '/storage/emulated/0/DCIM/Screenshots',
            '/storage/emulated/0/DCIM/Camera']
    seen, found = set(), []
    for d in dirs:
        try:
            names = os.listdir(d)
        except Exception:
            continue
        for f in names:
            if f.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.webp', '.gif')):
                p = os.path.join(d, f)
                rp = os.path.realpath(p)
                if rp in seen:
                    continue
                seen.add(rp)
                try:
                    found.append((os.path.getmtime(p), p))
                except OSError:
                    pass
    found.sort(reverse=True)
    return [p for _, p in found[:8]]


def ask_image_path():
    """Show the newest images and let the user pick one. Returns path, None (not found) or False (back)."""
    imgs = find_images()
    print("\nImages found on this device (newest first):")
    for i, p in enumerate(imgs, 1):
        print(" %d. %s" % (i, p))
    if not imgs:
        print(" (none found - type the full path instead)")
    s = input("Type a number, or a file path (0 = back): ").strip().strip('"').strip("'")
    if s in ("0", ""):
        return False
    if s.isdigit() and 1 <= int(s) <= len(imgs):
        return imgs[int(s) - 1]
    if os.path.isfile(s):
        return s
    for d in (os.getcwd(), '/storage/emulated/0/Download'):
        p = os.path.join(d, s)
        if os.path.isfile(p):
            return p
    print("File not found:", s)
    return None


def decode_and_show(path):
    try:
        text = decode_image(path)
    except Exception as error:
        print("Could not read this image:", error)
        return
    if text:
        show_result(text)
    else:
        print("No QR code could be read from this image.")
        print("Tip: use a clear, straight picture of the QR (a screenshot works best).")


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
#  WEBCAM SCANNER  (needs OpenCV and a camera - works on a computer)
# ======================================================================
def scan_webcam():
    if cv2 is None:
        print("Webcam scanning needs OpenCV:  pip install opencv-python")
        return ""
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("Webcam not available here (normal on mobile / online terminals).")
        return ""
    detector = cv2.QRCodeDetector()
    result = ""
    print("Camera started. Show a QR code. Press Q in the camera window to stop.")
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        text, points, _ = detector.detectAndDecode(frame)
        if points is not None:
            box = points.astype(int).reshape(-1, 2)
            cv2.polylines(frame, [box], True, (0, 255, 0), 3)
        if text:
            result = text
            cv2.imshow("QR Webcam Scanner (Q to quit)", frame)
            cv2.waitKey(800)
            break
        cv2.imshow("QR Webcam Scanner (Q to quit)", frame)
        if cv2.waitKey(1) & 0xFF in (ord("q"), 27):
            break
    cap.release()
    cv2.destroyAllWindows()
    return result


# ======================================================================
#  MAIN PROGRAM  (Module 4 : everything together)
# ======================================================================
def main():
    while True:
        print("\n===== QR CODE ENCODER / DECODER =====")
        print("1. Generate QR from text / URL")
        print("2. Generate QR for a contact (vCard)")
        print("3. Decode QR from an image file")
        print("4. Decode QR from webcam (computer only)")
        print("0. Exit")
        choice = input("Choose (0-4): ").strip()
        try:
            if choice == "1":
                data = input("Enter text or URL: ").strip()
                if data:
                    name = input("File name [qrcode.png]: ").strip() or "qrcode.png"
                    if not name.lower().endswith((".png", ".jpg", ".jpeg")):
                        name += ".png"
                    generate(data, name)
                else:
                    print("Nothing entered.")
            elif choice == "2":
                ask_contact_and_generate()
            elif choice == "3":
                path = ask_image_path()
                if path:
                    decode_and_show(path)
            elif choice == "4":
                text = scan_webcam()
                if text:
                    show_result(text)
            elif choice == "0":
                print("Goodbye!")
                break
            else:
                print("Please type a number from 0 to 4.")
        except Exception as error:
            print("Something went wrong:", error)


if __name__ == "__main__":
    main()
