import math
import FreeCAD
import Part

V = FreeCAD.Vector


def rrp(L, W, R, z, seg=24):
    x, y = L / 2.0, W / 2.0
    pts = [V(-x + R, -y, z), V(x - R, -y, z)]
    for cx, cy, a0, a1 in [(x - R, -y + R, -90, 0), (x - R, y - R, 0, 90),
                           (-x + R, y - R, 90, 180), (-x + R, -y + R, 180, 270)]:
        for i in range(seg + 1):
            if i == 0:
                continue
            a = math.radians(a0 + (a1 - a0) * i / seg)
            pts.append(V(cx + R * math.cos(a), cy + R * math.sin(a), z))
        if a1 == 0:      pts.append(V(x, y - R, z))
        elif a1 == 90:   pts.append(V(-x + R, y, z))
        elif a1 == 180:  pts.append(V(-x, -y + R, z))
    return pts


def vol(s):
    try:
        return float(s.Volume)
    except Exception:
        return sum(float(x.Volume) for x in s.Solids)


L, W, H, D, WALL, R = 120.0, 80.0, 45.0, 1.8, 2.4, 4.5
t = math.tan(math.radians(D))
off = WALL / math.cos(math.radians(D))
top_z = H - off


def build(seg):
    p0 = rrp(L, W, R, 0.0, seg)
    p1 = rrp(L - 2 * H * t, W - 2 * H * t, R - H * t, H, seg)
    outer = Part.makeLoft([Part.makePolygon(p0), Part.makePolygon(p1)], True, True, False)
    sx0, sy0, r0 = L - 2 * off + 2 * t, W - 2 * off + 2 * t, R + t - off
    sx1, sy1, r1 = L - 2 * off - 2 * top_z * t, W - 2 * off - 2 * top_z * t, R - top_z * t - off
    cav = Part.makeLoft([Part.makePolygon(rrp(sx0, sy0, r0, -1.0, seg)),
                         Part.makePolygon(rrp(sx1, sy1, r1, top_z, seg))], True, True, False)
    return outer, cav


for seg in (4, 12, 24):
    outer, cav = build(seg)
    inter = outer.common(cav)
    cut = outer.cut(cav)
    print(f"seg={seg:2d} pts={len(rrp(L, W, R, 0, seg)):3d} outer={vol(outer):9.1f} cav={vol(cav):9.1f} "
          f"common={vol(inter):9.1f} cut={vol(cut):9.1f} expect={vol(outer) - vol(cav) + (vol(cav) - vol(inter)):9.1f} "
          f"cutbbox_z=[{cut.BoundBox.ZMin:.3f},{cut.BoundBox.ZMax:.3f}]")

# fix() 修复
outer, cav = build(24)
for tag, o, c in (("raw", outer, cav),
                  ("fix", outer.fix(1e-6, 1e-6, 1e-6), cav.fix(1e-6, 1e-6, 1e-6))):
    r = o.cut(c)
    print(f"{tag:4s} cut={vol(r):9.1f} z=[{r.BoundBox.ZMin:.3f},{r.BoundBox.ZMax:.3f}] valid={r.isValid()} "
          f"outerValid={o.isValid()} cavValid={c.isValid()}")
    # 检查 z<0 与 z>45 是否有实体
    slab_lo = Part.makeBox(400, 400, 10, V(-200, -200, -10))
    slab_hi = Part.makeBox(400, 400, 10, V(-200, -200, 45))
    print(f"     below z=0: {vol(r.common(slab_lo)):8.3f}   above z=45: {vol(r.common(slab_hi)):8.3f}")
