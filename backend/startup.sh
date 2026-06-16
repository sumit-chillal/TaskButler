#!/bin/bash
echo "Starting TaskButler Backend..."
cd backend
source venv/bin/activate 2>/dev/null || true
pip install -r requirements.txt -q
python -m src.main &
echo "Backend started on port 8000"
