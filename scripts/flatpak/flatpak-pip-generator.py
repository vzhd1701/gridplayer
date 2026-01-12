#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#    "requirements-parser<1.0.0,>=0.11.0",
#    "packaging>=23.0",
# ]
# ///

__license__ = "MIT"

import sys

if sys.version_info < (3, 10):
    sys.stderr.write("Error: This script requires Python 3.10 or higher.\n")
    sys.exit(1)

import platform
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import urllib.request
from collections import OrderedDict
from collections.abc import Iterator
from contextlib import suppress
from typing import Any, TextIO, Callable
import operator
from packaging.version import Version

try:
    import requirements
except ImportError:
    sys.exit("Please install the 'requirements-parser' module")

parser = argparse.ArgumentParser()
parser.add_argument("packages", nargs="*")
parser.add_argument(
    "--python2", action="store_true", help="Look for a Python 2 package"
)
parser.add_argument(
    "--cleanup", choices=["scripts", "all"], help="Select what to clean up after build"
)
parser.add_argument(
    "--requirements-file",
    "-r",
    help="Specify requirements.txt file. Cannot be used with pyproject file.",
)
parser.add_argument(
    "--pyproject-file",
    help="Specify pyproject.toml file. Cannot be used with requirements file.",
)
parser.add_argument(
    "--build-only",
    action="store_const",
    dest="cleanup",
    const="all",
    help="Clean up all files after build",
)
parser.add_argument(
    "--build-isolation",
    action="store_true",
    default=False,
    help=(
        "Do not disable build isolation. "
        "Mostly useful on pip that does't "
        "support the feature."
    ),
)
parser.add_argument(
    "--ignore-installed",
    type=lambda s: s.split(","),
    default="",
    help="Comma-separated list of package names for which pip "
    "should ignore already installed packages. Useful when "
    "the package is installed in the SDK but not in the "
    "runtime.",
)
parser.add_argument(
    "--checker-data",
    action="store_true",
    help='Include x-checker-data in output for the "Flatpak External Data Checker"',
)
parser.add_argument("--output", "-o", help="Specify output file name")
parser.add_argument(
    "--runtime",
    help=(
        "Specify a flatpak to run pip inside of a sandbox, "
        "ensures python version compatibility. Format: $RUNTIME_ID//$RUNTIME_BRANCH"
    ),
)
parser.add_argument(
    "--yaml", action="store_true", help="Use YAML as output format instead of JSON"
)
parser.add_argument(
    "--ignore-errors",
    action="store_true",
    help="Ignore errors when downloading packages",
)
parser.add_argument(
    "--ignore-pkg",
    nargs="*",
    help=(
        "Ignore packages when generating the manifest. "
        "Needs to be specified with version constraints if present "
        "(e.g. --ignore-pkg 'foo>=3.0.0' 'baz>=21.0')."
    ),
)
parser.add_argument(
    "--use-prebuilt-wheels",
    nargs="*",
    default=[],
    help=(
        "Comma-separated list of package names that should use pre-built wheels "
        "for aarch64 and x86_64 architectures instead of source packages. "
        "Example: --use-prebuilt-wheels numpy pandas pydantic-core"
    ),
)

opts = parser.parse_args()

if opts.requirements_file and opts.pyproject_file:
    sys.exit("Can't use both requirements and pyproject files at the same time")

if opts.pyproject_file:
    try:
        from tomllib import load as toml_load
    except ModuleNotFoundError:
        try:
            from tomli import load as toml_load  # type: ignore
        except ModuleNotFoundError:
            sys.exit("Please install the 'tomli' module")

if opts.yaml:
    try:
        import yaml
    except ImportError:
        sys.exit("Please install the 'PyYAML' module")


def get_poetry_deps(pyproject_data: dict[str, Any]) -> list[str]:
    poetry_deps = pyproject_data.get("tool", {}).get("poetry", {}).get("dependencies")

    if not poetry_deps:
        return []

    def format_dependency_version(name: str, value: Any) -> str:
        sep, suffix = "@", ""
        dep_name = name

        if isinstance(value, dict):
            if version := value.get("version"):
                sep, val = "==", version
            elif git_url := value.get("git"):
                val = f"git+{git_url}" if not git_url.startswith("git@") else git_url
                if rev := value.get("branch") or value.get("rev") or value.get("tag"):
                    val += f"@{rev}"
                if subdir := value.get("subdirectory"):
                    val += f"#subdirectory={subdir}"
            elif path := value.get("path"):
                dep_name, sep, val = "", "", path
            elif url := value.get("url"):
                dep_name, sep, val = "", "", url
            else:
                dep_name, sep, val = name, "", ""

            if markers := value.get("markers"):
                suffix = f";{markers}"
        else:
            sep, val = "==", value

        if val.startswith("^"):
            sep, val = ">=", val[1:]
        elif val.startswith("~"):
            sep, val = "~=", val[1:]
        elif "<" in val or ">" in val:
            sep, val = "", val.replace(" ", "")

        return f"{dep_name}{sep}{val}{suffix}"

    return sorted(
        format_dependency_version(dep, val)
        for dep, val in poetry_deps.items()
        if dep != "python"
    )


def get_pypi_url(name: str, filename: str) -> str:
    url = f"https://pypi.org/pypi/{name}/json"
    print("Extracting download url for", name)
    with urllib.request.urlopen(url) as response:  # noqa: S310
        body = json.loads(response.read().decode("utf-8"))
        for release in body["releases"].values():
            for source in release:
                if source["filename"] == filename:
                    return str(source["url"])
        raise Exception(f"Failed to extract url from {url}")


def get_wheel_urls_for_arches(
    name: str, version: str, python_version: str = "cp312"
) -> dict[str, dict[str, str]]:
    """Get wheel URLs for both aarch64 and x86_64 architectures."""
    url = f"https://pypi.org/pypi/{name}/{version}/json"
    arch_mapping = {
        "aarch64": "manylinux_2_17_aarch64.manylinux2014_aarch64",
        "x86_64": "manylinux_2_17_x86_64.manylinux2014_x86_64",
    }

    results = {}

    with urllib.request.urlopen(url) as response:  # noqa: S310
        body = json.loads(response.read().decode("utf-8"))

        for arch, arch_pattern in arch_mapping.items():
            for source in body["urls"]:
                filename = source["filename"]
                # Match wheels for the specific arch and python version
                if (
                    filename.endswith(".whl")
                    and arch_pattern in filename
                    and python_version in filename
                ):
                    results[arch] = {
                        "url": source["url"],
                        "sha256": source["digests"]["sha256"],
                        "filename": filename,
                    }
                    break

    if len(results) != 2:
        missing = set(arch_mapping.keys()) - set(results.keys())
        raise Exception(
            f"Failed to find wheels for {name}-{version} for architectures: {missing}"
        )

    return results


def get_tar_package_url_pypi(name: str, version: str) -> str:
    url = f"https://pypi.org/pypi/{name}/{version}/json"
    with urllib.request.urlopen(url) as response:  # noqa: S310
        body = json.loads(response.read().decode("utf-8"))
        for ext in ["bz2", "gz", "xz", "zip", "none-any.whl"]:
            for source in body["urls"]:
                if source["url"].endswith(ext):
                    return str(source["url"])
        err = f"Failed to get {name}-{version} source from {url}"
        raise Exception(err)


def get_package_name(filename: str) -> str:
    if filename.endswith(("bz2", "gz", "xz", "zip")):
        segments = filename.split("-")
        if len(segments) == 2:
            return segments[0]
        return "-".join(segments[: len(segments) - 1])
    if filename.endswith("whl"):
        segments = filename.split("-")
        if len(segments) == 5:
            return segments[0]
        candidate = segments[: len(segments) - 4]
        # Some packages list the version number twice
        # e.g. PyQt5-5.15.0-5.15.0-cp35.cp36.cp37.cp38-abi3-manylinux2014_x86_64.whl
        if candidate[-1] == segments[len(segments) - 4]:
            return "-".join(candidate[:-1])
        return "-".join(candidate)
    raise Exception(
        f"Downloaded filename: {filename} does not end with bz2, gz, xz, zip, or whl"
    )


def get_file_version(filename: str) -> str:
    name = get_package_name(filename)
    segments = filename.split(name + "-")
    version = segments[1].split("-")[0]
    for ext in ["tar.gz", "whl", "tar.xz", "tar.gz", "tar.bz2", "zip"]:
        version = version.replace("." + ext, "")
    return version


def get_file_hash(filename: str) -> str:
    sha = hashlib.sha256()
    print("Generating hash for", filename.split("/")[-1])
    with open(filename, "rb") as f:
        while True:
            data = f.read(1024 * 1024 * 32)
            if not data:
                break
            sha.update(data)
        return sha.hexdigest()


def download_tar_pypi(url: str, tempdir: str) -> None:
    if not url.startswith(("https://", "http://")):
        raise ValueError("URL must be HTTP(S)")

    with urllib.request.urlopen(url) as response:  # noqa: S310
        file_path = os.path.join(tempdir, url.split("/")[-1])
        with open(file_path, "x+b") as tar_file:
            shutil.copyfileobj(response, tar_file)


def parse_continuation_lines(fin: TextIO) -> Iterator[str]:
    for raw_line in fin:
        line = raw_line.rstrip("\n")
        while line.endswith("\\"):
            try:
                line = line[:-1] + next(fin).rstrip("\n")
            except StopIteration:
                sys.exit(
                    "Requirements have a wrong number of line "
                    'continuation characters "\\"'
                )
        yield line


def fprint(string: str) -> None:
    separator = "=" * 72  # Same as `flatpak-builder`
    print(separator)
    print(string)
    print(separator)


def get_flatpak_runtime_scope(runtime: str) -> str:
    for scope in ("--user", "--system"):
        try:
            subprocess.run(
                ["flatpak", "info", scope, runtime],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=True,
            )
            return scope
        except subprocess.CalledProcessError:
            continue
    sys.exit(f"Runtime {runtime} not found for user or system")


def handle_req_env_markers(requirements_text: str) -> str:
    def handle_sys_platform(marker: str) -> bool:
        pattern = r'sys_platform\s*(==|!=)\s*["\']([^"\']+)["\']'

        for match in re.finditer(pattern, marker, re.IGNORECASE):
            op, platform = match.group(1), match.group(2).lower()
            if (op == "==" and not platform.startswith("linux")) or (
                op == "!=" and platform.startswith("linux")
            ):
                return False
        return True

    def handle_os_name(marker: str) -> bool:
        pattern = r'os_name\s*(==|!=)\s*["\']([^"\']+)["\']'

        for match in re.finditer(pattern, marker, re.IGNORECASE):
            op, name = match.group(1), match.group(2).lower()
            if (op == "==" and name != "posix") or (op == "!=" and name == "posix"):
                return False
        return True

    def handle_implementation_name(marker: str) -> bool:
        pattern_impl_name = r'implementation_name\s*(==|!=)\s*["\']([^"\']+)["\']'
        pattern_platform_impl = (
            r'platform_python_implementation\s*(==|!=)\s*["\']([^"\']+)["\']'
        )

        current_impl_name = sys.implementation.name.lower()
        current_platform_impl = platform.python_implementation().lower()

        if current_impl_name != "cpython":
            print(
                f"WARNING: sys.implementation.name '{current_impl_name}' does not match fdsdk runtime",
                file=sys.stderr,
            )
        if current_platform_impl != "cpython":
            print(
                f"WARNING: platform.python_implementation() '{current_platform_impl}' "
                f"does not match fdsdk runtime",
                file=sys.stderr,
            )

        for match in re.finditer(pattern_impl_name, marker, re.IGNORECASE):
            op, expected = match.group(1), match.group(2).lower()
            if (op == "==" and expected != current_impl_name) or (
                op == "!=" and expected == current_impl_name
            ):
                return False

        for match in re.finditer(pattern_platform_impl, marker, re.IGNORECASE):
            op, expected = match.group(1), match.group(2).lower()
            if (op == "==" and expected != current_platform_impl) or (
                op == "!=" and expected == current_platform_impl
            ):
                return False

        return True

    def handle_platform_machine(marker: str) -> bool:
        pattern = r'platform_machine\s*(==|!=)\s*["\']([^"\']+)["\']'

        if re.search(pattern, marker, re.IGNORECASE):
            print(
                f"WARNING: Ignoring platform_machine marker: '{marker}'",
                file=sys.stderr,
            )

        return True

    def handle_version_markers(marker: str) -> bool:
        # https://peps.python.org/pep-0496/#version-numbers
        def format_full_version(info) -> str:
            version = f"{info.major}.{info.minor}.{info.micro}"
            if info.releaselevel != "final":
                version += info.releaselevel[0] + str(info.serial)
            return version

        MARKERS: dict[str, str] = {
            "python_version": f"{sys.version_info.major}.{sys.version_info.minor}",  # MAJOR.MINOR, :3 breaks comparison
            "python_full_version": format_full_version(sys.version_info),
            "platform_version": platform.version(),
            "implementation_version": format_full_version(sys.implementation.version),
        }

        OPS: dict[str, Callable[[Version, Version], bool]] = {
            "==": operator.eq,
            "!=": operator.ne,
            "<": operator.lt,
            "<=": operator.le,
            ">": operator.gt,
            ">=": operator.ge,
        }

        PAT = (
            r"(python_version|python_full_version|platform_version|implementation_version)"
            r'\s*(==|!=|<=|>=|<|>)\s*["\']([^"\']+)["\']'
        )

        def to_ver(v: str) -> Version | None:
            for s in (v, v.split("-", 1)[0]):
                try:
                    return Version(s)
                except Exception:
                    pass
            print(f"WARNING: unable to parse version '{v}'", file=sys.stderr)
            return None

        for name, op, rhs in re.findall(PAT, marker):
            lhs = to_ver(MARKERS[name])
            rhs = to_ver(rhs)
            if lhs and rhs and not OPS[op](lhs, rhs):
                return False

        return True

    marker_handlers = (
        handle_sys_platform,
        handle_os_name,
        handle_implementation_name,
        handle_platform_machine,
    )

    filtered_lines = []
    ignored_lines = []

    for line in requirements_text.split("\n"):
        stripped = line.strip()

        if not stripped or stripped.startswith("#"):
            filtered_lines.append(line)
            continue

        if ";" in line:
            marker = line.split(";", 1)[1].strip()
            should_include = all(handler(marker) for handler in marker_handlers)
        else:
            should_include = True

        if should_include:
            filtered_lines.append(line)
        else:
            ignored_lines.append(line)

    if ignored_lines:
        print(f"Ignored packages: {ignored_lines}")

    return "\n".join(filtered_lines)


# Normalize prebuilt wheel package names (case-insensitive, handle underscores)
prebuilt_wheel_packages = set()
if opts.use_prebuilt_wheels:
    for pkg in opts.use_prebuilt_wheels:
        # Normalize: lowercase and replace underscores with hyphens
        normalized = pkg.lower().replace("_", "-")
        prebuilt_wheel_packages.add(normalized)
    print(f"Using prebuilt wheels for: {sorted(prebuilt_wheel_packages)}")

packages = []
if opts.requirements_file:
    requirements_file_input = os.path.expanduser(opts.requirements_file)
    try:
        with open(requirements_file_input) as in_req_file:
            reqs = parse_continuation_lines(in_req_file)
            reqs_as_str = handle_req_env_markers(
                "\n".join([r.split("--hash")[0] for r in reqs])
            )
            reqs_list_raw = reqs_as_str.splitlines()
            py_version_regex = re.compile(
                r";.*python_version .+$"
            )  # Remove when pip-generator can handle python_version
            reqs_list = [py_version_regex.sub("", p) for p in reqs_list_raw]
            if opts.ignore_pkg:
                reqs_new = "\n".join(i for i in reqs_list if i not in opts.ignore_pkg)
            else:
                reqs_new = reqs_as_str
            packages = list(requirements.parse(reqs_new))
            with tempfile.NamedTemporaryFile(
                "w", delete=False, prefix="requirements."
            ) as temp_req_file:
                temp_req_file.write(reqs_new)
                requirements_file_output = temp_req_file.name
    except FileNotFoundError as err:
        print(err)
        sys.exit(1)

elif opts.pyproject_file:
    pyproject_file = os.path.expanduser(opts.pyproject_file)
    with open(pyproject_file, "rb") as f:
        pyproject_data = toml_load(f)
    is_poetry = pyproject_data.get("tool", {}).get("poetry") is not None
    if is_poetry:
        dependencies = get_poetry_deps(pyproject_data)
    else:
        dependencies = pyproject_data.get("project", {}).get("dependencies", [])

    if not dependencies:
        sys.exit("Pyproject file was specified but no dependencies were collected")

    build_system_requires = pyproject_data.get("build-system", {}).get("requires", [])
    if build_system_requires:
        dependencies.extend(build_system_requires)

    if opts.ignore_pkg:
        print(dependencies)
        print(opts.ignore_pkg)
        dependencies = [
            dep for dep in dependencies if dep.split(" ")[0] not in opts.ignore_pkg
        ]

    packages = list(requirements.parse("\n".join(dependencies)))

    with tempfile.NamedTemporaryFile(
        "w", delete=False, prefix="requirements."
    ) as req_file:
        req_file.write("\n".join(dependencies))
        requirements_file_output = req_file.name

elif opts.packages:
    filtered_packages_str = handle_req_env_markers("\n".join(opts.packages))
    packages = list(requirements.parse(filtered_packages_str))
    with tempfile.NamedTemporaryFile(
        "w", delete=False, prefix="requirements."
    ) as req_file:
        req_file.write(filtered_packages_str)
        requirements_file_output = req_file.name
elif not len(sys.argv) > 1:
    sys.exit("Please specifiy either packages or requirements file argument")
else:
    sys.exit("This option can only be used with requirements file")

for i in packages:
    if i["name"].lower().startswith("pyqt"):
        print("PyQt packages are not supported by flapak-pip-generator")
        print("However, there is a BaseApp for PyQt available, that you should use")
        print(
            "Visit https://github.com/flathub/com.riverbankcomputing.PyQt.BaseApp "
            "for more information"
        )
        sys.exit(0)

with open(requirements_file_output) as in_req_file:
    use_hash = "--hash=" in in_req_file.read()

python_version = "2" if opts.python2 else "3"
pip_executable = "pip2" if opts.python2 else "pip3"

if opts.runtime:
    parts = opts.runtime.split("//", 1)
    if len(parts) != 2 or not parts[0] or not parts[1]:
        sys.exit(
            "Runtime argument must be in the following format: $RUNTIME_ID//$RUNTIME_BRANCH"
        )

    flatpak_cmd = [
        "flatpak",
        get_flatpak_runtime_scope(opts.runtime),
        "--devel",
        "--share=network",
        "--filesystem=/tmp",
        f"--command={pip_executable}",
        "run",
        opts.runtime,
    ]
    if opts.requirements_file and os.path.exists(requirements_file_output):
        prefix = os.path.realpath(requirements_file_output)
        flag = f"--filesystem={prefix}"
        flatpak_cmd.insert(1, flag)
else:
    flatpak_cmd = [pip_executable]

output_path = ""
output_package = ""

if opts.output:
    if os.path.isdir(opts.output):
        output_path = opts.output
    else:
        output_path = os.path.dirname(opts.output)
        output_package = os.path.basename(opts.output)

if not output_package:
    if opts.requirements_file:
        output_package = "python{}-{}".format(
            python_version,
            os.path.basename(opts.requirements_file).replace(".txt", ""),
        )
    elif len(packages) == 1:
        output_package = f"python{python_version}-{packages[0].name}"
    else:
        output_package = f"python{python_version}-modules"

output_filename = os.path.join(output_path, output_package)
suffix = ".yaml" if opts.yaml else ".json"
if not output_filename.endswith(suffix):
    output_filename += suffix

modules: list[dict[str, str | list[str] | list[dict[str, Any]]]] = []
vcs_modules: list[dict[str, str | list[str] | list[dict[str, Any]]]] = []
sources = {}
wheel_sources = {}  # Separate storage for wheel-based packages

unresolved_dependencies_errors = []

tempdir_prefix = f"pip-generator-{output_package}"
with tempfile.TemporaryDirectory(prefix=tempdir_prefix) as tempdir:
    pip_download = [
        *flatpak_cmd,
        "download",
        "--exists-action=i",
        "--dest",
        tempdir,
        "-r",
        requirements_file_output,
    ]
    if use_hash:
        pip_download.append("--require-hashes")

    fprint("Downloading sources")
    cmd = " ".join(pip_download)
    print(f'Running: "{cmd}"')
    try:
        subprocess.run(pip_download, check=True)
        os.remove(requirements_file_output)
    except subprocess.CalledProcessError:
        os.remove(requirements_file_output)
        print("Failed to download")
        print("Please fix the module manually in the generated file")
        if not opts.ignore_errors:
            print("Ignore the error by passing --ignore-errors")
            raise

        with suppress(FileNotFoundError):
            os.remove(requirements_file_output)

    fprint("Downloading arch independent packages")
    for filename in os.listdir(tempdir):
        if not filename.endswith(("bz2", "any.whl", "gz", "xz", "zip")):
            version = get_file_version(filename)
            name = get_package_name(filename)
            try:
                url = get_tar_package_url_pypi(name, version)
                print(f"Downloading {url}")
                download_tar_pypi(url, tempdir)
            except Exception as err:
                # Can happen if only an arch dependent wheel is
                # available like for wasmtime-27.0.2
                unresolved_dependencies_errors.append(err)
            print("Deleting", filename)
            with suppress(FileNotFoundError):
                os.remove(os.path.join(tempdir, filename))

    files: dict[str, list[str]] = {get_package_name(f): [] for f in os.listdir(tempdir)}

    for filename in os.listdir(tempdir):
        name = get_package_name(filename)
        files[name].append(filename)

    # Delete redundant sources, for vcs sources
    for name, files_list in files.items():
        if len(files_list) > 1:
            zip_source = False
            for fname in files[name]:
                if fname.endswith(".zip"):
                    zip_source = True
            if zip_source:
                for fname in files[name]:
                    if not fname.endswith(".zip"):
                        with suppress(FileNotFoundError):
                            os.remove(os.path.join(tempdir, fname))

    vcs_packages: dict[str, dict[str, str | None]] = {
        str(x.name): {"vcs": x.vcs, "revision": x.revision, "uri": x.uri}
        for x in packages
        if x.vcs and x.name
    }

    # Process prebuilt wheel packages
    fprint("Processing prebuilt wheel packages")
    for filename in os.listdir(tempdir):
        name = get_package_name(filename)
        normalized_name = name.lower().replace("_", "-")

        if normalized_name in prebuilt_wheel_packages:
            version = get_file_version(filename)
            print(f"Fetching wheel URLs for {name} version {version}")

            try:
                # Determine Python version from the current wheel filename
                py_version_match = re.search(r"cp(\d+)", filename)
                py_version = (
                    f"cp{py_version_match.group(1)}" if py_version_match else "cp312"
                )

                wheel_info = get_wheel_urls_for_arches(name, version, py_version)
                wheel_sources[normalized_name] = {
                    "version": version,
                    "wheels": wheel_info,
                }
                print(f"Successfully fetched wheels for {name}")
            except Exception as err:
                print(f"Warning: Failed to fetch wheels for {name}: {err}")
                unresolved_dependencies_errors.append(err)

    fprint("Obtaining hashes and urls")
    for filename in os.listdir(tempdir):
        source: OrderedDict[str, str | dict[str, str]] = OrderedDict()
        name = get_package_name(filename)
        normalized_name = name.lower().replace("_", "-")

        # Skip if this package should use prebuilt wheels
        if (
            normalized_name in prebuilt_wheel_packages
            and normalized_name in wheel_sources
        ):
            print(f"Skipping {name} (using prebuilt wheels)")
            continue

        sha256 = get_file_hash(os.path.join(tempdir, filename))
        is_pypi = False

        if name in vcs_packages:
            uri = vcs_packages[name]["uri"]
            if not uri:
                raise ValueError(f"Missing URI for VCS package: {name}")
            revision = vcs_packages[name]["revision"]
            vcs = vcs_packages[name]["vcs"]
            if not vcs:
                raise ValueError(
                    f"Unable to determine VCS type for VCS package: {name}"
                )
            url = "https://" + uri.split("://", 1)[1]
            s = "commit"
            if vcs == "svn":
                s = "revision"
            source["type"] = vcs
            source["url"] = url
            if revision:
                source[s] = revision
            is_vcs = True
        else:
            name = name.casefold()
            is_pypi = True
            url = get_pypi_url(name, filename)
            source["type"] = "file"
            source["url"] = url
            source["sha256"] = sha256
            if opts.checker_data:
                checker_data = {"type": "pypi", "name": name}
                if url.endswith(".whl"):
                    checker_data["packagetype"] = "bdist_wheel"
                source["x-checker-data"] = checker_data
            is_vcs = False
        sources[name] = {"source": source, "vcs": is_vcs, "pypi": is_pypi}

# Python3 packages that come as part of org.freedesktop.Sdk.
system_packages = [
    "cython",
    "mako",
    "markdown",
    "meson",
    "packaging",
    "pip",
    "setuptools",
    "wheel",
]

fprint("Generating dependencies")
for package in packages:
    if package.name is None:
        print(
            f"Warning: skipping invalid requirement specification {package.line} "
            "because it is missing a name",
            file=sys.stderr,
        )
        print(
            "Append #egg=<pkgname> to the end of the requirement line to fix",
            file=sys.stderr,
        )
        continue
    elif (
        not opts.python2
        and package.name.casefold() in system_packages
        and package.name.casefold() not in opts.ignore_installed
    ):
        print(f"{package.name} is in system_packages. Skipping.")
        continue

    if len(package.extras) > 0:
        extras = "[" + ",".join(extra for extra in package.extras) + "]"
    else:
        extras = ""

    version_list = [x[0] + x[1] for x in package.specs]
    version = ",".join(version_list)

    if package.vcs:
        revision = ""
        if package.revision:
            revision = "@" + package.revision
        pkg = package.uri + revision + "#egg=" + package.name
    else:
        pkg = package.name + extras + version

    dependencies = []
    # Downloads the package again to list dependencies

    tempdir_prefix = f"pip-generator-{package.name}"
    with tempfile.TemporaryDirectory(
        prefix=f"{tempdir_prefix}-{package.name}"
    ) as tempdir:
        pip_download = [
            *flatpak_cmd,
            "download",
            "--exists-action=i",
            "--dest",
            tempdir,
        ]
        try:
            print(f"Generating dependencies for {package.name}")
            subprocess.run([*pip_download, pkg], check=True, stdout=subprocess.DEVNULL)
            for filename in sorted(os.listdir(tempdir)):
                dep_name = get_package_name(filename)
                if (
                    dep_name.casefold() in system_packages
                    and dep_name.casefold() not in opts.ignore_installed
                ):
                    continue
                dependencies.append(dep_name)

        except subprocess.CalledProcessError:
            print(f"Failed to download {package.name}")

    is_vcs = bool(package.vcs)
    package_sources = []

    # Check if this package should use prebuilt wheels
    normalized_pkg_name = package.name.lower().replace("_", "-")
    use_wheels_for_this_pkg = normalized_pkg_name in wheel_sources

    if use_wheels_for_this_pkg:
        # Add wheel sources for both architectures
        wheel_data = wheel_sources[normalized_pkg_name]
        for arch in ["aarch64", "x86_64"]:
            if arch in wheel_data["wheels"]:
                wheel_info = wheel_data["wheels"][arch]
                wheel_source = OrderedDict(
                    [
                        ("type", "file"),
                        ("url", wheel_info["url"]),
                        ("sha256", wheel_info["sha256"]),
                        ("only-arches", [arch]),
                    ]
                )
                if opts.checker_data:
                    wheel_source["x-checker-data"] = {
                        "type": "pypi",
                        "name": normalized_pkg_name,
                        "packagetype": "bdist_wheel",
                    }
                package_sources.append(wheel_source)

    # Add dependencies (always process dependencies, whether using wheels or not)
    for dependency in dependencies:
        # Skip the main package itself if it's using wheels (already added above)
        dep_normalized = dependency.lower().replace("_", "-")
        if use_wheels_for_this_pkg and dep_normalized == normalized_pkg_name:
            continue

        casefolded = dependency.casefold()
        if casefolded in sources and sources[casefolded].get("pypi") is True:
            source = sources[casefolded]
        elif dependency in sources and sources[dependency].get("pypi") is False:
            source = sources[dependency]
        elif (
            casefolded.replace("_", "-") in sources
            and sources[casefolded.replace("_", "-")].get("pypi") is True
        ):
            source = sources[casefolded.replace("_", "-")]
        elif (
            dependency.replace("_", "-") in sources
            and sources[dependency.replace("_", "-")].get("pypi") is False
        ):
            source = sources[dependency.replace("_", "-")]
        else:
            continue

        if not (not source["vcs"] or is_vcs):
            continue

        package_sources.append(source["source"])

    name_for_pip = "." if package.vcs else pkg

    module_name = f"python{python_version}-{package.name}"

    pip_command = [
        pip_executable,
        "install",
        "--verbose",
        "--exists-action=i",
        "--no-index",
        '--find-links="file://${PWD}"',
        "--prefix=${FLATPAK_DEST}",
        f'"{name_for_pip}"',
    ]
    if package.name in opts.ignore_installed:
        pip_command.append("--ignore-installed")
    if not opts.build_isolation:
        pip_command.append("--no-build-isolation")

    module = OrderedDict(
        [
            ("name", module_name),
            ("buildsystem", "simple"),
            ("build-commands", [" ".join(pip_command)]),
            ("sources", package_sources),
        ]
    )
    if opts.cleanup == "all":
        module["cleanup"] = ["*"]
    elif opts.cleanup == "scripts":
        module["cleanup"] = ["/bin", "/share/man/man1"]

    if package.vcs:
        vcs_modules.append(module)
    else:
        modules.append(module)

modules = vcs_modules + modules
if len(modules) == 1:
    pypi_module = modules[0]
else:
    pypi_module = {
        "name": output_package,
        "buildsystem": "simple",
        "build-commands": [],
        "modules": modules,
    }

print()
with open(output_filename, "w") as output:
    if opts.yaml:

        class OrderedDumper(yaml.Dumper):
            def increase_indent(
                self, flow: bool = False, indentless: bool = False
            ) -> None:
                return super().increase_indent(flow, indentless)

        def dict_representer(
            dumper: yaml.Dumper, data: OrderedDict[str, Any]
        ) -> yaml.nodes.MappingNode:
            return dumper.represent_dict(data.items())

        OrderedDumper.add_representer(OrderedDict, dict_representer)

        output.write(
            "# Generated with flatpak-pip-generator " + " ".join(sys.argv[1:]) + "\n"
        )
        yaml.dump(pypi_module, output, Dumper=OrderedDumper)
    else:
        output.write(json.dumps(pypi_module, indent=4) + "\n")
    print(f"Output saved to {output_filename}")

if len(unresolved_dependencies_errors) != 0:
    print("Unresolved dependencies. Handle them manually")
    for e in unresolved_dependencies_errors:
        print(f"- ERROR: {e}")

    workaround = """Example on how to handle arch dependent wheels:
    - type: file
      url: https://files.pythonhosted.org/packages/79/ae/7e5b85136806f9dadf4878bf73cf223fe5c2636818ba3ab1c585d0403164/numpy-1.26.4-cp311-cp311-manylinux_2_17_aarch64.manylinux2014_aarch64.whl
      sha256: 7ab55401287bfec946ced39700c053796e7cc0e3acbef09993a9ad2adba6ca6e
      only-arches:
      - aarch64
    - type: file
      url: https://files.pythonhosted.org/packages/3a/d0/edc009c27b406c4f9cbc79274d6e46d634d139075492ad055e3d68445925/numpy-1.26.4-cp311-cp311-manylinux_2_17_x86_64.manylinux2014_x86_64.whl
      sha256: 666dbfb6ec68962c033a450943ded891bed2d54e6755e35e5835d63f4f6931d5
      only-arches:
      - x86_64
    """
    raise Exception(
        f"Not all dependencies can be determined. Handle them manually.\n{workaround}"
    )
