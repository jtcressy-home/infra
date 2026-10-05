"""HTTPS callback transport. Resolve per request, pin validated IP, retain TLS SNI."""

import http.client
import ipaddress
import socket
import ssl
import queue
import threading
import time
from urllib.parse import urlsplit
from .store import Invalid

MAX_BODY = 262144
_RESOLVERS = threading.BoundedSemaphore(4)


def destination(url):
    try:
        value = urlsplit(url)
        if (
            value.scheme != "https"
            or not value.hostname
            or value.username
            or value.password
            or value.fragment
            or value.port not in (None, 443)
        ):
            raise ValueError()
        return value
    except (ValueError, TypeError):
        raise Invalid(
            "callback requires HTTPS on port 443 without credentials or fragment"
        ) from None


def resolve(host, timeout):
    # getaddrinfo has no portable timeout. Bound both caller wait and the number
    # of abandoned resolver threads if the platform resolver stops responding.
    if not _RESOLVERS.acquire(blocking=False):
        raise TimeoutError("callback resolver capacity reached")
    result = queue.Queue(maxsize=1)

    def lookup():
        try:
            result.put((socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM), None))
        except Exception as error:
            result.put((None, error))
        finally:
            _RESOLVERS.release()

    threading.Thread(target=lookup, daemon=True).start()
    try:
        addresses, error = result.get(timeout=timeout)
    except queue.Empty:
        raise TimeoutError("callback DNS deadline exceeded") from None
    if error:
        raise error
    return addresses


class PublicHTTPS:
    def __init__(self, timeout=10):
        if timeout <= 0:
            raise ValueError("positive callback timeout required")
        self.timeout = timeout

    def request(self, url, body, headers):
        if len(body) > MAX_BODY:
            return 413, {}, b""
        target = destination(url)
        deadline = time.monotonic() + self.timeout
        lock = threading.Lock()
        active = []
        expired = threading.Event()

        def remaining():
            seconds = deadline - time.monotonic()
            if seconds <= 0 or expired.is_set():
                raise TimeoutError("callback request deadline exceeded")
            return seconds

        def abort():
            with lock:
                expired.set()
                for sock in active:
                    try:
                        sock.shutdown(socket.SHUT_RDWR)
                    except OSError:
                        pass
                    sock.close()

        def track(sock):
            with lock:
                if expired.is_set():
                    sock.close()
                    raise TimeoutError("callback request deadline exceeded")
                active.append(sock)
            return sock

        timer = threading.Timer(self.timeout, abort)
        timer.daemon = True
        timer.start()
        connection = None
        try:
            addresses = resolve(target.hostname, remaining())
            if not addresses:
                raise Invalid("callback DNS lookup failed")
            # Reject mixed public/private answers, not just the selected address.
            for _, _, _, _, address in addresses:
                ip = ipaddress.ip_address(address[0])
                if not ip.is_global or (
                    getattr(ip, "ipv4_mapped", None) and not ip.ipv4_mapped.is_global
                ):
                    raise Invalid("callback address is not public")
            connection = http.client.HTTPSConnection(
                target.hostname,
                443,
                timeout=remaining(),
                context=ssl.create_default_context(),
            )
            raw = track(
                socket.create_connection(addresses[0][4][:2], timeout=remaining())
            )
            # Track the TLS socket before handshake so the overall timer can
            # interrupt a peer that drips handshake, headers or body bytes.
            connection.sock = track(
                connection._context.wrap_socket(
                    raw, server_hostname=target.hostname, do_handshake_on_connect=False
                )
            )
            connection.sock.settimeout(remaining())
            connection.sock.do_handshake()
            path = target.path or "/"
            if target.query:
                path += "?" + target.query
            connection.request("POST", path, body=body, headers=headers)
            response = connection.getresponse()
            payload = response.read(MAX_BODY + 1)
            remaining()  # A deadline-triggered EOF cannot become a success.
            if len(payload) > MAX_BODY:
                raise Invalid("callback response too large")
            return response.status, dict(response.getheaders()), payload
        finally:
            timer.cancel()
            if connection:
                connection.close()
            with lock:
                for sock in active:
                    sock.close()
