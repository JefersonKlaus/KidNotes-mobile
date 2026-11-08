"""Ponto de entrada do RelatórioFácil Infantil.

Execute com: flet run main.py
"""

import flet as ft

from app import RelatorioFacilApp


def main(page: ft.Page) -> None:
    RelatorioFacilApp(page)


if __name__ == "__main__":
    ft.run(main)
