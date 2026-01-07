"""Tests for SSRF protection."""

import pytest

from src.security.ssrf import (
    is_url_safe,
    is_ip_blocked,
    is_hostname_blocked,
    validate_url,
    SSRFError,
)


class TestIsIpBlocked:
    """Tests for IP blocking."""
    
    def test_localhost_ipv4_blocked(self):
        """Test that localhost IPv4 is blocked."""
        assert is_ip_blocked("127.0.0.1") is True
        assert is_ip_blocked("127.0.0.2") is True
        assert is_ip_blocked("127.255.255.255") is True
    
    def test_localhost_ipv6_blocked(self):
        """Test that localhost IPv6 is blocked."""
        assert is_ip_blocked("::1") is True
    
    def test_private_class_a_blocked(self):
        """Test that 10.x.x.x range is blocked."""
        assert is_ip_blocked("10.0.0.1") is True
        assert is_ip_blocked("10.255.255.255") is True
    
    def test_private_class_b_blocked(self):
        """Test that 172.16-31.x.x range is blocked."""
        assert is_ip_blocked("172.16.0.1") is True
        assert is_ip_blocked("172.31.255.255") is True
        # 172.32.x.x is NOT private
        assert is_ip_blocked("172.32.0.1") is False
    
    def test_private_class_c_blocked(self):
        """Test that 192.168.x.x range is blocked."""
        assert is_ip_blocked("192.168.0.1") is True
        assert is_ip_blocked("192.168.255.255") is True
    
    def test_link_local_blocked(self):
        """Test that link-local addresses are blocked."""
        assert is_ip_blocked("169.254.0.1") is True
        assert is_ip_blocked("169.254.169.254") is True  # Cloud metadata
    
    def test_cgnat_blocked(self):
        """Test that Carrier-Grade NAT range is blocked."""
        assert is_ip_blocked("100.64.0.1") is True
        assert is_ip_blocked("100.127.255.255") is True
    
    def test_public_ip_allowed(self):
        """Test that public IPs are allowed."""
        assert is_ip_blocked("8.8.8.8") is False  # Google DNS
        assert is_ip_blocked("1.1.1.1") is False  # Cloudflare
        assert is_ip_blocked("93.184.216.34") is False  # example.com


class TestIsHostnameBlocked:
    """Tests for hostname blocking."""
    
    def test_localhost_blocked(self):
        """Test that localhost hostnames are blocked."""
        assert is_hostname_blocked("localhost") is True
        assert is_hostname_blocked("LOCALHOST") is True
        assert is_hostname_blocked("localhost.localdomain") is True
    
    def test_metadata_blocked(self):
        """Test that cloud metadata hostnames are blocked."""
        assert is_hostname_blocked("metadata.google.internal") is True
        assert is_hostname_blocked("metadata") is True
    
    def test_normal_hostnames_allowed(self):
        """Test that normal hostnames are allowed."""
        assert is_hostname_blocked("google.com") is False
        assert is_hostname_blocked("api.ra.no") is False
        assert is_hostname_blocked("snl.no") is False


class TestIsUrlSafe:
    """Tests for URL safety checking."""
    
    def test_http_scheme_allowed(self):
        """Test that http scheme is allowed."""
        is_safe, _ = is_url_safe("http://google.com", resolve_dns=False)
        assert is_safe is True
    
    def test_https_scheme_allowed(self):
        """Test that https scheme is allowed."""
        is_safe, _ = is_url_safe("https://google.com", resolve_dns=False)
        assert is_safe is True
    
    def test_file_scheme_blocked(self):
        """Test that file scheme is blocked."""
        is_safe, reason = is_url_safe("file:///etc/passwd", resolve_dns=False)
        assert is_safe is False
        assert "scheme" in reason.lower()
    
    def test_ftp_scheme_blocked(self):
        """Test that ftp scheme is blocked."""
        is_safe, reason = is_url_safe("ftp://server.com/file", resolve_dns=False)
        assert is_safe is False
        assert "scheme" in reason.lower()
    
    def test_localhost_url_blocked(self):
        """Test that localhost URLs are blocked."""
        is_safe, _ = is_url_safe("http://localhost/path", resolve_dns=False)
        assert is_safe is False
        
        is_safe, _ = is_url_safe("http://127.0.0.1/path", resolve_dns=False)
        assert is_safe is False
    
    def test_private_ip_url_blocked(self):
        """Test that private IP URLs are blocked."""
        is_safe, _ = is_url_safe("http://192.168.1.1/", resolve_dns=False)
        assert is_safe is False
        
        is_safe, _ = is_url_safe("http://10.0.0.1/", resolve_dns=False)
        assert is_safe is False
    
    def test_public_url_allowed(self):
        """Test that public URLs are allowed."""
        is_safe, _ = is_url_safe("https://api.ra.no/collections", resolve_dns=False)
        assert is_safe is True
        
        is_safe, _ = is_url_safe("https://snl.no/api/v1/search", resolve_dns=False)
        assert is_safe is True


class TestValidateUrl:
    """Tests for URL validation with exceptions."""
    
    def test_valid_url_does_not_raise(self):
        """Test that valid URLs don't raise exceptions."""
        # Should not raise
        validate_url("https://api.ra.no/")
    
    def test_invalid_url_raises_ssrf_error(self):
        """Test that invalid URLs raise SSRFError."""
        with pytest.raises(SSRFError):
            validate_url("http://localhost/")
        
        with pytest.raises(SSRFError):
            validate_url("http://192.168.1.1/")
        
        with pytest.raises(SSRFError):
            validate_url("file:///etc/passwd")

