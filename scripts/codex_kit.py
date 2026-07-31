#!/usr/bin/env python3
"""Deterministic validation and AGENTS.md rendering for Codex Kit."""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import difflib
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import tempfile
import unicodedata
from typing import Any, Sequence


SCHEMA_VERSION = 2
KEBAB_CASE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
GITHUB_REPOSITORY = re.compile(
    r"https://github\.com/[A-Za-z0-9][A-Za-z0-9_.-]*/"
    r"[A-Za-z0-9_.-]+(?:\.git)?/?\Z"
)
FRONTMATTER_FIELD = re.compile(r"([A-Za-z][A-Za-z0-9_-]*):[ \t]*(.*)\Z")

MANAGED_START = b"<!-- codex-kit:managed:start -->"
MANAGED_END = b"<!-- codex-kit:managed:end -->"
MANAGED_TOKEN = b"codex-kit:managed:"
RESERVED_MODULE_TOKEN = b"codex-kit:"


class CodexKitError(Exception):
    """A user-actionable validation or rendering error."""


@dataclasses.dataclass(frozen=True)
class CatalogSpec:
    filename: str
    array_name: str
    required_fields: frozenset[str]
    optional_fields: frozenset[str]


CATALOG_SPECS = (
    CatalogSpec(
        "skills.json",
        "skills",
        frozenset({"id", "description", "source"}),
        frozenset({"repository", "path", "scope", "recommended", "notes"}),
    ),
    CatalogSpec(
        "plugins.json",
        "plugins",
        frozenset({"id", "description", "repository"}),
        frozenset({"marketplace", "plugin", "recommended", "notes"}),
    ),
    CatalogSpec(
        "agents.json",
        "modules",
        frozenset({"id", "description", "path"}),
        frozenset({"recommended"}),
    ),
)


@dataclasses.dataclass(frozen=True)
class Catalogs:
    skills: tuple[dict[str, Any], ...]
    plugins: tuple[dict[str, Any], ...]
    modules: tuple[dict[str, Any], ...]
    module_bodies: dict[str, bytes]


@dataclasses.dataclass(frozen=True)
class FileSnapshot:
    exists: bool
    content: bytes
    mode: int | None


@dataclasses.dataclass(frozen=True)
class RenderPlan:
    target: Path
    current: FileSnapshot
    rendered: bytes
    current_sha256: str
    rendered_sha256: str


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CodexKitError(f"duplicate JSON object key: {key!r}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise CodexKitError(f"non-standard JSON number is not allowed: {value}")


def _contains_control_character(value: str) -> bool:
    return any(unicodedata.category(character) == "Cc" for character in value)


def _check_json_controls(value: Any, context: str) -> None:
    if isinstance(value, str):
        if _contains_control_character(value):
            raise CodexKitError(f"{context} contains a control character")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _check_json_controls(item, f"{context}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            _check_json_controls(key, f"{context} object key")
            _check_json_controls(item, f"{context}.{key}")


def _read_json(path: Path) -> Any:
    raw = _read_regular_file(path, allow_missing=False).content
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise CodexKitError(f"{path} is not valid UTF-8: {error}") from error
    try:
        value = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_json_constant,
        )
    except json.JSONDecodeError as error:
        raise CodexKitError(
            f"{path} is not valid JSON at line {error.lineno}, "
            f"column {error.colno}: {error.msg}"
        ) from error
    _check_json_controls(value, str(path))
    return value


def _require_exact_type(
    item: dict[str, Any], field: str, expected: type, context: str
) -> Any:
    value = item[field]
    if type(value) is not expected:
        raise CodexKitError(
            f"{context}.{field} must be {expected.__name__}, "
            f"got {type(value).__name__}"
        )
    return value


def _require_nonempty_string(
    item: dict[str, Any], field: str, context: str
) -> str:
    value = _require_exact_type(item, field, str, context)
    if not value.strip():
        raise CodexKitError(f"{context}.{field} must not be empty")
    return value


def _validate_optional_string(
    item: dict[str, Any], field: str, context: str, *, nonempty: bool
) -> str | None:
    if field not in item:
        return None
    value = _require_exact_type(item, field, str, context)
    if nonempty and not value.strip():
        raise CodexKitError(f"{context}.{field} must not be empty")
    return value


def _validate_relative_posix_path(path_text: str, context: str) -> None:
    parts = path_text.split("/")
    if (
        path_text.startswith("/")
        or "\\" in path_text
        or any(part in {"", ".", ".."} for part in parts)
        or PurePosixPath(path_text).is_absolute()
    ):
        raise CodexKitError(
            f"{context} must be a repository-relative POSIX path without "
            "empty, '.' or '..' segments"
        )


def _validate_common_item(item: Any, spec: CatalogSpec, index: int) -> dict[str, Any]:
    context = f"{spec.filename}.{spec.array_name}[{index}]"
    if type(item) is not dict:
        raise CodexKitError(f"{context} must be an object")

    fields = set(item)
    missing = spec.required_fields - fields
    unknown = fields - spec.required_fields - spec.optional_fields
    if missing:
        raise CodexKitError(
            f"{context} is missing required field(s): {', '.join(sorted(missing))}"
        )
    if unknown:
        raise CodexKitError(
            f"{context} has unknown field(s): {', '.join(sorted(unknown))}"
        )

    item_id = _require_nonempty_string(item, "id", context)
    if not KEBAB_CASE.fullmatch(item_id):
        raise CodexKitError(f"{context}.id must use kebab-case")
    _require_nonempty_string(item, "description", context)

    if "recommended" in item:
        _require_exact_type(item, "recommended", bool, context)
    return item


def _validate_module_path(repo: Path, path_text: str, context: str) -> tuple[Path, bytes]:
    _validate_relative_posix_path(path_text, f"{context}.path")
    pure = PurePosixPath(path_text)
    if (
        pure.is_absolute()
        or len(pure.parts) != 3
        or pure.parts[:2] != ("agents", "modules")
        or pure.name in {"", ".", ".."}
        or pure.suffix != ".md"
        or "\\" in path_text
    ):
        raise CodexKitError(
            f"{context}.path must match agents/modules/*.md "
            "and use a repository-relative POSIX path"
        )

    for directory in (repo / "agents", repo / "agents" / "modules"):
        try:
            directory_status = directory.lstat()
        except OSError as error:
            raise CodexKitError(
                f"cannot inspect module directory {directory}: {error}"
            ) from error
        if (
            stat.S_ISLNK(directory_status.st_mode)
            or not stat.S_ISDIR(directory_status.st_mode)
        ):
            raise CodexKitError(
                f"module directory must be a non-symlink directory: {directory}"
            )

    candidate = repo.joinpath(*pure.parts)
    body = _read_regular_file(candidate, allow_missing=False).content
    resolved = candidate.resolve()
    try:
        resolved.relative_to(repo)
    except ValueError as error:
        raise CodexKitError(f"{context}.path escapes the repository: {path_text}") from error

    try:
        body_text = body.decode("utf-8")
    except UnicodeDecodeError as error:
        raise CodexKitError(f"module {path_text} is not valid UTF-8: {error}") from error
    for character in body_text:
        if (
            unicodedata.category(character) == "Cc"
            and character not in {"\n", "\r", "\t"}
        ):
            raise CodexKitError(f"module {path_text} contains a control character")
    if not body_text.strip():
        raise CodexKitError(f"module {path_text} must not be empty")
    if RESERVED_MODULE_TOKEN in body:
        raise CodexKitError(
            f"module {path_text} contains the reserved codex-kit marker token"
        )
    return candidate, body


def _is_forbidden_bundled_name(name: str) -> bool:
    return (
        name in {".git", ".DS_Store", "__pycache__"}
        or name.startswith(".env")
    )


def _read_bundled_skill_tree(
    repo: Path, skill_path: str, context: str
) -> tuple[Path, dict[PurePosixPath, bytes]]:
    pure = PurePosixPath(skill_path)
    current = repo
    for part in pure.parts:
        current /= part
        try:
            current_status = current.lstat()
        except FileNotFoundError as error:
            raise CodexKitError(
                f"{context}.path bundled Skill directory does not exist: {skill_path}"
            ) from error
        except OSError as error:
            raise CodexKitError(
                f"cannot inspect bundled Skill directory {current}: {error}"
            ) from error
        if stat.S_ISLNK(current_status.st_mode) or not stat.S_ISDIR(
            current_status.st_mode
        ):
            raise CodexKitError(
                f"bundled Skill path component must be a non-symlink directory: "
                f"{current}"
            )

    skill_root = current
    files: dict[PurePosixPath, bytes] = {}
    pending = [skill_root]
    while pending:
        directory = pending.pop()
        try:
            directory_status = directory.lstat()
        except OSError as error:
            raise CodexKitError(
                f"cannot inspect bundled Skill directory {directory}: {error}"
            ) from error
        if stat.S_ISLNK(directory_status.st_mode) or not stat.S_ISDIR(
            directory_status.st_mode
        ):
            raise CodexKitError(
                f"bundled Skill directory must be a non-symlink directory: "
                f"{directory}"
            )

        try:
            entries = sorted(os.scandir(directory), key=lambda entry: entry.name)
        except OSError as error:
            raise CodexKitError(
                f"cannot list bundled Skill directory {directory}: {error}"
            ) from error
        for entry in entries:
            candidate = Path(entry.path)
            relative = PurePosixPath(candidate.relative_to(skill_root).as_posix())
            if _is_forbidden_bundled_name(entry.name):
                raise CodexKitError(
                    f"{context}.path contains forbidden bundled Skill artifact: "
                    f"{relative}"
                )
            try:
                entry_status = entry.stat(follow_symlinks=False)
            except OSError as error:
                raise CodexKitError(
                    f"cannot inspect bundled Skill entry {candidate}: {error}"
                ) from error
            if stat.S_ISLNK(entry_status.st_mode):
                raise CodexKitError(
                    f"bundled Skill entry must be non-symlink: {candidate}"
                )
            if stat.S_ISDIR(entry_status.st_mode):
                pending.append(candidate)
                continue
            if not stat.S_ISREG(entry_status.st_mode):
                raise CodexKitError(
                    f"bundled Skill entry must be a regular file or directory: "
                    f"{candidate}"
                )
            files[relative] = _read_regular_file(
                candidate, allow_missing=False
            ).content
    return skill_root, files


def _parse_frontmatter_scalar(
    raw_value: str, field: str, skill_path: str
) -> str:
    value = raw_value.strip()
    if not value:
        return ""
    if value[0] == '"':
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as error:
            raise CodexKitError(
                f"{skill_path} frontmatter {field} has an invalid quoted value"
            ) from error
        if type(parsed) is not str:
            raise CodexKitError(
                f"{skill_path} frontmatter {field} must be a string"
            )
        return parsed
    if value[0] == "'":
        if len(value) < 2 or value[-1] != "'":
            raise CodexKitError(
                f"{skill_path} frontmatter {field} has an invalid quoted value"
            )
        return value[1:-1].replace("''", "'")
    if value in {"|", ">", "|-", ">-", "|+", ">+", "null", "Null", "NULL", "~"}:
        raise CodexKitError(
            f"{skill_path} frontmatter {field} must use a non-empty one-line string"
        )
    comment = re.search(r"[ \t]+#", value)
    if comment is not None:
        value = value[: comment.start()].rstrip()
    return value


def _validate_skill_frontmatter(
    content: bytes, item_id: str, skill_path: str
) -> None:
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as error:
        raise CodexKitError(
            f"{skill_path}/SKILL.md is not valid UTF-8: {error}"
        ) from error
    lines = text.splitlines()
    if not lines or lines[0] != "---":
        raise CodexKitError(
            f"{skill_path}/SKILL.md must start with YAML frontmatter"
        )
    try:
        end = lines.index("---", 1)
    except ValueError as error:
        raise CodexKitError(
            f"{skill_path}/SKILL.md has unterminated YAML frontmatter"
        ) from error

    fields: dict[str, str] = {}
    for line_number, line in enumerate(lines[1:end], start=2):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = FRONTMATTER_FIELD.fullmatch(line)
        if match is None:
            raise CodexKitError(
                f"{skill_path}/SKILL.md frontmatter line {line_number} "
                "must be a simple key-value field"
            )
        field, raw_value = match.groups()
        if field in fields:
            raise CodexKitError(
                f"{skill_path}/SKILL.md frontmatter has duplicate field: {field}"
            )
        fields[field] = _parse_frontmatter_scalar(
            raw_value, field, f"{skill_path}/SKILL.md"
        )

    name = fields.get("name")
    if name != item_id:
        raise CodexKitError(
            f"{skill_path}/SKILL.md frontmatter name must equal catalog id "
            f"{item_id!r}"
        )
    description = fields.get("description")
    if description is None or not description.strip():
        raise CodexKitError(
            f"{skill_path}/SKILL.md frontmatter description must not be empty"
        )


def _validate_bundled_skill(
    repo: Path, item_id: str, skill_path: str, context: str
) -> None:
    _, files = _read_bundled_skill_tree(repo, skill_path, context)
    skill_file = PurePosixPath("SKILL.md")
    if skill_file not in files:
        raise CodexKitError(f"{context}.path SKILL.md is required")
    if not any(
        license_path in files
        for license_path in (PurePosixPath("LICENSE"), PurePosixPath("LICENSE.txt"))
    ):
        raise CodexKitError(f"{context}.path LICENSE or LICENSE.txt is required")

    _validate_skill_frontmatter(files[skill_file], item_id, skill_path)
    for relative, content in files.items():
        if relative.suffix.lower() != ".md":
            continue
        try:
            content.decode("utf-8")
        except UnicodeDecodeError as error:
            raise CodexKitError(
                f"{skill_path}/{relative} is not valid UTF-8: {error}"
            ) from error


def validate_catalogs(repo_arg: str | os.PathLike[str]) -> Catalogs:
    repo_input = Path(repo_arg).expanduser()
    try:
        repo = repo_input.resolve(strict=True)
    except OSError as error:
        raise CodexKitError(f"repository does not exist: {repo_input}") from error
    if not repo.is_dir():
        raise CodexKitError(f"repository is not a directory: {repo}")

    catalog_dir = repo / "catalog"
    try:
        catalog_status = catalog_dir.lstat()
    except OSError as error:
        raise CodexKitError(
            f"cannot inspect catalog directory {catalog_dir}: {error}"
        ) from error
    if (
        stat.S_ISLNK(catalog_status.st_mode)
        or not stat.S_ISDIR(catalog_status.st_mode)
    ):
        raise CodexKitError(
            f"catalog path must be a non-symlink directory: {catalog_dir}"
        )

    loaded: dict[str, tuple[dict[str, Any], ...]] = {}
    module_bodies: dict[str, bytes] = {}

    for spec in CATALOG_SPECS:
        path = catalog_dir / spec.filename
        value = _read_json(path)
        if type(value) is not dict:
            raise CodexKitError(f"{path} top level must be an object")
        expected_top_fields = {"schema_version", spec.array_name}
        fields = set(value)
        missing = expected_top_fields - fields
        unknown = fields - expected_top_fields
        if missing:
            raise CodexKitError(
                f"{path} is missing top-level field(s): {', '.join(sorted(missing))}"
            )
        if unknown:
            raise CodexKitError(
                f"{path} has unknown top-level field(s): "
                f"{', '.join(sorted(unknown))}"
            )
        if (
            type(value["schema_version"]) is not int
            or value["schema_version"] != SCHEMA_VERSION
        ):
            raise CodexKitError(
                f"{path}.schema_version must be integer {SCHEMA_VERSION}"
            )
        items = value[spec.array_name]
        if type(items) is not list:
            raise CodexKitError(f"{path}.{spec.array_name} must be an array")

        validated: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        for index, raw_item in enumerate(items):
            item = _validate_common_item(raw_item, spec, index)
            context = f"{spec.filename}.{spec.array_name}[{index}]"
            item_id = item["id"]
            if item_id in seen_ids:
                raise CodexKitError(
                    f"{spec.filename}.{spec.array_name} has duplicate id: {item_id}"
                )
            seen_ids.add(item_id)

            if spec.array_name == "plugins":
                repository = _require_nonempty_string(
                    item, "repository", context
                )
                if not GITHUB_REPOSITORY.fullmatch(repository):
                    raise CodexKitError(
                        f"{context}.repository must be an HTTPS github.com "
                        "repository URL"
                    )
                _validate_optional_string(
                    item, "notes", context, nonempty=False
                )

            if spec.array_name == "skills":
                source = _require_exact_type(item, "source", str, context)
                if source not in {"github", "bundled"}:
                    raise CodexKitError(
                        f"{context}.source must be 'github' or 'bundled'"
                    )
                _validate_optional_string(
                    item, "notes", context, nonempty=False
                )
                if source == "github":
                    if "repository" not in item:
                        raise CodexKitError(
                            f"{context} github source requires repository"
                        )
                    repository = _require_nonempty_string(
                        item, "repository", context
                    )
                    if not GITHUB_REPOSITORY.fullmatch(repository):
                        raise CodexKitError(
                            f"{context}.repository must be an HTTPS github.com "
                            "repository URL"
                        )
                    skill_path = _validate_optional_string(
                        item, "path", context, nonempty=True
                    )
                    if skill_path is not None:
                        _validate_relative_posix_path(
                            skill_path, f"{context}.path"
                        )
                else:
                    if "repository" in item:
                        raise CodexKitError(
                            f"{context} bundled source must not include repository"
                        )
                    if "path" not in item:
                        raise CodexKitError(
                            f"{context} bundled source requires path"
                        )
                    skill_path = _require_nonempty_string(
                        item, "path", context
                    )
                    _validate_relative_posix_path(
                        skill_path, f"{context}.path"
                    )
                    expected_path = f"bundled/skills/{item_id}"
                    if skill_path != expected_path:
                        raise CodexKitError(
                            f"{context}.path must be exactly {expected_path}"
                        )
                    _validate_bundled_skill(
                        repo, item_id, skill_path, context
                    )
                if "scope" in item:
                    scope = _require_exact_type(item, "scope", str, context)
                    if scope not in {"user", "project"}:
                        raise CodexKitError(
                            f"{context}.scope must be 'user' or 'project'"
                        )

            if spec.array_name == "plugins":
                for field in ("marketplace", "plugin"):
                    name = _validate_optional_string(
                        item, field, context, nonempty=True
                    )
                    if name is not None and not KEBAB_CASE.fullmatch(name):
                        raise CodexKitError(
                            f"{context}.{field} must use kebab-case"
                        )

            if spec.array_name == "modules":
                module_path = _require_nonempty_string(item, "path", context)
                _, body = _validate_module_path(repo, module_path, context)
                module_bodies[item_id] = body

            validated.append(item)
        loaded[spec.array_name] = tuple(validated)

    return Catalogs(
        skills=loaded["skills"],
        plugins=loaded["plugins"],
        modules=loaded["modules"],
        module_bodies=module_bodies,
    )


def _read_regular_file(path: Path, *, allow_missing: bool) -> FileSnapshot:
    try:
        before = path.lstat()
    except FileNotFoundError:
        if allow_missing:
            return FileSnapshot(False, b"", None)
        raise CodexKitError(f"file does not exist: {path}")
    except OSError as error:
        raise CodexKitError(f"cannot inspect {path}: {error}") from error

    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
        raise CodexKitError(f"must be a non-symlink regular file: {path}")

    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise CodexKitError(f"cannot safely open {path}: {error}") from error
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode):
            raise CodexKitError(f"must be a regular file: {path}")
        if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
            raise CodexKitError(f"file changed while opening: {path}")
        with os.fdopen(descriptor, "rb") as stream:
            descriptor = -1
            content = stream.read()
            after = os.fstat(stream.fileno())
            if (
                (after.st_dev, after.st_ino) != (opened.st_dev, opened.st_ino)
                or after.st_size != opened.st_size
                or after.st_mtime_ns != opened.st_mtime_ns
                or after.st_ctime_ns != opened.st_ctime_ns
            ):
                raise CodexKitError(f"file changed while reading: {path}")
    except OSError as error:
        raise CodexKitError(f"cannot read {path}: {error}") from error
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    return FileSnapshot(True, content, stat.S_IMODE(opened.st_mode))


def _check_codex_home(codex_home_arg: str | os.PathLike[str]) -> Path:
    codex_home = Path(codex_home_arg).expanduser()
    try:
        home_status = codex_home.lstat()
    except FileNotFoundError as error:
        raise CodexKitError(f"Codex home does not exist: {codex_home}") from error
    except OSError as error:
        raise CodexKitError(f"cannot inspect Codex home {codex_home}: {error}") from error
    if stat.S_ISLNK(home_status.st_mode) or not stat.S_ISDIR(home_status.st_mode):
        raise CodexKitError(
            f"Codex home must be a non-symlink directory: {codex_home}"
        )
    return codex_home.resolve()


def _check_override(codex_home: Path) -> None:
    override = codex_home / "AGENTS.override.md"
    snapshot = _read_regular_file(override, allow_missing=True)
    if snapshot.exists and snapshot.content:
        raise CodexKitError(
            f"non-empty AGENTS.override.md takes precedence; refusing to render: "
            f"{override}"
        )


def _origin_marker(module_id: str, boundary: str) -> bytes:
    return f"<!-- codex-kit:module:{module_id}:{boundary} -->".encode("ascii")


def _render_managed_block(
    modules: Sequence[dict[str, Any]], module_bodies: dict[str, bytes]
) -> bytes:
    parts = [MANAGED_START]
    for module in modules:
        module_id = module["id"]
        parts.append(_origin_marker(module_id, "start"))
        body = module_bodies[module_id]
        parts.append(body)
        parts.append(_origin_marker(module_id, "end"))
    parts.append(MANAGED_END)

    rendered = bytearray()
    for index, part in enumerate(parts):
        if index:
            previous = parts[index - 1]
            if not previous.endswith(b"\n"):
                rendered.extend(b"\n")
        rendered.extend(part)
    return bytes(rendered)


def _render_target(current: bytes, block: bytes) -> bytes:
    start_count = current.count(MANAGED_START)
    end_count = current.count(MANAGED_END)
    generic_count = current.count(MANAGED_TOKEN)

    if start_count == 0 and end_count == 0:
        if generic_count:
            raise CodexKitError("AGENTS.md contains a malformed managed marker")
        if not current:
            return block + b"\n"
        if current.endswith(b"\n\n"):
            separator = b""
        elif current.endswith(b"\n"):
            separator = b"\n"
        else:
            separator = b"\n\n"
        return current + separator + block + b"\n"

    if start_count != 1 or end_count != 1 or generic_count != 2:
        raise CodexKitError(
            "AGENTS.md must contain either no managed markers or exactly one "
            "start marker and one end marker"
        )
    start = current.index(MANAGED_START)
    end = current.index(MANAGED_END)
    if start >= end:
        raise CodexKitError("AGENTS.md managed markers are reversed")
    end += len(MANAGED_END)
    return current[:start] + block + current[end:]


def _digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _select_modules(
    catalogs: Catalogs, selected_ids: Sequence[str]
) -> tuple[dict[str, Any], ...]:
    if not selected_ids:
        raise CodexKitError("at least one --module ID is required")
    duplicates = sorted(
        item_id for item_id in set(selected_ids) if selected_ids.count(item_id) > 1
    )
    if duplicates:
        raise CodexKitError(
            f"duplicate --module ID(s): {', '.join(duplicates)}"
        )
    available = {module["id"] for module in catalogs.modules}
    unknown = sorted(set(selected_ids) - available)
    if unknown:
        raise CodexKitError(f"unknown module ID(s): {', '.join(unknown)}")
    selected = set(selected_ids)
    return tuple(module for module in catalogs.modules if module["id"] in selected)


def build_render_plan(
    repo_arg: str | os.PathLike[str],
    codex_home_arg: str | os.PathLike[str],
    selected_ids: Sequence[str],
) -> RenderPlan:
    catalogs = validate_catalogs(repo_arg)
    modules = _select_modules(catalogs, selected_ids)
    codex_home = _check_codex_home(codex_home_arg)
    _check_override(codex_home)
    target = codex_home / "AGENTS.md"
    current = _read_regular_file(target, allow_missing=True)
    if current.exists:
        try:
            current.content.decode("utf-8")
        except UnicodeDecodeError as error:
            raise CodexKitError(
                f"{target} is not valid UTF-8 and cannot be rendered: {error}"
            ) from error
    block = _render_managed_block(modules, catalogs.module_bodies)
    rendered = _render_target(current.content, block)
    current_digest = _digest(current.content) if current.exists else "MISSING"
    return RenderPlan(
        target=target,
        current=current,
        rendered=rendered,
        current_sha256=current_digest,
        rendered_sha256=_digest(rendered),
    )


def _unified_diff(plan: RenderPlan) -> str:
    try:
        current_text = plan.current.content.decode("utf-8")
    except UnicodeDecodeError as error:
        raise CodexKitError(
            f"{plan.target} is not valid UTF-8 and cannot be rendered: {error}"
        ) from error
    rendered_text = plan.rendered.decode("utf-8")
    return "".join(
        difflib.unified_diff(
            current_text.splitlines(keepends=True),
            rendered_text.splitlines(keepends=True),
            fromfile=str(plan.target),
            tofile=f"{plan.target} (rendered)",
        )
    )


def _validate_expected_hash(value: str, *, allow_missing: bool, name: str) -> None:
    if allow_missing and value == "MISSING":
        return
    if not SHA256.fullmatch(value):
        expected = "MISSING or a lowercase SHA-256" if allow_missing else "a lowercase SHA-256"
        raise CodexKitError(f"{name} must be {expected}")


def _assert_expected(
    plan: RenderPlan, expected_current: str, expected_rendered: str
) -> None:
    if plan.current_sha256 != expected_current:
        raise CodexKitError(
            "current AGENTS.md changed after preview: "
            f"expected {expected_current}, got {plan.current_sha256}"
        )
    if plan.rendered_sha256 != expected_rendered:
        raise CodexKitError(
            "rendered AGENTS.md changed after preview: "
            f"expected {expected_rendered}, got {plan.rendered_sha256}"
        )


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    descriptor = os.open(path, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _ensure_backup_directory(path: Path) -> None:
    try:
        directory_status = path.lstat()
    except FileNotFoundError:
        try:
            path.mkdir(mode=0o700)
        except FileExistsError:
            pass
        try:
            directory_status = path.lstat()
        except OSError as error:
            raise CodexKitError(
                f"cannot inspect backup directory {path}: {error}"
            ) from error
    except OSError as error:
        raise CodexKitError(
            f"cannot inspect backup directory {path}: {error}"
        ) from error

    if (
        stat.S_ISLNK(directory_status.st_mode)
        or not stat.S_ISDIR(directory_status.st_mode)
    ):
        raise CodexKitError(
            f"backup path must be a non-symlink directory: {path}"
        )


def _write_backup(codex_home: Path, snapshot: FileSnapshot) -> Path:
    backups = codex_home / "backups"
    _ensure_backup_directory(backups)
    backup_root = backups / "codex-kit"
    _ensure_backup_directory(backup_root)
    timestamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    backup_dir = backup_root / timestamp
    counter = 0
    while True:
        candidate = backup_dir if counter == 0 else backup_root / f"{timestamp}-{counter}"
        try:
            candidate.mkdir()
            backup_dir = candidate
            break
        except FileExistsError:
            counter += 1

    backup = backup_dir / "AGENTS.md"
    descriptor = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, snapshot.mode or 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = -1
            stream.write(snapshot.content)
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    if snapshot.mode is not None:
        os.chmod(backup, snapshot.mode)
    _fsync_directory(backup_dir)
    _fsync_directory(backup_root)
    return backup


def _command_validate(args: argparse.Namespace) -> int:
    catalogs = validate_catalogs(args.repo)
    print(
        "catalogs valid: "
        f"{len(catalogs.skills)} skill(s), "
        f"{len(catalogs.plugins)} plugin(s), "
        f"{len(catalogs.modules)} module(s)"
    )
    return 0


def _command_render(args: argparse.Namespace) -> int:
    if args.apply:
        if args.expect_current_sha256 is None or args.expect_rendered_sha256 is None:
            raise CodexKitError(
                "--apply requires --expect-current-sha256 and "
                "--expect-rendered-sha256 from a prior preview"
            )
        _validate_expected_hash(
            args.expect_current_sha256,
            allow_missing=True,
            name="--expect-current-sha256",
        )
        _validate_expected_hash(
            args.expect_rendered_sha256,
            allow_missing=False,
            name="--expect-rendered-sha256",
        )
    elif args.expect_current_sha256 is not None or args.expect_rendered_sha256 is not None:
        raise CodexKitError("expected hashes are accepted only with --apply")

    plan = build_render_plan(args.repo, args.codex_home, args.module)
    print(f"current_sha256={plan.current_sha256}")
    print(f"rendered_sha256={plan.rendered_sha256}")

    if not args.apply:
        diff = _unified_diff(plan)
        if diff:
            sys.stdout.write(diff)
        else:
            print("(no changes)")
        return 0

    _assert_expected(
        plan, args.expect_current_sha256, args.expect_rendered_sha256
    )
    if plan.current.exists and plan.current.content == plan.rendered:
        print("no changes; nothing written")
        return 0

    # Re-read all inputs immediately before preparing the write. This catches
    # edits made between validation, preview, and application.
    verified = build_render_plan(args.repo, args.codex_home, args.module)
    _assert_expected(
        verified, args.expect_current_sha256, args.expect_rendered_sha256
    )

    backup: Path | None = None
    if verified.current.exists:
        backup = _write_backup(verified.target.parent, verified.current)

    # Prepare the same-directory temporary file, then perform one final
    # input check before the atomic replacement.
    directory = verified.target.parent
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".AGENTS.md.codex-kit-", dir=directory
    )
    temporary = Path(temporary_name)
    try:
        if verified.current.mode is not None:
            os.fchmod(descriptor, verified.current.mode)
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = -1
            stream.write(verified.rendered)
            stream.flush()
            os.fsync(stream.fileno())

        final_plan = build_render_plan(args.repo, args.codex_home, args.module)
        _assert_expected(
            final_plan, args.expect_current_sha256, args.expect_rendered_sha256
        )
        if final_plan.current.exists:
            os.replace(temporary, final_plan.target)
        else:
            try:
                os.link(
                    temporary,
                    final_plan.target,
                    follow_symlinks=False,
                )
            except FileExistsError as error:
                raise CodexKitError(
                    "AGENTS.md appeared after the final missing-file check; "
                    "refusing to overwrite it"
                ) from error
            temporary.unlink()
        _fsync_directory(directory)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass

    print(f"updated={verified.target}")
    if backup is not None:
        print(f"backup={backup}")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate Codex Kit catalogs and render managed AGENTS.md content."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate", help="validate all catalogs")
    validate.add_argument("--repo", required=True, help="Codex Kit repository root")
    validate.set_defaults(handler=_command_validate)

    render = subparsers.add_parser(
        "render-agents", help="preview or apply selected AGENTS.md modules"
    )
    render.add_argument("--repo", required=True, help="Codex Kit repository root")
    render.add_argument("--codex-home", required=True, help="target Codex home")
    render.add_argument(
        "--module",
        action="append",
        default=[],
        metavar="ID",
        help="module ID to render; repeat for multiple modules",
    )
    render.add_argument(
        "--apply", action="store_true", help="write the previously previewed result"
    )
    render.add_argument("--expect-current-sha256")
    render.add_argument("--expect-rendered-sha256")
    render.set_defaults(handler=_command_render)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        return args.handler(args)
    except CodexKitError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    except OSError as error:
        print(f"error: operating-system failure: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
