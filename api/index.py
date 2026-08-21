import os
import sys

# Add parent directory to path so modules like app, routes, database are discoverable
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app
