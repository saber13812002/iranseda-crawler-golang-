#!/usr/bin/env python3
"""
Environment-aware script to run the site generator
Usage:
    python run_generator.py                    # Uses local config
    python run_generator.py --env server      # Uses server config
    python run_generator.py --env production  # Uses production config
"""

import argparse
import os
import sys
from pathlib import Path

def load_env_file(env_file):
    """Load environment variables from a file"""
    if not Path(env_file).exists():
        print(f"❌ Environment file not found: {env_file}")
        return False
    
    with open(env_file, 'r') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#'):
                if '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key.strip()] = value.strip()
    return True

def main():
    parser = argparse.ArgumentParser(description='Run site generator with different environments')
    parser.add_argument('--env', choices=['local', 'server', 'production'], 
                       default='local', help='Environment to use')
    parser.add_argument('--env-file', help='Custom environment file path')
    
    args = parser.parse_args()
    
    # Load environment variables
    if args.env_file:
        if not load_env_file(args.env_file):
            sys.exit(1)
    else:
        env_file = f"env.{args.env}.example"
        if not load_env_file(env_file):
            print(f"⚠️  Using default environment: {args.env}")
        else:
            print(f"✅ Loaded environment from: {env_file}")
    
    # Set environment
    os.environ['ENVIRONMENT'] = args.env
    
    # Import and run generator
    try:
        from generate_site import generate
        generate()
    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("Make sure generate_site.py and config.py are in the same directory")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error running generator: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
