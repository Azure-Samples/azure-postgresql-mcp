import logging
import unittest
from unittest.mock import MagicMock, patch

# Constants
NETWORK_ERROR_MESSAGE = "Network error"

from azure_postgresql_mcp import AzurePostgreSQLMCP


class TestAzurePostgreSQLMCPAADEnabled(unittest.TestCase):
    """Tests for AzurePostgreSQLMCP with AAD enabled."""

    @patch("azure_postgresql_mcp.DefaultAzureCredential")
    @patch("azure_postgresql_mcp.PostgreSQLManagementClient")
    def setUp(self, mock_postgresql_client, mock_credential):
        # Mock the credential and client
        mock_credential.return_value = MagicMock()
        mock_client_instance = MagicMock()
        mock_postgresql_client.return_value = mock_client_instance

        """Set up the AzurePostgreSQLMCP instance with AAD enabled."""
        with patch.dict(
            "os.environ",
            {
                "AZURE_USE_AAD": "True",
                "PGHOST": "test-host",
                "PGUSER": "test-user",
                "PGPASSWORD": "test-password",
                "AZURE_SUBSCRIPTION_ID": "test-subscription-id",
                "AZURE_RESOURCE_GROUP": "test-resource-group",
            },
        ):
            self.azure_pg_mcp = AzurePostgreSQLMCP()
            self.azure_pg_mcp.init()

    def test_get_server_config(self):
        mock_server = MagicMock()
        mock_server.name = "test-server"
        mock_server.location = "eastus"
        mock_server.version = "12"
        mock_server.sku.name = "Standard_D2s_v3"
        mock_server.storage.storage_size_gb = 100
        mock_server.backup.backup_retention_days = 7
        mock_server.backup.geo_redundant_backup = "Enabled"

        # Ensure the mocked server response is serializable
        self.azure_pg_mcp.postgresql_client.servers.get.return_value = mock_server
        # Call the method
        result = self.azure_pg_mcp.get_server_config()

        # Assert the result
        self.assertIn("test-server", result)
        self.assertIn("eastus", result)
        self.assertIn("12", result)
        self.assertIn("Standard_D2s_v3", result)
        self.assertIn("100", result)
        self.assertIn("7", result)
        self.assertIn("Enabled", result)

    def test_get_server_parameter(self):
        # Mock the configuration response
        mock_configuration = MagicMock()
        mock_configuration.name = "max_connections"
        mock_configuration.value = "100"

        self.azure_pg_mcp.postgresql_client.configurations.get.return_value = (
            mock_configuration
        )

        # Call the method
        result = self.azure_pg_mcp.get_server_parameter("max_connections")

        # Assert the result
        self.assertIn("max_connections", result)
        self.assertIn("100", result)


class TestAzurePostgreSQLMCPAADDisabled(unittest.TestCase):
    """Tests for AzurePostgreSQLMCP with AAD disabled."""

    def setUp(self):
        patcher = patch.dict(
            "os.environ",
            {
                "PGHOST": "test-host",
                "PGUSER": "test-user",
                "PGPASSWORD": "test-password",
            },
        )
        self.addCleanup(patcher.stop)
        patcher.start()
        self.azure_pg_mcp = AzurePostgreSQLMCP()
        self.azure_pg_mcp.init()

    @patch("psycopg.connect")
    def test_query_data(self, mock_connect):
        # Mock the cursor and its behavior
        mock_cursor = MagicMock()
        mock_cursor.description = [("col1",), ("col2",)]
        mock_cursor.fetchall.return_value = [(1, "value1"), (2, "value2")]

        mock_connect.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value = (
            mock_cursor
        )

        # Call the method
        result = self.azure_pg_mcp.query_data("test_db", "SELECT * FROM test_table;")

        # Assert the result
        self.assertIn("value1", result)
        self.assertIn("value2", result)

    @patch("psycopg.connect")
    def test_create_table(self, mock_connect):
        # Mock the connection and cursor
        mock_cursor = MagicMock()
        mock_connect.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value = (
            mock_cursor
        )

        # Call the method
        self.azure_pg_mcp.create_table("test_db", "CREATE TABLE test_table (id INT);")

        # Assert that the query was executed and committed
        mock_cursor.execute.assert_called_once_with("CREATE TABLE test_table (id INT);")
        mock_connect.return_value.__enter__.return_value.commit.assert_called_once()

    @patch("psycopg.connect")
    def test_drop_table(self, mock_connect):
        # Mock the connection and cursor
        mock_cursor = MagicMock()
        mock_connect.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value = (
            mock_cursor
        )

        # Call the method
        self.azure_pg_mcp.drop_table("test_db", "DROP TABLE test_table;")

        # Assert that the query was executed and committed
        mock_cursor.execute.assert_called_once_with("DROP TABLE test_table;")
        mock_connect.return_value.__enter__.return_value.commit.assert_called_once()


class TestAzurePostgreSQLMCPNetworkErrors(unittest.TestCase):
    """Tests for handling network errors in AzurePostgreSQLMCP."""

    @patch("azure_postgresql_mcp.DefaultAzureCredential")
    @patch("azure_postgresql_mcp.PostgreSQLManagementClient")
    def setUp(self, mock_postgresql_client, mock_credential):
        # Mock the credential and client
        mock_credential.return_value = MagicMock()
        mock_client_instance = MagicMock()
        mock_postgresql_client.return_value = mock_client_instance

        with patch.dict(
            "os.environ",
            {
                "PGHOST": "test-host",
                "PGUSER": "test-user",
                "PGPASSWORD": "test-password",
                "AZURE_SUBSCRIPTION_ID": "test-subscription-id",
                "AZURE_RESOURCE_GROUP": "test-resource-group",
                "AZURE_USE_AAD": "True",
            },
        ):
            self.azure_pg_mcp = AzurePostgreSQLMCP()
            self.azure_pg_mcp.init()

    @patch("psycopg.connect")
    def test_query_data_network_error(self, mock_connect):
        # Simulate a network error
        mock_connect.side_effect = Exception(NETWORK_ERROR_MESSAGE)

        # Call the method
        result = self.azure_pg_mcp.query_data("test_db", "SELECT * FROM test_table;")

        # Assert the result
        self.assertEqual(result, "")

    @patch("psycopg.connect")
    def test_create_table_network_error(self, mock_connect):
        # Simulate a network error
        mock_connect.side_effect = Exception("Network error")

        # Call the method
        self.azure_pg_mcp.create_table("test_db", "CREATE TABLE test_table (id INT);")

        # Assert that no exception was raised
        mock_connect.return_value.__enter__.return_value.commit.assert_not_called()

    def test_get_server_config_network_error(self):
        # Simulate a network error
        self.azure_pg_mcp.postgresql_client.servers.get.side_effect = Exception(
            NETWORK_ERROR_MESSAGE
        )

        with self.assertRaises(Exception) as context:
            self.azure_pg_mcp.get_server_config()

        # Assert the exception message
        self.assertEqual(str(context.exception), "Network error")

    def test_get_server_parameter_network_error(self):
        # Simulate a network error
        self.azure_pg_mcp.postgresql_client.configurations.get.side_effect = Exception(
            NETWORK_ERROR_MESSAGE
        )

        with self.assertRaises(Exception) as context:
            self.azure_pg_mcp.get_server_parameter("max_connections")

        # Assert the exception message
        self.assertEqual(str(context.exception), "Network error")


if __name__ == "__main__":
    unittest.main()
