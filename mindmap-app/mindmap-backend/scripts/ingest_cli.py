#!/usr/bin/env python3
"""Simple CLI for ingestion tasks"""
import argparse

from app.services.ingestion_service import ingest_source


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--source", required=True)
    args = p.parse_args()
    print(ingest_source({"path": args.source}))


if __name__ == "__main__":
    main()
