"""SSRF (Server-Side Request Forgery) protection utilities."""

import ipaddress
import logging
import socket
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class SSRFError(Exception):
    """Raised when a URL is blocked due to SSRF protection."""
    pass


# Private/reserved IP ranges that should be blocked
BLOCKED_NETWORKS = [
    # Loopback
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
    
    # Private networks (RFC 1918)
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    
    # Link-local
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("fe80::/10"),
    
    # Carrier-grade NAT (RFC 6598)
    ipaddress.ip_network("100.64.0.0/10"),
    
    # Documentation/example ranges
    ipaddress.ip_network("192.0.2.0/24"),
    ipaddress.ip_network("198.51.100.0/24"),
    ipaddress.ip_network("203.0.113.0/24"),
    ipaddress.ip_network("2001:db8::/32"),
    
    # Broadcast
    ipaddress.ip_network("255.255.255.255/32"),
    
    # Unspecified
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("::/128"),
    
    # Cloud metadata endpoints
    ipaddress.ip_network("169.254.169.254/32"),  # AWS, GCP, Azure metadata
]

# Blocked hostnames (case-insensitive)
BLOCKED_HOSTNAMES = {
    "localhost",
    "localhost.localdomain",
    "metadata.google.internal",
    "metadata",
}


def is_ip_blocked(ip_str: str) -> bool:
    """Check if an IP address is in a blocked range."""
    try:
        ip = ipaddress.ip_address(ip_str)
        return any(ip in network for network in BLOCKED_NETWORKS)
    except ValueError:
        # Invalid IP address format
        return True  # Block by default if we can't parse it


def is_hostname_blocked(hostname: str) -> bool:
    """Check if a hostname is explicitly blocked."""
    hostname_lower = hostname.lower()
    return hostname_lower in BLOCKED_HOSTNAMES


def resolve_hostname(hostname: str) -> list[str]:
    """Resolve a hostname to IP addresses."""
    try:
        results = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC)
        return list(set(result[4][0] for result in results))
    except socket.gaierror:
        return []


def is_url_safe(url: str, resolve_dns: bool = True) -> tuple[bool, str]:
    """
    Check if a URL is safe from SSRF attacks.
    
    Args:
        url: The URL to check.
        resolve_dns: If True, also resolve hostname and check IPs.
    
    Returns:
        Tuple of (is_safe, reason). If not safe, reason explains why.
    """
    # Parse the URL
    try:
        parsed = urlparse(url)
    except Exception as e:
        return False, f"Invalid URL: {e}"
    
    # Check scheme
    if parsed.scheme not in ("http", "https"):
        return False, f"Invalid scheme: {parsed.scheme}. Only http/https allowed."
    
    # Get hostname
    hostname = parsed.hostname
    if not hostname:
        return False, "No hostname in URL"
    
    # Check blocked hostnames
    if is_hostname_blocked(hostname):
        return False, f"Blocked hostname: {hostname}"
    
    # Check if hostname is a literal IP address
    try:
        ip = ipaddress.ip_address(hostname)
        if is_ip_blocked(hostname):
            return False, f"Blocked IP address: {hostname}"
    except ValueError:
        # Not an IP address, it's a hostname
        pass
    
    # Resolve DNS and check resulting IPs (only if requested)
    if resolve_dns:
        ips = resolve_hostname(hostname)
        if not ips:
            return False, f"Could not resolve hostname: {hostname}"
        
        for ip in ips:
            if is_ip_blocked(ip):
                return False, f"Hostname {hostname} resolves to blocked IP: {ip}"
    
    return True, "URL is safe"


def validate_url(url: str) -> None:
    """
    Validate a URL for SSRF safety, raising SSRFError if unsafe.
    
    Args:
        url: The URL to validate.
    
    Raises:
        SSRFError: If the URL is not safe.
    """
    is_safe, reason = is_url_safe(url)
    if not is_safe:
        logger.warning(f"SSRF blocked URL: {url} - {reason}")
        raise SSRFError(reason)

