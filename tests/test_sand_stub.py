# -*- coding: utf-8 -*-
"""沙粒破碎（bake_sand）宿主桩测试：python3 -I tests/test_sand_stub.py"""

import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)

import c4d_stub
c4d_stub.install()

import importlib.util
from importlib.machinery import SourceFileLoader

import c4d

_pyp = os.path.join(ROOT, "ring_builder_c4d.pyp")
_loader = SourceFileLoader("ring_builder_c4d", _pyp)
_spec = importlib.util.spec_from_loader("ring_builder_c4d", _loader)
RB = importlib.util.module_from_spec(_spec)
sys.modules["ring_builder_c4d"] = RB
_loader.exec_module(RB)

SAMPLE = os.path.join(ROOT, "rb_level_sample.json")


def plane_dist(v):
    return math.hypot(v.x, v.z)


def main():
    doc = c4d.Document()
    r = RB.build(doc, SAMPLE)
    assert r["rings"] >= 1 and r["clasps"] >= 1, r
    # 旧功能回归：解环动画 + 碎块模式不受沙粒改动影响
    u0 = RB.bake_unlock(doc, SAMPLE, shatter=True)
    assert u0["ok"] and u0["keys"] > 0, u0
    # 沙粒在全新文档上执行（避免与已有解环缩尾轨道叠加）
    doc = c4d.Document()
    RB.build(doc, SAMPLE)
    u = RB.bake_sand(doc, SAMPLE)
    assert u["ok"], u
    assert u["sections"] == r["rings"] * 12, u
    assert u["grains"] == r["rings"] * 240, u
    assert u["frames"][1] > 0
    # 重跑清理：旧弧段/细沙不残留
    assert RB.bake_sand(doc, SAMPLE)["grains"] == u["grains"], "重跑替换而不是叠加"

    rings = RB._ring_objects(doc)
    assert len(rings) == r["rings"], sorted(rings)
    rid = sorted(rings)[0]
    ring = rings[rid]
    scale_track = c4d_stub.find_track(ring, c4d.ID_BASEOBJECT_REL_SCALE)
    assert scale_track is not None
    keys = c4d_stub.track_key_values(scale_track)
    assert abs(keys[0][0]) < 1e-6 and abs(keys[0][1].x - 1.0) < 1e-6, keys[:2]
    assert abs(keys[1][1].x) < 0.02, "整环在起始帧缩没"

    carriers = [o for o in doc.objects if o.name.startswith("RP_Sand_%s_" % rid)]
    assert len(carriers) == 12, len(carriers)
    carrier = carriers[0]
    pos_track = c4d_stub.find_track(carrier, c4d.ID_BASEOBJECT_REL_POSITION)
    rot_track = c4d_stub.find_track(carrier, c4d.ID_BASEOBJECT_REL_ROTATION)
    assert pos_track and rot_track
    pos_keys = c4d_stub.track_key_values(pos_track)
    times = [t for t, _v in pos_keys]
    assert times == sorted(times) and len(times) >= 4, times
    assert all(abs(v.y) < 1e-9 for _t, v in pos_keys), "俯拍滑动：弧段不离开地面平面"
    d0 = plane_dist(pos_keys[0][1])
    d_last = plane_dist(pos_keys[-1][1])
    assert d_last > d0 + 1.0, (d0, d_last)
    rot_values = [v for _t, v in c4d_stub.track_key_values(rot_track)]
    assert rot_values[0] == 0.0 and abs(rot_values[-1]) > 0.05, "弧段翻滚自转"
    carrier_scale = c4d_stub.find_track(carrier, c4d.ID_BASEOBJECT_REL_SCALE)
    scale_keys = c4d_stub.track_key_values(carrier_scale)
    assert abs(scale_keys[1][1].x - 1.0) < 1e-6
    assert abs(scale_keys[-2][1].x - 0.10) < 1e-6, scale_keys
    assert abs(scale_keys[-1][1].x) < 0.02, "弧段在撒沙结束后缩没"

    grains = [o for o in doc.objects if o.name.startswith("RP_Grain_%s_" % rid)]
    assert len(grains) == 240, len(grains)
    grain = grains[0]
    gpos = c4d_stub.find_track(grain, c4d.ID_BASEOBJECT_REL_POSITION)
    gkeys = c4d_stub.track_key_values(gpos)
    gtimes = [t for t, _v in gkeys]
    assert gtimes == sorted(gtimes) and abs(gtimes[0] - 0.1667) < 0.034, gtimes[:3]
    travel = [plane_dist(v) for _t, v in gkeys]
    assert travel[-1] > travel[0] + 1.0, "细沙从弧段表面滑出"
    span = [math.hypot(gkeys[i + 1][1].x - gkeys[i][1].x,
                       gkeys[i + 1][1].z - gkeys[i][1].z)
            for i in range(len(gkeys) - 1)]
    assert sum(span[:3]) > sum(span[-3:]), "细沙减速滑停"
    assert all(abs(v.y) < 1e-6 for _t, v in gkeys[-2:]), "细沙贴地停住"
    birth = [v for t, v in gkeys if t <= 0.2][-1]
    carrier_at_birth = [v for t, v in pos_keys if abs(t - gtimes[0]) < 0.034]
    assert carrier_at_birth, "细沙出生帧与弧段重叠"
    gap = math.hypot(carrier_at_birth[-1].x - birth.x,
                     carrier_at_birth[-1].z - birth.z)
    # 细沙出生在弧段表面：到弧段原点距离 ≈ 环中线半径 ± 管半径
    s0 = rings[rid].rel_scale.x
    assert (RB.MID_RADIUS - RB.TUBE_DEFAULT) * s0 - 1.0 < gap \
        < (RB.MID_RADIUS + RB.TUBE_DEFAULT) * s0 + 1.0, (gap, s0)

    doc2 = c4d.Document()
    RB.build(doc2, SAMPLE)
    u2 = RB.bake_sand(doc2, SAMPLE, ring_id=sorted(rings)[0], sections=6,
                      grains=60, sweep_sec=0.3, reverse=True)
    assert u2["sections"] == 6 and u2["grains"] == 60, u2
    carriers2 = [o for o in doc2.objects if o.name.startswith("RP_Sand_")]
    detach = []
    for o in carriers2:
        track = c4d_stub.find_track(o, c4d.ID_BASEOBJECT_REL_POSITION)
        detach.append(c4d_stub.track_key_values(track)[0][0])
    assert detach == sorted(detach, reverse=True), "reverse=True 从另一端开始"
    assert detach[-1] - detach[0] < 0.35, detach
    print("C4D SAND STUB: ALL PASS (%d rings, %d sections, %d grains)"
          % (r["rings"], u["sections"], u["grains"]))


main()
