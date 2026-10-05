import asyncio
import sys

import typer

from app.seeds.service import (
    run_all,
    run_seed_area,
    run_seed_categories,
    run_seed_organizational_units,
    run_seed_priorities,
    supported_priorities,
)

app = typer.Typer(help="Seeds: Organizational units, areas, categories and priorities")


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


@app.command("units")
def units():
    n = run_async(run_seed_organizational_units())
    typer.echo(f"Organizational units seed completed ({n} created).")


@app.command("area")
def area(
    area_name: str = typer.Option("Soporte técnico", help="Nombre del área de servicio"),
):
    n = run_async(run_seed_area(area_name))
    typer.echo(f"Service area seed completed ({n} created).")


@app.command("priorities")
def priorities():
    run_async(run_seed_priorities())
    typer.echo(f"Priorities seed completed: {', '.join(supported_priorities())}.")


if __name__ == "__main__":
    app()
