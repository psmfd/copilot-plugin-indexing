#!/usr/bin/env python3
"""Install the pinned CocoIndex CLI and prepare selected Git checkouts."""

import argparse
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import venv

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent / "extensions" / "indexing"))
import engine


MODEL_FILES = (
    "config.json", "config_sentence_transformers.json", "model.safetensors",
    "modules.json", "sentence_bert_config.json", "special_tokens_map.json",
    "tokenizer.json", "tokenizer_config.json", "vocab.txt", "1_Pooling/config.json",
)


def write_json(path, value):
    content = json.dumps(value) + "\n"
    if path.is_file() and path.read_text() == content:
        return
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        try:
            stream.write(content)
            stream.flush()
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)


def installed_python(directory, existing_ccc):
    if existing_ccc:
        ccc = existing_ccc.expanduser().resolve(strict=True)
        if ccc.name != "ccc" or not (ccc.parent.parent / "pyvenv.cfg").is_file():
            raise ValueError("--ccc must point to ccc in an isolated Python environment.")
        return ccc.with_name("python")

    python = directory / "venv" / "bin" / "python"
    if not python.is_file():
        venv.EnvBuilder(with_pip=True).create(python.parent.parent)
    try:
        subprocess.run(
            [python, "-I", Path(__file__).resolve(), "--check-toolchain"],
            check=True, capture_output=True,
        )
    except subprocess.CalledProcessError:
        subprocess.run(
            [python, "-I", "-m", "pip", "install", "--upgrade",
             f"cocoindex-code[full]=={engine.VERSION}", "transformers>=5.3.0"],
            check=True,
        )
    return python


def prepare_model(directory):
    from huggingface_hub import snapshot_download
    from huggingface_hub.errors import LocalEntryNotFoundError

    model = directory / "models" / engine.REVISION
    if model.is_dir():
        engine.check_weights(model)
        return model

    model_args = {
        "repo_id": engine.MODEL,
        "revision": engine.REVISION,
        "allow_patterns": MODEL_FILES,
        "token": False,
    }
    try:
        snapshot = Path(snapshot_download(**model_args, local_files_only=True))
    except LocalEntryNotFoundError:
        snapshot = Path(snapshot_download(**model_args))
    if not all((snapshot / name).is_file() for name in MODEL_FILES):
        snapshot = Path(snapshot_download(**model_args))
    if snapshot.name != engine.REVISION:
        raise ValueError("The embedding model snapshot does not match the pinned revision.")
    model.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.TemporaryDirectory(dir=model.parent) as work:
        staged = Path(work) / "model"
        for name in MODEL_FILES:
            destination = staged / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(snapshot / name, destination)
        engine.check_weights(staged)
        try:
            staged.rename(model)
        except OSError:
            if not model.is_dir():
                raise
            engine.check_weights(model)
    return model


def configure(directory, workspace):
    engine.check_toolchain()
    model = prepare_model(directory)
    write_json(directory / "engine" / "global_settings.yml", engine.model_settings(model))
    write_json(directory / "config.json", {"python": sys.executable})
    if workspace is None:
        print("CocoIndex is configured. Run setup with --workspace to build an index.")
        return

    root = engine.workspace_root(workspace)
    if root != workspace.resolve():
        raise ValueError(f"Pass the checkout root to --workspace: {root}")
    project_dir = root / ".cocoindex_code"
    settings = project_dir / "settings.yml"
    if project_dir.is_symlink() or settings.is_symlink() or settings.exists():
        engine.check_project_settings(root)
    else:
        subprocess.run(engine.ccc_command(["init", "--force"]), cwd=root,
                       env=engine.runtime_env(directory), check=True)
    engine.check_project_settings(root)
    subprocess.run(engine.ccc_command(["index"]), cwd=root,
                   env=engine.runtime_env(directory), check=True)
    write_json(engine.workspace_marker(directory, root), {"root": str(root)})
    print(f"Index ready for {root}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, help="Git checkout root to initialize or refresh")
    parser.add_argument("--ccc", type=Path, help="reuse ccc from an existing pinned virtual environment")
    parser.add_argument("--check-toolchain", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--configure", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.check_toolchain:
        engine.check_toolchain()
        return

    directory = engine.state_dir()
    if args.configure:
        configure(directory, args.workspace)
        return

    if sys.version_info < (3, 11) or os.name != "posix":
        raise ValueError("This proof of concept requires Python 3.11+ on macOS or Linux.")
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    config = directory / "config.json"
    if args.ccc is None and config.is_file():
        python = Path(json.loads(config.read_text())["python"])
    else:
        python = installed_python(directory, args.ccc)
    command = [python, "-I", Path(__file__).resolve(), "--configure"]
    if args.workspace:
        command.extend(("--workspace", args.workspace.resolve(strict=True)))
    keys = (
        "HOME", "PATH", "TMPDIR", "LANG", "LC_ALL", "COPILOT_INDEXING_HOME", "HF_HOME",
        "HF_HUB_CACHE", "HUGGINGFACE_HUB_CACHE", "HTTPS_PROXY", "HTTP_PROXY", "NO_PROXY",
        "https_proxy", "http_proxy", "no_proxy", "SSL_CERT_FILE", "REQUESTS_CA_BUNDLE",
    )
    env = {key: os.environ[key] for key in keys if key in os.environ}
    env["HF_HUB_DISABLE_TELEMETRY"] = "1"
    subprocess.run(command, env=env, check=True)


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as error:
        sys.exit(error.returncode)
    except (OSError, ValueError, importlib.metadata.PackageNotFoundError) as error:
        sys.exit(str(error))
