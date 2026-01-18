#!/usr/bin/env python3
"""
Run the Flask webapp for local development.

Usage:
  python run_web.py [--host HOST] [--port PORT] [--debug]
"""
import os
import sys
import argparse


def main():
    parser = argparse.ArgumentParser(description="Run the webapp Flask server")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind to")
    parser.add_argument("--port", type=int, default=5000, help="Port to listen on")
    parser.add_argument("--debug", action="store_true", help="Enable Flask debug mode")
    args = parser.parse_args()

    repo_root = os.path.dirname(__file__)
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)

    try:
        from webapp.app import app
    except Exception as e:
        print("Failed to import webapp.app:", e)
        raise

    app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()
