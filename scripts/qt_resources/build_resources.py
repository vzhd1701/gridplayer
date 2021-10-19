import argparse
import csv
import os
import shutil


class RCC:
    def __init__(self, src_dir, dst_dir):
        self.qrc_file = [
            "<!DOCTYPE RCC>",
            '<RCC version="1.0">',
            "<qresource>",
        ]

        self.src_dir = src_dir
        self.dst_dir = dst_dir

    def write_qrc(self):
        self.qrc_file += ["</qresource>", "</RCC>", ""]

        qrc_txt = "\n".join(self.qrc_file)

        qrc_path = os.path.join(self.dst_dir, "resources.qrc")

        with open(qrc_path, "w") as f:
            f.write(qrc_txt)

    def add_file(self, src_path, dst_path):
        f_src = self._get_src_f_path(src_path)
        f_dst = self._get_dst_f_path(dst_path)

        shutil.copy(f_src, f_dst)

        self._add_to_qrc(dst_path)

        return f_dst

    def new_file(self, dst_path, content):
        f_dst = self._get_dst_f_path(dst_path)

        with open(f_dst, "w") as f:
            f.write(content)

        self._add_to_qrc(dst_path)

        return f_dst

    def _get_src_f_path(self, src_path):
        return os.path.normpath(os.path.join(self.src_dir, src_path))

    def _get_dst_f_path(self, dst_path):
        f_dst = os.path.normpath(os.path.join(self.dst_dir, dst_path))

        f_dst_dir = os.path.dirname(f_dst)
        os.makedirs(f_dst_dir, exist_ok=True)

        return f_dst

    def _add_to_qrc(self, path):
        path.replace("\\", "/")

        self.qrc_file.append(f"<file>{path}</file>")


def make_dark(svg_path):
    with open(svg_path, "r") as f:
        svg = f.read()

    svg = svg.replace("<svg", '<svg fill="white"')

    with open(svg_path, "w") as f:
        f.write(svg)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build qt_resources.")
    parser.add_argument("resources_dir", help="source resources dir")
    parser.add_argument("build_dir", help="destination build dir")

    args = parser.parse_args()

    rcc = RCC(args.resources_dir, args.build_dir)

    files = []
    icons = []
    icons_symbolic = []

    resources_file = os.path.join(args.resources_dir, "resources.csv")

    with open(resources_file, newline="") as csvfile:
        type_map = {"file": files, "icon": icons, "icon-symbolic": icons_symbolic}
        for f_type, f_path, f_name in csv.reader(csvfile):
            type_map[f_type].append((f_path, f_name))

    for f_path, f_name in files:
        rcc.add_file(f_path, f_name)

    for f_path, f_name in icons:
        if "." not in f_name:
            _, ext = os.path.splitext(f_path)
            f_name += ext

        dst_path = f"icons/{f_name}"

        rcc.add_file(f_path, dst_path)

    if icons_symbolic:
        for theme in ("dark", "light"):

            dst_path = f"icons/{theme}/index.theme"

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

            rcc.new_file(dst_path, index)

            for f_path, f_name in icons_symbolic:
                if "." not in f_name:
                    _, ext = os.path.splitext(f_path)
                    f_name += ext

                dst_path = f"icons/{theme}/scalable/{f_name}"

                f_dst = rcc.add_file(f_path, dst_path)

                if theme == "dark":
                    make_dark(f_dst)

    rcc.write_qrc()
