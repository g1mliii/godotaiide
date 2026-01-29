# Security Policy

## 🔒 Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.x.x   | :white_check_mark: |

## 🚨 Reporting a Vulnerability

**Please do not report security vulnerabilities through public GitHub issues.**

If you discover a security vulnerability, please send an email to **security@example.com** with:

1. Description of the vulnerability
2. Steps to reproduce
3. Potential impact
4. Suggested fix (if available)

You should receive a response within 48 hours. We'll work with you to understand and address the issue promptly.

## 🛡️ Security Best Practices

### For Users

1. **API Keys**: Never commit `.env` files or hardcode API keys
2. **Updates**: Keep Godot-Minds and its dependencies up to date
3. **Permissions**: Review file system access permissions
4. **Network**: Use the backend server only on trusted networks

### For Contributors

1. **Dependencies**: Keep `requirements.txt` up to date and audit for vulnerabilities
2. **Input Validation**: Always validate and sanitize user inputs
3. **Secrets**: Use environment variables for sensitive data
4. **Code Review**: Security-sensitive changes require thorough review

## 🔐 Known Limitations

- API keys are stored in `.env` files (use proper file permissions)
- WebSocket connections are not encrypted by default (use reverse proxy with TLS for production)
- Local Ollama mode sends code to localhost (ensure Ollama is from trusted source)

## 📋 Security Checklist

- [x] `.env` files in `.gitignore`
- [x] CORS configuration for backend
- [x] Input validation on API endpoints
- [ ] Rate limiting (planned for v1.0)
- [ ] TLS/SSL support (planned for v1.0)
- [ ] Code signing for releases (planned for v1.0)

## 🆕 Security Updates

Security updates will be released as patch versions and announced in:
- GitHub Security Advisories
- Release notes
- Project README

Thank you for helping keep Godot-Minds secure!
