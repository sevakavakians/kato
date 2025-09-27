#!/usr/bin/env python3
"""
Test script to verify session management fixes
This tests the specific bugs that were fixed:
1. Session retrieval (GET /v2/sessions/{id})
2. Session-scoped operations
3. Session isolation
"""

import requests
import json
import time
import sys

BASE_URL = "http://localhost:8001"

def test_session_retrieval_fix():
    """Test the main bug fix: session retrieval"""
    print("🧪 Testing Session Retrieval Fix...")
    
    # 1. Create session
    response = requests.post(f"{BASE_URL}/v2/sessions", 
                           json={"user_id": "test-retrieval", "metadata": {"test": "fix"}})
    
    if response.status_code != 200:
        print(f"❌ Session creation failed: {response.status_code}")
        return False
    
    session_data = response.json()
    session_id = session_data['session_id']
    print(f"✅ Created session: {session_id}")
    
    # 2. Test session retrieval (THE MAIN FIX)
    response = requests.get(f"{BASE_URL}/v2/sessions/{session_id}")
    
    if response.status_code != 200:
        print(f"❌ Session retrieval failed: {response.status_code}")
        print(f"Response: {response.text}")
        return False
    
    retrieved_data = response.json()
    if retrieved_data['session_id'] == session_id:
        print("✅ Session retrieval working correctly!")
        return True
    else:
        print(f"❌ Session ID mismatch: expected {session_id}, got {retrieved_data.get('session_id')}")
        return False

def test_session_operations():
    """Test session-scoped operations"""
    print("\n🧪 Testing Session-Scoped Operations...")
    
    # 1. Create session
    response = requests.post(f"{BASE_URL}/v2/sessions", 
                           json={"user_id": "test-ops", "metadata": {"test": "operations"}})
    
    if response.status_code != 200:
        print(f"❌ Session creation failed: {response.status_code}")
        return False
    
    session_data = response.json()
    session_id = session_data['session_id']
    print(f"✅ Created session: {session_id}")
    
    # 2. Make observation
    response = requests.post(f"{BASE_URL}/v2/sessions/{session_id}/observe", 
                           json={"strings": ["hello", "world"]})
    
    if response.status_code != 200:
        print(f"❌ Observation failed: {response.status_code}")
        print(f"Response: {response.text}")
        return False
    
    obs_result = response.json()
    print(f"✅ Observation successful: STM length = {obs_result['stm_length']}")
    
    # 3. Get STM
    response = requests.get(f"{BASE_URL}/v2/sessions/{session_id}/stm")
    
    if response.status_code != 200:
        print(f"❌ STM retrieval failed: {response.status_code}")
        return False
    
    stm_data = response.json()
    print(f"✅ STM retrieved: {stm_data['stm']}")
    
    return True

def test_session_isolation():
    """Test that sessions are properly isolated"""
    print("\n🧪 Testing Session Isolation...")
    
    # Create two sessions
    sessions = []
    for i in range(2):
        response = requests.post(f"{BASE_URL}/v2/sessions", 
                               json={"user_id": f"test-isolation-{i}", "metadata": {"test": "isolation"}})
        
        if response.status_code != 200:
            print(f"❌ Session {i} creation failed: {response.status_code}")
            return False
        
        session_data = response.json()
        sessions.append(session_data['session_id'])
        print(f"✅ Created session {i}: {sessions[i]}")
    
    # Add different data to each session
    test_data = [
        {"strings": ["session1", "data"]},
        {"strings": ["session2", "different"]}
    ]
    
    for i, session_id in enumerate(sessions):
        response = requests.post(f"{BASE_URL}/v2/sessions/{session_id}/observe", 
                               json=test_data[i])
        
        if response.status_code != 200:
            print(f"❌ Session {i} observation failed: {response.status_code}")
            return False
    
    # Verify each session has its own data
    for i, session_id in enumerate(sessions):
        response = requests.get(f"{BASE_URL}/v2/sessions/{session_id}/stm")
        
        if response.status_code != 200:
            print(f"❌ Session {i} STM retrieval failed: {response.status_code}")
            return False
        
        stm_data = response.json()
        # KATO sorts strings alphanumerically, so we need to sort our expected data
        expected_strings_sorted = sorted(test_data[i]["strings"])
        
        if stm_data['stm'] == [expected_strings_sorted]:
            print(f"✅ Session {i} isolation confirmed: {stm_data['stm']}")
        else:
            print(f"❌ Session {i} isolation failed: expected {[expected_strings_sorted]}, got {stm_data['stm']}")
            return False
    
    return True

def test_health_check():
    """Test that the service is healthy"""
    print("🧪 Testing Service Health...")
    
    response = requests.get(f"{BASE_URL}/v2/health")
    
    if response.status_code != 200:
        print(f"❌ Health check failed: {response.status_code}")
        return False
    
    health_data = response.json()
    if health_data.get('status') == 'healthy':
        print("✅ Service is healthy")
        return True
    else:
        print(f"❌ Service unhealthy: {health_data}")
        return False

def main():
    print("=" * 60)
    print("🔧 KATO v2.0 Session Management Fix Verification")
    print("=" * 60)
    
    tests = [
        ("Health Check", test_health_check),
        ("Session Retrieval Fix", test_session_retrieval_fix),
        ("Session Operations", test_session_operations),
        ("Session Isolation", test_session_isolation),
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        try:
            if test_func():
                passed += 1
            else:
                print(f"❌ {test_name} failed")
        except Exception as e:
            print(f"❌ {test_name} failed with exception: {e}")
    
    print("\n" + "=" * 60)
    print(f"📊 Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All session management fixes verified!")
        return 0
    else:
        print("⚠️  Some tests failed")
        return 1

if __name__ == "__main__":
    sys.exit(main())