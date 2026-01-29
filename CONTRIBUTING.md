# Contributing to Godot-Minds

Thank you for your interest in contributing to Godot-Minds! This document provides guidelines and instructions for contributing.

## 🚀 Getting Started

1. **Fork the repository** on GitHub
2. **Clone your fork** locally
3. **Create a branch** for your changes: `git checkout -b feature/your-feature-name`
4. **Make your changes** following our code style guidelines
5. **Test your changes** thoroughly
6. **Commit your changes** using conventional commit format
7. **Push to your fork** and submit a pull request

## 📝 Code Style

### Python (Backend)
- Follow PEP 8 style guide
- Use type hints for all functions
- Format with `black` and lint with `ruff`
- Run `mypy` for type checking
- Write docstrings for public APIs

### GDScript (Plugin)
- Use static typing (GDScript 2.0)
- Follow Godot naming conventions
- Keep files organized (signals → enums → exports → methods)
- Add comments for complex logic

## 🧪 Testing

- Write tests for new features
- Ensure all tests pass: `pytest tests/ -v`
- Aim for >80% code coverage
- Test both success and error cases

## 💬 Commit Messages

Use conventional commit format:
```
feat: add inline completion support
fix: resolve git diff parsing error
docs: update installation instructions
refactor: simplify AI provider interface
test: add tests for git service
```

Types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`

## 🔍 Pull Request Process

1. Update README.md if you've added features
2. Add tests for new functionality
3. Ensure all tests and linting pass
4. Update CHANGELOG.md (if applicable)
5. Request review from maintainers

## 🐛 Reporting Bugs

When reporting bugs, please include:
- Operating system and version
- Python version
- Godot version
- Steps to reproduce
- Expected vs actual behavior
- Error messages and logs

## 💡 Suggesting Features

Feature requests are welcome! Please:
- Check existing issues first
- Clearly describe the feature
- Explain the use case
- Consider implementation complexity

## 📜 Code of Conduct

- Be respectful and inclusive
- Welcome newcomers
- Focus on constructive feedback
- Assume good intentions

## 📄 License

By contributing, you agree that your contributions will be licensed under the MIT License.

## 🙏 Questions?

Open an issue or discussion on GitHub if you need help!
