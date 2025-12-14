#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import click
import yaml

from smurfsniper import service
from smurfsniper.models.config import Config

DEFAULT_CONFIG_NAME = "config.yml"
DEFAULT_URL = "http://localhost:6119/game"
VERSION = "0.1.0"


def load_config(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise click.ClickException(f"Config file not found: {path}")

    if path.is_dir():
        raise click.ClickException(f"Config path is a directory: {path}")

    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def apply_overrides(config: Dict[str, Any], overrides: list[str]) -> None:
    """
    Apply overrides of the form key.subkey=value
    NOTE: These apply BEFORE pydantic validation.
    """
    for item in overrides:
        if "=" not in item:
            raise click.ClickException(
                f"Invalid override '{item}'. Expected key=value"
            )

        key, value = item.split("=", 1)
        parts = key.split(".")

        cursor: Dict[str, Any] = config
        for part in parts[:-1]:
            cursor = cursor.setdefault(part, {})

        v: Any = value
        if value.lower() in {"true", "false"}:
            v = value.lower() == "true"
        else:
            try:
                v = int(value)
            except ValueError:
                pass

        cursor[parts[-1]] = v


def load_and_validate_config(
    path: Path,
    overrides: list[str],
) -> Config:
    raw = load_config(path)
    apply_overrides(raw, overrides)

    try:
        return Config.from_config_file(path)
    except Exception as e:
        raise click.ClickException(f"Config validation failed: {e}")

def run_service(
    *,
    url: str,
    config_path: Path,
    config: Config,
) -> None:
    click.echo("Service starting with config:")
    click.echo(yaml.dump(config.model_dump(), sort_keys=False))

    click.echo(f"Using SC2 game API: {url}")
    click.echo("Running service loop (ctrl+c to exit)")

    service.main(
        url=url,
        config_file_path=str(config_path),
    )

@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(VERSION)
def cli() -> None:
    """SmurfSniper service runner."""
    pass


@cli.command()
@click.option(
    "--config",
    "config_path",
    type=click.Path(
        exists=False,
        dir_okay=False,
        path_type=Path,
    ),
    default=Path.cwd() / DEFAULT_CONFIG_NAME,
    show_default=True,
    help="Path to config file",
)
@click.option(
    "--url",
    default=DEFAULT_URL,
    show_default=True,
    help="SC2 game API endpoint",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Validate config and exit",
)
@click.option(
    "--set",
    "overrides",
    multiple=True,
    metavar="KEY=VALUE",
    help="Override config values (can be repeated)",
)
def run(
    config_path: Path,
    url: str,
    dry_run: bool,
    overrides: tuple[str, ...],
) -> None:
    """
    Run the SmurfSniper service.
    """
    config = load_and_validate_config(
        config_path,
        list(overrides),
    )

    if dry_run:
        click.secho("Config is valid", fg="green")
        return

    run_service(
        url=url,
        config_path=config_path,
        config=config,
    )


@cli.command()
@click.option(
    "--config",
    "config_path",
    type=click.Path(
        exists=False,
        dir_okay=False,
        path_type=Path,
    ),
    default=Path.cwd() / DEFAULT_CONFIG_NAME,
    show_default=True,
    help="Path to config file",
)
@click.option(
    "--set",
    "overrides",
    multiple=True,
    metavar="KEY=VALUE",
    help="Override config values (can be repeated)",
)
@click.option(
    "--show",
    is_flag=True,
    help="Print the validated config",
)
def validate(
    config_path: Path,
    overrides: tuple[str, ...],
    show: bool,
) -> None:
    """
    Validate the SmurfSniper configuration.
    """
    config = load_and_validate_config(
        config_path,
        list(overrides),
    )

    click.secho("Config is valid", fg="green")

    if show:
        click.echo()
        click.echo(yaml.dump(config.model_dump(), sort_keys=False))


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
