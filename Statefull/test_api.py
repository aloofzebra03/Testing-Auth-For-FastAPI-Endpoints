"""
Test script for the Stateful Joke Generation API
Run the server first with: python main.py
Then run this script: python test_api.py
"""

import requests
import time
import json

BASE_URL = "http://localhost:8000"

def print_response(title, response):
    """Pretty print API response."""
    print(f"\n{'='*60}")
    print(f"{title}")
    print(f"{'='*60}")
    print(f"Status Code: {response.status_code}")
    try:
        print(json.dumps(response.json(), indent=2))
    except:
        print(response.text)
    print(f"{'='*60}\n")

def test_health():
    """Test health endpoint."""
    print("🔍 Testing /health endpoint...")
    response = requests.get(f"{BASE_URL}/health")
    print_response("Health Check", response)
    return response.status_code == 200

def test_start():
    """Test start endpoint."""
    print("🚀 Testing /start endpoint...")
    payload = {
        "topic": "artificial intelligence",
        "thread_id": "test_thread_1"
    }
    response = requests.post(f"{BASE_URL}/start", json=payload)
    print_response("Start Joke Generation", response)
    return response.status_code == 200

def test_status():
    """Test status endpoint."""
    print("📊 Testing /status endpoint...")
    payload = {
        "thread_id": "test_thread_1"
    }
    response = requests.post(f"{BASE_URL}/status", json=payload)
    print_response("Check Thread Status", response)
    return response.status_code == 200

def test_continue():
    """Test continue endpoint."""
    print("➡️ Testing /continue endpoint...")
    payload = {
        "thread_id": "test_thread_1"
    }
    response = requests.post(f"{BASE_URL}/continue", json=payload)
    print_response("Continue with Explanation", response)
    return response.status_code == 200

def test_restart():
    """Test restarting with same thread_id."""
    print("🔄 Testing restart with same thread_id...")
    payload = {
        "topic": "machine learning",
        "thread_id": "test_thread_1"
    }
    response = requests.post(f"{BASE_URL}/start", json=payload)
    print_response("Restart with New Topic", response)
    return response.status_code == 200

def test_invalid_thread():
    """Test continue with invalid thread_id."""
    print("❌ Testing /continue with invalid thread_id...")
    payload = {
        "thread_id": "non_existent_thread"
    }
    response = requests.post(f"{BASE_URL}/continue", json=payload)
    print_response("Continue with Invalid Thread (Should Fail)", response)
    return response.status_code == 404

def test_multiple_threads():
    """Test multiple simultaneous threads."""
    print("🔀 Testing multiple threads...")
    
    # Thread 2
    print("\n  Creating thread 2...")
    payload1 = {
        "topic": "cats",
        "thread_id": "test_thread_2"
    }
    response1 = requests.post(f"{BASE_URL}/start", json=payload1)
    print(f"  Thread 2 joke: {response1.json().get('joke', 'N/A')[:50]}...")
    
    # Thread 3
    print("\n  Creating thread 3...")
    payload2 = {
        "topic": "dogs",
        "thread_id": "test_thread_3"
    }
    response2 = requests.post(f"{BASE_URL}/start", json=payload2)
    print(f"  Thread 3 joke: {response2.json().get('joke', 'N/A')[:50]}...")
    
    # Check both threads are independent
    print("\n  Checking thread 2 status...")
    status2 = requests.post(f"{BASE_URL}/status", json={"thread_id": "test_thread_2"})
    print(f"  Thread 2 topic: {status2.json().get('topic')}")
    
    print("\n  Checking thread 3 status...")
    status3 = requests.post(f"{BASE_URL}/status", json={"thread_id": "test_thread_3"})
    print(f"  Thread 3 topic: {status3.json().get('topic')}")
    
    return response1.status_code == 200 and response2.status_code == 200

def run_all_tests():
    """Run all API tests."""
    print("\n" + "="*60)
    print("🧪 STATEFUL JOKE GENERATION API - TEST SUITE")
    print("="*60)
    
    tests = [
        ("Health Check", test_health),
        ("Start Endpoint", test_start),
        ("Status Endpoint", test_status),
        ("Continue Endpoint", test_continue),
        ("Status After Complete", test_status),
        ("Restart Thread", test_restart),
        ("Invalid Thread", test_invalid_thread),
        ("Multiple Threads", test_multiple_threads),
    ]
    
    results = []
    
    for test_name, test_func in tests:
        try:
            success = test_func()
            results.append((test_name, "✅ PASSED" if success else "❌ FAILED"))
        except requests.exceptions.ConnectionError:
            print(f"\n❌ ERROR: Cannot connect to server at {BASE_URL}")
            print("Make sure the server is running: python main.py")
            return
        except Exception as e:
            results.append((test_name, f"❌ ERROR: {str(e)}"))
        
        time.sleep(1)  # Small delay between tests
    
    # Print summary
    print("\n" + "="*60)
    print("📋 TEST SUMMARY")
    print("="*60)
    for test_name, result in results:
        print(f"{test_name:.<40} {result}")
    print("="*60)
    
    passed = sum(1 for _, result in results if "PASSED" in result)
    total = len(results)
    print(f"\n✨ Tests Passed: {passed}/{total}")
    
    if passed == total:
        print("🎉 All tests passed!")
    else:
        print("⚠️  Some tests failed. Check the output above.")

if __name__ == "__main__":
    try:
        run_all_tests()
    except KeyboardInterrupt:
        print("\n\n⏸️  Tests interrupted by user")
    except Exception as e:
        print(f"\n\n❌ Unexpected error: {str(e)}")
