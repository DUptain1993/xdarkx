# OSRipper Test Suite

This directory contains the test suite for OSRipper, covering unit and integration tests for payload generation, obfuscation, and compilation functionality.

## Test Structure

- `test_main.py` - Unit tests for validation and input functions in main.py
- `test_generator.py` - Unit tests for payload generation functions and Generator class
- `test_integration.py` - Integration tests for complete workflow with mocked dependencies

## Running Tests

### Run all tests
```bash
pytest
```

### Run specific test file
```bash
pytest tests/test_main.py
pytest tests/test_generator.py
pytest tests/test_integration.py
```

### Run specific test class or function
```bash
pytest tests/test_main.py::TestValidatePort
pytest tests/test_main.py::TestValidatePort::test_valid_port_min_range
```

### Run with coverage report
```bash
pytest --cov=src/osripper --cov-report=html
```

### Run with verbose output
```bash
pytest -v
```

### Run and stop on first failure
```bash
pytest -x
```

## Test Coverage

The test suite covers:

- Input validation functions (validate_port, validate_ip, get_user_input)
- Payload generation (bind, reverse SSL, custom, BTC miner)
- Generator class initialization and methods
- Obfuscation workflow (mocked)
- Compilation workflow (mocked)
- File cleanup and results management
- Error handling and edge cases
- Complete integration workflows

## Requirements

Install test dependencies:
```bash
pip install -r requirements.txt
```

The following packages are required:
- pytest >= 7.4.0
- pytest-cov >= 4.1.0
- pytest-mock >= 3.11.0

## Configuration

Test configuration is defined in `pytest.ini` at the project root.

