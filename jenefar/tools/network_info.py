from __future__ import annotations

import ipaddress
import json
import shutil
import socket
import subprocess
import urllib.error
import urllib.request
from typing import Any


def get_network_ip_info() -> dict[str, Any]:
    """Read local interface IPs and optionally query one service for public IPv4.

    This helper never scans hosts or subnets. The public-IP lookup sends a
    normal HTTPS request only to api.ipify.org and is best-effort.
    """
    ipv4: list[dict[str, str]] = []
    ipv6: list[dict[str, str]] = []
    interfaces: list[str] = []
    ip_command = shutil.which("ip")

    if ip_command:
        try:
            result = subprocess.run(
                [ip_command, "-j", "address", "show", "up"],
                capture_output=True,
                text=True,
                timeout=3,
                check=False,
            )
            if result.returncode == 0:
                links = json.loads(result.stdout or "[]")
                if isinstance(links, list):
                    for link in links:
                        if not isinstance(link, dict):
                            continue
                        interface = str(link.get("ifname") or "").strip()
                        if not interface or interface == "lo":
                            continue
                        for record in link.get("addr_info") or []:
                            if not isinstance(record, dict):
                                continue
                            address = str(record.get("local") or "").strip()
                            try:
                                parsed = ipaddress.ip_address(address)
                            except ValueError:
                                continue
                            if parsed.is_loopback or parsed.is_link_local or parsed.is_unspecified:
                                continue
                            item = {"address": str(parsed), "interface": interface}
                            target = ipv4 if parsed.version == 4 else ipv6
                            if item not in target:
                                target.append(item)
                            if interface not in interfaces:
                                interfaces.append(interface)
        except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError, TypeError):
            pass

    # Portable best-effort fallback for systems where the JSON ip output is unavailable.
    if not ipv4 and not ipv6:
        try:
            for family, _socktype, _proto, _canonname, sockaddr in socket.getaddrinfo(
                socket.gethostname(), None, type=socket.SOCK_STREAM
            ):
                address = str(sockaddr[0]).split("%", 1)[0]
                try:
                    parsed = ipaddress.ip_address(address)
                except ValueError:
                    continue
                if parsed.is_loopback or parsed.is_link_local or parsed.is_unspecified:
                    continue
                item = {"address": str(parsed), "interface": "host-resolution"}
                target = ipv4 if parsed.version == 4 else ipv6
                if item not in target:
                    target.append(item)
                if "host-resolution" not in interfaces:
                    interfaces.append("host-resolution")
        except OSError:
            pass

    public_ip = ""
    public_ip_status = "unavailable"
    try:
        request = urllib.request.Request(
            "https://api.ipify.org?format=json",
            headers={"User-Agent": "Jenefar/1.0"},
        )
        with urllib.request.urlopen(request, timeout=4) as response:
            raw = response.read(512).decode("utf-8", errors="replace").strip()
        try:
            payload = json.loads(raw)
            candidate = str(payload.get("ip") or "").strip() if isinstance(payload, dict) else raw
        except json.JSONDecodeError:
            candidate = raw
        parsed_public = ipaddress.ip_address(candidate)
        if parsed_public.version == 4:
            public_ip = str(parsed_public)
            public_ip_status = "available"
        else:
            public_ip_status = "service returned a non-IPv4 address"
    except (OSError, urllib.error.URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
        public_ip_status = f"unavailable ({type(exc).__name__})"

    return {
        "local_ipv4": ipv4,
        "local_ipv6": ipv6,
        "interfaces": interfaces,
        "public_ipv4": public_ip or None,
        "public_ipv4_status": public_ip_status,
        "method": "local interface inspection; optional HTTPS public-IP lookup",
        "network_scan_performed": False,
    }
