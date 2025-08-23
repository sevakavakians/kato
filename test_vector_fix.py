#!/usr/bin/env python3
"""
Simple test to verify that vector classifiers are working correctly.
"""

import time
import requests
import subprocess
import json
import signal
import sys

def cleanup(signum=None, frame=None):
    """Clean up by stopping KATO."""
    print("\nStopping KATO...")
    subprocess.run(["./kato-manager.sh", "stop"], capture_output=True)
    sys.exit(0)

# Set up signal handler for clean exit
signal.signal(signal.SIGINT, cleanup)
signal.signal(signal.SIGTERM, cleanup)

def test_cvc_vectors():
    """Test CVC vector classifier."""
    print("\n=== Testing CVC Vector Classifier ===")
    
    # Start KATO with CVC classifier
    print("Starting KATO with CVC classifier...")
    result = subprocess.run([
        "./kato-manager.sh", "start",
        "--id", "p46b6b076c",
        "--name", "P1",
        "--classifier", "CVC",
        "--port", "8000"
    ], capture_output=True, text=True)
    
    if result.returncode != 0:
        print(f"Failed to start KATO: {result.stderr}")
        return False
    
    # Wait for KATO to be ready
    time.sleep(3)
    
    base_url = "http://localhost:8000/p46b6b076c"
    
    try:
        # Clear memory
        print("Clearing memory...")
        response = requests.post(f"{base_url}/clear_all_memory")
        assert response.json() == "all-cleared"
        
        # Observe vector
        print("Observing vector [[2,2]]...")
        response = requests.post(f"{base_url}/observe", json={
            "strings": [],
            "vectors": [[2, 2]],
            "emotives": {}
        })
        assert response.json()["status"] == "observed"
        
        # Observe string
        print("Observing string ['blue']...")
        response = requests.post(f"{base_url}/observe", json={
            "strings": ["blue"],
            "vectors": [],
            "emotives": {}
        })
        assert response.json()["status"] == "observed"
        
        # Get working memory
        print("Getting working memory...")
        response = requests.get(f"{base_url}/get_wm")
        wm = response.json()
        print(f"Working memory: {wm}")
        
        # Check that both vector hash and string are in WM
        assert len(wm) == 2, f"Expected 2 events in WM, got {len(wm)}"
        assert wm[1] == ["blue"], f"Expected second event to be ['blue'], got {wm[1]}"
        assert wm[0][0].startswith("VECTOR|"), f"Expected first event to have vector hash, got {wm[0]}"
        
        print("✓ CVC test passed!")
        return True
        
    except Exception as e:
        print(f"✗ CVC test failed: {e}")
        return False
    finally:
        # Stop KATO
        subprocess.run(["./kato-manager.sh", "stop"], capture_output=True)
        time.sleep(2)

def test_dvc_vectors():
    """Test DVC vector classifier."""
    print("\n=== Testing DVC Vector Classifier ===")
    
    # Start KATO with DVC classifier
    print("Starting KATO with DVC classifier...")
    result = subprocess.run([
        "./kato-manager.sh", "start",
        "--id", "p46b6b076d",
        "--name", "P2",
        "--classifier", "DVC",
        "--port", "8001"
    ], capture_output=True, text=True)
    
    if result.returncode != 0:
        print(f"Failed to start KATO: {result.stderr}")
        return False
    
    # Wait for KATO to be ready
    time.sleep(3)
    
    base_url = "http://localhost:8001/p46b6b076d"
    
    try:
        # Clear memory
        print("Clearing memory...")
        response = requests.post(f"{base_url}/clear_all_memory")
        assert response.json() == "all-cleared"
        
        # Observe vector and string together
        print("Observing vector [[0,1,2,3,4],[5,6,7,8,9]] and string ['more-symbol-placeholder']...")
        response = requests.post(f"{base_url}/observe", json={
            "strings": ["more-symbol-placeholder"],
            "vectors": [[0,1,2,3,4],[5,6,7,8,9]],
            "emotives": {}
        })
        assert response.json()["status"] == "observed"
        
        # Get working memory
        print("Getting working memory...")
        response = requests.get(f"{base_url}/get_wm")
        wm = response.json()
        print(f"Working memory: {wm}")
        
        # Check that WM is not empty and contains expected elements
        assert len(wm) > 0, "Working memory should not be empty"
        assert len(wm[0]) == 2, f"Expected 2 symbols in event, got {len(wm[0])}"
        
        # Check for vector hash and string (order may vary due to sorting)
        symbols = wm[0]
        assert "more-symbol-placeholder" in symbols, f"Expected 'more-symbol-placeholder' in symbols"
        vector_found = any(s.startswith("VECTOR|") for s in symbols)
        assert vector_found, f"Expected vector hash in symbols, got {symbols}"
        
        print("✓ DVC test passed!")
        return True
        
    except Exception as e:
        print(f"✗ DVC test failed: {e}")
        return False
    finally:
        # Stop KATO
        subprocess.run(["./kato-manager.sh", "stop"], capture_output=True)

if __name__ == "__main__":
    print("Testing vector classifier fixes...")
    
    cvc_passed = test_cvc_vectors()
    time.sleep(2)
    dvc_passed = test_dvc_vectors()
    
    print("\n" + "="*50)
    if cvc_passed and dvc_passed:
        print("✓ All vector tests passed!")
        sys.exit(0)
    else:
        print("✗ Some tests failed")
        if not cvc_passed:
            print("  - CVC test failed")
        if not dvc_passed:
            print("  - DVC test failed")
        sys.exit(1)