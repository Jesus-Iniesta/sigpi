"""Pruebas unitarias de la resolución de la IP auditada (S5-08)."""

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.core.network import is_trusted_proxy, parse_trusted_proxies, resolve_client_ip

FORWARDED = "203.0.113.7, 10.0.0.1"


def test_lista_vacia_no_confia_en_ningun_proxy() -> None:
    assert parse_trusted_proxies("") == []
    assert parse_trusted_proxies(" , ") == []
    assert resolve_client_ip("10.0.0.1", FORWARDED, []) == "10.0.0.1"


def test_acepta_ips_y_redes_cidr_separadas_por_comas() -> None:
    trusted = parse_trusted_proxies("10.0.0.1, 172.16.0.0/12 ,::1")

    assert is_trusted_proxy("10.0.0.1", trusted)
    assert is_trusted_proxy("172.20.3.4", trusted)
    assert is_trusted_proxy("::1", trusted)
    assert not is_trusted_proxy("10.0.0.2", trusted)


def test_host_que_no_es_ip_o_ausente_no_es_de_confianza() -> None:
    trusted = parse_trusted_proxies("10.0.0.1")

    assert not is_trusted_proxy("testclient", trusted)
    assert not is_trusted_proxy(None, trusted)


def test_desde_proxy_de_confianza_usa_el_primer_salto_del_encabezado() -> None:
    trusted = parse_trusted_proxies("10.0.0.1")

    assert resolve_client_ip("10.0.0.1", FORWARDED, trusted) == "203.0.113.7"


def test_encabezado_vacio_desde_proxy_usa_la_ip_directa() -> None:
    trusted = parse_trusted_proxies("10.0.0.1")

    assert resolve_client_ip("10.0.0.1", " , ", trusted) == "10.0.0.1"
    assert resolve_client_ip("10.0.0.1", None, trusted) == "10.0.0.1"


def test_sin_cliente_directo_no_hay_ip() -> None:
    assert resolve_client_ip(None, FORWARDED, parse_trusted_proxies("10.0.0.1")) is None


def test_ip_se_recorta_al_largo_de_la_columna() -> None:
    trusted = parse_trusted_proxies("10.0.0.1")

    assert len(resolve_client_ip("10.0.0.1", "x" * 80, trusted)) == 45


def test_config_rechaza_proxies_invalidos() -> None:
    assert Settings(trusted_proxies="10.0.0.1,10.1.0.0/16").trusted_proxies
    with pytest.raises(ValidationError):
        Settings(trusted_proxies="no-es-una-ip")
