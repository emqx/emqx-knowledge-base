import logging
import json
import urllib.request
import requests
from functools import cache

logger = logging.getLogger(__name__)


class EmqxToolWrapper:
    def __init__(self, endpoint, username, password):
        self.endpoint = endpoint
        self.username = username
        self.password = password

    def get_cluster_info(self) -> str:
        """
        Return the EMQX cluster information for the server. The
        returned value include EMQX version number, edtion (such as
        open source or enterprise etc), cluster status (running or
        stopped) etc. It helps you to know the overall status of the
        EMQX cluster.

        Returns:

            str: A string that represents the status of the cluster. A sample cluster information is as in below.
            [{'node': 'emqx@172.17.0.2', 'version': '5.8.3', 'otp_release': '26.2.5.2-1/14.2.5.2', 'load1': 0.0, 'uptime': 14302535, 'role': 'core', 'memory_used': '1.14G', 'memory_total': '7.68G', 'node_status': 'running', 'edition': 'Enterprise', 'max_fds': 1048576, 'connections': 0, 'load15': 0.07, 'load5': 0.07, 'live_connections': 0, 'cluster_sessions': 0, 'log_path': 'log.file.enable is false, not logging to file.', 'process_available': 2097152, 'process_used': 822, 'sys_path': '/opt/emqx'}]
        """
        return make_emqx_api_request(
            base_url=self.endpoint,
            api="/api/v5/nodes",
            username=self.username,
            password=self.password,
        )

    def get_connector_info(self) -> str:
        """
        The function is used for getting information for
        connectors. The tag value for connectors is started with
        "CONNECTOR", such as "CONNECTOR/MYSQL".
        The EMQX connector is a key concept in data integration,
        serving as the underlying connection channel for Sink/Source,
        used to connect to external data systems.
        The connector focuses solely on connecting to external data
        systems. Users can create different connectors for various
        external data systems, and a single connector can provide
        connections for multiple Sinks/Sources.

        Returns:

            str: A string that represents the status of the connector.
        """
        return make_emqx_api_request(
            base_url=self.endpoint,
            api="/api/v5/connectors",
            username=self.username,
            password=self.password,
        )

    def get_authentication_info(self) -> str:
        """
        The function is used for getting information for
        authentications. The tag value for connectors is started with
        "AUTHN", such as "AUTHN/WEBHOOK".
        Authentication is the process of verifying the identity of a
        client. It is an essential part of most applications and can
        help to protect our services from illegal client connections.

        Returns:

            str: A string that represents the status of the authentication.
        """
        return make_emqx_api_request(
            base_url=self.endpoint,
            api="/api/v5/authentication",
            username=self.username,
            password=self.password,
        )


@cache
def emqx_login(endpoint: str, username: str, password: str) -> str:
    """Obtain an authentication token from the EMQX broker.

    Args:
        endpoint: The EMQX API endpoint
        username: EMQX API username
        password: EMQX API password

    Returns:
        str: Token if successful, empty string if failed
    """
    # Ensure the endpoint doesn't end with a slash
    if endpoint.endswith("/"):
        endpoint = endpoint[:-1]

    try:
        # Set a timeout for the request (5 seconds)
        login_url = f"{endpoint}/api/v5/login"
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        payload = {"username": username, "password": password}

        # Request the token
        response = requests.post(
            login_url, headers=headers, data=json.dumps(payload), timeout=5
        )

        if response.status_code == 200:
            token_data = response.json()
            token = token_data.get("token", "")
            if token:
                logger.info("Successfully obtained EMQX API token")
                return token
            else:
                logger.error("Token not found in response")
                return ""
        else:
            logger.error(
                f"Failed to get token. Status code: {response.status_code}, Response: {response.text}"
            )
            return ""

    except Exception as e:
        logger.error(f"Error creating API token: {e}")
        return ""


def make_emqx_api_request(
    base_url: str,
    api: str,
    username: str = None,
    password: str = None,
    method: str = "GET",
    data: str = None,
) -> str:
    """Make an API request to the EMQX broker.

    Args:
        base_url: The base URL of the EMQX broker.
        api: The API endpoint to call, e.g., "/api/v5/nodes"
        username: Username for basic auth
        password: Password for basic auth
        method: The HTTP method to use (GET, POST, etc.)
        data: Optional data to send with the request

    Returns:
        The JSON response from the EMQX API
    """

    # Create the complete URL
    url = f"{base_url}{api}"

    logger.info(f"make_emqx_api_request({url})")

    # Create the request
    headers = {"Content-Type": "application/json"}
    req = urllib.request.Request(url, method=method, headers=headers)

    # Add auth header if credentials provided
    if username and password:
        # Get a token using username/password from cache or login
        token = emqx_login(base_url, username, password)
        if token:
            req.add_header("Authorization", f"Bearer {token}")
        else:
            logging.warning("Failed to get token, request will likely fail")
    else:
        logging.warning("No authentication provided for EMQX API request")

    # Add data if provided
    if data and method != "GET":
        req.data = json.dumps(data).encode("utf-8")

    try:
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as e:
        error_msg = f"EMQX API request {method} {url} failed: {str(e)}"
        logging.error(error_msg)
        if hasattr(e, "read"):
            error_response = e.read().decode("utf-8")
            logging.error(f"Error response: {error_response}")
        raise Exception(error_msg)
