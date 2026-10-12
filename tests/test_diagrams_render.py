"""docs/diagrams/render.sh, run against a copy of the folder with a stub container engine (no real mermaid-cli)."""
import os
import shutil
import subprocess

import pytest

from diagrams_support import DIAGRAMS, HASH_COMMENT, image_ref, source_hash

pytestmark = pytest.mark.skipif(os.name == "nt", reason="render.sh is a bash tool for maintainers on Linux and macOS")

# Stands in for podman/docker: finds the mount, the -i input and the -o output, and writes a minimal SVG that
# carries the composed input, so tests can see what render.sh handed to mermaid-cli.
STUB = r"""#!/usr/bin/env bash
[ -n "${STUB_FAIL:-}" ] && { echo "engine failed" >&2; exit 1; }
while [ $# -gt 0 ]; do
  case "$1" in
    -v) host="${2%%:*}"; shift 2;;
    -i) in="$2"; shift 2;;
    -o) out="$2"; shift 2;;
    *) shift;;
  esac
done
{ printf '<svg id="my-svg" xmlns="http://www.w3.org/2000/svg"><desc>'; cat "$host/$in"; printf '</desc></svg>'; } > "$host/$out"
"""

FLOW = "flowchart LR\n  a --> b\n  class a kit\n%% palette\n"
SEQ = "sequenceDiagram\n  A->>B: hi\n"


@pytest.fixture
def folder(tmp_path):
    d = tmp_path / "diagrams"
    d.mkdir()
    for f in ("render.sh", "palette.light.mmd", "palette.dark.mmd", "theme.light.json", "theme.dark.json"):
        shutil.copy2(DIAGRAMS / f, d / f)
    (d / "flow.mmd").write_text(FLOW, encoding="utf-8", newline="\n")
    (d / "seq.mmd").write_text(SEQ, encoding="utf-8", newline="\n")
    stub = tmp_path / "engine"
    stub.write_text(STUB, encoding="utf-8", newline="\n")
    stub.chmod(0o755)
    return d


def render(folder, *names, **env):
    e = {**os.environ, "DIAGRAMS_ENGINE": str(folder.parent / "engine"), **env}
    return subprocess.run(["bash", str(folder / "render.sh"), *names], capture_output=True, text=True, env=e, timeout=60)


def svgs(folder):
    return sorted(p.name for p in folder.glob("*.svg"))


def test_image_is_pinned_by_version_and_digest():
    assert image_ref(DIAGRAMS / "render.sh") == (
        "ghcr.io/mermaid-js/mermaid-cli/mermaid-cli:11.16.0"
        "@sha256:29077c6bd02f14bdfdd5fee552d9c00fe68d4fab3cd84952d21e2d1faf2fadaf"
    )


def test_renders_every_diagram_in_both_variants_offline(folder):
    p = render(folder)
    assert p.returncode == 0, p.stderr
    assert svgs(folder) == ["flow.dark.svg", "flow.light.svg", "seq.dark.svg", "seq.light.svg"]
    assert "--network=none" in (folder / "render.sh").read_text(encoding="utf-8")


def test_svg_records_the_hash_python_computes(folder):
    assert render(folder).returncode == 0
    image = image_ref(folder / "render.sh")
    for name in ("flow", "seq"):
        for variant in ("light", "dark"):
            text = (folder / f"{name}.{variant}.svg").read_text(encoding="utf-8")
            assert text.startswith('<svg id="my-svg" xmlns="http://www.w3.org/2000/svg"><!-- diagram-source sha256:')
            assert HASH_COMMENT.findall(text) == [source_hash(folder, name, variant, image)]


def test_palette_line_is_replaced_by_the_variant_palette(folder):
    assert render(folder).returncode == 0
    light = (folder / "flow.light.svg").read_text(encoding="utf-8")
    dark = (folder / "flow.dark.svg").read_text(encoding="utf-8")
    assert "%% palette\n" not in light and "%% palette\n" not in dark
    assert (folder / "palette.light.mmd").read_text(encoding="utf-8").strip() in light
    assert (folder / "palette.dark.mmd").read_text(encoding="utf-8").strip() in dark


def test_named_render_touches_only_that_diagram(folder):
    p = render(folder, "seq")
    assert p.returncode == 0, p.stderr
    assert svgs(folder) == ["seq.dark.svg", "seq.light.svg"]


def test_unknown_name_fails(folder):
    p = render(folder, "nope")
    assert p.returncode == 2 and "no such diagram: nope" in p.stderr
    assert svgs(folder) == []


def test_palette_is_not_a_diagram(folder):
    p = render(folder, "palette.light")
    assert p.returncode == 2 and "not a diagram" in p.stderr


def test_engine_failure_writes_nothing(folder):
    p = render(folder, STUB_FAIL="1")
    assert p.returncode != 0
    assert svgs(folder) == []
    assert not list(folder.glob(".render.*")), "the temporary folder must be removed"


def test_crlf_source_hashes_like_lf(folder):
    (folder / "flow.mmd").write_bytes(FLOW.replace("\n", "\r\n").encode())
    assert render(folder, "flow").returncode == 0
    crlf = HASH_COMMENT.findall((folder / "flow.light.svg").read_text(encoding="utf-8"))
    (folder / "flow.mmd").write_bytes(FLOW.encode())
    assert render(folder, "flow").returncode == 0
    lf = HASH_COMMENT.findall((folder / "flow.light.svg").read_text(encoding="utf-8"))
    assert crlf == lf == [source_hash(folder, "flow", "light", image_ref(folder / "render.sh"))]


def test_a_change_to_render_sh_makes_svgs_stale(folder):
    assert render(folder, "flow").returncode == 0
    with (folder / "render.sh").open("a", encoding="utf-8", newline="\n") as f:
        f.write("# changed render logic\n")
    stamped = HASH_COMMENT.findall((folder / "flow.light.svg").read_text(encoding="utf-8"))
    assert stamped != [source_hash(folder, "flow", "light", image_ref(folder / "render.sh"))]


def test_name_may_carry_the_mmd_suffix(folder):
    p = render(folder, "seq.mmd")
    assert p.returncode == 0, p.stderr
    assert svgs(folder) == ["seq.dark.svg", "seq.light.svg"]


def test_rootful_podman_gets_no_keep_id(folder, tmp_path):
    """--userns=keep-id exists only for rootless podman; as root the engine would refuse it."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    podman = bin_dir / "podman"
    podman.write_text('#!/usr/bin/env bash\necho "$@" >> "$(dirname "$0")/args"\n' + STUB.split("\n", 1)[1],
                      encoding="utf-8", newline="\n")
    fake_id = bin_dir / "id"
    fake_id.write_text("#!/usr/bin/env bash\necho 0\n", encoding="utf-8", newline="\n")
    for f in (podman, fake_id):
        f.chmod(0o755)
    env = {"PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}", "DIAGRAMS_ENGINE": "podman"}
    p = subprocess.run(["bash", str(folder / "render.sh"), "seq"], capture_output=True, text=True,
                       env={**os.environ, **env}, timeout=60)
    assert p.returncode == 0, p.stderr
    args = (bin_dir / "args").read_text(encoding="utf-8")
    assert "--userns=keep-id" not in args and "--user 0:0" in args


def test_render_temp_folders_are_ignored_by_git():
    rel = "docs/diagrams/.render.AbC123/flow.light.svg"
    p = subprocess.run(["git", "-C", str(DIAGRAMS), "check-ignore", "-q", rel.split("docs/diagrams/", 1)[1]])
    assert p.returncode == 0, "a temp folder left by a killed render must never be committed"
