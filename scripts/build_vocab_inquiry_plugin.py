"""Package the repository's Vocab Inquiry skill without unrelated files."""

import json
import re
import shutil
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


def build(repository: Path) -> Path:
    repository = repository.resolve()
    source = repository / ".agents" / "skills" / "vocab-inquiry"
    plugin = repository / "plugins" / "vocab-inquiry"
    manifest = json.loads((plugin / "plugin.json").read_text(encoding="utf-8"))
    if manifest["name"] != "vocab-inquiry":
        raise ValueError("Unexpected plugin name")
    version = manifest["version"]
    if not isinstance(version, str) or not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError("Use a numeric major.minor.patch plugin version")

    resources = (Path("SKILL.md"), Path("agents/openai.yaml"))
    allowed = {Path("plugin.json")} | {
        Path("skills/vocab-inquiry") / resource for resource in resources
    }
    for item in plugin.rglob("*"):
        if item.is_symlink():
            raise ValueError("Plugin package must not contain symlinks")
        if item.is_file() and item.relative_to(plugin) not in allowed:
            raise ValueError("Unexpected package file: " + str(item.relative_to(plugin)))
    for resource in resources:
        if not (source / resource).is_file() or (source / resource).is_symlink():
            raise ValueError("Missing or linked source file: " + str(resource))
    for item in source.rglob("*"):
        if item.is_symlink():
            raise ValueError("Skill source must not contain symlinks")
        if item.is_file() and item.relative_to(source) not in resources:
            raise ValueError("Unexpected skill resource: " + str(item.relative_to(source)))

    output = repository / "_local" / "vocab-inquiry" / f"vocab-inquiry-{version}.zip"
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise FileExistsError("Archive already exists; change the plugin version before rebuilding")
    for resource in resources:
        destination = plugin / "skills" / "vocab-inquiry" / resource
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / resource, destination)

    with ZipFile(output, "x", compression=ZIP_DEFLATED) as archive:
        for relative in sorted(allowed):
            archive.write(plugin / relative, arcname=relative.as_posix())
    with ZipFile(output) as archive:
        if archive.testzip() is not None:
            raise ValueError("Archive integrity check failed")
        for relative in allowed:
            if archive.read(relative.as_posix()) != (plugin / relative).read_bytes():
                raise ValueError("Archive content mismatch: " + relative.as_posix())
    return output


if __name__ == "__main__":
    print(build(Path(__file__).resolve().parents[1]))
