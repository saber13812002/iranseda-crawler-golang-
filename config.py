"""
Configuration management for different environments
Manages database connections and other settings for local vs server environments
"""

import os
from pathlib import Path
from typing import Dict, Any

class Config:
    """Base configuration class"""
    
    def __init__(self):
        self.environment = os.getenv('ENVIRONMENT', 'local')
        self.load_config()
    
    def load_config(self):
        """Load configuration based on environment"""
        if self.environment == 'server':
            self.load_server_config()
        elif self.environment == 'production':
            self.load_production_config()
        else:
            self.load_local_config()
    
    def load_local_config(self):
        """Local development configuration"""
        self.db_config = {
            'host': os.getenv('DB_HOST', 'localhost'),
            'port': int(os.getenv('DB_PORT', '3306')),
            'user': os.getenv('DB_USER', 'root'),
            'password': os.getenv('DB_PASS', ''),
            'database': os.getenv('DB_NAME', 'radio'),
            'charset': 'utf8mb4'
        }
        
        self.github_config = {
            'user': os.getenv('GITHUB_USER', 'saber13812002'),
            'repo': os.getenv('GITHUB_REPO', 'iranseda-crawler-golang-'),
            'branch': os.getenv('GITHUB_BRANCH', 'download-db')
        }
        
        self.paths = {
            'downloads': Path('downloads'),
            'docs': Path('docs'),
            'programs': Path('docs/programs')
        }
    
    def load_server_config(self):
        """Server configuration"""
        self.db_config = {
            'host': os.getenv('DB_HOST', '192.168.2.160'),
            'port': int(os.getenv('DB_PORT', '3306')),
            'user': os.getenv('DB_USER', 'n8nuser'),
            'password': os.getenv('DB_PASS', 'StrongPassword123!'),
            'database': os.getenv('DB_NAME', 'radio'),
            'charset': 'utf8mb4'
        }
        
        self.github_config = {
            'user': os.getenv('GITHUB_USER', 'saber13812002'),
            'repo': os.getenv('GITHUB_REPO', 'iranseda-crawler-golang-'),
            'branch': os.getenv('GITHUB_BRANCH', 'download-db')
        }
        
        self.paths = {
            'downloads': Path('/mnt/data/saberprojects/iranseda-crawler-golang-/downloads'),
            'docs': Path('/mnt/data/saberprojects/iranseda-crawler-golang-/docs'),
            'programs': Path('/mnt/data/saberprojects/iranseda-crawler-golang-/docs/programs')
        }
    
    def load_production_config(self):
        """Production configuration"""
        self.db_config = {
            'host': os.getenv('DB_HOST'),
            'port': int(os.getenv('DB_PORT', '3306')),
            'user': os.getenv('DB_USER'),
            'password': os.getenv('DB_PASS'),
            'database': os.getenv('DB_NAME'),
            'charset': 'utf8mb4'
        }
        
        self.github_config = {
            'user': os.getenv('GITHUB_USER'),
            'repo': os.getenv('GITHUB_REPO'),
            'branch': os.getenv('GITHUB_BRANCH')
        }
        
        self.paths = {
            'downloads': Path(os.getenv('DOWNLOADS_PATH', 'downloads')),
            'docs': Path(os.getenv('DOCS_PATH', 'docs')),
            'programs': Path(os.getenv('PROGRAMS_PATH', 'docs/programs'))
        }
    
    def get_db_connection_string(self) -> str:
        """Get database connection string for Go programs"""
        return f"{self.db_config['user']}:{self.db_config['password']}@tcp({self.db_config['host']}:{self.db_config['port']})/{self.db_config['database']}"
    
    def get_github_raw_url(self, relative_path: str) -> str:
        """Generate GitHub raw URL"""
        import urllib.parse
        encoded_path = urllib.parse.quote(relative_path.replace(os.sep, '/'))
        return f"https://raw.githubusercontent.com/{self.github_config['user']}/{self.github_config['repo']}/{self.github_config['branch']}/{encoded_path}"
    
    def print_config(self):
        """Print current configuration (without sensitive data)"""
        print(f"🔧 Environment: {self.environment}")
        print(f"📊 Database: {self.db_config['host']}:{self.db_config['port']}/{self.db_config['database']}")
        print(f"👤 DB User: {self.db_config['user']}")
        print(f"🐙 GitHub: {self.github_config['user']}/{self.github_config['repo']}@{self.github_config['branch']}")
        print(f"📁 Downloads: {self.paths['downloads']}")
        print(f"📄 Docs: {self.paths['docs']}")

# Global config instance
config = Config()

def get_config() -> Config:
    """Get the global configuration instance"""
    return config
