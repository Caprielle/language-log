"""Build the local exportation package; never upload or change visibility."""

import json
import re
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


PACKAGE_RESOURCES = (
    Path("SKILL.md"), Path("agents/openai.yaml"),
    Path("references/snapshot-format.md"), Path("scripts/export_chat.py"),
)
SOURCE_RESOURCES = (*PACKAGE_RESOURCES, Path("scripts/test_export_chat.py"))


def check_tree(root, allowed):
    for item in root.rglob("*"):
        if item.is_symlink() or item.is_junction():
            raise ValueError("Package inputs must not contain links or junctions")
        if item.is_file() and item.relative_to(root) not in allowed:
            raise ValueError("Unexpected package input: " + str(item.relative_to(root)))


def build(repository):
    repository = Path(repository).resolve()
    source = repository / ".agents" / "skills" / "exportation"
    plugin = repository / "plugins" / "exportation"
    if source.is_symlink() or source.is_junction() or plugin.is_symlink() or plugin.is_junction():
        raise ValueError("Skill and plugin roots must be ordinary directories")
    manifest_file = plugin / "plugin.json"
    if manifest_file.is_symlink():
        raise ValueError("Plugin manifest must not be a link")
    manifest_bytes = manifest_file.read_bytes()
    manifest = json.loads(manifest_bytes)
    if manifest.get("$schema") != "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json":
        raise ValueError("Unexpected plugin schema")
    if manifest.get("name") != "exportation":
        raise ValueError("Unexpected plugin name")
    version = manifest.get("version")
    if not isinstance(version, str) or not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError("Use a numeric major.minor.patch plugin version")
    interface = manifest["extensions"]["com.openai"]["interface"]
    for key in ("displayName", "shortDescription", "longDescription", "developerName", "category"):
        if not isinstance(interface.get(key), str) or not interface[key].strip():
            raise ValueError("Missing or invalid plugin presentation text: " + key)
    if len(interface["shortDescription"]) > 30:
        raise ValueError("Plugin shortDescription must be at most 30 characters")
    capabilities = interface.get("capabilities")
    if not isinstance(capabilities, list) or any(not isinstance(c, str) or not c.strip() for c in capabilities):
        raise ValueError("Plugin capabilities must be an array of nonblank strings")
    check_tree(source, set(SOURCE_RESOURCES))
    payload = {Path("plugin.json"): manifest_bytes}
    for resource in SOURCE_RESOURCES:
        candidate = source / resource
        if not candidate.is_file():
            raise ValueError("Missing skill resource: " + str(resource))
        if resource in PACKAGE_RESOURCES:
            payload[Path("skills/exportation") / resource] = candidate.read_bytes()
    check_tree(plugin, set(payload))
    output = repository / "_local" / "exportation" / f"exportation-{version}.zip"
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise FileExistsError("Archive already exists; change the version before rebuilding")
    for relative, data in payload.items():
        if relative == Path("plugin.json"):
            continue
        destination = plugin / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
    with ZipFile(output, "x", compression=ZIP_DEFLATED) as archive:
        for relative in sorted(payload):
            archive.writestr(relative.as_posix(), payload[relative])
    with ZipFile(output) as archive:
        if archive.testzip() is not None or set(archive.namelist()) != {p.as_posix() for p in payload}:
            raise ValueError("Archive structure or integrity check failed: " + str(output))
        for relative, data in payload.items():
            if archive.read(relative.as_posix()) != data or (plugin / relative).read_bytes() != data:
                raise ValueError("Package content mismatch: " + relative.as_posix())
    return output


if __name__ == "__main__":
    print(build(Path(__file__).resolve().parents[1]))
