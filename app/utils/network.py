def get_ping_response_time(host: str, count: int = 5) -> float:
    """
    Ping tool: Get average ping response time from a remote host using ICMP protocol.

    Args:
        host (str): IP address or hostname to ping
        count (int): Number of pings to average (default: 5)

    Returns:
        float: Average response time in milliseconds, or -1 if host is unreachable
    """
    print(f"ping {host} to get the response time.")
    try:
        from ping3 import ping

        total_time = 0
        successful_pings = 0

        for _ in range(count):
            response_time = ping(host, timeout=2)
            if response_time is not None:
                total_time += response_time
                successful_pings += 1

        if successful_pings == 0:
            return -1

        # Convert to milliseconds and return average
        return (total_time / successful_pings) * 1000

    except Exception:
        return -1


def check_port_available(host: str, port: int, timeout: float = 2.0) -> bool:
    """
    Telnet tool: Check if a remote host:port is available using telnet protocol.

    Args:
        host (str): IP address or hostname to check
        port (int): Port number to check
        timeout (float): Connection timeout in seconds (default: 2.0)

    Returns:
        bool: True if port is available, False otherwise
    """
    print(f"check_port_available for {host}.")
    import socket

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except (socket.gaierror, socket.error, Exception):
        return False
