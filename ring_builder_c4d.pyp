# -*- coding: utf-8 -*-
"""RingBuilder for Cinema 4D：解环关卡 JSON → C4D 场景 + 解环关键帧动画。

与 Blender 端（ring_level_builder）和 UE5 端（RingBuilder 插件）共享 rp_core 解谜内核。
单位约定：1 画布像素 = 0.1 cm（C4D 默认 cm）；画布 x → C4D X，画布 y（向下）→ C4D -Y，
竖直向上 = C4D Y。缺口朝局部 +Y（画布上方）。

安装：本目录整包放入 C4D 插件目录（如 ~/Library/Preferences/MAXON/<版本>/plugins/），
重启 C4D → 扩展菜单 →「RingBuilder: 导入关卡 JSON」→ 选关卡文件。
"""

import json
import math
import os
import sys

import c4d
import c4d.bitmaps
from c4d import plugins, gui

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.append(HERE)

import rp_core as C          # noqa: E402  共享解谜内核
import rb_toon as T          # noqa: E402  共享卡通色带内核
import rb_geom as G          # noqa: E402  三环结/钻戒几何内核

PX_CM = 0.1
GAP_3D_DEG = 80.0
TUBE_DEFAULT = 24.715 * PX_CM
MID_RADIUS = 151.06 * PX_CM
N_SEG, M_SEG, K_CAP = 56, 14, 5

RING_HEX = {"red": "dc3247", "orange": "ec8a23", "green": "24b24a",
            "blue": "3a6fde", "cyan": "33a9e0", "purple": "8c45dc",
            "silver": "c8ccd2", "ground": "6b7078",
            "gem_silver": "c8bcc0", "gem": "dfe8fb", "knot": "c4b3a2"}
GEM_MAT = {"metal": "gem_silver", "gem": "gem"}


def _sect_mesh(doc, parent, name, verts_cm, tris, mat):
    """rb_geom section（顶点 cm + 三角索引）→ PolygonObject。parent=None 时挂文档顶层。"""
    pts = [c4d.Vector(v[0], v[1], v[2]) for v in verts_cm]
    polys = [(tris[i], tris[i + 1], tris[i + 2], tris[i + 2])
             for i in range(0, len(tris), 3)]
    obj = _make_mesh(name, pts, polys, mat)
    if parent is not None:
        doc.InsertObject(obj, parent)
    else:
        doc.InsertObject(obj)
    return obj


def _sect_group(doc, root, label, sections, mats):
    """sections → Null 父级；同材质 kind 合并为一个子对象（钻戒 metal/gem、三环结 metal）。
    mats = {mat_key: Material}。返回 null。"""
    parent = c4d.BaseObject(c4d.Null)
    parent.SetName(label)
    doc.InsertObject(parent, root)
    groups = {}
    for verts_cm, tris, normals, uvs, kind in sections:
        mk = GEM_MAT.get(kind, kind)
        if mk not in groups:
            groups[mk] = ([], [])
        groups[mk][0].extend(verts_cm)
        groups[mk][1].extend(tris)
    for mk, (v, t) in groups.items():
        _sect_mesh(doc, parent, label + "_" + mk, v, t, mats.get(mk))
    return parent

PLUGIN_ID = 1066317
MENU_STR = "RingBuilder: 导入关卡 JSON"


def _hex_lin(hexstr):
    """sRGB hex → C4D 线性色。"""
    rgb = T._hex_lin(hexstr)
    return c4d.Vector(rgb[0], rgb[1], rgb[2])


# ---------------------------------------------------------------------------
# 几何（同 UE 端公式：管环 + 半球圆头，缺口朝局部 +Y）
# ---------------------------------------------------------------------------


def _tube_polys(radius_cm, tube_cm, gap_deg):
    """返回 (points, polys, uvs)，polys 为 (a, b, c, d) 四元组（三角时 c==d），
    uvs 为逐点 (tube 径向 u,) —— 卡通色带纹理的 u 采样（内沿 0 → 外沿 1）。"""
    if gap_deg > 0:
        a0, arc = 90.0 + gap_deg / 2.0, 360.0 - gap_deg
    else:
        a0, arc = 0.0, 360.0
    pts, polys, uvs = [], [], []
    rings = []
    for i in range(N_SEG + 1):
        u = math.radians(a0 + arc * i / N_SEG)
        cu, su = math.cos(u), math.sin(u)
        loop = []
        for j in range(M_SEG):
            v = j / M_SEG * 2 * math.pi
            rad = radius_cm + tube_cm * math.cos(v)
            loop.append(len(pts))
            uvs.append(T.tube_to_u(math.cos(v)))
            pts.append(c4d.Vector(rad * cu, tube_cm * math.sin(v), rad * su))
        rings.append(loop)
    for i in range(N_SEG):
        a, b = rings[i], rings[i + 1]
        for j in range(M_SEG):
            k1 = (j + 1) % M_SEG
            polys.append((a[j], a[k1], b[k1], b[j]))
    if gap_deg > 0:
        for u, sign, prev in ((math.radians(a0), -1, rings[0]),
                              (math.radians(a0 + arc), 1, rings[-1])):
            c = c4d.Vector(radius_cm * math.cos(u), 0.0,
                           radius_cm * math.sin(u))
            rad_d = c4d.Vector(math.cos(u), 0.0, math.sin(u))
            tan_d = c4d.Vector(-math.sin(u) * sign, 0.0, math.cos(u) * sign)
            for step in range(1, K_CAP):
                w = math.pi / 2 * step / K_CAP
                cur = []
                for j in range(M_SEG):
                    v = j / M_SEG * 2 * math.pi
                    d = (rad_d * math.cos(v) * math.cos(w)
                         + tan_d * math.sin(w)) * tube_cm
                    cur.append(len(pts))
                    uvs.append(T.tube_to_u(math.cos(v) * math.cos(w)))
                    pts.append(c + d)
                for j in range(M_SEG):
                    k1 = (j + 1) % M_SEG
                    polys.append((prev[j], prev[k1], cur[k1], cur[j]))
                prev = cur
            pole = len(pts)
            uvs.append(1.0)
            pts.append(c + tan_d * tube_cm)
            for j in range(M_SEG):
                k1 = (j + 1) % M_SEG
                polys.append((prev[j], prev[k1], pole, pole))
    return pts, polys, uvs


def _cyl_polys(r, depth, seg=14):
    """实心短圆柱（轴向 X）：T 扣占位体。"""
    pts, polys = [], []
    for x in (-depth / 2, depth / 2):
        for j in range(seg):
            a = j / seg * 2 * math.pi
            pts.append(c4d.Vector(x, r * math.cos(a), r * math.sin(a)))
    for j in range(seg):
        k1 = (j + 1) % seg
        polys.append((j, k1, seg + k1, seg + j))
        polys.append((0, 0, k1, j))
        polys.append((seg, seg, seg + j, seg + k1))
    return pts, polys


def _make_mesh(name, pts, polys, mat, uvs=None):
    obj = c4d.PolygonObject(len(pts), len(polys))
    obj.SetName(name)
    for i, p in enumerate(pts):
        obj.SetPoint(i, p)
    for i, q in enumerate(polys):
        obj.SetPolygon(i, c4d.CPolygon(*q))
    obj.Message(c4d.MSG_UPDATE)
    phong = c4d.BaseTag(c4d.Tphong)
    phong[c4d.PHONGTAG_PHONG_ANGLE] = 40
    obj.InsertTag(phong)
    if uvs is not None:
        uvw = c4d.UVWTag(len(polys))
        for i, q in enumerate(polys):
            corners = []
            for k in q:
                u = uvs[k]
                corners.append(c4d.Vector(u, 0.0, 0.0))
            uvw.Set(i, *corners)
        obj.InsertTag(uvw)
    if mat is not None:
        tag = c4d.TextureTag()
        tag.SetMaterial(mat)
        obj.InsertTag(tag)
    return obj


def _make_mat(name, hexstr, lum=0.55):
    mat = c4d.Material()
    mat.SetName(name)
    col = _hex_lin(hexstr)
    mat[c4d.MATERIAL_COLOR_COLOR] = col * 0.45
    mat[c4d.MATERIAL_LUMINANCE_CHANNEL] = True
    mat[c4d.MATERIAL_LUMINANCE_COLOR] = col * lum
    return mat


def _make_toon_mat(name, hexstr):
    """卡通色带材质：256×1 sRGB 渐变纹理（BaseBitmap 生成 PNG），
    color 通道贴图（受光底色）+ luminance 同贴图（自发光感）。"""
    bmp = c4d.bitmaps.BaseBitmap()
    bmp.Init(T.RAMP_W, 1)
    for x, (r, g, b) in enumerate(T.toon_rgb_row(hexstr)):
        bmp.SetPixel(x, 0, r, g, b)
    png = os.path.join(HERE, "_ramp_%s.png" % name.rsplit("_", 1)[-1])
    bmp.Save(png, c4d.FILTER_PNG)
    mat = c4d.Material()
    mat.SetName(name)
    sh = c4d.BaseList2D(c4d.Xbitmap)
    sh[c4d.BITMAPSHADER_FILENAME] = png
    mat.InsertShader(sh)
    mat[c4d.MATERIAL_COLOR_SHADER] = sh
    mat[c4d.MATERIAL_LUMINANCE_CHANNEL] = True
    mat[c4d.MATERIAL_LUMINANCE_SHADER] = sh
    try:
        mat[c4d.MATERIAL_LUMINANCE_STRENGTH] = T.TOON_EMISSION * 0.25
    except (AttributeError, TypeError):
        pass
    mat.Update(True, True)
    return mat


# ---------------------------------------------------------------------------
# 关键帧（解环动画：绕 C4D Y 轴 = 俯视旋转；画布顺时针 → C4D 取负）
# ---------------------------------------------------------------------------


def _rot_track(doc, obj, keys_sec):
    """keys_sec = [(t_seconds, canvas_deg), ...]。"""
    track = c4d.CTrack(obj, c4d.DescID(c4d.DescLevel(c4d.ID_BASEOBJECT_REL_ROTATION),
                                       c4d.DescLevel(c4d.VECTOR_Y)))
    obj.InsertTrackSorted(track)
    curve = track.GetCurve()
    for t, deg in keys_sec:
        key = c4d.CKey()
        key.SetTime(c4d.BaseTime(t))
        key.SetValue(curve, math.radians(-deg))
        curve.InsertKey(key)
    return track


def _pos_track(doc, obj, keys_cm):
    track = c4d.CTrack(obj, c4d.DescID(c4d.DescLevel(c4d.ID_BASEOBJECT_REL_POSITION)))
    obj.InsertTrackSorted(track)
    curve = track.GetCurve()
    for t, p in keys_cm:
        key = c4d.CKey()
        key.SetTime(c4d.BaseTime(t))
        key.SetValue(curve, c4d.Vector(p[0], 0.0, p[1]))
        curve.InsertKey(key)
    return track


def _scale_track(doc, obj, keys_s):
    track = c4d.CTrack(obj, c4d.DescID(c4d.DescLevel(c4d.ID_BASEOBJECT_REL_SCALE)))
    obj.InsertTrackSorted(track)
    curve = track.GetCurve()
    for t, s in keys_s:
        key = c4d.CKey()
        key.SetTime(c4d.BaseTime(t))
        key.SetValue(curve, c4d.Vector(s, s, s))
        curve.InsertKey(key)
    return track


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

RB_DOC_DATA = "rp_level"


def build(doc, json_path):
    with open(json_path, "r", encoding="utf-8") as f:
        L = json.load(f)
    C.validate_level(L)
    mats = {}
    for key, hexstr in RING_HEX.items():
        mats[key] = _make_mat("RB_Mat_" + key, hexstr)
        doc.InsertMaterial(mats[key])
    root = c4d.BaseObject(c4d.Null)
    root.SetName("解环关卡")
    doc.InsertObject(root)
    rings = {r["id"]: r for r in L["rings"]}
    ring_objs = {}
    for r in sorted(L["rings"], key=lambda q: q.get("z", 0)):
        a = C.asset(r["asset"])
        if a.get("gem"):
            # 钻戒：环带+钻石+六爪（rb_geom 内核顶点表，metal/gem 双材质）
            parent = _sect_group(doc, root, "RP_Ring_" + r["id"],
                                 G.gem_sections(a.get("gemAngle", -90.0)),
                                 mats)
            s = r["scale"] / 100.0
            parent.SetRelPos(c4d.Vector(r["x"] * PX_CM, 0.0, -r["y"] * PX_CM))
            parent.SetRelScale(c4d.Vector(s, s, s))
            parent.SetRelRot(c4d.Vector(0.0, math.radians(-r["rotation"]), 0.0))
            ring_objs[r["id"]] = parent
            continue
        gap = GAP_3D_DEG if a.get("shape") == "gap" else 0.0
        color = a.get("color", "blue")
        pts, polys, uvs = _tube_polys(MID_RADIUS, TUBE_DEFAULT, gap)
        toon = _make_toon_mat("RB_Toon_" + color, RING_HEX.get(color, "888888"))
        doc.InsertMaterial(toon)
        obj = _make_mesh("RP_Ring_" + r["id"], pts, polys, toon, uvs=uvs)
        s = r["scale"] / 100.0
        obj.SetRelPos(c4d.Vector(r["x"] * PX_CM, 0.0, -r["y"] * PX_CM))
        obj.SetRelScale(c4d.Vector(s, s, s))
        obj.SetRelRot(c4d.Vector(0.0, math.radians(-r["rotation"]), 0.0))
        doc.InsertObject(obj, root)
        ring_objs[r["id"]] = obj
    # 三环结等静态道具（不可解，扣子可挂）
    for q in sorted(L.get("props") or [], key=lambda q: q.get("z", 0)):
        pa = C.asset(q["asset"])
        if pa.get("kind") != "prop":
            continue
        parent = _sect_group(doc, root, "RP_Prop_" + q["id"],
                             G.knot_sections(), mats)
        parent.SetRelPos(c4d.Vector(q["x"] * PX_CM, 0.0, -q["y"] * PX_CM))
        s = q["scale"] / 100.0
        parent.SetRelScale(c4d.Vector(s, s, s))
        parent.SetRelRot(c4d.Vector(0.0, math.radians(-q.get("rotation", 0)), 0.0))
    for c in L["clasps"]:
        A = rings.get(c["ringId"])
        if A is None:
            continue
        hook = C.hook_point(A, c)
        w_ = C.clasp_world(A, c)
        cs = c["scale"] / 100.0
        pts, polys = _cyl_polys(TUBE_DEFAULT * 1.24 * cs,
                                TUBE_DEFAULT * 1.9 * cs)
        obj = _make_mesh("RP_Clasp_" + c["id"], pts, polys, mats["silver"])
        obj.SetRelPos(c4d.Vector(hook["x"] * PX_CM, 0.0, -hook["y"] * PX_CM))
        obj.SetRelRot(c4d.Vector(0.0, math.radians(-w_["rotation"]), 0.0))
        doc.InsertObject(obj, root)
        parent = ring_objs.get(c["ringId"])
        if parent is not None:
            mg_parent = parent.GetMgn()
            mg_self = obj.GetMgn()
            obj.InsertUnder(parent)
            obj.SetMl(~mg_parent * mg_self)
    return {"rings": len(ring_objs), "clasps": len(L["clasps"]), "root": root}


def bake_unlock(doc, json_path, start_sec=0.0, shatter=False):
    """解环动画：旋转步 → 移出 → 缩尾消失（扣子是子级随环缩没）。
    shatter=True 时按 rp_core 碎片计划生成弧段碎片（drift/spin/缩尾）。"""
    with open(json_path, "r", encoding="utf-8") as f:
        L = json.load(f)
    fps = int(L.get("fps") or 30)
    T = C.bake_timeline(L, {"moveOut": True, "fade": True, "shatter": shatter,
                            "shards": 12, "shatterSec": 0.8},
                        start=start_sec)
    if not T.get("ok"):
        raise ValueError(T.get("error") or "解谜时间轴生成失败")
    objs = {}
    def _walk(o):
        if o.GetName().startswith("RP_Ring_"):
            objs[o.GetName()[len("RP_Ring_"):]] = o
        for ch in o.GetChildren():
            _walk(ch)
    for top in doc.GetObjects():
        _walk(top)
    base = {r["id"]: r for r in L["rings"]}
    n = 0
    for k in T["keys"]:
        obj = objs.get(k["ring"])
        if obj is None:
            continue
        r0 = base[k["ring"]]["rotation"]
        _rot_track(doc, obj, [(k["t0"], r0 + k["v0"]), (k["t1"], r0 + k["v1"])])
        n += 2
    for O in T["outros"]:
        obj = objs.get(O["ring"])
        if obj is None:
            continue
        r = base[O["ring"]]
        rot0 = r["rotation"]
        mv = O.get("move")
        if mv:
            _pos_track(doc, obj, [
                (mv["t0"], (mv["from"][0] * PX_CM, -mv["from"][1] * PX_CM)),
                (mv["t1"], (mv["to"][0] * PX_CM, -mv["to"][1] * PX_CM))])
        if O.get("op"):
            s = r["scale"] / 100.0
            _scale_track(doc, obj, [(O["op"][0][0], s), (O["op"][-1][0], 0.01)])
        n += 4
        if O.get("shards"):
            # 原环 hideAt 隐藏；碎片 drift/spin/缩尾（世界坐标，Ry 旋转映射）
            _scale_track(doc, obj, [(O["hideAt"], r["scale"] / 100.0),
                                    (O["hideAt"] + 1 / fps, 0.01)])
            a = C.asset(r["asset"])
            color = a.get("color", "blue")
            toon = _make_toon_mat("RB_Toon_" + color,
                                  RING_HEX.get(color, "888888"))
            doc.InsertMaterial(toon)
            s = r["scale"] / 100.0
            rot0 = r["rotation"]
            th = math.radians(-rot0)
            for sh in O["shards"]:
                verts_cm, tris, normals = G.shard_mesh(
                    MID_RADIUS, TUBE_DEFAULT, sh["a0"], sh["a1"])
                sh_obj = _sect_mesh(doc, None,
                                    "RP_Shard_%s_%d" % (O["ring"], sh["i"]),
                                    verts_cm, tris, toon)
                sh_obj.SetRelPos(c4d.Vector(r["x"] * PX_CM, 0.0,
                                            -r["y"] * PX_CM))
                sh_obj.SetRelRot(c4d.Vector(0.0, math.radians(-rot0), 0.0))
                sh_obj.SetRelScale(c4d.Vector(s, s, s))
                # 世界漂移：局部 canvas (dx, dy↓) → C4D (x, z=-dy) 绕 Y 转 th
                lx, lz = sh["drift"][0] * s * PX_CM, -sh["drift"][1] * s * PX_CM
                wx = lx * math.cos(th) + lz * math.sin(th)
                wz = -lx * math.sin(th) + lz * math.cos(th)
                px0 = r["x"] * PX_CM
                pz0 = -r["y"] * PX_CM
                _pos_track(doc, sh_obj, [
                    (sh["tb"], (px0, pz0)),
                    (sh["t1"], (px0 + wx, pz0 + wz))])
                _rot_track(doc, sh_obj, [
                    (sh["tb"], rot0), (sh["t1"], rot0 + sh["spin"])])
                _scale_track(doc, sh_obj, [
                    (sh["op"][0][0], s), (sh["op"][-1][0], 0.01)])
                n += 6
    c4d.EventAdd()
    return {"ok": True, "keys": n, "frames": [0, round(T["end"] * fps)]}


class RingBuilderCommand(plugins.CommandData):

    def Execute(self, doc):
        path = gui.LoadDialog(title="选择解环关卡 JSON", suffix="json")
        if not path:
            return True
        try:
            r = build(doc, path)
            u = bake_unlock(doc, path)
            gui.MessageDialog(
                "RingBuilder 导入完成\n环 %d · 扣 %d\n解环动画 %d 关键帧（第 %d–%d 帧）"
                % (r["rings"], r["clasps"], u["keys"],
                   u["frames"][0], u["frames"][1]))
        except Exception as exc:
            gui.MessageDialog("RingBuilder 失败：%s" % exc)
            return False
        c4d.EventAdd()
        return True

    def RestoreLayout(self, sec_ref):
        return True


if __name__ == "__main__":
    plugins.RegisterCommandPlugin(
        id=PLUGIN_ID, str=MENU_STR, info=0,
        help="读取 ring_level_builder 前端搭建器导出的关卡 JSON，"
             "程序化建模（共享 rp_core 解谜内核）并烘焙解环动画",
        bitmap=None, dat=RingBuilderCommand())


def setup_render(doc, json_path, out_dir="/renders/ring_ad",
                 prefix="ring_", end_sec=None):
    """配置渲染参数（广告画幅 1080×1920@30 / 全帧范围 / PNG 序列输出）。
    end_sec 缺省 = bake_timeline 全长。渲染：Ctrl+R 单帧或命令行
    Cinema4D -nogui -render <工程>.c4d 批量出片。"""
    with open(json_path, "r", encoding="utf-8") as f:
        L = json.load(f)
    fps = int(L.get("fps") or 30)
    if end_sec is None:
        T = C.bake_timeline(L, {"moveOut": True, "fade": True})
        end_sec = float(T["end"]) if T.get("ok") else 6.0
    rd = doc.GetRenderData()
    rd[c4d.RDATA_X] = L["width"]
    rd[c4d.RDATA_Y] = L["height"]
    rd[c4d.RDATA_FRAMERATE] = float(fps)
    rd[c4d.RDATA_FROM] = 0
    rd[c4d.RDATA_TO] = int(math.ceil(end_sec * fps))
    rd[c4d.RDATA_PATH] = os.path.join(out_dir, prefix + "_####.png")
    rd[c4d.RDATA_FORMAT] = c4d.FILTER_PNG
    doc.SetRenderData(rd)
    c4d.EventAdd()
    return {"ok": True, "res": "%dx%d" % (L["width"], L["height"]),
            "fps": fps, "frames": [0, int(math.ceil(end_sec * fps))],
            "out": rd[c4d.RDATA_PATH]}
