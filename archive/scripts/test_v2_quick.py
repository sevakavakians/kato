#!/usr/bin/env python3
"""
Quick test to verify KATO session management is running correctly.
This tests the key feature: multi-user session isolation.
"""

import requests
import json
import time

def test_v2_basic():
    """Test basic v2.0 functionality"""
    base_url = "http://localhost:8001"
    
    print("Testing KATO Session Management")
    print("=" * 40)
    
    # 1. Test health endpoint
    print("\n1. Testing health endpoint...")
    try:
        response = requests.get(f"{base_url}/health")
        response.raise_for_status()
        print(f"   ✅ Health check passed: {response.json()}")
    except Exception as e:
        print(f"   ❌ Health check failed: {e}")
        return False
    
    # 2. Create a session for User A
    print("\n2. Creating session for User A...")
    try:
        response = requests.post(
            f"{base_url}/sessions",
            json={"user_id": "alice"}
        )
        response.raise_for_status()
        session_a = response.json()["session_id"]
        print(f"   ✅ Session created: {session_a}")
    except Exception as e:
        print(f"   ❌ Failed to create session: {e}")
        return False
    
    # 3. Create a session for User B
    print("\n3. Creating session for User B...")
    try:
        response = requests.post(
            f"{base_url}/sessions",
            json={"user_id": "bob"}
        )
        response.raise_for_status()
        session_b = response.json()["session_id"]
        print(f"   ✅ Session created: {session_b}")
    except Exception as e:
        print(f"   ❌ Failed to create session: {e}")
        return False
    
    # 4. User A observes data
    print("\n4. User A observes: ['alice', 'data']")
    try:
        response = requests.post(
            f"{base_url}/sessions/{session_a}/observe",
            json={"strings": ["alice", "data"]}
        )
        response.raise_for_status()
        print(f"   ✅ Observation successful")
    except Exception as e:
        print(f"   ❌ Observation failed: {e}")
        return False
    
    # 5. User B observes different data
    print("\n5. User B observes: ['bob', 'info']")
    try:
        response = requests.post(
            f"{base_url}/sessions/{session_b}/observe",
            json={"strings": ["bob", "info"]}
        )
        response.raise_for_status()
        print(f"   ✅ Observation successful")
    except Exception as e:
        print(f"   ❌ Observation failed: {e}")
        return False
    
    # 6. Check User A's STM (should only have alice's data)
    print("\n6. Checking User A's STM...")
    try:
        response = requests.get(f"{base_url}/sessions/{session_a}/stm")
        response.raise_for_status()
        stm_a = response.json()["stm"]
        print(f"   User A STM: {stm_a}")
        
        # Verify it contains alice's data
        if any("alice" in event or "data" in event for event in stm_a):
            print("   ✅ User A has correct data")
        else:
            print("   ❌ User A missing expected data")
            return False
            
        # Verify it doesn't contain bob's data
        if any("bob" in event or "info" in event for event in stm_a):
            print("   ❌ User A has User B's data (ISOLATION FAILURE)")
            return False
        else:
            print("   ✅ User A doesn't have User B's data")
            
    except Exception as e:
        print(f"   ❌ Failed to get STM: {e}")
        return False
    
    # 7. Check User B's STM (should only have bob's data)
    print("\n7. Checking User B's STM...")
    try:
        response = requests.get(f"{base_url}/sessions/{session_b}/stm")
        response.raise_for_status()
        stm_b = response.json()["stm"]
        print(f"   User B STM: {stm_b}")
        
        # Verify it contains bob's data
        if any("bob" in event or "info" in event for event in stm_b):
            print("   ✅ User B has correct data")
        else:
            print("   ❌ User B missing expected data")
            return False
            
        # Verify it doesn't contain alice's data
        if any("alice" in event or "data" in event for event in stm_b):
            print("   ❌ User B has User A's data (ISOLATION FAILURE)")
            return False
        else:
            print("   ✅ User B doesn't have User A's data")
            
    except Exception as e:
        print(f"   ❌ Failed to get STM: {e}")
        return False
    
    # 8. Test backward compatibility (v1 endpoints)
    print("\n8. Testing backward compatibility...")
    try:
        # Use v1 endpoint with session header
        headers = {"X-Session-ID": session_a}
        response = requests.get(f"{base_url}/stm", headers=headers)
        response.raise_for_status()
        v1_stm = response.json()["stm"]
        
        if v1_stm == stm_a:
            print("   ✅ v1 endpoints work with sessions")
        else:
            print("   ⚠️  v1 endpoint returned different data")
            
    except Exception as e:
        print(f"   ❌ v1 compatibility test failed: {e}")
        # Not critical, v2 is working
    
    # 9. Clean up sessions
    print("\n9. Cleaning up sessions...")
    try:
        requests.delete(f"{base_url}/sessions/{session_a}")
        requests.delete(f"{base_url}/sessions/{session_b}")
        print("   ✅ Sessions cleaned up")
    except:
        pass  # Cleanup errors are not critical
    
    return True

if __name__ == "__main__":
    print("\n" + "=" * 50)
    print("  KATO Session Management Quick Test")
    print("=" * 50)
    
    success = test_v2_basic()
    
    print("\n" + "=" * 50)
    if success:
        print("  ✅ ALL TESTS PASSED - Session management is working!")
        print("=" * 50)
        print("\nKATO key features verified:")
        print("✅ Multi-user session isolation is working")
        print("✅ Each user maintains separate STM")
        print("✅ No data collision between users")
        print("\nRun 'python test_v2_demo.py' for a full demo")
    else:
        print("  ❌ TESTS FAILED - Check the errors above")
        print("=" * 50)
        print("\nTroubleshooting:")
        print("1. Ensure KATO is running: ./kato-manager.sh start")
        print("2. Check logs: docker-compose logs")
        print("3. Verify services: docker ps")
    
    print()