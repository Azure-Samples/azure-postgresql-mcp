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
import os
import sys
import urllib.parse

import psycopg
from azure.identity import DefaultAzureCredential
from azure.mgmt.postgresqlflexibleservers import PostgreSQLManagementClient
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("Flex PG Explorer")

import logging

logger = logging.getLogger("azure")
logger.setLevel(logging.ERROR)


def get_environ_variable(name: str):
    """Helper function to get environment variable or raise an error."""
    value = os.environ.get(name)
    if value is None:
        raise EnvironmentError(f"Environment variable {name} not found.")
    return value


aad_in_use = os.environ.get("AZURE_USE_AAD")
dbhost = get_environ_variable("PGHOST")
dbuser = urllib.parse.quote(get_environ_variable("PGUSER"))

# The variables and other objects below are only needed in EntraID mode.
if aad_in_use:
    subscription_id = get_environ_variable("AZURE_SUBSCRIPTION_ID")
    resource_group_name = get_environ_variable("AZURE_RESOURCE_GROUP")
    server_name = dbhost.split(".", 1)[0] if "." in dbhost else dbhost
    credential = DefaultAzureCredential()
    postgresql_client = PostgreSQLManagementClient(credential, subscription_id)


def get_password() -> str:
    """Get password based on the auth mode set"""
    if aad_in_use:
        password = credential.get_token(
            "https://ossrdbms-aad.database.windows.net/.default"
        ).token
    else:
        password = get_environ_variable("PGPASSWORD")
    return password


password = get_password()


def get_dbs_resource_uri():
    """Gets the resource URI exposed as MCP resource for getting list of dbs."""
    dbhost_normalized = dbhost.split(".", 1)[0] if "." in dbhost else dbhost
    db_uri = f"flexpg://{dbhost_normalized}/databases"
    return db_uri


def get_databases_internal() -> str:
    """Internal function which gets the list of all databases in a server instance."""
    try:
        with psycopg.connect(
            f"host={dbhost} user={dbuser} dbname='postgres' password={password}"
        ) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT datname FROM pg_database WHERE datistemplate = false;"
                )
                colnames = [desc[0] for desc in cur.description]
                dbs = cur.fetchall()
                ret = json.dumps(
                    {"columns": str(colnames), "rows": "".join(str(row) for row in dbs)}
                )
    except Exception as e:
        print(f"Error: {str(e)}")
        ret = ""
    return ret


@mcp.resource(get_dbs_resource_uri())
def get_databases_resource():
    """Gets list of databases as a resource"""
    return get_databases_internal()


@mcp.tool()
def get_databases():
    """Gets the list of all the databases in a server instance."""
    return get_databases_internal()


# Function to construct URI for connection.
def get_connection_uri(dbname: str) -> str:
    # Read parameters from the environment
    db_uri = f"host={dbhost} dbname={dbname} user={dbuser} password={password}"
    return db_uri


# MCP reseource to send back schema for all tables.
@mcp.tool()
def get_schemas(database: str):
    """Gets schemas of all the tables."""
    try:
        with psycopg.connect(get_connection_uri(database)) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT table_name, column_name, data_type FROM information_schema.columns "
                    "WHERE table_schema = 'public' ORDER BY table_name, ordinal_position;"
                )
                colnames = [desc[0] for desc in cur.description]
                tables = cur.fetchall()
                ret = json.dumps(
                    {
                        "columns": str(colnames),
                        "rows": "".join(str(row) for row in tables),
                    }
                )
    except Exception as e:
        print(f"Error: {str(e)}")
        ret = ""
    return ret


# MCP tool to query data.
@mcp.tool()
def query_data(dbname: str, s: str) -> str:
    """Runs read queries on a database."""
    try:
        with psycopg.connect(get_connection_uri(dbname)) as conn:
            with conn.cursor() as cur:
                cur.execute(s)
                rows = cur.fetchall()
                colnames = [desc[0] for desc in cur.description]
                ret = json.dumps(
                    {
                        "columns": str(colnames),
                        "rows": ",".join(str(row) for row in rows),
                    }
                )
    except Exception as e:
        print(f"Error: {str(e)}", file=sys.stderr)
        ret = ""
    return ret


# Internal function to execute and commit transaction.
def exec_and_commit(dbname: str, s: str) -> None:
    try:
        with psycopg.connect(get_connection_uri(dbname)) as conn:
            with conn.cursor() as cur:
                cur.execute(s)
                conn.commit()
    except Exception as e:
        print(f"Error: {str(e)}")


# MCP tool to update values in a table
@mcp.tool()
def update_values(dbname: str, s: str):
    """Updates or inserts values into a table."""
    exec_and_commit(dbname, s)


# MCP tool to create table in the database
@mcp.tool()
def create_table(dbname: str, s: str):
    """Creates a table in a database."""
    exec_and_commit(dbname, s)


# MCP tool to drop table from the database
@mcp.tool()
def drop_table(dbname: str, s: str):
    """Drops a table in a database."""
    exec_and_commit(dbname, s)


@mcp.tool()
def get_server_config() -> str:
    """Gets the configuration of a server instance. [Available with Microsoft EntraID]"""
    if aad_in_use:
        try:
            server = postgresql_client.servers.get(resource_group_name, server_name)
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
            print(f"Failed to get PostgreSQL server configuration: {e}")
            return None
    else:
        raise NotImplementedError("This tool is available only with Microsoft EntraID")


@mcp.tool()
def get_server_parameter(parameter_name: str) -> str:
    """Gets the value of a server parameter. [Available with Microsoft EntraID]"""
    if aad_in_use:
        try:
            configuration = postgresql_client.configurations.get(
                resource_group_name, server_name, parameter_name
            )
            return json.dumps(
                {"param": configuration.name, "value": configuration.value}
            )
        except Exception as e:
            print(f"Failed to get PostgreSQL server parameter '{parameter_name}': {e}")
            return None
    else:
        raise NotImplementedError("This tool is available only with Microsoft EntraID")


if __name__ == "__main__":
    mcp.run()
