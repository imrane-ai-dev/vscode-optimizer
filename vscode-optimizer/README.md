# VSCode Optimizer 🚀

> A lightweight, safe, and open-source utility to clean, speed up, and optimize your Visual Studio Code environment.

[![Python](https://img.shields.io/badge/Python-3.8%2B-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey)]()

VS Code becomes slow over time due to accumulated cache, logs, and unused extensions. **VSCode Optimizer** safely reclaims disk space and improves startup performance without touching your settings or projects.

### ✨ Features
- **Safe Cache Cleaning:** Clears `CachedData`, `Code Cache`, and logs without deleting settings
- **Smart Analysis:** Shows you how much space will be freed before deleting
- **Extension Health Check:** Detects heavy / unused extensions
- **One-Click Optimization:** Simple CLI for developers
- **Cross-Platform:** Works on Windows, macOS, and Linux

### 📦 Installation

```bash
git clone https://github.com/YOUR_USERNAME/vscode-optimizer.git
cd vscode-optimizer
pip install -r requirements.txt