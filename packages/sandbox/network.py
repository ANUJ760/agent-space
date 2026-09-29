"""Network Isolation and SSRF Egress Defense for Agent Space Sandboxes.

Default:
    network = DENY

For approved network access:
    sandbox
       ↓
    controlled egress validator
       ↓
    allowlist matching

Blocks:
- Localhost and loopback (127.0.0.0/8, ::1)
- RFC1918 private IPv4 networks (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16)
- Link-local & cloud metadata endpoints (169.254.169.254, metadata.google.internal)
- Internal service discovery names (postgres, keycloak, redis, nats, temporal)
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

import structlog

logger = structlog.stdlib.get_logger(__name__)

# RFC1918, Loopback, Link-Local, and Cloud Metadata Networks
BLOCKED_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),  # IPv4 loopback
    ipaddress.ip_network("10.0.0.0/8"),  # RFC1918 Class A
    ipaddress.ip_network("172.16.0.0/12"),  # RFC1918 Class B
    ipaddress.ip_network("192.168.0.0/16"),  # RFC1918 Class C
    ipaddress.ip_network("169.254.0.0/16"),  # IPv4 Link-local (Cloud metadata)
    ipaddress.ip_network("::1/128"),  # IPv6 loopback
    ipaddress.ip_network("fc00::/7"),  # IPv6 Unique Local
    ipaddress.ip_network("fe80::/10"),  # IPv6 Link-local
]

FORBIDDEN_HOSTNAMES = {
    "localhost",
    "metadata.google.internal",
    "metadata",
    "postgres",
    "postgresql",
    "redis",
    "nats",
    "temporal",
    "keycloak",
    "qdrant",
    "seaweedfs",
    "gitea",
    "docker",
}


class NetworkEgressBlockedError(PermissionError):
    """Raised when an egress request targets a forbidden, internal, or unallowlisted network."""


def is_ip_blocked(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Check if an IP falls within loopback, RFC1918, link-local, or cloud metadata ranges."""
    for network in BLOCKED_NETWORKS:
        if ip in network:
            return True

    # NAT64 well-known prefix (RFC 6052 64:ff9b::/96) translates public IPv4, not internal private network
    nat64_prefix = ipaddress.ip_network("64:ff9b::/96")
    if ip in nat64_prefix:
        return False

    return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast


def validate_egress_target(
    url_or_host: str,
    allowlist: list[str] | None = None,
) -> bool:
    """Validate whether an outbound network target is permitted.

    Raises NetworkEgressBlockedError if the target points to internal,
    private, loopback, or metadata services, or if it violates the domain allowlist.
    """
    target = url_or_host.strip()
    if "://" in target:
        parsed = urlparse(target)
        hostname = parsed.hostname or ""
    else:
        hostname = target.split(":")[0]

    hostname = hostname.lower().strip()

    if not hostname:
        raise NetworkEgressBlockedError("Empty egress destination hostname")

    # 1. Check prohibited hostname strings
    if hostname in FORBIDDEN_HOSTNAMES or hostname.endswith(".localhost") or hostname.endswith(".internal"):
        logger.warning("network_egress_blocked_hostname", hostname=hostname)
        raise NetworkEgressBlockedError(f"Access to internal service or hostname '{hostname}' is blocked")

    # 2. Check if hostname is directly an IP literal
    try:
        ip = ipaddress.ip_address(hostname)
        if is_ip_blocked(ip):
            logger.warning("network_egress_blocked_ip_literal", ip=str(ip))
            raise NetworkEgressBlockedError(f"Access to private/internal IP '{ip}' is blocked (SSRF defense)")
    except ValueError:
        # Hostname is a domain name, not an IP literal. Resolve DNS.
        try:
            addr_info = socket.getaddrinfo(hostname, None)
            resolved_ips = {res[4][0] for res in addr_info}
            for ip_str in resolved_ips:
                resolved_ip = ipaddress.ip_address(ip_str)
                if is_ip_blocked(resolved_ip):
                    logger.warning("network_egress_blocked_dns_rebinding", hostname=hostname, ip=ip_str)
                    raise NetworkEgressBlockedError(
                        f"Domain '{hostname}' resolves to private/internal IP '{ip_str}' (SSRF defense)"
                    )
        except socket.gaierror:
            # Cannot resolve in isolated environment, will be blocked if allowlist not matched
            pass

    # 3. Check Domain Allowlist if configured
    if allowlist is not None:
        matched = False
        for allowed in allowlist:
            allowed_clean = allowed.lower().strip()
            if hostname == allowed_clean or hostname.endswith(f".{allowed_clean}"):
                matched = True
                break
        if not matched:
            logger.warning("network_egress_not_in_allowlist", hostname=hostname)
            raise NetworkEgressBlockedError(f"Domain '{hostname}' is not in sandbox network allowlist")

    return True
