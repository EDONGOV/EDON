"""Simple test runner for production mode tests."""

import sys
import os

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from edon_gateway.test_production_mode import run_production_mode_tests
    
    print("Starting production mode tests...")
    print("=" * 70)
    
    exit_code = run_production_mode_tests()
    
    sys.exit(exit_code)
except Exception as e:
    print(f"Error running tests: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
