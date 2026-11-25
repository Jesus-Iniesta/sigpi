"""Resolución de la IP de origen de una petición para la auditoría (S5-08).

`X-Forwarded-For` lo puede escribir cualquier cliente, así que solo se toma en cuenta
cuando la conexión directa viene de un proxy de confianza (`TRUSTED_PROXIES`).
"""

import ipaddress
from collections.abc import Iterable

IPNetwork = ipaddress.IPv4Network | ipaddress.IPv6Network

# Longitud de la columna `audit_logs.ip_address` (cabe una IPv6 completa).
IP_MAX_LENGTH = 45


def parse_trusted_proxies(raw: str) -> list[IPNetwork]:
    """Convierte la lista separada por comas (IPs o redes CIDR) en redes; ignora vacíos."""
    networks: list[IPNetwork] = []
    for item in raw.split(","):
        value = item.strip()
        if value:
            networks.append(ipaddress.ip_network(value, strict=False))
    return networks


def is_trusted_proxy(host: str | None, trusted: Iterable[IPNetwork]) -> bool:
    """Indica si `host` pertenece a alguna de las redes de confianza."""
    if not host:
        return False
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    return any(address in network for network in trusted)


def resolve_client_ip(
    direct_host: str | None, forwarded_for: str | None, trusted: Iterable[IPNetwork]
) -> str | None:
    """IP que se audita: el primer salto de `X-Forwarded-For` solo si la conexión directa
    viene de un proxy de confianza; en cualquier otro caso, la del cliente directo."""
    if forwarded_for and is_trusted_proxy(direct_host, trusted):
        first = forwarded_for.split(",")[0].strip()
        if first:
            return first[:IP_MAX_LENGTH]
    if direct_host is None:
        return None
    return direct_host[:IP_MAX_LENGTH]
