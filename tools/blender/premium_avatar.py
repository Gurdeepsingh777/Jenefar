"""
Jenefar premium VRM remodel/retexture pipeline.

Run with Blender + VRM Add-on for Blender:
    blender --background --python tools/blender/premium_avatar.py -- \
      --input data/avatar/AvatarSample_A_1.0.vrm.glb \
      --output data/avatar/Jenefar_Premium.vrm

The script deliberately fails closed if VRM import/export operators are unavailable.
It preserves the original source asset and writes a separate premium output.
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import bpy
from mathutils import Color


PIPELINE_VERSION = "2026.10-premium-1"
PREMIUM_WHITE = (0.72, 0.82, 0.90, 1.0)
PREMIUM_DARK = (0.025, 0.045, 0.075, 1.0)
PREMIUM_CYAN = (0.07, 0.82, 1.0, 1.0)
PREMIUM_VIOLET = (0.42, 0.22, 0.95, 1.0)
SKIN_TINT = (0.72, 0.42, 0.34, 1.0)
HAIR_DARK = (0.025, 0.018, 0.035, 1.0)


def parse_args() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--blend-output", default="")
    return parser.parse_args(argv)


def enable_vrm_addon() -> None:
    if not hasattr(bpy.ops.import_scene, "vrm") or not hasattr(bpy.ops.export_scene, "vrm"):
        try:
            bpy.ops.preferences.addon_enable(module="io_scene_vrm")
        except Exception:
            pass
    if not hasattr(bpy.ops.import_scene, "vrm") or not hasattr(bpy.ops.export_scene, "vrm"):
        raise RuntimeError(
            "VRM Add-on for Blender is required. "
            "Install the maintained saturday06 VRM add-on, then rerun this pipeline."
        )


def clear_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for block in (bpy.data.materials, bpy.data.meshes, bpy.data.curves):
        for item in list(block):
            if item.users == 0:
                block.remove(item)


def set_material_color(material: bpy.types.Material, rgba: tuple[float, float, float, float]) -> None:
    material.diffuse_color = rgba
    material.metallic = min(0.65, max(0.0, getattr(material, "metallic", 0.0)))
    material.roughness = min(0.72, max(0.28, getattr(material, "roughness", 0.5)))

    node_tree = getattr(material, "node_tree", None)
    if not node_tree:
        return
    for node in node_tree.nodes:
        if node.type == "BSDF_PRINCIPLED":
            base = node.inputs.get("Base Color")
            rough = node.inputs.get("Roughness")
            metallic = node.inputs.get("Metallic")
            if base:
                base.default_value = rgba
            if rough:
                rough.default_value = material.roughness
            if metallic:
                metallic.default_value = material.metallic
            break


def add_emission(material: bpy.types.Material, color: tuple[float, float, float, float], strength: float = 1.8) -> None:
    node_tree = getattr(material, "node_tree", None)
    if not node_tree:
        return
    for node in node_tree.nodes:
        if node.type == "BSDF_PRINCIPLED":
            emission = node.inputs.get("Emission Color") or node.inputs.get("Emission")
            emission_strength = node.inputs.get("Emission Strength")
            if emission:
                emission.default_value = color
            if emission_strength:
                emission_strength.default_value = strength
            break


def classify_material(material: bpy.types.Material) -> str:
    name = (material.name or "").lower()
    if any(token in name for token in ("skin", "face", "body", "arm", "leg")):
        return "skin"
    if any(token in name for token in ("hair", "eyebrow", "lash")):
        return "hair"
    if any(token in name for token in ("eye", "iris", "pupil")):
        return "eye"
    if any(token in name for token in ("shoe", "boot", "sock")):
        return "shoe"
    if any(token in name for token in ("cloth", "dress", "shirt", "top", "jacket", "outfit", "uniform", "skirt")):
        return "outfit"
    if any(token in name for token in ("accent", "accessory", "metal", "ring", "collar")):
        return "accent"

    # Fallback: keep most neutral assets unchanged rather than aggressively
    # recolouring unknown materials.
    return "unknown"


def retexture_materials() -> dict[str, int]:
    counts = {"skin": 0, "hair": 0, "eye": 0, "shoe": 0, "outfit": 0, "accent": 0, "unknown": 0}
    for material in bpy.data.materials:
        kind = classify_material(material)
        counts[kind] += 1
        if kind == "skin":
            set_material_color(material, SKIN_TINT)
        elif kind == "hair":
            set_material_color(material, HAIR_DARK)
        elif kind == "eye":
            set_material_color(material, (0.02, 0.025, 0.04, 1.0))
        elif kind == "shoe":
            set_material_color(material, (0.035, 0.05, 0.08, 1.0))
        elif kind == "outfit":
            set_material_color(material, PREMIUM_WHITE)
            add_emission(material, (0.05, 0.32, 0.50, 1.0), 0.25)
        elif kind == "accent":
            set_material_color(material, PREMIUM_CYAN)
            add_emission(material, PREMIUM_CYAN, 2.4)
    return counts


def find_armature() -> bpy.types.Object | None:
    for obj in bpy.context.scene.objects:
        if obj.type == "ARMATURE":
            return obj
    return None


def apply_premium_pose(armature: bpy.types.Object | None) -> None:
    if not armature:
        return
    bpy.context.view_layer.objects.active = armature
    armature.select_set(True)
    bpy.ops.object.mode_set(mode="POSE")
    pose_bones = armature.pose.bones
    values = {
        "leftUpperArm": (0.08, 0.04, -1.32),
        "rightUpperArm": (0.08, -0.04, 1.32),
        "leftLowerArm": (0.34, 0.10, -0.12),
        "rightLowerArm": (0.34, -0.10, 0.12),
        "leftHand": (0.02, 0.0, -0.08),
        "rightHand": (0.02, 0.0, 0.08),
    }
    for name, euler in values.items():
        bone = pose_bones.get(name)
        if bone:
            bone.rotation_mode = "XYZ"
            bone.rotation_euler = euler
    bpy.ops.object.mode_set(mode="OBJECT")
    armature.select_set(False)


def add_premium_chest_core(armature: bpy.types.Object | None) -> None:
    if not armature:
        return
    chest = armature.pose.bones.get("chest") or armature.pose.bones.get("upperChest")
    if not chest:
        return

    deps = bpy.context.evaluated_depsgraph_get()
    world = armature.matrix_world @ chest.matrix
    bpy.ops.mesh.primitive_uv_sphere_add(
        segments=24,
        ring_count=12,
        radius=0.07,
        location=world.translation,
    )
    core = bpy.context.object
    core.name = "Jenefar_Premium_Chest_Core"

    material = bpy.data.materials.new(core.name + "_Material")
    material.diffuse_color = PREMIUM_CYAN
    material.metallic = 0.65
    material.roughness = 0.2
    add_emission(material, PREMIUM_CYAN, 4.0)
    core.data.materials.append(material)

    core.parent = armature
    core.parent_type = "BONE"
    core.parent_bone = chest.name
    core.matrix_parent_inverse = armature.matrix_world.inverted()
    del deps


def add_premium_neck_ring(armature: bpy.types.Object | None) -> None:
    if not armature:
        return
    neck = armature.pose.bones.get("neck")
    if not neck:
        return
    world = armature.matrix_world @ neck.matrix
    bpy.ops.mesh.primitive_torus_add(
        major_radius=0.12,
        minor_radius=0.014,
        major_segments=36,
        minor_segments=8,
        location=world.translation,
        rotation=(math.radians(90), 0, 0),
    )
    ring = bpy.context.object
    ring.name = "Jenefar_Premium_Neck_Ring"
    material = bpy.data.materials.new(ring.name + "_Material")
    material.diffuse_color = PREMIUM_CYAN
    material.metallic = 0.88
    material.roughness = 0.18
    add_emission(material, PREMIUM_CYAN, 2.7)
    ring.data.materials.append(material)
    ring.parent = armature
    ring.parent_type = "BONE"
    ring.parent_bone = neck.name
    ring.matrix_parent_inverse = armature.matrix_world.inverted()


def bake_metadata(output: Path, material_counts: dict[str, int]) -> None:
    meta = output.with_suffix(output.suffix + ".pipeline.json")
    meta.write_text(
        "{\\n"
        f'  "pipeline": "{PIPELINE_VERSION}",\\n'
        f'  "output": "{output.name}",\\n'
        f'  "materials": {material_counts}\\n'
        "}\\n",
        encoding="utf-8",
    )


def main() -> None:
    args = parse_args()
    source = Path(args.input).expanduser().resolve()
    output = Path(args.output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    if not source.is_file():
        raise FileNotFoundError(source)
    enable_vrm_addon()
    clear_scene()

    result = bpy.ops.import_scene.vrm(filepath=str(source))
    if result != {"FINISHED"}:
        raise RuntimeError(f"VRM import failed: {result}")

    armature = find_armature()
    counts = retexture_materials()
    apply_premium_pose(armature)
    add_premium_chest_core(armature)
    add_premium_neck_ring(armature)

    if args.blend_output:
        blend_path = Path(args.blend_output).expanduser().resolve()
        blend_path.parent.mkdir(parents=True, exist_ok=True)
        bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))

    result = bpy.ops.export_scene.vrm(filepath=str(output))
    if result != {"FINISHED"}:
        raise RuntimeError(f"VRM export failed: {result}")
    bake_metadata(output, counts)
    print(f"[JENEFAR] Premium VRM exported: {output}")


if __name__ == "__main__":
    main()
