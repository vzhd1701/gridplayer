import argparse
import csv
import shutil
import struct
import subprocess
from pathlib import Path


class ResourceBuilder:
    def __init__(self, src_dir: Path, dst_dir: Path):
        self.src_dir = src_dir
        self.dst_dir = dst_dir

    def copy_file(self, src_path: Path, dst_path: Path):
        f_src = self.src_dir / src_path
        f_dst = self.dst_dir / dst_path

        f_dst.parent.mkdir(parents=True, exist_ok=True)

        shutil.copy(f_src, f_dst)

        return f_dst

    def new_file(self, dst_path: Path, content: str):
        f_dst = self.dst_dir / dst_path

        f_dst.parent.mkdir(parents=True, exist_ok=True)

        with open(f_dst, "w", newline="\n") as f:
            f.write(content)

        return f_dst


def drop_icns_toc(icns_path):
    """The icns without its table of contents, which is optional.

    Qt's reader (to 6.12 and its dev branch at least) adds the table up 8
    bytes short, warns on every launch that the last entry is bad, and then
    reads the file block by block all the same. Only Qt reads this copy: the
    app bundle's icon is taken from resources/ as it is.
    """

    data = icns_path.read_bytes()

    blocks = []
    pos = 8
    while pos < len(data):
        block_type, length = struct.unpack(">4sI", data[pos : pos + 8])
        if length < 8:
            raise ValueError(f"Bad block in {icns_path} at {pos}")
        if block_type != b"TOC ":
            blocks.append(data[pos : pos + length])
        pos += length

    body = b"".join(blocks)
    icns_path.write_bytes(b"icns" + struct.pack(">I", 8 + len(body)) + body)


def make_dark(svg_path):
    with open(svg_path, "r") as f:
        svg = f.read()

    svg = svg.replace("<svg", '<svg fill="white"')

    with open(svg_path, "w", newline="\n") as f:
        f.write(svg)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build qt_resources.")
    parser.add_argument("resources_dir", help="source resources dir", type=Path)
    parser.add_argument("build_dir", help="destination build dir", type=Path)

    args = parser.parse_args()

    builder = ResourceBuilder(args.resources_dir, args.build_dir)

    files = []
    icons = []
    icons_symbolic = []
    translations = []

    resources_file = args.resources_dir / "resources.csv"

    with open(resources_file, newline="") as csvfile:
        type_map = {
            "file": files,
            "icon": icons,
            "icon-symbolic": icons_symbolic,
            "translation": translations,
        }
        for f_type, f_path, f_name in csv.reader(csvfile):
            type_map[f_type].append((Path(f_path), Path(f_name)))

    for f_path, f_name in files:
        builder.copy_file(f_path, f_name)

    for f_path, f_name in icons:
        if not f_name.suffix:
            f_name = f_name.with_suffix(f_path.suffix)

        dst_path = Path("icons") / f_name

        f_dst = builder.copy_file(f_path, dst_path)

        if f_dst.suffix == ".icns":
            drop_icns_toc(f_dst)

    if icons_symbolic:
        for theme in ("dark", "light"):
            dst_path = Path("icons") / theme / "index.theme"

            index = (
                "[Icon Theme]\n"
                f"Name={theme}\n"
                "Directories=scalable\n\n"
                "[scalable]\n"
                "Size=32\n"
                "MinSize=16\n"
                "MaxSize=128\n"
                "Type=Scalable\n"
            )

            builder.new_file(dst_path, index)

            for f_path, f_name in icons_symbolic:
                if not f_name.suffix:
                    f_name = f_name.with_suffix(f_path.suffix)

                dst_path = Path("icons") / theme / "scalable" / f_name

                f_dst = builder.copy_file(f_path, dst_path)

                if theme == "dark":
                    make_dark(f_dst)

    for f_path, f_name in translations:
        dst_path = Path("translations") / f"{f_path.stem}.qm"

        if f_path.suffix == ".ts":
            (args.build_dir / dst_path.parent).mkdir(parents=True, exist_ok=True)

            subprocess.run(
                [
                    "lrelease",
                    args.resources_dir / f_path,
                    "-silent",
                    "-qm",
                    args.build_dir / dst_path,
                ]
            )
        else:
            raise ValueError(f"Unknown translation file type: {f_path}")
