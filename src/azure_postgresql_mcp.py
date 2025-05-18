"""
Copyright (c) Microsoft Corporation.
Licensed under the MIT License.
"""

"""
MCP server for Azure Database for PostgreSQL - Flexible Server.

This server exposes the following capabilities:

Tools:
- create_table: Creates a table in a database.
- drop_table: Drops a table in a database.
- get_databases: Gets the list of all the databases in a server instance.
- get_schemas: Gets schemas of all the tables.
- get_server_config: Gets the configuration of a server instance. [Available with Microsoft EntraID]
- get_server_parameter: Gets the value of a server parameter. [Available with Microsoft EntraID]
- query_data: Runs read queries on a database.
- update_values: Updates or inserts values into a table.

Resources:
- databases: Gets the list of all databases in a server instance.

To run the code using PowerShell, expose the following variables:

```
$env:PGHOST="<Fully qualified name of your Azure Database for PostgreSQL instance>"
$env:PGUSER="<Your Azure Database for PostgreSQL username>"
$env:PGPASSWORD="<Your password>"
```

Run the MCP Server using the following command:

```
python azure_postgresql_mcp.py
```

For detailed usage instructions, please refer to the README.md file.

"""

import json
import logging
import os
import sys
import urllib.parse

import psycopg
from azure.identity import DefaultAzureCredential
from azure.mgmt.postgresqlflexibleservers import PostgreSQLManagementClient
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.resources import FunctionResource

logger = logging.getLogger("azure")
logger.setLevel(logging.ERROR)


class AzurePostgreSQLMCP:
    def init(self):
        self.aad_in_use = os.environ.get("AZURE_USE_AAD")
        self.dbhost = self.get_environ_variable("PGHOST")
        self.dbuser = urllib.parse.quote(self.get_environ_variable("PGUSER"))

        if self.aad_in_use == "True":
            self.subscription_id = self.get_environ_variable("AZURE_SUBSCRIPTION_ID")
            self.resource_group_name = self.get_environ_variable("AZURE_RESOURCE_GROUP")
            self.server_name = (
                self.dbhost.split(".", 1)[0] if "." in self.dbhost else self.dbhost
            )
            self.credential = DefaultAzureCredential()
            self.postgresql_client = PostgreSQLManagementClient(
                self.credential, self.subscription_id
            )
        # Password initialization should be done after checking if AAD is in use
        # because then we need to get the token using the credential
        # which is only available after the above block.
        self.password = self.get_password()

    @staticmethod
    def get_environ_variable(name: str):
        """Helper function to get environment variable or raise an error."""
        value = os.environ.get(name)
        if value is None:
            raise EnvironmentError(f"Environment variable {name} not found.")
        return value

    def get_password(self) -> str:
        """Get password based on the auth mode set"""
        if self.aad_in_use == "True":
            return self.credential.get_token(
                "https://ossrdbms-aad.database.windows.net/.default"
            ).token
        else:
            return self.get_environ_variable("PGPASSWORD")

    def get_dbs_resource_uri(self):
        """Gets the resource URI exposed as MCP resource for getting list of dbs."""
        dbhost_normalized = (
            self.dbhost.split(".", 1)[0] if "." in self.dbhost else self.dbhost
        )
        return f"flexpg://{dbhost_normalized}/databases"

    def get_databases_internal(self) -> str:
        """Internal function which gets the list of all databases in a server instance."""
        try:
            with psycopg.connect(
                f"host={self.dbhost} user={self.dbuser} dbname='postgres' password={self.password}"
            ) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT datname FROM pg_database WHERE datistemplate = false;"
                    )
                    colnames = [desc[0] for desc in cur.description]
                    dbs = cur.fetchall()
                    return json.dumps(
                        {
                            "columns": str(colnames),
                            "rows": "".join(str(row) for row in dbs),
                        }
                    )
        except Exception as e:
            logger.error(f"Error: {str(e)}")
            return ""

    def get_databases_resource(self):
        """Gets list of databases as a resource"""
        return self.get_databases_internal()

    def get_databases(self):
        """Gets the list of all the databases in a server instance."""
        return self.get_databases_internal()

    def get_connection_uri(self, dbname: str) -> str:
        """Construct URI for connection."""
        return f"host={self.dbhost} dbname={dbname} user={self.dbuser} password={self.password}"

    def get_schemas(self, database: str):
        """Gets schemas of all the tables."""
        try:
            with psycopg.connect(self.get_connection_uri(database)) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT table_name, column_name, data_type FROM information_schema.columns "
                        "WHERE table_schema = 'public' ORDER BY table_name, ordinal_position;"
                    )
                    colnames = [desc[0] for desc in cur.description]
                    tables = cur.fetchall()
                    return json.dumps(
                        {
                            "columns": str(colnames),
                            "rows": "".join(str(row) for row in tables),
                        }
                    )
        except Exception as e:
            logger.error(f"Error: {str(e)}")
            return ""

    def query_data(self, dbname: str, s: str) -> str:
        """Runs read queries on a database."""
        try:
            with psycopg.connect(self.get_connection_uri(dbname)) as conn:
                with conn.cursor() as cur:
                    cur.execute(s)
                    rows = cur.fetchall()
                    colnames = [desc[0] for desc in cur.description]
                    return json.dumps(
                        {
                            "columns": str(colnames),
                            "rows": ",".join(str(row) for row in rows),
                        }
                    )
        except Exception as e:
            logger.error(f"Error: {str(e)}")
            return ""

    def exec_and_commit(self, dbname: str, s: str) -> None:
        """Internal function to execute and commit transaction."""
        try:
            with psycopg.connect(self.get_connection_uri(dbname)) as conn:
                with conn.cursor() as cur:
                    cur.execute(s)
                    conn.commit()
        except Exception as e:
            logger.error(f"Error: {str(e)}")

    def update_values(self, dbname: str, s: str):
        """Updates or inserts values into a table."""
        self.exec_and_commit(dbname, s)

    def create_table(self, dbname: str, s: str):
        """Creates a table in a database."""
        self.exec_and_commit(dbname, s)

    def drop_table(self, dbname: str, s: str):
        """Drops a table in a database."""
        self.exec_and_commit(dbname, s)

    def get_server_config(self) -> str:
        """Gets the configuration of a server instance. [Available with Microsoft EntraID]"""
        if self.aad_in_use:
            try:
                server = self.postgresql_client.servers.get(
                    self.resource_group_name, self.server_name
                )
                return json.dumps(
                    {
                        "server": {
                            "name": server.name,
                            "location": server.location,
                            "version": server.version,
                            "sku": server.sku.name,
                            "storage_profile": {
                                "storage_size_gb": server.storage.storage_size_gb,
                                "backup_retention_days": server.backup.backup_retention_days,
                                "geo_redundant_backup": server.backup.geo_redundant_backup,
                            },
                        },
                    }
                )
            except Exception as e:
                logger.error(f"Failed to get PostgreSQL server configuration: {e}")
                raise e

        else:
            raise NotImplementedError(
                "This tool is available only with Microsoft EntraID"
            )

    def get_server_parameter(self, parameter_name: str) -> str:
        """Gets the value of a server parameter. [Available with Microsoft EntraID]"""
        if self.aad_in_use:
            try:
                configuration = self.postgresql_client.configurations.get(
                    self.resource_group_name, self.server_name, parameter_name
                )
                return json.dumps(
                    {"param": configuration.name, "value": configuration.value}
                )
            except Exception as e:
                logger.error(
                    f"Failed to get PostgreSQL server parameter '{parameter_name}': {e}"
                )
                raise e
        else:
            raise NotImplementedError(
                "This tool is available only with Microsoft EntraID"
            )


if __name__ == "__main__":
    mcp = FastMCP("Flex PG Explorer")
    azure_pg_mcp = AzurePostgreSQLMCP()
    azure_pg_mcp.init()
    mcp.add_tool(azure_pg_mcp.get_databases)
    mcp.add_tool(azure_pg_mcp.get_schemas)
    mcp.add_tool(azure_pg_mcp.query_data)
    mcp.add_tool(azure_pg_mcp.update_values)
    mcp.add_tool(azure_pg_mcp.create_table)
    mcp.add_tool(azure_pg_mcp.drop_table)
    mcp.add_tool(azure_pg_mcp.get_server_config)
    mcp.add_tool(azure_pg_mcp.get_server_parameter)
    databases_resource = FunctionResource(
        name=azure_pg_mcp.get_dbs_resource_uri(),
        uri=azure_pg_mcp.get_dbs_resource_uri(),
        description="List of databases in the server",
        mime_type="application/json",
        fn=azure_pg_mcp.get_databases_resource,
    )

    # Add the resource to the MCP server
    mcp.add_resource(databases_resource)
    mcp.run()
