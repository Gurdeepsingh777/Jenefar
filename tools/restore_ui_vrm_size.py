#!/usr/bin/env python3
"""Restore polished Jenefar UI CSS with moderate VRM size (280x380)."""
from pathlib import Path
import subprocess
import sys

root = Path.cwd()
style = root / "jenefar" / "avatar" / "web" / "style.css"
if not style.parent.is_dir():
    print("Run from Jenefar repo root", file=sys.stderr)
    sys.exit(1)

# Restore original polished CSS from first good commit
css = subprocess.check_output(
    ["git", "show", "a559a72:jenefar/avatar/web/style.css"],
    text=True,
)
old = """#vrm-canvas{
  left:calc(50% - 105px)!important;
  bottom:72px!important;
  width:210px!important;
  height:235px!important;
  z-index:45!important;
}
.avatar-shell{
  left:calc(50% - 78px)!important;
  bottom:68px!important;
  width:156px!important;
  height:210px!important;
  z-index:46!important;
}"""
new = """#vrm-canvas{
  left:calc(50% - 140px)!important;
  bottom:88px!important;
  width:280px!important;
  height:380px!important;
  z-index:45!important;
}
.avatar-shell{
  left:calc(50% - 120px)!important;
  bottom:84px!important;
  width:240px!important;
  height:340px!important;
  z-index:46!important;
}"""
if old not in css:
    print("Unexpected CSS layout; aborting", file=sys.stderr)
    sys.exit(1)
css = css.replace(old, new, 1)
css = css.replace(
    "#vrm-canvas{left:calc(50% - 92px)!important;width:184px!important}",
    "#vrm-canvas{left:calc(50% - 125px)!important;width:250px!important;height:340px!important}",
    1,
)
css = css.replace(
    ".avatar-shell{left:calc(50% - 70px)!important;width:140px!important}",
    ".avatar-shell{left:calc(50% - 105px)!important;width:210px!important;height:300px!important}",
    1,
)
css = css.replace(
    "#vrm-canvas{left:calc(50% - 78px)!important;width:156px!important;height:180px!important;bottom:62px!important}",
    "#vrm-canvas{left:calc(50% - 110px)!important;width:220px!important;height:300px!important;bottom:70px!important}",
    1,
)
css = css.replace(
    ".avatar-shell{left:calc(50% - 60px)!important;width:120px!important;height:150px!important;bottom:58px!important}",
    ".avatar-shell{left:calc(50% - 95px)!important;width:190px!important;height:270px!important;bottom:66px!important}",
    1,
)
style.write_text(css, encoding="utf-8")
print(f"Restored polished UI with moderate VRM ({style.stat().st_size} bytes)")
print("Next: git add jenefar/avatar/web/style.css && git commit -m 'Restore UI; moderate VRM size' && git push")
