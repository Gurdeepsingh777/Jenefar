from __future__ import annotations

import ipaddress
import json
import re
import shutil
import socket
import subprocess
import urllib.error
import urllib.request
from typing import Any


def get_primary_private_ipv4_network() -> dict[str, Any]:
    """Resolve one bounded private IPv4 network from the active LAN interface.

    Virtual/container interfaces are excluded. If multiple plausible physical
    networks exist without a default-route interface to disambiguate them, ask
    the caller to choose rather than guessing a subnet.
    """
    ip_command = shutil.which("ip")
    if not ip_command:
        return {
            "status": "error",
            "error": "The 'ip' utility is unavailable; provide an explicit IPv4 CIDR.",
        }

    try:
        links_result = subprocess.run(
            [ip_command, "-j", "address", "show", "up"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"status": "error", "error": f"Unable to inspect active interfaces: {type(exc).__name__}"}
    if links_result.returncode != 0:
        return {"status": "error", "error": "The active interface query failed; provide an explicit IPv4 CIDR."}

    try:
        links = json.loads(links_result.stdout or "[]")
    except json.JSONDecodeError:
        return {"status": "error", "error": "The active interface result was invalid; provide an explicit IPv4 CIDR."}
    if not isinstance(links, list):
        return {"status": "error", "error": "The active interface result was invalid; provide an explicit IPv4 CIDR."}

    default_interface = ""
    try:
        route_result = subprocess.run(
            [ip_command, "-4", "route", "show", "default"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
        if route_result.returncode == 0:
            match = re.search(r"(?:^|\\s)dev\\s+(\\S+)", route_result.stdout or "")
            if match:
                default_interface = match.group(1)
    except (OSError, subprocess.TimeoutExpired):
        pass

    virtual_prefixes = (
        "docker", "br-", "veth", "virbr", "cni", "flannel", "podman",
        "tun", "tap", "wg", "tailscale", "zt", "lo",
    )
    candidates: list[dict[str, Any]] = []
    oversized: list[dict[str, str]] = []
    for link in links:
        if not isinstance(link, dict):
            continue
        interface = str(link.get("ifname") or "").strip()
        if not interface or interface.casefold().startswith(virtual_prefixes):
            continue
        for record in link.get("addr_info") or []:
            if not isinstance(record, dict) or record.get("family") != "inet":
                continue
            address = str(record.get("local") or "").strip()
            try:
                parsed = ipaddress.ip_address(address)
                prefixlen = int(record.get("prefixlen"))
                if parsed.version != 4 or not parsed.is_private or prefixlen < 0 or prefixlen > 32:
                    continue
                iface = ipaddress.ip_interface(f"{address}/{prefixlen}")
            except (ValueError, TypeError):
                continue
            network = iface.network
            if network.num_addresses > 4096:
                oversized.append({"interface": interface, "network": str(network)})
                continue
            if network.num_addresses < 4:
                continue
            if network.is_loopback or network.is_link_local:
                continue
            item = {
                "interface": interface,
                "address": str(parsed),
                "network": str(network),
                "prefixlen": prefixlen,
                "num_addresses": network.num_addresses,
            }
            if item not in candidates:
                candidates.append(item)

    if not candidates:
        if oversized:
            ranges = ", ".join(f"{item['interface']}={item['network']}" for item in oversized[:4])
            return {
                "status": "too_large",
                "error": f"The detected local network is too broad for automatic discovery ({ranges}). Supply a narrower CIDR explicitly.",
                "networks": oversized[:4],
            }
        return {
            "status": "error",
            "error": "No bounded private IPv4 subnet was found on an active physical interface. Provide the exact IPv4 CIDR.",
        }

    if default_interface:
        preferred = [item for item in candidates if item["interface"] == default_interface]
        if len(preferred) == 1:
            chosen = preferred[0]
        elif len(preferred) > 1:
            return {"status": "ambiguous", "networks": preferred, "default_interface": default_interface}
        elif len(candidates) == 1:
            chosen = candidates[0]
        else:
            return {"status": "ambiguous", "networks": candidates, "default_interface": default_interface}
    elif len(candidates) == 1:
        chosen = candidates[0]
    else:
        return {"status": "ambiguous", "networks": candidates}

    return {"status": "ok", **chosen}


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
