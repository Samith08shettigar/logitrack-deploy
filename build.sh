#!/usr/bin/env bash
# Exit immediately if a command exits with a non-zero status
set -o errexit

# Install required dependencies
pip install --upgrade pip
pip install -r requirements.txt
