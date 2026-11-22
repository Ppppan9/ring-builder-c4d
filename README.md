# RingBuilder for Cinema 4D

解环关卡 JSON → C4D 场景 + 解环关键帧动画（Python 插件）。与 Blender 端
（ring_level_builder）和 UE5 端共享同一份 `rp_core.py` 解谜内核与 `assets_manifest.json`。

## 关于

本项目由 **ZCode（AI 编程 Agent）全程编写**——基于 GLM 大模型驱动，从需求分析、
架构设计、逐模块实现到 stub 干跑测试全部由 AI 完成，人类负责提需求、验收效果和决策方向。

- AI 模型：GLM（智谱）
- Agent 框架：ZCode CLI
- 人类角色：产品经理 + 测试验收

## 安装

把本目录整包放入 C4D 插件目录（`~/Library/Preferences/MAXON/<C4D 版本>/plugins/`），
重启 C4D。无第三方依赖（纯 c4d + 标准库）。

## 用法

菜单 **扩展 → RingBuilder: 导入关卡 JSON** → 选关卡文件。一条命令完成：
程序化建模（花心/环/扣 + 材质 + 层级）+ 烘焙解环动画（旋转 → 移出 → 缩尾消失），
弹窗汇报环数/扣数/关键帧数/帧范围。

菜单 **扩展 → RingBuilder: 沙粒破碎动画**：建模后按沙粒模式破碎（同步
Blender 0.3.15）——起始帧整环缩没（扣件是子级一起消失），原环切出的实体弧段
沿 C 口依次脱落、绕 Y 翻滚滑出，随后在弧段自身网格表面分批撒出哑光细沙、
减速滑停（俯拍滑动版：以平面滑动替代立式下落）。脚本可调：

```python
bake_sand(doc, json_path, start_sec=0.0, ring_id=None, sections=12,
          grains=240, spread=1.0, reverse=False, sweep_sec=0.6)
```

`ring_id` 指定单环；`sections=1` 为整体脱落；`reverse=True` 从另一端开始；
重跑自动替换上一次的弧段/细沙。默认与 Blender 端同一参数量级
（弧段 ≤14、细沙 240 粒/环、散出速度随「散开幅度」）。

关卡 JSON 来自前端搭建器导出；样例 `rb_level_sample.json`（花心 + 四 C 环，
内核级测试已验证扣点精确、可解）。

## 单位与坐标

1 画布像素 = 0.1 cm；画布 x → C4D X，画布 y（向下）→ C4D -Z（屏幕上下 = Y 轴），
俯视旋转绕 C4D Y 轴（画布顺时针为正 → C4D 取负）。C 环缺口朝局部 +Y。

## 结构

- 环 = PolygonObject（手写顶点：管环 + 半球圆头）+ Phong 标签 + 纹理标签
- 扣子 = 独立 PolygonObject **InsertUnder 到所属环**（相对矩阵换算，解环旋转自动跟随）
- 动画 = CTrack 关键帧（REL_ROTATION.Y / REL_POSITION / REL_SCALE），曲线默认贝塞尔
- 缩尾消失代替 AE 淡出（scale 1 → 0.01，扣子随父级缩没）

## 首跑注意（无本机 C4D 环境，以下为真机首跑排查点）

1. 本插件在 stub 干跑下验证了全部控制流（`tests/test_sand_stub.py` 覆盖
   建模 + 解环 + 碎块 + 沙粒）；C4D 版本差异主要在材质通道常量名
   （`MATERIAL_LUMINANCE_CHANNEL` 等，R21+ 未变）。
2. 相机未生成（MVP 用 C4D 默认视图/自建相机）；平行投影相机加
   `CAMERAOBJECT_PARALLEL_ZOOM` 一行即可，二期。
3. 关键帧插值默认贝塞尔近似 AE easeIn/Out 33%，需要精确可再调切线。
4. 卡通色带：256×1 sRGB PNG（`_ramp_<色>.png`，插件目录自动生成）挂
   color + luminance 双通道，`UVWTag` 径向 UV。若自发光过亮，
   调低 `MATERIAL_LUMINANCE_STRENGTH`（脚本已 try 设置 0.1375）。

## 已含（MVP + 二期）

已含：默认主题 C 环/整环 + T 扣占位箍、**卡通色带材质**（256×1 sRGB 纹理 + UVWTag 径向）、
**三环结道具**（`rb_geom.knot_sections` 暖银）、**钻戒**（`rb_geom.gem_sections`：
环带/六爪粉银 + 刻面钻石，metal/gem 双子对象挂 Null）、**破碎**（`bake_unlock(..., shatter=True)`：
弧段碎片 12 片/环，drift/spin/缩尾 CTrack 动画，原环 hideAt 隐藏）、**沙粒破碎**
（`bake_sand`：实体弧段逐段脱落 → 表面分批撒细沙，与 Blender 端同步）、
解环动画（同一时间轴）。样例关卡 `rb_level_sample.json` / `rb_level_sample2.json`
（含钻戒+三环结）。

## 渲染出片

`setup_render(doc, json_path, out_dir)`：配置 1080×1920@30（画幅=关卡宽高）、
全帧范围、PNG 序列（`ring_####.png`）。出片：Ctrl+R 单帧预览；批量走命令行
`Cinema 4D -nogui -render <工程>.c4d`（先保存工程）。

## 二期路线（剩余）

平行相机、金属/紫水晶主题（影棚反射材质）、C4D 原生 Voronoi Fracture 增强
（当前为弧段碎片）、三环结暖铬影棚材质（当前纯色近似）。
