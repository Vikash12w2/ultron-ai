from __future__ import annotations

import math
import random

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPen, QRadialGradient
from PySide6.QtWidgets import QWidget

PALETTES = {
    "crimson": {"main": (235, 64, 72), "hot": (255, 150, 140), "soft": (120, 30, 38)},
    "ice": {"main": (64, 190, 255), "hot": (190, 240, 255), "soft": (20, 70, 110)},
    "gold": {"main": (255, 176, 46), "hot": (255, 228, 160), "soft": (110, 70, 15)},
}
SPEED = {"idle": 0.35, "listening": 0.6, "thinking": 2.4, "speaking": 0.9}
BARS = 96


def _icosphere():
    t = (1 + 5 ** 0.5) / 2
    verts = [(-1, t, 0), (1, t, 0), (-1, -t, 0), (1, -t, 0), (0, -1, t), (0, 1, t), (0, -1, -t), (0, 1, -t),
             (t, 0, -1), (t, 0, 1), (-t, 0, -1), (-t, 0, 1)]
    faces = [(0, 11, 5), (0, 5, 1), (0, 1, 7), (0, 7, 10), (0, 10, 11), (1, 5, 9), (5, 11, 4), (11, 10, 2),
             (10, 7, 6), (7, 1, 8), (3, 9, 4), (3, 4, 2), (3, 2, 6), (3, 6, 8), (3, 8, 9), (4, 9, 5), (2, 4, 11),
             (6, 2, 10), (8, 6, 7), (9, 8, 1)]
    verts = [_norm(v) for v in verts]
    cache: dict = {}

    def mid(a, b):
        key = tuple(sorted((a, b)))
        if key not in cache:
            va, vb = verts[a], verts[b]
            verts.append(_norm(((va[0] + vb[0]) / 2, (va[1] + vb[1]) / 2, (va[2] + vb[2]) / 2)))
            cache[key] = len(verts) - 1
        return cache[key]

    new_faces = []
    for a, b, c in faces:
        ab, bc, ca = mid(a, b), mid(b, c), mid(c, a)
        new_faces += [(a, ab, ca), (b, bc, ab), (c, ca, bc), (ab, bc, ca)]
    edges = {tuple(sorted(e)) for f in new_faces for e in ((f[0], f[1]), (f[1], f[2]), (f[2], f[0]))}
    return verts, sorted(edges)


def _norm(v):
    n = math.sqrt(sum(c * c for c in v))
    return (v[0] / n, v[1] / n, v[2] / n)


class OrbWidget(QWidget):
    def __init__(self, parent=None, palette: str = "crimson"):
        super().__init__(parent)
        self.setMinimumSize(280, 280)
        self.palette_name = palette if palette in PALETTES else "crimson"
        self.verts, self.edges = _icosphere()
        self.state = "idle"
        self.level = 0.0
        self.target_level = 0.0
        self.t = 0.0
        self.spin = 0.0
        self.bars = [0.0] * BARS
        self.bar_seed = [random.random() * math.tau for _ in range(BARS)]
        self.sparks: list[list[float]] = []
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(16)

    def set_state(self, state: str) -> None:
        self.state = state if state in SPEED else "idle"

    def set_level(self, level: float) -> None:
        self.target_level = max(0.0, min(1.0, float(level)))

    def set_palette(self, name: str) -> None:
        self.palette_name = name if name in PALETTES else "crimson"


    def _tick(self):
        dt = 0.016
        self.t += dt
        self.level += (self.target_level - self.level) * 0.3
        if self.state not in ("listening", "speaking"):
            self.target_level *= 0.85
        self.spin += dt * SPEED[self.state]
        active = self.state in ("listening", "speaking")
        for i in range(BARS):
            wave = 0.5 + 0.5 * math.sin(self.t * 7 + self.bar_seed[i] * 3 + i * 0.35)
            target = (self.level * (0.35 + 0.65 * wave)) if active else 0.06 + 0.04 * math.sin(self.t * 2 + i * 0.2)
            self.bars[i] += (target - self.bars[i]) * 0.35
        if self.state == "speaking" and self.level > 0.08:
            for _ in range(int(1 + self.level * 4)):
                self.sparks.append([random.random() * math.tau, 0.55, 0.8 + random.random() * 1.6, 1.0])
        for s in self.sparks:
            s[1] += dt * s[2] * 0.6
            s[3] -= dt * 1.1
        self.sparks = [s for s in self.sparks if s[3] > 0][-260:]
        self.update()


    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pal = PALETTES[self.palette_name]
        main, hot, soft = pal["main"], pal["hot"], pal["soft"]
        w, h = self.width(), self.height()
        cx, cy = w / 2, h / 2
        R = min(w, h) * 0.40
        breathe = 1 + 0.02 * math.sin(self.t * 1.4) + 0.05 * self.level
        c = QPointF(cx, cy)


        glow = QRadialGradient(c, R * 1.25)
        glow.setColorAt(0.0, QColor(*main, int(55 + 80 * self.level)))
        glow.setColorAt(0.5, QColor(*soft, 30))
        glow.setColorAt(1.0, QColor(*soft, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(glow)
        p.drawEllipse(c, R * 1.25, R * 1.25)
        p.setBrush(Qt.BrushStyle.NoBrush)


        p.save()
        p.translate(c)
        p.rotate(-math.degrees(self.spin * 0.15))
        for i in range(120):
            long = i % 10 == 0
            pen = QPen(QColor(*main, 170 if long else 70))
            pen.setWidthF(1.6 if long else 1.0)
            p.setPen(pen)
            r1 = R * (0.97 if long else 0.99)
            a = math.radians(i * 3)
            p.drawLine(QPointF(r1 * math.cos(a), r1 * math.sin(a)), QPointF(R * 1.03 * math.cos(a), R * 1.03 * math.sin(a)))
        p.restore()


        for i, (radius, width, segs, gap, speed) in enumerate(
                ((0.90, 3.0, 6, 14, 0.5), (0.84, 1.5, 24, 6, -0.9), (0.78, 5.0, 3, 50, 0.3))):
            pen = QPen(QColor(*main, 150 if i != 1 else 110))
            pen.setWidthF(width)
            pen.setCapStyle(Qt.PenCapStyle.FlatCap)
            p.setPen(pen)
            r = R * radius * breathe
            rect = QRectF(cx - r, cy - r, 2 * r, 2 * r)
            base = math.degrees(self.spin * speed) + i * 17
            span = 360 / segs
            for s in range(segs):
                p.drawArc(rect, int((base + s * span) * 16), int((span - gap) * 16))


        scan_speed = 4.0 if self.state == "thinking" else 1.0
        pen = QPen(QColor(*hot, 220))
        pen.setWidthF(2.4)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        r = R * 0.72 * breathe
        p.drawArc(QRectF(cx - r, cy - r, 2 * r, 2 * r), int(math.degrees(self.t * scan_speed) * 16 % 5760), 40 * 16)


        inner = R * 0.50 * breathe
        for i, v in enumerate(self.bars):
            a = i / BARS * math.tau - math.pi / 2
            length = R * (0.03 + 0.17 * v)
            alpha = int(90 + 160 * min(1.0, v * 1.4))
            pen = QPen(QColor(*(hot if v > 0.5 else main), alpha))
            pen.setWidthF(2.2)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            p.drawLine(QPointF(cx + inner * math.cos(a), cy + inner * math.sin(a)),
                       QPointF(cx + (inner + length) * math.cos(a), cy + (inner + length) * math.sin(a)))


        p.setPen(Qt.PenStyle.NoPen)
        for ang, dist, _spd, life in self.sparks:
            d = R * dist
            p.setBrush(QColor(*hot, int(200 * life)))
            p.drawEllipse(QPointF(cx + d * math.cos(ang), cy + d * math.sin(ang)), 1.4 + life, 1.4 + life)


        ay, ax = self.spin * 0.8, 0.5 + 0.2 * math.sin(self.t * 0.5)
        cay, say, cax, sax = math.cos(ay), math.sin(ay), math.cos(ax), math.sin(ax)
        gr = R * 0.36 * breathe
        proj = []
        for x, y, z in self.verts:
            x1, z1 = x * cay - z * say, x * say + z * cay
            y1, z2 = y * cax - z1 * sax, y * sax + z1 * cax
            persp = 1 / (1.7 - 0.5 * z2)
            proj.append((cx + x1 * gr * persp * 1.3, cy + y1 * gr * persp * 1.3, z2))
        for a, b in self.edges:
            za = (proj[a][2] + proj[b][2]) / 2
            depth = (za + 1) / 2
            pen = QPen(QColor(*(hot if depth > 0.6 else main), int(25 + 170 * depth)))
            pen.setWidthF(0.6 + 1.0 * depth)
            p.setPen(pen)
            p.drawLine(QPointF(proj[a][0], proj[a][1]), QPointF(proj[b][0], proj[b][1]))
        p.setPen(Qt.PenStyle.NoPen)
        for x, y, z in proj:
            if z > 0.2:
                p.setBrush(QColor(*hot, int(120 + 120 * z)))
                p.drawEllipse(QPointF(x, y), 1.6, 1.6)


        pulse = 0.06 * math.sin(self.t * (9 if self.state == "thinking" else 2.5))
        core_r = R * (0.16 + 0.10 * self.level + pulse * 0.3)
        core = QRadialGradient(c, core_r * 2.2)
        core.setColorAt(0.0, QColor(255, 255, 255, 250))
        core.setColorAt(0.18, QColor(*hot, 235))
        core.setColorAt(0.45, QColor(*main, 150))
        core.setColorAt(1.0, QColor(*main, 0))
        p.setBrush(core)
        p.drawEllipse(c, core_r * 2.2, core_r * 2.2)
        p.end()
