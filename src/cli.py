from __future__ import annotations

import typer

app = typer.Typer(
    name="kyberna",
    help="Kyberna — Decision Intelligence & Prescriptive Analytics CLI",
    no_args_is_help=True,
)


@app.callback()
def main() -> None:
    """Entry point da CLI Kyberna."""
    pass


if __name__ == "__main__":
    app()
