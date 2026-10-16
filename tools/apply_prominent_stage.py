#!/usr/bin/env python3
"""Apply prominent center-stage VRM layout (380x520) to style.css."""
from pathlib import Path
import sys
p = Path("jenefar/avatar/web/style.css")
if not p.is_file():
    print("Run from Jenefar repo root", file=sys.stderr)
    sys.exit(1)
css = p.read_text(encoding="utf-8")
old = """#vrm-canvas{\n  left:calc(50% - 150px)!important;\n  bottom:88px!important;\n  width:300px!important;\n  height:430px!important;\n  z-index:45!important;\n}\n.avatar-shell{\n  left:calc(50% - 130px)!important;\n  bottom:84px!important;\n  width:260px!important;\n  height:390px!important;\n  z-index:46!important;\n}"""
new = """/* Prominent center-stage avatar \u2014 fills focus without eating side panels */\n#vrm-canvas{\n  left:calc(50% - 190px)!important;\n  bottom:72px!important;\n  width:380px!important;\n  height:520px!important;\n  z-index:45!important;\n}\n.avatar-shell{\n  left:calc(50% - 170px)!important;\n  bottom:68px!important;\n  width:340px!important;\n  height:480px!important;\n  z-index:46!important;\n}\n/* Keep live task strip off the avatar face */\n#task-screen{\n  left:auto!important;\n  right:18px!important;\n  width:315px!important;\n  bottom:122px!important;\n}\n#desktop-mirror{\n  display:none!important;\n}\n#hud-avatar{\n  left:calc(50% - 220px)!important;\n  right:calc(50% - 220px)!important;\n  top:90px!important;\n  bottom:100px!important;\n  opacity:.18!important;\n}"""
if old not in css:
    if "width:380px!important" in css and "height:520px!important" in css:
        print("Already applied")
        sys.exit(0)
    print("Expected Phase 12 VRM block not found \u2014 check style.css", file=sys.stderr)
    sys.exit(1)
css = css.replace(old, new, 1)
css = css.replace(
    "#vrm-canvas{left:calc(50% - 125px)!important;width:250px!important;height:340px!important}",
    "#vrm-canvas{left:calc(50% - 160px)!important;width:320px!important;height:440px!important}",
    1,
)
css = css.replace(
    ".avatar-shell{left:calc(50% - 105px)!important;width:210px!important;height:300px!important}",
    ".avatar-shell{left:calc(50% - 140px)!important;width:280px!important;height:400px!important}",
    1,
)
css = css.replace(
    "#vrm-canvas{left:calc(50% - 110px)!important;width:220px!important;height:300px!important;bottom:70px!important}",
    "#vrm-canvas{left:calc(50% - 140px)!important;width:280px!important;height:380px!important;bottom:64px!important}",
    1,
)
css = css.replace(
    ".avatar-shell{left:calc(50% - 95px)!important;width:190px!important;height:270px!important;bottom:66px!important}",
    ".avatar-shell{left:calc(50% - 125px)!important;width:250px!important;height:350px!important;bottom:60px!important}",
    1,
)
p.write_text(css, encoding="utf-8")
print(f"Applied prominent stage ({p.stat().st_size} bytes)")
