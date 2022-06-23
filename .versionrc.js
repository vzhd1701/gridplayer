const version_updater_regex = {
  readVersion: function (contents) {
    version_m = contents.match(this.regex);
    if (!version_m)
      throw new Error("Cannot parse version!");
    return version_m[1];
  },
  writeVersion: function (contents, version) {
    new_version = this.regex_repl.replace("$1", version);
    return contents.replace(this.regex, new_version);
  }
}

let version_updater_poetry = {...version_updater_regex};
version_updater_poetry.regex = /^version = \"([^\"]+)\"$/m;
version_updater_poetry.regex_repl = "version = \"$1\"";

// YYYY-MM-DD
let today = new Date().toISOString().substring(0, 10);

let version_updater_python = {...version_updater_regex};
version_updater_python.regex = /^__version__ = \"([^\"]+)\"\n__version_date__ = \"[^\"]+\"$/m;
version_updater_python.regex_repl = "__version__ = \"$1\"\n__version_date__ = \"" + today + "\"";

let version_updater_readme = {...version_updater_regex};
version_updater_readme.regex = /\d+\.\d+\.\d+/g;
version_updater_readme.regex_repl = "$1";

version_file = "gridplayer/version.py"

let packageFiles = [
  {
    filename: "pyproject.toml",
    updater: version_updater_poetry,
  }
]

let bumpFiles = packageFiles.concat([
  {
    filename: version_file,
    updater: version_updater_python,
  },
  {
    filename: "README.md",
    updater: version_updater_readme,
  }
])

module.exports = {
  header: "",
  commitAll: true,
  sign: true,
  packageFiles: packageFiles,
  bumpFiles: bumpFiles,
  skip: {
    changelog: true
  },
  scripts: {
    postbump: `poetry run python scripts/_helpers/kacl.py "${version_file}" CHANGELOG.md && git add CHANGELOG.md`
  }
}
