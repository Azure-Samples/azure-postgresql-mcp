# Running Tests for Azure PostgreSQL MCP

To run the tests, first ensure you have `pytest` installed. You can install it using:

```bash
pip install pytest
```

To execute the tests, use the following command:

```bash
PYTHONPATH=src pytest --color=yes -v
```

Error logs will be written to `tests/test_errors.log` as configured in `pytest.ini`.
