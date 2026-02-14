# Contributing to AgentOS

Thanks for your interest in contributing!

## Getting Started

1. **Fork** the repository
2. **Clone** your fork: `git clone https://github.com/YOUR_USERNAME/agentic-patterns.git`
3. **Create a branch**: `git checkout -b feature/your-feature`
4. **Install dependencies**: `pip install -e ".[dev]"`

## Development

```bash
# Run tests
pytest tests/ -v

# Lint
ruff check .

# Format
ruff format .
```

## Pull Requests

1. Keep PRs focused — one feature or fix per PR
2. Add tests for new functionality
3. Ensure all tests pass before submitting
4. Write a clear description of what your PR does

## Adding a New Vertical

See [Creating Verticals](docs/creating-verticals.md) for the full guide. The `verticals/starter/` template gives you a skeleton to start from.

## Code Style

- Python 3.11+
- Type hints on all public functions
- Async-first patterns (FastAPI, SQLAlchemy async)
- Pydantic models for data validation

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
