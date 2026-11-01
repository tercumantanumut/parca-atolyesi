"""Cel-shaded still of a mesh on a transparent background (headless Blender 4.2+).

  blender -b --factory-startup -P blender/toon_still.py -- --girdi textured.glb --cikti toon_ucceyrek.png \
      [--aci on|ucceyrek|yan] [--boyut 1024] [--yukseklik 6] [--cizgi 1.0] [--duz]

The mesh is expected in the Hunyuan frame (Y up, front +Z), which Blender imports as Z up facing -Y. The camera is
fixed (orthographic, slightly above, looking at the front); the model turns: `on` = front, `ucceyrek` = three-quarter,
`yan` = profile facing screen right.

The look is analytic and light-free (emission): albedo x a 3-tone hue-shifted ramp of a warm key light from the camera
side and above, plus a 2-tone cool rim from behind. The key reads surface normals blurred over the mesh, so the light
bands follow the big forms instead of every small fold of a generated mesh. An inverted-hull outline (--cizgi, in
thousandths of the model height; 0 = off) draws the silhouette and the big inner contours.

Without a texture the albedo is the mesh's vertex colours (e.g. P3-SAM part colours) or, if none, clay.
"""
import argparse
import json
import math
import sys
import time

import bpy
from mathutils import Vector

ACILAR = {"on": 0.0, "ucceyrek": -35.0, "yan": -90.0}  # model yaw about Z (deg); negative = faces screen right
KIL = (0.70, 0.66, 0.61, 1.0)


def args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser(prog="toon_still")
    ap.add_argument("--girdi", required=True, action="append", help="GLB/OBJ; repeat for several files (parts)")
    ap.add_argument("--cikti", required=True)
    ap.add_argument("--aci", choices=list(ACILAR), default="ucceyrek")
    ap.add_argument("--boyut", type=int, default=1024)
    ap.add_argument("--yukseklik", type=float, default=6.0, help="camera elevation in degrees")
    ap.add_argument("--cizgi", type=float, default=1.0, help="outline width in 1/1000 of the model height; 0 = none")
    ap.add_argument("--yumusak", type=int, default=8, help="normal blur iterations for the light bands; 0 = off")
    ap.add_argument("--duz", action="store_true", help="flat albedo only (no light bands)")
    return ap.parse_args(argv)


# ---------------------------------------------------------------- scene
def ice_al(yol):
    once = set(bpy.data.objects)
    if yol.lower().endswith(".obj"):
        bpy.ops.wm.obj_import(filepath=yol)
    else:
        bpy.ops.import_scene.gltf(filepath=yol)
    return [o for o in bpy.data.objects if o not in once and o.type == "MESH"]


def sinirlar(objs):
    pts = [o.matrix_world @ Vector(c) for o in objs for c in o.bound_box]
    lo = Vector([min(p[i] for p in pts) for i in range(3)])
    hi = Vector([max(p[i] for p in pts) for i in range(3)])
    return lo, hi


def gercek_sinirlar(objs):
    """Bounds over the actual vertices (bound_box of a rotated object is loose)."""
    import numpy as np

    dg = bpy.context.evaluated_depsgraph_get()
    lo, hi = None, None
    for o in objs:
        ev = o.evaluated_get(dg)
        me = ev.to_mesh()
        co = np.empty(len(me.vertices) * 3, np.float32)
        me.vertices.foreach_get("co", co)
        co = co.reshape(-1, 3)
        mw = np.array(ev.matrix_world)
        w = co @ mw[:3, :3].T + mw[:3, 3]
        ev.to_mesh_clear()
        if len(w) == 0:
            continue
        a, b = w.min(0), w.max(0)
        lo = a if lo is None else np.minimum(lo, a)
        hi = b if hi is None else np.maximum(hi, b)
    return Vector(lo.tolist()), Vector(hi.tolist())


def albedo_kaynagi(mat):
    """(image, None) if the material has a base colour texture, else (None, rgba) for a plain base colour."""
    if mat is None or not mat.use_nodes:
        return None, None
    nt = mat.node_tree
    bsdf = next((n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"), None)
    if bsdf is None:
        img = next((n.image for n in nt.nodes if n.type == "TEX_IMAGE" and n.image), None)
        return img, None
    sock = bsdf.inputs["Base Color"]
    if sock.is_linked:
        n = sock.links[0].from_node
        seen = 0
        while n is not None and n.type != "TEX_IMAGE" and seen < 6:  # through a vertex-colour multiply etc.
            nxt = next((i.links[0].from_node for i in n.inputs if i.is_linked), None)
            n, seen = nxt, seen + 1
        if n is not None and n.type == "TEX_IMAGE":
            return n.image, None
    return None, tuple(sock.default_value)


def renk_ozniteligi(ob):
    me = ob.data
    if getattr(me, "color_attributes", None) and len(me.color_attributes):
        return me.color_attributes.active_color_name or me.color_attributes[0].name
    return None


def yumusak_normal(ob, iterations):
    """Geometry nodes: the normals blurred over the surface, stored as point attribute `snrm`."""
    ng = bpy.data.node_groups.get(f"yumusak_{iterations}")
    if ng is None:
        ng = bpy.data.node_groups.new(f"yumusak_{iterations}", "GeometryNodeTree")
        ng.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
        ng.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
        gi, go = ng.nodes.new("NodeGroupInput"), ng.nodes.new("NodeGroupOutput")
        nrm = ng.nodes.new("GeometryNodeInputNormal")
        blur = ng.nodes.new("GeometryNodeBlurAttribute")
        blur.data_type = "FLOAT_VECTOR"
        store = ng.nodes.new("GeometryNodeStoreNamedAttribute")
        store.data_type = "FLOAT_VECTOR"
        store.domain = "POINT"
        store.inputs["Name"].default_value = "snrm"
        L = ng.links.new
        L(nrm.outputs["Normal"], next(s for s in blur.inputs if s.type == "VECTOR" and s.enabled))
        blur.inputs["Iterations"].default_value = iterations
        L(gi.outputs["Geometry"], store.inputs["Geometry"])
        L(next(s for s in blur.outputs if s.type == "VECTOR" and s.enabled),
          next(s for s in store.inputs if s.type == "VECTOR" and s.enabled))
        L(store.outputs["Geometry"], go.inputs["Geometry"])
    m = ob.modifiers.new("yumusak_normal", "NODES")
    m.node_group = ng


def toon_malzeme(ad, img, renk, ozn, yumusak, duz):
    """albedo x ramp(warm key) + cool rim, as emission. Albedo: image > vertex colour attribute > flat colour."""
    mat = bpy.data.materials.new(ad)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    N, L = nt.nodes.new, nt.links.new
    if img is not None:
        tex = N("ShaderNodeTexImage")
        tex.image = img
        alb = tex.outputs["Color"]
    elif ozn:
        at = N("ShaderNodeAttribute")
        at.attribute_type = "GEOMETRY"
        at.attribute_name = ozn
        alb = at.outputs["Color"]
    else:
        rgb = N("ShaderNodeRGB")
        rgb.outputs[0].default_value = renk or KIL
        alb = rgb.outputs[0]
    em = N("ShaderNodeEmission")
    out = N("ShaderNodeOutputMaterial")
    L(em.outputs[0], out.inputs["Surface"])
    if duz:
        L(alb, em.inputs["Color"])
        return mat

    geo = N("ShaderNodeNewGeometry")
    nsock = geo.outputs["Normal"]
    if yumusak:
        at = N("ShaderNodeAttribute")
        at.attribute_type = "GEOMETRY"
        at.attribute_name = "snrm"
        vt = N("ShaderNodeVectorTransform")
        vt.vector_type = "NORMAL"
        vt.convert_from, vt.convert_to = "OBJECT", "WORLD"
        L(at.outputs["Vector"], vt.inputs["Vector"])
        nz = N("ShaderNodeVectorMath")
        nz.operation = "NORMALIZE"
        L(vt.outputs["Vector"], nz.inputs[0])
        nsock = nz.outputs["Vector"]
    key_dir = Vector((0.45, -0.75, 0.55)).normalized()  # camera side, from screen right, above
    rim_dir = Vector((-0.8, 0.5, 0.3)).normalized()     # from behind, screen left

    def dot(vec):
        d = N("ShaderNodeVectorMath")
        d.operation = "DOT_PRODUCT"
        L(nsock, d.inputs[0])
        d.inputs[1].default_value = vec
        return d

    ramp = N("ShaderNodeValToRGB")
    cr = ramp.color_ramp
    cr.interpolation = "CONSTANT"
    cr.elements[0].position = 0.0
    cr.elements[0].color = (0.58, 0.55, 0.72, 1)   # shadow: cool, purple-shifted
    cr.elements[1].position = 0.42
    cr.elements[1].color = (0.84, 0.82, 0.88, 1)   # mid
    e = cr.elements.new(0.68)
    e.color = (1.02, 1.0, 0.95, 1)                # light: warm
    mr = N("ShaderNodeMapRange")
    L(dot(key_dir).outputs["Value"], mr.inputs["Value"])
    mr.inputs["From Min"].default_value = -1.0
    mr.inputs["From Max"].default_value = 1.0
    L(mr.outputs["Result"], ramp.inputs["Fac"])
    mul = N("ShaderNodeMix")
    mul.data_type = "RGBA"
    mul.blend_type = "MULTIPLY"
    mul.inputs["Factor"].default_value = 1.0
    L(alb, mul.inputs[6])
    L(ramp.outputs["Color"], mul.inputs[7])
    lw = N("ShaderNodeLayerWeight")
    lw.inputs["Blend"].default_value = 0.2
    rmul = N("ShaderNodeMath")
    rmul.operation = "MULTIPLY"
    L(lw.outputs["Facing"], rmul.inputs[0])
    L(dot(rim_dir).outputs["Value"], rmul.inputs[1])
    rstep = N("ShaderNodeMath")
    rstep.operation = "GREATER_THAN"
    rstep.inputs[1].default_value = 0.5
    L(rmul.outputs["Value"], rstep.inputs[0])
    rimcol = N("ShaderNodeMix")
    rimcol.data_type = "RGBA"
    rimcol.blend_type = "SCREEN"
    rimcol.inputs["Factor"].default_value = 0.45
    L(alb, rimcol.inputs[6])
    rimcol.inputs[7].default_value = (0.35, 0.65, 0.95, 1)
    rim = N("ShaderNodeMix")
    rim.data_type = "RGBA"
    rim.blend_type = "MIX"
    L(rstep.outputs["Value"], rim.inputs["Factor"])
    L(mul.outputs[2], rim.inputs[6])
    L(rimcol.outputs[2], rim.inputs[7])
    L(rim.outputs[2], em.inputs["Color"])
    return mat


def cizgi_malzeme():
    """Inverted hull: back faces only, flat dark warm ink."""
    mat = bpy.data.materials.new("cizgi")
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (0.035, 0.028, 0.025, 1)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(em.outputs[0], out.inputs["Surface"])
    mat.use_backface_culling = True
    return mat


def motor_sec(sc):
    for e in ("BLENDER_EEVEE", "BLENDER_EEVEE_NEXT"):
        try:
            sc.render.engine = e
            return e
        except TypeError:
            continue
    sc.render.engine = "CYCLES"
    return "CYCLES"


def main():
    a = args()
    t0 = time.time()
    import os

    cikti = os.path.abspath(a.cikti)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    objs = []
    for g in a.girdi:
        objs += ice_al(os.path.abspath(g))
    if not objs:
        raise SystemExit("no mesh in the input")

    # Toon materials (one per source material), smoothed normals, outline hull.
    cache = {}
    cmat = cizgi_malzeme() if a.cizgi > 0 else None
    lo, hi = sinirlar(objs)
    yukseklik = max(hi.z - lo.z, 1e-6)
    for o in objs:
        ozn = renk_ozniteligi(o)
        if a.yumusak > 0 and not a.duz:
            yumusak_normal(o, a.yumusak)
        mats = list(o.data.materials) or [None]
        yeni = []
        for m in mats:
            img, renk = albedo_kaynagi(m)
            key = (m.name if m else "", ozn)
            if key not in cache:
                cache[key] = toon_malzeme(f"toon_{len(cache)}", img, renk, None if img else ozn, a.yumusak > 0, a.duz)
            yeni.append(cache[key])
        o.data.materials.clear()
        for m in yeni:
            o.data.materials.append(m)
        if cmat is not None:
            o.data.materials.append(cmat)
            sol = o.modifiers.new("cizgi", "SOLIDIFY")
            sol.thickness = -yukseklik * a.cizgi / 1000.0
            sol.offset = 1.0
            sol.use_flip_normals = True
            sol.use_rim = False
            sol.material_offset = len(yeni)

    # Turn the model about the vertical axis through its footprint centre.
    c = (lo + hi) / 2
    pivot = bpy.data.objects.new("pivot", None)
    bpy.context.scene.collection.objects.link(pivot)
    pivot.location = (c.x, c.y, lo.z)
    bpy.context.view_layer.update()
    for o in [o for o in bpy.context.scene.objects if o.parent is None and o is not pivot]:
        mw = o.matrix_world.copy()
        o.parent = pivot
        o.matrix_world = mw
    pivot.rotation_euler = (0, 0, math.radians(ACILAR[a.aci]))
    bpy.context.view_layer.update()
    lo, hi = gercek_sinirlar(objs)
    c = (lo + hi) / 2

    sc = bpy.context.scene
    motor = motor_sec(sc)
    sc.render.film_transparent = True
    sc.render.resolution_x = sc.render.resolution_y = a.boyut
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGBA"
    sc.view_settings.view_transform = "Standard"
    sc.view_settings.look = "None"
    try:
        sc.eevee.taa_render_samples = 16
    except AttributeError:
        pass

    el = math.radians(a.yukseklik)
    cam = bpy.data.objects.new("kamera", bpy.data.cameras.new("kamera"))
    sc.collection.objects.link(cam)
    sc.camera = cam
    cam.data.type = "ORTHO"
    w, h = hi.x - lo.x, (hi.z - lo.z) * math.cos(el) + (hi.y - lo.y) * math.sin(el)
    cam.data.ortho_scale = max(w, h) * 1.08
    d = max(hi - lo) * 4 + 1
    cam.location = c + Vector((0, -d * math.cos(el), d * math.sin(el)))
    cam.rotation_euler = (math.pi / 2 - el, 0, 0)
    cam.data.clip_end = d * 4

    sc.render.filepath = cikti
    bpy.ops.render.render(write_still=True)
    print("@@sonuc " + json.dumps({"dosya": os.path.basename(cikti), "aci": a.aci, "boyut": a.boyut, "motor": motor,
                                   "nesne": len(objs), "sure_sn": round(time.time() - t0, 2)}))


main()
