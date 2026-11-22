# -*- coding: utf-8 -*-
"""Headless fake `c4d` module：覆盖 ring_builder_c4d 建模/沙粒烘焙用到的 API 子集，
关键帧/对象全部记录在 Python 对象上供断言。仅测试用。"""

import math
import sys
import types


class Vector:
    __slots__ = ("x", "y", "z")

    def __init__(self, x=0.0, y=0.0, z=0.0):
        self.x, self.y, self.z = float(x), float(y), float(z)

    def __add__(self, o):
        return Vector(self.x + o.x, self.y + o.y, self.z + o.z)

    def __sub__(self, o):
        return Vector(self.x - o.x, self.y - o.y, self.z - o.z)

    def __mul__(self, k):
        return Vector(self.x * k, self.y * k, self.z * k)

    __rmul__ = __mul__

    def __repr__(self):
        return "Vector(%g, %g, %g)" % (self.x, self.y, self.z)


class Matrix:
    def __mul__(self, o):
        return Matrix()

    def __invert__(self):
        return Matrix()


class BaseTime:
    def __init__(self, seconds):
        self.seconds = float(seconds)


class DescLevel:
    def __init__(self, *args):
        self.args = args


class DescID:
    def __init__(self, *levels):
        self.levels = levels


class Key:
    def __init__(self):
        self.time = None
        self.value = None

    def SetTime(self, t):
        self.time = t.seconds

    def SetValue(self, curve, value):
        self.value = value


class Curve:
    def __init__(self):
        self.keys = []

    def InsertKey(self, key):
        self.keys.append(key)
        return key


class CTrack:
    def __init__(self, owner, desc):
        self.owner = owner
        self.desc = desc
        self.curve = Curve()

    def GetCurve(self):
        return self.curve


class Tag:
    def __init__(self, kind):
        self.kind = kind
        self.data = {}

    def __setitem__(self, key, value):
        self.data[key] = value

    def __getitem__(self, key):
        return self.data.get(key)


class BaseList2D:
    def __init__(self, kind=None):
        self.name = ""
        self.kind = kind
        self.data = {}
        self.tags = []
        self.shaders = []
        self.tracks = []

    def SetName(self, name):
        self.name = name

    def GetName(self):
        return self.name

    def __setitem__(self, key, value):
        self.data[key] = value

    def __getitem__(self, key):
        return self.data.get(key)

    def InsertTag(self, tag):
        tag.owner = self
        self.tags.append(tag)
        return tag

    def InsertShader(self, shader):
        self.shaders.append(shader)
        return shader

    def InsertTrackSorted(self, track):
        track.owner = self
        self.tracks.append(track)
        return track


class BaseObject(BaseList2D):
    def __init__(self, kind=None):
        super().__init__()
        self.kind = kind
        self.rel_pos = Vector()
        self.rel_rot = Vector()
        self.rel_scale = Vector(1.0, 1.0, 1.0)
        self.children = []
        self.parent = None
        self.doc = None

    def SetRelPos(self, v):
        self.rel_pos = v

    def SetRelRot(self, v):
        self.rel_rot = v

    def SetRelScale(self, v):
        self.rel_scale = v

    def GetRelScale(self):
        return self.rel_scale

    def InsertUnder(self, parent):
        parent.children.append(self)

    def GetChildren(self):
        return list(self.children)

    def GetMgn(self):
        return Matrix()

    def SetMl(self, m):
        self.rel_matrix = m

    def Remove(self):
        if self.parent is not None and self in self.parent.children:
            self.parent.children.remove(self)
        elif self.doc is not None and self in self.doc:
            self.doc.remove(self)


class PolygonObject(BaseObject):
    def __init__(self, point_count=0, poly_count=0):
        super().__init__()
        self.points = [None] * point_count
        self.polys = [None] * poly_count
        self.messages = []

    def SetPoint(self, i, v):
        self.points[i] = v

    def SetPolygon(self, i, p):
        self.polys[i] = p

    def Message(self, msg):
        self.messages.append(msg)


class CPolygon:
    def __init__(self, a, b, c, d):
        self.a, self.b, self.c, self.d = a, b, c, d


class UVWTag(Tag):
    def __init__(self, count):
        super().__init__("UVW")
        self.count = count

    def Set(self, i, *corners):
        self.data[i] = corners


class TextureTag(Tag):
    def __init__(self):
        super().__init__("Texture")
        self.material = None

    def SetMaterial(self, mat):
        self.material = mat


class Material(BaseList2D):
    def __init__(self):
        super().__init__()
        self.updated = False

    def Update(self, a, b):
        self.updated = True


class BaseBitmap:
    def __init__(self):
        self.size = None
        self.pixels = []
        self.saved = []

    def Init(self, w, h):
        self.size = (w, h)

    def SetPixel(self, x, y, r, g, b):
        self.pixels.append((x, y, r, g, b))

    def Save(self, path, fmt):
        self.saved.append((path, fmt))
        return 1


class Document:
    def __init__(self):
        self.objects = []
        self.materials = []
        self.render_data = {}

    def InsertObject(self, obj, parent=None):
        if parent is not None:
            parent.children.append(obj)
        else:
            self.objects.append(obj)
        obj.parent = parent if parent is not None else None
        obj.doc = self.objects

    def GetObjects(self):
        return list(self.objects)

    def InsertMaterial(self, mat):
        self.materials.append(mat)

    def SetRenderData(self, rd):
        self.render_data = rd

    def GetRenderData(self):
        return self.render_data


def track_key_values(track):
    """[(time_seconds, value), ...] 按插入顺序。"""
    return [(k.time, k.value) for k in track.curve.keys]


def find_track(obj, desc_arg):
    """按 DescLevel 首参匹配轨道（REL_POSITION / REL_ROTATION / REL_SCALE）。"""
    for track in obj.tracks:
        levels = track.desc.levels
        if levels and levels[0].args and levels[0].args[0] == desc_arg:
            return track
    return None


def install():
    mod = types.ModuleType("c4d")
    consts = {}

    def _const(name):
        if name not in consts:
            consts[name] = len(consts) + 4096
        return consts[name]

    mod.__getattr__ = _const
    mod.Vector = Vector
    mod.Matrix = Matrix
    mod.BaseTime = BaseTime
    mod.DescLevel = DescLevel
    mod.DescID = DescID
    mod.CKey = Key
    mod.CTrack = CTrack
    mod.BaseTag = Tag
    mod.UVWTag = UVWTag
    mod.TextureTag = TextureTag
    mod.Material = Material
    mod.BaseList2D = BaseList2D
    mod.BaseObject = BaseObject
    mod.PolygonObject = PolygonObject
    mod.CPolygon = CPolygon
    mod.BaseBitmap = BaseBitmap
    mod.Document = Document
    mod.EventAdd = lambda: None

    bitmaps = types.ModuleType("c4d.bitmaps")
    bitmaps.BaseBitmap = BaseBitmap
    bitmaps.__getattr__ = _const
    mod.bitmaps = bitmaps

    plugins = types.ModuleType("c4d.plugins")
    plugins.registered = []

    class CommandData:
        pass

    plugins.CommandData = CommandData
    plugins.RegisterCommandPlugin = lambda **kw: plugins.registered.append(kw)
    mod.plugins = plugins

    gui = types.ModuleType("c4d.gui")
    gui.dialogs = []
    gui.paths = []
    gui.LoadDialog = lambda **kw: gui.paths.append(kw) and None
    gui.MessageDialog = lambda text: gui.dialogs.append(text)
    mod.gui = gui

    sys.modules["c4d"] = mod
    sys.modules["c4d.bitmaps"] = bitmaps
    sys.modules["c4d.plugins"] = plugins
    sys.modules["c4d.gui"] = gui
    return mod
