import asyncio
import sys

import typer

from app.seeds.service import (
    run_all,
    run_seed_categories,
    run_seed_priorities,
    supported_priorities,
)

app = typer.Typer(help="Seeds: Categories and priorities")


def run_async(coro) -> object:
    if sys.platform == "win32":
        return asyncio.run(coro, loop_factory=asyncio.SelectorEventLoop)
    return asyncio.run(coro)


@app.command("all")
def all_(
    area_name: str = typer.Option("Soporte técnico", help="Área de servicio para las categorías"),
):
    counts = run_async(run_all(area_name))
    typer.echo(f"All seeds completed: {counts}")


@app.command("categories")
def categories(
    area_name: str = typer.Option("Soporte técnico", help="Área de servicio para las categorías"),
):
    n = run_async(run_seed_categories(area_name))
    typer.echo(f"Categories seed completed ({n} created).")


@app.command("priorities")
def priorities():
    run_async(run_seed_priorities())
    typer.echo(f"Priorities seed completed: {', '.join(supported_priorities())}.")


if __name__ == "__main__":
    app()