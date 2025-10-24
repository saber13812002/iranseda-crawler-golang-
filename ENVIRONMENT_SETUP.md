# 🔧 Environment Configuration Guide

This guide explains how to manage different database configurations for local development, server, and production environments.

## 📁 Files Created

- `config.py` - Main configuration management system
- `env.local.example` - Local development configuration
- `env.server.example` - Server configuration  
- `env.production.example` - Production configuration
- `run_generator.py` - Environment-aware script runner
- `setup_env.sh` - Linux/Mac environment setup script
- `setup_env.ps1` - Windows PowerShell environment setup script

## 🚀 Quick Start

### Method 1: Using the Environment Runner (Recommended)

```bash


ENVIRONMENT=server python3 generate_site.py





























# Local development
python run_generator.py --env local

# Server environment
python run_generator.py --env server

# Production environment
python run_generator.py --env production

# Custom environment file
python run_generator.py --env-file my-custom.env
```

### Method 2: Using Environment Setup Scripts

**Windows (PowerShell):**
```powershell
# Setup local environment
.\setup_env.ps1 local

# Setup server environment
.\setup_env.ps1 server

# Then run generator
python generate_site.py
```

**Linux/Mac (Bash):**
```bash
# Setup local environment
./setup_env.sh local

# Setup server environment
./setup_env.sh server

# Then run generator
python generate_site.py
```

### Method 3: Manual Environment Variables

**Windows (PowerShell):**
```powershell
$env:ENVIRONMENT="server"
$env:DB_HOST="192.168.2.160"
$env:DB_USER="n8nuser"
$env:DB_PASS="StrongPassword123!"
$env:DB_NAME="radio"
python generate_site.py
```

**Linux/Mac (Bash):**
```bash
export ENVIRONMENT=server
export DB_HOST=192.168.2.160
export DB_USER=n8nuser
export DB_PASS=StrongPassword123!
export DB_NAME=radio
python generate_site.py
```

## 🔧 Configuration Details

### Local Development (`env.local.example`)
```env
ENVIRONMENT=local
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASS=
DB_NAME=radio
GITHUB_USER=saber13812002
GITHUB_REPO=iranseda-crawler-golang-
GITHUB_BRANCH=download-db
```

### Server Environment (`env.server.example`)
```env
ENVIRONMENT=server
DB_HOST=192.168.2.160
DB_PORT=3306
DB_USER=n8nuser
DB_PASS=StrongPassword123!
DB_NAME=radio
GITHUB_USER=saber13812002
GITHUB_REPO=iranseda-crawler-golang-
GITHUB_BRANCH=download-db
```

### Production Environment (`env.production.example`)
```env
ENVIRONMENT=production
DB_HOST=your-production-db-host
DB_PORT=3306
DB_USER=your-production-user
DB_PASS=your-production-password
DB_NAME=radio
GITHUB_USER=saber13812002
GITHUB_REPO=iranseda-crawler-golang-
GITHUB_BRANCH=main
```

## 🐳 Docker Environment

For Docker containers, you can pass environment variables:

```bash
docker run -e ENVIRONMENT=server \
           -e DB_HOST=192.168.2.160 \
           -e DB_USER=n8nuser \
           -e DB_PASS=StrongPassword123! \
           -e DB_NAME=radio \
           your-image
```

## 🔄 N8N Workflow Integration

### For Server Environment in N8N:

**SSH Command:**
```bash
cd /mnt/data/saberprojects/iranseda-crawler-golang-/
export ENVIRONMENT=server
export DB_HOST=192.168.2.160
export DB_USER=n8nuser
export DB_PASS=StrongPassword123!
export DB_NAME=radio
export GITHUB_USER=saber13812002
export GITHUB_REPO=iranseda-crawler-golang-
export GITHUB_BRANCH=download-db
python3 generate_site.py
```

**Working Directory:** `/mnt/data/saberprojects/iranseda-crawler-golang-/`

### For Local Development in N8N:

**SSH Command:**
```bash
cd /path/to/your/local/project
export ENVIRONMENT=local
export DB_HOST=localhost
export DB_USER=root
export DB_PASS=
export DB_NAME=radio
python3 generate_site.py
```

## 🔍 Configuration Validation

The system will show you the current configuration when running:

```
🔧 Configuration:
🔧 Environment: server
📊 Database: 192.168.2.160:3306/radio
👤 DB User: n8nuser
🐙 GitHub: saber13812002/iranseda-crawler-golang-@download-db
📁 Downloads: /mnt/data/saberprojects/iranseda-crawler-golang-/downloads
📄 Docs: /mnt/data/saberprojects/iranseda-crawler-golang-/docs
```

## 🛠 Custom Configuration

To create a custom environment:

1. Copy an existing example: `cp env.server.example env.myenv.example`
2. Modify the values in `env.myenv.example`
3. Run with: `python run_generator.py --env-file env.myenv.example`

## 🔒 Security Notes

- Never commit actual `.env` files to version control
- Use strong passwords for production environments
- Consider using environment variable injection in production
- The example files are safe to commit as they contain placeholder values

## 🐛 Troubleshooting

**Database Connection Issues:**
- Check if the database server is running
- Verify the host, port, and credentials
- Ensure the database exists and user has proper permissions

**Path Issues:**
- Verify the paths exist on the target system
- Check file permissions for the directories
- Ensure the working directory is correct

**Environment Loading Issues:**
- Check if the environment file exists
- Verify the file format (no spaces around `=`)
- Ensure the environment variable names match exactly
